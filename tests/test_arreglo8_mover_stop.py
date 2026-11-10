"""Arreglo 8: mover el stop con el reemplazo en una sola operación de Binance (order/cancelReplace)."""
from sobreviviente import papel as P

from test_papel import _buscar_dia_con_compra, _datos_dia, _reg_papel

BOLETO = {"boleto_id": "20261110-A-MOD-SOL-1", "accion": "MODIFICAR_STOP", "simbolo": "SOLUSDT", "estrategia": "M1",
          "cantidad": 0.12, "stop": 150.5, "precio_limite_stop": 149.74, "stop_anterior": 140.0,
          "precio_limite_stop_anterior": 139.3, "regla_precio": P.REGLA_PRECIO_STOP}


def test_texto_mover_stop_usa_reemplazo():
    t = P.texto_boleto(BOLETO)
    assert "reemplazo" in t
    assert "cancela el stop actual y pon" not in t
    assert "cancelReplace" in t and "STOP_ON_FAILURE" in t
    assert "Si Binance rechaza el stop nuevo, el viejo se queda; avisa a THE BOSS y no improvises" in t
    assert "-2021" in t and "stop 140," in t                   # cómo reponer el stop viejo en el único caso en que se pierde
    assert "por debajo del precio actual" in t


def test_boleto_mover_stop_real_trae_regla_de_precio(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    mover = []
    for j in range(k, k + 40):
        res = P.ronda_cartera(r, "A", _datos_dia(r, j)[0], [], [])
        mover += [b for b in res["boletos"] if b["accion"] == "MODIFICAR_STOP"]
    assert mover, "en 40 días el canal de M1 debió subir el stop al menos una vez"
    b = mover[0]
    assert b["regla_precio"] == ("el stop nuevo debe quedar por debajo del precio actual; si no, NO lo pongas, "
                                 "deja el viejo y avisa")
    assert b["stop"] > b["stop_anterior"] and b["precio_limite_stop_anterior"] < b["stop_anterior"]
    assert "reemplazo" in b["texto"] and "cancela el stop actual y pon" not in b["texto"]
