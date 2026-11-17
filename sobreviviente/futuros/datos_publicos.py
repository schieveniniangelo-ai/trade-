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
    return out
