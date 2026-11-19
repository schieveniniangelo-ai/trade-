"""Arreglo 193 (R102 + I9): conciliar --real aplica la misma revisión de updateTime que registrar-saldo (184).

registrar-saldo rechaza una foto cuyo updateTime (la hora de la cuenta en Binance) es de antes del último llenado anotado.
Pero un llenado puede anotarse DESPUÉS de registrar la foto: la foto sigue «fresca» por la hora del archivo y conciliar la
usaba para comparar contra un estado que ya cambió. Ahora conciliar tampoco la usa: ❌, pide repetir la foto y no compara
nada (sin diferencias ni SIN STOP falsos por esa comparación)."""
import json
from datetime import timedelta

from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")
USDT_DESPUES = 142.54 - 0.00013 * 70100.0


def _llenar_despues_de_la_foto(r, b):
    """La foto del fixture se registró a las 00:07 UTC (updateTime 00:06). La compra se anota después."""
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", ahora=AHORA + timedelta(minutes=2), **LLENADA)[0]


def test_conciliar_rechaza_la_foto_de_antes_del_llenado(compra):
    r, b, _ = compra
    _llenar_despues_de_la_foto(r, b)
    res = RE.conciliar(r, AHORA + timedelta(minutes=3))
    assert not res["ok"] and res["foto_hora"] is None
    (e,) = [x for x in res["errores"] if "updateTime" in x]
    assert e == (f"la foto de saldo es de antes del último llenado anotado: su hora en Binance (updateTime) es 6:06 p. m. "
                 f"del 15/11/2026 (hora CDMX) y el COMPRA_LLENADA del boleto {b['boleto_id']} pasó después de 6:13 p. m. "
                 f"del 15/11/2026 (hora CDMX). Parece una foto vieja copiada otra vez (la fecha del archivo no basta): "
                 f"vuelve a pedir spot.getAccount y repite registrar-saldo")
    assert not any(t.startswith("USDT:") for _, t in res["lineas"])            # no comparó nada
    assert "usdt" not in res["diferencias"] and "sin_stop" not in res["diferencias"]
    guardada = json.loads(RE.archivo_conciliacion(r).read_text(encoding="utf-8"))
    assert guardada["ok"] is False and e in guardada["errores"]
    assert RE.conciliacion_ok(r, AHORA + timedelta(minutes=3))[0] is False


def test_con_una_foto_nueva_si_concilia(compra):
    r, b, foto = compra
    _llenar_despues_de_la_foto(r, b)
    assert RE.registrar_llenado(r, b["boleto_id"], "STOP_PUESTO", ahora=AHORA + timedelta(minutes=3), orden_id=888,
                                stop_id=b["id_stop"])[0]
    foto(cuenta(usdt=USDT_DESPUES, btc_bloq=0.00012), [orden_stop(client=b["id_stop"], order_id=888)],
         ahora=AHORA + timedelta(minutes=10))
    res = RE.conciliar(r, AHORA + timedelta(minutes=11))
    assert res["ok"] and not any("updateTime" in x for x in res["errores"])


def test_la_revision_despues_de_la_compra_dice_su_mensaje_primero(compra):
    """Con la revisión del 171 pendiente, su mensaje («de antes de la compra») va primero y basta."""
    r, b, _ = compra
    _llenar_despues_de_la_foto(r, b)
    assert RE.registrar_llenado(r, b["boleto_id"], "STOP_PUESTO", ahora=AHORA + timedelta(minutes=3), orden_id=888,
                                stop_id=b["id_stop"])[0]
    res = RE.conciliar(r, AHORA + timedelta(minutes=4))
    assert any("es de antes de la compra del boleto" in x for x in res["errores"])
    assert not any("updateTime" in x for x in res["errores"])


def test_foto_sin_update_time_no_se_rechaza_por_esto(compra):
    """Como en el 184: si la foto no trae updateTime (formato viejo), esta revisión no aplica."""
    r, b, _ = compra
    _llenar_despues_de_la_foto(r, b)
    arch = RE.archivo_saldo(r)
    f = json.loads(arch.read_text(encoding="utf-8"))
    f.pop("update_time_cuenta", None)
    arch.write_text(json.dumps(f), encoding="utf-8")
    res = RE.conciliar(r, AHORA + timedelta(minutes=3))
    assert not any("updateTime" in x for x in res["errores"]) and res["foto_hora"] is not None


def test_sin_llenados_la_foto_sirve(compra):
    r, _, _ = compra
    res = RE.conciliar(r, AHORA)
    assert res["ok"] and res["foto_hora"] is not None
