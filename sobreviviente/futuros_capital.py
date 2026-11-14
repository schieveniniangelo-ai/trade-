"""Comando `futuros-capital` (Arreglo 121): cuánto capital haría falta para un corto de E5 en cada perpetuo.

SOLO INFORMA. No cambia reglas, carteras ni señales. Por perpetuo: el mínimo de la orden según las reglas de Binance
Futuros (`exchangeInfo`, arreglo 92), el stop típico de E5 (mediana de `stop_atr` × ATR ÷ cierre en las últimas velas
de 4 h), el capital necesario con el riesgo por operación de cada cartera (`riesgo.capital_necesario`) y si cabe con
el capital real. Manda lo que diga `exchangeInfo`: si la cantidad mínima (minQty) pide más que el mínimo en USDT,
cuenta la cantidad mínima.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from . import datos as D
from . import indicadores as ind
from . import riesgo as R
from .exchange import Filtros, filtros_desde_exchangeinfo
from .reglamento import Reglamento

VELAS_STOP = 540          # unos 90 días de velas de 4 h para el stop típico
VELAS_MIN = 60


def capital_necesario_corto(filtros: Filtros, precio: float, stop_pct: float, riesgo_pct: float) -> float:
    """Capital con el que un corto con stop a `stop_pct` % arriba sí cabría con `riesgo_pct` % de riesgo."""
    cand = R.Candidato(simbolo=filtros.simbolo, mercado="FUTUROS", lado=R.CORTO, estrategia="E5", cubeta="futuros",
                       precio_entrada=precio, stop=precio * (1 + stop_pct / 100.0), apalancamiento=2.0)
    return R.capital_necesario(riesgo_pct, cand, filtros, capital=1.0, tope_actual=0.0)


def stop_tipico_pct(velas4h: pd.DataFrame, stop_atr: float) -> float:
    """Mediana de la distancia del stop de E5 (stop_atr × ATR de 14 velas ÷ cierre), en %; NaN con pocas velas."""
    if len(velas4h) < VELAS_MIN:
        return float("nan")
    v = velas4h.iloc[-VELAS_STOP:]
    dist = (float(stop_atr) * ind.atr(v, 14) / v["close"]).iloc[14:]
    dist = dist[np.isfinite(dist)]
    return float(dist.median() * 100.0) if len(dist) else float("nan")


def _riesgos(reg: Reglamento) -> dict[str, float]:
    carteras = reg.datos.get("carteras") or {}
    return {k: float(v["riesgo_por_operacion_pct"]) for k, v in carteras.items()
            if isinstance(v, dict) and "riesgo_por_operacion_pct" in v}


def filas(reg: Reglamento, filtros: dict[str, Filtros], velas4h: dict[str, pd.DataFrame],
          capital: float) -> list[dict[str, Any]]:
    """Una fila por perpetuo con reglas de Futuros y velas: mínimo, precio, stop típico, capital por cartera y si cabe."""
    stop_atr = float(reg.estrategias["E5"]["parametros"]["stop_atr"])
    riesgos = _riesgos(reg)
    out = []
    for s in sorted(velas4h):
        if s not in filtros or velas4h[s].empty:
            continue
        f = filtros[s]
        precio = float(velas4h[s]["close"].iloc[-1])
        stop = stop_tipico_pct(velas4h[s], stop_atr)
        cap = {k: (capital_necesario_corto(f, precio, stop, r) if math.isfinite(stop) else float("nan"))
               for k, r in riesgos.items()}
        out.append({"simbolo": s, "minimo_usdt": f.minimo_usdt, "cantidad_min": f.cantidad_min, "precio": precio,
                    "orden_minima_usdt": max(f.minimo_usdt, max(f.cantidad_min, f.paso) * precio),
                    "stop_pct": stop, "capital": cap,
                    "cabe": {k: bool(math.isfinite(v) and v <= capital) for k, v in cap.items()}})
    return out


def _n(x: float, d: int = 0) -> str:
    return "sin dato" if not math.isfinite(x) else f"{x:,.{d}f}"


def texto(filas_: list[dict[str, Any]], capital: float, riesgos: dict[str, float]) -> str:
    carteras = list(riesgos)
    L = [f"Capital para un corto de E5 por perpetuo (capital real: {capital:.2f} USDT). Solo informa: no cambia "
         "reglas ni carteras; E5 sigue APAGADA.",
         "Capital necesario = el mínimo con el que la orden más chica de Binance Futuros cabe con el riesgo por "
         "operación de cada cartera (" + ", ".join(f"{k} {r:g} %" for k, r in riesgos.items()) + ").",
         "La Cartera C se dimensiona por exposición, no por riesgo: su cifra es solo de referencia.", "",
         "| Perpetuo | Mínimo (USDT) | Cantidad mínima | Orden mínima (último cierre guardado) | Stop típico E5 | "
         + " | ".join(f"Capital {k}" for k in carteras) + " | ¿Cabe? |",
         "|---|---|---|---|---|" + "---|" * len(carteras) + "---|"]
    for f in filas_:
        cabe = ", ".join(k for k in carteras if f["cabe"][k]) or "no"
        L.append(f"| {f['simbolo']} | {f['minimo_usdt']:g} USDT | {f['cantidad_min']:g} | "
                 f"{_n(f['orden_minima_usdt'], 2)} USDT | {_n(f['stop_pct'], 1)} % | "
                 + " | ".join(f"{_n(f['capital'][k])} USDT" for k in carteras) + f" | {cabe} |")
    por_cartera = ", ".join(f"{k} {sum(f['cabe'][k] for f in filas_)}" for k in carteras)
    L += ["", f"Caben con {capital:.2f} USDT, de {len(filas_)} perpetuos: {por_cartera}."]
    return "\n".join(L)


def comando(reg: Reglamento, args, avisar=print) -> int:
    cli = D.ClienteBinance(reg)
    try:
        info = cli.exchange_info("FUTUROS")
    except Exception as e:  # noqa: BLE001 - sin reglas de Futuros no hay tabla, pero se dice claro
        avisar(f"❌ No pude leer las reglas de Binance Futuros ({type(e).__name__}). Sin ellas no hay tabla.")
        return 1
    por_simbolo = {x["symbol"]: x for x in info.get("symbols", [])}
    pedidos = getattr(args, "simbolos", None)
    carpeta = cli.cache / "futuros" / "1h"
    simbolos = pedidos or sorted(p.name.removesuffix(".csv.gz") for p in carpeta.glob("*.csv.gz"))
    filtros = {s: filtros_desde_exchangeinfo(por_simbolo[s]) for s in simbolos
               if s in por_simbolo and por_simbolo[s].get("status", "TRADING") == "TRADING"}
    velas = {}
    for s in filtros:
        f1 = D.leer(D.ruta_cache(cli, "futuros", "1h", s))
        if not f1.empty:
            velas[s] = D.resamplear(f1.astype({c: "float64" for c in ["open", "high", "low", "close"]}), "4h")
    if not velas:
        avisar("❌ No hay velas de Futuros guardadas para esos perpetuos. Corre antes el comando descargar.")
        return 1
    capital = float(getattr(args, "capital", None) or reg.get("backtest.capital_real", 46.18))
    avisar(texto(filas(reg, filtros, velas, capital), capital, _riesgos(reg)))
    return 0
