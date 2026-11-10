"""Arreglo 51: si falta el precio de apertura (falla de red), la compra o la venta que no se hizo sale con ⚠️ en el
resumen. No cambia ninguna regla: solo deja de pasar callado."""
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _resumen(c):
    return P.resumen_corto({"dia": c["dia"], "carteras": {"C": c}, "referencias": {}, "avisos": []})


def test_compra_sin_precio_de_apertura_se_ve_en_el_resumen(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    dd = _datos_dia(r, k)[0]
    dd.apertura_hoy = lambda s: None                                   # Binance no contestó el precio de apertura
    c = P.ronda_cartera(r, "C", dd, [], [])
    assert not c["boletos"] and c["posiciones"] == []                  # no se compra a ciegas
    assert "⚠️ BTCUSDT (M0): no hay precio de apertura; no entra hoy." in c["mensajes"]
    assert "⚠️ Cartera C: BTCUSDT (M0): no hay precio de apertura; no entra hoy." in _resumen(c)


def test_venta_sin_precio_de_apertura_se_ve_y_se_intenta_manana(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])               # día k: compra BTC
    original = P._senales

    def pide_salir(dd, clave, simbolo, params):
        sen = original(dd, clave, simbolo, params)
        if sen is not None:
            sen = sen.copy()
            sen["salir"], sen["entrada"] = True, False
        return sen

    monkeypatch.setattr(P, "_senales", pide_salir)
    dd1 = _datos_dia(r, k + 1)[0]
    dd1.apertura_hoy = lambda s: None                                  # día k+1: toca vender, pero no hay precio
    c1 = P.ronda_cartera(r, "C", dd1, [], [])
    assert c1["posiciones"] == ["BTCUSDT"] and not c1["boletos"]       # sigue abierta, sin boleto inventado
    aviso = "BTCUSDT: toca vender en la apertura pero no hay precio; se intenta mañana."
    assert "⚠️ " + aviso in c1["mensajes"] and "⚠️ Cartera C: " + aviso in _resumen(c1)
    c2 = P.ronda_cartera(r, "C", _datos_dia(r, k + 2)[0], [], [])      # día k+2: ya hay precio → se vende
    assert [b["accion"] for b in c2["boletos"]] == ["CERRAR"] and c2["posiciones"] == []
