"""E2 — Retroceso en tendencia (Spot, largos, entrada en velas de 1 h).

Con la tendencia de 4 h ALCISTA, entra en 1 h cuando el precio regresó a la zona EMA 20/50,
el RSI se "reseteó" (bajó de `rsi_reset`) y retoma (cruza otra vez arriba de 50).
Stop bajo el último mínimo, entre 1 y `stop_atr` ATR de distancia. Meta 2R; al tocarla, el stop
sube a +1R y sigue con stop dinámico.
"""
from __future__ import annotations

import numpy as np

from .base import Contexto, flanco, salida

TEMPORALIDAD = "1h"
PARAMETROS = ("rsi_reset", "stop_atr", "chandelier_atr")
VELAS_RETROCESO = 5
VELAS_RESET = 6
VELAS_MINIMO = 10


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    e20, e50 = ctx.ema(20), ctx.ema(50)
    rsi = ctx.rsi(14)
    atr = ctx.atr()
    tendencia_4h = ctx.extra["regimen_moneda_4h"] == "ALCISTA"
    retroceso = (v["low"].rolling(VELAS_RETROCESO).min() <= e20) & (v["close"] > e50)
    reseteo = rsi.rolling(VELAS_RESET).min() < float(p["rsi_reset"])
    retoma = (rsi > 50) & (rsi.shift(1) <= 50) & (v["close"] > e20)
    entrada = flanco(tendencia_4h & retroceso & reseteo & retoma)
    minimo = v["low"].rolling(VELAS_MINIMO).min()
    stop_minimo = np.minimum(minimo - 0.2 * atr, v["close"] - 1.0 * atr)
    stop = np.maximum(stop_minimo, v["close"] - float(p["stop_atr"]) * atr)
    meta = v["close"] + 2.0 * (v["close"] - stop)
    fuerza = (v["close"] - e50) / atr
    return salida(ctx, entrada, stop, meta, fuerza)


def gestion(p: dict) -> dict:
    return {"modo": "meta_luego_chandelier", "chandelier_atr": float(p["chandelier_atr"])}
