"""Arreglo 90: E7 usa `day_of_week` (pandas marca `dayofweek` como obsoleto). Mismas entradas, misma salida."""
import warnings

import pandas as pd
import pytest
from pandas.errors import Pandas4Warning

from sobreviviente.estrategias import e7
from sobreviviente.estrategias.base import salida

from test_arreglo86_estrategias_diarias import PARAMS, _ctx, _extra_e7
from test_v2 import diarias


def _senales_con_dayofweek(ctx, p):
    """La fórmula de E7 de antes del arreglo, con el nombre viejo `dayofweek`."""
    v = ctx.velas
    lugar = ctx.extra[f"lugar_{int(p['ventana'])}"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Pandas4Warning)
        rebalanceo = pd.Series(v.index.dayofweek == e7.DIA_REBALANCEO, index=v.index)
    en_top = lugar <= e7.TOP
    btc_ok = ctx.regimen_btc != "BAJISTA"
    stop = v["close"] - float(p["stop_atr"]) * ctx.atr()
    return salida(ctx, rebalanceo & en_top & btc_ok, stop, None, -lugar, rebalanceo & (~en_top | ~btc_ok))


def test_e7_no_usa_el_nombre_obsoleto():
    df = diarias(120)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Pandas4Warning)
        e7.senales(_ctx(df, extra=_extra_e7(df)), PARAMS["E7"])


@pytest.mark.parametrize("btc", ["ALCISTA", "BAJISTA"])
def test_e7_salida_identica_con_los_dos_nombres(btc):
    df = diarias(600)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Pandas4Warning)
        assert (df.index.dayofweek == df.index.day_of_week).all()
    nueva = e7.senales(_ctx(df, btc=btc, extra=_extra_e7(df)), PARAMS["E7"])
    vieja = _senales_con_dayofweek(_ctx(df, btc=btc, extra=_extra_e7(df)), PARAMS["E7"])
    assert nueva["entrada"].any() or btc == "BAJISTA"
    assert nueva["salir"].any()
    pd.testing.assert_frame_equal(nueva, vieja)
