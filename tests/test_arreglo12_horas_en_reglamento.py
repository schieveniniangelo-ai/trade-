"""Arreglo 12: los límites de hora de la ronda viven en el reglamento (mismos valores que antes)."""
from datetime import datetime, timezone

from sobreviviente import cli_ronda as CR
from sobreviviente import reglamento as RGL


def _utc(h, m):
    return datetime(2026, 11, 10, h, m, tzinfo=timezone.utc)


def test_reglamento_trae_los_mismos_valores():
    r = RGL.cargar()
    assert r.get("ronda.minuto_minimo_utc") == 5 and r.get("ronda.max_retraso_min") == 120


def test_con_el_reglamento_normal_todo_igual_que_antes(reg):
    assert CR.revisar_hora(reg, _utc(0, 4))["estado"] == "TEMPRANO"
    assert CR.revisar_hora(reg, _utc(0, 5))["estado"] == "OK"
    assert CR.revisar_hora(reg, _utc(2, 10))["estado"] == "OK"
    assert CR.revisar_hora(reg, _utc(2, 11))["estado"] == "FUERA_DE_HORA"


def test_sin_los_valores_usa_los_de_siempre(reg):
    datos = dict(reg.datos)
    datos["ronda"] = {k: v for k, v in reg.datos["ronda"].items() if k not in ("minuto_minimo_utc", "max_retraso_min")}
    r = RGL.Reglamento(datos=datos, ruta=reg.ruta)
    assert CR.revisar_hora(r, _utc(0, 4))["estado"] == "TEMPRANO"
    assert CR.revisar_hora(r, _utc(2, 11))["estado"] == "FUERA_DE_HORA"


def test_max_retraso_30_una_hora_tarde_es_fuera_de_hora(reg):
    r = reg.copia_con({"ronda.max_retraso_min": 30})
    h = CR.revisar_hora(r, _utc(1, 10))                       # 60 minutos después de las 00:10
    assert h["estado"] == "FUERA_DE_HORA" and h["retraso_min"] == 60
    assert CR.revisar_hora(r, _utc(0, 30))["estado"] == "OK"
