"""E1 — Ruptura de tendencia (Spot, largos, velas de 4 h).

Entra cuando el precio cierra arriba del máximo de las últimas N velas (canal Donchian) y la moneda
está en tendencia ALCISTA (precio sobre la EMA 200 con pendiente positiva). Stop inicial a
`stop_atr` ATR. Sale con stop dinámico tipo Chandelier (máximo desde la entrada − `chandelier_atr` ATR).
"""
from __future__ import annotations

from .. import indicadores as ind
from .base import Contexto, flanco, salida

TEMPORALIDAD = "4h"
PARAMETROS = ("donchian_n", "stop_atr", "chandelier_atr")


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    n = int(p["donchian_n"])
    techo = ctx.memo(f"max{n}", lambda: ind.maximo_previo(v["high"], n))
    atr = ctx.atr()
    cond = (v["close"] > techo) & (ctx.regimen_moneda == "ALCISTA")
    entrada = flanco(cond)
    stop = v["close"] - float(p["stop_atr"]) * atr
    fuerza = (v["close"] - techo) / atr
    return salida(ctx, entrada, stop, None, fuerza)


def gestion(p: dict) -> dict:
    return {"modo": "chandelier", "chandelier_atr": float(p["chandelier_atr"])}
