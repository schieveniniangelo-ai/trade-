"""Variantes declaradas de F1 (Hipótesis 004, registrada el 2026-11-17 desde 5619f84) y barras por pruebas múltiples.

SOLO PAPEL y SOLO MIDE. Las variantes son fijas (MECÁNICO por delegación de Ángelo, 2026-11-17): no son parámetros de
F1 (no van en `estrategias/f1.PARAMETROS`), así que no entran a la rejilla ni a la robustez. Cada una cuenta como una
prueba de la familia F1: 4 pruebas → 8 ideas del reglamento + 4 = 12 → azar ≥ 100 − 10/12 = 99.17 % y t ≥ 2.2414
(Bonferroni α = 0.05/4, una cola). Método de deflactar por varias pruebas: Bailey y López de Prado, «The Deflated
Sharpe Ratio», https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

Cada corrida de `validar-futuros` agrega un renglón a VARIANTES_FUTUROS.md (solo se agregan renglones; nunca se borra
ni se reemplaza uno). Nada de aquí escribe `activo`.
"""
from __future__ import annotations

import copy
from pathlib import Path
from statistics import NormalDist
from typing import Any

from ..exchange import Filtros

VARIANTES: dict[str, dict[str, Any]] = {
    "F1": {"lados": "ambos", "tiempo_max_velas": None},                  # referencia (ya medida): prueba #1
    "F1-L": {"lados": "largo", "tiempo_max_velas": None},                # sin cortos
    "F1-LC": {"lados": "largo+corto_fuerte", "tiempo_max_velas": None},  # cortos solo en «bajista fuerte»
    "F1-LT": {"lados": "largo", "tiempo_max_velas": 30},                 # F1-L + salida por tiempo (30 velas de 4 h)
}
PRUEBAS_FAMILIA = 4
ALFA = 0.05
ARCHIVO_REGISTRO = "VARIANTES_FUTUROS.md"


class ErrorVariante(ValueError):
    """La variante no es una de las 4 declaradas en la Hipótesis 004."""


def variante(nombre: str | None) -> dict[str, Any]:
    """El dict fijo de una variante (copia). Una variante desconocida es error."""
    if nombre not in VARIANTES:
        raise ErrorVariante(f"variante desconocida: {nombre!r}; las declaradas son {sorted(VARIANTES)}")
    return copy.deepcopy(VARIANTES[nombre])


def ideas_totales(reg) -> int:
    """Ideas probadas del proyecto: las del reglamento (validacion.ronda2.ideas_probadas, sin tocarlo) + 4."""
    return int(reg.get("validacion.ronda2.ideas_probadas")) + PRUEBAS_FAMILIA


def azar_min(reg) -> float:
    """Percentil mínimo contra el azar: 100 − azar_base ÷ ideas totales (100 − 10/12 = 99.17 %)."""
    return 100.0 - float(reg.get("validacion.ronda2.azar_base_pct", 10)) / ideas_totales(reg)


def t_min() -> float:
    """t mínima de la expectativa: normal inversa de 1 − 0.05/4 (2.2414)."""
    return NormalDist().inv_cdf(1.0 - ALFA / PRUEBAS_FAMILIA)


# ---------------------------------------------------------------------------- holdout de monedas (Arreglo 162)
# Declaradas el 2026-11-17 (Hipótesis 004) y nunca usadas en F1. ESTE es el único lugar del código que las nombra (una
# prueba lo revisa). Se abren UNA sola vez por variante, y solo con una variante que pasó las 15 compuertas sin contar
# «escalones».
MONEDAS_HOLDOUT = ("ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT")
HOLDOUT_OPS_MIN = 30


def _escalon_supuesto() -> list[dict[str, Any]]:
    return [{"escalon": 1, "nocional_min": 0.0, "nocional_max": 10000.0, "mmr_pct": 1.0, "cum": 0.0,
             "apalancamiento_max": 50}]


# Respaldo si exchangeInfo de Futuros no contesta (desde la sesión de MECÁNICO responde 451). SUPUESTOS sin verificar,
# del lado prudente: pasos y mínimos de memoria (mínimo de 20 USDT donde había duda), tarifa de liquidación de 1.5 % (la
# más alta de las 4 monedas de F1) y escalón de MMR 1 % con cum 0 (como escalones.json). Con cum 0 la liquidación no
# depende de la cantidad, solo del apalancamiento.
RESPALDO_HOLDOUT: dict[str, dict[str, Any]] = {
    "ADAUSDT": {"filtros": Filtros("ADAUSDT", 0.0001, 1.0, 1.0, 5.0), "tarifa_liq_pct": 1.5,
                "escalones": _escalon_supuesto()},
    "LINKUSDT": {"filtros": Filtros("LINKUSDT", 0.001, 0.01, 0.01, 20.0), "tarifa_liq_pct": 1.5,
                 "escalones": _escalon_supuesto()},
    "AVAXUSDT": {"filtros": Filtros("AVAXUSDT", 0.001, 1.0, 1.0, 5.0), "tarifa_liq_pct": 1.5,
                 "escalones": _escalon_supuesto()},
    "LTCUSDT": {"filtros": Filtros("LTCUSDT", 0.01, 0.001, 0.001, 20.0), "tarifa_liq_pct": 1.5,
                "escalones": _escalon_supuesto()},
}


