"""Arreglo 120 (F4): la simulación revisa la liquidación con el precio de MARCA (informativo).

Antes `simular_operacion` nunca la revisaba. Ahora, si trae las velas de marca (`marca_h`, `marca_l`) y el
apalancamiento, calcula la liquidación estimada con `riesgo.precio_liquidacion` (la misma fórmula de siempre; la
oficial de Binance queda como DECISIÓN DE ÁNGELO). Si la marca la cruza antes de que salga el stop, la operación
queda con liquidada=True y pierde el margen aislado completo (entrada ÷ apalancamiento; de ahí sale la comisión de
liquidación), más la comisión de entrada, más el funding que ya llevaba. Sin velas de marca no cambia nada.
"""
import numpy as np
import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente import regimen as RG
from sobreviviente import riesgo as R
from sobreviviente.backtest import simular_operacion

from test_estrategias_backtest import velas_sinteticas

IDX = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
H4 = pd.Timedelta(hours=4)
SALIDA = {"modo": "chandelier", "chandelier_atr": 1000}


def _arr(vela_2, marca_2=None):
    filas = [[101, 101, 99, 100], [100, 101, 99, 100], vela_2]
    a = np.array(filas, dtype=float)
    arr = {"o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3], "atr": np.ones(3)}
    if marca_2 is not None:
        m = np.array(filas[:2] + [marca_2], dtype=float)
        arr["marca_h"], arr["marca_l"] = m[:, 1], m[:, 2]
    return arr


def _corto(arr, stop, apal, funding=None):
    return simular_operacion(arr, IDX, 0, "CORTO", 100.0, stop, None, SALIDA, 0.05, 0.0, H4, funding,
                             apalancamiento=apal, mantenimiento_pct=0.5)


def test_e5_con_2x_y_colchon_2_el_stop_sale_antes():
    # liquidación estimada del corto con 2x: 100 × (1 + 1/2 − 0.005) = 149.5; stop a 5 % (colchón ~9.9)
    assert R.precio_liquidacion(100.0, "CORTO", 2, 0.5) == pytest.approx(149.5)
    vela = [100, 160, 99, 150]                                      # sube hasta 160: toca el stop y la liquidación
    s = _corto(_arr(vela, vela), 105.0, 2)
    assert s["motivo"] == "stop" and s["liquidada"] is False and s["salida"] == 105.0
    sin_marca = _corto(_arr(vela), 105.0, 2)
    assert "liquidada" not in sin_marca                             # sin velas de marca: como antes
    assert {k: v for k, v in s.items() if k != "liquidada"} == sin_marca


def test_10x_la_marca_cruza_la_liquidacion_antes_del_stop():
    # 10x: liquidación 100 × (1 + 0.1 − 0.005) = 109.5; el stop en 115 queda más lejos
    s = _corto(_arr([100, 112, 99, 111], [100, 112, 99, 111]), 115.0, 10, pd.Series({IDX[2]: 0.001}))
    assert s["liquidada"] is True and s["motivo"] == "liquidación" and s["salida"] == pytest.approx(109.5)
    margen, comision_entrada, funding = 100.0 / 10, 100.0 * 0.0005, 0.1
    assert s["funding_unidad"] == pytest.approx(funding)
    assert s["pnl_unidad"] == pytest.approx(-margen - comision_entrada + funding)
    assert s["comision_unidad"] == pytest.approx(comision_entrada)
    assert s["r"] == pytest.approx(s["pnl_unidad"] / 15.0)
    assert not s["abierta"] and s["velas"] == 2


def test_la_marca_manda_aunque_el_ultimo_precio_no_llegue():
    s = _corto(_arr([100, 108, 99, 107], [100, 110, 99, 108]), 115.0, 10)
    assert s["liquidada"] is True
    s2 = _corto(_arr([100, 110, 99, 108], [100, 108, 99, 107]), 115.0, 10)
    assert s2["liquidada"] is False and s2["abierta"]               # el último precio sí, la marca no: sigue


def test_hueco_mas_alla_de_la_liquidacion_liquida():
    s = _corto(_arr([120, 121, 118, 119], [120, 121, 118, 119]), 105.0, 10)
    assert s["liquidada"] is True                                   # abre arriba de 109.5: no hubo stop a tiempo


def test_el_largo_se_liquida_con_el_minimo_de_la_marca():
    arr = {"o": np.array([99.0, 100, 100]), "h": np.array([100.0, 101, 100]), "l": np.array([98.0, 99, 89]),
           "c": np.array([100.0, 100, 90]), "atr": np.ones(3),
           "marca_h": np.array([100.0, 101, 100]), "marca_l": np.array([98.0, 99, 89])}
    s = simular_operacion(arr, IDX, 0, "LARGO", 100.0, 80.0, None, SALIDA, 0.05, 0.0, H4,
                          apalancamiento=10, mantenimiento_pct=0.5)
    assert s["liquidada"] is True and s["salida"] == pytest.approx(100 * (1 - 0.1 + 0.005))


def test_e5_en_el_backtest_trae_la_marca_y_no_se_liquida_con_2x(reg):
    """Mercado falso de Futuros con BTC bajista: las señales de E5 se simulan con la marca (= velas de Futuros)."""
    B._CTX_CACHE.clear()
    try:
        f1 = velas_sinteticas(6000, semilla=3, tendencia=-0.0004, onda=0.004)
        f4 = B.D.resamplear(f1, "4h")
        dias = pd.date_range("2023-01-01", periods=260, freq="D", tz="UTC")
        reg4 = RG.tendencia(f4, reg)
        m = B.Mercado(reg=reg, spot1h={}, spot4h={"BTCUSDT": f4, "XUSDT": f4}, fut4h={"XUSDT": f4},
                      funding={"XUSDT": pd.Series(0.0001, index=pd.date_range("2023-01-01", periods=780, freq="8h",
                                                                               tz="UTC"))},
                      volumen=pd.DataFrame(), pertenece=pd.DataFrame(True, index=dias, columns=["XUSDT"]),
                      vol_mediano=pd.DataFrame(1e9, index=dias, columns=["XUSDT"]),
                      fut_liquido=pd.DataFrame(True, index=dias, columns=["XUSDT"]),
                      btc_reg4h=reg4, btc_vol4h=RG.percentil_volatilidad(f4, reg))
        m.reg4h["XUSDT"], m.vol4h["XUSDT"] = reg4, RG.percentil_volatilidad(f4, reg)
        m.marca4h["XUSDT"] = f4
        m.precio_funding["XUSDT"] = pd.Series(f1["close"].values, index=f1.index + pd.Timedelta(hours=1))
        cands = B.generar_candidatos(m, "E5", reg.estrategias["E5"]["parametros"], "2023-02-01", "2023-09-01",
                                     procesos=1)
        del m.marca4h["XUSDT"]
        B._CTX_CACHE.clear()
        sin_marca = B.generar_candidatos(m, "E5", reg.estrategias["E5"]["parametros"], "2023-02-01", "2023-09-01",
                                         procesos=1)
    finally:
        B._CTX_CACHE.clear()
    assert len(cands) > 0 and "liquidada" in cands and not cands["liquidada"].any()
    assert "liquidada" not in sin_marca
    pd.testing.assert_frame_equal(cands.drop(columns="liquidada"), sin_marca)


def test_series_marca_usa_la_marca_si_esta_en_la_cache(tmp_path):
    from types import SimpleNamespace
    cli = SimpleNamespace(cache=tmp_path)
    f1 = velas_sinteticas(48, semilla=2)
    precio, marca = B.series_marca(cli, "XUSDT", f1)
    assert marca is None                                             # sin marca: cierre de Futuros, sin liquidación
    assert precio.index[0] == f1.index[0] + pd.Timedelta(hours=1) and precio.iloc[0] == f1["close"].iloc[0]
    m1 = f1.copy()
    m1[["open", "high", "low", "close"]] *= 1.01
    B.D.guardar(m1, B.D.ruta_marca(cli, "XUSDT"))
    precio, marca = B.series_marca(cli, "XUSDT", f1)
    assert precio.iloc[0] == pytest.approx(f1["close"].iloc[0] * 1.01)
    assert len(marca) == 12 and marca["high"].iloc[0] == pytest.approx(m1["high"].iloc[:4].max())
