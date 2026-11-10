"""Arreglo 33: Binance Spot cobra la comisión en la moneda comprada; el stop y la venta van por la cantidad NETA."""
from sobreviviente import papel as P
from sobreviviente import riesgo as R
from sobreviviente.exchange import Filtros

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _boleto(accion, **kw):
    b = {"boleto_id": "20261109-C-X-ETHUSDT-M0", "accion": accion, "simbolo": "ETHUSDT", "cantidad": 0.0531,
         "cantidad_stop": R.cantidad_neta(0.0531, 0.1, 0.0001), "paso_cantidad": 0.0001, "tick_precio": 0.01,
         "precio_entrada": 3000.0, "stop": 2550.0, "precio_limite_stop": 2537.25, "id_stop": "x-s0",
         "stop_anterior": 2500.0, "precio_limite_stop_anterior": 2487.5, "tipo_orden": "MARKET", "razon": "salida"}
    b.update(kw)
    return b


def test_compra_de_0_0531_da_neta_0_0530_en_el_stop():
    assert R.cantidad_neta(0.0531, 0.1, 0.0001) == 0.053
    texto = P.texto_boleto(_boleto("COMPRAR"))
    assert "COMPRAR 0.0531 ETHUSDT" in texto                       # la compra sigue siendo la cantidad bruta
    assert "VENTA de 0.053 ETHUSDT: stop 2550" in texto              # el stop va por la neta
    assert "Después de la compra tendrás 0.053 ETH" in texto and "commissionAsset" in texto
    assert "el stop se pone por esa cantidad" in texto
    assert "VENTA de 0.053 ETHUSDT" in P.texto_boleto(_boleto("MODIFICAR_STOP"))
    assert "VENDER 0.053 ETHUSDT a MERCADO" in P.texto_boleto(_boleto("CERRAR"))


def test_compra_de_exactamente_minqty_no_se_aprueba():
    f = Filtros("ETHUSDT", 0.01, 0.0001, 0.0531, 1.0)
    c = R.Candidato("ETHUSDT", "SPOT", "LARGO", "M0", "normales", 100.0, 90.0, precio_limite_stop=89.0)
    t = R.calcular_tamano(1000, 1.0, 1.0, c, f, 5.315, "riesgo", comision_en_moneda_pct=0.1)   # compra = 0.0531 = minQty
    assert not t.ok and "no llega al mínimo" in t.razon                                       # neta 0.0530 < minQty
    assert R.calcular_tamano(1000, 1.0, 1.0, c, f, 5.315, "riesgo").ok                          # sin comisión en la moneda


def _compra_c(reg, carpeta, en_moneda: bool):
    r = _reg_m0(reg, carpeta).copia_con({"costos.comision_en_moneda_comprada": en_moneda})
    r.ruta = carpeta / "reglamento.yaml"
    k = _dia_marea_alta(r)
    c = P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])
    compra = next(b for b in c["boletos"] if b["accion"] == "COMPRAR")
    pos = P.cargar_estado(r, "C", "")["posiciones"][0]
    return compra, pos


def test_con_la_llave_en_false_la_neta_es_la_bruta(reg, tmp_path):
    compra, pos = _compra_c(reg, tmp_path, en_moneda=False)
    assert compra["cantidad_stop"] == compra["cantidad"] and pos["cantidad_stop"] == pos["cantidad"]


def test_tamano_y_riesgo_del_boleto_no_cambian(reg, tmp_path):
    (tmp_path / "neta").mkdir()
    (tmp_path / "bruta").mkdir()
    neta, pos = _compra_c(reg, tmp_path / "neta", en_moneda=True)
    bruta, _ = _compra_c(reg, tmp_path / "bruta", en_moneda=False)
    for campo in ("cantidad", "riesgo_pct", "riesgo_usdt", "valor_usdt", "llenado_papel", "stop", "precio_entrada"):
        assert neta[campo] == bruta[campo], campo
    assert neta["cantidad_stop"] == R.cantidad_neta(neta["cantidad"], 0.1, neta["paso_cantidad"]) < neta["cantidad"]
    assert pos["cantidad_stop"] == neta["cantidad_stop"]
    assert f"VENTA de {P.numero_txt(neta['cantidad_stop'], neta['paso_cantidad'])} BTCUSDT" in neta["texto"]
