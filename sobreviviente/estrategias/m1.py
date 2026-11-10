"""M1 — MAREA: tendencia propia de cada moneda (v2).

- Entrada: el cierre diario supera el máximo de los `n` días previos Y la marea de BTC está alta
  (cierre diario de BTC sobre su media de 200 días).
- Salida: el cierre diario cae bajo el mínimo de los `n/2` días previos → sale en la apertura siguiente.
  Sin meta y sin "+1R → entrada".
- Stop real en Binance: el mínimo de `n/2` días al entrar (contando el día de la señal), con tope de 15 %
  de distancia. Se sube cada día al nuevo mínimo; solo se mueve a favor.

Nota honesta: como el stop vive justo en el piso del canal, casi siempre lo toca el stop (durante el día)
antes de que se confirme la salida por cierre. La salida por cierre queda como respaldo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicadores as ind
from .base import Contexto, flanco, salida

TEMPORALIDAD = "1d"
PARAMETROS = ("n",)
STOP_MAX_PCT = 15.0


def canal_velas(n: int) -> int:
    return max(2, int(n) // 2)


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    n = int(p["n"])
    k = canal_velas(n)
    techo = ind.maximo_previo(v["high"], n)
    marea_alta = ctx.regimen_btc == "ALCISTA"
    entrada = flanco((v["close"] > techo) & marea_alta)
    piso = v["low"].rolling(k).min()
    tope = float(p.get("stop_max_pct", STOP_MAX_PCT))
    stop = np.maximum(piso, v["close"] * (1 - tope / 100.0))
    stop = pd.Series(stop, index=v.index).where(techo.notna())
    fuerza = (v["close"] - techo) / ctx.atr()   # cuánto rompió, en ATR (para elegir cuando no hay lugar)
    return salida(ctx, entrada, stop, None, fuerza)


def gestion(p: dict) -> dict:
    return {"modo": "canal", "canal_velas": canal_velas(int(p["n"]))}
