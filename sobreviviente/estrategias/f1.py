"""F1 v2 — Futuros de dos lados en velas de 4 h (SOLO PAPEL; Hipótesis 003, registrada el 2026-11-17).

NO está en el registro de estrategias (`estrategias/__init__.ESTRATEGIAS`) ni en `estrategias:` del reglamento: vive
aparte para que `ronda_real.compuertas_puerta` no cambie. La usan solo `futuros-papel` y `validar-futuros`.

- Régimen doble: largo solo con la marea de BTC ALCISTA (cierre diario contra la media de 200 días) Y la tendencia de
  4 h de la moneda ALCISTA (EMA 200 con pendiente); corto solo con las dos BAJISTA.
- Entrada: el cierre rompe el máximo (largo) o el mínimo (corto) de las `donchian_n` velas anteriores; solo la primera
  vela (`flanco`). Señal al cierre; la entrada es en la apertura de la vela siguiente.
- Stop: `stop_atr` × ATR14; si queda abajo de 1.5 % o arriba de 8 % del precio, la señal se descarta.
- Funding: sin largo si los largos pagan más de `funding_extremo_pct` cada 8 h; sin corto si los cortos pagan más.
- Volatilidad EXTREMA (percentil ≥ 95 del ATR de 4 h): sin entradas.
- Salida: chandelier de `chandelier_atr` × ATR (solo a favor) o el régimen se voltea (la marea o la tendencia pasan al
  lado contrario); sin meta fija y sin mover el stop a la entrada.

Variantes (Arreglo 160, Hipótesis 004; `futuros/variantes.py`): `senales(ctx, p, variante)`. "F1" = lo de arriba, sin
cambios. lados="largo" (F1-L, F1-LT) apaga los cortos; "largo+corto_fuerte" (F1-LC) deja los cortos de F1 solo con
`extra["btc_bajista_fuerte"]`: al cierre DIARIO ya conocido, BTC < SMA200 y SMA200 < SMA200 de 20 días antes (la moneda
BAJISTA ya la pide todo corto de F1). La salida por tiempo de F1-LT vive en `gestion.salida_por_tiempo`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import datos as D
from .. import indicadores as ind
from .. import regimen as RG
from ..futuros import variantes as VR
from .base import Contexto, flanco, salida

TEMPORALIDAD = "4h"
PARAMETROS = ("donchian_n", "stop_atr", "chandelier_atr", "funding_extremo_pct")
POR_DEFECTO = {"donchian_n": 55, "stop_atr": 2.5, "chandelier_atr": 3.0,   # MECÁNICO por delegación de Ángelo 2026-11-16
               "funding_extremo_pct": 0.05}                                 # fijos, sin rejilla
STOP_MIN_PCT, STOP_MAX_PCT, VOL_EXTREMA = 1.5, 8.0, 95.0                    # MECÁNICO por delegación de Ángelo 2026-11-16
SMA_BAJA_DIAS = 20                       # F1-LC (Hipótesis 004): la SMA200 de BTC más baja que hace 20 días


def senales(ctx: Contexto, p: dict, variante: str = "F1") -> pd.DataFrame:
    """Señales de F1. Columnas extra: `lado` (LARGO/CORTO/None), `stop_pct`, `salir_largo` y `salir_corto`.
    `variante` (Hipótesis 004): F1, F1-L, F1-LC o F1-LT; una desconocida es error."""
    lados = VR.variante(variante)["lados"]
    v = ctx.velas
    n = int(p["donchian_n"])
    techo = ctx.memo(f"max{n}", lambda: ind.maximo_previo(v["high"], n))
    piso = ctx.memo(f"min{n}", lambda: ind.minimo_previo(v["low"], n))
    atr = ctx.atr(14)
    marea, tend = ctx.regimen_btc, ctx.regimen_moneda
    alcista = (marea == RG.ALCISTA) & (tend == RG.ALCISTA)
    bajista = (marea == RG.BAJISTA) & (tend == RG.BAJISTA)
    x = ctx.extra
    fund = x.get("funding_8h")
    fund = pd.Series(0.0, index=v.index) if fund is None else fund.reindex(v.index)
    lim = float(p["funding_extremo_pct"])
    largo_fund_ok = fund.notna() & (fund <= lim)            # funding > 0: pagan los largos
    corto_fund_ok = fund.notna() & (fund >= -lim)           # funding < 0: pagan los cortos
    vol = x.get("vol_percentil")
    vol_ok = pd.Series(True, index=v.index) if vol is None else ~(vol.reindex(v.index) >= float(x.get("vol_extrema", VOL_EXTREMA)))
    k = float(p["stop_atr"])
    stop_pct = k * atr / v["close"] * 100.0
    stop_ok = (stop_pct >= float(x.get("stop_min_pct", STOP_MIN_PCT))) & (stop_pct <= float(x.get("stop_max_pct", STOP_MAX_PCT)))
    filtros = vol_ok & stop_ok
    largo = flanco(alcista & (v["close"] > techo)) & largo_fund_ok & filtros
    corto = flanco(bajista & (v["close"] < piso)) & corto_fund_ok & filtros
    if lados == "largo":                                    # F1-L y F1-LT: sin cortos
        corto = pd.Series(False, index=v.index)
    elif lados == "largo+corto_fuerte":                     # F1-LC: los cortos de F1 solo en «bajista fuerte»
        fuerte = x.get("btc_bajista_fuerte")
        fuerte = pd.Series(False, index=v.index) if fuerte is None else \
            fuerte.reindex(v.index).fillna(False).astype(bool)
        corto = corto & fuerte
    stop = pd.Series(np.where(corto, v["close"] + k * atr, v["close"] - k * atr), index=v.index)
    fuerza = pd.Series(np.where(corto, (piso - v["close"]) / atr, (v["close"] - techo) / atr), index=v.index)
    df = salida(ctx, largo | corto, stop, None, fuerza)
    df["lado"] = pd.Series(np.where(largo, "LARGO", np.where(corto, "CORTO", None)), index=v.index, dtype=object)
    df.loc[~df["entrada"], "lado"] = None
    df["stop_pct"] = stop_pct
    df["salir_largo"] = ((marea == RG.BAJISTA) | (tend == RG.BAJISTA)).fillna(False).astype(bool)
    df["salir_corto"] = ((marea == RG.ALCISTA) | (tend == RG.ALCISTA)).fillna(False).astype(bool)
    return df


def gestion(p: dict) -> dict:
    """Chandelier que además sale en la apertura siguiente si el régimen se voltea; sin «+1R → entrada»."""
    return {"modo": "chandelier_senal", "chandelier_atr": float(p["chandelier_atr"]), "sin_breakeven": True}


def funding_8h_por_vela(funding: pd.Series | None, indice: pd.DatetimeIndex, ultimos: int = 3) -> pd.Series:
    """Promedio de los últimos `ultimos` cobros llevados a 8 h (en %), conocido al CIERRE de cada vela de 4 h."""
    if funding is None or funding.empty:
        return pd.Series(np.nan, index=indice)
    f = funding.sort_index()
    f = f[~f.index.duplicated(keep="last")]
    prom = D.funding_por_8h(f).rolling(ultimos).mean() * 100.0
    prom.index = prom.index.floor("s")
    cierre = indice + pd.Timedelta(hours=4)
    return pd.Series(prom.reindex(cierre, method="ffill").to_numpy(float), index=indice)


def bajista_fuerte_diario(btc1d: pd.DataFrame, reg) -> pd.Series:
    """F1-LC: día D → cierre de BTC < SMA200 Y SMA200 < SMA200 de 20 días antes (se conoce al cierre del día D)."""
    n = int(reg.get("regimen.diario.sma_btc_dias", 200))
    media = ind.sma(btc1d["close"], n)
    antes = media.shift(SMA_BAJA_DIAS)
    out = (btc1d["close"] < media) & (media < antes)
    return out.where(media.notna() & antes.notna(), False).astype(bool)


def armar_contexto(simbolo: str, velas4h: pd.DataFrame, btc1d: pd.DataFrame, funding: pd.Series | None, reg,
                   stop_min_pct: float = STOP_MIN_PCT, stop_max_pct: float = STOP_MAX_PCT) -> Contexto:
    """Contexto de F1 sin mirar el futuro: la marea del día D se usa desde su cierre (D+1 00:00 UTC). Igual el
    «bajista fuerte» de F1-LC (misma alineación)."""
    marea = RG.marea_diaria(btc1d, reg)
    marea4 = RG.a_intervalo(marea, velas4h.index, pd.Timedelta(days=1), pd.Timedelta(hours=4))
    fuerte4 = RG.a_intervalo(bajista_fuerte_diario(btc1d, reg).astype(object), velas4h.index, pd.Timedelta(days=1),
                             pd.Timedelta(hours=4))
    extra = {"funding_8h": funding_8h_por_vela(funding, velas4h.index),
             "vol_percentil": RG.percentil_volatilidad(velas4h, reg),
             "vol_extrema": float(reg.get("riesgo.ajustes.vol_extrema_percentil", VOL_EXTREMA)),
             "stop_min_pct": stop_min_pct, "stop_max_pct": stop_max_pct,
             "btc_bajista_fuerte": fuerte4.fillna(False).astype(bool)}
    return Contexto(simbolo=simbolo, velas=velas4h, regimen_moneda=RG.tendencia(velas4h, reg), regimen_btc=marea4,
                    extra=extra)
