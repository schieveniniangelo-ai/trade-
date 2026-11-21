"""Arreglo 199: con un llenado anotado, una foto de saldo sin `update_time_cuenta` válido NO sirve.

Antes (184 y 193), `real._foto_de_antes_del_llenado` regresaba "" (la foto servía) si la foto no traía un updateTime
entero: sin la hora de Binance no se podía saber si la foto era de antes del último llenado, y se aceptaba. registrar-saldo
ya rechazaba una cuenta sin updateTime, pero un archivo datos/real/saldo_binance.json sin `update_time_cuenta` (de antes
del 184 o editado a mano) pasaba la revisión de conciliar --real. Ahora, si ya hay un llenado anotado, esa foto no sirve
y se pide repetir registrar-saldo. Sin llenados, igual que antes."""
import json
from datetime import timedelta

import pytest

from sobreviviente import real as RE

from apoyo_real import AHORA
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture


def _comprar(r, b):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", cantidad=0.00013, precio=70000.0,
                                comision=0.00000013, moneda_comision="BTC", ahora=AHORA + timedelta(minutes=2))[0]


@pytest.mark.parametrize("ut", [None, 0, -5, 1.5e12, True, "x"])
def test_con_llenado_sin_updatetime_valido_no_sirve(compra, ut):
    r, b, _ = compra
    _comprar(r, b)
    msg = RE._foto_de_antes_del_llenado(r, {"update_time_cuenta": ut}, "la foto de saldo")
    assert msg == (f"la foto de saldo no trae una hora de Binance válida (updateTime de spot.getAccount) y ya hay un "
                   f"llenado anotado (el COMPRA_LLENADA del boleto {b['boleto_id']}): no se puede saber si la foto es de "
                   f"después. Vuelve a pedir spot.getAccount tal cual y repite registrar-saldo")


def test_updatetime_imposible_tampoco_sirve(compra):
    r, b, _ = compra
    _comprar(r, b)
    assert RE._foto_de_antes_del_llenado(r, {"update_time_cuenta": 10 ** 30}, "x").startswith(
        "x trae un updateTime de Binance que no se entiende")


def test_conciliar_rechaza_la_foto_sin_updatetime(compra):
    r, b, foto = compra
    _comprar(r, b)
    foto(ahora=AHORA + timedelta(minutes=3))
    arch = RE.archivo_saldo(r)
    datos = json.loads(arch.read_text(encoding="utf-8"))
    datos.pop("update_time_cuenta")                               # un archivo de antes del 184 o editado a mano
    arch.write_text(json.dumps(datos), encoding="utf-8")
    res = RE.conciliar(r, AHORA + timedelta(minutes=4), escribir=False)
    assert not res["ok"]
    assert any("no trae una hora de Binance válida" in e for e in res["errores"])


def test_sin_llenados_sigue_igual(compra):
    r, _, _ = compra
    assert RE._foto_de_antes_del_llenado(r, {}, "x") == ""
