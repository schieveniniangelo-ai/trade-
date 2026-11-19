"""Arreglo 188 (R98): COMPRA_NO_LLENADA quita la falsa alarma SOLO si la última foto de saldo fresca no trae BTC sin estado.

Antes (183), anotar COMPRA_NO_LLENADA quitaba el bloqueo de compras que había puesto esa misma compra enviada sin anotar,
sin mirar la cuenta. Si el EJECUTOR se equivocaba (la compra sí se llenó), las compras quedaban libres hasta la siguiente
conciliación. Ahora el bloqueo se quita solo si la última foto FRESCA no trae BTC que el estado real no conoce; si lo trae,
o si no hay foto fresca para confirmarlo, se queda (solo Ángelo lo quita) y se dice por qué. Con una posición anotada
solo cuenta lo que SOBRA sobre ella (180)."""
import json
from datetime import timedelta

from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture


def _bloqueada(r, b):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    RE.conciliar(r, AHORA + timedelta(minutes=2))
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == RE.motivo_compra_sin_anotar("BTC", b["boleto_id"])


def _no_llenada(r, b, minutos=3):
    return RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", motivo="EXPIRED",
                                ahora=AHORA + timedelta(minutes=minutos))


def test_con_btc_sin_estado_en_la_foto_fresca_el_bloqueo_se_queda(compra):
    r, b, foto = compra
    _bloqueada(r, b)
    foto(cuenta(usdt=142.54 - 9.10, btc=0.00013), [], ahora=AHORA + timedelta(minutes=2))
    ok, msgs = _no_llenada(r, b)
    assert ok and msgs[0] == "👍 Anotado: la compra no se llenó (EXPIRED); no hay posición (no se reintenta)."
    assert msgs[1] == (f"❌ NO se quitó el bloqueo de compras de esta compra enviada sin anotar ({b['boleto_id']}): la "
                       f"última foto de saldo fresca trae 0.00013 BTC que el estado real no conoce. Puede haber BTC SIN "
                       f"STOP: avisa a THE BOSS con prioridad; el bloqueo solo lo quita Ángelo (reanudar --cartera REAL).")
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"]["motivo"] == RE.motivo_compra_sin_anotar("BTC", b["boleto_id"])
    assert "falsas_alarmas" not in est


def test_con_la_foto_fresca_limpia_se_quita(compra):
    r, b, foto = compra
    _bloqueada(r, b)
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=2))
    ok, msgs = _no_llenada(r, b)
    assert ok and msgs[1].startswith("✅ Se quitó el bloqueo de compras")
    assert RE.cargar_estado(r)["bloqueo_compras"] is None


def test_sin_foto_fresca_el_bloqueo_se_queda(compra):
    r, b, _ = compra                                   # la foto del fixture es de AHORA − 5 min
    _bloqueada(r, b)
    ok, msgs = _no_llenada(r, b, minutos=200)           # ya tiene más de 120 min
    assert ok and msgs[1] == (f"❌ NO se quitó el bloqueo de compras de esta compra enviada sin anotar "
                              f"({b['boleto_id']}): no hay una foto de saldo fresca que confirme que no hay BTC sin anotar "
                              f"(EJECUTOR: registrar-saldo y conciliar --real). Puede haber BTC SIN STOP: avisa a THE BOSS "
                              f"con prioridad; el bloqueo solo lo quita Ángelo (reanudar --cartera REAL).")
    assert RE.cargar_estado(r)["bloqueo_compras"] is not None


def test_sin_ninguna_foto_el_bloqueo_se_queda(compra):
    r, b, _ = compra
    _bloqueada(r, b)
    RE.archivo_saldo(r).unlink()
    ok, msgs = _no_llenada(r, b)
    assert ok and "no hay una foto de saldo fresca" in msgs[1] and RE.cargar_estado(r)["bloqueo_compras"] is not None


def _posicion(cant):
    return {"id": "20261114-RA-COM-BTC-00000000", "simbolo": "BTCUSDT", "cantidad_neta": cant, "paso_cantidad": 0.00001}


def _foto_con(r, sin_estado, activos):
    arch = RE.archivo_saldo(r)
    f = json.loads(arch.read_text(encoding="utf-8"))
    f.update(sin_estado=sin_estado, activos=activos)
    arch.write_text(json.dumps(f), encoding="utf-8")


def test_con_posicion_anotada_solo_cuenta_lo_que_sobra(compra):
    r, b, _ = compra
    est = {**RE.cargar_estado(r), "posiciones": [_posicion(0.0002)]}
    ahora = AHORA
    _foto_con(r, {"BTC": 0.0002}, {"BTC": {"libre": 0.0, "bloqueado": 0.0002}})     # solo lo anotado
    assert RE._sin_estado_en_la_foto(r, est, "BTC", ahora) == (True, "")
    _foto_con(r, {"BTC": 0.0005}, {"BTC": {"libre": 0.0003, "bloqueado": 0.0002}})  # 0.0003 de más
    assert RE._sin_estado_en_la_foto(r, est, "BTC", ahora) == (
        True, "la última foto de saldo fresca trae 0.0003 BTC que el estado real no conoce")
    assert RE._sin_estado_en_la_foto(r, est, "ETH", ahora) == (True, "")             # otra moneda no cuenta
    assert RE._sin_estado_en_la_foto(r, est, "BTC", ahora + timedelta(hours=3))[0] is False
