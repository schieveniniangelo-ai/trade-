"""E4 — Surfista de memes (Spot, largos, velas de 1 h, riesgo reducido).

Entra cuando el volumen de 24 h es al menos `vol_mult` veces su promedio de los 7 días previos, la
moneda está en el 10 % más fuerte de las memes (subida de 24 h), NO subió más de 40 % en 24 h, y
ya tomó un "respiro" (está al menos `respiro_pct` % abajo de su máximo de 6 h).
Stop: el más cercano entre −15 % y `stop_atr` ATR. Sale a las 24 horas si no tocó el stop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Contexto, flanco, salida

TEMPORALIDAD = "1h"
PARAMETROS = ("vol_mult", "respiro_pct", "stop_atr")
FIJOS = {"subida_max_24h_pct": 40.0, "stop_max_pct": 15.0, "horas_max": 24, "fuerza_percentil": 90.0}


def fuerza_relativa(cierres: pd.DataFrame, pertenece: pd.DataFrame | None = None) -> pd.DataFrame:
    """Percentil (0–100) de la subida de 24 h de cada meme contra las demás memes en el universo, hora por hora."""
    ret = cierres / cierres.shift(24) - 1.0
    if pertenece is not None:
        ret = ret.where(pertenece.reindex_like(ret).fillna(False).astype(bool))
    return ret.rank(axis=1, pct=True) * 100.0


def senales(ctx: Contexto, p: dict, fijos: dict | None = None):
    f = {**FIJOS, **(fijos or {})}
    v = ctx.velas
    atr = ctx.atr()
    vol24 = ctx.memo("vol24", lambda: v["quote_volume"].rolling(24).sum())
    prom = ctx.memo("vol24_prom", lambda: vol24.shift(24).rolling(168, min_periods=120).mean())
    ratio = vol24 / prom
    sub24 = (v["close"] / v["close"].shift(24) - 1.0) * 100.0
    fr = ctx.extra.get("fuerza_relativa")
    fuerte = (fr >= float(f["fuerza_percentil"])) if fr is not None else pd.Series(False, index=v.index)
    maximo6 = v["high"].rolling(6).max()
    respiro = v["close"] <= maximo6 * (1 - float(p["respiro_pct"]) / 100.0)
    cond = (ratio >= float(p["vol_mult"])) & fuerte & (sub24 <= float(f["subida_max_24h_pct"])) & respiro
    entrada = flanco(cond)
    stop_pct = v["close"] * (1 - float(f["stop_max_pct"]) / 100.0)
    stop_atr = v["close"] - float(p["stop_atr"]) * atr
    stop = np.maximum(stop_pct, stop_atr)
    return salida(ctx, entrada, stop, None, ratio)


def gestion(p: dict, fijos: dict | None = None) -> dict:
    f = {**FIJOS, **(fijos or {})}
    return {"modo": "tiempo", "max_velas": int(f["horas_max"])}
