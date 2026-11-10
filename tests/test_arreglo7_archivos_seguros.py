"""Arreglo 7: los archivos de estado se escriben sin quedar a medias y, si se dañan, se usa la copia anterior."""
import json

import pandas as pd
import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def test_escribir_guarda_la_version_anterior_como_bak(tmp_path):
    ruta = tmp_path / "estado.json"
    AR.escribir_json_seguro(ruta, {"v": 1})
    assert not (tmp_path / "estado.json.bak").exists()
    AR.escribir_json_seguro(ruta, {"v": 2})
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"v": 2}
    assert json.loads((tmp_path / "estado.json.bak").read_text(encoding="utf-8")) == {"v": 1}
    assert not list(tmp_path.glob("*.tmp")) and not list(tmp_path.glob("*.baktmp"))   # sin temporales sueltos


def test_no_pisa_una_copia_buena_con_una_danada(tmp_path):
    ruta = tmp_path / "estado.json"
    AR.escribir_json_seguro(ruta, {"v": 1})
    AR.escribir_json_seguro(ruta, {"v": 2})                 # .bak = v1
    ruta.write_text("{dañado", encoding="utf-8")
    AR.escribir_json_seguro(ruta, {"v": 3})                 # el actual está dañado: el .bak bueno se queda
    assert json.loads((tmp_path / "estado.json.bak").read_text(encoding="utf-8")) == {"v": 1}


def test_archivo_danado_con_bak_sano_usa_el_bak(tmp_path):
    ruta = tmp_path / "cartera_A.json"
    AR.escribir_json_seguro(ruta, {"v": 1})
    AR.escribir_json_seguro(ruta, {"v": 2})
    ruta.write_text('{"v": 2, "corta', encoding="utf-8")   # se cortó a medias
    AR.tomar_avisos()
    assert AR.leer_json_seguro(ruta) == {"v": 1}
    avisos = AR.tomar_avisos()
    assert avisos and "se usó la copia anterior de cartera_A.json" in avisos[0]


def test_archivo_danado_sin_bak_da_error_claro(tmp_path):
    ruta = tmp_path / "cartera_A.json"
    ruta.write_text("{dañado", encoding="utf-8")
    with pytest.raises(AR.ArchivoDanado, match="cartera_A.json está dañado"):
        AR.leer_json_seguro(ruta)


def test_estado_de_cartera_danado_usa_el_bak(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])
    P.ronda_cartera(r, "C", _datos_dia(r, k + 1)[0], [], [])     # ahora hay .bak (estado del día k)
    arch = tmp_path / "datos" / "papel" / "cartera_C.json"
    arch.write_text("{dañado", encoding="utf-8")
    est = P.cargar_estado(r, "C", "")
    assert est["cartera"] == "C" and est["ultimo_dia"] == f"{_datos_dia(r, k)[0].dia:%Y-%m-%d}"


def test_ronda_con_estado_danado_sin_bak_no_corre(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    (tmp_path / "datos" / "papel" / "cartera_A.json").write_text("{dañado", encoding="utf-8")
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 1
    salida = capsys.readouterr().out
    assert "❌ La ronda NO corrió: El archivo cartera_A.json está dañado" in salida
    assert "Traceback" not in salida
    assert AR.leer_registro(r)[-1]["ok"] is False


def test_la_ronda_escribe_con_copia_anterior(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    P.ronda(r, _datos_dia(r, k)[0])
    P.ronda(r, _datos_dia(r, k + 1)[0])
    assert (tmp_path / "datos" / "papel" / "referencias.json.bak").exists()
    assert (tmp_path / "datos" / "papel" / "cartera_C.json.bak").exists()
