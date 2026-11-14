"""Arreglo 113: referencias.py usa `day_of_week` (pandas marca `dayofweek` como obsoleto), como E7 en el arreglo 90.

Mismas entradas, misma salida: DCA semanal y rotación pura no cambian.
"""
import warnings

import numpy as np
import pandas as pd
import pytest
from pandas.errors import Pandas4Warning

from sobreviviente import referencias as RF


def _velas(n=120, semilla=1, inicio="2024-01-01"):
    rng = np.random.default_rng(semilla)
    idx = pd.date_range(inicio, periods=n, freq="D", tz="UTC")
    o = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame({"open": o, "close": o * (1 + rng.normal(0, 0.01, n))}, index=idx)


def _rotacion():
    spot = {s: _velas(semilla=i) for i, s in enumerate(["AAA", "BBB", "CCC"])}
    idx = spot["AAA"].index
    rng = np.random.default_rng(7)
    lugar = pd.DataFrame({s: rng.integers(1, 4, len(idx)) for s in spot}, index=idx).astype(float)
    btc = pd.Series(np.where(np.arange(len(idx)) % 30 < 20, "ALCISTA", "BAJISTA"), index=idx)
    return spot, lugar, btc, idx


def test_sin_aviso_de_nombre_obsoleto():
    df = _velas()
    spot, lugar, btc, idx = _rotacion()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Pandas4Warning)
        RF.dca_semanal(df, df.index[0], df.index[-1], 0.1)
        RF.rotacion_pura(spot, lugar, btc, 2, idx[0], idx[-1], 0.1)


@pytest.mark.parametrize("dia", [0, 3, 6])
def test_dca_compra_los_mismos_dias(dia):
    df = _velas()
    curva = RF.dca_semanal(df, df.index[0], df.index[-1], 0.1, dia=dia)
    o = df["open"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Pandas4Warning)
        viejos = o.index[o.index.dayofweek == dia]
    monto = 1.0 / len(viejos)
    efectivo, monedas, esperado = 1.0, 0.0, []
    for t, p in o.items():
        if t in viejos:
            efectivo -= monto
            monedas += monto * (1 - 0.1 / 100) / p
        esperado.append(efectivo + monedas * p)
    assert np.allclose(curva.values, esperado)


def test_rotacion_rebalancea_los_domingos():
    spot, lugar, btc, idx = _rotacion()
    curva, invertido, ops = RF.rotacion_pura(spot, lugar, btc, 2, idx[0], idx[-1], 0.1)
    assert len(curva) == len(idx) and ops > 0
    # los pesos solo cambian el día después de un domingo (apertura siguiente al rebalanceo)
    cambia = invertido.diff().abs().fillna(0) > 1e-12
    assert set(invertido.index[cambia].day_of_week) <= {0}
