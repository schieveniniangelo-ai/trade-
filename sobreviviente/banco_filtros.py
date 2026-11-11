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

import numpy as np
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
    # Protección contra sobreajuste (fase 5). N es del BANCO, no de las reglas vivas. Sale del espíritu de
    # `validacion.wf_min_operaciones_entrenamiento` (20 en general, 8 en motores lentos): aquí se usa el más exigente.
    min_operaciones: int = 20                         # con menos de N no se opina: "sin datos suficientes"
    bootstrap_n: int = 2000                           # repeticiones del remuestreo
    semilla: int | None = None                        # None = `validacion.semilla` del reglamento


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


# ---------------------------------------------------------------------------
# Walk-forward: ventanas de entrenamiento y de prueba. Se reporta SOLO la prueba (fuera de muestra).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Ventana:
    """Una ventana del walk-forward. El entrenamiento SOLO se observa (aquí no se elige ni se busca nada);
    los resultados que se publican salen únicamente de la prueba."""

    nombre: str                                               # mes en que empieza la prueba ("2023-01") o "prueba final"
    entrenamiento: tuple[pd.Timestamp, pd.Timestamp] | None   # [inicio, fin): None en la prueba final
    prueba: tuple[pd.Timestamp, pd.Timestamp]                 # [inicio, fin)
    final: bool = False                                       # la prueba final ya definida en el reglamento (se reporta aparte)


@dataclass
class ResultadoWF:
    reg: Reglamento
    cfg: ConfigBanco
    ventanas: list[Ventana]
    corridas: dict[str, dict[str, Corrida]]          # cartera → experimento → corrida de TODA la zona de prueba, de corrido
    solo_observado: dict[str, dict[str, Any]]        # ventana → lo que se vio en su entrenamiento. NO es un resultado.
    pool: Pool                                       # señales de la zona de prueba (lo único que entra a las corridas)


def ventanas(reg: Reglamento, con_prueba_final: bool = True) -> list[Ventana]:
    """Las mismas ventanas del walk-forward de la validación (`validacion.ventanas_wf`: los meses de entrenamiento y
    de prueba se LEEN del reglamento) y, al final, la prueba final ya definida (los últimos `holdout_meses`)."""
    from .validacion import fechas, ventanas_wf
    out = [Ventana(f"{c:%Y-%m}", (a, b), (c, d)) for a, b, c, d in ventanas_wf(reg)]
    f = fechas(reg)
    fin = f["fin"] + pd.Timedelta(minutes=1)          # `fin` es el último minuto del último día: la ventana cierra ahí
    if con_prueba_final and f["holdout"] < fin:
        out.append(Ventana("prueba final", None, (f["holdout"], fin), final=True))
    return out


def _en(t, tramo: tuple[pd.Timestamp, pd.Timestamp]) -> bool:
    return tramo[0] <= pd.Timestamp(t) < tramo[1]


def recortar(pool: Pool, inicio: pd.Timestamp, fin: pd.Timestamp) -> Pool:
    """Solo las señales cuya decisión cae en [inicio, fin). Lo de antes (entrenamiento) no entra a ninguna corrida."""
    base = pool.base
    if not base.empty:
        base = base[(base["t_decision"] >= inicio) & (base["t_decision"] < fin)].reset_index(drop=True)
    previos = [d for d in pool.previos if d["fecha"] and _en(d["fecha"], (inicio, fin))]
    return Pool(base=base, previos=previos, veto_estela=pool.veto_estela)


