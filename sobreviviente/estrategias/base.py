"""Piezas comunes de las estrategias.

Cada estrategia es una función PURA: recibe las velas cerradas de una moneda (y el contexto de
régimen) y devuelve, para cada vela t, si hay señal de entrada al cierre de t, dónde iría el stop
y la meta. Solo usa datos hasta t. La entrada se ejecuta en la apertura de la vela t+1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .. import indicadores as ind


@dataclass
class Contexto:
    """Todo lo que una estrategia puede mirar de una moneda."""

    simbolo: str
    velas: pd.DataFrame                 # velas de la temporalidad de la estrategia (1h o 4h)
    regimen_moneda: pd.Series           # ALCISTA/BAJISTA/LATERAL de la moneda, alineado a `velas`
    regimen_btc: pd.Series              # régimen de BTC alineado a `velas`
    extra: dict[str, Any] = field(default_factory=dict)  # p. ej. funding, fuerza relativa de memes
    _memo: dict[str, pd.Series] = field(default_factory=dict, repr=False)

    def memo(self, clave: str, funcion) -> pd.Series:
        """Guarda indicadores ya calculados (acelera el walk-forward)."""
        if clave not in self._memo:
            self._memo[clave] = funcion()
        return self._memo[clave]

    def atr(self, n: int = 14) -> pd.Series:
        return self.memo(f"atr{n}", lambda: ind.atr(self.velas, n))

    def ema(self, n: int) -> pd.Series:
        return self.memo(f"ema{n}", lambda: ind.ema(self.velas["close"], n))

    def sma(self, n: int) -> pd.Series:
        return self.memo(f"sma{n}", lambda: ind.sma(self.velas["close"], n))

    def rsi(self, n: int) -> pd.Series:
        return self.memo(f"rsi{n}", lambda: ind.rsi(self.velas["close"], n))


def flanco(cond: pd.Series) -> pd.Series:
    """True solo en la primera vela en que la condición se cumple (evita señales repetidas)."""
    c = cond.fillna(False).astype(bool)
    return c & ~c.shift(1, fill_value=False)


def salida(ctx: Contexto, entrada: pd.Series, stop: pd.Series, meta: pd.Series | None = None,
           fuerza: pd.Series | None = None) -> pd.DataFrame:
    """Arma el DataFrame estándar de señales."""
    df = pd.DataFrame(index=ctx.velas.index)
    df["entrada"] = entrada.fillna(False).astype(bool)
    df["stop"] = stop
    df["meta"] = meta if meta is not None else float("nan")
    df["fuerza"] = fuerza if fuerza is not None else 0.0
    df["precio"] = ctx.velas["close"]
    df.loc[df["stop"].isna(), "entrada"] = False
    return df
