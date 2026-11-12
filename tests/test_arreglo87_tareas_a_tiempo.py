"""Arreglo 87 (B3): cada tarea del horario de bots/MIGRACION.md mide si llegó a tiempo.

A tiempo = desde su hora del horario hasta el paso que usa su resultado (hora CDMX). La ronda ya medía lo suyo
y no cambia. Las tareas sin horario siguen contando como a tiempo, como antes.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR

from test_arreglo47_conciliar_ensayo_estado import _reg_tmp

CDMX = ZoneInfo("America/Mexico_City")


def _hora(h, m, dia=11):                  # 2026-11-11 es miércoles; el 15 es domingo y el 16 lunes
    return datetime(2026, 11, dia, h, m, tzinfo=CDMX)


def _ultima(r):
    return AR.leer_registro(r)[-1]["a_tiempo"]


@pytest.mark.parametrize("bot,tarea,ahora,esperado", [
    ("RADAR", "verificar", _hora(18, 3), True),
    ("RADAR", "verificar", _hora(18, 12), False),          # la ronda de las 6:10 ya no la pudo usar
    ("RADAR", "verificar", _hora(12, 0), False),           # antes de su hora
    ("ESTELA", "estela --foto", _hora(18, 6), True),
    ("ESTELA", "estela --foto", _hora(18, 10), False),
    ("EJECUTOR", "ronda --verificar", _hora(18, 20), True),
    ("EJECUTOR", "ronda --verificar", _hora(18, 40), False),
    ("CONTADOR", "conciliar", _hora(18, 26), True),
    ("CONTADOR", "conciliar", _hora(19, 0), False),
    ("CONTADOR", "reporte diario", _hora(18, 29), True),
    ("CONTADOR", "respaldo", _hora(18, 24), False),
    ("CONTADOR", "reporte semanal", _hora(18, 27, dia=15), True),     # domingo
    ("CONTADOR", "reporte semanal", _hora(18, 27, dia=16), False),    # lunes
    ("CONTADOR", "reporte semanal", datetime(2026, 11, 16, 0, 27, tzinfo=timezone.utc), True),  # = domingo 18:27 CDMX
    ("THE BOSS", "reanudar", _hora(3, 0), True),           # sin horario: como antes
    ("EJECUTOR", "registrar-llenado", _hora(3, 0), None),  # Arreglo 89: sin hora límite = sin medir
])
def test_cada_tarea_del_horario_mide_su_hora(reg, tmp_path, bot, tarea, ahora, esperado):
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, bot, tarea, True, ahora=ahora)
    assert _ultima(r) is esperado


def test_a_tiempo_explicito_se_respeta(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, "RADAR", "verificar", True, a_tiempo=False, ahora=_hora(18, 3))
    assert _ultima(r) is False
    AR.registrar_tarea(r, "THE BOSS", "ronda", True, a_tiempo=True, ahora=_hora(3, 0))
    assert _ultima(r) is True


def test_estado_bots_cuenta_las_tareas_tarde(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    antier = (datetime.now(CDMX) - timedelta(days=2)).replace(second=0, microsecond=0)   # dentro de los últimos 7 días
    AR.registrar_tarea(r, "CONTADOR", "conciliar", True, ahora=antier.replace(hour=18, minute=26))
    AR.registrar_tarea(r, "CONTADOR", "conciliar", True, ahora=antier.replace(hour=21, minute=0))
    assert CR.mostrar_estado(r, bots=True, dias=7) == 0
    assert "CONTADOR: 2 tareas, 50 % bien y a tiempo" in capsys.readouterr().out
