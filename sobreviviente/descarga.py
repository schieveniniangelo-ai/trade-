"""Descarga masiva de históricos para el backtest (comando `descargar`)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from . import datos as D
from . import universo as U
from .reglamento import Reglamento

log = logging.getLogger("sobreviviente.descarga")


def descargar_todo(reg: Reglamento, cliente: D.ClienteBinance, avisar=print, con_futuros: bool = True) -> dict:
    """1) Velas diarias de TODOS los pares USDT (incluidos deslistados) para saber quién estuvo en el universo.
    2) Velas de 1 h de las monedas que alguna vez estuvieron en el universo.
    3) Futuros (velas de 1 h, funding y precio de marca de 1 h) de las de mayor volumen.
    """
    inicio = reg.get("datos.inicio_historicos")
    fin_bt = reg.get("backtest.fin")
    fin_dia = (pd.Timestamp(fin_bt) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    info = cliente.exchange_info("SPOT", forzar=True)
    candidatos = U.simbolos_candidatos(reg, info, incluir_deslistados=True)
    avisar(f"Pares USDT candidatos (incluye deslistados): {len(candidatos)}")

    D.descargar_muchos(lambda s: D.actualizar_spot(cliente, s, "1d", inicio, fin_dia), [(s,) for s in candidatos])
    diarios = {s: D.leer(D.ruta_cache(cliente, "spot", "1d", s)) for s in candidatos}
    vol = U.tabla_volumen(diarios)
    per = U.pertenencia(reg, vol)
    ventana = per.loc[pd.Timestamp(reg.get("backtest.inicio"), tz="UTC") - pd.Timedelta(days=30):]
    alguna_vez = sorted(ventana.columns[ventana.any()])
    avisar(f"Monedas que alguna vez estuvieron en el universo: {len(alguna_vez)}")

    D.descargar_muchos(lambda s: D.actualizar_spot(cliente, s, "1h", inicio, fin_dia), [(s,) for s in alguna_vez])

    fut = []
    if con_futuros:
        med = vol.rolling(30).median()
        umbral = float(reg.get("universo.futuros_volumen_min_usdt"))
        fut = sorted([s for s in alguna_vez if (med[s] >= umbral).any()])
        avisar(f"Descargando Futuros de {len(fut)} monedas")
        D.descargar_muchos(lambda s: D.actualizar_futuros(cliente, s, "1h", inicio, fin_bt), [(s,) for s in fut])
        avisar(f"Descargando el precio de marca (1 h) de {len(fut)} perpetuos")
        D.descargar_muchos(lambda s: D.actualizar_precio_marca(cliente, s, inicio, fin_bt), [(s,) for s in fut])

    descargar_largo(cliente, reg.get("backtest.fin"))

    resumen = {
        "fecha": pd.Timestamp.now(tz="UTC").isoformat(),
        "candidatos": len(candidatos),
        "universo_alguna_vez": alguna_vez,
        "futuros": fut,
        "deslistados_incluidos": [s for s in alguna_vez
                                  if next((x for x in info["symbols"] if x["symbol"] == s), {}).get("status") != "TRADING"],
    }
    (cliente.cache / "resumen_descarga.json").write_text(json.dumps(resumen, indent=1))
    return resumen


def descargar_largo(cliente: D.ClienteBinance, fin: str, simbolos=("BTCUSDT", "ETHUSDT"),
                    inicio: str = "2017-08-01") -> None:
    """Velas diarias largas de BTC y ETH (desde 2017) para la media de 200 días y las referencias."""
    fin_ms = int((pd.Timestamp(fin, tz="UTC") + pd.Timedelta(days=1)).value // 10**6)
    for s in simbolos:
        df = cliente.velas_api(s, "1d", int(pd.Timestamp(inicio, tz="UTC").value // 10**6), fin_ms)
        if not df.empty:
            D.guardar(df, cliente.cache / "spot" / "1d_largo" / f"{s}.csv.gz")
