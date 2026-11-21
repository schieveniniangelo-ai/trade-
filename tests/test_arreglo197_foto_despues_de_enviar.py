"""Arreglo 197: la falsa alarma de una compra enviada sin anotar se quita solo con una foto de DESPUÉS de enviarla.

Antes (188), COMPRA_NO_LLENADA quitaba el bloqueo si la última foto de saldo fresca no traía BTC sin estado, aunque esa
foto fuera de ANTES del COMPRA_ENVIADA (una foto de antes de mandar la compra no puede decir si la compra dejó BTC). Ahora
`real._sin_estado_en_la_foto` exige además que la hora de la foto, o su update_time_cuenta, sea igual o posterior a la
del COMPRA_ENVIADA de ese boleto; si no, el bloqueo se queda y se pide una foto nueva."""
from datetime import timedelta

from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture


def _enviar_y_bloquear(r, b):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    RE.conciliar(r, AHORA + timedelta(minutes=2))
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == RE.motivo_compra_sin_anotar("BTC", b["boleto_id"])


def test_foto_de_antes_de_la_compra_no_quita_el_bloqueo(compra):
    r, b, _ = compra                                   # la foto del fixture es de AHORA − 5 min: antes del ENVIADA
    _enviar_y_bloquear(r, b)
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", motivo="EXPIRED",
                                    ahora=AHORA + timedelta(minutes=3))
    assert ok and msgs[1] == (f"❌ NO se quitó el bloqueo de compras de esta compra enviada sin anotar ({b['boleto_id']}): "
                              f"la última foto de saldo es de antes del COMPRA_ENVIADA del boleto {b['boleto_id']}: no "
                              f"dice si esa compra dejó BTC en la cuenta. Falta una foto nueva (EJECUTOR: registrar-saldo "
                              f"y conciliar --real). Puede haber BTC SIN STOP: avisa a THE BOSS con prioridad; el bloqueo "
                              f"solo lo quita Ángelo (reanudar --cartera REAL).")
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"]["motivo"] == RE.motivo_compra_sin_anotar("BTC", b["boleto_id"])
    assert "falsas_alarmas" not in est


def test_la_hora_de_la_foto_o_su_update_time(compra):
    r, b, _ = compra
    _enviar_y_bloquear(r, b)
    est = RE.cargar_estado(r)
    enviada = AHORA + timedelta(minutes=1)
    antes = (enviada - timedelta(minutes=3)).isoformat()
    ut = int(enviada.timestamp() * 1000)
    assert RE._foto_despues_de_enviar(r, {"hora_utc": enviada.isoformat()}, b["boleto_id"])          # igual vale
    assert RE._foto_despues_de_enviar(r, {"hora_utc": antes, "update_time_cuenta": ut}, b["boleto_id"])
    assert not RE._foto_despues_de_enviar(r, {"hora_utc": antes, "update_time_cuenta": ut - 1}, b["boleto_id"])
    assert not RE._foto_despues_de_enviar(r, {"hora_utc": antes, "update_time_cuenta": True}, b["boleto_id"])
    assert not RE._foto_despues_de_enviar(r, {"hora_utc": enviada.isoformat()}, "20261115-RA-COM-BTC-otro0000")
    assert RE._sin_estado_en_la_foto(r, est, "BTC", AHORA + timedelta(minutes=3)) == (True, "")   # sin boleto: igual que antes
    assert RE._sin_estado_en_la_foto(r, est, "BTC", AHORA + timedelta(minutes=3), b["boleto_id"])[0] is False


def test_con_la_foto_de_despues_si_se_quita(compra):
    r, b, foto = compra
    _enviar_y_bloquear(r, b)
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=1))     # la misma hora del ENVIADA ya vale
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", motivo="EXPIRED",
                                    ahora=AHORA + timedelta(minutes=3))
    assert ok and msgs[1].startswith("✅ Se quitó el bloqueo de compras")
    assert RE.cargar_estado(r)["bloqueo_compras"] is None
