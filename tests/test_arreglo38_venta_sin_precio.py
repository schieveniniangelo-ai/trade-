"""Arreglo 38: un CERRAR a mercado no se bloquea si no se puede leer el precio, y usa el paso de mercado de Binance."""
import test_arreglo34_verificar_completo as T34

PASO_MERCADO = {"filterType": "MARKET_LOT_SIZE", "minQty": "0", "maxQty": "1000", "stepSize": "0.001"}


def test_precio_promedio_caido_da_ok_con_aviso(reg, tmp_path, monkeypatch, capsys):
    codigo, salida = T34._verificar(reg, tmp_path, monkeypatch, capsys, T34._base("CERRAR"), precio=None)
    assert codigo == 0 and "✅" in salida and "❌" not in salida
    assert "⚠️ no pude leer el precio para revisar el mínimo; revísalo a mano" in salida


def test_cantidad_fuera_del_paso_de_mercado(reg, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(T34, "FILTROS", T34.FILTROS + [PASO_MERCADO])
    b = T34._base("CERRAR")                                  # vende 0.0044: múltiplo de 0.0001, pero no de 0.001
    codigo, salida = T34._verificar(reg, tmp_path, monkeypatch, capsys, b)
    assert codigo == 1 and "❌" in salida and "paso de Binance para órdenes a mercado" in salida


def test_cantidad_en_el_paso_de_mercado(reg, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(T34, "FILTROS", T34.FILTROS + [PASO_MERCADO])
    b = T34._base("CERRAR")
    b.update({"cantidad": 0.0041, "cantidad_stop": 0.004})
    codigo, salida = T34._verificar(reg, tmp_path, monkeypatch, capsys, b)
    assert codigo == 0 and "✅" in salida
