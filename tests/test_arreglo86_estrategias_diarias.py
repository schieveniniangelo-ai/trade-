"""Arreglo 86 (B10): E1D, E6 y E7 con velas diarias falsas.

Propiedades: sin ver el futuro, stop debajo del precio en cada entrada, sin señales sin historia,
el filtro de BTC bloquea entradas, y la gestión que cada una declara.
"""
import numpy as np
import pandas as pd
import pytest

from sobreviviente.estrategias import ESTRATEGIAS
from sobreviviente.estrategias import e7
from sobreviviente.estrategias.base import Contexto

from test_v2 import diarias

PARAMS = {"E1D": {"donchian_n": 20, "stop_atr": 2.0, "chandelier_atr": 5.0},
          "E6": {"sma": 50, "stop_atr": 3.0},
          "E7": {"ventana": 14, "stop_atr": 3.0}}


def _ctx(df, btc="ALCISTA", moneda="ALCISTA", extra=None):
    return Contexto("XUSDT", df, pd.Series(moneda, index=df.index, dtype=object),
                    pd.Series(btc, index=df.index, dtype=object), extra or {})


def _extra_e7(df):
    lugar = pd.Series(np.where(np.arange(len(df)) % 3 == 0, 1.0, 5.0), index=df.index)
    return {"lugar_14": lugar}


def _senales(clave, df, **kw):
    extra = _extra_e7(df) if clave == "E7" else None
    return ESTRATEGIAS[clave].senales(_ctx(df, extra=extra, **kw), PARAMS[clave])


@pytest.mark.parametrize("clave", ["E1D", "E6", "E7"])
def test_hay_entradas_y_el_stop_queda_debajo_del_precio(clave):
    s = _senales(clave, diarias(600))
    e = s[s["entrada"]]
    assert len(e) >= 3
    assert (e["stop"] < e["precio"]).all()


@pytest.mark.parametrize("clave", ["E1D", "E6", "E7"])
def test_sin_ver_el_futuro(clave):
    df = diarias(600)
    completo = _senales(clave, df)
    corto = _senales(clave, df.iloc[:400])
    pd.testing.assert_frame_equal(completo.iloc[:400], corto, check_freq=False)


@pytest.mark.parametrize("clave", ["E1D", "E6"])
def test_sin_historia_no_hay_entradas(clave):
    s = _senales(clave, diarias(15))
    assert not s["entrada"].any()


def test_e1d_solo_entra_en_el_primer_dia_de_la_ruptura_y_con_tendencia():
    df = diarias(600)
    s = _senales("E1D", df)
    assert not (s["entrada"] & s["entrada"].shift(1, fill_value=False)).any()
    assert not _senales("E1D", df, moneda="LATERAL")["entrada"].any()
    assert ESTRATEGIAS["E1D"].gestion(PARAMS["E1D"]) == {"modo": "chandelier", "chandelier_atr": 5.0}


def test_e6_entra_arriba_de_la_media_y_sale_abajo():
    df = diarias(600)
    s = _senales("E6", df)
    media = df["close"].rolling(50).mean()
    assert (df.loc[s["entrada"], "close"] > media[s["entrada"]]).all()
    assert (df.loc[s["salir"], "close"] < media[s["salir"]]).all()
    assert not (s["entrada"] & s["salir"]).any()
    assert ESTRATEGIAS["E6"].gestion(PARAMS["E6"]) == {"modo": "senal_salida"}


def test_e7_solo_rebalancea_en_domingo_y_btc_bajista_saca_todo():
    df = diarias(600)
    s = _senales("E7", df)
    marcadas = s["entrada"] | s["salir"]
    assert (df.index[marcadas].day_of_week == e7.DIA_REBALANCEO).all()
    baj = _senales("E7", df, btc="BAJISTA")
    assert not baj["entrada"].any()
    assert baj["salir"].sum() == (df.index.day_of_week == e7.DIA_REBALANCEO).sum()


def test_e7_sin_lugar_no_entra():
    df = diarias(200)
    s = ESTRATEGIAS["E7"].senales(_ctx(df), PARAMS["E7"])
    assert not s["entrada"].any()


def test_e7_ranking_solo_liquidas_y_1_es_la_mas_fuerte():
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    cierres = pd.DataFrame({"A": [1, 1, 1, 1, 2.0], "B": [1, 1, 1, 1, 3.0], "C": [1, 1, 1, 1, 9.0]}, index=idx)
    liquidas = pd.DataFrame(True, index=idx, columns=["A", "B", "C"])
    liquidas["C"] = False
    r = e7.ranking(cierres, liquidas, 2)
    assert r.iloc[-1].to_dict()["B"] == 1.0 and r.iloc[-1].to_dict()["A"] == 2.0
    assert np.isnan(r.iloc[-1]["C"])
