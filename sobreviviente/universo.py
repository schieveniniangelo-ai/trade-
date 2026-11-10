"""Universo: qué monedas se pueden operar. Solo por datos, sin moneda favorita."""
from __future__ import annotations

import re
from typing import Any, Iterable

import pandas as pd

from .reglamento import Reglamento


def activo_base(simbolo: str, cotizacion: str = "USDT") -> str:
    return simbolo[: -len(cotizacion)] if simbolo.endswith(cotizacion) else simbolo


def es_apalancado(base: str, bases_conocidas: set[str], sufijos: Iterable[str]) -> bool:
    """BTCUP, ETHDOWN, BNBBULL… son tokens apalancados. JUP o SUPER no lo son."""
    for suf in sufijos:
        m = re.fullmatch(rf"(.+){suf}", base)
        if m and len(m.group(1)) >= 2 and m.group(1) in bases_conocidas:
            return True
    return False


def nombre_permitido(reg: Reglamento, simbolo: str, bases_conocidas: set[str]) -> tuple[bool, str]:
    """Filtro por nombre: fuera stablecoins, fiat y tokens apalancados."""
    u = reg.datos["universo"]
    cot = u["cotizacion"]
    if not simbolo.endswith(cot):
        return False, f"no es par contra {cot}"
    base = activo_base(simbolo, cot)
    if base in set(u["stablecoins"]):
        return False, "stablecoin"
    if base in set(u["fiat"]):
        return False, "moneda fiat"
    if es_apalancado(base, bases_conocidas, u["sufijos_apalancados"]):
        return False, "token apalancado"
    return True, ""


def simbolos_candidatos(reg: Reglamento, exchange_info: dict[str, Any], incluir_deslistados: bool = False) -> list[str]:
    """Pares USDT que pasan el filtro por nombre. En vivo solo los que están en TRADING."""
    cot = reg.datos["universo"]["cotizacion"]
    simbolos = [s for s in exchange_info["symbols"] if s.get("quoteAsset") == cot]
    bases = {s["baseAsset"] for s in exchange_info["symbols"]}
    out = []
    for s in simbolos:
        if not incluir_deslistados and s.get("status") != "TRADING":
            continue
        if nombre_permitido(reg, s["symbol"], bases)[0]:
            out.append(s["symbol"])
    return sorted(out)


def tabla_volumen(diarios: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Tabla de volumen diario en USDT: filas = días, columnas = monedas."""
    cols = {s: df["quote_volume"] for s, df in diarios.items() if df is not None and not df.empty}
    return pd.DataFrame(cols).sort_index()


def pertenencia(reg: Reglamento, volumen: pd.DataFrame, minimo: float | None = None) -> pd.DataFrame:
    """Para cada día, qué monedas están en el universo (True/False), usando solo datos de días anteriores.

    Reglas: volumen mediano de los últimos N días ≥ mínimo, al menos N días listada y que haya operado ayer.
    """
    u = reg.datos["universo"]
    n = int(u["dias_volumen"])
    minimo = float(u["volumen_mediano_min_usdt"]) if minimo is None else minimo
    mediana = volumen.rolling(n, min_periods=n).median().shift(1)
    dias_listada = volumen.notna().cumsum().shift(1)
    opero_ayer = volumen.shift(1).notna() & (volumen.shift(1) > 0)
    return (mediana >= minimo) & (dias_listada >= int(u["dias_listada_min"])) & opero_ayer


def grandes(vol_mediano: pd.DataFrame, pertenece: pd.DataFrame, excluir: Iterable[str] = (), n: int = 15) -> pd.DataFrame:
    """v2: universo "grandes", día por día: las `n` monedas del universo con mayor volumen mediano
    de 30 días (calculado con días ANTERIORES), sin las de `excluir` (memes). True/False por día y moneda."""
    cols = [c for c in vol_mediano.columns if c not in set(excluir)]
    per = pertenece.reindex(index=vol_mediano.index, columns=cols).fillna(False).astype(bool)
    vm = vol_mediano[cols].where(per)
    lugar = vm.rank(axis=1, ascending=False, method="first")
    return (lugar <= n).fillna(False)


def clasificar_liquidez(reg: Reglamento, volumen_mediano: float, es_meme: bool) -> str:
    """grande / mediana / meme → define el deslizamiento que se supone."""
    if es_meme:
        return "meme"
    if volumen_mediano >= float(reg.costos["volumen_grande_min_usdt"]):
        return "grande"
    return "mediana"


def deslizamiento(reg: Reglamento, liquidez: str) -> float:
    return float(reg.costos["deslizamiento_pct"][liquidez])
