"""E6 — Tendencia larga en BTC y ETH (ronda 2).

Regla: estar comprado mientras el cierre diario está ARRIBA de su media de `sma` días (200);
quedarse en USDT cuando está abajo. Se revisa al cierre de cada día; la orden va en la apertura siguiente.
Para que el motor de riesgo pueda calcular el tamaño, cada entrada lleva un stop de protección
a `stop_atr` ATR diarios (solo para desastres; la salida normal es por la media).
"""
from __future__ import annotations

from .base import Contexto, salida

TEMPORALIDAD = "1d"
PARAMETROS = ("sma", "stop_atr")
SIMBOLOS = ("BTCUSDT", "ETHUSDT")


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    media = ctx.sma(int(p["sma"]))
    arriba = v["close"] > media
    # Señal cada día que está arriba: si no hay posición (o se cerró por el stop), el motor puede volver a entrar.
    entrada = arriba & media.notna()
    stop = v["close"] - float(p["stop_atr"]) * ctx.atr()
    salir = (v["close"] < media) & media.notna()
    fuerza = (v["close"] / media - 1.0)
    return salida(ctx, entrada, stop, None, fuerza, salir)


def gestion(p: dict) -> dict:
    return {"modo": "senal_salida"}
