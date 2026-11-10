"""Arreglo 42 (T11-1, R04): si CENTINELA o RADAR dejan de actualizar sus archivos, la ronda lo dice con ℹ️.

Solo informa: no activa MODO SEGURO ni quita el 👍."""
import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas

RAIZ = Path(__file__).resolve().parent.parent
AHORA = datetime(2026, 11, 12, 0, 10, tzinfo=timezone.utc)      # ronda del 11 de noviembre, 6:10 p. m. CDMX


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    return r


def _escribir(tmp_path, nombre, contenido):
    texto = contenido if isinstance(contenido, str) else json.dumps(contenido)
    (tmp_path / "datos" / nombre).write_text(texto, encoding="utf-8")


def _los_tres(tmp_path, fecha):
    _escribir(tmp_path, "vetos.json", {"actualizado": fecha, "vetos": []})
    _escribir(tmp_path, "eventos.json", {"actualizado": fecha, "eventos": []})
    _escribir(tmp_path, "exclusiones.json", {"actualizado": fecha, "exclusiones": []})


def test_vetos_sin_actualizado_da_una_linea_de_centinela(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _escribir(tmp_path, "vetos.json", {"vetos": []})
    avisos = P.avisos_bots_dormidos(r, AHORA)
    assert len(avisos) == 1
    assert avisos[0].startswith("ℹ️ CENTINELA no ha actualizado vetos.json (no trae 'actualizado'): ¿sigue revisando noticias?")
    assert "Pídele que ponga la fecha de hoy en 'actualizado' aunque no haya vetos." in avisos[0]


def test_actualizado_de_hace_3_dias_avisa(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    assert r.get("bots.max_horas_sin_actualizar") == 48
    _los_tres(tmp_path, "2026-11-08")
    avisos = P.avisos_bots_dormidos(r, AHORA)
    assert len(avisos) == 2                                                   # una línea por bot, no por archivo
    assert "ℹ️ CENTINELA no ha actualizado vetos.json/eventos.json desde 2026-11-08:" in avisos[0]
    assert "ℹ️ RADAR no ha actualizado exclusiones.json desde 2026-11-08:" in avisos[1]
    assert "aunque no haya exclusiones" in avisos[1]


def test_actualizado_de_hoy_o_de_ayer_no_avisa(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _los_tres(tmp_path, "2026-11-11")
    assert P.avisos_bots_dormidos(r, AHORA) == []
    _los_tres(tmp_path, "2026-11-10")                                         # un día sin tocar: todavía dentro de 48 h
    assert P.avisos_bots_dormidos(r, AHORA) == []
    _los_tres(tmp_path, "2026-11-11T17:55:00-06:00")                          # también vale fecha y hora
    assert P.avisos_bots_dormidos(r, AHORA) == []


@pytest.mark.parametrize("valor", ["ayer", 5, None, "", "11/11/2026", ["2026-11-11"]])
def test_actualizado_raro_avisa_sin_traceback(reg, tmp_path, valor):
    r = _reg_tmp(reg, tmp_path)
    _los_tres(tmp_path, "2026-11-11")
    _escribir(tmp_path, "vetos.json", {"actualizado": valor, "vetos": []})
    avisos = P.avisos_bots_dormidos(r, AHORA)
    assert len(avisos) == 1 and "CENTINELA no ha actualizado vetos.json (no trae 'actualizado')" in avisos[0]


def test_un_archivo_viejo_y_otro_sin_fecha(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _escribir(tmp_path, "vetos.json", {"actualizado": "2026-11-01", "vetos": []})
    _escribir(tmp_path, "eventos.json", {"eventos": []})
    avisos = P.avisos_bots_dormidos(r, AHORA)
    assert avisos == [a for a in avisos if "vetos.json/eventos.json desde 2026-11-01 (o no trae 'actualizado')" in a]
    assert len(avisos) == 1


def test_archivo_inexistente_o_danado_no_agrega_linea(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    assert P.avisos_bots_dormidos(r, AHORA) == []                             # no existe ninguno
    _escribir(tmp_path, "vetos.json", "{dañado")
    _escribir(tmp_path, "exclusiones.json", {"exclusiones": "no es lista"})
    assert P.avisos_bots_dormidos(r, AHORA) == []                             # dañados: ya tienen su aviso (modo seguro)


def test_ronda_con_centinela_dormido_informa_sin_modo_seguro_y_con_pulgar(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path)
    r.datos["estrategias"]["M0"]["estado"] = "APAGADA"
    k = _dia_marea_alta(r)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    _escribir(tmp_path, "vetos.json", {"vetos": []})                          # válido, pero CENTINELA no puso la fecha
    cli = ClienteFalso(tmp_path, _velas_completas(), k)
    ahora = (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()
    for vez in ("primera", "repetida"):
        assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0
        salida = capsys.readouterr().out
        assert ("ya corrió" in salida) == (vez == "repetida")
        assert "ℹ️ CENTINELA no ha actualizado vetos.json" in salida, vez
        assert "MODO SEGURO" not in salida and "👍 No necesito nada de ti." in salida, vez


class _ClienteVerificar:
    _spot_bloqueado = False

    def __init__(self, reg):
        pass

    def spot(self, ruta, params=None):
        return {}

    def futuros(self, ruta, params=None):
        raise D.ErrorDatos("bloqueado por región")


def test_cmd_verificar_deja_fila_de_radar(tmp_path, monkeypatch, capsys):
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")       # así "datos/" queda en la carpeta temporal
    monkeypatch.setattr(D, "ClienteBinance", _ClienteVerificar)
    assert MAIN.cmd_verificar(argparse.Namespace(reglamento=str(tmp_path / "reglamento.yaml"))) == 0
    filas = [json.loads(x) for x in (tmp_path / "datos" / "bots" / "registro.jsonl").read_text(encoding="utf-8").splitlines()]
    assert filas[-1]["bot"] == "RADAR" and filas[-1]["tarea"] == "verificar" and filas[-1]["ok"] is True

    def sin_conexion(self, ruta, params=None):
        raise D.ErrorDatos("sin internet")

    monkeypatch.setattr(_ClienteVerificar, "spot", sin_conexion)
    assert MAIN.cmd_verificar(argparse.Namespace(reglamento=str(tmp_path / "reglamento.yaml"))) == 1
    filas = [json.loads(x) for x in (tmp_path / "datos" / "bots" / "registro.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(filas) == 2 and filas[-1]["bot"] == "RADAR" and filas[-1]["ok"] is False
    assert "Traceback" not in capsys.readouterr().out


def test_validadores_aceptan_con_y_sin_actualizado(reg):
    vence = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")
    veto = {"simbolo": "GLOBAL", "razon": "hackeo grande", "vence": vence}
    evento = {"nombre": "Fed", "fecha_hora": "2026-12-09T13:00:00-06:00", "importancia": "ALTA"}
    exclusion = {"simbolo": "XYZUSDT", "razon": "MONITOREO"}
    for extra in ({}, {"actualizado": "2026-11-10"}, {"actualizado": "ayer"}):
        assert AR.validar_vetos({**extra, "vetos": [veto]}, reg) == []
        assert AR.validar_eventos({**extra, "eventos": [evento]}) == []
        assert AR.validar_exclusiones({**extra, "exclusiones": [exclusion]}) == []


# ---------------- Arreglo 60: una fecha del futuro no apaga el aviso ----------------

def test_actualizado_con_fecha_del_futuro_avisa(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _los_tres(tmp_path, "2026-11-11")
    _escribir(tmp_path, "vetos.json", {"actualizado": "2027-11-11", "vetos": []})       # año mal escrito
    avisos = P.avisos_bots_dormidos(r, AHORA)
    assert len(avisos) == 1
    assert "ℹ️ CENTINELA no ha actualizado vetos.json (trae una fecha del futuro): ¿sigue revisando noticias?" in avisos[0]


def test_la_fecha_de_manana_no_cuenta_como_futuro(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _los_tres(tmp_path, "2026-11-12")            # el bot usó la fecha UTC (ya es "mañana" a las 6 p. m. de CDMX): vale
    assert P.avisos_bots_dormidos(r, AHORA) == []
