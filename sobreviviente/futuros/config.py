"""Configuración de F1 v2 (SOLO PAPEL): valores por defecto y lectura del bloque propio `futuros_papel`.

Mientras el reglamento no traiga el bloque `futuros_papel` (llega en el arreglo 152, en la ventana del domingo), F1 usa
`POR_DEFECTO`. Si el bloque existe, se mezcla con los valores por defecto y se valida contra los límites duros de
Ángelo. F1 no va en `estrategias:` ni en `carteras:` del reglamento: así `ronda_real.compuertas_puerta` no cambia.
"""
from __future__ import annotations

import copy
from typing import Any

from ..reglamento import Reglamento
from . import liquidacion as LQ

ANGELO = "DECISIÓN DE ÁNGELO 2026-11-16"
MECANICO = "MECÁNICO por delegación de Ángelo 2026-11-16"

# Lista fija de monedas que F1 puede operar. BTCUSDT y ETHUSDT no caben con 42.54 USDT (BTC solo es filtro de régimen).
MONEDAS_PERMITIDAS = ("SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT")   # MECÁNICO por delegación de Ángelo 2026-11-16

POR_DEFECTO: dict[str, Any] = {
    "activo": False,                     # DECISIÓN DE ÁNGELO 2026-11-16: pasa a true solo si F1 PASA validar-futuros
    "capital_papel": 42.54,              # DECISIÓN DE ÁNGELO 2026-11-16: reparto 100 Spot / 42.54 F1 (el papel de Spot sigue en 142.54)
    "apalancamiento_tope": 2,            # DECISIÓN DE ÁNGELO 2026-11-16 (K5): 1x por defecto, 2x como máximo
    "margen": "AISLADO",                 # DECISIÓN DE ÁNGELO 2026-11-16: nunca cruzado
    "modo_posicion": "ONE_WAY",          # MECÁNICO por delegación de Ángelo 2026-11-16
    "monedas": list(MONEDAS_PERMITIDAS),  # MECÁNICO por delegación de Ángelo 2026-11-16
    "regimen_btc": "BTCUSDT",            # MECÁNICO por delegación de Ángelo 2026-11-16: solo filtro, no se opera
    "temporalidad": "4h",                # MECÁNICO por delegación de Ángelo 2026-11-16
    "riesgo_por_operacion_pct": 1.0,     # MECÁNICO por delegación de Ángelo 2026-11-16 (0.43 USDT con 42.54)
    "calor_total_max_pct": 2.0,          # MECÁNICO por delegación de Ángelo 2026-11-16
    "posiciones_max": 2,                 # MECÁNICO por delegación de Ángelo 2026-11-16 (1 por moneda)
    "margen_posicion_max_pct": 30.0,     # MECÁNICO por delegación de Ángelo 2026-11-16 (12.76 USDT)
    "margen_total_max_pct": 60.0,        # MECÁNICO por delegación de Ángelo 2026-11-16 (25.52 USDT)
    "stop_min_pct": 1.5,                 # MECÁNICO por delegación de Ángelo 2026-11-16
    "stop_max_pct": 8.0,                 # MECÁNICO por delegación de Ángelo 2026-11-16
    "volumen_mediano_min_usdt": 100000000,  # MECÁNICO por delegación de Ángelo 2026-11-16 (30 días del perpetuo)
    "tope_diario_pct": 3.0,              # DECISIÓN DE ÁNGELO 2026-11-16 (siempre hay frenos): pausa hasta las 00:00 UTC
    "tope_semanal_pct": 6.0,             # DECISIÓN DE ÁNGELO 2026-11-16: pausa hasta el lunes
    "caida_max_desde_pico_pct": 15.0,    # DECISIÓN DE ÁNGELO 2026-11-16: todo se detiene hasta el OK de Ángelo
    "perdidas_seguidas_pausa": 4,        # MECÁNICO por delegación de Ángelo 2026-11-16
    "pausa_horas": 24,                   # MECÁNICO por delegación de Ángelo 2026-11-16
    "funding_extremo_pct_8h": 0.05,      # MECÁNICO por delegación de Ángelo 2026-11-16
}

ORIGEN: dict[str, str] = {
    "activo": ANGELO, "capital_papel": ANGELO, "apalancamiento_tope": ANGELO, "margen": ANGELO,
    "modo_posicion": MECANICO, "monedas": MECANICO, "regimen_btc": MECANICO, "temporalidad": MECANICO,
    "riesgo_por_operacion_pct": MECANICO, "calor_total_max_pct": MECANICO, "posiciones_max": MECANICO,
    "margen_posicion_max_pct": MECANICO, "margen_total_max_pct": MECANICO, "stop_min_pct": MECANICO,
    "stop_max_pct": MECANICO, "volumen_mediano_min_usdt": MECANICO, "tope_diario_pct": ANGELO,
    "tope_semanal_pct": ANGELO, "caida_max_desde_pico_pct": ANGELO, "perdidas_seguidas_pausa": MECANICO,
    "pausa_horas": MECANICO, "funding_extremo_pct_8h": MECANICO,
}

