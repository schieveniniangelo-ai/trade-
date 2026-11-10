"""Arreglo 13: mover el stop con ONLY_NEW y el id del stop viejo; plan si Binance lo pierde (-2021); compra sin OCO."""
import json

from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _buscar_dia_con_compra, _datos_dia, _reg_papel


def test_texto_mover_stop_only_new_y_plan_de_emergencia(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    mover = []
    for j in range(k, k + 40):
        mover += [b for b in P.ronda_cartera(r, "A", _datos_dia(r, j)[0], [], [])["boletos"] if b["accion"] == "MODIFICAR_STOP"]
    assert mover
    b = mover[0]
    t = b["texto"]
    assert "cancelRestrictions=ONLY_NEW" in t
    assert f"cancelOrigClientOrderId={b['id_stop_anterior']}" in t and f"newClientOrderId={b['id_stop']}" in t
    assert "VENDE la posición a MERCADO" in t
    assert f"stop {P.numero_txt(b['stop_anterior'], b['tick_precio'])}" in t     # el stop viejo, para reponerlo
    # Cada movimiento cancela exactamente el stop que puso el anterior (o la compra)
    ids = [(x["id_stop_anterior"], x["id_stop"]) for x in mover if x["simbolo"] == b["simbolo"]]
    for (a1, n1), (a2, n2) in zip(ids, ids[1:]):
        assert a2 == n1
    assert all(len(i) <= 36 and i.isascii() for par in ids for i in par)


def test_boleto_comprar_sin_oco(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    c = P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])
    b = next(x for x in c["boletos"] if x["accion"] == "COMPRAR")
    assert "OCO" not in json.dumps(b, ensure_ascii=False)
    assert "STOP_LOSS_LIMIT individual" in b["texto"] and f"newClientOrderId={b['id_stop']}" in b["texto"]
    # El primer movimiento de stop de esta posición cancelará justo ese stop
    pos = P.cargar_estado(r, "C", "")["posiciones"][0]
    assert P.id_stop(pos["id"], pos["stop_n"]) == b["id_stop"]