def walk_forward(reg: Reglamento, cfg: ConfigBanco, pool: Pool, filtros: dict, cierres: dict | None = None,
                 con_prueba_final: bool = True) -> ResultadoWF:
    """Corre la línea base y cada experimento SOLO con las señales de la zona de prueba (de la primera ventana de
    prueba al final de la última), de corrido, para que las posiciones abiertas pasen de una ventana a la otra y
    ninguna operación se cuente dos veces. Después cada operación se reporta en la ventana de su decisión.

    Del entrenamiento solo se anota cuántas señales había (`solo_observado`): no se usa para decidir nada."""
    vs = ventanas(reg, con_prueba_final)
    if not vs:
        raise ValueError("No hay ninguna ventana de prueba: el periodo del backtest es más corto que el entrenamiento.")
    zona = recortar(pool, vs[0].prueba[0], vs[-1].prueba[1])
    observado = {}
    for v in vs:
        if v.entrenamiento is None:
            continue
        b = pool.base
        tramo = b[(b["t_decision"] >= v.entrenamiento[0]) & (b["t_decision"] < v.entrenamiento[1])] if not b.empty else b
        observado[v.nombre] = {"senales": int(len(tramo)),
                               "por_motor": {str(k): int(n) for k, n in tramo.groupby("estrategia").size().items()}
                               if len(tramo) else {}}
    return ResultadoWF(reg, cfg, vs, ablacion(reg, cfg, zona, filtros, cierres), observado, zona)


def operaciones_de(corrida: Corrida, v: Ventana) -> pd.DataFrame:
    """Operaciones de la corrida cuya DECISIÓN cayó en la prueba de esa ventana."""
    ops = corrida.resultado.operaciones
    if ops is None or ops.empty:
        return pd.DataFrame()
    return ops[(ops["t_decision"] >= v.prueba[0]) & (ops["t_decision"] < v.prueba[1])].reset_index(drop=True)


def curva_de(corrida: Corrida, inicio: pd.Timestamp, fin: pd.Timestamp) -> pd.Series:
    """Tramo [inicio, fin) de la curva de capital de `backtest.cartera`, empezando con el capital que había al entrar."""
    c = corrida.resultado.curva
    antes = c[c.index < inicio]
    arranque = float(antes.iloc[-1]) if len(antes) else float(corrida.capital)
    return pd.concat([pd.Series([arranque], index=pd.DatetimeIndex([inicio])), c[(c.index >= inicio) & (c.index < fin)]])


def registro_de(corrida: Corrida, v: Ventana) -> list[dict[str, Any]]:
    """Decisiones (aprobadas o no) del registro de la corrida dentro de la prueba de esa ventana."""
    return [d for d in corrida.registro if _en(d["fecha"], v.prueba)]


def ventanas_de_prueba(wf: ResultadoWF) -> list[Ventana]:
    """Las ventanas del walk-forward, sin la prueba final (esa se reporta aparte)."""
    return [v for v in wf.ventanas if not v.final]


def anotacion_ventanas(wf: ResultadoWF) -> list[dict[str, Any]]:
    """Fechas de entrenamiento y de prueba de cada ventana, para el reporte."""
    def tramo(t):
        return "" if t is None else f"{t[0]:%Y-%m-%d} a {(t[1] - pd.Timedelta(minutes=1)):%Y-%m-%d}"

    return [{"ventana": v.nombre, "entrenamiento": tramo(v.entrenamiento), "prueba": tramo(v.prueba),
             "senales_vistas_en_entrenamiento": wf.solo_observado.get(v.nombre, {}).get("senales")}
            for v in wf.ventanas]


# ---------------------------------------------------------------------------
# Métricas por filtro (solo en las ventanas de prueba)
# ---------------------------------------------------------------------------

TODAS = "TODAS"   # todas las ventanas de prueba del walk-forward juntas (sin la prueba final, que va aparte)


