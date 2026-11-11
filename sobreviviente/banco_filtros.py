"""Banco de pruebas de filtros y descartes. SOLO mide: es un experimento con datos del pasado, en papel.

Qué hace: toma las señales de los motores (con los parámetros que YA están en el reglamento; aquí no se busca
ningún parámetro), corre la cartera del backtest con el reglamento tal cual (la LÍNEA BASE) y la vuelve a correr
cambiando UN solo filtro a la vez (apagándolo, o encendiéndolo si hoy está apagado, como el veto de ESTELA).

Qué NO hace: no cambia `reglamento.yaml`, no toca la ronda de papel ni la ronda viva (ninguna de las dos importa
este archivo ni lee su configuración), no usa llaves ni red, y no enciende ni apaga nada por su cuenta. Si un
número sugiere cambiar una regla, eso va a PROPUESTAS.md como DECISIÓN DE ÁNGELO.

Aviso honesto: un backtest no promete nada. Con pocas operaciones un resultado puede ser pura suerte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from . import backtest as B
from . import descartes as DS
from .reglamento import Reglamento

BASE = "BASE"
MOTORES_ESTELA = ("M1", "M2")   # el veto de ESTELA solo aplica a estos motores (igual que en diario.generar y en papel)

# Descartes PREVIOS al motor de riesgo que el banco puede probar: la señal descartada (ya simulada) se vuelve a meter.
APAGABLES_GENERACION = frozenset({DS.FUERA_DE_UNIVERSO, DS.FUTUROS_NO_LIQUIDO})

# Lo que el banco NO prueba, y por qué (sale tal cual en el reporte).
NO_SE_PRUEBAN: dict[str, str] = {
    DS.STOP_INVALIDO: "no se apaga: un stop del lado equivocado (o un corto en Spot) no es una orden válida",
    DS.EXPOSICION_O_MARGEN: "no se apaga: no se puede comprar sin dinero libre (lo de memes y Futuros no aplica a "
                            "los motores de la v2)",
    DS.TAMANO_O_CAPITAL: "no se apaga: el mínimo de Binance no es una regla nuestra; solo se cuenta cuántas salta",
    DS.SIN_VELAS: "no se apaga: sin velas no se puede calcular la señal",
    DS.STOP_O_SIMULACION: "no se apaga: sin stop o sin vela siguiente no hay operación que simular",
    DS.SIN_SENAL: "solo existe en la ronda de papel (ahí se registra)",
    DS.COMPRAS_BLOQUEADAS: "solo existe en la ronda de papel (ronda FUERA DE HORA): ahí se registra",
    DS.SIN_FILTROS_O_PRECIO: "solo existe en la ronda de papel (falta un dato de Binance ese día): ahí se registra",
    DS.CANTIDAD_CERO: "solo existe en la ronda de papel: ahí se registra",
    DS.NO_SE_LLENO: "solo existe en la ronda de papel (la compra LIMIT no se llenó): ahí se registra",
    DS.SIN_EFECTIVO: "solo existe en la ronda de papel: ahí se registra",
    DS.MODO_SEGURO: "solo existe en la ronda de papel (protege contra datos malos): ahí se registra",
}


# ---------------------------------------------------------------------------
# Configuración del experimento (vive AQUÍ, no en reglamento.yaml)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigBanco:
    """Configuración del banco. No es parte de las reglas vivas: la ronda no la lee."""

    carteras: tuple[str, ...] = ("A", "B", "C")
    motores: tuple[str, ...] = ("M0", "M1", "M2")     # motores de los que se generan señales
    # Motores que cuentan como ENCENDIDOS. None = los que el reglamento tiene encendidos (estado distinto de APAGADA).
    # Poner aquí un motor que hoy está APAGADO es un ESTUDIO aparte, no la línea base vigente (el reporte lo dice).
    encendidos: tuple[str, ...] | None = None
    capital: float | None = None                      # None = `backtest.capital_ventaja` del reglamento
    reanudar_tras_detencion: bool = True              # como en la validación: tras el freno total se simula el OK
    filtros: tuple[str, ...] | None = None            # None = todos los que se pueden probar


@dataclass(frozen=True)
class Experimento:
    """Una corrida del banco: la línea base, o UN filtro cambiado."""

    nombre: str                 # "BASE" o el código del filtro
    filtro: str | None = None   # código del filtro que cambia (None = línea base)
    accion: str = ""            # "apagar" o "encender" ("" en la línea base)


@dataclass
class Pool:
    """Señales disponibles para el banco, cada una con su operación SUELTA ya simulada."""

    base: pd.DataFrame                                             # las que hoy sí llegan al motor de riesgo
    previos: list[dict[str, Any]] = field(default_factory=list)    # descartadas antes (registro de descartes.py)
    veto_estela: dict[str, set] | None = None                      # símbolo → días de señal que ESTELA vetaría; None = sin datos


@dataclass
class Corrida:
    experimento: Experimento
    cartera: str
    capital: float
    candidatos: pd.DataFrame
    resultado: B.ResultadoCartera
    registro: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Qué se puede probar
# ---------------------------------------------------------------------------

def capital_del_banco(reg: Reglamento, cfg: ConfigBanco) -> float:
    return float(cfg.capital) if cfg.capital is not None else float(reg.get("backtest.capital_ventaja"))


def motores_encendidos(reg: Reglamento, cfg: ConfigBanco) -> tuple[str, ...]:
    """Motores que cuentan como encendidos en las corridas. Por defecto, los que el reglamento NO tiene APAGADOS."""
    if cfg.encendidos is not None:
        return tuple(m for m in cfg.motores if m in cfg.encendidos)
    return tuple(m for m in cfg.motores if reg.estrategias.get(m, {}).get("estado", "APAGADA") != "APAGADA")


def es_linea_base_vigente(reg: Reglamento, cfg: ConfigBanco) -> bool:
    """True si los motores encendidos son exactamente los del reglamento (no es un estudio con motores apagados)."""
    return cfg.encendidos is None or motores_encendidos(reg, cfg) == motores_encendidos(reg, ConfigBanco(motores=cfg.motores))


def veto_estela_en_reglamento(reg: Reglamento) -> bool:
    return bool(reg.estrategias.get("M3", {}).get("veto_activo"))


def experimentos(reg: Reglamento, cfg: ConfigBanco, pool: Pool | None = None) -> list[Experimento]:
    """La línea base y, después, un experimento por cada filtro que se puede probar (uno a la vez)."""
    lista = [Experimento(BASE)]
    for codigo in DS.CATALOGO:   # en el orden del catálogo, para que el reporte salga siempre igual
        if cfg.filtros is not None and codigo not in cfg.filtros:
            continue
        if codigo in DS.APAGABLES_RIESGO or codigo in APAGABLES_GENERACION:
            lista.append(Experimento(codigo, codigo, "apagar"))
        elif codigo == DS.VETO_ESTELA and (pool is None or pool.veto_estela is not None):
            # Hoy el veto está apagado en el reglamento: el experimento es ENCENDERLO (y al revés si estuviera encendido)
            lista.append(Experimento(codigo, codigo, "apagar" if veto_estela_en_reglamento(reg) else "encender"))
    return lista


# ---------------------------------------------------------------------------
# Señales
# ---------------------------------------------------------------------------

def _ordenar(df: pd.DataFrame) -> pd.DataFrame:
    """Mismo orden que los generadores: por momento de decisión y, dentro del mismo momento, la más fuerte primero."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.reset_index(drop=True)
    return df.sort_values(["t_decision", "fuerza", "simbolo", "estrategia"],
                          ascending=[True, False, True, True]).reset_index(drop=True)


