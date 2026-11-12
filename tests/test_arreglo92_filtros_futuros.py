"""Arreglo 92: E5 (cortos en Futuros) se dimensiona con las reglas de Binance FUTUROS, no con las de Spot.

El mínimo de la orden y el paso de cantidad de un perpetuo no son los de Spot (p. ej. BTC: 0.001 en Futuros contra
0.00001 en Spot). Con poco capital, usar los de Spot hacía pasar cortos que Binance Futuros no aceptaría.
Sin red ni llaves: filtros y cliente falsos.
"""
from types import SimpleNamespace

import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente import datos as D
from sobreviviente.exchange import Filtros

T0 = pd.Timestamp("2024-03-04 16:00", tz="UTC")
SPOT = {"SOLUSDT": Filtros("SOLUSDT", 0.01, 0.001, 0.001, 5)}
FUT = {"SOLUSDT": Filtros("SOLUSDT", 0.01, 1.0, 1.0, 5)}      # en Futuros se opera de 1 en 1


def _corto(**cambios):
    fila = dict(estrategia="E5", mercado="FUTUROS", lado="CORTO", cubeta="futuros", simbolo="SOLUSDT",
                precio_plan=100.0, stop=105.0, meta=None, fuerza=1.0, comision_pct=0.05, desliz_pct=0.0,
                regimen_btc="BAJISTA", vol_btc=50.0, vol_moneda=50.0, pnl_unidad=10.0, comision_unidad=0.1,
                stops_t=[], stops=[], entrada=100.0, t_entrada=T0, t_decision=T0, t_salida=T0 + pd.Timedelta(hours=8))
    fila.update(cambios)
    return pd.DataFrame([fila])


def test_con_46_usdt_el_corto_cabe_con_reglas_de_spot_y_no_con_las_de_futuros(reg):
    # 1 % de 46.18 = 0.4618 USDT de riesgo; stop a 5 → 0.092 SOL. Con paso de Spot (0.001) cabe; con paso 1, no.
    con_spot = B.cartera(reg, _corto(), 46.18, SPOT, ["E5"])
    assert con_spot.decisiones["aprobada"].tolist() == [True]
    assert con_spot.operaciones["cantidad"].iloc[0] == pytest.approx(0.092)
    con_fut = B.cartera(reg, _corto(), 46.18, SPOT, ["E5"], filtros_futuros=FUT)
    d = con_fut.decisiones.iloc[0]
    assert not d["aprobada"] and d["saltada_por_capital"] and "saltada por capital" in d["razon"]
    assert d["capital_necesario"] == pytest.approx(500.0)       # 1 SOL × 5 de stop ÷ 1 % de riesgo
    assert con_fut.operaciones.empty


def test_sin_reglas_de_futuros_para_esa_moneda_queda_como_antes(reg):
    antes = B.cartera(reg, _corto(), 46.18, SPOT, ["E5"])
    otro = B.cartera(reg, _corto(), 46.18, SPOT, ["E5"], filtros_futuros={"BTCUSDT": FUT["SOLUSDT"]})
    pd.testing.assert_frame_equal(antes.decisiones, otro.decisiones)
    pd.testing.assert_frame_equal(antes.operaciones, otro.operaciones)


def test_las_compras_de_spot_no_usan_las_reglas_de_futuros(reg):
    largo = _corto(estrategia="E1", mercado="SPOT", lado="LARGO", cubeta="normales", stop=95.0, comision_pct=0.1,
                   regimen_btc="ALCISTA")
    antes = B.cartera(reg, largo, 1000.0, SPOT, ["E1"])
    con = B.cartera(reg, largo, 1000.0, SPOT, ["E1"], filtros_futuros=FUT)
    pd.testing.assert_frame_equal(antes.decisiones, con.decisiones)
    pd.testing.assert_frame_equal(antes.operaciones, con.operaciones)
    assert antes.decisiones["aprobada"].tolist() == [True]


def _info_futuros():
    return {"symbols": [{"symbol": "SOLUSDT", "status": "TRADING", "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.0100"},
        {"filterType": "LOT_SIZE", "stepSize": "1", "minQty": "1"},
        {"filterType": "MARKET_LOT_SIZE", "stepSize": "1", "minQty": "1", "maxQty": "1000000"},
        {"filterType": "MIN_NOTIONAL", "notional": "5"}]}]}


def test_carga_las_reglas_de_futuros_de_la_copia(caplog):
    pedidos = []

    def exchange_info(mercado):
        pedidos.append(mercado)
        return _info_futuros()

    f = B.filtros_futuros(SimpleNamespace(exchange_info=exchange_info), ["SOLUSDT", "NOESTAUSDT"])
    assert pedidos == ["FUTUROS"] and set(f) == {"SOLUSDT"}
    assert (f["SOLUSDT"].paso, f["SOLUSDT"].cantidad_min, f["SOLUSDT"].minimo_usdt) == (1.0, 1.0, 5.0)


def test_sin_red_ni_copia_avisa_y_sigue_con_las_de_spot(caplog):
    def exchange_info(mercado):
        raise D.ErrorDatos("La API de Futuros no está disponible desde esta computadora.")

    with caplog.at_level("WARNING", logger="sobreviviente.backtest"):
        assert B.filtros_futuros(SimpleNamespace(exchange_info=exchange_info), ["SOLUSDT"]) == {}
    assert "reglas de Binance Futuros" in caplog.text
