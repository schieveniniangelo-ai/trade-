"""Calidad de datos: si los datos no son confiables, no se opera."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .reglamento import Reglamento


@dataclass
class ReporteCalidad:
    simbolo: str
    confiable: bool = True
    motivos: list[str] = field(default_factory=list)
    huecos: int = 0
    atraso_velas: float = 0.0
    saltos: int = 0


def revisar_velas(reg: Reglamento, df: pd.DataFrame, simbolo: str, intervalo: str = "1h",
                  ahora: datetime | None = None, ventana: int = 500) -> ReporteCalidad:
    """Revisa velas faltantes, datos viejos y precios absurdos en las últimas `ventana` velas."""
    rep = ReporteCalidad(simbolo=simbolo)
    if df is None or df.empty:
        rep.confiable = False
        rep.motivos.append("no hay datos")
        return rep
    paso = pd.Timedelta(intervalo)
    reciente = df.iloc[-ventana:]

    # Velas faltantes
    esperadas = int((reciente.index[-1] - reciente.index[0]) / paso) + 1
    rep.huecos = max(0, esperadas - len(reciente))
    pct = rep.huecos / max(esperadas, 1) * 100
    if pct > float(reg.get("datos.max_huecos_pct", 1.0)):
        rep.confiable = False
        rep.motivos.append(f"faltan {rep.huecos} velas ({pct:.1f} %)")

    # Datos viejos: la última vela cerrada debe ser reciente
    if ahora is not None:
        ultima_cierre = reciente.index[-1] + paso
        rep.atraso_velas = (pd.Timestamp(ahora).tz_convert("UTC") - ultima_cierre) / paso
        if rep.atraso_velas > float(reg.get("datos.max_velas_atraso", 2)):
            rep.confiable = False
            rep.motivos.append(f"datos viejos: {rep.atraso_velas:.1f} velas de atraso")

    # Precios absurdos
    malos = (reciente[["open", "high", "low", "close"]] <= 0).any(axis=1) | (reciente["high"] < reciente["low"])
    if malos.any():
        rep.confiable = False
        rep.motivos.append(f"{int(malos.sum())} velas con precios imposibles")
    limite = float(reg.get("datos.salto_absurdo_pct", 60)) / 100
    cambio = (reciente["close"] / reciente["close"].shift(1) - 1).abs()
    rep.saltos = int((cambio > limite).sum())
    if rep.saltos:
        rep.confiable = False
        rep.motivos.append(f"{rep.saltos} saltos de precio de más de {limite:.0%} en una vela")
    return rep


def ajustar_redenominaciones(df: pd.DataFrame, hueco_min_horas: float = 12.0,
                             salto_min_pct: float = 40.0) -> tuple[pd.DataFrame, list[dict]]:
    """Corrige cambios de denominación (token swaps): Binance pausa la moneda unos días y regresa con
    otro precio (p. ej. BNX 1:100). Eso NO es una ganancia ni una pérdida real.

    Regla: si hay un hueco de más de `hueco_min_horas` en las velas Y el precio salta más de
    `salto_min_pct` % entre el último cierre antes del hueco y la primera apertura después, se ajustan
    los precios ANTERIORES por esa proporción (como un "split" de acciones). El volumen en USDT no cambia.
    Las caídas reales con la moneda operando (como LUNA en mayo de 2022) NO se tocan.
    """
    if df is None or len(df) < 2:
        return df, []
    huecos = df.index.to_series().diff() > pd.Timedelta(hours=hueco_min_horas)
    eventos = []
    out = df.copy()
    cols_precio = [c for c in ("open", "high", "low", "close") if c in out.columns]
    for t in df.index[huecos.to_numpy()]:
        i = out.index.get_loc(t)
        antes = out["close"].iloc[i - 1]
        despues = out["open"].iloc[i]
        if antes <= 0:
            continue
        razon = despues / antes
        if abs(razon - 1) * 100 >= salto_min_pct:
            out.iloc[:i, [out.columns.get_loc(c) for c in cols_precio]] *= razon
            if "volume" in out.columns:
                out.iloc[:i, out.columns.get_loc("volume")] /= razon
            eventos.append({"fecha": t, "proporcion": float(razon)})
    return out, eventos
