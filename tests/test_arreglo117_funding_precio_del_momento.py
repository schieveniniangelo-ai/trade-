"""Arreglo 117 (F1): cada cobro de funding se multiplica por el precio de ESA hora, no por el de la entrada.

Binance cobra el funding sobre el valor de la posición en ese momento (precio de marca × cantidad). Antes se hacía
suma de tasas × precio de entrada. Ahora, con `precio_funding` (cierre de la vela de 1 h de Futuros, con índice = hora
de cierre), cada cobro va por el último precio conocido a su hora. Sin esa serie (o antes de que empiece) se usa la
entrada, como antes: los motores diarios y las pruebas viejas no cambian.

Caso de la tanda: corto de 30 días, el precio baja 30 % en línea recta desde 100, +0.01 % cada 8 h (90 cobros).
Antes: 90 × 0.0001 × 100 = 0.9 por unidad. Con el precio de cada cobro: 0.0001 × Σ 100·(1 − 0.3·8k/720) = 0.7635.
La función de antes sobrestima 17.9 % (la tanda calculó 0.8985 contra 0.7672, 17.1 %, con otra entrada).
"""
import numpy as np
import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente.backtest import simular_operacion

H = pd.Timedelta(hours=1)
H4 = pd.Timedelta(hours=4)
T0 = pd.Timestamp("2024-03-01", tz="UTC")
ENTRA = T0 + H4                                   # señal al cierre de la vela 0; entra en la apertura de la 1
SALIDA = {"modo": "chandelier", "chandelier_atr": 1000}   # el stop nunca se toca


def _precio(t):
    return 100.0 * (1 - 0.3 * ((t - ENTRA) / H) / 720)


def _caso():
    idx = pd.date_range(T0, periods=181, freq="4h", tz="UTC")
    filas = [[100.0, 100.0, 100.0, 100.0]]
    for t in idx[1:]:
        a, c = _precio(t), _precio(t + H4)
        filas.append([a, a, c, c])
    x = np.array(filas)
    arr = {"o": x[:, 0], "h": x[:, 1], "l": x[:, 2], "c": x[:, 3], "atr": np.ones(len(x))}
    cobros = pd.Series(0.0001, index=[ENTRA + 8 * k * H for k in range(1, 91)])
    horas = pd.date_range(ENTRA + H, ENTRA + 720 * H, freq="1h", tz="UTC")
    precio_1h = pd.Series([_precio(t) for t in horas], index=horas)     # índice = hora de cierre de la vela de 1 h
    return arr, idx, cobros, precio_1h


def _corto(precio_funding=None, cobros=None):
    arr, idx, c, p = _caso()
    return simular_operacion(arr, idx, 0, "CORTO", 100.0, 200.0, None, SALIDA, 0.0, 0.0, H4,
                             c if cobros is None else cobros, precio_funding=precio_funding)


def test_caso_de_la_tanda_30_dias_baja_30():
    arr, idx, cobros, precio_1h = _caso()
    antes = _corto()
    ahora = _corto(precio_1h)
    assert antes["abierta"] and ahora["abierta"] and antes["entrada"] == 100.0
    assert antes["funding_unidad"] == pytest.approx(0.9)
    assert ahora["funding_unidad"] == pytest.approx(0.7635)
    assert antes["funding_unidad"] / ahora["funding_unidad"] - 1 == pytest.approx(0.1788, abs=1e-4)
    # lo demás de la operación es idéntico: solo cambia el funding
    assert ahora["pnl_unidad"] - antes["pnl_unidad"] == pytest.approx(0.7635 - 0.9)
    for k in ("entrada", "salida", "motivo", "velas", "comision_unidad", "t_salida"):
        assert ahora[k] == antes[k]


def test_el_largo_paga_con_el_precio_del_momento():
    idx = pd.date_range(T0, periods=3, freq="4h", tz="UTC")
    arr = {"o": np.array([100.0, 100.0, 120.0]), "h": np.array([100.0, 100.0, 120.0]),
           "l": np.array([100.0, 100.0, 120.0]), "c": np.array([100.0, 120.0, 120.0]), "atr": np.ones(3)}
    cobros = pd.Series({idx[1] + 2 * H: 0.001, idx[2] + 3 * H: 0.001})
    precio = pd.Series({idx[1] + 2 * H: 110.0, idx[2] + H: 120.0})       # el segundo usa el último conocido (120)
    s = simular_operacion(arr, idx, 0, "LARGO", 100.0, 50.0, None, SALIDA, 0.0, 0.0, H4, cobros,
                          precio_funding=precio)
    assert s["funding_unidad"] == pytest.approx(-(0.001 * 110 + 0.001 * 120))


def test_sin_precio_a_esa_hora_usa_la_entrada():
    _, _, cobros, precio_1h = _caso()
    tarde = precio_1h[precio_1h.index > ENTRA + 400 * H]            # la serie empieza tarde
    s = _corto(tarde)
    esperado = sum(0.0001 * (_precio(t) if t >= tarde.index[0] else 100.0) for t in cobros.index)
    assert s["funding_unidad"] == pytest.approx(esperado)
    assert _corto(pd.Series(dtype=float))["funding_unidad"] == pytest.approx(0.9)     # serie vacía: como antes


def test_milisegundos_de_binance_toman_el_precio_de_su_hora():
    _, _, _, precio_1h = _caso()
    cobros = pd.Series({ENTRA + 8 * H + pd.Timedelta(milliseconds=3): 0.0001})
    assert _corto(precio_1h, cobros)["funding_unidad"] == pytest.approx(0.0001 * _precio(ENTRA + 8 * H))


def test_el_mercado_guarda_el_cierre_de_1h_de_futuros_por_hora_de_cierre():
    assert "precio_funding" in B.Mercado.__dataclass_fields__
