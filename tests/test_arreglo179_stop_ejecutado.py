"""Arreglo 179 (I3): cuando el stop se ejecutó normal, conciliar --real NO marca SIN STOP ni bloquea: pide STOP_EJECUTADO.

Antes, si el stop se había llenado (no hay ninguna orden abierta con su id y en la cuenta queda menos BTC que el paso de
Binance), `conciliar` lo trataba como una posición SIN STOP: cambiaba `estado_stop` a SIN_STOP y ponía `bloqueo_compras`
(que solo Ángelo quita), aunque no había nada que proteger. La ronda real sí lo distinguía (boleto informativo
STOP_EJECUTADO), pero su conciliación corría antes y bloqueaba igual.

Ahora sale «STOP EJECUTADO: BTC — … EJECUTOR: registra STOP_EJECUTADO …»: la conciliación no cuadra (falta anotarlo, así
que no se compra), pero no se marca SIN STOP, no se bloquea y no se toca el estado. Con el STOP_EJECUTADO anotado, la
siguiente conciliación cuadra sin que Ángelo tenga que reanudar nada. Con BTC de más (≥ el paso) sigue siendo SIN STOP.
"""
import json
from datetime import datetime, timedelta, timezone

from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture

VENTA = 0.00012 * 59300.0 - 0.0071             # lo que dejó el stop (en USDT, comisión en USDT)
USDT_DESPUES = USDT_CON_POS + VENTA


def _con_posicion(r, **cambios):
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [{**POS, **cambios}]})


def _textos(res):
    return [t for _, t in res["lineas"]]


def test_stop_ejecutado_no_es_sin_stop_ni_bloquea(mundo):
    r, _, foto, _ = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_DESPUES, btc=0.000009), [])                 # sin órdenes abiertas y polvo (< 0.00001)
    res = RE.conciliar(r, AHORA - timedelta(minutes=1))
    assert not res["ok"] and res["sin_stop"] == [] and res["avisos"] == []
    assert not any(t.startswith("SIN STOP") for t in _textos(res))
    (linea,) = [t for t in _textos(res) if t.startswith("STOP EJECUTADO")]
    assert linea == ("STOP EJECUTADO: BTC — no hay stop abierto y quedan 9e-06 BTC (menos del paso de 1e-05): el stop se "
                     "ejecutó normal. No es SIN STOP y no se bloquea nada. EJECUTOR: registra STOP_EJECUTADO "
                     "(registrar-llenado --real) con los datos de spot.getOrder del stop (sp0123456789abcdef) y vuelve a "
                     "conciliar --real")
    assert set(res["diferencias"]) == {"stop_ejecutado", "usdt"} and res["diferencias"]["stop_ejecutado"] == ["BTC"]
    usdt = next(t for t in _textos(res) if t.startswith("USDT:"))
    assert usdt.endswith("seguramente es la venta del stop de BTC; se arregla al registrar STOP_EJECUTADO")
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"] is None and est["posiciones"][0]["estado_stop"] == "ACTIVO"


def test_anotado_el_stop_ejecutado_cuadra_sin_que_angelo_reanude(mundo, capsys):
    r, _, foto, correr = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_DESPUES, btc=0.000009), [])
    assert correr() == 0                                                  # la ronda: boleto informativo, sin bloqueo
    (b,) = json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
    assert b["motivo"] == "STOP_EJECUTADO" and b["solo_informativo"] is True and b["urgente"] is False
    salida = capsys.readouterr().out
    assert "URGENTE" not in salida and "SIN STOP" not in salida
    assert RE.cargar_estado(r)["bloqueo_compras"] is None
    ok, _ = RE.registrar_llenado(r, b["boleto_id"], "STOP_EJECUTADO", cantidad=0.00012, precio=59300.0, comision=0.0071,
                                 moneda_comision="USDT", ahora=AHORA + timedelta(minutes=3))
    assert ok
    foto(cuenta(usdt=USDT_DESPUES, btc=0.000009), [], ahora=AHORA + timedelta(minutes=4))
    res = RE.conciliar(r, AHORA + timedelta(minutes=5))
    assert res["ok"], res["lineas"]
    assert RE.cargar_estado(r)["bloqueo_compras"] is None


def test_con_btc_de_mas_sigue_siendo_sin_stop(mundo):
    r, _, foto, _ = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00001), [])                  # justo el paso: no es polvo
    res = RE.conciliar(r, AHORA - timedelta(minutes=1))
    assert res["sin_stop"] == ["BTC"] and "stop_ejecutado" not in res["diferencias"]
    est = RE.cargar_estado(r)
    assert est["posiciones"][0]["estado_stop"] == "SIN_STOP" and est["bloqueo_compras"]["motivo"] == "SIN STOP: BTC"


def test_con_una_orden_abierta_con_su_id_no_es_ejecutado(mundo):
    r, _, foto, _ = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS), [orden_stop(estado="PARTIALLY_FILLED")])   # sigue abierta
    res = RE.conciliar(r, AHORA - timedelta(minutes=1))
    assert "stop_ejecutado" not in res["diferencias"] and res["sin_stop"] == ["BTC"]
    assert RE.stop_ejecutado(POS, {"ordenes_abiertas": [], "activos": {}}) is True        # sin BTC ni órdenes
    assert RE.stop_ejecutado({**POS, "paso_cantidad": None}, {"ordenes_abiertas": [],
                                                              "activos": {"BTC": {"libre": 1e-13, "bloqueado": 0.0}}})


def test_por_la_linea_de_comandos_sale_primero_y_sin_sin_stop(mundo, capsys):
    r, _, foto, _ = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_DESPUES, btc=0.000009), [], ahora=datetime.now(timezone.utc) - timedelta(minutes=1))
    capsys.readouterr()
    assert cli_real.conciliar_real(r) == 1                               # con la hora de verdad (sin --ahora)
    salida = capsys.readouterr().out.splitlines()
    assert salida[0].startswith("❌ STOP EJECUTADO: BTC — no hay stop abierto") and not any("SIN STOP:" in x
                                                                                          for x in salida)
    assert salida[-1].startswith("❌ Lo real NO cuadra")


def test_la_revision_despues_de_la_compra_queda_pendiente_sin_bloquear(mundo):
    r, _, foto, _ = mundo
    _con_posicion(r, id=POS["id"])
    est = RE.cargar_estado(r)
    est[RE.REVISION] = {"boleto": POS["id"], "desde": (AHORA - timedelta(minutes=30)).isoformat(timespec="seconds")}
    RE.guardar_estado(r, est)
    foto(cuenta(usdt=USDT_DESPUES, btc=0.000009), [])
    res = RE.conciliar(r, AHORA - timedelta(minutes=1))
    assert f"revisión justo después de la compra (boleto {POS['id']}): pendiente hasta que se registre STOP_EJECUTADO" \
        in _textos(res)
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"] is None and est[RE.REVISION]["boleto"] == POS["id"]
    # Con otra diferencia además del stop ejecutado, la revisión no cuadra y bloquea como siempre (171)
    foto(cuenta(usdt=USDT_DESPUES + 5.0, btc=0.000009), [orden_stop(client="otra")])
    RE.conciliar(r, AHORA)
    est = RE.cargar_estado(r)
    assert "no cuadró" in est["bloqueo_compras"]["motivo"] and RE.REVISION not in est
