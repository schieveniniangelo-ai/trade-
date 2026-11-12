"""Arreglo 93: el funding de un corto de Futuros solo cuenta mientras la posición seguro estaba abierta.

Binance anota muchas horas de funding unos milisegundos tarde (20:00:00.003 en vez de 20:00). Se comparan sin los
milisegundos. Cuenta el funding después de entrar (la entrada va después de la foto de esa hora) y hasta la apertura
de la vela de salida; si el stop salta dentro de la vela, el del cierre de esa vela ya no toca. Si la posición
sigue abierta al final de los datos, cuenta hasta el último cierre. Casos a mano de un corto (E5), sin red.
"""
import pandas as pd
import pytest

from sobreviviente.backtest import simular_operacion

from test_estrategias_backtest import _arr

IDX = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
H4 = pd.Timedelta(hours=4)
MS = pd.Timedelta(milliseconds=1)
SALIDA = {"modo": "chandelier", "chandelier_atr": 10}          # el stop no se mueve en estos casos
# Señal al cierre de la vela 0 (100); vende en la apertura de la vela 1 (100); stop en 105 (1R = 5).
ENTRA = [[101, 101, 99, 100], [100, 101, 99, 100]]


def _corto(vela_2, funding):
    return simular_operacion(_arr(ENTRA + [vela_2]), IDX, 0, "CORTO", 100.0, 105.0, None, SALIDA, 0.05, 0.0, H4,
                             pd.Series(funding))


STOP_DENTRO = [100, 106, 99, 104]      # el máximo toca el stop (105) dentro de la vela 2
HUECO = [107, 108, 106, 107]           # abre arriba del stop: sale en la apertura (107)
SIGUE = [100, 101, 98, 99]             # nunca toca el stop: sigue abierta al final


def test_el_funding_del_instante_de_entrada_no_cuenta_aunque_venga_con_milisegundos():
    s = _corto(STOP_DENTRO, {IDX[1] + 3 * MS: 0.001})
    assert s["funding_unidad"] == 0.0
    assert s["pnl_unidad"] == pytest.approx(100 - 105 - (100 + 105) * 0.0005)   # el resto de la operación, igual


def test_si_el_stop_salta_dentro_de_la_vela_el_funding_del_cierre_ya_no_toca():
    s = _corto(STOP_DENTRO, {IDX[2] + H4: 0.001})
    assert s["motivo"] == "stop" and s["funding_unidad"] == 0.0


def test_el_funding_de_la_apertura_de_la_vela_de_salida_si_cuenta():
    s = _corto(STOP_DENTRO, {IDX[2] + 5 * MS: 0.001})
    assert s["funding_unidad"] == pytest.approx(0.1)                # el corto cobra: 0.1 % de la entrada (100)


def test_salida_por_hueco_cuenta_el_de_esa_apertura_y_no_el_del_cierre():
    s = _corto(HUECO, {IDX[2]: 0.001, IDX[2] + H4: 0.002})
    assert s["motivo"] == "stop (hueco)" and s["funding_unidad"] == pytest.approx(0.1)


def test_si_sigue_abierta_al_final_cuenta_hasta_el_ultimo_cierre():
    s = _corto(SIGUE, {IDX[2] + H4 + 2 * MS: 0.001})
    assert s["abierta"] and s["funding_unidad"] == pytest.approx(0.1)


def test_el_largo_paga_con_la_misma_ventana():
    s = simular_operacion(_arr([[99, 100, 98, 100], [100, 101, 99, 100], [100, 100, 94, 96]]), IDX, 0, "LARGO",
                          100.0, 95.0, None, SALIDA, 0.1, 0.0, H4,
                          pd.Series({IDX[1] + MS: 0.001, IDX[2] + MS: 0.001, IDX[2] + H4: 0.001}))
    assert s["funding_unidad"] == pytest.approx(-0.1)                 # solo el de la apertura de la vela de salida
