"""Arreglo 89: CENTINELA y `registrar-llenado` no tienen hora límite medida.

Se anotan con a_tiempo = null ("sin medir") y `estado --bots` no los cuenta como puntuales: el porcentaje
"bien y a tiempo" se saca solo de las tareas medidas. No se les inventa horario.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR

from test_arreglo47_conciliar_ensayo_estado import _reg_tmp

CDMX = ZoneInfo("America/Mexico_City")


def test_centinela_rechazado_se_ve_sin_medir(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, "CENTINELA", "vetos.json", False, "veto mal escrito")
    assert AR.leer_registro(r)[-1]["a_tiempo"] is None
    cal = AR.calificacion_bots(r, 7)["CENTINELA"]
    assert cal["tareas"] == 1 and cal["sin_medir"] == 1 and cal["a_tiempo"] == 0 and cal["rechazos"] == 1
    assert CR.mostrar_estado(r, bots=True, dias=7) == 0
    assert "CENTINELA: 1 tareas, sin medir, 1 archivos rechazados, 0 diferencias boleto/llenado" in capsys.readouterr().out


def test_registrar_llenado_no_cuenta_como_puntual(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, "EJECUTOR", "registrar-llenado", True, "cantidad 2 en vez de 1", diferencias=1)
    assert AR.leer_registro(r)[-1]["a_tiempo"] is None
    cal = AR.calificacion_bots(r, 7)["EJECUTOR"]
    assert cal["a_tiempo"] == 0 and cal["sin_medir"] == 1 and cal["diferencias"] == 1
    AR.registrar_tarea(r, "EJECUTOR", "ronda --verificar", True,
                       ahora=datetime.now(CDMX).replace(hour=18, minute=20, second=0, microsecond=0))
    assert AR.leer_registro(r)[-1]["a_tiempo"] is True
    assert CR.mostrar_estado(r, bots=True, dias=7) == 0
    assert ("EJECUTOR: 2 tareas, 100 % bien y a tiempo (de 1 medidas; 1 sin medir), 0 archivos rechazados, "
            "1 diferencias boleto/llenado") in capsys.readouterr().out


def test_a_tiempo_explicito_y_tareas_con_horario_no_cambian(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, "CENTINELA", "eventos.json", False, "x", a_tiempo=False)
    assert AR.leer_registro(r)[-1]["a_tiempo"] is False
    AR.registrar_tarea(r, "RADAR", "verificar", True, ahora=datetime(2026, 11, 11, 18, 3, tzinfo=CDMX))
    assert AR.leer_registro(r)[-1]["a_tiempo"] is True
    AR.registrar_tarea(r, "RADAR", "verificar", True, ahora=datetime(2026, 11, 11, 18, 12, tzinfo=CDMX))
    assert AR.leer_registro(r)[-1]["a_tiempo"] is False
    AR.registrar_tarea(r, "THE BOSS", "reanudar", True)             # otras sin horario: como antes
    assert AR.leer_registro(r)[-1]["a_tiempo"] is True
