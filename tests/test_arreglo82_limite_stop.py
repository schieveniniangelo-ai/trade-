"""Arreglo 82: la ronda de papel calcula el precio límite del STOP_LOSS_LIMIT en un solo lugar.

Antes `ronda_cartera` lo calculaba en tres sitios (el candidato de la compra y los dos límites del boleto
MODIFICAR_STOP). Estas pruebas fijan lo que sale hoy en los boletos, para que la función única dé lo mismo.
Sin red ni llaves: velas sintéticas y filtros falsos."""
import pytest

from sobreviviente import papel as P
from sobreviviente.exchange import Filtros, redondear_abajo

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo75_stop_sin_mover import STOP_ANTERIOR, _mover, _ronda_con_stop
from test_papel import _datos_dia


def test_limite_stop_redondea_hacia_abajo_al_tick():
    f = Filtros("XUSDT", 0.01, 0.0001, 0.0001, 5.0)
    assert P._limite_stop(10.02, f, 0.5) == 9.96                       # 10.02 × 0.995 = 9.9699 → 9.96
    assert P._limite_stop(10.02, None, 0.5) == pytest.approx(9.9699)   # sin reglas de Binance: sin redondear


def test_la_compra_lleva_el_limite_del_stop_redondeado(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    res = P.ronda_cartera(r, "C", _datos_dia(r, _dia_marea_alta(r))[0], [], [])
    compra = [b for b in res["boletos"] if b["accion"] == "COMPRAR"]
    _, lim = P.limites_ejecucion(r)
    assert len(compra) == 1
    b = compra[0]
    assert b["precio_limite_stop"] == redondear_abajo(b["stop"] * (1 - lim / 100), b["tick_precio"])


def test_mover_el_stop_lleva_los_dos_limites_redondeados(reg, tmp_path, monkeypatch):
    res, _, _, r, _ = _ronda_con_stop(reg, tmp_path, monkeypatch, 10.02)
    (b,) = _mover(res)
    _, lim = P.limites_ejecucion(r)
    assert b["precio_limite_stop"] == redondear_abajo(10.02 * (1 - lim / 100), 0.01)
    assert b["precio_limite_stop_anterior"] == redondear_abajo(STOP_ANTERIOR * (1 - lim / 100), 0.01)
