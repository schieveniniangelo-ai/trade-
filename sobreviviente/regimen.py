"""Régimen de mercado: ¿el mercado va para arriba, para abajo o de lado? ¿Está tranquilo o loco?"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicadores as ind
from .reglamento import Reglamento

ALCISTA, BAJISTA, LATERAL = "ALCISTA", "BAJISTA", "LATERAL"


def tendencia(df4h: pd.DataFrame, reg: Reglamento) -> pd.Series:
    """ALCISTA si el precio está sobre la EMA 200 y la EMA sube más del umbral; BAJISTA al revés; si no, LATERAL.

    El valor en la vela t usa solo velas cerradas hasta t.
    """
    cfg = reg.datos["regimen"]
    e = ind.ema(df4h["close"], int(cfg["ema"]))
    p = ind.pendiente_pct(e, int(cfg["pendiente_velas"]))
    u = float(cfg["pendiente_umbral_pct"])
    out = np.where((df4h["close"] > e) & (p > u), ALCISTA,
                   np.where((df4h["close"] < e) & (p < -u), BAJISTA, LATERAL))
    s = pd.Series(out, index=df4h.index, dtype=object)
    s[e.isna() | p.isna()] = None
    return s


def atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR como % del precio."""
    return ind.atr(df, n) / df["close"] * 100.0


def percentil_volatilidad(df4h: pd.DataFrame, reg: Reglamento) -> pd.Series:
    """Percentil (0–100) del ATR% actual contra los últimos 90 días de velas de 4 h."""
    cfg = reg.datos["regimen"]
    ventana = int(cfg["vol_ventana_dias"]) * 6  # 6 velas de 4 h por día
    return ind.percentil_movil(atr_pct(df4h, int(cfg["atr_periodo"])), ventana)


def clasificar_vol(percentil: pd.Series, reg: Reglamento) -> pd.Series:
    """BAJA / NORMAL / ALTA / EXTREMA según los percentiles del reglamento."""
    a = reg.riesgo["ajustes"]
    out = np.select(
        [percentil > a["vol_extrema_percentil"], percentil > a["vol_alta_percentil"], percentil < a["vol_baja_percentil"]],
        ["EXTREMA", "ALTA", "BAJA"], default="NORMAL",
    )
    s = pd.Series(out, index=percentil.index, dtype=object)
    s[percentil.isna()] = "NORMAL"
    return s


def a_intervalo_menor(serie_4h: pd.Series, indice_1h: pd.DatetimeIndex) -> pd.Series:
    """Lleva un valor de 4 h a velas de 1 h SIN mirar el futuro.

    La vela de 4 h que abre a las 00:00 cierra a las 04:00. Su valor se puede usar en la decisión
    que se toma al cierre de la vela de 1 h que abre a las 03:00 (cierra a las 04:00).
    Regla general: el valor de 4 h con apertura T está disponible para la vela de 1 h con
    apertura ≥ T + 3 h.
    """
    s = serie_4h.copy()
    s.index = s.index + pd.Timedelta(hours=3)
    return s.reindex(indice_1h, method="ffill")
