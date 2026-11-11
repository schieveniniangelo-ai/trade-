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
    cierres: dict | None = None                      # cierres diarios por moneda (para la caída a valor de mercado)


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
    return ResultadoWF(reg, cfg, vs, ablacion(reg, cfg, zona, filtros, cierres), observado, zona, cierres)


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
    """tramo → métricas de esa corrida. Las operaciones cuentan en el tramo de su decisión.

    Si hay cierres diarios, se agrega `caida_max_mercado_pct`: la caída sobre la curva diaria A VALOR DE MERCADO
    (`backtest.curva_diaria`), que también cuenta lo que va perdiendo una posición mientras sigue abierta. La
    `caida_max_pct` de siempre solo ve el capital después de cada cierre, así que se queda corta."""
    from .metricas import caida_maxima_pct
    out = {}
    ops = corrida.resultado.operaciones
    hay = ops is not None and not ops.empty
    ts = tramos(wf)
    diaria = None
    if wf.cierres is not None and hay and ts:
        diaria = B.curva_diaria(ops, corrida.capital, wf.cierres, min(a for _, (a, _) in ts), max(b for _, (_, b) in ts))
    for nombre, (a, b) in ts:
        sub = ops[(ops["t_decision"] >= a) & (ops["t_decision"] < b)] if hay else None
        out[nombre] = metricas(sub, curva_de(corrida, a, b))
        if wf.cierres is not None:
            tramo = diaria[(diaria.index >= a) & (diaria.index <= b)] if diaria is not None else []
            out[nombre]["caida_max_mercado_pct"] = caida_maxima_pct(tramo.to_numpy(float)) if len(tramo) else 0.0
    return out


_DIFERENCIAS = ("operaciones", "expectativa_r", "expectativa_usdt", "ganancia_usdt", "caida_max_pct",
                "caida_max_mercado_pct")


def tabla_metricas(wf: ResultadoWF) -> pd.DataFrame:
    """Una fila por cartera, experimento y tramo, con la diferencia contra la línea base del mismo tramo."""
    filas = []
    for cartera, corridas in wf.corridas.items():
        base = metricas_corrida(wf, corridas[BASE])
        for nombre, c in corridas.items():
            for tramo, m in metricas_corrida(wf, c).items():
                fila = {"cartera": cartera, "experimento": nombre, "accion": c.experimento.accion, "ventana": tramo, **m}
                for k in _DIFERENCIAS:
                    if k in m:
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
    return {"senales": int(len(df)), "con_simulacion": int(len(con)), "episodios": int(len(episodios(df))),
            "sueltas_pct_ganadoras": m["pct_ganadoras"],
            "sueltas_expectativa_r": m["expectativa_r"], "sueltas_factor_ganancia": m["factor_ganancia"],
            "sueltas_suma_r": float(con["r"].sum()) if len(con) else 0.0,
            "sueltas_usdt_nominal": float(con["usdt_nominal"].sum()) if len(con) else 0.0,
            "sueltas_usdt_nominal_por_senal": float(con["usdt_nominal"].mean()) if len(con) else 0.0}


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
    apagados = sorted(set(bloqueadas["estrategia"]) - set(motores_encendidos(wf.reg, cfg))) if len(bloqueadas) else []
    if apagados and exp.filtro != DS.ESTRATEGIA_APAGADA:
        out["nota"] = (f"las señales que toca son de motores APAGADOS en esta corrida ({', '.join(apagados)}): "
                       f"mientras sigan apagados, cambiar este filtro no mueve la cartera")
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
                        f"este filtro." + (f" Ojo: {out['nota']}." if out["nota"] else ""))
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
        f"cambiar una regla es DECISIÓN DE ÁNGELO." + (f" Ojo: {out['nota']}." if out["nota"] else ""))
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


# ---------------------------------------------------------------------------
# Comando `banco-filtros`: lee SOLO velas ya guardadas y escribe el reporte en salida/
# ---------------------------------------------------------------------------

class ErrorBanco(Exception):
    """Falta algo para correr el banco (por ejemplo, las velas guardadas). El mensaje se le muestra a la persona."""


