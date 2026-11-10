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


def _firma(s: dict[str, Any]) -> frozenset | None:
    """Firma de permisos de un par: los grupos de `permissionSets` sin importar el orden. Sin el campo (o vacío): None."""
    try:
        grupos = s.get("permissionSets")
        if not grupos:
            return None
        return frozenset(frozenset(g) for g in grupos)
    except (TypeError, AttributeError):
        return None


def bstocks_detectadas(reg: Reglamento, exchange_info: dict[str, Any]) -> tuple[set[str], list[str]]:
    """(bases excluidas, símbolos "raros" que solo se avisan).

    Binance NO publica un campo que diga "acción tokenizada" (bStock): solo se observó que todas comparten la misma
    firma de `permissionSets`, distinta de la cripto. Es una correlación observada, no algo de la documentación.
    Referencia = las firmas de los pares cuya base está en `universo.excluir_bases`. Una base se excluye si (a) está en
    esa lista o (b) tiene una firma de referencia, termina en "B" y no está en `universo.permitir_con_B`.
    Rara (solo aviso): firma de referencia sin terminar en B, o termina en B con par USDT en TRADING y no está en
    ninguna de las dos listas. Una copia vieja de exchangeInfo sin `permissionSets` no falla: solo vale la lista fija."""
    u = reg.datos["universo"]
    cot = u["cotizacion"]
    lista = set(u.get("excluir_bases") or [])
    permitir = set(u.get("permitir_con_B") or [])
    simbolos = [s for s in (exchange_info or {}).get("symbols", []) if isinstance(s, dict)]
    referencia = {f for s in simbolos if s.get("baseAsset") in lista and (f := _firma(s)) is not None}
    excluidas, raras = set(lista), {}
    for s in simbolos:
        base = str(s.get("baseAsset", ""))
        if not base or base in lista or base in permitir:
            continue
        misma_firma = _firma(s) in referencia if referencia else False
        con_b = base.endswith("B")
        if misma_firma and con_b:
            excluidas.add(base)
        elif s.get("quoteAsset") == cot and s.get("status") == "TRADING" and (misma_firma or con_b):
            raras[str(s.get("symbol", base + cot))] = base
    return excluidas, sorted(sim for sim, base in raras.items() if base not in excluidas)


def nombre_permitido(reg: Reglamento, simbolo: str, bases_conocidas: set[str],
                     excluidas: set[str] | None = None) -> tuple[bool, str]:
    """Filtro por nombre: fuera stablecoins, fiat y tokens apalancados.
    `excluidas`: bases fuera del universo (de `bstocks_detectadas`); si no se da, solo `universo.excluir_bases`."""
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
    if base in (set(u.get("excluir_bases") or []) if excluidas is None else excluidas):
        return False, "excluida por el reglamento (no es cripto, p. ej. acción tokenizada)"
    return True, ""


def simbolos_candidatos(reg: Reglamento, exchange_info: dict[str, Any], incluir_deslistados: bool = False) -> list[str]:
    """Pares USDT que pasan el filtro por nombre. En vivo solo los que están en TRADING."""
    cot = reg.datos["universo"]["cotizacion"]
    simbolos = [s for s in exchange_info["symbols"] if s.get("quoteAsset") == cot]
    bases = {s["baseAsset"] for s in exchange_info["symbols"]}
    excluidas, _ = bstocks_detectadas(reg, exchange_info)
    out = []
    for s in simbolos:
        if not incluir_deslistados and s.get("status") != "TRADING":
            continue
        if nombre_permitido(reg, s["symbol"], bases, excluidas)[0]:
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
