"""Arreglo 148: backtest.simular_operacion acepta la liquidación OFICIAL (precio_liq) y la tarifa de liquidación.

Sin esos parámetros todo queda EXACTAMENTE como antes (las pruebas viejas no cambian)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sobreviviente import backtest as B

IDX = pd.date_range("2026-01-01", periods=6, freq="4h", tz="UTC")
GEST = {"modo": "chandelier", "chandelier_atr": 3.0, "sin_breakeven": True}


def _arr(o, h, l, c, mh=None, ml=None):
    a = {"o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float),
         "atr": np.full(len(o), 30.0)}   # ATR grande: el chandelier no se acerca en estas pocas velas
    if mh is not None:
        a["marca_h"], a["marca_l"] = np.array(mh, float), np.array(ml, float)
    return a


def _sim(arr, lado="LARGO", stop=80.0, **kw):
    return B.simular_operacion(arr, IDX, 0, lado, 100.0, stop, None, GEST, 0.05, 0.0, pd.Timedelta(hours=4), **kw)


def test_sin_parametros_nuevos_nada_cambia():
    arr = _arr([100] * 6, [101] * 6, [99, 99, 99, 79, 99, 99], [100] * 6, [101] * 6, [99, 99, 99, 40, 99, 99])
    viejo = _sim(arr, apalancamiento=2.0, mantenimiento_pct=0.5)
    nuevo = _sim(arr, apalancamiento=2.0, mantenimiento_pct=0.5, precio_liq=None, tarifa_liq_pct=0.0)
    assert viejo == nuevo
    assert viejo["liquidada"] is False and viejo["motivo"] == "stop"   # el stop (80) sale antes de la liquidación


def test_liquidacion_pierde_el_margen_mas_la_tarifa():
    # El stop está lejos (10) y la marca baja a 45 en la vela 3: con la liquidación oficial en 50, se liquida.
    arr = _arr([100] * 6, [101] * 6, [99, 99, 99, 60, 99, 99], [100] * 6, [101] * 6, [99, 99, 99, 45, 99, 99])
    r = _sim(arr, stop=10.0, apalancamiento=2.0, precio_liq=50.0, tarifa_liq_pct=1.25)
    assert r["liquidada"] is True and r["motivo"] == "liquidación"
    entrada = 100.0
    margen = entrada / 2.0
    tarifa = 50.0 * 1.25 / 100.0                # sobre el nocional a la hora de la liquidación
    comision = entrada * 0.05 / 100.0
    assert r["pnl_unidad"] == pytest.approx(-margen - tarifa - comision)
    assert r["tarifa_liq_unidad"] == pytest.approx(tarifa)


def test_la_liquidacion_oficial_manda_sobre_la_estimada():
    # Marca baja a 52: con la estimación vieja (50.5) no se liquidaría; con la oficial en 55, sí.
    arr = _arr([100] * 6, [101] * 6, [99, 99, 99, 60, 99, 99], [100] * 6, [101] * 6, [99, 99, 99, 52, 99, 99])
    assert _sim(arr, stop=10.0, apalancamiento=2.0)["liquidada"] is False
    assert _sim(arr, stop=10.0, apalancamiento=2.0, precio_liq=55.0)["liquidada"] is True


def test_corto_liquidado_y_signo_del_funding():
    arr = _arr([100] * 6, [101, 101, 101, 140, 101, 101], [99] * 6, [100] * 6,
               [101, 101, 101, 160, 101, 101], [99] * 6)
    fund = pd.Series([0.001], index=[IDX[2]])     # funding positivo: el corto COBRA (backtest: signo +1 en corto)
    r = _sim(arr, lado="CORTO", stop=190.0, apalancamiento=1.0, precio_liq=150.0, tarifa_liq_pct=1.5, funding=fund)
    assert r["liquidada"] is True
    assert r["funding_unidad"] == pytest.approx(0.001 * 100.0)
    assert r["pnl_unidad"] == pytest.approx(-100.0 - 150.0 * 1.5 / 100 - 100.0 * 0.05 / 100 + 0.1)
    largo = _sim(_arr([100] * 6, [101] * 6, [99] * 6, [100] * 6), funding=fund)
    assert largo["funding_unidad"] == pytest.approx(-0.1)    # el largo paga


def test_sin_marca_no_se_revisa_y_sin_apalancamiento_falla():
    arr = _arr([100] * 6, [101] * 6, [99] * 6, [100] * 6)
    assert "liquidada" not in _sim(arr, apalancamiento=2.0, precio_liq=50.0)
    arr_m = _arr([100] * 6, [101] * 6, [99] * 6, [100] * 6, [101] * 6, [99] * 6)
    with pytest.raises(ValueError):
        _sim(arr_m, precio_liq=50.0)
