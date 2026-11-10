"""Estrategias. Cada una: `senales(ctx, params)` y `gestion(params)`.

Ronda 1: E1 a E5. Ronda 2: E1D (E1 corregida, diaria), E6 (tendencia larga BTC/ETH), E7 (rotación por momentum).
"""
from . import e1, e1d, e2, e3, e4, e5, e6, e7, m0, m1, m2

ESTRATEGIAS = {"E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5, "E1D": e1d, "E6": e6, "E7": e7,
               "M0": m0, "M1": m1, "M2": m2}  # v2: M0 (R1 como motor), M1 MAREA y M2 RANKING