def metricas(ops: pd.DataFrame | None, curva: pd.Series | None = None) -> dict[str, Any]:
    """Métricas de un grupo de operaciones: las de siempre (`metricas.resumen_r`) más el dinero.

    El dinero sale de `ganancia_usdt` = cantidad × pnl ya simulado, que YA trae descontadas la comisión y el
    deslizamiento (no se inventa otra comisión). La caída máxima es `metricas.caida_maxima_pct` sobre el tramo de
    la curva de `backtest.cartera`."""
    from .metricas import caida_maxima_pct, resumen_r
    hay = ops is not None and not ops.empty
    m = resumen_r(ops["r"].to_numpy(float) if hay else [])
    out = {"operaciones": int(m["operaciones"]), "pct_ganadoras": m["pct_ganadoras"], "expectativa_r": m["expectativa_r"],
           "factor_ganancia": m["factor_ganancia"],
           "expectativa_usdt": float(ops["ganancia_usdt"].mean()) if hay else 0.0,
           "ganancia_usdt": float(ops["ganancia_usdt"].sum()) if hay else 0.0}
    if curva is not None:
        out["caida_max_pct"] = caida_maxima_pct(curva.to_numpy(float))
    return out


def _zona_wf(wf: ResultadoWF) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    vs = ventanas_de_prueba(wf)
    return (vs[0].prueba[0], vs[-1].prueba[1]) if vs else None


def tramos(wf: ResultadoWF) -> list[tuple[str, tuple[pd.Timestamp, pd.Timestamp]]]:
    """Los tramos que se reportan: TODAS (el walk-forward completo), cada ventana de prueba y la prueba final."""
    zona = _zona_wf(wf)
    return ([(TODAS, zona)] if zona else []) + [(v.nombre, v.prueba) for v in wf.ventanas]


def metricas_corrida(wf: ResultadoWF, corrida: Corrida) -> dict[str, dict[str, Any]]:
    """tramo → métricas de esa corrida. Las operaciones cuentan en el tramo de su decisión."""
    out = {}
    ops = corrida.resultado.operaciones
    for nombre, (a, b) in tramos(wf):
        sub = ops[(ops["t_decision"] >= a) & (ops["t_decision"] < b)] if ops is not None and not ops.empty else None
        out[nombre] = metricas(sub, curva_de(corrida, a, b))
    return out


_DIFERENCIAS = ("operaciones", "expectativa_r", "expectativa_usdt", "ganancia_usdt", "caida_max_pct")


def tabla_metricas(wf: ResultadoWF) -> pd.DataFrame:
    """Una fila por cartera, experimento y tramo, con la diferencia contra la línea base del mismo tramo."""
    filas = []
    for cartera, corridas in wf.corridas.items():
        base = metricas_corrida(wf, corridas[BASE])
        for nombre, c in corridas.items():
            for tramo, m in metricas_corrida(wf, c).items():
                fila = {"cartera": cartera, "experimento": nombre, "accion": c.experimento.accion, "ventana": tramo, **m}
                for k in _DIFERENCIAS:
                    fila[f"dif_{k}"] = m[k] - base[tramo][k]
                filas.append(fila)
    return pd.DataFrame(filas)


def _riesgo_nominal_pct(reg: Reglamento, cartera: str, estrategia: str) -> float:
    return float(reg.para_cartera(cartera).riesgo_pct_estrategia(estrategia))


_COLUMNAS_BLOQUEADAS = ["estrategia", "simbolo", "t_decision", "r", "pnl_unidad", "capital", "t_salida"]


