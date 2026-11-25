"""Datos PÚBLICOS de Binance Futuros para F1 (SOLO PAPEL): solo GET y solo rutas de la lista blanca.

Todo pasa por `ClienteBinance.futuros` (GET a la API pública de Futuros) y por lo que ya existe en datos.py:
`velas_api` con mercado FUTUROS, `actualizar_futuros` (4 h, históricos), `actualizar_precio_marca` remuestreado a 4 h
con `resamplear`, `funding_api` y `funding_por_8h`. Nada de llaves ni de rutas firmadas. Si Futuros responde 451 o 403
(bloqueo por región), F1 dice «Futuros no disponible» y ese día no hay entradas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from .. import datos as D

RUTAS_PERMITIDAS = ("/fapi/v1/klines", "/fapi/v1/markPriceKlines", "/fapi/v1/fundingRate", "/fapi/v1/premiumIndex",
                    "/fapi/v1/fundingInfo", "/fapi/v1/exchangeInfo", "/fapi/v1/ticker/24hr")
HOST_FUTUROS = "fapi.binance.com"
HOST_HISTORICOS = "data.binance.vision"
PREFIJO_HISTORICOS = "/data/futures/um/"
MAX_HORAS_DATOS = 48           # MECÁNICO por delegación de Ángelo 2026-11-16: datos de más de 48 h = sin entradas
DIAS_4H = 150                  # EMA 200 + pendiente de 20 velas + percentil de 90 días de velas de 4 h
DIAS_BTC_1D = 260              # media de 200 días de la marea de BTC
NO_DISPONIBLE = "Futuros no disponible"


def ruta_permitida(url: str) -> bool:
    """¿La URL es un GET público de la lista blanca de F1?"""
    u = urlparse(url)
    if u.hostname == HOST_HISTORICOS:
        return u.path.startswith(PREFIJO_HISTORICOS)
    if u.hostname == HOST_FUTUROS:
        return u.path in RUTAS_PERMITIDAS
    return False


def _ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def velas_4h(cliente: D.ClienteBinance, simbolo: str, ahora: datetime, dias: int = DIAS_4H) -> pd.DataFrame:
    """Velas de 4 h YA CERRADAS del perpetuo (GET /fapi/v1/klines por `velas_api`)."""
    return cliente.velas_api(simbolo, "4h", _ms(ahora - timedelta(days=dias)), _ms(ahora), mercado="FUTUROS")


def velas_1d(cliente: D.ClienteBinance, simbolo: str, ahora: datetime, dias: int) -> pd.DataFrame:
    """Velas diarias ya cerradas del perpetuo (marea de BTC y volumen de 30 días)."""
    return cliente.velas_api(simbolo, "1d", _ms(ahora - timedelta(days=dias)), _ms(ahora), mercado="FUTUROS")


def marca_4h(cliente: D.ClienteBinance, simbolo: str, ahora: datetime, dias: int = 10) -> pd.DataFrame:
    """Velas de 4 h del precio de MARCA ya cerradas (GET /fapi/v1/markPriceKlines): con ellas se revisa la liquidación."""
    filas = cliente.futuros("/fapi/v1/markPriceKlines", {"symbol": simbolo, "interval": "4h",
                                                         "startTime": _ms(ahora - timedelta(days=dias)), "limit": 1500})
    if not filas:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    df = pd.DataFrame([f[:7] for f in filas], columns=["t", "open", "high", "low", "close", "_", "fin"])
    df.index = pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True)
    df = df[pd.to_datetime(df["fin"].astype("int64"), unit="ms", utc=True) < pd.Timestamp(ahora)]
    return df[["open", "high", "low", "close"]].astype(float)


def marca_4h_historica(cliente: D.ClienteBinance, simbolo: str, inicio: str, fin: str) -> pd.DataFrame:
    """Precio de marca de 1 h de data.binance.vision (`actualizar_precio_marca`) remuestreado a 4 h."""
    return D.resamplear(D.actualizar_precio_marca(cliente, simbolo, inicio, fin), "4h")


def funding(cliente: D.ClienteBinance, simbolo: str, ahora: datetime, dias: int = 10) -> pd.Series:
    """Cobros de funding (fracción por cobro) de los últimos días (`funding_api`)."""
    return cliente.funding_api(simbolo, _ms(ahora - timedelta(days=dias)))


def funding_8h_promedio(serie: pd.Series, ultimos: int = 3) -> float | None:
    """Promedio de los últimos 3 cobros llevados a 8 h (`funding_por_8h`), en %. None sin cobros."""
    if serie is None or serie.empty:
        return None
    return float(D.funding_por_8h(serie.sort_index()).tail(ultimos).mean() * 100.0)


def marca_y_funding(cliente: D.ClienteBinance, simbolo: str) -> dict[str, Any]:
    """Precio de marca, último funding y próximo cobro (GET /fapi/v1/premiumIndex)."""
    d = cliente.futuros("/fapi/v1/premiumIndex", {"symbol": simbolo})
    return {"marca": float(d["markPrice"]), "funding_pct": float(d["lastFundingRate"]) * 100.0,
            "proximo_cobro": pd.Timestamp(int(d["nextFundingTime"]), unit="ms", tz="UTC")}


def info_funding(cliente: D.ClienteBinance) -> dict[str, dict[str, Any]]:
    """Intervalo de cobro y topes por moneda (GET /fapi/v1/fundingInfo). Solo trae las monedas con ajustes."""
    out = {}
    for x in cliente.futuros("/fapi/v1/fundingInfo") or []:
        out[x["symbol"]] = {"intervalo_h": int(x.get("fundingIntervalHours", 8)),
                            "tope_pct": float(x.get("adjustedFundingRateCap", 0)) * 100.0,
                            "piso_pct": float(x.get("adjustedFundingRateFloor", 0)) * 100.0}
    return out


def volumen_mediano_30d(diarias: pd.DataFrame) -> float:
    """Mediana del volumen en USDT de los últimos 30 días cerrados del perpetuo (klines diarias)."""
    if diarias is None or diarias.empty:
        return 0.0
    return float(diarias["quote_volume"].tail(30).median())


def horas_de_atraso(velas: pd.DataFrame, ahora: datetime, duracion: timedelta = timedelta(hours=4)) -> float:
    """Horas desde el cierre de la última vela (infinito si no hay velas)."""
    if velas is None or velas.empty:
        return float("inf")
    cierre = velas.index[-1].to_pydatetime() + duracion
    return max(0.0, (ahora - cierre).total_seconds() / 3600.0)


def huecos_velas(indice: pd.Index, paso: timedelta) -> dict[str, Any]:
    """Arreglo 203 (solo informa): velas esperadas de la primera a la última recibida, cada `paso`, contra las recibidas.
    Solo cuenta los huecos de EN MEDIO: el atraso del final ya lo mide `horas_de_atraso` y una moneda recién listada
    no tiene hueco al principio. `desde`/`hasta`: la primera y la última vela que faltan (None si no falta ninguna)."""
    vacio = {"esperadas": 0, "recibidas": 0, "faltan": 0, "desde": None, "hasta": None}
    if indice is None or len(indice) == 0:
        return vacio
    recibidas = pd.DatetimeIndex(indice).floor("s").unique().sort_values()
    esperadas = pd.date_range(recibidas[0], recibidas[-1], freq=pd.Timedelta(paso))
    faltan = esperadas.difference(recibidas)
    return {"esperadas": len(esperadas), "recibidas": len(recibidas), "faltan": len(faltan),
            "desde": faltan[0] if len(faltan) else None, "hasta": faltan[-1] if len(faltan) else None}


MIN_TRAMO_FUNDING = 3         # Arreglo 207: separaciones iguales seguidas para decir que el intervalo cambió (solo avisos)


def _tramos_funding(redondeo: list[float]) -> tuple[list[float], list[tuple[int, float]]]:
    """Arreglo 207: el intervalo de cada separación y los tramos [(primera separación, intervalo)].

    Un tramo es una racha de al menos MIN_TRAMO_FUNDING separaciones normales iguales (redondeadas a 1/2/4/8 h). Una
    separación suelta (un hueco) toma el intervalo del tramo de antes; si no hay, el del siguiente. Sin ninguna racha
    así (serie muy corta), toda la serie usa el intervalo más común, como el Arreglo 203."""
    rachas, k = [], 0
    while k < len(redondeo):
        fin = k
        while fin < len(redondeo) and redondeo[fin] == redondeo[k]:
            fin += 1
        rachas.append((k, fin, redondeo[k]))
        k = fin
    normales = [r for r in rachas if r[1] - r[0] >= MIN_TRAMO_FUNDING]
    if not normales:
        iv = max(set(redondeo), key=lambda x: (redondeo.count(x), -x))
        return [iv] * len(redondeo), [(0, iv)]
    por_sep: list[float | None] = [None] * len(redondeo)
    tramos: list[tuple[int, float]] = []
    for a, b, v in normales:
        por_sep[a:b] = [v] * (b - a)
        if not tramos or tramos[-1][1] != v:
            tramos.append((a, v))
    anterior = None
    for k in range(len(por_sep)):
        if por_sep[k] is None:
            por_sep[k] = anterior if anterior is not None else normales[0][2]
        else:
            anterior = por_sep[k]
    return [float(x) for x in por_sep], tramos


def huecos_funding(serie: pd.Series) -> dict[str, Any]:
    """Arreglo 203 (solo informa): cobros de funding esperados contra los recibidos.

    Arreglo 207: el intervalo se mide POR TRAMOS (cuando cambia la separación normal entre cobros, ver
    `_tramos_funding`), redondeado a 1, 2, 4 u 8 h como `D.intervalo_funding` (sin pedir /fapi/v1/fundingInfo), y cada
    hueco se cuenta con el intervalo de su tramo: una separación de k intervalos = k − 1 cobros faltantes.
    `intervalo_h` es el del último tramo y `tramos` dice desde cuándo rige cada uno."""
    vacio = {"esperados": 0, "recibidos": 0, "faltan": 0, "intervalo_h": None, "desde": None, "hasta": None,
             "tramos": []}
    if serie is None or len(serie) == 0:
        return vacio
    horas = pd.DatetimeIndex(serie.index).floor("s").unique().sort_values()
    if len(horas) < 2:
        return {**vacio, "esperados": 1, "recibidos": 1}
    dif = horas.to_series().diff().dropna().dt.total_seconds().to_numpy() / 3600.0
    opciones = np.array(D.INTERVALOS_FUNDING_H, dtype=float)
    redondeo = [float(opciones[np.argmin(np.abs(opciones - min(x, 8.0)))]) for x in dif]
    por_sep, tramos = _tramos_funding(redondeo)
    faltan, desde, hasta = 0, None, None
    for k, x in enumerate(dif):
        iv = por_sep[k]
        n = int(round(x / iv)) - 1
        if n > 0:
            faltan += n
            primera = horas[k] + pd.Timedelta(hours=iv)
            desde = desde if desde is not None else primera
            hasta = horas[k + 1] - pd.Timedelta(hours=iv)
    return {"esperados": len(horas) + faltan, "recibidos": len(horas), "faltan": faltan,
            "intervalo_h": int(tramos[-1][1]), "desde": desde, "hasta": hasta,
            "tramos": [{"desde": horas[a], "intervalo_h": int(v)} for a, v in tramos]}


def _cada(f: dict[str, Any]) -> str:
    """«8 y luego 4» si el intervalo cambió dentro de la ventana (Arreglo 207); si no, el intervalo."""
    ivs = [t["intervalo_h"] for t in f.get("tramos") or []]
    return " y luego ".join(str(x) for x in ivs) if len(ivs) > 1 else str(f["intervalo_h"])


def _hora(t: pd.Timestamp) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M")


def texto_huecos(simbolo: str, h: dict[str, dict[str, Any]], marca_h: int = 4) -> list[str]:
    """Los avisos de huecos de una moneda (vacío si no falta nada). Solo avisan: no bloquean nada."""
    out = []
    piezas = [("velas", "vela" if h.get("velas", {}).get("faltan") == 1 else "velas", "de 4 h"),
              ("marca", "vela" if h.get("marca", {}).get("faltan") == 1 else "velas", f"de marca de {marca_h} h")]
    for clave, nombre, que in piezas:
        x = h.get(clave) or {}
        if x.get("faltan"):
            verbo = "falta" if x["faltan"] == 1 else "faltan"
            out.append(f"⚠️ Huecos de datos de {simbolo}: {verbo} {x['faltan']} {nombre} {que} entre {_hora(x['desde'])} "
                       f"y {_hora(x['hasta'])} UTC (de {x['esperadas']} esperadas; solo aviso).")
    f = h.get("funding") or {}
    if f.get("faltan"):
        cobros = "falta 1 cobro" if f["faltan"] == 1 else f"faltan {f['faltan']} cobros"
        out.append(f"⚠️ Huecos de datos de {simbolo}: {cobros} de funding (cada {_cada(f)} h) entre "
                   f"{_hora(f['desde'])} y {_hora(f['hasta'])} UTC (de {f['esperados']} esperados; solo aviso).")
    return out


@dataclass
class DatosF1:
    """Lo que necesita una corrida de F1. `entradas_ok` False = ese día no hay entradas nuevas."""

    velas: dict[str, pd.DataFrame] = field(default_factory=dict)
    marca: dict[str, pd.DataFrame] = field(default_factory=dict)
    funding: dict[str, pd.Series] = field(default_factory=dict)
    volumen: dict[str, float] = field(default_factory=dict)
    btc1d: pd.DataFrame | None = None
    exchange: dict[str, dict[str, Any]] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    disponible: bool = True
    entradas_ok: bool = True
    huecos: dict[str, dict[str, Any]] = field(default_factory=dict)    # Arreglo 203: conteos por moneda (solo informan)


def cargar(cliente: D.ClienteBinance, cfg: dict[str, Any], ahora: datetime | None = None) -> DatosF1:
    """Baja todo lo de las monedas de F1 y BTC. Si algo falla, avisa y apaga las entradas (nunca truena)."""
    ahora = ahora or datetime.now(timezone.utc)
    out = DatosF1()
    try:
        info = cliente.exchange_info("FUTUROS")
        out.exchange = {x["symbol"]: x for x in info.get("symbols", []) if x.get("symbol") in cfg["monedas"]}
        out.btc1d = velas_1d(cliente, cfg["regimen_btc"], ahora, DIAS_BTC_1D)
        for s in cfg["monedas"]:
            out.velas[s] = velas_4h(cliente, s, ahora)
            out.marca[s] = marca_4h(cliente, s, ahora)
            out.funding[s] = funding(cliente, s, ahora)
            out.volumen[s] = volumen_mediano_30d(velas_1d(cliente, s, ahora, 31))
    except D.ErrorDatos as e:
        out.entradas_ok = False
        if cliente.futuros_disponible is False:
            out.disponible = False
            out.avisos.append(f"⚠️ {NO_DISPONIBLE} desde esta computadora ({e}): hoy F1 no tiene entradas.")
        else:
            out.avisos.append(f"⚠️ Falló un dato de Futuros ({e}): hoy F1 no tiene entradas.")
        return out
    for s, v in [(cfg["regimen_btc"] + " 1d", out.btc1d)] + list(out.velas.items()):
        dur = timedelta(days=1) if s.endswith(" 1d") else timedelta(hours=4)
        h = horas_de_atraso(v, ahora, dur)
        if h > MAX_HORAS_DATOS:
            out.entradas_ok = False
            out.avisos.append(f"⚠️ Los datos de {s} tienen {h:.0f} h de atraso (más de {MAX_HORAS_DATOS} h): "
                              f"hoy F1 no tiene entradas.")
    for s in cfg["monedas"]:      # Arreglo 203: huecos de en medio. Solo avisan: no tocan entradas_ok
        mk = out.marca.get(s)
        out.huecos[s] = {"velas": huecos_velas(out.velas[s].index, timedelta(hours=4)),
                         "marca": huecos_velas(mk.index if mk is not None else None, timedelta(hours=4)),
                         "funding": huecos_funding(out.funding.get(s))}
        out.avisos.extend(texto_huecos(s, out.huecos[s]))
    return out
