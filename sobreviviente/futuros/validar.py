"""`validar-futuros` (arreglo 151): backtest walk-forward y compuertas ESTRICTAS de F1 v2 → VALIDACION_FUTUROS.md.

SOLO PAPEL y SOLO MIDE. Datos: velas de 4 h de Futuros, precio de marca de 1 h y funding de data.binance.vision desde
2021-01 (`datos.actualizar_futuros`, `datos.actualizar_precio_marca`), con caché. Cada señal se simula con
`backtest.simular_operacion` (la misma simulación de Futuros que E5, con la liquidación OFICIAL y su tarifa). No hay
rejilla: el entrenamiento de cada ventana (12 meses) solo verifica que haya operaciones mínimas, y la prueba (3 meses)
es la que cuenta. Si una sola compuerta falla, F1 NO PASA (y se queda con activo: false). Nada promete ganancias.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import backtest as B
from .. import datos as D
from .. import validacion as V
from ..estrategias import f1 as F1
from ..exchange import Filtros
from ..metricas import caida_maxima_pct, resumen_r
from ..reglamento import Reglamento
from . import cartera as C
from . import config as CF
from . import datos_publicos as DP
from . import liquidacion as LQ
from . import tamano as T
from . import variantes as VR

INICIO_DATOS = "2021-01-01"
DUR = pd.Timedelta(hours=4)
# Estrés de costos (MECÁNICO por delegación de Ángelo 2026-11-16): comisión 0.075 % por lado, deslizamiento al doble,
# funding al doble.
ESTRES = {"comision_pct": 0.075, "desliz_mult": 2.0, "funding_mult": 2.0}
EXPECTATIVA_ESTRES_MIN = 0.05
SIN_UNA_MONEDA_MIN = 0.05
CONCENTRACION_MAX_PCT = 50.0
NO_CABEN_MAX_PCT = 20.0
CAPITAL_GRANDE = 10000.0
# Reglas de Binance Futuros consultadas el 2026-11-16 (exchangeInfo): respaldo si exchangeInfo no contesta.
FILTROS_2026_11_16 = {
    "SOLUSDT": Filtros("SOLUSDT", 0.01, 0.01, 0.01, 5.0), "XRPUSDT": Filtros("XRPUSDT", 0.0001, 0.1, 0.1, 5.0),
    "BNBUSDT": Filtros("BNBUSDT", 0.01, 0.01, 0.01, 5.0), "DOGEUSDT": Filtros("DOGEUSDT", 0.00001, 1.0, 1.0, 5.0),
}


@dataclass
class MercadoF1:
    reg: Reglamento
    cfg: dict[str, Any]
    velas: dict[str, pd.DataFrame]                     # 4 h de Futuros
    funding: dict[str, pd.Series]
    marca4h: dict[str, pd.DataFrame]
    precio_funding: dict[str, pd.Series]               # cierre de la marca de 1 h, índice = hora de cierre
    btc1d: pd.DataFrame
    liquido: dict[str, pd.Series]                      # día → mediana de 30 días ≥ volumen mínimo
    filtros: dict[str, Filtros]
    tarifa_liq: dict[str, float]
    avisos: list[str] = field(default_factory=list)
    _memo: dict = field(default_factory=dict, repr=False)
    escalones: dict[str, list[dict[str, Any]]] = field(default_factory=dict)   # Arreglo 162: respaldo por moneda
    huecos: dict[str, dict[str, Any]] = field(default_factory=dict)     # Arreglo 203: conteos por moneda (solo informan)

    def senales(self, s: str, params: dict[str, Any], variante: str = "F1"):
        """(contexto, señales) de una moneda y variante, guardados para no recalcular en cada ventana."""
        kc = ("ctx", s)
        if kc not in self._memo:
            self._memo[kc] = F1.armar_contexto(s, self.velas[s], self.btc1d, self.funding.get(s), self.reg,
                                               float(self.cfg["stop_min_pct"]), float(self.cfg["stop_max_pct"]))
        ks = ("sen", s, tuple(sorted(params.items())), variante)
        if ks not in self._memo:
            self._memo[ks] = F1.senales(self._memo[kc], params, variante)
        return self._memo[kc], self._memo[ks]


def diarias_desde_4h(v: pd.DataFrame) -> pd.DataFrame:
    """Velas diarias (UTC) a partir de las de 4 h; solo días completos (6 velas)."""
    if v.empty:
        return v
    g = v.resample("1D", label="left", closed="left")
    out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "quote_volume": "sum"})
    return out[g["close"].count() >= 6].dropna(subset=["close"])


def liquidez_diaria(v: pd.DataFrame, minimo: float) -> pd.Series:
    """Día D → la mediana del volumen de los 30 días ANTERIORES es ≥ el mínimo (sin mirar el futuro)."""
    d = diarias_desde_4h(v)
    if d.empty:
        return pd.Series(dtype=bool)
    return (d["quote_volume"].rolling(30, min_periods=30).median().shift(1) >= minimo).fillna(False)


def cargar_mercado(reg: Reglamento, cliente: D.ClienteBinance, cfg: dict[str, Any],
                   inicio: str = INICIO_DATOS, fin: str | None = None,
                   respaldo: dict[str, dict[str, Any]] | None = None) -> MercadoF1:
    """Lee (y descarga con caché) los históricos de las monedas de `cfg["monedas"]` y de BTC. `respaldo` (Arreglo 162,
    holdout): pasos, tarifa y escalones de las monedas que no están en FILTROS_2026_11_16 ni en escalones.json."""
    respaldo = respaldo or {}
    fin = fin or str(reg.get("backtest.fin"))
    avisos: list[str] = []
    velas, funding, marca4h, pf, liquido, huecos = {}, {}, {}, {}, {}, {}
    for s in [cfg["regimen_btc"]] + list(cfg["monedas"]):
        v, f = D.actualizar_futuros(cliente, s, "4h", inicio, fin)
        v = v.astype({c: "float64" for c in ["open", "high", "low", "close", "volume", "quote_volume"] if c in v})
        velas[s], funding[s] = v, f
        if s == cfg["regimen_btc"]:
            continue
        m1 = D.actualizar_precio_marca(cliente, s, inicio, fin)
        if not m1.empty:
            m1 = m1.astype({c: "float64" for c in ["open", "high", "low", "close"]})
            marca4h[s] = D.resamplear(m1, "4h")
            pf[s] = pd.Series(m1["close"].to_numpy(float), index=m1.index + pd.Timedelta(hours=1))
        else:
            avisos.append(f"{s}: sin precio de marca; la liquidación se revisa con el último precio.")
        liquido[s] = liquidez_diaria(v, float(cfg["volumen_mediano_min_usdt"]))
        if v.empty:
            avisos.append(f"{s}: no hay velas de 4 h en data.binance.vision.")
        huecos[s] = _huecos_moneda(s, v, m1, f, cliente, inicio, fin)
        avisos.extend(_avisos_huecos(s, huecos[s]))
    avisos.extend(a for a in getattr(cliente, "avisos_checksum", []) or [] if a not in avisos)   # Arreglo 205
    filtros, tarifas = {}, {}
    try:
        info = {x["symbol"]: x for x in cliente.exchange_info("FUTUROS")["symbols"]}
    except Exception as e:  # noqa: BLE001 - Futuros puede estar bloqueado: se usan las reglas del 2026-11-16
        info = {}
        avisos.append(f"exchangeInfo de Futuros no disponible ({type(e).__name__}): se usan los pasos y mínimos "
                      f"consultados el 2026-11-16 y la tarifa de liquidación de esa fecha.")
    for s in cfg["monedas"]:
        r = respaldo.get(s)
        filtros[s] = T.filtros_moneda(info[s]) if s in info else (r["filtros"] if r else FILTROS_2026_11_16[s])
        tarifas[s] = LQ.tarifa_liquidacion(s, info.get(s)) if (s in info or not r) else float(r["tarifa_liq_pct"])
    btc = velas[cfg["regimen_btc"]]
    return MercadoF1(reg, cfg, {s: velas[s] for s in cfg["monedas"]}, {s: funding[s] for s in cfg["monedas"]},
                     marca4h, pf, diarias_desde_4h(btc), liquido, filtros, tarifas, avisos,
                     escalones={s: x["escalones"] for s, x in respaldo.items() if s in cfg["monedas"]}, huecos=huecos)


def _huecos_moneda(s: str, v: pd.DataFrame, m1: pd.DataFrame, f: pd.Series, cliente, inicio: str,
                   fin: str) -> dict[str, Any]:
    """Arreglo 203 (solo informa): velas de 4 h, velas de marca de 1 h y cobros de funding que faltan en medio, y los
    meses que data.binance.vision no tenía (404) en esta descarga. Con los datos de la caché no hay meses que anotar."""
    pedidos = D.meses_entre(inicio, fin)
    meses: dict[str, list[str]] = {}
    for sim, tipo, mes in getattr(cliente, "meses_sin_archivo", []) or []:
        if sim == s and mes not in meses.setdefault(tipo, []):
            meses[tipo].append(mes)
    en_medio = {}
    for tipo, faltan in meses.items():
        llegaron = [x for x in pedidos if x not in faltan]
        en_medio[tipo] = [x for x in faltan if llegaron and llegaron[0] < x < llegaron[-1]]
    return {"velas": DP.huecos_velas(v.index, DUR),
            "marca": DP.huecos_velas(m1.index if not m1.empty else None, pd.Timedelta(hours=1)),
            "funding": DP.huecos_funding(f), "meses": meses, "meses_en_medio": en_medio,
            "meses_usados": {tipo: list(ms) for (sim, tipo), ms in (getattr(cliente, "meses_usados", {}) or {}).items()
                             if sim == s}}


def _avisos_huecos(s: str, h: dict[str, Any]) -> list[str]:
    out = [f"⚠️ {s}: no llegaron los archivos mensuales de {tipo} de {', '.join(ms)} (data.binance.vision respondió "
           f"404; solo aviso)." for tipo, ms in h["meses_en_medio"].items() if ms]
    return out + DP.texto_huecos(s, h, marca_h=1)


# ---------------------------------------------------------------------------- candidatos
def _costos(reg: Reglamento, estres: bool) -> tuple[float, float, float]:
    com = float(reg.costos["comision_futuros_taker_pct"])
    des = float(reg.costos["deslizamiento_pct"]["grande"])
    if estres:
        return ESTRES["comision_pct"], des * ESTRES["desliz_mult"], ESTRES["funding_mult"]
    return com, des, 1.0


def candidatos(m: MercadoF1, params: dict[str, Any], inicio: pd.Timestamp, fin: pd.Timestamp,
               estres: bool = False, filas_azar: dict[str, list[tuple[int, str]]] | None = None,
               monedas: list[str] | None = None, variante: str = "F1") -> pd.DataFrame:
    """Cada señal de F1 (o cada entrada al azar de `filas_azar`) simulada como operación suelta, en R. `variante`
    (Arreglo 161): sus señales y, en F1-LT, su salida por tiempo (también para las entradas al azar)."""
    com, des, fmult = _costos(m.reg, estres)
    cfg = m.cfg
    tiempo = VR.variante(variante)["tiempo_max_velas"]
    filas = []
    for s in (monedas or cfg["monedas"]):
        v = m.velas.get(s)
        if v is None or len(v) < 300:
            continue
        ctx, sen = m.senales(s, params, variante)
        idx = v.index
        if filas_azar is not None:
            lista = filas_azar.get(s, [])
        else:
            ok = sen["entrada"].to_numpy() & (idx >= inicio) & (idx <= fin)
            lista = [(int(i), sen["lado"].iloc[i]) for i in np.flatnonzero(ok)]
        if not lista:
            continue
        gest = F1.gestion(params)
        base = {"o": v["open"].to_numpy(float), "h": v["high"].to_numpy(float), "l": v["low"].to_numpy(float),
                "c": v["close"].to_numpy(float), "atr": ctx.atr(14).to_numpy(float)}
        mk = m.marca4h.get(s)
        if mk is not None:
            mk = mk.reindex(idx)
            base["marca_h"], base["marca_l"] = mk["high"].to_numpy(float), mk["low"].to_numpy(float)
        else:
            # Arreglo 202: sin ninguna serie de marca, la liquidación se revisa con el último precio en TODAS las velas
            # (backtest.simular_operacion usa el máximo y el mínimo de la vela donde la marca es NaN).
            base["marca_h"] = base["marca_l"] = np.full(len(idx), np.nan)
        fund = m.funding.get(s)
        fund = None if fund is None else fund * fmult
        liq_dia = m.liquido.get(s, pd.Series(dtype=bool))
        k = float(params["stop_atr"])
        fund8 = ctx.extra.get("funding_8h")
        fund8 = fund8.to_numpy(float) if fund8 is not None else np.zeros(len(idx))
        for i, lado in lista:
            dia = (idx[i] + DUR).floor("D")
            if not bool(liq_dia.get(dia, False)):
                continue
            precio = float(base["c"][i])
            atr = float(base["atr"][i])
            stop = precio + k * atr if lado == "CORTO" else precio - k * atr
            if not B.stop_valido(lado, precio, stop, atr):
                continue
            if i + 1 >= len(idx):          # sin vela siguiente no hay entrada (simular_operacion regresaría None)
                continue
            arr = dict(base)
            arr["salir"] = sen["salir_largo" if lado == "LARGO" else "salir_corto"].to_numpy(bool)
            # Arreglo 155: tamaño y liquidación con la ENTRADA REAL (apertura siguiente ± deslizamiento), no con el cierre.
            entrada = B.precio_entrada(float(base["o"][i + 1]), lado, des)
            esc = m.escalones.get(s) or LQ.cargar_escalones(s)
            f8 = float(fund8[i]) if np.isfinite(fund8[i]) else 0.0
            # Arreglo 158: el tamaño (y con él el apalancamiento) cuenta comisiones, deslizamiento y funding en contra.
            t = T.calcular(float(cfg["capital_papel"]), float(cfg["riesgo_por_operacion_pct"]), entrada, stop, lado,
                           m.filtros[s], cfg, escalones=esc, costos=T.costos_reglamento(m.reg, f8))
            apal = float(t.apalancamiento or 1)
            q = t.cantidad if t.cantidad > 0 else 1.0
            liq = LQ.precio_liquidacion_aislado(entrada, q, lado, apal, esc)
            sim = B.simular_operacion(arr, idx, i, lado, precio, stop, None, gest, com, des, DUR, fund, None,
                                      precio_funding=m.precio_funding.get(s),
                                      apalancamiento=apal if "marca_h" in arr else None,
                                      precio_liq=liq if "marca_h" in arr else None, tarifa_liq_pct=m.tarifa_liq[s],
                                      tiempo_max_velas=tiempo)
            if sim is None:
                continue
            filas.append({"simbolo": s, "lado": lado, "t_senal": idx[i], "t_decision": idx[i] + DUR,
                          "precio_plan": precio, "stop": stop, "stop_pct": abs(precio - stop) / precio * 100,
                          "fuerza": float(sen["fuerza"].iloc[i]), "cabe_42": t.cabe, "razon_42": t.razon,
                          "apalancamiento": apal, "liquidacion": liq, "comision_pct": com, "desliz_pct": des,
                          "funding_8h_pct": f8,
                          **{k2: v2 for k2, v2 in sim.items() if k2 not in ("stops_t", "stops")}})
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas).sort_values(["t_decision", "fuerza", "simbolo"], ascending=[True, False, True])
    return df.reset_index(drop=True)


def seleccionar(cands: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Lo que F1 podría tener abierto a la vez: 1 por moneda y hasta `posiciones_max` (con 1 % de riesgo y calor de 2 %
    son las mismas 2). En orden de tiempo y, en el mismo momento, por fuerza."""
    if cands.empty:
        return cands
    abiertas: list[tuple[pd.Timestamp, str]] = []
    keep = []
    for k, f in cands.iterrows():
        t = f["t_decision"]
        abiertas = [(ts, s) for ts, s in abiertas if ts > t]
        if len(abiertas) >= int(cfg["posiciones_max"]) or any(s == f["simbolo"] for _, s in abiertas):
            continue
        keep.append(k)
        abiertas.append((f["t_salida"], f["simbolo"]))
    return cands.loc[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------- cartera con 42.54
def _entrada(f) -> float:
    """Entrada real de un candidato (la que simuló backtest); candidatos sin esa columna usan el precio del plan."""
    e = f.get("entrada") if hasattr(f, "get") else None
    return float(e) if e is not None and np.isfinite(e) else float(f["precio_plan"])


def simular_cartera(cands: pd.DataFrame, m: MercadoF1, capital: float | None = None) -> dict[str, Any]:
    """La Cartera F con su capital de papel: frenos, rachas, posiciones, calor, mínimos y pasos reales de Binance.

    Como en backtest.cartera, si se toca el freno de 15 % se anota y se simula el OK de Ángelo para seguir midiendo."""
    cfg = m.cfg
    cap0 = float(capital if capital is not None else cfg["capital_papel"])
    est = C.estado_nuevo({**cfg, "capital_papel": cap0})
    rf = C.reglamento_f1(m.reg, cfg)
    abiertas: list[dict[str, Any]] = []
    ops, no_caben, evaluadas, detenciones, liquidaciones = [], [], 0, [], 0
    curva = [(cands["t_decision"].iloc[0] if len(cands) else pd.Timestamp.now(tz="UTC"), cap0)]

    def cerrar_hasta(t):
        nonlocal abiertas, liquidaciones
        for op in sorted([o for o in abiertas if o["t_salida"] <= t], key=lambda o: o["t_salida"]):
            g = op["cantidad"] * op["pnl_unidad"]
            est["capital"] += g
            liquidaciones += int(bool(op.get("liquidada")))
            C.registrar_racha(est, g, op["t_salida"].to_pydatetime(), cfg)
            ops.append({**op, "ganancia_usdt": g, "capital_despues": est["capital"]})
            curva.append((op["t_salida"], est["capital"]))
        abiertas = [o for o in abiertas if o["t_salida"] > t]

    for _, f in cands.iterrows():
        t = f["t_decision"]
        cerrar_hasta(t)
        ahora = t.to_pydatetime()
        est["posiciones"] = [{"simbolo": o["simbolo"], "lado": o["lado"], "entrada": _entrada(o),
                              "stop": o["stop"], "cantidad": o["cantidad"], "margen": o["margen"]} for o in abiertas]
        C.aplicar_frenos(rf, est, ahora)
        if est["detenido"]:
            detenciones.append(t)
            est["detenido"], est["pico"] = False, est["capital"]
            continue
        if C.bloqueos_entrada(rf, est, f["simbolo"], ahora):
            continue
        evaluadas += 1
        # Arreglo 155: el tamaño va con la entrada real; así cantidad × |entrada − stop| nunca pasa del riesgo pedido, y
        # si con ella ya no cabe, la operación no se cuenta.
        # Arreglo 158: los candidatos de `candidatos` traen `funding_8h_pct` y se dimensionan CON costos. Un renglón de
        # formato viejo (sin esa columna, como los que no traen `entrada`) se dimensiona como antes, sin costos.
        f8 = f.get("funding_8h_pct")
        costos = None if f8 is None else T.costos_reglamento(m.reg, float(f8) if np.isfinite(f8) else 0.0)
        tam = C.cabe(cfg, est, f["simbolo"], f["lado"], _entrada(f), f["stop"], m.filtros[f["simbolo"]], costos)
        if not tam.cabe:
            if "posiciones" not in tam.razon and "1 por moneda" not in tam.razon and "calor" not in tam.razon:
                no_caben.append(tam.razon)
            continue
        abiertas.append({**f.to_dict(), "cantidad": tam.cantidad, "margen": tam.margen,
                         "apalancamiento_real": tam.apalancamiento})
    cerrar_hasta(pd.Timestamp.max.tz_localize("UTC"))
    serie = pd.Series([v for _, v in curva], index=pd.DatetimeIndex([t for t, _ in curva])).sort_index()
    return {"capital_inicial": cap0, "capital_final": float(est["capital"]), "operaciones": len(ops),
            "caida_max_pct": caida_maxima_pct(serie.values), "detenciones": [str(x) for x in detenciones],
            "no_caben": len(no_caben), "evaluadas": evaluadas,
            "no_caben_pct": (len(no_caben) / evaluadas * 100.0) if evaluadas else 0.0,
            "razones_no_caben": no_caben[:5], "liquidaciones": liquidaciones, "_ops": pd.DataFrame(ops)}


# ---------------------------------------------------------------------------- walk-forward y compuertas
@dataclass
class ResultadoF1:
    ventanas: list[dict[str, Any]] = field(default_factory=list)
    oos: pd.DataFrame = field(default_factory=pd.DataFrame)
    resumen: dict[str, Any] = field(default_factory=dict)
    mc: dict[str, Any] = field(default_factory=dict)
    mc_bloques: dict[str, Any] = field(default_factory=dict)
    azar: dict[str, Any] = field(default_factory=dict)
    robustez: dict[str, Any] = field(default_factory=dict)
    estres: dict[str, Any] = field(default_factory=dict)
    por_lado: dict[str, dict[str, Any]] = field(default_factory=dict)
    por_moneda: dict[str, dict[str, Any]] = field(default_factory=dict)
    sin_moneda: dict[str, float] = field(default_factory=dict)
    capital: dict[str, Any] = field(default_factory=dict)
    compuertas: dict[str, tuple[bool, str]] = field(default_factory=dict)
    pasa: bool = False
    avisos: list[str] = field(default_factory=list)
    variante: str | None = None                 # Arreglo 161: None = la evaluación del 151 (13 compuertas)
    pasa_sin_escalones: bool = False
    veredicto: str = "NO PASA"


def _oos(m: MercadoF1, params: dict[str, Any], ventanas, estres: bool = False,
         monedas: list[str] | None = None, variante: str = "F1") -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Operaciones fuera de muestra de todas las ventanas. La selección (1 por moneda, 2 a la vez) se hace sobre TODO el
    tramo de prueba junto, para que una posición que sigue abierta al cambiar de ventana también cuente."""
    partes, info = [], []
    minimo = int(m.reg.get("validacion.wf_min_operaciones_entrenamiento", 20))
    for k, (a, b, p0, p1) in enumerate(ventanas):
        ent = seleccionar(candidatos(m, params, a, b - pd.Timedelta(seconds=1), estres, monedas=monedas,
                                     variante=variante), m.cfg)
        pru = candidatos(m, params, p0, p1 - pd.Timedelta(seconds=1), estres, monedas=monedas, variante=variante)
        info.append({"prueba": f"{p0:%Y-%m}→{p1:%Y-%m}", "ops_entrenamiento": len(ent),
                     "entrenamiento_ok": len(ent) >= minimo})
        if len(pru):
            partes.append(pru.assign(ventana=k))
    todo = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if len(todo):
        todo = seleccionar(todo.sort_values(["t_decision", "fuerza", "simbolo"], ascending=[True, False, True])
                           .reset_index(drop=True), m.cfg)
    for k, w in enumerate(info):
        r = todo.loc[todo["ventana"] == k, "r"].to_numpy(float) if len(todo) else np.array([])
        w.update({"ops": len(r), "r_total": float(r.sum()), "expectativa": float(r.mean()) if len(r) else 0.0})
    return todo, info


def _expectativa(df: pd.DataFrame) -> float:
    return float(df["r"].mean()) if len(df) else float("nan")


def azar(m: MercadoF1, params: dict[str, Any], inicio: pd.Timestamp, fin: pd.Timestamp, n_ops: int,
         expectativa: float, n: int, semilla: int, pool: int = 3000, variante: str = "F1") -> dict[str, Any]:
    """Entradas al azar (vela, moneda y lado al azar, con el mismo stop y las mismas salidas); se toman `n` grupos de
    `n_ops` y se mide en qué percentil queda la expectativa de F1. Arreglo 161: en una variante solo de largos (F1-L,
    F1-LT) las entradas al azar también son solo largos (comparar contra cortos al azar no sería justo)."""
    rng = np.random.default_rng(semilla)
    elegibles = []
    for s in m.cfg["monedas"]:
        v = m.velas.get(s)
        if v is None or len(v) < 300:
            continue
        idx = v.index
        filas = np.flatnonzero((idx >= inicio) & (idx <= fin))[:-1]
        elegibles.extend((s, int(i)) for i in filas)
    if not elegibles or n_ops == 0:
        return {"percentil_estrategia": 0.0, "pool": 0}
    elegidos = rng.choice(len(elegibles), size=min(pool, len(elegibles)), replace=False)
    solo_largo = VR.variante(variante)["lados"] == "largo"
    lados = rng.choice(["LARGO"] if solo_largo else ["LARGO", "CORTO"], size=len(elegidos))
    por: dict[str, list[tuple[int, str]]] = {}
    for k, lado in zip(sorted(elegidos), lados):
        s, i = elegibles[k]
        por.setdefault(s, []).append((i, str(lado)))
    c = candidatos(m, params, inicio, fin, filas_azar=por, variante=variante)
    if c.empty:
        return {"percentil_estrategia": 0.0, "pool": 0}
    r = c["r"].to_numpy(float)
    medias = np.array([rng.choice(r, size=n_ops, replace=True).mean() for _ in range(n)])
    return {"percentil_estrategia": float((medias < expectativa).mean() * 100.0), "pool": len(r),
            "azar_p50": float(np.median(medias)), "azar_p95": float(np.percentile(medias, 95))}


def robustez(m: MercadoF1, base: dict[str, Any], inicio: pd.Timestamp, fin: pd.Timestamp,
             variacion: float, variante: str = "F1") -> dict[str, Any]:
    """donchian_n y stop_atr ±10/20 % (los dos primeros parámetros), con la misma selección de 1 por moneda."""
    pasos = [-variacion, -variacion / 2, 0.0, variacion / 2, variacion]
    tabla = {}
    for d1 in pasos:
        for d2 in pasos:
            p = dict(base)
            p["donchian_n"] = int(round(base["donchian_n"] * (1 + d1 / 100)))
            p["stop_atr"] = round(base["stop_atr"] * (1 + d2 / 100), 4)
            ops = seleccionar(candidatos(m, p, inicio, fin, variante=variante), m.cfg)
            tabla[(d1, d2)] = (_expectativa(ops), len(ops))
    vals = [x[0] for x in tabla.values()]
    return {"pasos": pasos, "tabla": tabla, "todas_positivas": bool(all(np.isfinite(x) and x > 0 for x in vals)),
            "minimo": float(np.nanmin(vals)) if vals else float("nan")}


def estadistico_t(r) -> float:
    """t de la expectativa: media ÷ (desviación muestral ÷ √n). Con menos de 2 operaciones o sin dispersión: nan."""
    r = np.asarray(r, dtype=float)
    if len(r) < 2:
        return float("nan")
    de = float(r.std(ddof=1))
    return float(r.mean() / (de / np.sqrt(len(r)))) if de > 0 else float("nan")


def evaluar(m: MercadoF1, params: dict[str, Any] | None = None, azar_n: int | None = None,
            mc_n: int | None = None, robustez_on: bool = True, variante: str | None = None) -> ResultadoF1:
    """Walk-forward y compuertas. `variante` None = la evaluación del 151 tal cual (13 compuertas, azar con 9 ideas);
    con una variante (Arreglo 161) = sus señales y salidas y las 15 compuertas de `compuertas_variante`."""
    reg = m.reg
    params = dict(params or F1.POR_DEFECTO)
    var = "F1" if variante is None else variante
    VR.variante(var)                                  # una variante desconocida es error antes de medir nada
    semilla = int(reg.get("validacion.semilla"))
    res = ResultadoF1(avisos=list(m.avisos), variante=variante)
    ventanas = V.ventanas_wf(reg, sin_holdout=True)
    oos, res.ventanas = _oos(m, params, ventanas, variante=var)
    res.oos = oos
    r = oos["r"].to_numpy(float) if len(oos) else np.array([])
    res.resumen = resumen_r(r)
    pos = sum(1 for w in res.ventanas if w["r_total"] > 0)
    res.resumen["ventanas_positivas_pct"] = pos / len(res.ventanas) * 100.0 if res.ventanas else 0.0
    res.resumen["liquidaciones"] = int(oos["liquidada"].fillna(False).astype(bool).sum()) if "liquidada" in oos else 0
    res.resumen["velas_liq_ultimo_precio"] = velas_sin_marca(oos)
    res.resumen["t"] = estadistico_t(r)
    riesgo = float(m.cfg["riesgo_por_operacion_pct"])
    caida_alerta = float(m.cfg["caida_max_desde_pico_pct"])
    n_mc = int(mc_n or reg.get("validacion.montecarlo_n"))
    if len(r):
        res.mc = V.montecarlo(r, riesgo, n_mc, semilla, caida_alerta)
        res.mc_bloques = V.montecarlo_bloques(oos, riesgo, n_mc, semilla,
                                              caida_alerta, int(reg.get("validacion.lentos.bloque_dias", 20)))
    p_ini, p_fin = (ventanas[0][2], ventanas[-1][3]) if ventanas else (None, None)
    if p_ini is not None:
        res.azar = azar(m, params, p_ini, p_fin, len(r), float(r.mean()) if len(r) else 0.0,
                        int(azar_n or reg.get("validacion.azar_n")), semilla, variante=var)
        if robustez_on:
            res.robustez = robustez(m, params, p_ini, p_fin, float(reg.get("validacion.robustez_variacion_pct")),
                                    variante=var)
    estres, _ = _oos(m, params, ventanas, estres=True, variante=var)
    res.estres = resumen_r(estres["r"].to_numpy(float) if len(estres) else [])
    for lado in ("LARGO", "CORTO"):
        res.por_lado[lado] = resumen_r(oos.loc[oos["lado"] == lado, "r"].to_numpy(float) if len(oos) else [])
    total_r = float(r.sum()) if len(r) else 0.0
    for s in m.cfg["monedas"]:
        rs = oos.loc[oos["simbolo"] == s, "r"].to_numpy(float) if len(oos) else np.array([])
        res.por_moneda[s] = {**resumen_r(rs), "r_total": float(rs.sum()),
                             "parte_pct": float(rs.sum() / total_r * 100.0) if total_r > 0 else float("nan")}
        sin, _ = _oos(m, params, ventanas, monedas=[x for x in m.cfg["monedas"] if x != s], variante=var)
        res.sin_moneda[s] = _expectativa(sin)
    res.capital = simular_cartera(oos, m)
    caida_max = float(reg.get("validacion.compuertas.caida_p95_max_pct"))
    if variante is None:
        res.compuertas = compuertas(res, m.cfg, caida_max, azar_min_pct(reg))
        res.pasa = bool(res.compuertas) and all(ok for ok, _ in res.compuertas.values())
        res.pasa_sin_escalones = res.pasa
        res.veredicto = "PASA" if res.pasa else "NO PASA"
        return res
    res.compuertas = compuertas_variante(res, m.cfg, caida_max, reg, variante)
    res.pasa = all(ok for ok, _ in res.compuertas.values())
    res.pasa_sin_escalones = all(ok for k, (ok, _) in res.compuertas.items() if k != "escalones")
    res.veredicto = veredicto(res.pasa, res.pasa_sin_escalones)
    return res


VEREDICTO_SIN_ESCALONES = "PASA SIN ESCALONES VERIFICADOS → no se puede activar"


def veredicto(pasa: bool, pasa_sin_escalones: bool) -> str:
    """PASA (las 15) / PASA SIN ESCALONES VERIFICADOS → no se puede activar / NO PASA. Ninguno activa nada."""
    if pasa:
        return "PASA"
    return VEREDICTO_SIN_ESCALONES if pasa_sin_escalones else "NO PASA"


def compuertas_variante(res: ResultadoF1, cfg: dict[str, Any], caida_max: float, reg: Reglamento,
                        variante: str) -> dict[str, tuple[bool, str]]:
    """Arreglo 161: las 13 compuertas del 151 con azar ≥ 99.17 % (12 ideas), «largo» en vez de «largo y corto» en las
    variantes solo de largos (el corto se sigue reportando si lo hay), más «significancia» (t ≥ 2.2414) y «escalones»
    (todas las monedas con su tabla verificada). Si falla una, no PASA."""
    base = compuertas(res, cfg, caida_max, VR.azar_min(reg))
    c: dict[str, tuple[bool, str]] = {}
    for k, v in base.items():
        if k == "largo_y_corto" and VR.variante(variante)["lados"] == "largo":
            x, y = res.por_lado.get("LARGO", {}), res.por_lado.get("CORTO", {})
            el, nl = float(x.get("expectativa_r", 0.0)), int(x.get("operaciones", 0))
            ec, nc = float(y.get("expectativa_r", 0.0)), int(y.get("operaciones", 0))
            corto = f"; corto reportado: {ec:+.3f}R ({nc} ops)" if nc else "; sin cortos"
            c["largo"] = (nl > 0 and el > 0, f"largo {el:+.3f}R ({nl} ops), debe ser > 0R{corto}")
        else:
            c[k] = v
    t, tmin = float(res.resumen.get("t", float("nan"))), VR.t_min()
    c["significancia"] = (bool(np.isfinite(t) and t >= tmin - 1e-12),
                          f"t de la expectativa {t:.2f} (mínimo {tmin:.2f}; Bonferroni α = 0.05/{VR.PRUEBAS_FAMILIA})")
    falta = LQ.sin_verificar(cfg["monedas"])
    c["escalones"] = (not falta, "todas las monedas con escalones verificados" if not falta else
                      f"escalones sin verificar: {', '.join(falta)} (TAREA DE ÁNGELO: copiarlos de Leverage & Margin)")
    return c


def azar_min_pct(reg: Reglamento, ideas: int = 9) -> float:
    """Regla de la ronda 2 con 9 ideas probadas (8 del reglamento + F1): 100 − 10/9 = 98.9 %."""
    return 100.0 - float(reg.get("validacion.ronda2.azar_base_pct", 10)) / ideas


def compuertas(res: ResultadoF1, cfg: dict[str, Any], caida_max: float, azar_min: float) -> dict[str, tuple[bool, str]]:
    """Compuertas ESTRICTAS de F1. Si falla una, NO PASA."""
    o = res.resumen
    c: dict[str, tuple[bool, str]] = {}
    n = int(o.get("operaciones", 0))
    c["operaciones"] = (n >= 100, f"{n} operaciones fuera de muestra, sumando las 4 monedas (mínimo 100)")
    fg = float(o.get("factor_ganancia", 0.0))
    c["factor_ganancia"] = (fg >= 1.3, f"factor de ganancia {fg:.2f} (mínimo 1.3)")
    e = float(o.get("expectativa_r", 0.0))
    c["expectativa"] = (n > 0 and e >= 0.10, f"expectativa {e:+.3f}R después de costos (mínimo +0.10R)")
    vp = float(o.get("ventanas_positivas_pct", 0.0))
    c["ventanas"] = (vp >= 60.0, f"{vp:.0f} % de ventanas positivas (mínimo 60 %)")
    cp = max(res.mc.get("caida_p95", float("inf")), res.mc_bloques.get("caida_p95", float("inf")))
    c["caida_p95"] = (cp <= caida_max, f"caída p95 {cp:.1f} % con {cfg['riesgo_por_operacion_pct']:g} % de riesgo, "
                                       f"la peor entre Monte Carlo suelto y por bloques (máximo {caida_max:g} %)")
    pz = float(res.azar.get("percentil_estrategia", 0.0))
    c["azar"] = (pz >= azar_min - 1e-9, f"le gana al {pz:.1f} % de las entradas al azar (mínimo {azar_min:.1f} %)")
    rb = res.robustez
    c["robustez"] = (bool(rb.get("todas_positivas")),
                     f"robustez ±20 %: peor expectativa {rb.get('minimo', float('nan')):+.3f}R (todas deben ser > 0)")
    liq = int(o.get("liquidaciones", 0))
    c["liquidaciones"] = (liq == 0, f"{liq} liquidaciones (deben ser CERO)")
    ee = float(res.estres.get("expectativa_r", 0.0))
    c["estres"] = (int(res.estres.get("operaciones", 0)) > 0 and ee >= EXPECTATIVA_ESTRES_MIN,
                   f"con estrés de costos (comisión 0.075 %, deslizamiento ×2, funding ×2): {ee:+.3f}R (mínimo +0.05R)")
    el, ec = (float(res.por_lado.get(x, {}).get("expectativa_r", 0.0)) for x in ("LARGO", "CORTO"))
    nl, nc = (int(res.por_lado.get(x, {}).get("operaciones", 0)) for x in ("LARGO", "CORTO"))
    c["largo_y_corto"] = (nl > 0 and nc > 0 and el > 0 and ec > 0,
                          f"largo solo {el:+.3f}R ({nl} ops) y corto solo {ec:+.3f}R ({nc} ops); los dos > 0R")
    partes = {s: x.get("parte_pct", float("nan")) for s, x in res.por_moneda.items()}
    peor = max(partes.values(), default=float("nan"))
    c["concentracion"] = (bool(partes) and all(np.isfinite(x) and x <= CONCENTRACION_MAX_PCT for x in partes.values()),
                          f"la moneda que más aporta da {peor:.0f} % de la R total (máximo 50 %; sin R total positiva "
                          f"no se puede repartir)")
    sm = res.sin_moneda
    peor_sin = min(sm.values(), default=float("nan"))
    c["sin_una_moneda"] = (bool(sm) and all(np.isfinite(x) and x >= SIN_UNA_MONEDA_MIN for x in sm.values()),
                           f"quitando cualquier moneda, la peor expectativa es {peor_sin:+.3f}R (mínimo +0.05R)")
    nc_pct = float(res.capital.get("no_caben_pct", 100.0))
    c["no_caben"] = (nc_pct <= NO_CABEN_MAX_PCT,
                     f"con {cfg['capital_papel']} USDT, {res.capital.get('no_caben', 0)} de "
                     f"{res.capital.get('evaluadas', 0)} señales «no caben» ({nc_pct:.1f} %; máximo 20 %)")
    return c


# ---------------------------------------------------------------------------- informe
def velas_sin_marca(oos: pd.DataFrame) -> int:
    """Arreglo 202: velas en que la liquidación se revisó con el último precio porque faltaba la marca."""
    if oos is None or "velas_liq_ultimo_precio" not in oos:
        return 0
    return int(oos["velas_liq_ultimo_precio"].fillna(0).sum())


def _renglon_sin_marca(res: ResultadoF1) -> str:
    return f"- Velas revisadas con el último precio (faltaba la marca): {res.resumen.get('velas_liq_ultimo_precio', 0)}."


def _seccion_huecos(m: MercadoF1) -> list[str]:
    """Arreglo 203: «Huecos de datos» con los conteos por moneda (solo informa; no cambia ninguna compuerta)."""
    L = ["", "## Huecos de datos", ""]
    if not m.huecos:
        return L + ["- Sin conteos (el mercado no se bajó de Binance)."]
    L += ["Piezas que faltan en medio (de la primera a la última recibida). Solo informa: no cambia entradas, salidas ni "
          "compuertas.", "", "| Moneda | Velas 4 h | Marca 1 h | Funding | Meses sin archivo |", "|---|---|---|---|---|"]
    for s, h in m.huecos.items():
        v, mk, f = h.get("velas", {}), h.get("marca", {}), h.get("funding", {})
        meses = []
        for tipo, ms in (h.get("meses") or {}).items():
            medio = set((h.get("meses_en_medio") or {}).get(tipo, []))
            meses += [f"{tipo} {x}" + ("" if x in medio else " (antes o después de los archivos que sí hay)") for x in ms]
        L.append(f"| {s} | faltan {v.get('faltan', 0)} de {v.get('esperadas', 0)} | faltan {mk.get('faltan', 0)} de "
                 f"{mk.get('esperadas', 0)} | faltan {f.get('faltan', 0)} de {f.get('esperados', 0)} | "
                 f"{', '.join(meses) or '—'} |")
    return L


def _meses_texto(ms: list[str]) -> str:
    """«2024-01 a 2024-04 (3 meses; falta 2024-02)»: los meses de data.binance.vision que se usaron (Arreglo 205)."""
    if not ms:
        return "—"
    todos = [str(p) for p in pd.period_range(ms[0], ms[-1], freq="M")]
    faltan = [x for x in todos if x not in set(ms)]
    extra = f"; falta {', '.join(faltan)}" if len(faltan) == 1 else (f"; faltan {', '.join(faltan)}" if faltan else "")
    return f"{ms[0]} a {ms[-1]} ({len(ms)} {'mes' if len(ms) == 1 else 'meses'}{extra})"


def _seccion_meses(m: MercadoF1) -> list[str]:
    """Arreglo 205: «Meses de datos usados» por moneda (solo informa; no cambia ninguna compuerta)."""
    L = ["", "## Meses de datos usados", ""]
    filas = {s: h.get("meses_usados") for s, h in (m.huecos or {}).items() if h.get("meses_usados")}
    if not filas:
        return L + ["- Sin registro (el mercado no se bajó de data.binance.vision)."]
    L += ["Meses de data.binance.vision en la caché, cada zip verificado con su .CHECKSUM. Solo informa.", "",
          "| Moneda | Velas 4 h | Marca 1 h | Funding |", "|---|---|---|---|"]
    for s, mu in filas.items():
        L.append(f"| {s} | {_meses_texto(mu.get('velas 4h', []))} | {_meses_texto(mu.get('marca 1h', []))} | "
                 f"{_meses_texto(mu.get('funding', []))} |")
    return L


def _f(x: Any, fmt: str = "{:+.3f}") -> str:
    try:
        return fmt.format(float(x)) if np.isfinite(float(x)) else "—"
    except (TypeError, ValueError):
        return "—"


def informe(res: ResultadoF1, m: MercadoF1, ruta: Path, commit: str = "") -> str:
    cfg = m.cfg
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if res.variante is None:                  # la evaluación del 151, tal cual
        L = [f"# VALIDACIÓN DE FUTUROS F1 v2 — SOLO PAPEL", "",
             f"**Veredicto: F1 {'PASA' if res.pasa else 'NO PASA'}.**" + ("" if res.pasa else " Se queda con `activo: "
                                                                          "false`; es un resultado válido."), "",
             f"Fecha: {hoy}. {('Commit: ' + commit + '. ') if commit else ''}Hipótesis 003 (HIPOTESIS.md), registrada "
             f"antes de ver resultados. Datos de data.binance.vision desde {INICIO_DATOS}: velas de 4 h de Futuros, "
             f"precio de marca y funding. Walk-forward de 12 meses de entrenamiento (sin rejilla: solo verifica "
             f"operaciones mínimas) y 3 de prueba. Nada de esto promete ganancias.", ""]
    else:
        d = VR.variante(res.variante)
        L = [f"# VALIDACIÓN DE FUTUROS {res.variante} (variante de F1 v2) — SOLO PAPEL", "",
             f"**Veredicto: {res.variante} {res.veredicto}.** Se queda con `activo: false`: activar cualquier variante es "
             f"DECISIÓN DE ÁNGELO y exige escalones verificados y el Arreglo 152.", "",
             f"Fecha: {hoy}. {('Commit: ' + commit + '. ') if commit else ''}Hipótesis 004 (HIPOTESIS.md), registrada "
             f"antes de medir: lados «{d['lados']}», salida por tiempo "
             f"{'apagada' if d['tiempo_max_velas'] is None else str(d['tiempo_max_velas']) + ' velas sin +1R'}; todo lo "
             f"demás igual a F1 v2. Barras por {VR.PRUEBAS_FAMILIA} pruebas en la familia F1 ({VR.ideas_totales(m.reg)} "
             f"ideas): azar ≥ {VR.azar_min(m.reg):.2f} % y t ≥ {VR.t_min():.4f}. Mismas ventanas walk-forward (12/3) y "
             f"mismas monedas que F1, datos de data.binance.vision desde {INICIO_DATOS}. Nada de esto promete ganancias.",
             ""]
    L += ["## Compuertas (si falla una, NO PASA)", "", "| Compuerta | ¿Pasa? | Detalle |", "|---|---|---|"]
    for k, (ok, txt) in res.compuertas.items():
        L.append(f"| {k} | {'✅' if ok else '❌'} | {txt} |")
    o = res.resumen
    L += ["", "## Fuera de muestra (sumando las 4 monedas)", "",
          f"- Operaciones: {o.get('operaciones', 0)}; ganadoras {o.get('pct_ganadoras', 0):.0f} %; expectativa "
          f"{_f(o.get('expectativa_r'))}R; factor de ganancia {_f(o.get('factor_ganancia'), '{:.2f}')}; peor racha "
          f"{o.get('racha_perdedora_max', 0)} pérdidas.",
          f"- Monte Carlo suelto: caída p95 {_f(res.mc.get('caida_p95'), '{:.1f}')} %; por bloques: "
          f"{_f(res.mc_bloques.get('caida_p95'), '{:.1f}')} % (1 % de riesgo).",
          f"- Azar: le gana al {_f(res.azar.get('percentil_estrategia'), '{:.1f}')} % (pool de "
          f"{res.azar.get('pool', 0)} entradas al azar).",
          f"- Estrés de costos: expectativa {_f(res.estres.get('expectativa_r'))}R.",
          f"- t de la expectativa: {_f(o.get('t'), '{:.2f}')}.", "",
          "| Lado | Ops | Expectativa | Factor |", "|---|---|---|---|"]
    for lado, x in res.por_lado.items():
        L.append(f"| {lado} | {x.get('operaciones', 0)} | {_f(x.get('expectativa_r'))}R | "
                 f"{_f(x.get('factor_ganancia'), '{:.2f}')} |")
    L += ["", "| Moneda | Ops | Expectativa | R total | Parte | Sin ella |", "|---|---|---|---|---|---|"]
    for s, x in res.por_moneda.items():
        L.append(f"| {s} | {x.get('operaciones', 0)} | {_f(x.get('expectativa_r'))}R | {_f(x.get('r_total'), '{:+.2f}')} | "
                 f"{_f(x.get('parte_pct'), '{:.0f}')} % | {_f(res.sin_moneda.get(s))}R |")
    L += ["", "## Ventanas de prueba", "", "| Prueba | Ops entrenamiento | Ops prueba | R total | Expectativa |",
          "|---|---|---|---|---|"]
    for w in res.ventanas:
        L.append(f"| {w['prueba']} | {w['ops_entrenamiento']}{'' if w['entrenamiento_ok'] else ' (pocas)'} | {w['ops']} | "
                 f"{w['r_total']:+.2f} | {w['expectativa']:+.3f} |")
    rb = res.robustez
    if rb:
        L += ["", "## Robustez ±20 % (donchian_n × stop_atr)", "",
              "| donchian \\ stop | " + " | ".join(f"{p:+.0f} %" for p in rb["pasos"]) + " |",
              "|---" * (len(rb["pasos"]) + 1) + "|"]
        for d1 in rb["pasos"]:
            L.append(f"| {d1:+.0f} % | " + " | ".join(f"{rb['tabla'][(d1, d2)][0]:+.3f}" for d2 in rb["pasos"]) + " |")
    k = res.capital
    L += ["", f"## Cartera F con {cfg['capital_papel']} USDT (mínimos y pasos reales)", "",
          f"- Operaciones tomadas: {k.get('operaciones', 0)}; capital final {k.get('capital_final', 0):.2f} USDT; caída "
          f"máxima {k.get('caida_max_pct', 0):.1f} %; veces que se habría detenido todo (−15 %): "
          f"{len(k.get('detenciones', []))}; liquidaciones: {k.get('liquidaciones', 0)}.",
          f"- Señales que «no caben»: {k.get('no_caben', 0)} de {k.get('evaluadas', 0)} ({k.get('no_caben_pct', 0):.1f} %)."]
    L += ["", "## Cifras usadas (y quién las decidió)", ""] + [f"- {x}" for x in CF.renglones_origen(cfg)]
    L += [f"- Parámetros de F1: {F1.POR_DEFECTO} — MECÁNICO por delegación de Ángelo 2026-11-16 (fijos, sin rejilla)."]
    L += _seccion_huecos(m)
    L += _seccion_meses(m)
    L += ["", "## Avisos", ""] + ([f"- {a}" for a in res.avisos] or ["- Ninguno."])
    L.append(_renglon_sin_marca(res))
    L += ["- Tablas de escalones de liquidación: " + ("verificadas." if all(LQ.verificado(s) for s in cfg["monedas"])
          else "SUPUESTO CONSERVADOR (MMR 1 %) en las monedas sin verificar; ver escalones.json y PROPUESTAS.md N.")]
    texto = "\n".join(L) + "\n"
    ruta.write_text(texto, encoding="utf-8")
    return texto


# ---------------------------------------------------------------------------- holdout de monedas (Arreglo 162)
def veredicto_holdout(n: int, expectativa: float, expectativa_estres: float) -> str:
    """Con menos de 30 operaciones: SIN VEREDICTO (no cuenta como pasar). Si no: PASA con expectativa ≥ 0R normal y
    ≥ 0R con estrés; si no, NO PASA."""
    if n < VR.HOLDOUT_OPS_MIN:
        return "SIN VEREDICTO"
    return "PASA" if expectativa >= 0 and expectativa_estres >= 0 else "NO PASA"


def evaluar_holdout(m: MercadoF1, variante: str) -> ResultadoF1:
    """El holdout: mismas ventanas walk-forward, mismas reglas, misma selección y mismo filtro de liquidez que la
    validación completa, con las monedas del mercado `m` (las de variantes.MONEDAS_HOLDOUT)."""
    VR.variante(variante)
    params = dict(F1.POR_DEFECTO)
    res = ResultadoF1(avisos=list(m.avisos), variante=variante)
    ventanas = V.ventanas_wf(m.reg, sin_holdout=True)
    oos, res.ventanas = _oos(m, params, ventanas, variante=variante)
    res.oos = oos
    r = oos["r"].to_numpy(float) if len(oos) else np.array([])
    res.resumen = resumen_r(r)
    res.resumen["t"] = estadistico_t(r)
    res.resumen["liquidaciones"] = int(oos["liquidada"].fillna(False).astype(bool).sum()) if "liquidada" in oos else 0
    res.resumen["velas_liq_ultimo_precio"] = velas_sin_marca(oos)
    estres, _ = _oos(m, params, ventanas, estres=True, variante=variante)
    res.estres = resumen_r(estres["r"].to_numpy(float) if len(estres) else [])
    for lado in ("LARGO", "CORTO"):
        res.por_lado[lado] = resumen_r(oos.loc[oos["lado"] == lado, "r"].to_numpy(float) if len(oos) else [])
    for s in m.cfg["monedas"]:
        rs = oos.loc[oos["simbolo"] == s, "r"].to_numpy(float) if len(oos) else np.array([])
        res.por_moneda[s] = {**resumen_r(rs), "r_total": float(rs.sum())}
    n = int(res.resumen["operaciones"])
    res.veredicto = veredicto_holdout(n, float(res.resumen["expectativa_r"]), float(res.estres["expectativa_r"]))
    res.pasa = res.veredicto == "PASA"
    res.compuertas = {
        "operaciones": (n >= VR.HOLDOUT_OPS_MIN, f"{n} operaciones (mínimo {VR.HOLDOUT_OPS_MIN}; con menos, SIN "
                                                 f"VEREDICTO)"),
        "expectativa": (n > 0 and res.resumen["expectativa_r"] >= 0,
                        f"expectativa {res.resumen['expectativa_r']:+.3f}R con costos normales (mínimo 0R)"),
        "estres": (int(res.estres["operaciones"]) > 0 and res.estres["expectativa_r"] >= 0,
                   f"con estrés de costos: {res.estres['expectativa_r']:+.3f}R (mínimo 0R)")}
    return res


def informe_holdout(res: ResultadoF1, m: MercadoF1, ruta: Path, commit: str = "") -> str:
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    o = res.resumen
    extra = " (con menos de 30 operaciones no cuenta como pasar)" if res.veredicto == "SIN VEREDICTO" else ""
    L = [f"# HOLDOUT DE MONEDAS — {res.variante} — SOLO PAPEL", "",
         f"**Veredicto del holdout: {res.variante} {res.veredicto}.**{extra} Ningún veredicto activa nada: activar es "
         f"DECISIÓN DE ÁNGELO y exige escalones verificados y el Arreglo 152.", "",
         f"Fecha: {hoy}. {('Commit: ' + commit + '. ') if commit else ''}Hipótesis 004. Monedas declaradas el "
         f"2026-11-17 y nunca usadas en F1: {', '.join(m.cfg['monedas'])}. Mismo periodo, mismos datos de "
         f"data.binance.vision, mismas reglas, misma selección y mismo filtro de liquidez. Se abre UNA sola vez por "
         f"variante. Pasos, tarifa y escalones de respaldo: supuestos conservadores (variantes.RESPALDO_HOLDOUT) si "
         f"exchangeInfo no contesta. Nada de esto promete ganancias.", "",
         "| Regla | ¿Cumple? | Detalle |", "|---|---|---|"]
    L += [f"| {k} | {'✅' if ok else '❌'} | {txt} |" for k, (ok, txt) in res.compuertas.items()]
    L += ["", f"- Operaciones: {o.get('operaciones', 0)}; expectativa {_f(o.get('expectativa_r'))}R; factor "
              f"{_f(o.get('factor_ganancia'), '{:.2f}')}; t {_f(o.get('t'), '{:.2f}')}; estrés "
              f"{_f(res.estres.get('expectativa_r'))}R; liquidaciones {o.get('liquidaciones', 0)}.", "",
          "| Lado | Ops | Expectativa |", "|---|---|---|"]
    L += [f"| {k} | {x.get('operaciones', 0)} | {_f(x.get('expectativa_r'))}R |" for k, x in res.por_lado.items()]
    L += ["", "| Moneda | Ops | Expectativa | R total |", "|---|---|---|---|"]
    L += [f"| {s} | {x.get('operaciones', 0)} | {_f(x.get('expectativa_r'))}R | {_f(x.get('r_total'), '{:+.2f}')} |"
          for s, x in res.por_moneda.items()]
    L += _seccion_huecos(m)
    L += _seccion_meses(m)
    L += ["", "## Avisos", ""] + ([f"- {a}" for a in res.avisos] or ["- Ninguno."])
    L.append(_renglon_sin_marca(res))
    texto = "\n".join(L) + "\n"
    ruta.write_text(texto, encoding="utf-8")
    return texto


def fila_registro(res: ResultadoF1, commit: str = "", tipo: str = "completa") -> dict[str, Any]:
    """El renglón de VARIANTES_FUTUROS.md de una corrida (Arreglo 161)."""
    o = res.resumen
    ok = sum(1 for x, _ in res.compuertas.values() if x)
    return {"fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "commit": commit or "—",
            "variante": res.variante or "F1", "tipo": tipo, "veredicto": res.veredicto,
            "pasa_sin_escalones": res.pasa_sin_escalones, "compuertas": f"{ok}/{len(res.compuertas)}",
            "operaciones": int(o.get("operaciones", 0)), "expectativa_r": float(o.get("expectativa_r", float("nan"))),
            "factor": float(o.get("factor_ganancia", float("nan"))), "t": float(o.get("t", float("nan"))),
            "azar_pct": float(res.azar.get("percentil_estrategia", float("nan"))),
            "estres_r": float(res.estres.get("expectativa_r", float("nan"))),
            "largo_r": float(res.por_lado.get("LARGO", {}).get("expectativa_r", float("nan"))),
            "corto_r": float(res.por_lado.get("CORTO", {}).get("expectativa_r", float("nan")))}
