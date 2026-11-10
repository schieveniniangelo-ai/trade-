"""Arreglo 40: una venta a mercado debe cumplir el paso de LOT_SIZE y, si existe, también el de MARKET_LOT_SIZE."""
import test_arreglo34_verificar_completo as T34
from sobreviviente.exchange import filtros_desde_exchangeinfo


def _filtros(lote, mercado=None, min_mkt="0", max_mkt="1000"):
    f = [{"filterType": "PRICE_FILTER", "tickSize": "0.01"},
         {"filterType": "LOT_SIZE", "stepSize": lote, "minQty": "0.001"},
         {"filterType": "NOTIONAL", "minNotional": "1"}]
    if mercado:
        f.append({"filterType": "MARKET_LOT_SIZE", "stepSize": mercado, "minQty": min_mkt, "maxQty": max_mkt})
    return f


def _venta(reg, tmp_path, monkeypatch, capsys, filtros, cantidad, **kw):
    monkeypatch.setattr(T34, "FILTROS", filtros)
    b = T34._base("CERRAR")
    b.update({"cantidad": cantidad, "cantidad_stop": cantidad})
    return T34._verificar(reg, tmp_path, monkeypatch, capsys, b, **kw)


def test_fuera_del_paso_de_lote_aunque_cumpla_el_de_mercado(reg, tmp_path, monkeypatch, capsys):
    codigo, salida = _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.01", "0.001"), 0.105)
    assert codigo == 1 and "paso de Binance (LOT_SIZE)" in salida and "MARKET_LOT_SIZE)" not in salida


def test_fuera_del_paso_de_mercado(reg, tmp_path, monkeypatch, capsys):
    codigo, salida = _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.001", "0.01"), 0.105)
    assert codigo == 1 and "para órdenes a mercado (MARKET_LOT_SIZE)" in salida and "(LOT_SIZE)" not in salida


def test_cumple_los_dos_pasos(reg, tmp_path, monkeypatch, capsys):
    codigo, salida = _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.01", "0.001"), 0.11)
    assert codigo == 0 and "✅" in salida


def test_sin_market_lot_size_igual_que_antes(reg, tmp_path, monkeypatch, capsys):
    assert _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.001"), 0.105)[0] == 0
    codigo, salida = _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.01"), 0.105)
    assert codigo == 1 and "paso de Binance (LOT_SIZE)" in salida


def test_maximo_y_minimo_de_mercado(reg, tmp_path, monkeypatch, capsys):
    f = filtros_desde_exchangeinfo({"symbol": "ETHUSDT", "filters": _filtros("0.001", "0.001", "0.05", "0.1")})
    assert f.cantidad_min_mercado == 0.05 and f.cantidad_max_mercado == 0.1
    codigo, salida = _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.001", "0.001", "0.05", "0.1"), 0.11)
    assert codigo == 1 and "MARKET_LOT_SIZE maxQty" in salida
    codigo, salida = _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.001", "0.001", "0.05", "0.1"), 0.04)
    assert codigo == 1 and "MARKET_LOT_SIZE minQty" in salida


def test_precio_promedio_caido_sigue_solo_avisando(reg, tmp_path, monkeypatch, capsys):
    codigo, salida = _venta(reg, tmp_path, monkeypatch, capsys, _filtros("0.01", "0.001"), 0.11, precio=None)
    assert codigo == 0 and "⚠️ no pude leer el precio para revisar el mínimo; revísalo a mano" in salida
    assert "❌" not in salida
