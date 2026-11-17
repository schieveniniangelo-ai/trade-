"""Precio de liquidación de Futuros USDⓈ-M con la fórmula oficial de Binance (margen AISLADO, modo ONE_WAY).

    LP = (WB + cum − lado·Q·EP) ÷ (Q·MMR − lado·Q)

WB = margen aislado = nocional ÷ apalancamiento; cum = «maintenance amount» del escalón; lado = +1 largo, −1 corto;
Q = cantidad; EP = precio de entrada; MMR = tasa de mantenimiento del escalón. Si el nocional al precio de liquidación
cae en otro escalón, se recalcula con ese escalón.

Las tablas de escalones vienen de escalones.json (copiadas a mano; el endpoint de escalones de Binance es firmado y
no se usa). La tarifa de liquidación sale de exchangeInfo (campo liquidationFee de cada moneda). No reemplaza ni cambia
`riesgo.precio_liquidacion`, que sigue igual para todo lo demás.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ARCHIVO_ESCALONES = Path(__file__).resolve().parent / "escalones.json"
MAX_RECALCULOS = 5


class ErrorEscalones(ValueError):
    """No hay escalón para ese nocional o la tabla no existe."""


@lru_cache(maxsize=1)
def _tabla() -> dict[str, Any]:
    return json.loads(ARCHIVO_ESCALONES.read_text(encoding="utf-8"))


def cargar_escalones(simbolo: str) -> list[dict[str, Any]]:
    """Escalones de una moneda (copia), ordenados por nocional."""
    m = _tabla()["monedas"].get(simbolo)
    if m is None:
        raise ErrorEscalones(f"no hay tabla de escalones para {simbolo} en escalones.json")
    return sorted((dict(e) for e in m["escalones"]), key=lambda e: float(e["nocional_min"]))


def verificado(simbolo: str) -> bool:
    m = _tabla()["monedas"].get(simbolo) or {}
    return bool(m.get("verificado", False))


def sin_verificar(monedas) -> list[str]:
    """Las monedas cuya tabla de escalones sigue siendo un supuesto (verificado: false o sin tabla), en orden."""
    return [s for s in monedas if not verificado(s)]


def todas_verificadas(monedas) -> bool:
    """¿Todas las monedas tienen su tabla de escalones copiada y verificada? (compuerta «escalones» de validar-futuros)"""
    return not sin_verificar(monedas)


def escalon_de(nocional: float, escalones: list[dict[str, Any]]) -> dict[str, Any]:
    """El escalón donde cae un nocional (nocional_min ≤ nocional < nocional_max)."""
    for e in escalones:
        if float(e["nocional_min"]) <= nocional < float(e["nocional_max"]):
            return e
    raise ErrorEscalones(f"el nocional {nocional:,.2f} USDT no cae en ningún escalón de la tabla")


def _formula(entrada: float, cantidad: float, signo: int, wb: float, esc: dict[str, Any]) -> float:
    mmr = float(esc["mmr_pct"]) / 100.0
    cum = float(esc["cum"])
    return (wb + cum - signo * cantidad * entrada) / (cantidad * mmr - signo * cantidad)


def precio_liquidacion_aislado(entrada: float, cantidad: float, lado: str, apalancamiento: float,
                               escalones: list[dict[str, Any]]) -> float:
    """Precio de liquidación de una posición aislada (nunca negativo: un largo a 1x no se liquida → 0)."""
    if entrada <= 0 or cantidad <= 0 or apalancamiento <= 0:
        raise ValueError("entrada, cantidad y apalancamiento deben ser mayores que 0")
    signo = 1 if lado == "LARGO" else -1
    nocional = entrada * cantidad
    wb = nocional / float(apalancamiento)
    esc = escalon_de(nocional, escalones)
    lp = _formula(entrada, cantidad, signo, wb, esc)
    for _ in range(MAX_RECALCULOS):
        try:
            otro = escalon_de(max(lp, 0.0) * cantidad, escalones)
        except ErrorEscalones:
            break                       # fuera de la tabla: se queda con el último cálculo
        if otro is esc or otro.get("escalon") == esc.get("escalon"):
            break
        esc = otro
        lp = _formula(entrada, cantidad, signo, wb, esc)
    return max(0.0, lp)


def tarifa_liquidacion(simbolo: str, info_simbolo: dict[str, Any] | None = None) -> float:
    """Tarifa de liquidación en % del nocional: exchangeInfo.liquidationFee; si no hay, la cifra del 2026-11-16."""
    if info_simbolo:
        try:
            return float(info_simbolo["liquidationFee"]) * 100.0
        except (KeyError, TypeError, ValueError):
            pass
    respaldo = _tabla()["tarifa_liquidacion_pct_2026_11_16"]
    if simbolo not in respaldo:
        raise ErrorEscalones(f"no hay tarifa de liquidación para {simbolo}")
    return float(respaldo[simbolo])
