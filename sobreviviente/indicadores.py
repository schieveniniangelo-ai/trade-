"""Indicadores técnicos. Todos usan solo datos hasta la vela actual (nunca del futuro)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    """Media móvil exponencial. Las primeras n-1 velas quedan vacías (todavía no hay datos suficientes)."""
    e = s.ewm(span=n, adjust=False).mean()
    e.iloc[: n - 1] = np.nan
    return e


def sma(s: pd.Series, n: int) -> pd.Series:
    """Promedio simple de las últimas n velas."""
    return s.rolling(n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Promedio de Wilder (el que usan el RSI y el ATR clásicos)."""
    r = s.ewm(alpha=1.0 / n, adjust=False).mean()
    r.iloc[: n - 1] = np.nan
    return r


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR: tamaño promedio de las velas, contando huecos entre velas."""
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    return rma(tr, n)


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """RSI: de 0 a 100; abajo de 30 = sobreventa, arriba de 70 = sobrecompra."""
    d = s.diff()
    sube = rma(d.clip(lower=0).fillna(0), n)
    baja = rma((-d.clip(upper=0)).fillna(0), n)
    rs = sube / baja.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(baja != 0, 100.0)
    out.iloc[:n] = np.nan
    return out


def maximo_previo(s: pd.Series, n: int) -> pd.Series:
    """Máximo de las n velas ANTERIORES (sin contar la actual): el techo del canal Donchian."""
    return s.shift(1).rolling(n).max()


def minimo_previo(s: pd.Series, n: int) -> pd.Series:
    """Mínimo de las n velas anteriores: el piso del canal Donchian."""
    return s.shift(1).rolling(n).min()


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bandas de Bollinger: (media, banda superior, banda inferior)."""
    m = s.rolling(n).mean()
    d = s.rolling(n).std(ddof=0)
    return m, m + k * d, m - k * d


def pendiente_pct(s: pd.Series, n: int) -> pd.Series:
    """Cambio porcentual de la serie contra n velas atrás."""
    return (s / s.shift(n) - 1.0) * 100.0


def percentil_movil(s: pd.Series, ventana: int) -> pd.Series:
    """Qué tan alto está el valor actual comparado con las últimas `ventana` velas (0 a 100)."""
    return s.rolling(ventana, min_periods=max(20, ventana // 3)).rank(pct=True) * 100.0
