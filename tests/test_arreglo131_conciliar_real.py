"""Arreglo 131: `conciliar --real` compara la foto de saldo contra cartera_REAL.json (cierra R4).

Falla cerrada: sin foto, con foto vieja o con el estado dañado NO cuadra. Un cambio de USDT que no viene de llenados da
❌ y solo Ángelo lo resuelve con `ajustar-capital-real`. El conciliar de papel queda igual."""
import json
import os
from datetime import timedelta

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import papel as P
from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta, escribir_entrada, orden_stop, reg_real
from test_arreglo129_base_real import POSICION

POS = {**POSICION, "paso_cantidad": 0.00001}             # costo: 0.00013 × 70010 = 9.1013 USDT (comisión en BTC)
USDT_CON_POS = 142.54 - 0.00013 * 70010.0


@pytest.fixture
def r(tmp_path):
    return reg_real(tmp_path)


def _foto(r, tmp_path, cta, ordenes, ahora=AHORA):
    c, o = escribir_entrada(tmp_path, cta, ordenes)
    for p in (c, o):
        os.utime(p, (ahora.timestamp() - 60, ahora.timestamp() - 60))
    return RE.registrar_saldo(r, c, o, lambda s: 70000.0, ahora=ahora)


def _con_posicion(r):
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-16"), "posiciones": [dict(POS)]})


def _textos(res):
    return [t for _, t in res["lineas"]]


def test_sin_posiciones_cuadra(r, tmp_path):
    _foto(r, tmp_path, cuenta(), [])
    res = RE.conciliar(r, AHORA + timedelta(minutes=5))
    assert res["ok"] and res["diferencias"] == {} and res["foto_hora"] == "2026-11-16T00:12:00+00:00"
    assert RE.conciliacion_ok(r, AHORA + timedelta(minutes=6)) == (True, "")
    guardado = json.loads(RE.archivo_conciliacion(r).read_text(encoding="utf-8"))
    assert guardado["ok"] is True and "lineas" not in guardado


def test_con_posicion_y_stop_vivo_cuadra(r, tmp_path):
    _con_posicion(r)
    _foto(r, tmp_path, cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    res = RE.conciliar(r, AHORA)
    assert res["ok"], res["lineas"]
    assert "stop de BTC vivo (0.00012 a 59500.0)" in _textos(res)


def test_sobra_usdt(r, tmp_path):
    _foto(r, tmp_path, cuenta(usdt=152.54), [])
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["diferencias"]["usdt"] == pytest.approx(10.0)
    assert any("ajustar-capital-real" in t for t in _textos(res))
    ok, por_que = RE.conciliacion_ok(r, AHORA)
    assert not ok and "no cuadró" in por_que


def test_falta_el_stop_marca_sin_stop(r, tmp_path):
    _con_posicion(r)
    _foto(r, tmp_path, cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["sin_stop"] == ["BTC"] and "SIN STOP: BTC" in _textos(res)
    assert RE.cargar_estado(r)["posiciones"][0]["estado_stop"] == "SIN_STOP"


def test_falta_el_stop_simulando_no_escribe(r, tmp_path):
    _con_posicion(r)
    _foto(r, tmp_path, cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    res = RE.conciliar(r, AHORA, escribir=False)
    assert res["sin_stop"] == ["BTC"] and not RE.archivo_conciliacion(r).exists()
    assert RE.cargar_estado(r)["posiciones"][0]["estado_stop"] == "ACTIVO"


@pytest.mark.parametrize("orden", [orden_stop(cantidad="0.00011000"), orden_stop(stop="58000.00000000")])
def test_stop_con_otra_cantidad_o_precio(r, tmp_path, orden):
    _con_posicion(r)
    _foto(r, tmp_path, cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden])
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["diferencias"]["stop_distinto"] == ["BTC"]


def test_stop_que_no_es_de_venta_cuenta_como_sin_stop(r, tmp_path):
    _con_posicion(r)
    _foto(r, tmp_path, cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop(lado="BUY")])
    assert RE.conciliar(r, AHORA)["sin_stop"] == ["BTC"]


def test_cantidad_de_btc_distinta(r, tmp_path):
    _con_posicion(r)
    _foto(r, tmp_path, cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012, btc=0.00005), [orden_stop()])
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["diferencias"]["activos"]["BTC"] == pytest.approx(0.00005)


