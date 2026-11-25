"""Arreglo 207: los huecos de funding se cuentan con el intervalo de cada tramo (SOLO AVISOS).

Antes `huecos_funding` tomaba un solo intervalo (el más común) para toda la serie: si Binance pasaba una moneda de
cobrar cada 8 h a cada 4 h dentro de la ventana, el tramo de 8 h salía como «faltan» cobros que nunca existieron.
Ahora la serie se parte en tramos (cuando cambia la separación normal entre cobros y se sostiene al menos 3 veces
seguidas) y los huecos se cuentan con el intervalo de su tramo. Solo avisa: no cambia entradas ni compuertas.
"""
from __future__ import annotations

import pandas as pd
import pytest

from sobreviviente.futuros import datos_publicos as DP

INICIO = pd.Timestamp("2026-11-01", tz="UTC")


def _serie(primero_h: int, segundo_h: int, dias: int = 5, quitar: tuple[int, ...] = ()) -> tuple[pd.Series, pd.DatetimeIndex]:
    """`dias` días cada `primero_h` h y luego `dias` días cada `segundo_h` h. `quitar`: posiciones del segundo tramo."""
    a = pd.date_range(INICIO, INICIO + pd.Timedelta(days=dias), freq=f"{primero_h}h", inclusive="left")
    b = pd.date_range(INICIO + pd.Timedelta(days=dias), INICIO + pd.Timedelta(days=2 * dias), freq=f"{segundo_h}h",
                      inclusive="left")
    idx = a.append(b.delete(list(quitar)) if quitar else b)
    return pd.Series(0.0001, index=idx), b


def test_8h_y_luego_4h_sin_faltantes_no_cuenta_huecos():
    s, _ = _serie(8, 4)
    h = DP.huecos_funding(s)
    assert h["faltan"] == 0 and h["recibidos"] == 15 + 30 and h["esperados"] == 45
    assert h["desde"] is None and h["hasta"] is None
    assert h["intervalo_h"] == 4                                           # el del último tramo
    assert h["tramos"] == [{"desde": INICIO, "intervalo_h": 8}, {"desde": INICIO + pd.Timedelta(days=5), "intervalo_h": 4}]
    assert DP.texto_huecos("BNBUSDT", {"funding": h}) == []


def test_un_cobro_quitado_en_el_tramo_de_4h_cuenta_1():
    s, b = _serie(8, 4, quitar=(10,))
    h = DP.huecos_funding(s)
    assert h["faltan"] == 1 and h["desde"] == b[10] and h["hasta"] == b[10]
    assert h["esperados"] == 45 and h["recibidos"] == 44
    aviso = DP.texto_huecos("BNBUSDT", {"funding": h})
    assert aviso == [f"⚠️ Huecos de datos de BNBUSDT: falta 1 cobro de funding (cada 8 y luego 4 h) entre "
                     f"{b[10]:%Y-%m-%d %H:%M} y {b[10]:%Y-%m-%d %H:%M} UTC (de 45 esperados; solo aviso)."]


def test_al_reves_4h_y_luego_8h():
    s, b = _serie(4, 8)
    assert DP.huecos_funding(s)["faltan"] == 0
    s, b = _serie(4, 8, quitar=(7,))
    h = DP.huecos_funding(s)
    assert h["faltan"] == 1 and h["desde"] == b[7] and h["intervalo_h"] == 8


def test_antes_el_intervalo_unico_inventaba_huecos():
    """Con un solo intervalo (4 h, el más común) el tramo de 8 h daba 15 «faltantes» que nunca existieron."""
    s, _ = _serie(8, 4)
    horas = s.index.to_series().diff().dropna().dt.total_seconds() / 3600
    assert int(sum(round(x / 4) - 1 for x in horas)) == 15                  # lo que contaba el arreglo 203
    assert DP.huecos_funding(s)["faltan"] == 0


def test_un_solo_intervalo_sigue_igual():
    idx = pd.date_range("2026-11-01", periods=20, freq="4h", tz="UTC")
    h = DP.huecos_funding(pd.Series(0.0001, index=idx.delete([5, 6, 12])))
    assert h["intervalo_h"] == 4 and h["faltan"] == 3 and h["tramos"] == [{"desde": idx[0], "intervalo_h": 4}]


@pytest.mark.parametrize("n", [2, 3])
def test_series_cortas_usan_el_mas_comun(n):
    idx = pd.date_range("2026-11-01", periods=n, freq="8h", tz="UTC")
    h = DP.huecos_funding(pd.Series(0.0001, index=idx))
    assert h["faltan"] == 0 and h["intervalo_h"] == 8


def test_hueco_al_principio_toma_el_intervalo_del_tramo_siguiente():
    idx = pd.date_range("2026-11-01", periods=12, freq="4h", tz="UTC")
    h = DP.huecos_funding(pd.Series(0.0001, index=idx.delete([1])))
    assert h["faltan"] == 1 and h["desde"] == idx[1] and h["intervalo_h"] == 4
