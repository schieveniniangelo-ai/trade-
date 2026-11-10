"""E5 — Francotirador de cortos (Futuros USDⓈ-M, margen aislado, máximo 2x, velas de 4 h).

Solo con BTC BAJISTA y la moneda también BAJISTA. Dos entradas espejo:
- Espejo de E1: cierre abajo del mínimo de N velas.
- Espejo de E2: rebote a la zona EMA 20/50, RSI que subió de 60 y vuelve a cruzar abajo de 50.
Filtro de funding: no entra si el funding va muy en contra (los cortos pagan más de `funding_min_pct`).
Stop a `stop_atr` ATR arriba; sale con stop dinámico (mínimo desde la entrada + `chandelier_atr` ATR).
"""
from __future__ import annotations

import pandas as pd

from .. import indicadores as ind
from .base import Contexto, flanco, salida

TEMPORALIDAD = "4h"
PARAMETROS = ("donchian_n", "stop_atr", "chandelier_atr", "funding_min_pct")


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    n = int(p["donchian_n"])
    piso = ctx.memo(f"min{n}", lambda: ind.minimo_previo(v["low"], n))
    e20, e50 = ctx.ema(20), ctx.ema(50)
    rsi = ctx.rsi(14)
    atr = ctx.atr()
    bajista = (ctx.regimen_moneda == "BAJISTA") & (ctx.regimen_btc == "BAJISTA")
    funding = ctx.extra.get("funding")
    if funding is None:
        funding = pd.Series(0.0, index=v.index)
    funding_ok = (funding * 100.0) >= float(p["funding_min_pct"])
    ruptura = v["close"] < piso
    rebote = (v["high"].rolling(3).max() >= e20) & (v["close"] < e50) & (rsi.rolling(6).max() > 60) \
        & (rsi < 50) & (rsi.shift(1) >= 50)
    entrada = (flanco(bajista & ruptura) | flanco(bajista & rebote)) & funding_ok
    stop = v["close"] + float(p["stop_atr"]) * atr
    fuerza = (piso - v["close"]) / atr
    return salida(ctx, entrada, stop, None, fuerza)


def gestion(p: dict) -> dict:
    return {"modo": "chandelier", "chandelier_atr": float(p["chandelier_atr"])}
