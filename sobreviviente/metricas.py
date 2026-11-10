"""Métricas de resultados, cada una con su explicación sencilla."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

EXPLICACION = {
    "operaciones": "cuántas operaciones hubo",
    "pct_ganadoras": "de cada 100 operaciones, cuántas ganaron",
    "expectativa_r": "lo que deja en promedio cada operación, medido en R (1R = lo que se arriesga)",
    "factor_ganancia": "lo ganado dividido entre lo perdido (más de 1 = gana; 1.3 o más = sano)",
    "ganancia_prom_r": "lo que deja en promedio una operación ganadora (en R)",
    "perdida_prom_r": "lo que quita en promedio una operación perdedora (en R)",
    "racha_perdedora_max": "la peor cadena de pérdidas seguidas",
    "caida_max_pct": "lo más que bajó el capital desde un máximo",
    "rendimiento_pct": "cuánto creció (o bajó) el capital en total",
    "comisiones_pct_bruto": "qué parte de la ganancia bruta se fue en comisiones",
}


def racha_max(valores: np.ndarray, perdedora: bool = True) -> int:
    mejor = actual = 0
    for v in valores:
        if (v < 0) if perdedora else (v > 0):
            actual += 1
            mejor = max(mejor, actual)
        else:
            actual = 0
    return mejor


def caida_maxima_pct(curva: np.ndarray | pd.Series) -> float:
    """Caída máxima (en %) de una curva de capital."""
    c = np.asarray(curva, dtype=float)
    if len(c) == 0:
        return 0.0
    pico = np.maximum.accumulate(c)
    return float(np.max((pico - c) / pico) * 100.0)


def calmar(curva: pd.Series) -> float:
    """Calmar = rendimiento ANUAL ÷ caída máxima. Más alto = más ganancia por cada susto grande."""
    c = curva.dropna()
    if len(c) < 2 or c.iloc[0] <= 0:
        return float("nan")
    anios = (c.index[-1] - c.index[0]).days / 365.25
    if anios <= 0:
        return float("nan")
    anual = (c.iloc[-1] / c.iloc[0]) ** (1 / anios) - 1 if c.iloc[-1] > 0 else -1.0
    dd = caida_maxima_pct(c.values) / 100
    return float(anual / dd) if dd > 0 else float("inf")


def resumen_curva(curva: pd.Series, invertido: pd.Series | None = None, operaciones: int | None = None) -> dict[str, Any]:
    """Rendimiento, rendimiento anual, caída máxima, Calmar, % del tiempo invertido y operaciones de una curva diaria."""
    c = curva.dropna()
    if len(c) < 2:
        return {"rend_total_pct": 0.0, "rend_anual_pct": 0.0, "caida_max_pct": 0.0, "calmar": float("nan"),
                "tiempo_invertido_pct": float("nan"), "operaciones": operaciones or 0}
    anios = (c.index[-1] - c.index[0]).days / 365.25
    out = {
        "rend_total_pct": float(c.iloc[-1] / c.iloc[0] - 1) * 100,
        "rend_anual_pct": float((c.iloc[-1] / c.iloc[0]) ** (1 / anios) - 1) * 100 if anios > 0 and c.iloc[-1] > 0 else float("nan"),
        "caida_max_pct": caida_maxima_pct(c.values),
        "calmar": calmar(c),
        "tiempo_invertido_pct": float(invertido.reindex(c.index).fillna(0).clip(0, 1).mean() * 100) if invertido is not None else float("nan"),
        "operaciones": int(operaciones) if operaciones is not None else 0,
    }
    return out


def topes_en_curva(curva: pd.Series, tope_diario_pct: float, tope_semanal_pct: float, freno_pct: float) -> dict[str, Any]:
    """Auditoría A2: cuántas veces la curva diaria a valor de mercado habría tocado cada tope."""
    c = curva.dropna()
    if len(c) < 2:
        return {"dias_tope_diario": 0, "semanas_tope_semanal": 0, "veces_freno": 0}
    diario = (c / c.shift(1) - 1) * 100
    ix = c.index.tz_localize(None) if c.index.tz is not None else c.index
    semanas = c.groupby(ix.to_period("W-SUN"))
    peor_sem = 0
    for _, s in semanas:
        base = c[c.index < s.index[0]]
        ref = base.iloc[-1] if len(base) else s.iloc[0]
        if (s.min() / ref - 1) * 100 <= -tope_semanal_pct:
            peor_sem += 1
    # Freno: cada vez que la caída desde el pico llega al límite (y se reinicia el pico, como el OK de Ángelo)
    veces, pico = 0, c.iloc[0]
    for v in c.values:
        pico = max(pico, v)
        if (pico - v) / pico * 100 >= freno_pct:
            veces += 1
            pico = v
    return {"dias_tope_diario": int((diario <= -tope_diario_pct).sum()), "semanas_tope_semanal": int(peor_sem),
            "veces_freno": int(veces)}


def concentracion(r: np.ndarray | pd.Series, top: int = 5) -> float:
    """Auditoría A7: qué parte (%) de la ganancia total viene de las `top` mejores operaciones."""
    r = np.asarray(r, dtype=float)
    total = r.sum()
    if len(r) == 0 or total <= 0:
        return float("nan")
    return float(np.sort(r)[::-1][:top].sum() / total * 100)


def resumen_r(r: np.ndarray | pd.Series) -> dict[str, Any]:
    """Estadísticas a partir de los resultados en R (sin importar el capital)."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n == 0:
        return {"operaciones": 0, "pct_ganadoras": 0.0, "expectativa_r": 0.0, "factor_ganancia": 0.0,
                "ganancia_prom_r": 0.0, "perdida_prom_r": 0.0, "racha_perdedora_max": 0}
    g = r[r > 0]
    p = r[r <= 0]
    fg = float(g.sum() / -p.sum()) if p.sum() < 0 else float("inf")
    return {
        "operaciones": n,
        "pct_ganadoras": float(len(g) / n * 100),
        "expectativa_r": float(r.mean()),
        "factor_ganancia": fg,
        "ganancia_prom_r": float(g.mean()) if len(g) else 0.0,
        "perdida_prom_r": float(p.mean()) if len(p) else 0.0,
        "racha_perdedora_max": racha_max(r),
    }


def resumen_cartera(ops: pd.DataFrame, curva: pd.Series, capital_inicial: float) -> dict[str, Any]:
    """Estadísticas en dinero de una corrida de cartera."""
    if ops is None or ops.empty:
        return {"operaciones": 0, "rendimiento_pct": 0.0, "caida_max_pct": 0.0, "comisiones_pct_bruto": 0.0}
    bruto_ganador = (ops["cantidad"] * (ops["pnl_unidad"] + ops["comision_unidad"])).clip(lower=0).sum()
    comis = (ops["cantidad"] * ops["comision_unidad"]).sum()
    return {
        "operaciones": int(len(ops)),
        "rendimiento_pct": float((curva.iloc[-1] / capital_inicial - 1) * 100),
        "caida_max_pct": caida_maxima_pct(curva.values),
        "comisiones_pct_bruto": float(comis / bruto_ganador * 100) if bruto_ganador > 0 else float("nan"),
        "ganancia_usdt": float(ops["ganancia_usdt"].sum()),
        "comisiones_usdt": float(comis),
    }
