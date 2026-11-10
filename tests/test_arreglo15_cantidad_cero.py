"""Arreglo 15: si la cantidad redondeada al paso de Binance queda en 0, no hay boleto y sí hay aviso."""
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def test_cantidad_menor_que_el_paso_no_genera_boleto(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    original = P.R.evaluar_candidato

    def cantidad_diminuta(reg_, estado, cand, filtros, *a, **kw):
        d = original(reg_, estado, cand, filtros, *a, **kw)
        if d.aprobada:
            d.cantidad = filtros.paso / 10          # menor que el paso: redondeada queda en 0
        return d
    monkeypatch.setattr(P.R, "evaluar_candidato", cantidad_diminuta)
    c = P.ronda_cartera(r, "C", dd, [], [])
    assert not [b for b in c["boletos"] if b["accion"] == "COMPRAR"]
    assert any("⚠️ cantidad menor que el mínimo de Binance, no se compra" in m and "BTCUSDT" in m for m in c["mensajes"])
    est = P.cargar_estado(r, "C", "")
    assert not est["posiciones"] and est["efectivo"] == est["capital_inicial"]    # no se abrió nada


def test_cantidad_normal_si_genera_boleto(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    c = P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])
    b = next(x for x in c["boletos"] if x["accion"] == "COMPRAR")
    assert P.numero_txt(b["cantidad"], b["paso_cantidad"]) != "0"
