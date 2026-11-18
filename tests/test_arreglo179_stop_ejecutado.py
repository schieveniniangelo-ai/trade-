"""Arreglo 179: cuando el stop se ejecutó normal, no es SIN STOP ni bloquea: se pide registrar STOP_EJECUTADO.

Antes, `conciliar --real` veía una posición sin su stop abierto y la marcaba SIN STOP (estado_stop SIN_STOP) y ponía
`bloqueo_compras`, que solo quita Ángelo, aunque el stop se hubiera ejecutado bien (no hay stop abierto y el BTC que
queda es menos que el paso mínimo). La ronda real ya lo veía como STOP_EJECUTADO (boleto solo informativo), pero la
conciliación (que corre antes) ya había bloqueado. Ahora la conciliación dice «el stop ya se ejecutó … registra
STOP_EJECUTADO»: no cuadra hasta que se anote (sin compras ese día), pero sin SIN STOP, sin bloqueo y sin urgencia.
Con BTC en la cuenta y sin stop sigue siendo SIN STOP, como siempre.
"""
import json
from datetime import timedelta

from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo135_salidas_real import _cierres, con_posicion  # noqa: F401 - fixture

VENTA = USDT_CON_POS + 7.10       # lo que dejó la venta del stop


def test_conciliar_no_marca_sin_stop_ni_bloquea(con_posicion):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=VENTA, btc=0.000001), [])                          # menos que el paso de 0.00001
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["sin_stop"] == [] and "sin_stop" not in res["diferencias"]
    assert res["diferencias"]["stop_ejecutado"] == ["BTC"]
    assert not [t for _, t in res["lineas"] if t.startswith("SIN STOP")]
    (linea,) = [t for ok, t in res["lineas"] if "el stop ya se ejecutó" in t]
    assert linea.startswith("BTC: el stop ya se ejecutó (no hay stop abierto y quedan 1e-06 BTC, menos que el paso de "
                            "1e-05). No es SIN STOP: EJECUTOR confirma con spot.getOrder y registra STOP_EJECUTADO")
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"] is None and est["posiciones"][0]["estado_stop"] == "ACTIVO"


def test_la_ronda_real_solo_informa_y_no_bloquea(con_posicion, capsys):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=VENTA, btc=0.0), [])
    assert correr() == 0
    (b,) = _cierres(r)
    assert b["motivo"] == "STOP_EJECUTADO" and b.get("solo_informativo") is True
    salida = capsys.readouterr().out
    assert "URGENTE" not in salida and "registra STOP_EJECUTADO" in salida
    assert RE.cargar_estado(r)["bloqueo_compras"] is None


def test_al_registrar_stop_ejecutado_se_cierra_y_cuadra(con_posicion, capsys):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=VENTA, btc=0.0), [])
    assert correr() == 0
    (b,) = _cierres(r)
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "STOP_EJECUTADO", cantidad=0.00012, precio=59166.6667,
                                    comision=0.0, moneda_comision="USDT", ahora=AHORA + timedelta(minutes=3))
    assert ok and RE.cargar_estado(r)["posiciones"] == []
    res = RE.conciliar(r, AHORA + timedelta(minutes=4))
    assert "stop_ejecutado" not in res["diferencias"] and res["sin_stop"] == []


def test_con_btc_y_sin_stop_sigue_siendo_sin_stop(con_posicion):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    res = RE.conciliar(r, AHORA)
    assert res["sin_stop"] == ["BTC"] and "stop_ejecutado" not in res["diferencias"]
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == "SIN STOP: BTC"


def test_justo_el_paso_ya_no_es_stop_ejecutado(con_posicion):
    r, cfg, foto, correr = con_posicion
    foto(cuenta(usdt=VENTA, btc=0.00001), [])                           # igual al paso: sí hay BTC que proteger
    res = RE.conciliar(r, AHORA)
    assert res["sin_stop"] == ["BTC"] and "stop_ejecutado" not in res["diferencias"]


def test_sin_paso_anotado_usa_casi_cero(mundo):
    r, cfg, foto, correr = mundo
    pos = {k: v for k, v in POS.items() if k != "paso_cantidad"}
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [pos]})
    foto(cuenta(usdt=VENTA, btc=0.0), [])
    res = RE.conciliar(r, AHORA, escribir=False)
    assert res["diferencias"]["stop_ejecutado"] == ["BTC"] and res["sin_stop"] == []
    assert json.loads(RE.archivo_estado(r).read_text(encoding="utf-8"))["bloqueo_compras"] is None
