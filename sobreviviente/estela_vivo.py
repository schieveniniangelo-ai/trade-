"""ESTELA en vivo: guarda cada día la foto del posicionamiento (las rutas públicas de Binance Futuros solo
guardan 30 días hacia atrás, así que hay que ir guardando).

Archivo: datos/estela/AAAA-MM-DD.json (fecha = día de la vela que cerró a las 00:00 UTC). Valor = la última
foto de 5 minutos ANTES de las 00:00 UTC, igual que en el estudio histórico.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from . import archivos as AR
from . import datos as D
from .reglamento import Reglamento


def guardar_foto(reg: Reglamento, cli: D.ClienteBinance, simbolos: list[str] | None = None,
                 ahora: datetime | None = None) -> tuple[bool, str]:
    ahora = ahora or datetime.now(timezone.utc)
    dia = pd.Timestamp(ahora).tz_convert("UTC").normalize() - pd.Timedelta(days=1)
    fin_ms = int((dia + pd.Timedelta(days=1)).timestamp() * 1000) - 1
    if simbolos is None:
        try:
            info = cli.futuros("/fapi/v1/exchangeInfo")
        except D.ErrorDatos as e:
            return False, f"Las rutas de Binance Futuros están bloqueadas desde esta computadora ({e}). M3 se queda apagado."
        perps = {x["symbol"] for x in info["symbols"] if x.get("contractType") == "PERPETUAL" and x.get("status") == "TRADING"}
        papel = AR.carpeta_datos(reg) / "papel" / "grandes.json"
        grandes = json.loads(papel.read_text(encoding="utf-8")) if papel.exists() else ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
        simbolos = [s for s in grandes if s in perps]
    foto = {"fecha": dia.strftime("%Y-%m-%d"), "por": "ESTELA", "simbolos": {}}
    fallas = []
    for s in simbolos:
        try:
            top = cli.futuros("/futures/data/topLongShortPositionRatio", {"symbol": s, "period": "5m", "endTime": fin_ms, "limit": 1})
            masa = cli.futuros("/futures/data/globalLongShortAccountRatio", {"symbol": s, "period": "5m", "endTime": fin_ms, "limit": 1})
        except D.ErrorDatos as e:
            return False, f"Las rutas de Binance Futuros están bloqueadas desde esta computadora ({e}). M3 se queda apagado."
        if not top or not masa:
            fallas.append(s)
            continue
        foto["simbolos"][s] = {"top_posiciones": float(top[-1]["longShortRatio"]), "masa_cuentas": float(masa[-1]["longShortRatio"]),
                               "hora": pd.Timestamp(int(top[-1]["timestamp"]), unit="ms", tz="UTC").isoformat()}
    err = AR.validar_estela(foto)
    if err:
        return False, "La foto salió incompleta: " + "; ".join(err)
    AR.escribir_json_seguro(AR.carpeta_datos(reg) / "estela" / f"{foto['fecha']}.json", foto)
    extra = f" (sin datos: {', '.join(fallas)})" if fallas else ""
    return True, f"Foto de ESTELA del {foto['fecha']} guardada: {len(foto['simbolos'])} monedas{extra}."