def test_orden_colgada_que_no_conoce(r, tmp_path):
    compra = orden_stop(lado="BUY", tipo="LIMIT", client="bp0000000000000001", order_id=9, stop="0")
    _foto(r, tmp_path, cuenta(usdt=133.44, usdt_bloq=9.10), [compra])
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["diferencias"]["ordenes_desconocidas"] == ["bp0000000000000001"]


def test_foto_vieja_o_sin_foto_no_cuadra(r, tmp_path):
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and "no hay foto" in res["errores"][0]
    _foto(r, tmp_path, cuenta(), [])
    res = RE.conciliar(r, AHORA + timedelta(minutes=121))
    assert not res["ok"] and "121 min" in res["errores"][0]
    assert not RE.conciliacion_ok(r, AHORA + timedelta(minutes=121))[0]


def test_conciliacion_de_otra_foto_o_danada_no_sirve(r, tmp_path):
    _foto(r, tmp_path, cuenta(), [])
    assert RE.conciliacion_ok(r, AHORA) == (False, "no hay conciliación real (corre conciliar --real)")
    RE.conciliar(r, AHORA)
    _foto(r, tmp_path, cuenta(), [], ahora=AHORA + timedelta(minutes=30))     # foto nueva, conciliación vieja
    assert "no es de la última foto" in RE.conciliacion_ok(r, AHORA + timedelta(minutes=31))[1]
    RE.archivo_conciliacion(r).write_text("{roto", encoding="utf-8")
    assert "dañada" in RE.conciliacion_ok(r, AHORA + timedelta(minutes=31))[1]


def test_estado_danado_no_cuadra(r, tmp_path):
    _foto(r, tmp_path, cuenta(), [])
    RE.archivo_estado(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert not RE.conciliar(r, AHORA)["ok"]


def test_ajustar_capital_solo_con_el_ok_de_angelo(r, tmp_path):
    _foto(r, tmp_path, cuenta(usdt=152.54), [])
    assert RE.ajustar_capital(r, 152.54, "  ") == (False, 'Falta el OK de Ángelo (--ok-angelo "…"). Sin eso no se ajusta nada.')
    assert not RE.archivo_estado(r).exists()
    assert RE.ajustar_capital(r, float("nan"), "ok")[0] is False
    ok, msg = RE.ajustar_capital(r, 152.54, "deposité 10 USDT el 16 nov", ahora=AHORA)
    assert ok and "152.54" in msg
    est = RE.cargar_estado(r)
    assert est["ajustes"][0]["texto"] == "deposité 10 USDT el 16 nov" and est["ajustes"][0]["delta"] == pytest.approx(10.0)
    assert est["ajustes"][0]["fecha"] == AHORA.isoformat(timespec="seconds")
    assert est["pico"] == est["capital_inicio_dia"] == est["capital_inicio_semana"] == 152.54
    assert RE.conciliar(r, AHORA)["ok"]


def test_comandos(r, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    _con_posicion(r)
    _foto(r, tmp_path, cuenta(usdt=USDT_CON_POS, btc=0.00012), [], ahora=RE.datetime.now(RE.timezone.utc))
    assert MAIN.main(["conciliar", "--real"]) == 1
    salida = capsys.readouterr().out
    assert salida.startswith("❌ SIN STOP: BTC") and "Avisa a THE BOSS de inmediato" in salida
    assert MAIN.main(["ajustar-capital-real", "--usdt", "100"]) == 2
    assert "Falta el OK de Ángelo" in capsys.readouterr().out
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert MAIN.main(["ajustar-capital-real", "--usdt", "100", "--ok-angelo", "sí"]) == 2
    assert "dañado" in capsys.readouterr().out
    RE.archivo_estado(r).unlink()
    RE.archivo_estado(r).with_name("cartera_REAL.json.bak").unlink()
    _foto(r, tmp_path, cuenta(), [], ahora=RE.datetime.now(RE.timezone.utc))
    assert MAIN.main(["conciliar", "--real"]) == 0
    assert capsys.readouterr().out.rstrip().endswith("👍 Las cuentas reales cuadran.")
    assert not (tmp_path / "datos" / "papel" / "conciliacion.json").exists()   # el de papel no se toca
    assert P.conciliacion_ok(r) is True
