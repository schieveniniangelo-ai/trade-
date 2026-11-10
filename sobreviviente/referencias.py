"""Referencias para comparar (ronda 2): comprar y aguantar, DCA semanal y las versiones "puras"
de la tendencia larga (E6) y la rotación por momentum (E7).

"Pura" = como la describió Ángelo: todo el dinero adentro o afuera, sin el motor de riesgo
(sin 1 % de riesgo por operación ni tope de 30 % por posición). Sirve para ver la idea en sí.
Todas operan en la apertura siguiente a la decisión y pagan comisión + deslizamiento en cada cambio.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metricas import caida_maxima_pct


def metricas_curva(curva: pd.Series, invertido: pd.Series | None = None) -> dict[str, float]:
    """Rendimiento total, anual, caída máxima, volatilidad y 'Sharpe' (rendimiento ÷ volatilidad)."""
    c = curva.dropna()
    if len(c) < 2:
        return {}
    anios = (c.index[-1] - c.index[0]).days / 365.25
    r = c.pct_change().dropna()
    vol = float(r.std() * np.sqrt(365)) * 100
    total = float(c.iloc[-1] / c.iloc[0] - 1) * 100
    anual = float((c.iloc[-1] / c.iloc[0]) ** (1 / anios) - 1) * 100 if anios > 0 else float("nan")
    out = {"rend_total_pct": total, "rend_anual_pct": anual, "caida_max_pct": caida_maxima_pct(c.values),
           "volatilidad_pct": vol, "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else float("nan")}
    if invertido is not None:
        out["tiempo_invertido_pct"] = float(invertido.reindex(c.index).fillna(0).mean() * 100)
    return out


def _abierto_a_abierto(df: pd.DataFrame) -> pd.Series:
    """Rendimiento de apertura a apertura (se opera en aperturas)."""
    return df["open"].shift(-1) / df["open"] - 1.0


def comprar_aguantar(dfs: dict[str, pd.DataFrame], pesos: dict[str, float], inicio, fin, costo_pct: float) -> pd.Series:
    """Compra al inicio (con costo) y no vende nunca."""
    partes = []
    for s, w in pesos.items():
        df = dfs[s]
        o = df["open"][(df.index >= inicio) & (df.index <= fin)]
        partes.append(w * o / o.iloc[0] * (1 - costo_pct / 100))
    return sum(partes)


def dca_semanal(df: pd.DataFrame, inicio, fin, costo_pct: float, dia: int = 0) -> pd.Series:
    """Empieza con 1 en efectivo y lo invierte en partes iguales cada semana (lunes) en BTC."""
    o = df["open"][(df.index >= inicio) & (df.index <= fin)]
    dias_compra = o.index[o.index.dayofweek == dia]
    monto = 1.0 / len(dias_compra)
    efectivo, monedas = 1.0, 0.0
    valores = []
    for t, precio in o.items():
        if t in dias_compra:
            efectivo -= monto
            monedas += monto * (1 - costo_pct / 100) / precio
        valores.append(efectivo + monedas * precio)
    return pd.Series(valores, index=o.index)


def tendencia_pura(dfs: dict[str, pd.DataFrame], simbolos: list[str], sma: int, inicio, fin,
                   costo_pct: float) -> tuple[pd.Series, pd.Series]:
    """Cada moneda es la mitad del dinero: adentro si el cierre de ayer quedó arriba de su media de `sma` días."""
    curvas, invertido = [], []
    for s in simbolos:
        df = dfs[s]
        senal = (df["close"] > df["close"].rolling(sma).mean()).astype(float)
        pos = senal.shift(1).fillna(0.0)            # decidida al cierre de ayer, vigente desde la apertura de hoy
        cambio = pos.diff().abs().fillna(pos)
        r = pos * _abierto_a_abierto(df) - cambio * costo_pct / 100
        r = r[(r.index >= inicio) & (r.index <= fin)].fillna(0)
        curvas.append((1 + r).cumprod() / len(simbolos))
        invertido.append(pos.reindex(r.index) / len(simbolos))
    return sum(curvas), sum(invertido)


def rotacion_pura(spot1d: dict[str, pd.DataFrame], lugar: pd.DataFrame, btc_reg_diario: pd.Series, top: int,
                  inicio, fin, costo_pct: float, dia_rebalanceo: int = 6) -> tuple[pd.Series, pd.Series, int]:
    """Cada semana: las `top` monedas más fuertes en partes iguales (si BTC no está BAJISTA); si no, efectivo."""
    simb = list(lugar.columns)
    ret = pd.DataFrame({s: _abierto_a_abierto(spot1d[s]) for s in simb}).reindex(lugar.index)
    pesos = pd.DataFrame(np.nan, index=lugar.index, columns=simb)
    reb = lugar.index[lugar.index.dayofweek == dia_rebalanceo]
    for t in reb:
        w = pd.Series(0.0, index=simb)
        if btc_reg_diario.get(t) != "BAJISTA":
            elegidas = lugar.loc[t][lugar.loc[t] <= top].index
            if len(elegidas):
                w[elegidas] = 1.0 / len(elegidas)
        pesos.loc[t] = w
    pesos = pesos.ffill().fillna(0.0).shift(1).fillna(0.0)  # decididos al cierre, vigentes desde la apertura siguiente
    rotacion = pesos.diff().abs().sum(axis=1).fillna(pesos.abs().sum(axis=1))
    r = (pesos * ret.fillna(0.0)).sum(axis=1) - rotacion * costo_pct / 100
    r = r[(r.index >= inicio) & (r.index <= fin)]
    operaciones = int((pesos.diff().abs() > 1e-9).sum().sum())
    return (1 + r).cumprod(), pesos.sum(axis=1).reindex(r.index), operaciones


def por_anio(curva: pd.Series) -> dict[int, float]:
    """Rendimiento de cada año calendario (%)."""
    out = {}
    for anio, c in curva.groupby(curva.index.year):
        base = curva[curva.index < c.index[0]]
        inicio = base.iloc[-1] if len(base) else c.iloc[0]
        out[int(anio)] = float(c.iloc[-1] / inicio - 1) * 100
    return out
