"""Arreglo 107: el guardado en JSON de ejecutar_v2 no pierde resultados ni los ignora sin avisar.

Hallazgos de la revisión del 12/11/2026: pd.NA, np.datetime64, np.timedelta64 y Period no se podían guardar; un tipo
desconocido tiraba el resultado de un paso largo; los .pkl viejos se ignoraban sin avisar (el informe salía vacío y el
paso `veto` tronaba); y la escritura no usaba la segura de archivos.py. Sin red ni llaves.
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import sobreviviente
from sobreviviente import __main__ as MAIN
from sobreviviente import ejecutar_v2, informe_v2

from test_arreglo99_resultados_json import _igual

RAIZ = Path(__file__).resolve().parent.parent


class Raro:
    def __repr__(self):
        return "Raro()"


@pytest.fixture
def salida_v2(tmp_path, monkeypatch):
    carpeta = tmp_path / "v2"
    monkeypatch.setattr(ejecutar_v2, "SALIDA", carpeta)
    monkeypatch.setattr(ejecutar_v2.D, "ClienteBinance", lambda reg: "cliente-falso")   # sin red
    return carpeta


def test_los_tipos_que_faltaban_regresan_iguales(salida_v2):
    obj = {
        "entero_nulo": pd.Series([1, pd.NA, 3], dtype="Int64"),
        "booleano_nulo": pd.Series([True, pd.NA], dtype="boolean"),
        "texto_nulo": pd.Series(["a", pd.NA], dtype="string"),
        "na_suelto": pd.NA,
        "dia_np": np.datetime64("2024-01-01"),
        "ns_np": np.datetime64("2024-01-01T00:00:00.000000001"),
        "nat_np": np.datetime64("NaT", "ns"),
        "duracion_np": np.timedelta64(5, "D"),
        "duracion_py": timedelta(days=1, seconds=5, microseconds=7),
        "mes": pd.Period("2024-01", freq="M"),
        "trimestre": pd.Period("2024Q1", freq="Q-DEC"),
        "meses": pd.Series(pd.period_range("2024-01", periods=3, freq="M")),
        "por_mes": pd.DataFrame({"r": [1.5, -0.5]}, index=pd.period_range("2024-01", periods=2, freq="M")),
    }
    ejecutar_v2._guardar("auditoria", obj)
    leido = ejecutar_v2.cargar_resultado("auditoria")
    assert leido["na_suelto"] is pd.NA and np.isnat(leido["nat_np"]) and leido["nat_np"].dtype == obj["nat_np"].dtype
    for k in ("entero_nulo", "booleano_nulo", "texto_nulo", "meses", "por_mes"):
        _igual(obj[k], leido[k])
    for k in ("dia_np", "ns_np", "duracion_np", "duracion_py", "mes", "trimestre"):
        assert type(leido[k]) is type(obj[k]) and leido[k] == obj[k]
        assert getattr(leido[k], "dtype", None) == getattr(obj[k], "dtype", None)


def test_un_paso_largo_no_pierde_su_resultado_por_un_tipo_desconocido(reg, salida_v2, monkeypatch):
    from sobreviviente import estela as ES
    resultado = {"hay_efecto": False, "raro": Raro(), "lista": [1, Raro()], "curva": pd.Series([1.0, 2.0])}
    monkeypatch.setattr(ES, "ejecutar", lambda reg, cli, avisar: resultado)
    avisos = []
    ejecutar_v2.ejecutar(reg, ["estela"], avisar=avisos.append)
    assert avisos == ["⚠️ estela: 2 valor(es) de tipo Raro no se pudieron guardar en JSON y quedaron vacíos; "
                      "el resto sí se guardó."]
    leido = ejecutar_v2.cargar_resultado("estela")
    assert leido["hay_efecto"] is False and leido["raro"] is None and leido["lista"] == [1, None]
    _igual(resultado["curva"], leido["curva"])
    crudo = json.loads((salida_v2 / "estela.json").read_text(encoding="utf-8"))
    assert crudo["raro"] == {"__tipo__": "sin_guardar", "tipo": "Raro", "texto": "Raro()"}


def test_el_guardado_normal_sigue_siendo_estricto(salida_v2):
    with pytest.raises(TypeError, match="Raro"):
        ejecutar_v2._guardar("M1", {"x": Raro()})
    assert not salida_v2.exists() or list(salida_v2.iterdir()) == []


def test_usa_la_escritura_segura_y_su_copia(salida_v2):
    ejecutar_v2._guardar("M1", {"pasa": False})
    ejecutar_v2._guardar("M1", {"pasa": True})
    assert sorted(p.name for p in salida_v2.iterdir()) == ["M1.json", "M1.json.bak"]   # sin temporales a medias
    (salida_v2 / "M1.json").write_text("{dañado", encoding="utf-8")
    assert ejecutar_v2.cargar_resultado("M1") == {"pasa": False}                     # la copia anterior


@pytest.mark.parametrize("nombre,paso", [("M1", "motores"), ("M2_veto", "veto"), ("auditoria", "auditoria"),
                                         ("referencias", "referencias"), ("estela", "estela")])
def test_un_pkl_viejo_no_se_lee_y_dice_que_correr(salida_v2, nombre, paso):
    salida_v2.mkdir()
    (salida_v2 / f"{nombre}.pkl").write_bytes(b"no es un pickle; si se intentara leer, tronaria distinto")
    with pytest.raises(ejecutar_v2.FaltaResultado) as e:
        ejecutar_v2.cargar_resultado(nombre)
    assert str(e.value) == (f"salida/v2/{nombre}.pkl está en el formato viejo (pickle) y ya no se lee, porque leerlo "
                            f"puede correr código. Vuelve a correr ese paso: {sobreviviente.python_actual()} -m "
                            f"sobreviviente validar --v2 --pasos {paso}")


def test_si_tambien_esta_el_json_se_usa_el_json(salida_v2):
    ejecutar_v2._guardar("M1", {"pasa": True})
    (salida_v2 / "M1.pkl").write_bytes(b"viejo")
    assert ejecutar_v2.cargar_resultado("M1") == {"pasa": True}
    assert ejecutar_v2.cargar_resultado("M2") is None                                   # nunca se corrió: como antes


def test_el_informe_no_sale_vacio_con_un_pkl_viejo(reg, salida_v2, tmp_path):
    salida_v2.mkdir()
    (salida_v2 / "M1.pkl").write_bytes(b"viejo")
    destino = tmp_path / "VALIDACION_V2.md"
    with pytest.raises(ejecutar_v2.FaltaResultado):
        informe_v2.escribir(reg, destino)
    assert not destino.exists()


def test_veto_sin_resultado_previo_lo_dice_antes_de_cargar_nada(reg, salida_v2, monkeypatch):
    def no_debe_cargar(reg):
        raise AssertionError("cargó las velas antes de revisar que existan M1 y M2 sin veto")

    monkeypatch.setattr(ejecutar_v2, "mercado_diario", no_debe_cargar)
    ejecutar_v2._guardar("M1", {"ventanas": []})
    with pytest.raises(ejecutar_v2.FaltaResultado) as e:
        ejecutar_v2.ejecutar(reg, ["veto"], avisar=lambda *_: None)
    assert str(e.value) == ("Falta el resultado sin veto de M2 (salida/v2/). Corre antes: "
                            f"{sobreviviente.python_actual()} -m sobreviviente validar --v2 --pasos motores")


def test_el_comando_validar_lo_dice_con_una_x_y_no_escribe_el_informe(salida_v2, tmp_path, monkeypatch, capsys):
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")      # así "datos/" queda en la carpeta temporal
    monkeypatch.setattr(MAIN, "RAIZ", tmp_path)                                 # el informe iría a la carpeta temporal
    monkeypatch.setattr(ejecutar_v2, "ejecutar", lambda reg, pasos: None)
    salida_v2.mkdir()
    (salida_v2 / "M1.pkl").write_bytes(b"viejo")
    codigo = MAIN.main(["--reglamento", str(tmp_path / "reglamento.yaml"), "validar", "--v2", "--informe",
                        "--pasos", "estela"])
    salida = capsys.readouterr().out
    assert codigo == 1 and "❌ salida/v2/M1.pkl está en el formato viejo (pickle)" in salida
    assert "falló y NO terminó" not in salida                                   # no es un comando caído
    assert not (tmp_path / "VALIDACION_V2.md").exists()
    assert not (tmp_path / "datos" / "bots" / "registro.jsonl").exists()       # no se anota como falla de un bot
