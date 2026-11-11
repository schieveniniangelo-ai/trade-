"""v2: datos y backtester de los motores DIARIOS (M0, M1, M2 y las referencias R0–R2).

Usa exactamente las mismas piezas que la v1 y que el modo en vivo/papel:
- señales: `estrategias/m1.py` y `m2.py` (funciones puras, velas diarias cerradas);
- gestión de la posición: `gestion.vela` (vía `backtest.simular_operacion`);
- motor de riesgo: `riesgo.evaluar_candidato` (vía `backtest.cartera`).

Reglas de tiempo (sin ver el futuro): la vela diaria que abre el día D cierra a las 00:00 UTC de D+1.
La decisión se toma a esa hora y se ejecuta en la apertura de D+1. El universo del día D+1 se calcula
con volúmenes de días anteriores (hasta D).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import datos as D
from . import descartes as DS
from . import regimen as RG
from . import universo as U
from .backtest import simular_operacion
from .calidad import ajustar_redenominaciones
from .estrategias import ESTRATEGIAS
from .estrategias.base import Contexto
from .estrategias import m2 as M2
from .exchange import Filtros, filtros_desde_exchangeinfo, filtros_supuestos
from .reglamento import Reglamento

DIA = pd.Timedelta(days=1)
MIN_VELAS_DIARIAS = 60


@dataclass
class MercadoDiario:
    reg: Reglamento
    velas: dict[str, pd.DataFrame]            # velas diarias (ajustadas por redenominación)
    volumen: pd.DataFrame
    pertenece: pd.DataFrame
    vol_mediano: pd.DataFrame
    grandes: pd.DataFrame                     # índice = día de DECISIÓN (D+1)
    btc: pd.DataFrame                         # BTC diario largo (desde 2017) para la media de 200 días
    marea: pd.Series                          # ALCISTA/BAJISTA por vela (índice = apertura)
    memes: set[str] = field(default_factory=set)
    filtros: dict[str, Filtros] = field(default_factory=dict)
    vol_pct: dict[str, pd.Series] = field(default_factory=dict)
    redenominaciones: dict[str, list] = field(default_factory=dict)
    lugar_m2: dict[int, pd.DataFrame] = field(default_factory=dict)
    # Veto de ESTELA para el backtest (Paso 2): símbolo → días de SEÑAL vetados. None = sin veto (por defecto).
    veto: dict[str, set] | None = None
    _ctx: dict[tuple[str, str], Contexto] = field(default_factory=dict, repr=False)

    @property
    def btc_vol(self) -> pd.Series:
        return self.vol_pct.get("BTCUSDT", pd.Series(dtype=float))

    def cierres(self) -> dict[str, pd.Series]:
        """Cierres diarios con índice = hora de CIERRE (para valuar a mercado)."""
        out = {}
        for s, df in self.velas.items():
            c = df["close"].copy()
            c.index = c.index + DIA
            out[s] = c
        return out

    def grandes_en_vela(self) -> pd.DataFrame:
        """Universo "grandes" alineado a la vela de señal (fila D = vigente para decidir al cierre de D)."""
        g = self.grandes.copy()
        g.index = g.index - DIA
        return g


def cargar(reg: Reglamento, cliente: D.ClienteBinance, memes: list[str], simbolos: list[str] | None = None,
           exchange_info: dict | None = None) -> MercadoDiario:
    """Lee las velas diarias de la caché (las de `descargar`) y prepara universo, grandes y marea."""
    resumen_arch = cliente.cache / "resumen_descarga.json"
    if simbolos is None:
        simbolos = json.loads(resumen_arch.read_text())["universo_alguna_vez"]
    velas, redenom = {}, {}
    for s in simbolos:
        df = D.leer(D.ruta_cache(cliente, "spot", "1d", s))
        if df.empty:
            continue
        df = df.astype({c: "float64" for c in ["open", "high", "low", "close", "volume", "quote_volume"] if c in df})
        # En velas diarias, un "hueco" es que falte más de un día (36 h entre aperturas).
        df, ev = ajustar_redenominaciones(df, hueco_min_horas=36)
        if ev:
            redenom[s] = ev
        velas[s] = df
    return preparar(reg, velas, cliente, memes, redenom, exchange_info)


def preparar(reg: Reglamento, velas: dict[str, pd.DataFrame], cliente: D.ClienteBinance | None, memes: list[str],
             redenom: dict | None = None, exchange_info: dict | None = None,
             btc_largo: pd.DataFrame | None = None) -> MercadoDiario:
    if "BTCUSDT" not in velas or velas["BTCUSDT"] is None or velas["BTCUSDT"].empty:
        # Sin BTC no hay marea ni referencias: es un error de datos, no un día sin señales.
        raise D.ErrorDatos("faltan velas de BTC")
    memes_set = {x if x.endswith("USDT") else x + "USDT" for x in memes}
    volumen = U.tabla_volumen(velas)
    # Un día más al final: el universo del día de DECISIÓN (D+1) se calcula con los volúmenes hasta D.
    # Sin esta fila, en vivo la última decisión no tendría universo y nunca entraría nada.
    if len(volumen):
        volumen = volumen.reindex(volumen.index.append(pd.DatetimeIndex([volumen.index[-1] + DIA])))
    pertenece = U.pertenencia(reg, volumen)
    vol_mediano = volumen.rolling(int(reg.get("universo.dias_volumen")), min_periods=1).median().shift(1)
    grandes = U.grandes(vol_mediano, pertenece, memes_set, int(reg.get("universo.grandes_n", 15)))
    if btc_largo is None and cliente is not None:
        arch = cliente.cache / "spot" / "1d_largo" / "BTCUSDT.csv.gz"
        btc_largo = D.leer(arch) if arch.exists() else pd.DataFrame()
    btc = btc_largo if btc_largo is not None and not btc_largo.empty else velas["BTCUSDT"]
    # Une el histórico largo con lo más reciente (por si la caché diaria es más nueva).
    if "BTCUSDT" in velas:
        btc = pd.concat([btc, velas["BTCUSDT"]])
        btc = btc[~btc.index.duplicated(keep="last")].sort_index()
    md = MercadoDiario(reg=reg, velas=velas, volumen=volumen, pertenece=pertenece, vol_mediano=vol_mediano,
                       grandes=grandes, btc=btc, marea=RG.marea_diaria(btc, reg), memes=memes_set,
                       redenominaciones=redenom or {})
    md.velas["BTCUSDT"] = btc[btc.index >= velas["BTCUSDT"].index[0]] if "BTCUSDT" in velas else btc
    for s, df in md.velas.items():
        md.vol_pct[s] = RG.percentil_volatilidad_diaria(df, reg)
    minimo_resp = float(reg.get("backtest.minimo_respaldo_usdt", 5.0))
    info = exchange_info
    if info is None and cliente is not None:
        try:
            info = cliente.exchange_info("SPOT")
        except Exception:  # noqa: BLE001 - sin reglas en línea se usan las supuestas
            info = None
    por_simbolo = {x["symbol"]: x for x in info["symbols"]} if info else {}
    for s, df in md.velas.items():
        md.filtros[s] = filtros_desde_exchangeinfo(por_simbolo[s]) if s in por_simbolo else \
            filtros_supuestos(s, float(df["close"].iloc[-1]), minimo_resp)
    return md


def preparar_m2(md: MercadoDiario, Ls: list[int]) -> None:
    """Tabla de lugares de M2 para cada L (una sola vez)."""
    cierres = pd.DataFrame({s: df["close"] for s, df in md.velas.items() if s not in md.memes}).sort_index()
    g = md.grandes_en_vela().reindex(index=cierres.index, columns=cierres.columns).fillna(False)
    for L in Ls:
        if int(L) not in md.lugar_m2:
            md.lugar_m2[int(L)] = M2.ranking(cierres, g, int(L))


def contexto(md: MercadoDiario, clave: str, simbolo: str) -> Contexto | None:
    k = (clave, simbolo)
    if k in md._ctx:
        ctx = md._ctx[k]
        if clave == "M2":  # tablas de M2 calculadas después de crear el contexto (otra L): se agregan
            for L, tabla in md.lugar_m2.items():
                if f"lugar_{L}" not in ctx.extra and simbolo in tabla:
                    ctx.extra[f"lugar_{L}"] = tabla[simbolo].reindex(ctx.velas.index)
        return ctx
    velas = md.velas.get(simbolo)
    if velas is None or len(velas) < MIN_VELAS_DIARIAS:
        return None
    marea = md.marea.reindex(velas.index)
    extra: dict[str, Any] = {}
    if clave == "M2":
        for L, tabla in md.lugar_m2.items():
            if simbolo in tabla:
                extra[f"lugar_{L}"] = tabla[simbolo].reindex(velas.index)
    ctx = Contexto(simbolo=simbolo, velas=velas, regimen_moneda=pd.Series(None, index=velas.index, dtype=object),
                   regimen_btc=marea, extra=extra)
    md._ctx[k] = ctx
    return ctx


def simbolos_grandes(md: MercadoDiario, inicio=None, fin=None) -> list[str]:
    g = md.grandes
    if inicio is not None:
        g = g[(g.index >= inicio) & (g.index <= (fin if fin is not None else g.index[-1]) + DIA)]
    return sorted(c for c in g.columns if g[c].any())


def generar(md: MercadoDiario, clave: str, params: dict[str, Any], inicio, fin,
            filas_azar: dict[str, list[int]] | None = None,
            gest_override: dict[str, Any] | None = None, ejecucion_realista: bool = False,
            descartes: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    """Candidatos de un motor diario (cada señal simulada como operación independiente).

    `ejecucion_realista`: llena como el papel (límite de la compra y del stop del reglamento, sección `ejecucion`).
    Apagado por defecto: VALIDACION_V2.md se calculó sin él (ver CAMBIOS.md para cuánto cambia).
    `descartes`: si se pasa una lista, ahí se anotan las señales que no llegan a ser candidato (sin velas, fuera
    de "grandes", veto de ESTELA, stop sin valor o simulación nula), y se revisan TODAS las monedas con velas
    (no solo las que fueron "grandes") para ver las señales de fuera del universo. Los candidatos son los mismos."""
    reg = md.reg
    mod = ESTRATEGIAS[clave]
    cfg = reg.estrategias[clave]
    inicio = pd.Timestamp(inicio)
    fin = pd.Timestamp(fin)
    inicio = inicio.tz_localize("UTC") if inicio.tzinfo is None else inicio
    fin = fin.tz_localize("UTC") if fin.tzinfo is None else fin
    if clave == "M2":
        preparar_m2(md, [int(params["L"])])
    comision = float(reg.costos["comision_spot_pct"])
    lim_c = float(reg.get("ejecucion.limite_compra_pct", 0.3)) if ejecucion_realista else None
    lim_s = float(reg.get("ejecucion.limite_stop_pct", 0.5)) if ejecucion_realista else None
    simbolos = sorted(filas_azar) if filas_azar is not None else simbolos_grandes(md, inicio, fin)
    registrar = descartes is not None
    if registrar and filas_azar is None:
        simbolos = sorted(set(simbolos) | set(md.velas))   # también las que nunca fueron "grandes" (solo se anotan)

    def anotar(codigo: str, texto: str, s: str, fecha, **extra) -> None:
        descartes.append(DS.registro(codigo, texto, s, fecha, "", clave, origen="generacion", **extra))

    filas = []
    for s in simbolos:
        ctx = contexto(md, clave, s)
        if ctx is None:
            if registrar:
                anotar(DS.SIN_VELAS, "no hay velas suficientes para calcular la señal", s, None)
            continue
        sen = mod.senales(ctx, {**cfg.get("fijos", {}), **params})
        gest = mod.gestion(params)
        if not cfg.get("mover_a_entrada", True):
            gest = {**gest, "sin_breakeven": True}
        if gest_override:
            gest = {**gest, **gest_override}
        idx = ctx.velas.index
        if filas_azar is not None:
            filas_i = np.asarray(filas_azar[s], dtype=int)
        else:
            filas_i = np.flatnonzero(sen["entrada"].to_numpy() & (idx >= inicio) & (idx <= fin))
        if len(filas_i) == 0:
            continue
        v = ctx.velas
        arr = {"o": v["open"].to_numpy(float), "h": v["high"].to_numpy(float), "l": v["low"].to_numpy(float),
               "c": v["close"].to_numpy(float), "atr": ctx.atr().to_numpy(float)}
        if gest["modo"] in ("senal_salida", "ranking"):
            arr["salir"] = sen["salir"].to_numpy(bool)
        if gest["modo"] == "canal":
            arr["canal"] = v["low"].rolling(int(gest["canal_velas"])).min().to_numpy(float)
        stops, fuerzas, precios = (sen[c].to_numpy(float) for c in ("stop", "fuerza", "precio"))
        vol_s = md.vol_pct.get(s, pd.Series(dtype=float))
        for i in filas_i:
            t_senal = idx[i]
            t_decision = t_senal + DIA
            dia = t_decision.floor("D")
            previo = None   # (código, texto) del descarte previo al motor de riesgo; solo se usa si se registra
            try:
                ok = bool(md.grandes.at[dia, s])
            except KeyError:
                ok = False
            if not ok:
                if not registrar:
                    continue
                previo = (DS.FUERA_DE_UNIVERSO, 'la moneda no estaba en "grandes" ese día')
            if md.veto is not None and clave in ("M1", "M2") and t_senal in md.veto.get(s, ()):
                # ESTELA H2: la masa estaba en el 10 % más cargado en largo de sus 90 días → no se abre
                if not registrar:
                    continue
                previo = previo or (DS.VETO_ESTELA, "vetada por ESTELA (la masa está muy cargada en largo)")
            stop0 = stops[i]
            if not np.isfinite(stop0) or not np.isfinite(arr["atr"][i]) or stop0 >= precios[i]:
                if registrar:
                    cod, txt = previo or (DS.STOP_O_SIMULACION, "el stop o el ATR no tienen valor ese día")
                    anotar(cod, txt, s, t_decision)
                continue
            vm = md.vol_mediano.at[dia, s] if dia in md.vol_mediano.index and s in md.vol_mediano.columns else np.nan
            liquidez = U.clasificar_liquidez(reg, float(vm) if np.isfinite(vm) else 0.0, s in md.memes)
            desliz = U.deslizamiento(reg, liquidez)
            sim = simular_operacion(arr, idx, int(i), cfg["lado"], precios[i], stop0, None, gest, comision, desliz, DIA,
                                    limite_compra_pct=lim_c, limite_stop_pct=lim_s)
            if sim is None:
                if registrar:
                    cod, txt = previo or (DS.STOP_O_SIMULACION,
                                          "la operación no se pudo simular (sin vela siguiente o compra sin llenar)")
                    anotar(cod, txt, s, t_decision)
                continue
            fila = {
                "estrategia": clave, "simbolo": s, "t_senal": t_senal, "t_decision": t_decision,
                "precio_plan": precios[i], "stop": stop0, "meta": None, "fuerza": fuerzas[i],
                "comision_pct": comision, "desliz_pct": desliz, "liquidez": liquidez,
                "regimen_btc": md.marea.get(t_senal), "vol_btc": md.btc_vol.get(t_senal, np.nan),
                "vol_moneda": vol_s.get(t_senal, np.nan),
                "mercado": cfg["mercado"], "lado": cfg["lado"], "cubeta": cfg["cubeta"],
                **sim,
            }
            if previo is not None:
                # Descartada antes del motor de riesgo: queda en el registro con su operación SUELTA ya simulada
                # ("candidato"), para poder medir qué habría pasado. No entra a los candidatos.
                anotar(previo[0], previo[1], s, t_decision, r=sim["r"], pnl_unidad=sim["pnl_unidad"], candidato=fila)
                continue
            filas.append(fila)
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas).sort_values(["t_decision", "fuerza", "simbolo"], ascending=[True, False, True])
    return df.reset_index(drop=True)


def filas_elegibles(md: MercadoDiario, clave: str, params: dict[str, Any], inicio, fin) -> list[tuple[str, int]]:
    """Velas donde la moneda estaba en "grandes" (para entradas al azar con las mismas salidas)."""
    mod = ESTRATEGIAS[clave]
    out = []
    for s in simbolos_grandes(md, inicio, fin):
        ctx = contexto(md, clave, s)
        if ctx is None:
            continue
        idx = ctx.velas.index
        sen = mod.senales(ctx, {**md.reg.estrategias[clave].get("fijos", {}), **params})
        g = md.grandes[s].reindex((idx + DIA).floor("D")).fillna(False).to_numpy(bool)
        ok = g & (idx >= inicio) & (idx < fin) & np.isfinite(sen["stop"].to_numpy(float))
        out.extend((s, int(i)) for i in np.flatnonzero(ok[:-1]))
    return out