APALANCAMIENTO_MIN = 1
APALANCAMIENTO_MAX = 2      # DECISIÓN DE ÁNGELO 2026-11-16 (K5), igual que riesgo.futuros.apalancamiento_max
RIESGO_MAX_PCT = 2.0        # DECISIÓN DE ÁNGELO 2026-11-16: el riesgo por operación de F1 nunca pasa de 2 %


class ErrorConfigFuturos(ValueError):
    """La configuración de F1 rompe un límite duro. F1 no corre con ella."""

    def __init__(self, problemas: list[str]):
        self.problemas = problemas
        super().__init__("La configuración de Futuros F1 (futuros_papel) tiene problemas y F1 NO corre:\n"
                         + "\n".join(f"  - {p}" for p in problemas))


def _num(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def validar(cfg: dict[str, Any]) -> None:
    """Lanza ErrorConfigFuturos si algún valor rompe los límites duros."""
    p: list[str] = []
    ap = _num(cfg.get("apalancamiento_tope"))
    if ap is None or ap < APALANCAMIENTO_MIN or ap > APALANCAMIENTO_MAX:
        p.append(f"apalancamiento_tope = {cfg.get('apalancamiento_tope')}: debe estar entre 1x y 2x.")
    if str(cfg.get("margen", "")).upper() != "AISLADO":
        p.append(f"margen = {cfg.get('margen')}: siempre AISLADO, nunca cruzado.")
    if str(cfg.get("modo_posicion", "")).upper() != "ONE_WAY":
        p.append(f"modo_posicion = {cfg.get('modo_posicion')}: solo ONE_WAY.")
    rg = _num(cfg.get("riesgo_por_operacion_pct"))
    if rg is None or rg <= 0 or rg > RIESGO_MAX_PCT:
        p.append(f"riesgo_por_operacion_pct = {cfg.get('riesgo_por_operacion_pct')}: debe ser mayor que 0 y como "
                 f"mucho {RIESGO_MAX_PCT} %.")
    cap = _num(cfg.get("capital_papel"))
    if cap is None or cap <= 0:
        p.append(f"capital_papel = {cfg.get('capital_papel')}: debe ser mayor que 0.")
    monedas = cfg.get("monedas")
    if not isinstance(monedas, list) or not monedas:
        p.append("monedas: debe ser una lista con al menos una moneda.")
    else:
        fuera = [m for m in monedas if m not in MONEDAS_PERMITIDAS]
        if fuera:
            p.append(f"monedas fuera de la lista fija {list(MONEDAS_PERMITIDAS)}: {fuera}.")
    if p:
        raise ErrorConfigFuturos(p)


def escalones_pendientes(cfg: dict[str, Any]) -> list[str]:
    """Monedas de F1 cuya tabla de escalones sigue sin verificar (Arreglo 159)."""
    return LQ.sin_verificar(cfg["monedas"])


def leer(reg: Reglamento, exigir_activacion: bool = True) -> dict[str, Any]:
    """Configuración de F1: POR_DEFECTO si el reglamento no trae `futuros_papel`; si lo trae, la mezcla validada.

    Arreglo 159 (DECISIÓN DE ÁNGELO 2026-11-17): con `activo: true` y escalones sin verificar, lanza
    ErrorConfigFuturos. `futuros-papel` lee con `exigir_activacion=False` y niega la activación él mismo (modo muestra).
    """
    cfg = copy.deepcopy(POR_DEFECTO)
    bloque = reg.get("futuros_papel")
    if bloque is not None:
        if not isinstance(bloque, dict):
            raise ErrorConfigFuturos(["futuros_papel debe ser un bloque de claves y valores."])
        cfg.update(copy.deepcopy(bloque))
    validar(cfg)
    if exigir_activacion and cfg["activo"] is True:
        faltan = escalones_pendientes(cfg)
        if faltan:
            raise ErrorConfigFuturos([f"activo: true con escalones sin verificar: {', '.join(faltan)}. "
                                      "F1 no se activa hasta copiar y verificar sus tablas en escalones.json."])
    return cfg


def renglones_origen(cfg: dict[str, Any]) -> list[str]:
    """Cada cifra con quién la decidió, para los reportes de F1."""
    return [f"{k}: {cfg[k]} — {ORIGEN.get(k, 'sin origen anotado')}" for k in cfg]
