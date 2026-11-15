"""Arreglo 135: ronda real, parte 3 (salidas y vigilancia del stop; cierra R1 y R9).

Por cada posición real: salida de M0, stop tocado y sin llenar, stop que falta en la foto y stop ya ejecutado. Los
cierres salen aunque haya MODO SEGURO, pausa, tope o conciliación en ❌. Nunca se repone un stop: se vende."""
import json
from datetime import timedelta

import pandas as pd
import pytest

from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture


@pytest.fixture
def con_posicion(mundo, monkeypatch):  # noqa: F811
    r, cfg, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    cfg.update(salir=False, vela=None)
    original_preparar, original_senales = P.preparar_datos, P._senales

    def preparar(reg, cli, memes, ahora=None, **kw):
        dd = original_preparar(reg, cli, memes, ahora=ahora)
        if cfg["vela"]:
            v = dd.md.velas["BTCUSDT"].copy()
            for k, x in cfg["vela"].items():
                v.loc[dd.dia, k] = x
            dd.md.velas["BTCUSDT"] = v
        if cfg.get("seguro"):
            dd.datos_ok = False
        return dd

    def senales(dd, clave, s, params):
        sen = original_senales(dd, clave, s, params)
        sen["salir"] = cfg["salir"]
        return sen
    monkeypatch.setattr(P, "preparar_datos", preparar)
    monkeypatch.setattr(P, "_senales", senales)
    return r, cfg, foto, correr


def _cierres(r):
    return [b for b in json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
            if b["accion"] == "CERRAR"]


def test_salida_de_m0(con_posicion):
    r, cfg, foto, correr = con_posicion
    cfg["salir"] = True
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0
    (b,) = _cierres(r)
    assert b["motivo"] == "SALIDA_M0" and b["urgente"] is False and b["orden_venta"]["type"] == "MARKET"
    assert b["orden_cancelar"]["origClientOrderId"] == POS["id_stop"]


def test_stop_tocado_y_sin_llenar(con_posicion, capsys):
    r, cfg, foto, correr = con_posicion
    cfg["vela"] = {"low": 58000.0, "close": 58500.0}         # pasó el stop (59,500) y cerró abajo de su límite (59,202.5)
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0
    (b,) = _cierres(r)
    assert b["motivo"] == "STOP_SIN_LLENAR" and b["urgente"] is True and "No repongas el stop" in b["texto"]
    assert capsys.readouterr().out.startswith("❌ URGENTE: STOP_SIN_LLENAR en BTCUSDT")
    assert RE.cargar_estado(r)["posiciones"][0]["estado_stop"] == "DISPARADO_SIN_LLENAR"


def test_vela_que_toca_el_stop_pero_cierra_arriba_no_es_urgente(con_posicion):
    r, cfg, foto, correr = con_posicion
    cfg["vela"] = {"low": 59400.0, "close": 69000.0}
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0 and _cierres(r) == []


def test_sin_stop_cierre_urgente_en_la_primera_linea(con_posicion, capsys):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    assert correr() == 0
    (b,) = _cierres(r)
    assert b["motivo"] == "SIN_STOP" and b["urgente"] is True and b["orden_venta"]["quantity"] == "0.00012"
    assert capsys.readouterr().out.splitlines()[0] == "❌ URGENTE: SIN_STOP en BTCUSDT — EJECUTOR debe cerrar ya. " \
                                                      "Avisa a Ángelo con prioridad."


def test_stop_ya_ejecutado_solo_informa(con_posicion):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=USDT_CON_POS + 7.10, btc=0.00000001), [])
    assert correr() == 0
    (b,) = _cierres(r)
    assert b["motivo"] == "STOP_EJECUTADO" and b.get("solo_informativo") is True and "orden_venta" not in b


@pytest.mark.parametrize("como", ["modo_seguro", "pausa", "conciliacion"])
def test_los_cierres_salen_aunque_haya_frenos(con_posicion, como):
    r, cfg, foto, correr = con_posicion
    otras = []
    if como == "modo_seguro":
        cfg["seguro"] = True
    elif como == "pausa":
        est = RE.cargar_estado(r)
        est.update(pausa_hasta=(AHORA + timedelta(days=2)).isoformat(), pausa_motivo="tope semanal")
        RE.guardar_estado(r, est)
    else:
        otras = [orden_stop(lado="BUY", tipo="LIMIT", client="bpdesconocida0001", order_id=9)]
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), otras)
    assert correr() == 0
    assert [b["motivo"] for b in _cierres(r)] == ["SIN_STOP"]


def test_sin_foto_fresca_avisa_y_no_inventa(con_posicion, capsys):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [], ahora=AHORA - timedelta(hours=3))
    assert correr() == 0 and _cierres(r) == []
    assert "sin foto de saldo fresca no puedo revisar si su stop sigue vivo" in capsys.readouterr().out
