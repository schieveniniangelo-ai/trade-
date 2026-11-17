"""Apoyo para las pruebas de F1 (arreglos 145 en adelante): un cliente de Binance FALSO que nunca sale a la red.

Hereda de datos.ClienteBinance y solo reemplaza `_get` (el único punto que hace HTTP): así se prueba el camino
completo (velas_api, funding_api, exchange_info…) y se anota cada URL pedida para revisar la lista blanca.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sobreviviente import datos as D

BASES = {"BTCUSDT": 64000.0, "ETHUSDT": 1800.0, "SOLUSDT": 71.63, "XRPUSDT": 0.9547, "BNBUSDT": 591.45,
         "DOGEUSDT": 0.05885}
PASOS = {"BTCUSDT": ("0.10", "0.001", "100"), "ETHUSDT": ("0.01", "0.001", "20"), "SOLUSDT": ("0.0100", "0.01", "5"),
         "XRPUSDT": ("0.0001", "0.1", "5"), "BNBUSDT": ("0.010", "0.01", "5"), "DOGEUSDT": ("0.000010", "1", "5")}
TARIFA = {"SOLUSDT": "0.015000", "DOGEUSDT": "0.015000"}
MS = {"4h": 14_400_000, "1d": 86_400_000, "1h": 3_600_000}


def precio(simbolo: str, t_ms: int) -> float:
    """Precio sintético con tendencia larga y ondas (determinista)."""
    dias = t_ms / 86_400_000
    return BASES.get(simbolo, 10.0) * (1 + 0.25 * math.sin(dias / 40.0) + 0.05 * math.sin(dias / 3.0))


def exchange_info_falso() -> dict:
    simbolos = []
    for s, (tick, paso, minimo) in PASOS.items():
        simbolos.append({"symbol": s, "status": "TRADING", "liquidationFee": TARIFA.get(s, "0.012500"),
                         "filters": [{"filterType": "PRICE_FILTER", "tickSize": tick},
                                     {"filterType": "LOT_SIZE", "stepSize": paso, "minQty": paso},
                                     {"filterType": "MARKET_LOT_SIZE", "stepSize": paso, "minQty": paso},
                                     {"filterType": "MIN_NOTIONAL", "notional": minimo}]})
    return {"symbols": simbolos}


class Respuesta:
    def __init__(self, estado: int, cuerpo=None):
        self.status_code = estado
        self._cuerpo = cuerpo
        self.text = json.dumps(cuerpo) if cuerpo is not None else ""
        self.content = b""
        self.headers = {}

    def json(self):
        return self._cuerpo


class ClienteFalso(D.ClienteBinance):
    """`fin`: hora hasta la que hay velas cerradas (por defecto, la última vela de 4 h cerrada de ahora)."""

    def __init__(self, reg, fin: datetime | None = None, estado: int = 200, volumen_dia: float = 3e8):
        super().__init__(reg)
        ahora = datetime.now(timezone.utc)
        self.fin_ms = int((fin or ahora).timestamp() * 1000) // MS["4h"] * MS["4h"]
        self.estado = estado
        self.volumen_dia = volumen_dia
        self.urls: list[str] = []

    def _velas(self, simbolo: str, intervalo: str, inicio: int, limite: int) -> list[list]:
        paso = MS[intervalo]
        t = max(inicio, 0) // paso * paso
        if t < inicio:
            t += paso
        filas = []
        while t + paso <= self.fin_ms and len(filas) < limite:
            o, c = precio(simbolo, t), precio(simbolo, t + paso)
            h, lo = max(o, c) * 1.004, min(o, c) * 0.996
            qv = self.volumen_dia * paso / MS["1d"]
            filas.append([t, str(o), str(h), str(lo), str(c), str(qv / c), t + paso - 1, str(qv), 100, "0", "0", "0"])
            t += paso
        return filas

    def _get(self, url, params=None, intentos=3):
        params = params or {}
        self.urls.append(url)
        if self.estado != 200:
            return Respuesta(self.estado, {"msg": "bloqueado"})
        ruta = urlparse(url).path
        s = params.get("symbol", "")
        if ruta in ("/fapi/v1/klines", "/fapi/v1/markPriceKlines"):
            return Respuesta(200, self._velas(s, params["interval"], int(params["startTime"]), int(params["limit"])))
        if ruta == "/fapi/v1/fundingRate":
            t = int(params["startTime"]) // (8 * MS["1h"]) * (8 * MS["1h"]) + 8 * MS["1h"]
            filas = []
            while t <= self.fin_ms and len(filas) < int(params["limit"]):
                filas.append({"symbol": s, "fundingTime": t, "fundingRate": "0.00010000"})
                t += 8 * MS["1h"]
            return Respuesta(200, filas)
        if ruta == "/fapi/v1/premiumIndex":
            return Respuesta(200, {"symbol": s, "markPrice": str(precio(s, self.fin_ms)), "lastFundingRate": "0.0001",
                                   "nextFundingTime": self.fin_ms + 8 * MS["1h"]})
        if ruta == "/fapi/v1/fundingInfo":
            return Respuesta(200, [{"symbol": "DOGEUSDT", "fundingIntervalHours": 4,
                                    "adjustedFundingRateCap": "0.02", "adjustedFundingRateFloor": "-0.02"}])
        if ruta == "/fapi/v1/exchangeInfo":
            return Respuesta(200, exchange_info_falso())
        if ruta == "/fapi/v1/ticker/24hr":
            return Respuesta(200, {"symbol": s, "quoteVolume": str(self.volumen_dia)})
        return Respuesta(404, {"msg": "no existe"})


def escalones_verificados(monkeypatch) -> None:
    """Arreglo 159 (DECISIÓN DE ÁNGELO 2026-11-17): reemplaza `liquidacion._tabla` por una copia con TODAS las monedas
    `verificado: True` (mismos escalones), como test_arreglo161. No toca sobreviviente/futuros/escalones.json."""
    from sobreviviente.futuros import liquidacion as LQ
    tabla = LQ._tabla()
    falsa = {**tabla, "monedas": {s: {**x, "verificado": True} for s, x in tabla["monedas"].items()}}
    monkeypatch.setattr(LQ, "_tabla", lambda: falsa)