def generar_pool(md, cfg: ConfigBanco, inicio, fin, veto_estela: dict[str, set] | None = None) -> Pool:
    """Señales de los motores diarios (M0, M1, M2) con los parámetros del reglamento vigente. No busca parámetros.

    Se generan SIN el veto de ESTELA (así está hoy el reglamento); el veto se prueba marcando sus señales."""
    from . import diario as DI
    partes, previos = [], []
    guardado, md.veto = md.veto, None
    try:
        for clave in cfg.motores:
            params = dict(md.reg.estrategias[clave]["parametros"])
            c = DI.generar(md, clave, params, inicio, fin, descartes=previos)
            if not c.empty:
                partes.append(c)
    finally:
        md.veto = guardado
    base = _ordenar(pd.concat(partes, ignore_index=True)) if partes else pd.DataFrame()
    return Pool(base=base, previos=previos, veto_estela=veto_estela)


def marca_estela(df: pd.DataFrame, veto: dict[str, set] | None) -> pd.Series:
    """True en las señales que el veto de ESTELA quitaría (solo M1 y M2, por día de la señal)."""
    if df.empty or not veto:
        return pd.Series(False, index=df.index)
    return pd.Series([e in MOTORES_ESTELA and t in veto.get(s, ()) for e, s, t in
                      zip(df["estrategia"], df["simbolo"], df["t_senal"])], index=df.index)


def candidatos_de(reg: Reglamento, pool: Pool, exp: Experimento) -> pd.DataFrame:
    """Las señales que llegan al motor de riesgo en ese experimento."""
    df = pool.base
    if exp.filtro in APAGABLES_GENERACION:
        extra = [d["candidato"] for d in pool.previos if d["codigo"] == exp.filtro and "candidato" in d]
        if extra:
            df = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
    con_veto = veto_estela_en_reglamento(reg)
    if exp.filtro == DS.VETO_ESTELA:
        con_veto = exp.accion == "encender"
    if con_veto and pool.veto_estela is not None and not df.empty:
        df = df[~marca_estela(df, pool.veto_estela)]
    return _ordenar(df)


# ---------------------------------------------------------------------------
# Corridas
# ---------------------------------------------------------------------------

def correr(reg: Reglamento, cfg: ConfigBanco, pool: Pool, exp: Experimento, cartera: str, filtros: dict,
           cierres: dict | None = None) -> Corrida:
    """Corre la cartera del backtest (`backtest.cartera`, el mismo motor de riesgo de siempre) para un experimento.
    La línea base es el reglamento de esa cartera sin tocar; un experimento cambia UN filtro."""
    capital = capital_del_banco(reg, cfg)
    cands = candidatos_de(reg, pool, exp)
    registro: list[dict[str, Any]] = []
    apagar = frozenset({exp.filtro}) if exp.filtro in DS.APAGABLES_RIESGO else frozenset()
    rc = B.cartera(reg.para_cartera(cartera), cands, capital, filtros, list(motores_encendidos(reg, cfg)),
                   cfg.reanudar_tras_detencion, cierres, registro=registro, nombre_cartera=cartera,
                   apagar_en_banco=apagar)
    return Corrida(exp, cartera, capital, cands, rc, registro)


def ablacion(reg: Reglamento, cfg: ConfigBanco, pool: Pool, filtros: dict,
             cierres: dict | None = None) -> dict[str, dict[str, Corrida]]:
    """Por cada cartera: la línea base y un experimento por filtro. Regresa cartera → nombre del experimento → corrida."""
    return {n: {e.nombre: correr(reg, cfg, pool, e, n, filtros, cierres) for e in experimentos(reg, cfg, pool)}
            for n in cfg.carteras}
