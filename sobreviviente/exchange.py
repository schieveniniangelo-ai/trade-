"""Reglas de Binance por moneda: decimales del precio, tamaño mínimo y mínimo en USDT.

Nunca se escriben fijas en el código: se leen de `exchangeInfo` (API oficial) y se
guardan en caché un día. Aquí solo se interpretan y se aplican los redondeos.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any


@dataclass(frozen=True)
class Filtros:
    """Reglas de una moneda en Binance."""

    simbolo: str
    tick: float          # Paso mínimo del precio (PRICE_FILTER.tickSize)
    paso: float          # Paso mínimo de la cantidad (LOT_SIZE.stepSize)
    cantidad_min: float  # Cantidad mínima (LOT_SIZE.minQty)
    minimo_usdt: float   # Valor mínimo de la orden (NOTIONAL o MIN_NOTIONAL)
    paso_mercado: float = 0.0  # Paso de cantidad para órdenes a mercado (MARKET_LOT_SIZE)
    estado: str = "TRADING"
    supuesto: bool = False  # True si son valores de respaldo (solo backtest de monedas deslistadas)


def _f(x: Any, defecto: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return defecto


def filtros_desde_exchangeinfo(simbolo_info: dict[str, Any]) -> Filtros:
    """Convierte la entrada de un símbolo de `exchangeInfo` (Spot o Futuros) en Filtros."""
    tick = paso = cant_min = minimo = paso_mkt = 0.0
    for f in simbolo_info.get("filters", []):
        t = f.get("filterType")
        if t == "PRICE_FILTER":
            tick = _f(f.get("tickSize"))
        elif t == "LOT_SIZE":
            paso = _f(f.get("stepSize"))
            cant_min = _f(f.get("minQty"))
        elif t == "MARKET_LOT_SIZE":
            paso_mkt = _f(f.get("stepSize"))
        elif t == "NOTIONAL":
            minimo = max(minimo, _f(f.get("minNotional")))
        elif t == "MIN_NOTIONAL":
            # Spot usa "minNotional"; Futuros usa "notional".
            minimo = max(minimo, _f(f.get("minNotional", f.get("notional"))))
    return Filtros(
        simbolo=simbolo_info["symbol"],
        tick=tick,
        paso=paso,
        cantidad_min=cant_min,
        minimo_usdt=minimo,
        paso_mercado=paso_mkt,
        estado=simbolo_info.get("status", "TRADING"),
    )


def filtros_supuestos(simbolo: str, precio: float, minimo_usdt: float) -> Filtros:
    """Filtros de respaldo SOLO para el backtest de monedas que ya no tienen reglas publicadas.

    Se usa un paso de precio y de cantidad razonable según el precio. Queda marcado como supuesto.
    """
    import math

    if precio <= 0:
        precio = 1.0
    # Precio con ~5 cifras significativas.
    tick = 10.0 ** (math.floor(math.log10(precio)) - 4)
    # Un paso de cantidad que valga como mucho ~0.01 USDT.
    exp = math.floor(math.log10(0.01 / precio))
    paso = 10.0 ** max(-8, min(3, exp))
    return Filtros(simbolo=simbolo, tick=tick, paso=paso, cantidad_min=paso, minimo_usdt=minimo_usdt, supuesto=True)


def redondear_abajo(valor: float, paso: float) -> float:
    """Redondea hacia abajo al múltiplo de `paso` (exacto, sin errores de punto flotante)."""
    if paso <= 0:
        return float(valor)
    d = Decimal(str(valor))
    p = Decimal(str(paso))
    return float((d / p).to_integral_value(rounding=ROUND_DOWN) * p)


def redondear_arriba(valor: float, paso: float) -> float:
    """Redondea hacia arriba al múltiplo de `paso`."""
    if paso <= 0:
        return float(valor)
    d = Decimal(str(valor))
    p = Decimal(str(paso))
    return float((d / p).to_integral_value(rounding=ROUND_UP) * p)


def redondear_precio(valor: float, tick: float, hacia: str = "abajo") -> float:
    """Ajusta un precio al tick. Para stops de un largo conviene 'abajo' (más conservador)."""
    return redondear_abajo(valor, tick) if hacia == "abajo" else redondear_arriba(valor, tick)
