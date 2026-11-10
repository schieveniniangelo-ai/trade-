"""Arreglo 35: una posición abierta sin velas vale su último cierre (o su entrada), no 0; se avisa y no se cierra."""
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _con_btc_abierto(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    hoy = P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])
    assert hoy["posiciones"] == ["BTCUSDT"]
    return r, k, hoy


def test_sin_velas_el_capital_no_cae_y_se_avisa(reg, tmp_path):
    r, k, ayer = _con_btc_abierto(reg, tmp_path)
    dd = _datos_dia(r, k + 1)[0]
    dd.md.velas.pop("BTCUSDT")                                   # hoy no llegaron las velas de BTC
    hoy = P.ronda_cartera(r, "C", dd, [], [])
    assert hoy["posiciones"] == ["BTCUSDT"]                      # no se cerró nada
    pos = P.cargar_estado(r, "C", "")["posiciones"][0]
    assert hoy["capital"] == hoy["efectivo"] + pos["cantidad"] * pos["entrada"]   # vale su entrada, no 0
    assert hoy["capital"] > 0.99 * ayer["capital"]
    assert P.cargar_estado(r, "C", "")["curva"][hoy["dia"]] == hoy["capital"]
    texto = P.resumen_corto({"dia": hoy["dia"], "carteras": {"C": hoy}, "referencias": {}, "avisos": []})
    assert "BTCUSDT: sin velas hoy, revisar a mano" in texto


def test_sin_la_vela_de_hoy_usa_el_ultimo_cierre(reg, tmp_path):
    r, k, ayer = _con_btc_abierto(reg, tmp_path)
    dd = _datos_dia(r, k + 1)[0]
    v = dd.md.velas["BTCUSDT"]
    dd.md.velas["BTCUSDT"] = v.iloc[:-1]                         # falta solo la vela de hoy
    hoy = P.ronda_cartera(r, "C", dd, [], [])
    pos = P.cargar_estado(r, "C", "")["posiciones"][0]
    assert hoy["capital"] == hoy["efectivo"] + pos["cantidad"] * float(v["close"].iloc[-2])
    assert any("BTCUSDT: sin velas hoy, revisar a mano" in m for m in hoy["mensajes"])
