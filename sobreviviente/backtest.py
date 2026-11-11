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
from . import descartes as DS
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
DURACION = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}
MIN_VELAS = {"1h": 300, "4h": 300, "1d": 210}


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
    spot1d: dict[str, pd.DataFrame] = field(default_factory=dict)
    reg1d: dict[str, pd.Series] = field(default_factory=dict)
    largo1d: dict[str, pd.DataFrame] = field(default_factory=dict)   # BTC y ETH desde 2017 (para la media de 200 días)
    lugar_rotacion: dict[int, pd.DataFrame] = field(default_factory=dict)
    redenominaciones: dict[str, list] = field(default_factory=dict)


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
    # Corregir cambios de denominación (no son ganancias ni pérdidas reales)
    from .calidad import ajustar_redenominaciones
    redenominaciones = {}
    for s in list(spot1h):
        spot1h[s], ev = ajustar_redenominaciones(spot1h[s])
        if ev:
            redenominaciones[s] = ev
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
        f1, ev = ajustar_redenominaciones(f1)
        if ev:
            redenominaciones["FUT:" + s] = ev
        fut4h[s] = D.resamplear(f1, "4h")
        fut_vol[s] = f1["quote_volume"].resample("1D").sum()
        arch = cliente.cache / "futuros" / "funding" / f"{s}.csv.gz"
        if arch.exists():
            x = pd.read_csv(arch, index_col=0, compression="gzip")
            x.index = pd.to_datetime(x.index, utc=True, format="ISO8601")
            funding[s] = x.iloc[:, 0]
    fv = pd.DataFrame(fut_vol)
    umbral_f = float(reg.get("universo.futuros_volumen_min_usdt"))
    fut_liquido = (fv.rolling(30, min_periods=30).median().shift(1) >= umbral_f) if not fv.empty else pd.DataFrame()

    btc4 = spot4h["BTCUSDT"]
    m = Mercado(
        redenominaciones=redenominaciones,
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

    # Velas diarias (ronda 2)
    m.spot1d = {s: D.resamplear(df, "1D") for s, df in spot1h.items()}
    m.reg1d = {s: RG.tendencia(df, reg) for s, df in m.spot1d.items() if len(df) > 0}
    for s in ("BTCUSDT", "ETHUSDT"):
        arch = cliente.cache / "spot" / "1d_largo" / f"{s}.csv.gz"
        if arch.exists():
            m.largo1d[s] = D.leer(arch)

    # Fuerza relativa de memes (hora por hora, solo entre memes que estaban en el universo)
    memes_presentes = [s for s in spot1h if s in m.memes]
    if memes_presentes:
        cierres = pd.DataFrame({s: spot1h[s]["close"] for s in memes_presentes})
        per_h = pertenece.reindex(columns=memes_presentes)
        per_h = per_h.reindex(cierres.index.floor("D")).set_axis(cierres.index)
        m.fuerza_memes = E4.fuerza_relativa(cierres, per_h)
    return m


def preparar_rotacion(m: Mercado, ventanas: list[int]) -> None:
    """Ranking diario de momentum entre las monedas más líquidas (para E7). Sin ver el futuro:
    la liquidez del día de la decisión se calcula con días anteriores."""
    from .estrategias import e7 as E7
    simb = [s for s in m.spot1d if s not in m.memes and len(m.spot1d[s])]
    cierres = pd.DataFrame({s: m.spot1d[s]["close"] for s in simb}).sort_index()
    vm = m.vol_mediano.reindex(columns=simb).where(m.pertenece.reindex(columns=simb).fillna(False).astype(bool))
    lugar_liq = vm.rank(axis=1, ascending=False, method="first")
    liquidas = (lugar_liq <= E7.LIQUIDAS)
    # La vela diaria con apertura D cierra en D+1: la decisión usa la liquidez del día D+1 (días anteriores).
    liquidas = liquidas.reindex(cierres.index + pd.Timedelta(days=1)).set_axis(cierres.index).fillna(False)
    for v in ventanas:
        if v not in m.lugar_rotacion:
            m.lugar_rotacion[v] = E7.ranking(cierres, liquidas, int(v))


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
    elif mod.TEMPORALIDAD == "1d":
        if clave == "E6" and simbolo in m.largo1d:
            velas = m.largo1d[simbolo]
        else:
            velas = m.spot1d.get(simbolo)
        if velas is None or len(velas) == 0:
            return None
        reg_m = RG.tendencia(velas, m.reg) if clave == "E6" else m.reg1d.get(simbolo)
        extra = {}
        if clave == "E7":
            for v, tabla in m.lugar_rotacion.items():
                if simbolo in tabla:
                    extra[f"lugar_{v}"] = tabla[simbolo].reindex(velas.index)
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
    elif mod.TEMPORALIDAD == "1d":
        reg_btc = RG.a_intervalo(m.btc_reg4h, velas.index, pd.Timedelta(hours=4), pd.Timedelta(days=1))
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
    if clave == "E6":
        return ["BTCUSDT", "ETHUSDT"]
    return sorted(s for s in m.spot1h if s not in m.memes)


# ---------------------------------------------------------------------------
# Simulación de una operación
# ---------------------------------------------------------------------------

def simular_operacion(arr: dict[str, np.ndarray], indice: pd.DatetimeIndex, i_senal: int, lado: str,
                      precio_plan: float, stop0: float, meta: float | None, gest: dict[str, Any],
                      comision_pct: float, desliz_pct: float, duracion: pd.Timedelta,
                      funding: pd.Series | None = None, en_r: float | None = 1.0,
                      limite_compra_pct: float | None = None, limite_stop_pct: float | None = None) -> dict[str, Any] | None:
    """Simula UNA operación desde la vela siguiente a la señal. Regresa None si no hay vela siguiente.

    Llenado realista (opcional, apagado por defecto): con `limite_compra_pct` la compra es LIMIT a
    precio_plan × (1 + límite): si la apertura queda más arriba, NO se llena (regresa None). Con `limite_stop_pct`
    el stop es STOP_LOSS_LIMIT: si el hueco pasa su límite, no se llena y queda pendiente (ver gestion.vela)."""
    e = i_senal + 1
    n = len(arr["o"])
    if e >= n:
        return None
    largo = lado == "LARGO"
    s = desliz_pct / 100.0
    entrada = arr["o"][e] * (1 + s if largo else 1 - s)
    if limite_compra_pct is not None and largo:
        tope_compra = precio_plan * (1 + limite_compra_pct / 100.0)
        if arr["o"][e] > tope_compra:
            return None
        entrada = min(entrada, tope_compra)
    costo_pct = 2 * (comision_pct + desliz_pct)
    params = {k: v for k, v in gest.items() if k != "modo"}
    if gest.get("sin_breakeven"):
        en_r = None
    est = EstadoGestion(lado=lado, entrada=entrada, entrada_plan=precio_plan, stop_inicial=stop0, stop=stop0,
                        meta=meta, modo=gest["modo"], params=params, costo_pct=costo_pct, en_r=en_r,
                        limite_stop_pct=limite_stop_pct)
    media = arr.get("media")
    salir = arr.get("salir")
    canal = arr.get("canal")
    if canal is not None and np.isfinite(canal[i_senal]):
        est.params["_canal_prev"] = float(canal[i_senal])
    tiempos_stop = []
    stops = []
    salida = None
    motivo = "sigue abierta"
    j = e
    o, h, l, c, a = arr["o"], arr["h"], arr["l"], arr["c"], arr["atr"]
    for j in range(e, n):
        ev = vela(est, o[j], h[j], l[j], c[j], a[j], None if media is None else media[j],
                  bool(salir[j]) if salir is not None else False,
                  None if canal is None else float(canal[j]))
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
    clave, simbolo, params, inicio, fin, filas_azar = args[:6]
    gest_override = args[6] if len(args) > 6 else None
    # Registro de descartes (apagado por defecto): lo que antes se descartaba en silencio regresa como registro
    # (diccionario con "codigo"). Los candidatos que sí salen son exactamente los mismos con o sin registro.
    registrar = bool(args[7]) if len(args) > 7 else False
    m = _M
    reg = m.reg
    mod = ESTRATEGIAS[clave]
    cfg = reg.estrategias[clave]
    ctx = contexto(m, clave, simbolo)
    if ctx is None or len(ctx.velas) < MIN_VELAS[mod.TEMPORALIDAD]:
        if registrar:
            return [DS.registro(DS.SIN_VELAS, "no hay velas suficientes para calcular la señal", simbolo, None, "",
                                clave, origen="generacion")]
        return []
    sen = mod.senales(ctx, params)
    gest = mod.gestion(params)
    if not cfg.get("mover_a_entrada", True):
        gest = {**gest, "sin_breakeven": True}
    if gest_override:
        # Auditoría A3 (prueba de salidas): misma entrada, otra regla de salida.
        gest = {**gest, **gest_override}
    if filas_azar is not None:
        idx_senales = np.asarray(filas_azar, dtype=int)
    else:
        mask = sen["entrada"].to_numpy() & (ctx.velas.index >= inicio) & (ctx.velas.index <= fin)
        idx_senales = np.flatnonzero(mask)
    if len(idx_senales) == 0:
        return []
    duracion = DURACION[mod.TEMPORALIDAD]
    arr = _arrays(ctx, gest)
    if gest["modo"] in ("senal_salida", "ranking"):
        arr["salir"] = sen["salir"].to_numpy(bool)
    if gest["modo"] == "canal":
        k = int(gest["canal_velas"])
        arr["canal"] = ctx.velas["low"].rolling(k).min().to_numpy(float)
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
        previo = None   # (código, texto) del descarte previo al motor de riesgo; solo se usa si se registra
        # Universo (solo con datos de días anteriores)
        try:
            en_universo = bool(m.pertenece.at[dia, simbolo])
        except KeyError:
            en_universo = False
        if not en_universo:
            if not registrar:
                continue
            previo = (DS.FUERA_DE_UNIVERSO, "la moneda no pertenecía al universo ese día")
        if cfg["mercado"] == "FUTUROS":
            try:
                liquido = bool(m.fut_liquido.at[dia, simbolo])
            except KeyError:
                liquido = False
            if not liquido:
                if not registrar:
                    continue
                previo = previo or (DS.FUTUROS_NO_LIQUIDO, "el perpetuo no tenía volumen suficiente ese día")
        stop0 = stops[i]
        if not np.isfinite(stop0) or not np.isfinite(arr["atr"][i]):
            if registrar:
                cod, txt = previo or (DS.STOP_O_SIMULACION, "el stop o el ATR no tienen valor ese día")
                out.append(DS.registro(cod, txt, simbolo, t_decision, "", clave, origen="generacion"))
            continue
        meta = metas[i] if np.isfinite(metas[i]) else None
        vm = m.vol_mediano.at[dia, simbolo] if dia in m.vol_mediano.index else np.nan
        liquidez = U.clasificar_liquidez(reg, float(vm) if np.isfinite(vm) else 0.0, es_meme)
        desliz = U.deslizamiento(reg, liquidez)
        sim = simular_operacion(arr, ctx.velas.index, i, cfg["lado"], precios[i], stop0, meta, gest,
                                comision, desliz, duracion, funding, en_r)
        if sim is None:
            if registrar:
                cod, txt = previo or (DS.STOP_O_SIMULACION, "la operación no se pudo simular (no hay vela siguiente)")
                out.append(DS.registro(cod, txt, simbolo, t_decision, "", clave, origen="generacion"))
            continue
        t4 = t_decision - pd.Timedelta(hours=4)
        vol_m = m.vol4h[simbolo].asof(t4) if simbolo in m.vol4h else np.nan
        fila = {
            "estrategia": clave, "simbolo": simbolo, "t_senal": t_senal, "t_decision": t_decision,
            "precio_plan": precios[i], "stop": stop0, "meta": meta, "fuerza": fuerzas[i],
            "comision_pct": comision, "desliz_pct": desliz, "liquidez": liquidez,
            "regimen_btc": m.btc_reg4h.asof(t4), "vol_btc": m.btc_vol4h.asof(t4), "vol_moneda": vol_m,
            "mercado": cfg["mercado"], "lado": cfg["lado"], "cubeta": cfg["cubeta"],
            **sim,
        }
        if previo is not None:
            # Descartada antes del motor de riesgo: queda en el registro con su operación SUELTA ya simulada
            # ("candidato"), para poder medir qué habría pasado. No entra a los candidatos.
            out.append(DS.registro(previo[0], previo[1], simbolo, t_decision, "", clave, origen="generacion",
                                   r=sim["r"], pnl_unidad=sim["pnl_unidad"], candidato=fila))
            continue
        out.append(fila)
    return out


def generar_candidatos(m: Mercado, clave: str, params: dict[str, Any], inicio: str | pd.Timestamp,
                       fin: str | pd.Timestamp, procesos: int | None = None,
                       filas_azar: dict[str, list[int]] | None = None,
                       gest_override: dict[str, Any] | None = None,
                       descartes: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    """Todas las señales de una estrategia en un periodo, cada una simulada como operación.

    `gest_override` (auditoría A3): cambia la regla de salida sin tocar la entrada.
    `descartes`: si se pasa una lista, ahí se anotan las señales que no llegan a ser candidato (sin velas, fuera
    del universo, Futuros sin liquidez, stop sin valor o simulación nula). Los candidatos son los mismos."""
    global _M
    _M = m
    inicio = pd.Timestamp(inicio, tz="UTC") if not isinstance(inicio, pd.Timestamp) else inicio
    fin = pd.Timestamp(fin, tz="UTC") if not isinstance(fin, pd.Timestamp) else fin
    simbolos = simbolos_estrategia(m, clave) if filas_azar is None else sorted(filas_azar)
    tareas = [(clave, s, params, inicio, fin, None if filas_azar is None else filas_azar[s], gest_override,
               descartes is not None) for s in simbolos]
    procesos = procesos if procesos is not None else min(4, mp.cpu_count())
    # "fork" no existe en Windows: ahí se calcula en un solo proceso (mismo resultado, más lento).
    if "fork" not in mp.get_all_start_methods():
        procesos = 1
    if procesos > 1 and len(tareas) > 4:
        with mp.get_context("fork").Pool(procesos) as pool:
            partes = pool.map(_candidatos_simbolo, tareas, chunksize=max(1, len(tareas) // (procesos * 4)))
    else:
        partes = [_candidatos_simbolo(t) for t in tareas]
    filas = [x for p in partes for x in p]
    if descartes is not None:   # los registros de descarte traen "codigo"; los candidatos no
        descartes.extend(x for x in filas if "codigo" in x)
        filas = [x for x in filas if "codigo" not in x]
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
            estrategias_activas: list[str] | None = None, reanudar_tras_detencion: bool = True,
            cierres: dict[str, pd.Series] | None = None, orden_azar: int | None = None,
            registro: list[dict[str, Any]] | None = None, nombre_cartera: str = "",
            apagar_en_banco: frozenset[str] = frozenset()) -> ResultadoCartera:
    """Recorre los candidatos en orden y los pasa por el motor de riesgo (igual que en vivo).

    `registro`: si se pasa una lista, ahí se anota cada decisión (aprobada o no) con su código de descarte
    (ver descartes.py) y `nombre_cartera`. Solo anota: el resultado de la corrida es idéntico con o sin él.

    `apagar_en_banco`: SOLO para el banco de pruebas de filtros (banco_filtros.py). Reglas del motor de riesgo que
    se apagan en esta corrida de experimento (ver `riesgo.evaluar_candidato`). Vacío por defecto = reglamento tal cual.

    `reanudar_tras_detencion`: en vivo, la caída de −15 % detiene todo hasta que Ángelo dé el OK.
    En el backtest se anota la fecha y se simula ese OK (el pico se reinicia) para poder seguir midiendo.

    `cierres` (auditoría A2): cierres diarios de cada moneda, con índice = hora de CIERRE de la vela.
    Si se dan, el capital que ven los topes y el tamaño es el valor a mercado (las abiertas que van
    perdiendo cuentan aunque no hayan cerrado), no solo lo ya cerrado.

    `orden_azar` (auditoría A8): si hay más señales que lugares, en vez de elegir por "fuerza" se elige
    al azar entre las señales del mismo momento (semilla dada).
    """
    if orden_azar is not None and not cands.empty:
        rng = np.random.default_rng(orden_azar)
        cands = cands.assign(_azar=rng.random(len(cands))).sort_values(["t_decision", "_azar"]) \
            .drop(columns="_azar").reset_index(drop=True)
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

    realizado = capital  # capital con lo ya cerrado

    def cerrar_hasta(t: pd.Timestamp) -> None:
        nonlocal abiertas, realizado
        pendientes = sorted([op for op in abiertas if op["t_salida"] <= t], key=lambda x: x["t_salida"])
        for op in pendientes:
            ganancia = op["cantidad"] * op["pnl_unidad"]
            realizado += ganancia
            estado.capital = realizado
            op["ganancia_usdt"] = ganancia
            op["capital_despues"] = realizado
            ejecutadas.append(op)
            curva_t.append(op["t_salida"])
            curva_v.append(realizado)
            R.registrar_resultado(reg, estado, op["estrategia"], ganancia, op["t_salida"].to_pydatetime())
        abiertas = [op for op in abiertas if op["t_salida"] > t]

    def a_mercado(t: pd.Timestamp) -> float:
        """Ganancia o pérdida NO realizada de lo abierto, con el último cierre diario conocido en t."""
        if cierres is None:
            return 0.0
        total = 0.0
        for op in abiertas:
            serie = cierres.get(op["simbolo"])
            if serie is None or op["t_entrada"] > t:
                continue
            px = serie.asof(t)
            if px is None or not np.isfinite(px):
                continue
            # Solo cuenta si ese cierre es posterior a la entrada.
            if serie.index[serie.index <= t][-1] <= op["t_entrada"]:
                continue
            signo = 1.0 if op["lado"] == "LARGO" else -1.0
            total += op["cantidad"] * (signo * (px - op["entrada"]) - op["entrada"] * op["comision_pct"] / 100.0)
        return total

    for t, grupo in cands.groupby("t_decision", sort=True):
        cerrar_hasta(t)
        estado.capital = realizado + a_mercado(t)
        ahora = t.to_pydatetime()
        d0 = R.inicio_dia_utc(ahora)   # el "día" del tope diario es el día UTC (igual que en la ronda de papel)
        w0 = R.inicio_semana(reg, ahora)
        if w0 != semana_actual:
            semana_actual = w0
            estado.capital_inicio_semana = estado.capital
        if R.aplicar_topes(reg, estado, ahora):   # se mide contra la referencia del día UTC anterior
            pausas += 1
        if d0 != dia_actual:
            # Día UTC nuevo: después de medir, el capital de ahora queda como referencia del día siguiente
            dia_actual = d0
            estado.capital_inicio_dia = estado.capital
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
                                      vol_moneda=vm, vol_btc=vb, apagar_en_banco=apagar_en_banco)
            decisiones.append({"t_decision": t, "estrategia": f["estrategia"], "simbolo": f["simbolo"],
                               "aprobada": dec.aprobada, "razon": dec.razon,
                               "saltada_por_capital": dec.saltada_por_capital,
                               "capital_necesario": dec.capital_necesario, "capital": estado.capital})
            if registro is not None:
                registro.append(DS.registro(dec.codigo, dec.razon, f["simbolo"], t, nombre_cartera, f["estrategia"],
                                            dec.aprobada, origen="riesgo", capital=estado.capital,
                                            capital_necesario=dec.capital_necesario))
            if dec.aprobada:
                op = dict(f)
                op["cantidad"] = dec.cantidad
                op["riesgo_usdt"] = dec.riesgo_usdt
                op["apalancamiento"] = apal
                op["capital_entrada"] = estado.capital
                op["valor_usdt"] = dec.valor_usdt
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


def curva_diaria(ops: pd.DataFrame, capital: float, cierres: dict[str, pd.Series],
                 inicio: pd.Timestamp | None = None, fin: pd.Timestamp | None = None) -> pd.Series:
    """Auditoría A2: capital de cada día a VALOR DE MERCADO (cierre 00:00 UTC).

    = capital inicial + ganancias ya cerradas + (precio de cierre − entrada) de lo que sigue abierto,
    descontando la comisión de entrada. Índice = hora de cierre del día. `cierres` como en `cartera`.
    """
    if ops is None or ops.empty:
        if inicio is None or fin is None:
            return pd.Series([capital], dtype=float)
        idx = pd.date_range(inicio.ceil("D"), fin.ceil("D"), freq="D")
        return pd.Series(capital, index=idx, dtype=float)
    a = inicio if inicio is not None else ops["t_entrada"].min()
    b = fin if fin is not None else ops["t_salida"].max()
    idx = pd.date_range(pd.Timestamp(a).ceil("D"), pd.Timestamp(b).ceil("D"), freq="D")
    valores = np.full(len(idx), float(capital))
    for op in ops.itertuples(index=False):
        # (se compara con fechas, no con números: según la versión de pandas la unidad interna cambia)
        k_cierre = int(idx.searchsorted(pd.Timestamp(op.t_salida), side="left"))  # primer día que cierra ≥ salida
        valores[k_cierre:] += op.ganancia_usdt
        k0 = int(idx.searchsorted(pd.Timestamp(op.t_entrada), side="right"))      # primer cierre diario después de entrar
        if k0 >= k_cierre:
            continue
        serie = cierres.get(op.simbolo)
        if serie is None:
            continue
        px = serie.reindex(idx[k0:k_cierre], method="ffill").to_numpy(float)
        signo = 1.0 if op.lado == "LARGO" else -1.0
        abierta = op.cantidad * (signo * (px - op.entrada) - op.entrada * op.comision_pct / 100.0)
        valores[k0:k_cierre] += np.nan_to_num(abierta)
    return pd.Series(valores, index=idx)
