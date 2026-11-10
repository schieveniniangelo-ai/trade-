"""Backtester: prueba las estrategias con datos del pasado usando EL MISMO código que en vivo.

Dos pasos:
1. `generar_candidatos`: cada señal se simula como operación independiente (entrada en la apertura
   de la vela siguiente, con deslizamiento y comisiones; stops al precio del stop o peor; si hay hueco,
   a la apertura; funding en futuros). Resultado en R (múltiplos del riesgo planeado).
2. `cartera`: recorre las señales en orden de tiempo y las pasa por `riesgo.evaluar_candidato`
   (el Guardián en código): capital, calor, posiciones máximas, topes, rachas, mínimos de Binance.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from . import datos as D
from . import regimen as RG
from . import riesgo as R
from . import universo as U
from .estrategias import ESTRATEGIAS
from .estrategias.base import Contexto
from .estrategias import e4 as E4
from .exchange import Filtros, filtros_desde_exchangeinfo, filtros_supuestos
from .gestion import EstadoGestion, vela
from .reglamento import Reglamento

log = logging.getLogger("sobreviviente.backtest")
DURACION = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}


# ---------------------------------------------------------------------------
# Datos históricos en memoria
# ---------------------------------------------------------------------------

@dataclass
class Mercado:
    """Todos los datos que necesita el backtest, ya preparados."""

    reg: Reglamento
    spot1h: dict[str, pd.DataFrame]
    spot4h: dict[str, pd.DataFrame]
    fut4h: dict[str, pd.DataFrame]
    funding: dict[str, pd.Series]
    volumen: pd.DataFrame            # volumen diario en USDT (Spot)
    pertenece: pd.DataFrame          # universo día por día (True/False)
    vol_mediano: pd.DataFrame        # volumen mediano de 30 días (de días anteriores)
    fut_liquido: pd.DataFrame        # perpetuo con volumen suficiente (día por día)
    btc_reg4h: pd.Series
    btc_vol4h: pd.Series
    reg4h: dict[str, pd.Series] = field(default_factory=dict)
    vol4h: dict[str, pd.Series] = field(default_factory=dict)
    memes: set[str] = field(default_factory=set)
    filtros: dict[str, Filtros] = field(default_factory=dict)
    fuerza_memes: pd.DataFrame | None = None


def cargar_mercado(reg: Reglamento, cliente: D.ClienteBinance, memes: list[str],
                   simbolos: list[str] | None = None) -> Mercado:
    """Lee los históricos de la caché y calcula régimen, volatilidad y universo."""
    import json
    resumen = json.loads((cliente.cache / "resumen_descarga.json").read_text())
    simbolos = simbolos or resumen["universo_alguna_vez"]
    spot1h = {}
    for s in simbolos:
        df = D.leer(D.ruta_cache(cliente, "spot", "1h", s))
        if not df.empty:
            spot1h[s] = df.astype({c: "float64" for c in ["open", "high", "low", "close", "volume", "quote_volume"]})
    if "BTCUSDT" not in spot1h:
        spot1h["BTCUSDT"] = D.leer(D.ruta_cache(cliente, "spot", "1h", "BTCUSDT"))
    spot4h = {s: D.resamplear(df, "4h") for s, df in spot1h.items()}
    diarios = {s: D.leer(D.ruta_cache(cliente, "spot", "1d", s)) for s in resumen["universo_alguna_vez"]}
    volumen = U.tabla_volumen(diarios)
    pertenece = U.pertenencia(reg, volumen)
    vol_mediano = volumen.rolling(int(reg.get("universo.dias_volumen")), min_periods=1).median().shift(1)

    fut4h, funding, fut_vol = {}, {}, {}
    for s in resumen.get("futuros", []):
        f1 = D.leer(D.ruta_cache(cliente, "futuros", "1h", s))
        if f1.empty:
            continue
        fut4h[s] = D.resamplear(f1, "4h")
        fut_vol[s] = f1["quote_volume"].resample("1D").sum()
        arch = cliente.cache / "futuros" / "funding" / f"{s}.csv.gz"
        if arch.exists():
            x = pd.read_csv(arch, index_col=0, compression="gzip")
            x.index = pd.to_datetime(x.index, utc=True)
            funding[s] = x.iloc[:, 0]
    fv = pd.DataFrame(fut_vol)
    umbral_f = float(reg.get("universo.futuros_volumen_min_usdt"))
    fut_liquido = (fv.rolling(30, min_periods=30).median().shift(1) >= umbral_f) if not fv.empty else pd.DataFrame()

    btc4 = spot4h["BTCUSDT"]
    m = Mercado(
        reg=reg, spot1h=spot1h, spot4h=spot4h, fut4h=fut4h, funding=funding, volumen=volumen,
        pertenece=pertenece, vol_mediano=vol_mediano, fut_liquido=fut_liquido,
        btc_reg4h=RG.tendencia(btc4, reg), btc_vol4h=RG.percentil_volatilidad(btc4, reg),
        memes={x if x.endswith("USDT") else x + "USDT" for x in memes},
    )
    for s, df in spot4h.items():
        m.reg4h[s] = RG.tendencia(df, reg)
        m.vol4h[s] = RG.percentil_volatilidad(df, reg)

    # Reglas de Binance de cada moneda (las actuales; las deslistadas también aparecen con estado BREAK).
    info = cliente.exchange_info("SPOT")
    por_simbolo = {x["symbol"]: x for x in info["symbols"]}
    minimo_resp = float(reg.get("backtest.minimo_respaldo_usdt", 5.0))
    for s, df in spot1h.items():
        if s in por_simbolo:
            m.filtros[s] = filtros_desde_exchangeinfo(por_simbolo[s])
        else:
            m.filtros[s] = filtros_supuestos(s, float(df["close"].iloc[-1]), minimo_resp)

    # Fuerza relativa de memes (hora por hora, solo entre memes que estaban en el universo)
    memes_presentes = [s for s in spot1h if s in m.memes]
    if memes_presentes:
        cierres = pd.DataFrame({s: spot1h[s]["close"] for s in memes_presentes})
        per_h = pertenece.reindex(columns=memes_presentes)
        per_h = per_h.reindex(cierres.index.floor("D")).set_axis(cierres.index)
        m.fuerza_memes = E4.fuerza_relativa(cierres, per_h)
    return m


# ---------------------------------------------------------------------------
# Contextos por moneda
# ---------------------------------------------------------------------------

_CTX_CACHE: dict[tuple[str, str], Contexto] = {}


def contexto(m: Mercado, clave: str, simbolo: str) -> Contexto | None:
    """Arma el Contexto de una moneda para una estrategia (con caché de indicadores)."""
    k = (clave, simbolo)
    if k in _CTX_CACHE:
        return _CTX_CACHE[k]
    mod = ESTRATEGIAS[clave]
    if clave == "E5":
        velas = m.fut4h.get(simbolo)
        if velas is None or simbolo not in m.reg4h:
            return None
        reg_m = m.reg4h[simbolo].reindex(velas.index)
        extra = {}
        if simbolo in m.funding:
            f = m.funding[simbolo]
            # El funding se conoce en su hora; la decisión es al cierre de la vela (apertura + 4 h).
            idx_cierre = velas.index + pd.Timedelta(hours=4)
            extra["funding"] = pd.Series(f.reindex(idx_cierre, method="ffill").values, index=velas.index)
    elif mod.TEMPORALIDAD == "4h":
        velas = m.spot4h.get(simbolo)
        if velas is None:
            return None
        reg_m = m.reg4h[simbolo]
        extra = {}
    else:
        velas = m.spot1h.get(simbolo)
        if velas is None:
            return None
        reg_m = RG.a_intervalo_menor(m.reg4h[simbolo], velas.index)
        extra = {"regimen_moneda_4h": reg_m}
        if clave == "E4" and m.fuerza_memes is not None and simbolo in m.fuerza_memes:
            extra["fuerza_relativa"] = m.fuerza_memes[simbolo].reindex(velas.index)
    if mod.TEMPORALIDAD == "4h":
        reg_btc = m.btc_reg4h.reindex(velas.index)
    else:
        reg_btc = RG.a_intervalo_menor(m.btc_reg4h, velas.index)
    ctx = Contexto(simbolo=simbolo, velas=velas, regimen_moneda=reg_m, regimen_btc=reg_btc, extra=extra)
    _CTX_CACHE[k] = ctx
    return ctx


def simbolos_estrategia(m: Mercado, clave: str) -> list[str]:
    """Monedas en las que puede operar cada estrategia."""
    if clave == "E4":
        return sorted(s for s in m.spot1h if s in m.memes)
    if clave == "E5":
        return sorted(s for s in m.fut4h if s not in m.memes)
    return sorted(s for s in m.spot1h if s not in m.memes)


# ---------------------------------------------------------------------------
# Simulación de una operación
# ---------------------------------------------------------------------------

def simular_operacion(arr: dict[str, np.ndarray], indice: pd.DatetimeIndex, i_senal: int, lado: str,
                      precio_plan: float, stop0: float, meta: float | None, gest: dict[str, Any],
                      comision_pct: float, desliz_pct: float, duracion: pd.Timedelta,
                      funding: pd.Series | None = None, en_r: float = 1.0) -> dict[str, Any] | None:
    """Simula UNA operación desde la vela siguiente a la señal. Regresa None si no hay vela siguiente."""
    e = i_senal + 1
    n = len(arr["o"])
    if e >= n:
        return None
    largo = lado == "LARGO"
    s = desliz_pct / 100.0
    entrada = arr["o"][e] * (1 + s if largo else 1 - s)
    costo_pct = 2 * (comision_pct + desliz_pct)
    params = {k: v for k, v in gest.items() if k != "modo"}
    est = EstadoGestion(lado=lado, entrada=entrada, entrada_plan=precio_plan, stop_inicial=stop0, stop=stop0,
                        meta=meta, modo=gest["modo"], params=params, costo_pct=costo_pct, en_r=en_r)
    media = arr.get("media")
    tiempos_stop = []
    stops = []
    salida = None
    motivo = "sigue abierta"
    j = e
    o, h, l, c, a = arr["o"], arr["h"], arr["l"], arr["c"], arr["atr"]
    for j in range(e, n):
        ev = vela(est, o[j], h[j], l[j], c[j], a[j], None if media is None else media[j])
        if ev.salio:
            salida = ev.precio
            motivo = ev.motivo
            break
        tiempos_stop.append(j)
        stops.append(est.stop)
    abierta = salida is None
    if abierta:
        salida = c[n - 1]
        j = n - 1
    salida_real = salida * (1 - s if largo else 1 + s)
    comisiones = (entrada + salida_real) * comision_pct / 100.0
    t_entrada = indice[e]
    t_salida = indice[j] + duracion
    fund = 0.0
    if funding is not None and not largo and len(funding):
        tramo = funding[(funding.index > t_entrada) & (funding.index <= t_salida)]
        fund = float(tramo.sum()) * entrada  # positivo: los cortos cobran
    elif funding is not None and largo and len(funding):
        tramo = funding[(funding.index > t_entrada) & (funding.index <= t_salida)]
        fund = -float(tramo.sum()) * entrada
    bruto = (salida_real - entrada) if largo else (entrada - salida_real)
    pnl = bruto - comisiones + fund
    r_unidad = abs(precio_plan - stop0)
    return {
        "t_entrada": t_entrada, "t_salida": t_salida, "entrada": entrada, "salida": salida_real,
        "motivo": motivo, "abierta": abierta, "pnl_unidad": pnl, "r": pnl / r_unidad if r_unidad > 0 else 0.0,
        "comision_unidad": comisiones, "funding_unidad": fund, "velas": j - e + 1,
        "stops_t": [int((indice[k] + duracion).value) for k in tiempos_stop], "stops": stops,
    }


def _arrays(ctx: Contexto, gest: dict[str, Any]) -> dict[str, np.ndarray]:
    v = ctx.velas
    arr = {"o": v["open"].to_numpy(float), "h": v["high"].to_numpy(float), "l": v["low"].to_numpy(float),
           "c": v["close"].to_numpy(float), "atr": ctx.atr().to_numpy(float)}
    if gest["modo"] == "media":
        arr["media"] = ctx.sma(int(gest["salida_media"])).to_numpy(float)
    return arr


# ---------------------------------------------------------------------------
# Candidatos de una estrategia
# ---------------------------------------------------------------------------

_M: Mercado | None = None  # mercado global para los procesos hijos


def _candidatos_simbolo(args) -> list[dict[str, Any]]:
    clave, simbolo, params, inicio, fin, filas_azar = args
    m = _M
    reg = m.reg
    mod = ESTRATEGIAS[clave]
    cfg = reg.estrategias[clave]
    ctx = contexto(m, clave, simbolo)
    if ctx is None or len(ctx.velas) < 300:
        return []
    sen = mod.senales(ctx, params)
    gest = mod.gestion(params)
    if filas_azar is not None:
        idx_senales = np.asarray(filas_azar, dtype=int)
    else:
        mask = sen["entrada"].to_numpy() & (ctx.velas.index >= inicio) & (ctx.velas.index <= fin)
        idx_senales = np.flatnonzero(mask)
    if len(idx_senales) == 0:
        return []
    duracion = DURACION[mod.TEMPORALIDAD]
    arr = _arrays(ctx, gest)
    es_meme = simbolo in m.memes
    comision = float(reg.costos["comision_futuros_taker_pct"] if cfg["mercado"] == "FUTUROS" else reg.costos["comision_spot_pct"])
    funding = m.funding.get(simbolo) if cfg["mercado"] == "FUTUROS" else None
    en_r = float(reg.riesgo["gestion"]["mover_a_entrada_en_r"])
    out = []
    stops = sen["stop"].to_numpy(float)
    metas = sen["meta"].to_numpy(float)
    fuerzas = sen["fuerza"].to_numpy(float)
    precios = sen["precio"].to_numpy(float)
    for i in idx_senales:
        t_senal = ctx.velas.index[i]
        t_decision = t_senal + duracion
        dia = t_decision.floor("D")
        # Universo (solo con datos de días anteriores)
        try:
            en_universo = bool(m.pertenece.at[dia, simbolo])
        except KeyError:
            en_universo = False
        if not en_universo:
            continue
        if cfg["mercado"] == "FUTUROS":
            try:
                if not bool(m.fut_liquido.at[dia, simbolo]):
                    continue
            except KeyError:
                continue
        stop0 = stops[i]
        if not np.isfinite(stop0) or not np.isfinite(arr["atr"][i]):
            continue
        meta = metas[i] if np.isfinite(metas[i]) else None
        vm = m.vol_mediano.at[dia, simbolo] if dia in m.vol_mediano.index else np.nan
        liquidez = U.clasificar_liquidez(reg, float(vm) if np.isfinite(vm) else 0.0, es_meme)
        desliz = U.deslizamiento(reg, liquidez)
        sim = simular_operacion(arr, ctx.velas.index, i, cfg["lado"], precios[i], stop0, meta, gest,
                                comision, desliz, duracion, funding, en_r)
        if sim is None:
            continue
        t4 = t_decision - pd.Timedelta(hours=4)
        vol_m = m.vol4h[simbolo].asof(t4) if simbolo in m.vol4h else np.nan
        out.append({
            "estrategia": clave, "simbolo": simbolo, "t_senal": t_senal, "t_decision": t_decision,
            "precio_plan": precios[i], "stop": stop0, "meta": meta, "fuerza": fuerzas[i],
            "comision_pct": comision, "desliz_pct": desliz, "liquidez": liquidez,
            "regimen_btc": m.btc_reg4h.asof(t4), "vol_btc": m.btc_vol4h.asof(t4), "vol_moneda": vol_m,
            "mercado": cfg["mercado"], "lado": cfg["lado"], "cubeta": cfg["cubeta"],
            **sim,
        })
    return out


def generar_candidatos(m: Mercado, clave: str, params: dict[str, Any], inicio: str | pd.Timestamp,
                       fin: str | pd.Timestamp, procesos: int | None = None,
                       filas_azar: dict[str, list[int]] | None = None) -> pd.DataFrame:
    """Todas las señales de una estrategia en un periodo, cada una simulada como operación."""
    global _M
    _M = m
    inicio = pd.Timestamp(inicio, tz="UTC") if not isinstance(inicio, pd.Timestamp) else inicio
    fin = pd.Timestamp(fin, tz="UTC") if not isinstance(fin, pd.Timestamp) else fin
    simbolos = simbolos_estrategia(m, clave) if filas_azar is None else sorted(filas_azar)
    tareas = [(clave, s, params, inicio, fin, None if filas_azar is None else filas_azar[s]) for s in simbolos]
    procesos = procesos if procesos is not None else min(4, mp.cpu_count())
    if procesos > 1 and len(tareas) > 4:
        with mp.get_context("fork").Pool(procesos) as pool:
            partes = pool.map(_candidatos_simbolo, tareas, chunksize=max(1, len(tareas) // (procesos * 4)))
    else:
        partes = [_candidatos_simbolo(t) for t in tareas]
    filas = [x for p in partes for x in p]
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas).sort_values(["t_decision", "fuerza", "simbolo"], ascending=[True, False, True])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cartera: el motor de riesgo decide
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCartera:
    operaciones: pd.DataFrame          # operaciones ejecutadas con su ganancia/pérdida en USDT
    decisiones: pd.DataFrame           # cada candidato con su decisión y razón
    curva: pd.Series                   # capital después de cada cierre
    capital_inicial: float
    detenido_en: pd.Timestamp | None = None
    pausas: int = 0
    detenciones: list = field(default_factory=list)  # fechas en que se habría detenido todo (−15 %)


def _stop_vigente(op: dict[str, Any], t: pd.Timestamp) -> float:
    ts = op["stops_t"]
    if not ts:
        return op["stop"]
    k = int(np.searchsorted(np.asarray(ts, dtype=np.int64), t.value, side="right")) - 1
    return op["stop"] if k < 0 else op["stops"][k]


def cartera(m_reg: Reglamento, cands: pd.DataFrame, capital: float, filtros: dict[str, Filtros],
            estrategias_activas: list[str] | None = None, reanudar_tras_detencion: bool = True) -> ResultadoCartera:
    """Recorre los candidatos en orden y los pasa por el motor de riesgo (igual que en vivo).

    `reanudar_tras_detencion`: en vivo, la caída de −15 % detiene todo hasta que Ángelo dé el OK.
    En el backtest se anota la fecha y se simula ese OK (el pico se reinicia) para poder seguir midiendo.
    """
    detenciones: list[pd.Timestamp] = []
    reg = m_reg.copia_con({})
    for k in reg.estrategias:
        reg.datos["estrategias"][k]["estado"] = "PAPEL" if (estrategias_activas is None or k in estrategias_activas) else "APAGADA"
        reg.datos["estrategias"][k]["permitir_vivo"] = True
    estado = R.EstadoCartera(capital=capital, pico=capital, capital_inicio_dia=capital, capital_inicio_semana=capital)
    abiertas: list[dict[str, Any]] = []
    ejecutadas, decisiones = [], []
    curva_t, curva_v = [cands["t_decision"].iloc[0] if len(cands) else pd.Timestamp.now(tz="UTC")], [capital]
    dia_actual = semana_actual = None
    detenido_en = None
    pausas = 0
    if cands.empty:
        return ResultadoCartera(pd.DataFrame(), pd.DataFrame(), pd.Series(curva_v, index=curva_t), capital)

    def cerrar_hasta(t: pd.Timestamp) -> None:
        nonlocal abiertas
        pendientes = sorted([op for op in abiertas if op["t_salida"] <= t], key=lambda x: x["t_salida"])
        for op in pendientes:
            ganancia = op["cantidad"] * op["pnl_unidad"]
            estado.capital += ganancia
            op["ganancia_usdt"] = ganancia
            op["capital_despues"] = estado.capital
            ejecutadas.append(op)
            curva_t.append(op["t_salida"])
            curva_v.append(estado.capital)
            R.registrar_resultado(reg, estado, op["estrategia"], ganancia, op["t_salida"].to_pydatetime())
        abiertas = [op for op in abiertas if op["t_salida"] > t]

    for t, grupo in cands.groupby("t_decision", sort=True):
        cerrar_hasta(t)
        ahora = t.to_pydatetime()
        d0 = R.inicio_dia(reg, ahora)
        w0 = R.inicio_semana(reg, ahora)
        if d0 != dia_actual:
            dia_actual = d0
            estado.capital_inicio_dia = estado.capital
        if w0 != semana_actual:
            semana_actual = w0
            estado.capital_inicio_semana = estado.capital
        if R.aplicar_topes(reg, estado, ahora):
            pausas += 1
        if estado.detenido:
            if detenido_en is None:
                detenido_en = t
            if reanudar_tras_detencion:
                detenciones.append(t)
                estado.detenido = False
                estado.pico = estado.capital
        estado.posiciones = [
            R.Posicion(op["simbolo"], op["mercado"], op["lado"], op["estrategia"], op["cubeta"], op["precio_plan"],
                       _stop_vigente(op, t), op["cantidad"], op.get("apalancamiento", 1.0))
            for op in abiertas
        ]
        valor_spot = sum(p.valor for p in estado.posiciones if p.mercado == "SPOT")
        estado.efectivo_spot = max(0.0, estado.capital - valor_spot - estado.margen_futuros())
        for fila in grupo.itertuples(index=False):
            f = fila._asdict()
            apal = float(reg.estrategias[f["estrategia"]].get("apalancamiento", 1)) if f["mercado"] == "FUTUROS" else 1.0
            cand = R.Candidato(
                simbolo=f["simbolo"], mercado=f["mercado"], lado=f["lado"], estrategia=f["estrategia"],
                cubeta=f["cubeta"], precio_entrada=f["precio_plan"], stop=f["stop"], meta=f["meta"],
                comision_pct=f["comision_pct"], deslizamiento_pct=f["desliz_pct"], apalancamiento=apal,
            )
            filt = filtros.get(f["simbolo"]) or filtros_supuestos(f["simbolo"], f["precio_plan"], 5.0)
            vm = R.clasificar_volatilidad(reg, None if pd.isna(f["vol_moneda"]) else float(f["vol_moneda"]))
            vb = R.clasificar_volatilidad(reg, None if pd.isna(f["vol_btc"]) else float(f["vol_btc"]))
            dec = R.evaluar_candidato(reg, estado, cand, filt, ahora, regimen_btc=f["regimen_btc"] or "LATERAL",
                                      vol_moneda=vm, vol_btc=vb)
            decisiones.append({"t_decision": t, "estrategia": f["estrategia"], "simbolo": f["simbolo"],
                               "aprobada": dec.aprobada, "razon": dec.razon,
                               "saltada_por_capital": dec.saltada_por_capital,
                               "capital_necesario": dec.capital_necesario, "capital": estado.capital})
            if dec.aprobada:
                op = dict(f)
                op["cantidad"] = dec.cantidad
                op["riesgo_usdt"] = dec.riesgo_usdt
                op["apalancamiento"] = apal
                abiertas.append(op)
                estado.posiciones.append(R.Posicion(op["simbolo"], op["mercado"], op["lado"], op["estrategia"],
                                                    op["cubeta"], op["precio_plan"], op["stop"], dec.cantidad, apal))
                if op["mercado"] == "SPOT":
                    estado.efectivo_spot = max(0.0, (estado.efectivo_spot or 0.0) - dec.valor_usdt)
        R.consumir_ronda(estado)
    cerrar_hasta(pd.Timestamp.max.tz_localize("UTC"))
    ops = pd.DataFrame(ejecutadas)
    if not ops.empty:
        ops = ops.drop(columns=["stops_t", "stops"], errors="ignore").sort_values("t_salida").reset_index(drop=True)
    curva = pd.Series(curva_v, index=pd.DatetimeIndex(curva_t)).sort_index()
    return ResultadoCartera(ops, pd.DataFrame(decisiones), curva, capital, detenido_en, pausas, detenciones)
