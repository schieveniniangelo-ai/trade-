"""Pruebas de las reglas de Binance (filtros y redondeos)."""
from sobreviviente.exchange import (
    filtros_desde_exchangeinfo, filtros_supuestos, redondear_abajo, redondear_arriba, redondear_precio,
)


def test_filtros_spot():
    info = {
        "symbol": "BTCUSDT", "status": "TRADING",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001"},
            {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.00000000"},
            {"filterType": "NOTIONAL", "minNotional": "5.0"},
        ],
    }
    f = filtros_desde_exchangeinfo(info)
    assert (f.tick, f.paso, f.cantidad_min, f.minimo_usdt) == (0.01, 0.00001, 0.00001, 5.0)
    assert not f.supuesto


def test_filtros_futuros_y_valores_raros():
    info = {"symbol": "ETHUSDT", "filters": [
        {"filterType": "MIN_NOTIONAL", "notional": "20"},
        {"filterType": "LOT_SIZE", "stepSize": "abc", "minQty": None},
    ]}
    f = filtros_desde_exchangeinfo(info)
    assert f.minimo_usdt == 20 and f.paso == 0 and f.estado == "TRADING"


def test_redondeos():
    assert redondear_abajo(0.123456, 0.001) == 0.123
    assert redondear_abajo(0.3, 0.1) == 0.3  # sin error de punto flotante
    assert redondear_arriba(0.1231, 0.001) == 0.124
    assert redondear_abajo(5.5, 0) == 5.5 and redondear_arriba(5.5, 0) == 5.5
    assert redondear_precio(101.239, 0.01) == 101.23
    assert redondear_precio(101.231, 0.01, "arriba") == 101.24


def test_filtros_supuestos():
    f = filtros_supuestos("OLDUSDT", 25000.0, 5.0)
    assert f.supuesto and f.tick == 1.0 and f.paso == 1e-7
    g = filtros_supuestos("MEMEUSDT", 0.00001, 1.0)
    assert g.paso == 1000 and g.minimo_usdt == 1.0
    h = filtros_supuestos("Z", 0, 5)
    assert h.tick > 0