def senales_bloqueadas(wf: ResultadoWF, cartera: str, filtro: str,
                       tramo: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> pd.DataFrame:
    """Señales que ese filtro bloqueó (o bloquearía, si hoy está apagado) en la LÍNEA BASE, con su operación SUELTA.

    `r` y `pnl_unidad` son los de la simulación que ya traía el candidato (`backtest.simular_operacion`): lo que
    habría hecho esa señal SOLA. No es el efecto completo sobre la cartera (eso lo da la corrida con el filtro
    cambiado). `usdt_nominal` = r × capital de ese momento × riesgo por operación de la cartera: una estimación."""
    base = wf.corridas[cartera][BASE]
    tramo = tramo or _zona_wf(wf)
    nan = float("nan")
    filas = []
    c = base.candidatos
    if filtro == DS.VETO_ESTELA:
        marcadas = c[marca_estela(c, wf.pool.veto_estela)] if not c.empty else c
        capital = {(d["estrategia"], d["simbolo"], d["fecha"]): d.get("capital") for d in base.registro}
        for f in marcadas.itertuples(index=False):
            filas.append({"estrategia": f.estrategia, "simbolo": f.simbolo, "t_decision": f.t_decision, "r": f.r,
                          "pnl_unidad": f.pnl_unidad, "t_salida": f.t_salida,
                          "capital": capital.get((f.estrategia, f.simbolo, f.t_decision.isoformat()))})
    elif DS.CATALOGO.get(filtro, ("",))[0].startswith("B"):
        for d in wf.pool.previos:
            if d["codigo"] == filtro:
                filas.append({"estrategia": d["estrategia"], "simbolo": d["simbolo"], "t_decision": pd.Timestamp(d["fecha"]),
                              "r": d.get("r", nan), "pnl_unidad": d.get("pnl_unidad", nan), "capital": None,
                              "t_salida": d.get("candidato", {}).get("t_salida", pd.NaT)})
    else:
        sim = {(f.estrategia, f.simbolo, f.t_decision.isoformat()): (f.r, f.pnl_unidad, f.t_salida)
               for f in c.itertuples(index=False)} if not c.empty else {}
        for d in base.registro:
            if d["codigo"] == filtro and not d["aprobada"]:
                r, pnl, sale = sim.get((d["estrategia"], d["simbolo"], d["fecha"]), (nan, nan, pd.NaT))
                filas.append({"estrategia": d["estrategia"], "simbolo": d["simbolo"], "t_decision": pd.Timestamp(d["fecha"]),
                              "r": r, "pnl_unidad": pnl, "capital": d.get("capital"), "t_salida": sale})
    df = pd.DataFrame(filas, columns=_COLUMNAS_BLOQUEADAS)
    if not df.empty and tramo is not None:
        df = df[(df["t_decision"] >= tramo[0]) & (df["t_decision"] < tramo[1])].reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=_COLUMNAS_BLOQUEADAS + ["usdt_nominal"])
    capital = pd.to_numeric(df["capital"], errors="coerce").fillna(base.capital)
    riesgo = df["estrategia"].map(lambda e: _riesgo_nominal_pct(wf.reg, cartera, e))
    return df.assign(capital=capital, usdt_nominal=df["r"].astype(float) * capital * riesgo / 100.0)


def resumen_bloqueadas(df: pd.DataFrame) -> dict[str, Any]:
    """Cuántas señales bloqueó y cómo les habría ido SUELTAS (solo las que tienen simulación)."""
    from .metricas import resumen_r
    con = df[df["r"].notna()] if not df.empty else df
    m = resumen_r(con["r"].to_numpy(float) if len(con) else [])
    return {"senales": int(len(df)), "con_simulacion": int(len(con)), "sueltas_pct_ganadoras": m["pct_ganadoras"],
            "sueltas_expectativa_r": m["expectativa_r"], "sueltas_factor_ganancia": m["factor_ganancia"],
            "sueltas_suma_r": float(con["r"].sum()) if len(con) else 0.0,
            "sueltas_usdt_nominal": float(con["usdt_nominal"].sum()) if len(con) else 0.0}


def codigos_con_bloqueos(wf: ResultadoWF, cartera: str) -> list[str]:
    """Códigos que bloquearon al menos una señal en la línea base (en el orden del catálogo)."""
    vistos = {d["codigo"] for d in wf.corridas[cartera][BASE].registro if not d["aprobada"]}
    vistos |= {d["codigo"] for d in wf.pool.previos}
    if wf.pool.veto_estela is not None:
        vistos.add(DS.VETO_ESTELA)
    return [c for c in DS.CATALOGO if c in vistos]


