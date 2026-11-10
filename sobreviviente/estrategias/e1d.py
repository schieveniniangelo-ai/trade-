"""E1D — E1 corregida (ronda 2): ruptura de tendencia en velas DIARIAS (Spot, largos).

Cambios contra E1 (pedidos por Ángelo para dejar correr las ganadoras):
- Velas diarias en lugar de 4 h (los costos pesan menos frente al tamaño del movimiento).
- NO se sube el stop a la entrada en +1R.
- Stop dinámico más amplio (`chandelier_atr` de 4 a 6 ATR diarios).
Tendencia: precio sobre la EMA 200 diaria con pendiente positiva (régimen calculado en velas diarias).
"""
from __future__ import annotations

from .. import indicadores as ind
from .base import Contexto, flanco, salida

TEMPORALIDAD = "1d"
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
