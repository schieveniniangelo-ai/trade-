"""Arreglo 137: nada se queda sin stop (cierra R1).

Una posición real con estado_stop distinto de ACTIVO, o con el stop ausente en la última foto, nunca pasa la noche: la
ronda siguiente emite el cierre urgente y las compras nuevas quedan bloqueadas hasta que Ángelo diga lo contrario con
`ajustar-capital-real` o `reanudar --cartera REAL`. `reanudar` con A, B y C sigue igual."""
import json
from datetime import timedelta

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_ronda as CR
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture

DIA2 = AHORA + timedelta(days=1)


def _boletos(r, dia):
    return json.loads(RR.archivo_boletos(r, dia).read_text(encoding="utf-8"))


def test_de_extremo_a_extremo(mundo, capsys):  # noqa: F811
    r, cfg, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    # Día 1: a la foto le falta el stop → conciliar lo marca SIN_STOP y bloquea compras
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    res = RE.conciliar(r, AHORA - timedelta(minutes=2))
    assert res["sin_stop"] == ["BTC"]
    est = RE.cargar_estado(r)
    assert est["posiciones"][0]["estado_stop"] == "SIN_STOP" and est["bloqueo_compras"]["motivo"] == "SIN STOP: BTC"
    # Día 2: EJECUTOR volvió a poner el stop (la foto ya lo trae), pero la posición sigue SIN_STOP: no pasa la noche
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()], ahora=DIA2 - timedelta(minutes=5))
    assert correr(ahora=DIA2) == 0
    (b,) = _boletos(r, "2026-11-16")
    assert b["accion"] == "CERRAR" and b["motivo"] == "SIN_STOP" and b["urgente"] is True
    salida = capsys.readouterr().out
    assert salida.startswith("❌ URGENTE: SIN_STOP en BTCUSDT") and "compras bloqueadas por SIN STOP: BTC" in salida
    # Se vende; aun sin posición, las compras siguen bloqueadas hasta que Ángelo diga
    RE.registrar_llenado(r, b["boleto_id"], "VENTA_LLENADA", cantidad=0.00012, precio=70000.0, comision=0.0084,
                         moneda_comision="USDT")
    assert RE.cargar_estado(r)["posiciones"] == [] and RE.cargar_estado(r)["bloqueo_compras"]
    dia3 = DIA2 + timedelta(days=1)
    usdt3 = USDT_CON_POS + 0.00012 * 70000 - 0.0084
    foto(cuenta(usdt=usdt3), [], ahora=dia3 - timedelta(minutes=5))
    assert correr(ahora=dia3) == 0 and _boletos(r, "2026-11-17") == []
    assert "compras bloqueadas" in capsys.readouterr().out
    # Ángelo reanuda: la ronda siguiente sí compra
    assert CR.reanudar(r, "REAL", "") == 2
    assert CR.reanudar(r, "real", "revisé: ya no hay BTC sin stop — Ángelo") == 0
    assert RE.cargar_estado(r)["bloqueo_compras"] is None
    dia4 = dia3 + timedelta(days=1)
    foto(cuenta(usdt=usdt3), [], ahora=dia4 - timedelta(minutes=5))
    assert correr(ahora=dia4) == 0
    assert [x["accion"] for x in _boletos(r, "2026-11-18")] == ["COMPRAR"]


def test_disparado_sin_llenar_tambien_cierra(mundo):  # noqa: F811
    r, cfg, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"),
                          "posiciones": [{**POS, "estado_stop": "DISPARADO_SIN_LLENAR"}]})
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0
    assert [(b["motivo"], b["urgente"]) for b in _boletos(r, "2026-11-15")] == [("STOP_SIN_LLENAR", True)]


def test_sin_foto_y_sin_stop_confirmado_igual_cierra(mundo):  # noqa: F811
    r, cfg, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [{**POS, "estado_stop": "SIN_STOP"}]})
    assert correr() == 0                                  # sin foto: compras bloqueadas, el cierre sí sale
    assert [b["motivo"] for b in _boletos(r, "2026-11-15")] == ["SIN_STOP"]
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == "SIN_STOP: BTC"


def test_ajustar_capital_tambien_desbloquea(mundo):  # noqa: F811
    r, *_ = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, ""), "bloqueo_compras": {"desde": "x", "motivo": "SIN STOP: BTC"}})
    assert RE.ajustar_capital(r, 142.54, "revisado — Ángelo")[0]
    assert RE.cargar_estado(r)["bloqueo_compras"] is None


def test_reanudar_real_casos(mundo, monkeypatch, capsys):  # noqa: F811
    r, *_ = mundo
    assert CR.reanudar(r, "REAL", "ok") == 0
    assert "no estaba detenida ni bloqueada" in capsys.readouterr().out
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, ""), "detenido": True, "pico": 200.0, "capital_inicio_dia": 120.0,
                          "posiciones": [{**POS, "estado_stop": "SIN_STOP"}]})
    assert CR.reanudar(r, "REAL", "sigue — Ángelo") == 0
    est = RE.cargar_estado(r)
    assert est["detenido"] is False and est["pico"] == 120.0 and est["reanudaciones"][0]["texto"] == "sigue — Ángelo"
    assert "OJO: sigue sin stop activo BTCUSDT" in capsys.readouterr().out
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert CR.reanudar(r, "REAL", "ok") == 1
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["reanudar", "--cartera", "A", "--ok-angelo", "x"]) == 0     # A, B y C siguen igual
    assert "no estaba detenida" in capsys.readouterr().out
