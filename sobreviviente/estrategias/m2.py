"""M2 — RANKING: las más fuertes del momento (v2).

- Cada lunes (cierre diario del domingo, 00:00 UTC del lunes): entre las "grandes" que cierran sobre su
  media de 100 días, se ordenan por su rendimiento de los últimos `L` días y se toman las 3 primeras.
- Sale la que cae fuera de las 6 primeras en la revisión semanal, o la que cierra bajo su media de
  100 días (revisión diaria). Si BTC cierra bajo su media de 200 días, se cierra todo.
- Stop real en Binance: 20 % bajo la entrada (de catástrofe). Tamaño por riesgo con ese stop.

Aviso honesto: en los estudios publicados esta señal es más débil que la de M1. Es la retadora.
"""
from __future__ import annotations

import pandas as pd

from .. import indicadores as ind
from .base import Contexto, salida

TEMPORALIDAD = "1d"
PARAMETROS = ("L",)
SMA = 100
TOP_ENTRADA = 3
TOP_SALIDA = 6
STOP_PCT = 20.0
DIA_REVISION = 6  # vela diaria que abre el domingo (cierra el lunes 00:00 UTC = domingo 6 p. m. CDMX)


def ranking(cierres: pd.DataFrame, grandes: pd.DataFrame, L: int, sma: int = SMA) -> pd.DataFrame:
    """Lugar (1 = la más fuerte) entre las grandes que cierran sobre su media de `sma` días. NaN si no califica.

    `grandes` debe venir alineada a la vela (fila D = universo vigente para decidir al cierre de D)."""
    media = cierres.rolling(sma).mean()
    ret = cierres / cierres.shift(int(L)) - 1.0
    califica = grandes.reindex_like(ret).fillna(False).astype(bool) & (cierres > media)
    return ret.where(califica).rank(axis=1, ascending=False, method="first")


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    L = int(p["L"])
    lugar = ctx.extra.get(f"lugar_{L}")
    if lugar is None:
        lugar = pd.Series(float("nan"), index=v.index)
    lugar = lugar.reindex(v.index)
    media = ind.sma(v["close"], SMA)
    revision = pd.Series(v.index.day_of_week == DIA_REVISION, index=v.index)
    marea_alta = ctx.regimen_btc == "ALCISTA"
    sobre_media = v["close"] > media
    entrada = revision & (lugar <= TOP_ENTRADA) & marea_alta & sobre_media
    fuera_tabla = ~(lugar <= TOP_SALIDA)
    salir = (revision & fuera_tabla) | ~sobre_media | ~marea_alta
    stop = v["close"] * (1 - STOP_PCT / 100.0)
    fuerza = -lugar
    return salida(ctx, entrada, stop, None, fuerza, salir)


def gestion(p: dict) -> dict:
    return {"modo": "ranking"}
