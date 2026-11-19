"""Arreglo 192 (R100): los avisos de la ronda real saltada (mantenimiento de Binance o red caída) también dicen la
REVISIÓN pendiente justo después de una compra (171) y el bloqueo de compras con su motivo.

Antes (178) salían el renglón ilegible, las compras enviadas sin anotar, el BTC sin anotar y las posiciones sin stop,
pero no que una compra seguía sin su revisión (nadie confirmó que el stop está vivo) ni que las compras estaban
bloqueadas y por qué. Todo sale del estado LOCAL, sin red y sin escribir nada."""
from datetime import timedelta

from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture
from test_arreglo178_saltada_urgentes import _correr, saltar  # noqa: F401 - fixture

LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")
REVISION = ("❌ URGENTE: falta la revisión justo después de la compra del boleto {b} (stop puesto 6:15 p. m. del 15/11/2026 "
            "(hora CDMX)): nadie ha confirmado con una foto de saldo que el stop esté vivo. EJECUTOR: foto de saldo "
            "(registrar-saldo) y conciliar --real en cuanto se pueda; avisa a THE BOSS.")


def _comprar_sin_revisar(r, b):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", ahora=AHORA + timedelta(minutes=2), **LLENADA)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "STOP_PUESTO", ahora=AHORA + timedelta(minutes=3), orden_id=888,
                                stop_id=b["id_stop"])[0]


def test_la_revision_pendiente_sale_urgente(compra, saltar, capsys):
    r, b, _ = compra
    _comprar_sin_revisar(r, b)
    antes = RE.archivo_estado(r).read_bytes()
    urgentes, _ = _correr(r, saltar, capsys, ahora=AHORA + timedelta(days=1))
    assert REVISION.format(b=b["boleto_id"]) in urgentes
    assert not any("BLOQUEADAS" in u for u in urgentes)                    # sin bloqueo, no se dice
    assert RE.archivo_estado(r).read_bytes() == antes                      # no escribe nada


def test_el_bloqueo_sale_con_su_motivo(compra, saltar, capsys):
    r, b, _ = compra
    est = RE.cargar_estado(r)
    est["bloqueo_compras"] = {"desde": "2026-11-16T00:20:00+00:00", "motivo": "SIN STOP: BTC"}
    RE.guardar_estado(r, est)
    urgentes, _ = _correr(r, saltar, capsys, ahora=AHORA + timedelta(days=1))
    assert ("❌ Compras reales BLOQUEADAS por SIN STOP: BTC (desde 6:20 p. m. del 15/11/2026 (hora CDMX)) → solo Ángelo "
            "las reanuda (reanudar --cartera REAL o ajustar-capital-real).") in urgentes
    assert not any("falta la revisión" in u for u in urgentes)


def test_los_dos_juntos_y_en_orden(compra):
    r, b, _ = compra
    _comprar_sin_revisar(r, b)
    est = RE.cargar_estado(r)
    est["bloqueo_compras"] = {"desde": "fecha rara", "motivo": "la revisión justo después de la compra no cuadró"}
    RE.guardar_estado(r, est)
    urg = RR.pendientes_urgentes(r)
    i = urg.index(REVISION.format(b=b["boleto_id"]))
    assert urg[i + 1] == ("❌ Compras reales BLOQUEADAS por la revisión justo después de la compra no cuadró (desde sin "
                          "hora) → solo Ángelo las reanuda (reanudar --cartera REAL o ajustar-capital-real).")


def test_formas_raras_no_truenan():
    assert RR._revision_y_bloqueo({RE.REVISION: True, "bloqueo_compras": "SIN STOP"}) == [
        "❌ URGENTE: falta la revisión justo después de la compra del boleto ? (stop puesto sin hora): nadie ha confirmado "
        "con una foto de saldo que el stop esté vivo. EJECUTOR: foto de saldo (registrar-saldo) y conciliar --real en "
        "cuanto se pueda; avisa a THE BOSS.",
        "❌ Compras reales BLOQUEADAS por SIN STOP (desde sin hora) → solo Ángelo las reanuda (reanudar --cartera REAL o "
        "ajustar-capital-real)."]
    assert RR._revision_y_bloqueo({"bloqueo_compras": {}}) == []          # vacío = sin bloqueo
    assert RR._revision_y_bloqueo({"bloqueo_compras": None}) == []


def test_con_la_revision_hecha_ya_no_sale(compra):
    r, b, foto = compra
    _comprar_sin_revisar(r, b)
    foto(cuenta(usdt=142.54 - 0.00013 * 70100.0, btc_bloq=0.00012), [orden_stop(client=b["id_stop"], order_id=888)],
         ahora=AHORA + timedelta(minutes=10))
    assert RE.conciliar(r, AHORA + timedelta(minutes=11))["ok"]
    assert not any("falta la revisión" in u for u in RR.pendientes_urgentes(r))
