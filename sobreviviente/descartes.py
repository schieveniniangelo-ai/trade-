"""Registro de descartes: por qué una señal NO se convirtió en operación (o sí).

Aquí no se decide nada. Solo se le pone un CÓDIGO estable a cada motivo, para poder contar y comparar entre el
backtest y el papel. Los códigos salen de tres lugares:

  A) el motor de riesgo (`riesgo.evaluar_candidato`): cada "no" tiene su código;
  B) antes del motor de riesgo, al armar los candidatos del backtest (`backtest._candidatos_simbolo` y
     `diario.generar`): lo que antes se descartaba en silencio;
  C) la ronda de papel (`papel.ronda_cartera`): lo que solo pasa ahí (sin señal, no se llenó, etc.).

Cada registro es un diccionario con, al menos: codigo, texto, simbolo, fecha, cartera, estrategia, aprobada y origen.
Los códigos NO se renombran: si una regla cambia de texto, su código se queda igual.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APROBADA = "APROBADA"

# --- A) Motor de riesgo (riesgo.evaluar_candidato) ---
FRENO_TOTAL = "FRENO_TOTAL"
PAUSA_TOPE = "PAUSA_TOPE"
CONCILIACION = "CONCILIACION"
DATOS_NO_CONFIABLES = "DATOS_NO_CONFIABLES"
ESTRATEGIA_APAGADA = "ESTRATEGIA_APAGADA"
RACHA_PERDIDAS = "RACHA_PERDIDAS"
VETO_NOTICIAS = "VETO_NOTICIAS"
EVENTO_FUERTE = "EVENTO_FUERTE"
VOL_EXTREMA = "VOL_EXTREMA"
BTC_BAJISTA = "BTC_BAJISTA"
YA_HAY_POSICION = "YA_HAY_POSICION"
MAX_POSICIONES = "MAX_POSICIONES"
STOP_INVALIDO = "STOP_INVALIDO"
EXPOSICION_O_MARGEN = "EXPOSICION_O_MARGEN"
TAMANO_O_CAPITAL = "TAMANO_O_CAPITAL"
CALOR_LLENO = "CALOR_LLENO"
COSTOS = "COSTOS"

# --- B) Al armar los candidatos del backtest (antes del motor de riesgo) ---
SIN_VELAS = "SIN_VELAS"
FUERA_DE_UNIVERSO = "FUERA_DE_UNIVERSO"
FUTUROS_NO_LIQUIDO = "FUTUROS_NO_LIQUIDO"
STOP_O_SIMULACION = "STOP_O_SIMULACION"

# --- C) Solo en la ronda de papel ---
SIN_SENAL = "SIN_SENAL"
COMPRAS_BLOQUEADAS = "COMPRAS_BLOQUEADAS"
VETO_ESTELA = "VETO_ESTELA"
SIN_FILTROS_O_PRECIO = "SIN_FILTROS_O_PRECIO"
CANTIDAD_CERO = "CANTIDAD_CERO"
NO_SE_LLENO = "NO_SE_LLENO"
SIN_EFECTIVO = "SIN_EFECTIVO"
MODO_SEGURO = "MODO_SEGURO"

# código → (grupo, explicación sencilla)
CATALOGO: dict[str, tuple[str, str]] = {
    APROBADA: ("-", "la señal pasó todas las reglas"),
    FRENO_TOTAL: ("A", "freno total por caída máxima desde el pico (hace falta el OK de Ángelo)"),
    PAUSA_TOPE: ("A", "pausa por tope diario o semanal de pérdida"),
    CONCILIACION: ("A", "la conciliación no cuadra"),
    DATOS_NO_CONFIABLES: ("A", "los datos no son confiables"),
    ESTRATEGIA_APAGADA: ("A", "el motor está APAGADO en el reglamento"),
    RACHA_PERDIDAS: ("A", "pausa o ronda saltada por racha de pérdidas"),
    VETO_NOTICIAS: ("A", "veto de Noticias (CENTINELA)"),
    EVENTO_FUERTE: ("A", "evento fuerte cerca"),
    VOL_EXTREMA: ("A", "volatilidad EXTREMA: sin entradas nuevas"),
    BTC_BAJISTA: ("A", "BTC BAJISTA: no se abren largos en monedas normales"),
    YA_HAY_POSICION: ("A", "ya hay posición en esa moneda (nunca promediar) o una contraria"),
    MAX_POSICIONES: ("A", "máximo de posiciones abiertas por cubeta"),
    STOP_INVALIDO: ("A", "stop del lado equivocado de la entrada, o corto en Spot"),
    EXPOSICION_O_MARGEN: ("A", "cubeta de memes llena, sin USDT libre en Spot, margen, apalancamiento o liquidación"),
    TAMANO_O_CAPITAL: ("A", "tamaño no viable o saltada por capital (mínimo de Binance)"),
    CALOR_LLENO: ("A", "calor lleno: ya hay demasiado dinero en riesgo"),
    COSTOS: ("A", "la meta no cubre el múltiplo del costo de entrar y salir"),
    SIN_VELAS: ("B", "no hay velas suficientes para calcular la señal"),
    FUERA_DE_UNIVERSO: ("B/C", "la moneda no pertenece al universo de ese día"),
    FUTUROS_NO_LIQUIDO: ("B", "el perpetuo de Futuros no tiene volumen suficiente"),
    STOP_O_SIMULACION: ("B", "stop o ATR sin valor, o la operación no se pudo simular"),
    SIN_SENAL: ("C", "sin señal ese día"),
    COMPRAS_BLOQUEADAS: ("C", "ronda FUERA DE HORA u otro bloqueo de compras"),
    VETO_ESTELA: ("B/C", "veto de ESTELA (la masa está muy cargada en largo)"),
    SIN_FILTROS_O_PRECIO: ("C", "sin reglas de Binance para la moneda o sin precio de apertura"),
    CANTIDAD_CERO: ("C", "la cantidad redondeada al paso de Binance queda en 0"),
    NO_SE_LLENO: ("C", "no se llenó: abrió arriba del límite de compra"),
    SIN_EFECTIVO: ("C", "no alcanza el efectivo de la cartera"),
    MODO_SEGURO: ("C", "MODO SEGURO: hoy no hay compras nuevas"),
}

CAMPOS = ("codigo", "texto", "simbolo", "fecha", "cartera", "estrategia", "aprobada", "origen")

# Reglas del motor de riesgo que el BANCO DE PRUEBAS puede apagar (una a la vez) en un backtest de experimento.
# Las que no están aquí NUNCA se apagan, ni en el banco: no son una decisión nuestra, son un límite de verdad
# (stop del lado equivocado, mínimo de Binance, no hay dinero libre).
APAGABLES_RIESGO = frozenset({
    FRENO_TOTAL, PAUSA_TOPE, CONCILIACION, DATOS_NO_CONFIABLES, ESTRATEGIA_APAGADA, RACHA_PERDIDAS, VETO_NOTICIAS,
    EVENTO_FUERTE, VOL_EXTREMA, BTC_BAJISTA, YA_HAY_POSICION, MAX_POSICIONES, CALOR_LLENO, COSTOS,
})


def _fecha_txt(fecha: Any) -> str:
    """Día de la ronda ("2026-11-10") o momento de la decisión en texto ISO. Siempre texto, para poder comparar."""
    if fecha is None:
        return ""
    if isinstance(fecha, str):
        return fecha
    iso = getattr(fecha, "isoformat", None)
    return iso() if iso else str(fecha)


def registro(codigo: str, texto: str, simbolo: str, fecha: Any, cartera: str, estrategia: str,
             aprobada: bool = False, origen: str = "", **extra: Any) -> dict[str, Any]:
    """Arma UN registro con el esquema común. `extra` son datos de apoyo (capital, R de la operación suelta, etc.)."""
    r = {"codigo": codigo, "texto": str(texto), "simbolo": simbolo, "fecha": _fecha_txt(fecha),
         "cartera": cartera, "estrategia": estrategia, "aprobada": bool(aprobada), "origen": origen}
    r.update(extra)
    return r


# ---------------------------------------------------------------------------
# Papel: un archivo por día (datos/papel/descartes/descartes_<día>.json)
# ---------------------------------------------------------------------------

def ruta_del_dia(reg, dia: str) -> Path:
    from . import archivos as AR
    return AR.carpeta_datos(reg) / "papel" / "descartes" / f"descartes_{dia}.json"


def leer_del_dia(reg, dia: str) -> dict[str, list[dict[str, Any]]]:
    """Registros de ese día por cartera ({} si no hay archivo o no se puede leer). Solo lectura."""
    try:
        datos = json.loads(ruta_del_dia(reg, dia).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    carteras = datos.get("carteras") if isinstance(datos, dict) else None
    return carteras if isinstance(carteras, dict) else {}


def guardar_del_dia(reg, dia: str, cartera: str, registros: list[dict[str, Any]]) -> None:
    """Guarda los registros de UNA cartera en el archivo del día. Repetible: si la ronda de ese día se repite,
    los de esa cartera se reemplazan (nunca se duplican). Lanza OSError si no se puede escribir."""
    from . import archivos as AR
    carteras = leer_del_dia(reg, dia)
    carteras[cartera] = registros
    AR.escribir_json_seguro(ruta_del_dia(reg, dia), {"dia": dia, "carteras": carteras}, indent=None)