def tabla_bloqueadas(wf: ResultadoWF) -> pd.DataFrame:
    """Una fila por cartera, filtro y tramo (TODAS y prueba final): señales bloqueadas y su resultado suelto."""
    zona = _zona_wf(wf)
    partes = ([(TODAS, zona)] if zona else []) + [(v.nombre, v.prueba) for v in wf.ventanas if v.final]
    filas = []
    for cartera in wf.corridas:
        for codigo in codigos_con_bloqueos(wf, cartera):
            for nombre, tramo in partes:
                filas.append({"cartera": cartera, "filtro": codigo, "ventana": nombre,
                              **resumen_bloqueadas(senales_bloqueadas(wf, cartera, codigo, tramo))})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Protección contra sobreajuste: muestra mínima, variación entre ventanas y remuestreo (bootstrap)
# ---------------------------------------------------------------------------
# Aquí NO se optimiza nada: no se buscan parámetros ni "la mejor combinación de filtros". Solo se describe, con
# cuidado, lo que se ve en las ventanas de prueba. Con pocos datos no se opina.

SIN_DATOS = "sin datos suficientes"
SIN_EFECTO = "no bloqueó nada"
PERDIAN = "bloqueó señales que perdían"
GANABAN = "bloqueó señales que ganaban"
NO_SE_DISTINGUE = "no se distingue de cero"

# Reglas que en el backtest no pueden bloquear nada, y por qué (para que el reporte no lo deje como "no sirve").
NOTAS_BACKTEST: dict[str, str] = {
    DS.FRENO_TOTAL: "en el backtest se simula el OK de Ángelo en cuanto se activa el freno, así que nunca bloquea "
                    "señales aquí; el reporte cuenta cuántas veces se habría detenido",
    DS.CONCILIACION: "en el backtest la conciliación siempre cuadra: no se puede medir aquí",
    DS.DATOS_NO_CONFIABLES: "en el backtest los datos se dan por buenos: no se puede medir aquí",
    DS.VETO_NOTICIAS: "no hay historial guardado de vetos de Noticias: no se puede medir aquí",
    DS.EVENTO_FUERTE: "no hay historial guardado de eventos fuertes: no se puede medir aquí",
}


def semilla_del_banco(reg: Reglamento, cfg: ConfigBanco) -> int:
    return int(cfg.semilla) if cfg.semilla is not None else int(reg.get("validacion.semilla", 0))


