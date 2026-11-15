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
    cantidad_min_mercado: float = 0.0  # MARKET_LOT_SIZE.minQty (0 = no hay)
    cantidad_max_mercado: float = 0.0  # MARKET_LOT_SIZE.maxQty (0 = no hay)
    # Arreglo 132 (boletos reales). Valores por defecto: si Binance no los manda, nada de lo anterior cambia.
    bid_mult_up: float = 0.0       # PERCENT_PRICE_BY_SIDE.bidMultiplierUp (compra: precio ≤ esto × precio promedio)
    bid_mult_down: float = 0.0     # PERCENT_PRICE_BY_SIDE.bidMultiplierDown
    ask_mult_up: float = 0.0       # PERCENT_PRICE_BY_SIDE.askMultiplierUp
    ask_mult_down: float = 0.0     # PERCENT_PRICE_BY_SIDE.askMultiplierDown (venta: precio ≥ esto × precio promedio)
    minimo_a_mercado: bool = False  # NOTIONAL.applyMinToMarket (el mínimo también vale para órdenes a mercado)
    max_algo: int = 0              # MAX_NUM_ALGO_ORDERS.maxNumAlgoOrders (stops abiertos por moneda; 0 = no se sabe)


def _f(x: Any, defecto: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return defecto


def filtros_desde_exchangeinfo(simbolo_info: dict[str, Any]) -> Filtros:
    """Convierte la entrada de un símbolo de `exchangeInfo` (Spot o Futuros) en Filtros."""
    tick = paso = cant_min = minimo = paso_mkt = min_mkt = max_mkt = 0.0
    extra: dict[str, Any] = {}
    for f in simbolo_info.get("filters", []):
        t = f.get("filterType")
        if t == "PERCENT_PRICE_BY_SIDE":
            extra.update(bid_mult_up=_f(f.get("bidMultiplierUp")), bid_mult_down=_f(f.get("bidMultiplierDown")),
                         ask_mult_up=_f(f.get("askMultiplierUp")), ask_mult_down=_f(f.get("askMultiplierDown")))
        elif t == "MAX_NUM_ALGO_ORDERS":
            extra["max_algo"] = int(_f(f.get("maxNumAlgoOrders")))
        if t == "NOTIONAL" and f.get("applyMinToMarket") is True:
            extra["minimo_a_mercado"] = True
        if t == "PRICE_FILTER":
            tick = _f(f.get("tickSize"))
        elif t == "LOT_SIZE":
            paso = _f(f.get("stepSize"))
            cant_min = _f(f.get("minQty"))
        elif t == "MARKET_LOT_SIZE":
            paso_mkt = _f(f.get("stepSize"))
            min_mkt = _f(f.get("minQty"))
            max_mkt = _f(f.get("maxQty"))
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
        cantidad_min_mercado=min_mkt,
        cantidad_max_mercado=max_mkt,
        **extra,
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
