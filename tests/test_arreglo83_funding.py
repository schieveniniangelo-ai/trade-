"""Arreglo 83: el funding de Futuros se cuenta en una sola cuenta para largos y cortos.

`simular_operacion` tenía dos ramas casi iguales (el corto cobra el funding positivo, el largo lo paga) y la del
largo no tenía prueba. Casos a mano, sin red ni llaves."""
import pandas as pd
import pytest

from sobreviviente.backtest import simular_operacion

from test_estrategias_backtest import _arr

IDX = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
# Entra en la apertura de la vela 1 (100) y sale en la vela 2 por el stop (95): 1R = 5.
VELAS = [[99, 100, 98, 100], [100, 101, 99, 100], [100, 100, 94, 96]]
SALIDA = {"modo": "chandelier", "chandelier_atr": 10}


def _largo(funding):
    return simular_operacion(_arr(VELAS), IDX, 0, "LARGO", 100.0, 95.0, None, SALIDA, 0.1, 0.0,
                             pd.Timedelta(hours=4), funding)


def test_el_largo_paga_el_funding_positivo():
    s = _largo(pd.Series([0.001], index=[IDX[2]]))
    assert s["funding_unidad"] == pytest.approx(-0.1)                  # 0.1 % de la entrada (100)
    assert s["pnl_unidad"] == pytest.approx(-5.195 - 0.1)              # el mismo caso sin funding da −5.195
    assert s["r"] == pytest.approx(-5.295 / 5)


def test_el_funding_de_la_vela_de_entrada_no_cuenta():
    # Solo cuenta el funding después de entrar y hasta la salida (incluida).
    assert _largo(pd.Series([0.001], index=[IDX[1]]))["funding_unidad"] == 0.0
    assert _largo(pd.Series(dtype=float))["funding_unidad"] == 0.0
