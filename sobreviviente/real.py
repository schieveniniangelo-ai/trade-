"""Dinero REAL: Spot, reglas de la Cartera A, motor M0 (solo BTC), solo largo (arreglos 129 a 140).

El programa NUNCA tiene llaves de Binance ni firma órdenes: solo lee datos públicos, emite boletos y lee los archivos
que EJECUTOR escribe con lo que contestó Binance (por el conector). Todo lo real vive en datos/real/ y en
salida/boletos_real_*.json, nunca mezclado con datos/papel/.

Falla cerrada: si falta o está viejo un dato del real, NO se compra. Lo que protege (poner el stop, vender a mercado,
reponer un stop) nunca se bloquea por MODO SEGURO, pausa, tope, conciliación o falta de datos.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import archivos as AR
from .reglamento import Reglamento

CARTERA = "REAL"
ESTADOS_STOP = ("ACTIVO", "SIN_STOP", "DISPARADO_SIN_LLENAR")
FOTO_MAX_MIN = 120   # minutos: una foto de saldo más vieja no sirve (un solo valor; real.foto_max_minutos lo puede fijar)
CAMPOS_ESTADO = ("cartera", "capital_inicial", "pico", "capital_inicio_dia", "capital_inicio_semana", "pausa_hasta",
                 "rachas", "posiciones", "cerradas")
CAMPOS_POSICION = ("id", "simbolo", "estrategia", "cantidad_comprada", "cantidad_neta", "precio_llenado", "comision",
                   "moneda_comision", "stop", "limite_stop", "id_stop", "orden_id_stop", "estado_stop", "t_entrada")


class EstadoRealDanado(Exception):
    """El estado real no se puede leer o tiene un formato raro. La ronda real no compra hasta que se revise."""


def ruta_real(reg: Reglamento) -> Path:
    return AR.carpeta_datos(reg) / "real"


def archivo_estado(reg: Reglamento) -> Path:
    return ruta_real(reg) / "cartera_REAL.json"


def foto_max_minutos(reg: Reglamento) -> float:
    return float(reg.get("real.foto_max_minutos", FOTO_MAX_MIN))


def estado_nuevo(capital: float, inicio: str) -> dict[str, Any]:
    """La cartera real recién creada: la misma forma que una de papel, sin posiciones. Solo cambia con llenados
    confirmados por EJECUTOR (registrar-llenado --real), nunca por simulación."""
    return {"cartera": CARTERA, "reglas_de": "A", "inicio": inicio, "capital_inicial": capital, "pico": capital,
            "capital_inicio_dia": capital, "capital_inicio_semana": capital, "dia_ref": None, "semana_ref": None,
            "pausa_hasta": None, "pausa_motivo": "", "detenido": False, "rachas": {}, "saltar_rondas": {},
            "posiciones": [], "cerradas": [], "ajustes": [], "bloqueo_compras": None}


def _revisar_forma(est: Any) -> list[str]:
    if not isinstance(est, dict):
        return ["no es un objeto"]
    errores = [f"falta '{k}'" for k in CAMPOS_ESTADO if k not in est]
    if errores:
        return errores
    if est.get("cartera") != CARTERA:
        errores.append(f"dice cartera {est.get('cartera')!r} y debe ser {CARTERA}")
    if not isinstance(est["posiciones"], list) or not isinstance(est["cerradas"], list):
        return errores + ["posiciones y cerradas deben ser listas"]
    for i, p in enumerate(est["posiciones"]):
        if not isinstance(p, dict):
            errores.append(f"la posición #{i + 1} no es un objeto")
            continue
        faltan = [k for k in CAMPOS_POSICION if k not in p]
        if faltan:
            errores.append(f"a la posición #{i + 1} le falta {', '.join(faltan)}")
        elif p["estado_stop"] not in ESTADOS_STOP:
            errores.append(f"la posición #{i + 1} tiene estado_stop {p['estado_stop']!r}")
    for k in ("capital_inicial", "pico", "capital_inicio_dia", "capital_inicio_semana"):
        if isinstance(est.get(k), bool) or not isinstance(est.get(k), (int, float)):
            errores.append(f"'{k}' no es un número")
    return errores


def cargar_estado(reg: Reglamento, inicio: str = "") -> dict[str, Any]:
    """Lee datos/real/cartera_REAL.json. Si no existe (ni su copia), regresa una cartera nueva con
    `carteras.capital_inicial`. Si está dañado, NO usa la copia .bak (podría no traer la última compra y la ronda
    compraría dos veces): lanza EstadoRealDanado con qué hacer."""
    arch = archivo_estado(reg)
    bak = arch.with_name(arch.name + ".bak")
    if not arch.exists():
        if bak.exists():
            raise EstadoRealDanado(f"Falta {arch.name} pero existe su copia {bak.name}. No uso la copia (podría no traer "
                                   f"la última compra): Ángelo debe revisar y restaurar el archivo a mano.")
        return estado_nuevo(reg.cifra("carteras.capital_inicial"), inicio)
    try:
        est = json.loads(arch.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as e:
        raise EstadoRealDanado(f"El estado real ({arch.name}) está dañado o no se puede leer ({type(e).__name__}). "
                               f"La ronda real NO compra. No uso la copia .bak: Ángelo debe revisarlo.")
    errores = _revisar_forma(est)
    if errores:
        raise EstadoRealDanado(f"El estado real ({arch.name}) tiene un formato raro: {'; '.join(errores)[:200]}. "
                               f"La ronda real NO compra hasta que Ángelo lo revise.")
    return est


def guardar_estado(reg: Reglamento, est: dict[str, Any]) -> None:
    """Escritura segura (temporal + copia .bak)."""
    AR.escribir_json_seguro(archivo_estado(reg), est)


def estado_ok(reg: Reglamento) -> tuple[bool, str]:
    """(True, "") si el estado real se lee bien; si no, (False, el mensaje con qué hacer)."""
    try:
        cargar_estado(reg)
    except EstadoRealDanado as e:
        return False, str(e)
    return True, ""
