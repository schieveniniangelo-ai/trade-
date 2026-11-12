"""E7 — Rotación por momentum (ronda 2).

Cada semana (cierre del domingo, hora UTC) se ordenan las monedas MÁS LÍQUIDAS del universo (las 20 con
más volumen mediano de 30 días, sin memes ni stablecoins) por su subida de los últimos `ventana` días.
Se compran las 3 más fuertes (3 = máximo de posiciones normales del reglamento) y se venden las que salen
del top 3. Filtro de BTC: con BTC BAJISTA no se entra (motor de riesgo) y se sale de todo en el rebalanceo.
Stop de protección a `stop_atr` ATR diarios para que el motor calcule el tamaño.
"""
from __future__ import annotations

import pandas as pd

from .base import Contexto, salida

TEMPORALIDAD = "1d"
PARAMETROS = ("ventana", "stop_atr")
TOP = 3
LIQUIDAS = 20
DIA_REBALANCEO = 6  # vela diaria que abre el domingo (cierra el lunes 00:00 UTC = domingo 6 p. m. CDMX)


def ranking(cierres: pd.DataFrame, liquidas: pd.DataFrame, ventana: int) -> pd.DataFrame:
    """Lugar (1 = la más fuerte) de cada moneda líquida por su subida de `ventana` días. NaN si no es líquida."""
    ret = cierres / cierres.shift(ventana) - 1.0
    ret = ret.where(liquidas.reindex_like(ret).fillna(False).astype(bool))
    return ret.rank(axis=1, ascending=False, method="first")


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    lugar = ctx.extra.get(f"lugar_{int(p['ventana'])}")
    if lugar is None:
        lugar = pd.Series(float("nan"), index=v.index)
    rebalanceo = pd.Series(v.index.day_of_week == DIA_REBALANCEO, index=v.index)
    en_top = lugar <= TOP
    btc_ok = ctx.regimen_btc != "BAJISTA"
    entrada = rebalanceo & en_top & btc_ok
    salir = rebalanceo & (~en_top | ~btc_ok)
    stop = v["close"] - float(p["stop_atr"]) * ctx.atr()
    fuerza = -lugar
    return salida(ctx, entrada, stop, None, fuerza, salir)


def gestion(p: dict) -> dict:
    return {"modo": "senal_salida"}