def intervalo_expectativa(r, n: int, semilla: int) -> dict[str, Any] | None:
    """Remuestreo sencillo (la misma idea del Monte Carlo de `validacion`): se vuelven a sacar las operaciones al
    azar, con reemplazo, `n` veces, y se ve entre qué valores cae la expectativa en R el 90 % de las veces.
    Con la misma semilla sale siempre lo mismo. None si no hay operaciones."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0 or n <= 0:
        return None
    rng = np.random.default_rng(semilla)
    medias = rng.choice(r, size=(int(n), len(r)), replace=True).mean(axis=1)
    return {"p5": float(np.percentile(medias, 5)), "p50": float(np.percentile(medias, 50)),
            "p95": float(np.percentile(medias, 95)), "repeticiones": int(n), "muestras": int(len(r))}


def episodios(bloqueadas: pd.DataFrame) -> pd.DataFrame:
    """Junta las señales repetidas del MISMO movimiento (mismo motor, misma moneda y misma salida simulada) en un
    solo episodio, con el R promedio. Un motor como M0 repite su señal cada día mientras la marea sigue alta: esas
    señales no son muestras independientes y, contadas una por una, harían ver seguro lo que no lo es."""
    con = bloqueadas[bloqueadas["r"].notna()] if not bloqueadas.empty else bloqueadas
    if con.empty:
        return pd.DataFrame(columns=["estrategia", "simbolo", "t_salida", "r", "senales"])
    g = con.groupby(["estrategia", "simbolo", "t_salida"], dropna=False)
    return g.agg(r=("r", "mean"), senales=("r", "size")).reset_index()


def variacion_entre_ventanas(wf: ResultadoWF, cartera: str, experimento: str) -> dict[str, Any]:
    """La diferencia contra la línea base, ventana de prueba por ventana (no solo el promedio)."""
    base = metricas_corrida(wf, wf.corridas[cartera][BASE])
    exp = metricas_corrida(wf, wf.corridas[cartera][experimento])
    por_ventana = [{"ventana": v.nombre,
                    "dif_operaciones": exp[v.nombre]["operaciones"] - base[v.nombre]["operaciones"],
                    "dif_ganancia_usdt": exp[v.nombre]["ganancia_usdt"] - base[v.nombre]["ganancia_usdt"],
                    "dif_caida_max_pct": exp[v.nombre]["caida_max_pct"] - base[v.nombre]["caida_max_pct"]}
                   for v in ventanas_de_prueba(wf)]
    d = np.array([x["dif_ganancia_usdt"] for x in por_ventana], dtype=float)
    if len(d) == 0:
        return {"ventanas": 0, "por_ventana": []}
    return {"ventanas": int(len(d)), "mejor_en": int((d > 1e-9).sum()), "peor_en": int((d < -1e-9).sum()),
            "igual_en": int((np.abs(d) <= 1e-9).sum()), "dif_usdt_min": float(d.min()),
            "dif_usdt_mediana": float(np.median(d)), "dif_usdt_max": float(d.max()),
            "dif_usdt_desviacion": float(d.std()), "por_ventana": por_ventana}


def veredicto(wf: ResultadoWF, cartera: str, experimento: str) -> dict[str, Any]:
    """Qué se puede decir de ese filtro con lo visto en las ventanas de prueba. No es un ranking ni una
    recomendación. Con menos de `min_operaciones` (N) no se opina: solo se avisa que faltan datos.

    N se pide tres veces: en las operaciones de la línea base, en las del experimento y en los EPISODIOS que el
    filtro tocó (señales bloqueadas con simulación, juntando las repetidas del mismo movimiento)."""
    cfg, c = wf.cfg, wf.corridas[cartera][experimento]
    exp = c.experimento
    n_min = int(cfg.min_operaciones)
    base_m = metricas_corrida(wf, wf.corridas[cartera][BASE])[TODAS]
    exp_m = metricas_corrida(wf, c)[TODAS]
    bloqueadas = senales_bloqueadas(wf, cartera, exp.filtro)
    epi = episodios(bloqueadas)
    out = {"cartera": cartera, "experimento": experimento, "accion": exp.accion, "min_operaciones": n_min,
           "operaciones_base": base_m["operaciones"], "operaciones_experimento": exp_m["operaciones"],
           "senales_afectadas": int(len(bloqueadas)), "episodios": int(len(epi)),
           "intervalo": None, "variacion": None, "nota": NOTAS_BACKTEST.get(exp.filtro, "")}
    verbo = "bloquearía" if exp.accion == "encender" else "bloqueó"
    if len(bloqueadas) == 0:
        out["estado"] = SIN_EFECTO
        out["texto"] = (f"No {verbo} ninguna señal en las ventanas de prueba: con este cambio sale lo mismo que la "
                        f"línea base." + (f" Ojo: {out['nota']}." if out["nota"] else ""))
        return out
    faltan = []
    if base_m["operaciones"] < n_min:
        faltan.append(f"la línea base tiene {base_m['operaciones']} operaciones")
    if exp_m["operaciones"] < n_min:
        faltan.append(f"el experimento tiene {exp_m['operaciones']} operaciones")
    if len(epi) < n_min:
        faltan.append(f"el filtro {verbo} {len(bloqueadas)} señales que son {len(epi)} episodios distintos con simulación")
    if faltan:
        out["estado"] = SIN_DATOS
        out["texto"] = (f"Sin datos suficientes: {'; '.join(faltan)} (se piden al menos {n_min}). No se opina sobre "
                        f"este filtro.")
        return out
    iv = intervalo_expectativa(epi["r"].to_numpy(float), int(cfg.bootstrap_n), semilla_del_banco(wf.reg, cfg))
    var = variacion_entre_ventanas(wf, cartera, experimento)
    out["intervalo"], out["variacion"] = iv, var
    if iv["p95"] < 0:
        out["estado"] = PERDIAN
        frase = f"Las señales que {verbo}, cada una por su cuenta, perdían en promedio"
    elif iv["p5"] > 0:
        out["estado"] = GANABAN
        frase = f"Las señales que {verbo}, cada una por su cuenta, ganaban en promedio"
    else:
        out["estado"] = NO_SE_DISTINGUE
        frase = f"No se distingue si las señales que {verbo} ganaban o perdían"
    dif = exp_m["ganancia_usdt"] - base_m["ganancia_usdt"]
    out["texto"] = (
        f"{frase} (expectativa suelta entre {iv['p5']:+.2f} R y {iv['p95']:+.2f} R en el 90 % de {iv['repeticiones']} "
        f"remuestreos de {iv['muestras']} episodios). Con el cambio, la cartera quedó {dif:+.2f} USDT contra la línea "
        f"base en las ventanas de prueba: mejor en {var['mejor_en']} de {var['ventanas']} ventanas, peor en "
        f"{var['peor_en']} e igual en {var['igual_en']} (por ventana, de {var['dif_usdt_min']:+.2f} a "
        f"{var['dif_usdt_max']:+.2f} USDT). Es lo que pasó en el pasado, no una promesa ni una recomendación: "
        f"cambiar una regla es DECISIÓN DE ÁNGELO.")
    return out


def linea_base(wf: ResultadoWF, cartera: str) -> dict[str, Any]:
    """Métricas de la línea base en las ventanas de prueba y, si hay muestra suficiente, el rango de su expectativa."""
    c = wf.corridas[cartera][BASE]
    m = metricas_corrida(wf, c)[TODAS]
    zona = _zona_wf(wf)
    ops = c.resultado.operaciones
    r = ops.loc[(ops["t_decision"] >= zona[0]) & (ops["t_decision"] < zona[1]), "r"].to_numpy(float) \
        if zona and not ops.empty else np.array([])
    suficiente = m["operaciones"] >= int(wf.cfg.min_operaciones)
    return {"cartera": cartera, **m, "detenciones": len(c.resultado.detenciones), "pausas": int(c.resultado.pausas),
            "intervalo": intervalo_expectativa(r, int(wf.cfg.bootstrap_n), semilla_del_banco(wf.reg, wf.cfg))
            if suficiente else None,
            "aviso": "" if suficiente else
            f"Sin datos suficientes: {m['operaciones']} operaciones en las ventanas de prueba (se piden al menos "
            f"{int(wf.cfg.min_operaciones)}). Los números de esta cartera pueden ser pura suerte."}


def tabla_veredictos(wf: ResultadoWF) -> pd.DataFrame:
    """Un renglón por cartera y filtro, en el orden del catálogo. NO es un ranking: no se ordena por resultado."""
    filas = []
    for cartera, corridas in wf.corridas.items():
        for nombre in corridas:
            if nombre == BASE:
                continue
            v = veredicto(wf, cartera, nombre)
            iv, var = v["intervalo"] or {}, v["variacion"] or {}
            filas.append({"cartera": cartera, "filtro": nombre, "accion": v["accion"], "estado": v["estado"],
                          "operaciones_base": v["operaciones_base"], "operaciones_experimento": v["operaciones_experimento"],
                          "senales_afectadas": v["senales_afectadas"], "episodios": v["episodios"],
                          "min_operaciones": v["min_operaciones"],
                          "suelta_r_p5": iv.get("p5"), "suelta_r_p50": iv.get("p50"), "suelta_r_p95": iv.get("p95"),
                          "ventanas": var.get("ventanas"), "mejor_en": var.get("mejor_en"), "peor_en": var.get("peor_en"),
                          "igual_en": var.get("igual_en"), "dif_usdt_min": var.get("dif_usdt_min"),
                          "dif_usdt_mediana": var.get("dif_usdt_mediana"), "dif_usdt_max": var.get("dif_usdt_max"),
                          "texto": v["texto"]})
    return pd.DataFrame(filas)
