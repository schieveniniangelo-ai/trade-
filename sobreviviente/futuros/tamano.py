"""Tamaño de una posición de F1 por RIESGO (SOLO PAPEL). El apalancamiento sale como consecuencia, nunca al revés.

1. valor = capital × riesgo ÷ distancia del stop, recortado al 60 % del capital (25.52 USDT con 42.54);
2. cantidad = valor ÷ precio redondeada HACIA ABAJO al paso de Binance (así el riesgo real nunca pasa del pedido);
3. apalancamiento 1x si el valor cabe en el 30 % del capital; 2x si cabe en el 60 %; nunca más que el tope (2x);
4. el margen abierto total debe quedar ≤ 60 % del capital;
5. la liquidación (fórmula oficial, liquidacion.py) debe quedar al menos 2 veces más lejos que el stop, después de
   acercarla un 5 % (el colchón `liquidation_buffer` = 0.05 de Freqtrade).
Si algo no se cumple: «no cabe», con la razón. Nunca se infla el riesgo para alcanzar el mínimo de Binance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..exchange import Filtros, filtros_desde_exchangeinfo, redondear_abajo
from . import liquidacion as LQ

COLCHON_LIQUIDACION = 2.0     # igual que riesgo.futuros.colchon_liquidacion: liquidación ≥ 2 × distancia del stop
COLCHON_FREQTRADE = 0.05      # MECÁNICO por delegación de Ángelo 2026-11-16: la liquidación se acerca 5 %


@dataclass
class Tamano:
    cabe: bool
    razon: str = ""
    cantidad: float = 0.0
    valor: float = 0.0
    apalancamiento: int = 0
    margen: float = 0.0
    riesgo_usdt: float = 0.0
    riesgo_pedido_usdt: float = 0.0
    liquidacion: float | None = None


def filtros_moneda(info_simbolo: dict[str, Any]) -> Filtros:
    """Reglas de Binance Futuros de una moneda (paso, cantidad mínima, mínimo en USDT) desde exchangeInfo."""
    return filtros_desde_exchangeinfo(info_simbolo)


def calcular(capital: float, riesgo_pct: float, precio: float, stop: float, lado: str, filtros: Filtros,
             cfg: dict[str, Any], margen_abierto: float = 0.0,
             escalones: list[dict[str, Any]] | None = None) -> Tamano:
    """Tamaño por riesgo con las reglas de F1. `margen_abierto`: margen que ya ocupan las posiciones abiertas."""
    pedido = capital * riesgo_pct / 100.0
    dist = (precio - stop) if lado == "LARGO" else (stop - precio)
    if capital <= 0 or precio <= 0 or dist <= 0:
        return Tamano(False, "el stop no queda del lado correcto del precio o no hay capital", riesgo_pedido_usdt=pedido)
    tope_pos = capital * float(cfg["margen_posicion_max_pct"]) / 100.0
    tope_total = capital * float(cfg["margen_total_max_pct"]) / 100.0
    valor = min(pedido / (dist / precio), tope_total)
    cantidad = redondear_abajo(valor / precio, filtros.paso)
    valor_real = cantidad * precio
    if cantidad <= 0 or cantidad < filtros.cantidad_min or valor_real < filtros.minimo_usdt:
        return Tamano(False, f"no cabe: con {capital:.2f} USDT y {riesgo_pct:g} % de riesgo la posición vale "
                             f"{valor_real:.3f} USDT y el mínimo de Binance es {filtros.minimo_usdt:g} USDT "
                             f"(cantidad mínima {filtros.cantidad_min:g})", cantidad=cantidad, valor=valor_real,
                      riesgo_pedido_usdt=pedido)
    apal = 1 if valor_real <= tope_pos + 1e-9 else 2
    if apal > int(cfg["apalancamiento_tope"]):
        return Tamano(False, f"no cabe: necesitaría {apal}x y el tope es {cfg['apalancamiento_tope']}x",
                      cantidad=cantidad, valor=valor_real, riesgo_pedido_usdt=pedido)
    margen = valor_real / apal
    if margen > tope_pos + 1e-9:
        return Tamano(False, f"no cabe por margen: {margen:.3f} USDT pasa del {cfg['margen_posicion_max_pct']:g} % "
                             f"por posición ({tope_pos:.2f})", cantidad=cantidad, valor=valor_real, apalancamiento=apal,
                      margen=margen, riesgo_pedido_usdt=pedido)
    if margen_abierto + margen > tope_total + 1e-9:
        return Tamano(False, f"no cabe por margen: ya hay {margen_abierto:.2f} USDT de margen y esta pide {margen:.3f}; "
                             f"el total no puede pasar de {tope_total:.2f} ({cfg['margen_total_max_pct']:g} %)",
                      cantidad=cantidad, valor=valor_real, apalancamiento=apal, margen=margen, riesgo_pedido_usdt=pedido)
    esc = escalones if escalones is not None else LQ.cargar_escalones(filtros.simbolo)
    liq = LQ.precio_liquidacion_aislado(precio, cantidad, lado, apal, esc)
    dist_liq = abs(precio - liq) * (1 - COLCHON_FREQTRADE)
    if dist_liq < COLCHON_LIQUIDACION * dist:
        return Tamano(False, f"no cabe: la liquidación ({liq:.6g}) queda a menos de {COLCHON_LIQUIDACION:g} veces la "
                             f"distancia del stop", cantidad=cantidad, valor=valor_real, apalancamiento=apal,
                      margen=margen, riesgo_pedido_usdt=pedido, liquidacion=liq)
    return Tamano(True, "cabe", cantidad, valor_real, apal, margen, cantidad * dist, pedido, liq)