class CacheLocal:
    """Solo sabe en qué carpeta están los archivos ya descargados. No tiene conexión: con esto es imposible
    que el banco salga a internet o toque una llave."""

    def __init__(self, reg: Reglamento):
        from . import archivos as AR
        self.carpeta = AR.carpeta_datos(reg)
        self.cache = self.carpeta / "cache"


def _leer_json(ruta, defecto):
    import json
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return defecto


def cargar_guardado(reg: Reglamento, avisar=print) -> tuple[Any, dict[str, set] | None, list[str]]:
    """Mercado diario armado con las velas que ya están en `datos/cache` (las del comando `descargar`), sin red.
    Regresa (mercado, días que vetaría ESTELA o None si no hay datos guardados de ESTELA, avisos)."""
    from . import datos as D
    from . import diario as DI
    local = CacheLocal(reg)
    avisos: list[str] = []
    if not (local.cache / "resumen_descarga.json").exists():
        raise ErrorBanco(f"No hay velas guardadas en {local.cache}. Corre primero `python -m sobreviviente descargar` "
                         f"(el banco no baja nada: solo lee lo que ya está guardado).")
    memes = _leer_json(local.carpeta / "memes.json", None)
    if not isinstance(memes, dict) or not isinstance(memes.get("memes"), list):
        avisos.append("No se pudo leer memes.json: los memes no se quitaron del universo en esta corrida.")
        memes = {"memes": []}
    info = _leer_json(local.cache / "exchangeinfo_spot.json", None)
    if not isinstance(info, dict) or not isinstance(info.get("symbols"), list):
        avisos.append("No hay copia guardada de las reglas de Binance (exchangeInfo): se usaron mínimos supuestos.")
        info = {"symbols": []}
    avisar("Leyendo las velas diarias guardadas…")
    try:
        md = DI.cargar(reg, local, memes["memes"], exchange_info=info)
    except D.ErrorDatos as e:
        raise ErrorBanco(f"Las velas guardadas no alcanzan para correr el banco: {e}.") from e
    veto = None
    try:
        from . import estela as ES
        simbolos = sorted(c for c in md.grandes.columns if md.grandes[c].any())
        veto = ES.dias_veto_h2(reg, local, simbolos) or None
    except Exception as e:  # noqa: BLE001 - ESTELA es opcional: sin sus datos, ese experimento simplemente no se corre
        avisos.append(f"No se pudieron leer los datos guardados de ESTELA ({type(e).__name__}): su veto no se probó.")
    if veto is None and not any("ESTELA" in a for a in avisos):
        avisos.append("No hay datos guardados de ESTELA: su veto no se probó.")
    return md, veto, avisos


def ejecutar(reg: Reglamento, cfg: ConfigBanco, avisar=print, con_prueba_final: bool = True) -> tuple[ResultadoWF, list[str]]:
    """Todo el banco con las velas guardadas: señales → línea base y experimentos → solo ventanas de prueba."""
    from .validacion import fechas
    md, veto, avisos = cargar_guardado(reg, avisar)
    f = fechas(reg)
    avisar(f"Generando las señales de {', '.join(cfg.motores)} con los parámetros del reglamento…")
    pool = generar_pool(md, cfg, f["inicio"], f["fin"], veto)
    n_exp = len(experimentos(reg, cfg, pool))
    avisar(f"Corriendo la línea base y {n_exp - 1} experimentos en {len(cfg.carteras)} cartera(s)…")
    return walk_forward(reg, cfg, pool, md.filtros, md.cierres(), con_prueba_final), avisos


# ----------------------------------------------------------------- reporte