def puede_holdout(filas: list[dict[str, Any]], nombre: str) -> tuple[bool, str]:
    """¿Se puede abrir el holdout de la variante? (True, "") o (False, razón). Una sola vez por variante, y solo si su
    renglón «completa» MÁS RECIENTE pasó las 15 compuertas sin contar «escalones»."""
    variante(nombre)
    previas = [f for f in filas if f.get("variante") == nombre and f.get("tipo") == "holdout"]
    if previas:
        return False, (f"el holdout de {nombre} ya se abrió el {previas[0].get('fecha_utc')} (commit "
                       f"{previas[0].get('commit')}): se abre una sola vez por variante.")
    completas = [f for f in filas if f.get("variante") == nombre and f.get("tipo") == "completa"]
    if not completas:
        return False, f"{nombre} no tiene corrida completa en {ARCHIVO_REGISTRO}: primero validar-futuros --variante."
    ultima = completas[-1]
    if not ultima.get("pasa_sin_escalones"):
        return False, (f"{nombre} no pasó las 15 compuertas sin contar «escalones» en su corrida más reciente "
                       f"({ultima.get('fecha_utc')}, {ultima.get('veredicto')}): el holdout queda sellado.")
    return True, ""


# ---------------------------------------------------------------------------- registro (solo agregar)
COLUMNAS = (("fecha_utc", "Fecha UTC"), ("commit", "Commit"), ("variante", "Variante"), ("tipo", "Tipo"),
            ("veredicto", "Veredicto"), ("pasa_sin_escalones", "Pasa sin contar escalones"),
            ("compuertas", "Compuertas"), ("operaciones", "Ops"), ("expectativa_r", "Expectativa"),
            ("factor", "Factor"), ("t", "t"), ("azar_pct", "Azar %"), ("estres_r", "Estrés"),
            ("largo_r", "Largo"), ("corto_r", "Corto"))
ENCABEZADO = ("# Registro de corridas de validar-futuros (variantes de F1) — SOLO PAPEL\n\n"
              "Hipótesis 004 (HIPOTESIS.md). Solo se agregan renglones: cada corrida de `validar-futuros` (completa u "
              "holdout) agrega uno y nunca se borra ni se reemplaza ninguno. Ningún veredicto activa nada: activar es "
              "DECISIÓN DE ÁNGELO y exige escalones verificados y el Arreglo 152. Nada de esto promete ganancias.\n\n")


def _celda(clave: str, valor: Any) -> str:
    if clave == "pasa_sin_escalones":
        return "sí" if valor else "no"
    if isinstance(valor, float):
        if valor != valor:
            return "—"
        return f"{valor:.1f}" if clave == "azar_pct" else (f"{valor:.2f}" if clave in ("factor", "t") else f"{valor:+.3f}")
    return str(valor).replace("|", "/")


def _tabla_encabezado() -> str:
    return ("| " + " | ".join(t for _, t in COLUMNAS) + " |\n" + "|" + "---|" * len(COLUMNAS) + "\n")


def registrar_corrida(ruta: Path, fila: dict[str, Any]) -> str:
    """Agrega UN renglón al registro (lo crea con su encabezado si no existe). Regresa el renglón."""
    ruta = Path(ruta)
    renglon = "| " + " | ".join(_celda(k, fila.get(k, "")) for k, _ in COLUMNAS) + " |\n"
    if not ruta.exists():
        ruta.write_text(ENCABEZADO + _tabla_encabezado(), encoding="utf-8", newline="\n")
    antes = ruta.read_text(encoding="utf-8")
    extra = "" if antes.endswith("\n") else "\n"
    if "| Fecha UTC |" not in antes:            # un archivo sin la tabla: se le agrega el encabezado de la tabla
        extra += "\n" + _tabla_encabezado()
    with ruta.open("a", encoding="utf-8", newline="\n") as f:   # modo «a»: nunca reescribe lo que ya está
        f.write(extra + renglon)
    return renglon


def leer_registro(ruta: Path) -> list[dict[str, Any]]:
    """Los renglones del registro, en orden (el más reciente al final)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    filas, dentro = [], False
    claves = [k for k, _ in COLUMNAS]
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.startswith("| Fecha UTC |"):
            dentro = True
            continue
        if not dentro or not linea.startswith("|") or linea.startswith("|---"):
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) != len(claves):
            continue
        f = dict(zip(claves, celdas))
        f["pasa_sin_escalones"] = f["pasa_sin_escalones"] == "sí"
        filas.append(f)
    return filas
