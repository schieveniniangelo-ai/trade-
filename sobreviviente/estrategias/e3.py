"""E3 — Reversión en rango (Spot, largos, velas de 4 h, riesgo reducido).

Solo cuando la moneda está LATERAL: entra en sobreventa extrema (RSI de 2 periodos abajo de
`rsi2_max` y cierre bajo la banda inferior de Bollinger). Sale rápido cuando el cierre regresa a la
media de `salida_media` velas, o a las 10 velas (40 horas) como máximo. Stop a `stop_atr` ATR.
"""
from __future__ import annotations

from .. import indicadores as ind
from .base import Contexto, flanco, salida

TEMPORALIDAD = "4h"
PARAMETROS = ("rsi2_max", "stop_atr", "salida_media")
MAX_VELAS = 10


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    rsi2 = ctx.rsi(2)
    _, _, banda_inf = ctx.memo("bb20", lambda: ind.bollinger(v["close"], 20, 2.0))
    atr = ctx.atr()
    cond = (ctx.regimen_moneda == "LATERAL") & (rsi2 < float(p["rsi2_max"])) & (v["close"] < banda_inf)
    entrada = flanco(cond)
    stop = v["close"] - float(p["stop_atr"]) * atr
    meta = ctx.sma(int(p["salida_media"]))
    fuerza = -rsi2
    return salida(ctx, entrada, stop, meta, fuerza)


def gestion(p: dict) -> dict:
    return {"modo": "media", "salida_media": int(p["salida_media"]), "max_velas": MAX_VELAS}