def _num(x, dec: int = 2, signo: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    if isinstance(x, float) and np.isinf(x):
        return "sin pérdidas"
    return f"{x:+.{dec}f}" if signo else f"{x:.{dec}f}"


def _tabla_md(encabezados: list[str], filas: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(encabezados) + " |", "|" + "---|" * len(encabezados)]
    out += ["| " + " | ".join(str(x) for x in fila) + " |" for fila in filas]
    return out


def _fila_metricas(m: dict[str, Any], base: dict[str, Any] | None = None) -> list[str]:
    def con_dif(k, dec=2):
        if k not in m:
            return "—"
        return _num(m[k], dec) + (f" ({_num(m[k] - base[k], dec, True)})" if base is not None else "")

    return [f"{m['operaciones']}" + (f" ({m['operaciones'] - base['operaciones']:+d})" if base is not None else ""),
            _num(m["pct_ganadoras"], 1), _num(m["expectativa_r"], 2, True), _num(m["expectativa_usdt"], 2, True),
            _num(m["factor_ganancia"]), con_dif("caida_max_pct", 1), con_dif("caida_max_mercado_pct", 1),
            con_dif("ganancia_usdt")]


_NOTA_CAIDAS = ("\"Caída máx.\" se mide sobre la curva de la cartera (el capital después de cada cierre). \"Caída a "
                "mercado\" cuenta también lo que va perdiendo una posición mientras sigue abierta (cierre de cada día): "
                "es la más realista y casi siempre la más grande.")


def texto_reporte(wf: ResultadoWF, avisos: list[str] | tuple[str, ...] = (), ahora=None) -> str:
    """El reporte en español sencillo (markdown). No recomienda nada y no promete nada."""
    from datetime import datetime, timezone
    reg, cfg = wf.reg, wf.cfg
    ahora = ahora or datetime.now(timezone.utc)
    encendidos = motores_encendidos(reg, cfg)
    n_min = int(cfg.min_operaciones)
    veredictos = {c: {n: veredicto(wf, c, n) for n in corridas if n != BASE} for c, corridas in wf.corridas.items()}
    L: list[str] = []
    L += ["# Banco de pruebas de filtros y descartes", "",
          f"Generado el {ahora:%Y-%m-%d %H:%M} UTC con velas ya guardadas (sin red y sin llaves de Binance).", "",
          "**Solo mide.** Es un experimento con datos del pasado, en papel. No cambia ninguna regla, no toca la ronda "
          "diaria y **no promete ganancias**: lo que pasó antes puede no repetirse. Si algún número sugiere cambiar "
          "una regla, eso es DECISIÓN DE ÁNGELO y va a PROPUESTAS.md; aquí nada se enciende ni se apaga solo.", ""]
    for a in avisos:
        L.append(f"- ⚠️ {a}")
    if avisos:
        L.append("")

    L += ["## Qué se midió", ""]
    params = "; ".join(f"{k} {dict(reg.estrategias[k]['parametros'])}" for k in cfg.motores)
    L.append(f"- **Motores y parámetros:** {params}. Son los del reglamento vigente: aquí no se buscó ni se eligió "
             f"ningún parámetro.")
    L.append(f"- **Motores encendidos en estas corridas:** {', '.join(encendidos) if encendidos else 'ninguno'}.")
    if not es_linea_base_vigente(reg, cfg):
        apagados = [m for m in encendidos if reg.estrategias[m].get("estado") == "APAGADA"]
        L.append(f"- ⚠️ **ESTUDIO, no la operación vigente:** {', '.join(apagados)} está(n) APAGADO(S) en el reglamento y "
                 f"aquí se trataron como encendidos solo para medir sus filtros.")
    L.append(f"- **Carteras:** {', '.join(cfg.carteras)}, cada una con sus reglas del reglamento. Capital de la prueba: "
             f"{capital_del_banco(reg, cfg):g} USDT.")
    L.append("- **Línea base:** el reglamento sin tocar. **Experimento:** la misma corrida cambiando UN solo filtro "
             "(apagarlo, o encenderlo si hoy está apagado). Nunca dos a la vez y nunca se buscó \"la mejor combinación\".")
    L.append(f"- **Ventanas (walk-forward):** {int(reg.get('validacion.wf_entrenamiento_meses'))} meses de entrenamiento "
             f"y {int(reg.get('validacion.wf_prueba_meses'))} de prueba (leídos del reglamento). En el entrenamiento solo "
             f"se observó; **todos los resultados de este reporte son de las ventanas de prueba** (fuera de muestra). "
             f"La prueba final va aparte.")
    L.append(f"- **Muestra mínima para opinar:** N = {n_min} (configuración del banco, no de las reglas vivas).")
    L += [""] + _tabla_md(["Ventana", "Entrenamiento (solo se observó)", "Prueba (lo que se reporta)",
                           "Señales vistas en el entrenamiento"],
                          [[a["ventana"], a["entrenamiento"] or "—", a["prueba"],
                            "—" if a["senales_vistas_en_entrenamiento"] is None else a["senales_vistas_en_entrenamiento"]]
                           for a in anotacion_ventanas(wf)]) + [""]

    L += ["## Advertencia de muestra chica", ""]
    for cartera in wf.corridas:
        lb = linea_base(wf, cartera)
        v = veredictos[cartera].values()
        sin = sum(1 for x in v if x["estado"] == SIN_DATOS)
        nada = sum(1 for x in v if x["estado"] == SIN_EFECTO)
        L.append(f"- **Cartera {cartera}:** {lb['operaciones']} operaciones en las ventanas de prueba. "
                 + (lb["aviso"] + " " if lb["aviso"] else "")
                 + f"De {len(veredictos[cartera])} filtros probados, {sin} quedaron como \"{SIN_DATOS}\" y {nada} no "
                   f"bloquearon nada.")
    L += ["", f"Con menos de {n_min} operaciones (en la línea base, en el experimento o en los episodios que tocó el "
              f"filtro) este reporte NO opina: un resultado con tan pocos casos puede ser pura suerte. Las señales "
              f"repetidas del mismo movimiento (mismo motor, moneda y salida) cuentan como un solo episodio.", ""]

    L += ["## Línea base (el reglamento sin tocar)", ""]
    enc = ["Cartera", "Tramo", "Operaciones", "Acierto %", "Expectativa R", "Expectativa USDT", "Factor de ganancia",
           "Caída máx. %", "Caída a mercado %", "Ganancia USDT", "Rango de la expectativa (R)"]
    filas = []
    for cartera, corridas in wf.corridas.items():
        m = metricas_corrida(wf, corridas[BASE])
        lb = linea_base(wf, cartera)
        rango = f"{lb['intervalo']['p5']:+.2f} a {lb['intervalo']['p95']:+.2f}" if lb["intervalo"] else SIN_DATOS
        if TODAS in m:
            filas.append([cartera, "ventanas de prueba"] + _fila_metricas(m[TODAS]) + [rango])
        for v in wf.ventanas:
            if v.final:
                filas.append([cartera, "prueba final (aparte)"] + _fila_metricas(m[v.nombre]) + ["—"])
    L += _tabla_md(enc, filas)
    L += ["", "Expectativa = lo que deja en promedio cada operación. R = lo que se arriesga en una operación. El dinero ya "
              "trae descontados la comisión y el deslizamiento de la simulación. " + _NOTA_CAIDAS, ""]
    for cartera, corridas in wf.corridas.items():
        r = corridas[BASE].resultado
        if r.detenciones or r.pausas:
            L.append(f"- Cartera {cartera}: el freno total se habría activado {len(r.detenciones)} vez/veces y hubo "
                     f"{int(r.pausas)} pausa(s) por tope diario o semanal en toda la corrida.")
    L.append("")

    L += ["## Un filtro cambiado a la vez", "",
          "Entre paréntesis, la diferencia contra la línea base de esa cartera. \"Señales\" = cuántas señales bloqueó "
          "(o bloquearía) ese filtro en la línea base.", ""]
    enc = ["Filtro", "Cambio", "Operaciones", "Acierto %", "Expectativa R", "Expectativa USDT", "Factor de ganancia",
           "Caída máx. %", "Caída a mercado %", "Ganancia USDT", "Señales", "Qué se puede decir"]
    for cartera, corridas in wf.corridas.items():
        base = metricas_corrida(wf, corridas[BASE])[TODAS]
        filas = [["LÍNEA BASE", "—"] + _fila_metricas(base) + ["—", "—"]]
        for nombre, c in corridas.items():
            if nombre == BASE:
                continue
            v = veredictos[cartera][nombre]
            filas.append([nombre, c.experimento.accion] + _fila_metricas(metricas_corrida(wf, c)[TODAS], base)
                         + [v["senales_afectadas"], v["estado"]])
        L += [f"### Cartera {cartera}", ""] + _tabla_md(enc, filas) + [""]
        for nombre, v in veredictos[cartera].items():
            if v["estado"] != SIN_EFECTO:
                L.append(f"- **{nombre}** ({DS.CATALOGO[nombre][1]}): {v['texto']}")
        nada = [n for n, v in veredictos[cartera].items() if v["estado"] == SIN_EFECTO]
        if nada:
            L.append(f"- **No bloquearon ninguna señal en las ventanas de prueba** (con el cambio sale lo mismo que la "
                     f"línea base): {', '.join(nada)}. Varios de ellos no se pueden medir en un backtest: ver la "
                     f"última sección.")
        L.append("")

    L += ["## Señales bloqueadas en la línea base y qué habría pasado con ellas", "",
          "\"Suelta\" = lo que habría hecho esa señal SOLA, con la simulación que ya traía (mismas salidas, comisión y "
          "deslizamiento). **No es el efecto completo sobre la cartera**: al entrar una operación más cambian el dinero "
          "libre, los lugares y los topes. El efecto completo es la corrida con el filtro cambiado (tabla de arriba). "
          "Los USDT son una estimación por señal con el riesgo por operación de la cartera. Ojo con las señales "
          "repetidas: un motor como M0 repite su señal cada día mientras la marea sigue alta, así que muchas "
          "\"señales\" son el mismo movimiento contado varias veces (por eso se muestran los episodios distintos).", ""]
    tb = tabla_bloqueadas(wf)
    enc = ["Cartera", "Filtro", "Señales bloqueadas", "Episodios distintos", "Acierto suelto %", "Expectativa suelta R",
           "USDT estimados por señal"]
    filas = []
    for x in (tb[tb["ventana"] == TODAS].itertuples(index=False) if not tb.empty else []):
        filas.append([x.cartera, x.filtro, x.senales, x.episodios if x.con_simulacion else "sin simulación",
                      _num(x.sueltas_pct_ganadoras, 1) if x.con_simulacion else "—",
                      _num(x.sueltas_expectativa_r, 2, True) if x.con_simulacion else "—",
                      _num(x.sueltas_usdt_nominal_por_senal, 2, True) if x.con_simulacion else "—"])
    L += (_tabla_md(enc, filas) if filas else ["Ningún filtro bloqueó señales en las ventanas de prueba."]) + [""]

    L += ["## Variación entre ventanas de prueba", ""]
    hubo = False
    for cartera in wf.corridas:
        for nombre, v in veredictos[cartera].items():
            if not v["variacion"]:
                continue
            hubo = True
            var = v["variacion"]
            L.append(f"**Cartera {cartera}, {nombre}:** mejor en {var['mejor_en']}, peor en {var['peor_en']} e igual en "
                     f"{var['igual_en']} de {var['ventanas']} ventanas. Diferencia por ventana: mínimo "
                     f"{var['dif_usdt_min']:+.2f}, mediana {var['dif_usdt_mediana']:+.2f}, máximo "
                     f"{var['dif_usdt_max']:+.2f} USDT.")
            L += [""] + _tabla_md(["Ventana", "Operaciones (dif.)", "Ganancia USDT (dif.)", "Caída máx. % (dif.)"],
                                  [[q["ventana"], f"{q['dif_operaciones']:+d}", _num(q["dif_ganancia_usdt"], 2, True),
                                    _num(q["dif_caida_max_pct"], 1, True)] for q in var["por_ventana"]]) + [""]
    if not hubo:
        L += [f"Ningún filtro llegó a la muestra mínima (N = {n_min}), así que no se compara ventana por ventana. "
              f"El detalle de todas formas está en los archivos CSV.", ""]

    L += ["## Lo que este banco no puede probar", ""]
    for codigo, razon in NO_SE_PRUEBAN.items():
        L.append(f"- **{codigo}** ({DS.CATALOGO[codigo][1]}): {razon}.")
    for codigo, razon in NOTAS_BACKTEST.items():
        L.append(f"- **{codigo}**: {razon}.")
    if wf.pool.veto_estela is None:
        L.append(f"- **{DS.VETO_ESTELA}**: no hay datos guardados de ESTELA, así que su veto no se probó.")
    L += ["", "## Qué sigue", "",
          "Nada de esto cambia una regla. Si un filtro parece sobrar o faltar, primero hay que ver si tiene muestra "
          "suficiente y si se sostiene ventana por ventana; y aun así, apagarlo, suavizarlo o encenderlo es **DECISIÓN "
          "DE ÁNGELO**. Un backtest describe el pasado: no asegura lo que viene.", ""]
    return "\n".join(L)


def escribir_reporte(wf: ResultadoWF, carpeta, avisos: list[str] | tuple[str, ...] = (), nombre: str = "banco_filtros",
                     ahora=None) -> dict[str, Any]:
    """Escribe el reporte (markdown) y las tablas (CSV) en `carpeta`. Regresa nombre → ruta."""
    from pathlib import Path
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = {"reporte": carpeta / f"{nombre}.md", "metricas": carpeta / f"{nombre}_metricas.csv",
             "bloqueadas": carpeta / f"{nombre}_bloqueadas.csv", "veredictos": carpeta / f"{nombre}_veredictos.csv"}
    rutas["reporte"].write_text(texto_reporte(wf, avisos, ahora), encoding="utf-8")
    tabla_metricas(wf).to_csv(rutas["metricas"], index=False, encoding="utf-8")
    tabla_bloqueadas(wf).to_csv(rutas["bloqueadas"], index=False, encoding="utf-8")
    tabla_veredictos(wf).to_csv(rutas["veredictos"], index=False, encoding="utf-8")
    return rutas


def comando(reg: Reglamento, args, avisar=print) -> int:
    """`python -m sobreviviente banco-filtros`. Código 0 si el reporte quedó escrito; 1 con un mensaje claro si no."""
    from pathlib import Path
    from . import archivos as AR
    desconocidos = [k for k in (getattr(args, "filtros", None) or []) if k not in DS.CATALOGO]
    if desconocidos:
        avisar(f"❌ No conozco estos filtros: {', '.join(desconocidos)}. Los códigos válidos están en descartes.py.")
        return 1
    motores = tuple(getattr(args, "motores", None) or ConfigBanco.motores)
    faltan = [m for m in motores + tuple(getattr(args, "encender", None) or ()) if m not in reg.estrategias]
    faltan += [c for c in (getattr(args, "carteras", None) or []) if c not in (reg.datos.get("carteras") or {})]
    if faltan:
        avisar(f"❌ No existen en el reglamento: {', '.join(faltan)}.")
        return 1
    encender = tuple(getattr(args, "encender", None) or ())
    cfg = ConfigBanco(
        carteras=tuple(getattr(args, "carteras", None) or ConfigBanco.carteras), motores=motores,
        encendidos=tuple(m for m in motores if m in encender or reg.estrategias[m].get("estado") != "APAGADA")
        if encender else None,
        capital=getattr(args, "capital", None),
        filtros=tuple(args.filtros) if getattr(args, "filtros", None) else None,
        min_operaciones=int(getattr(args, "min_operaciones", None) or ConfigBanco.min_operaciones),
        bootstrap_n=int(getattr(args, "bootstrap", None) or ConfigBanco.bootstrap_n),
        semilla=getattr(args, "semilla", None))
    try:
        wf, avisos = ejecutar(reg, cfg, avisar, con_prueba_final=not getattr(args, "sin_prueba_final", False))
    except (ErrorBanco, ValueError) as e:
        avisar(f"❌ {e}")
        return 1
    carpeta = Path(args.salida) if getattr(args, "salida", None) else AR.carpeta_datos(reg).parent / "salida"
    rutas = escribir_reporte(wf, carpeta, avisos, getattr(args, "nombre", None) or "banco_filtros")
    for cartera in wf.corridas:
        lb = linea_base(wf, cartera)
        avisar(f"Cartera {cartera}: {lb['operaciones']} operaciones en las ventanas de prueba."
               + (f" {lb['aviso']}" if lb["aviso"] else ""))
    avisar(f"Listo: {rutas['reporte']} (más 3 tablas CSV en la misma carpeta).")
    avisar("Esto solo mide. No cambió ninguna regla; cualquier cambio es DECISIÓN DE ÁNGELO.")
    return 0
