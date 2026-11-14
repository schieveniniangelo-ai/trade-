"""Arreglo 118 (F2): de cuántas horas es cada cobro de funding, y la tasa llevada a 8 h.

Binance cobra el funding cada 8, 4, 2 o 1 h y lo cambia sola (si un cobro toca el tope, la moneda pasa a cada hora;
anuncio vigente desde 2025-05-02). `intervalo_funding(serie)`: horas desde el cobro anterior, redondeadas a 1, 2, 4
u 8; el primero toma el intervalo del siguiente. `funding_por_8h(serie)` = tasa × 8 ÷ horas. Solo informa: la señal
de E5 no cambia (sigue comparando la tasa de cada cobro, ver Hipótesis 001).
"""
import inspect

import numpy as np
import pandas as pd
import pytest

from sobreviviente import datos as D
from sobreviviente.estrategias import e5


def _serie():
    t0 = pd.Timestamp("2025-05-01", tz="UTC")
    horas = [0, 8, 16, 24, 28, 32, 36, 37, 38, 39]        # 8 h → 4 h → 1 h
    idx = [t0 + pd.Timedelta(hours=h) for h in horas]
    idx[4] += pd.Timedelta(milliseconds=3)                 # Binance a veces anota milisegundos tarde
    return pd.Series([0.0001, 0.0001, 0.0001, 0.0002, 0.0002, 0.0002, -0.003, -0.003, 0.0001, 0.0001], index=idx)


def test_intervalo_pasa_de_8_a_4_y_a_1_hora():
    iv = D.intervalo_funding(_serie())
    assert list(iv) == [8, 8, 8, 8, 4, 4, 4, 1, 1, 1]
    assert iv.index.equals(_serie().index)


def test_funding_por_8h():
    f8 = D.funding_por_8h(_serie())
    assert list(f8.round(10)) == pytest.approx([0.0001, 0.0001, 0.0001, 0.0002, 0.0004, 0.0004, -0.006,
                                                -0.024, 0.0008, 0.0008])


def test_redondea_a_1_2_4_u_8():
    t0 = pd.Timestamp("2025-01-01", tz="UTC")
    huecos = [0, 2.2, 1.6, 6.5, 3.4, 11, 30]               # un hueco largo de datos se toma como 8 h
    idx = [t0 + pd.Timedelta(hours=h) for h in np.cumsum(huecos)]
    assert list(D.intervalo_funding(pd.Series(0.0, index=idx))) == [2, 2, 2, 8, 4, 8, 8]


def test_casos_cortos():
    assert D.intervalo_funding(pd.Series(dtype=float)).empty and D.funding_por_8h(pd.Series(dtype=float)).empty
    uno = pd.Series([0.0003], index=[pd.Timestamp("2025-01-01", tz="UTC")])
    assert list(D.intervalo_funding(uno)) == [8] and list(D.funding_por_8h(uno)) == [0.0003]
    desordenada = _serie().iloc[::-1]
    assert D.intervalo_funding(desordenada).sort_index().tolist() == [8, 8, 8, 8, 4, 4, 4, 1, 1, 1]   # mismo orden que la entrada


def test_docstring_de_funding_historico_corregida():
    doc = D.ClienteBinance.funding_historico.__doc__
    assert "1, 2, 4 u 8 h" in doc and "periodo de 8 h)" not in doc


def test_e5_no_usa_el_intervalo():
    fuente = inspect.getsource(e5)
    assert "intervalo_funding" not in fuente and "funding_por_8h" not in fuente
