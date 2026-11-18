"""Arreglo 172: boleto de VENTA URGENTE para el BTC que el estado real no tiene anotado.

Antes (170), si conciliar --real encontraba BTC en el saldo que el estado no conocía (o un COMPRA_ENVIADA sin su
resultado), lo marcaba SIN STOP, bloqueaba y avisaba, pero nadie armaba la venta. Ahora la ronda real arma un boleto de
VENTA URGENTE para ese BTC, igual que el cierre de una posición sin stop:
* un CERRAR (motivo SIN_ANOTAR) que vende a MERCADO solo lo LIBRE de una foto fresca (lo bloqueado no se toca);
* la misma revisión (revisar_boleto_real y ronda --verificar --real: LOT_SIZE, MARKET_LOT_SIZE, MIN_NOTIONAL; a mercado,
  sin precio límite, como el cierre SIN_STOP);
* el mismo flujo del EJECUTOR (paso 5b): vende y registra VENTA_LLENADA.
Sin foto fresca, o si no llega al mínimo de Binance, no sale venta: sale un ❌ URGENTE (nunca se vende a ciegas).
El código no manda órdenes: solo arma el boleto.
"""
import dataclasses
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import Cli, compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
DIA2 = AHORA + timedelta(days=1)
ENVIADA = "COMPRA_ENVIADA"
USDT_TRAS_COMPRA = 142.54 - 0.00013 * 70100.0


def _boletos(r, dia="2026-11-15"):
    return json.loads(RR.archivo_boletos(r, dia).read_text(encoding="utf-8"))


def _ventas(boletos):
    return [x for x in boletos if x.get("motivo") == RE.MOTIVO_SIN_ANOTAR]


def _enviada_y_btc_libre(compra_, capsys, btc=0.00012987, bloq=0.0, ordenes=()):
    """El EJECUTOR anotó COMPRA_ENVIADA, mandó la compra y se cayó: al día siguiente la foto trae el BTC."""
    r, b, foto = compra_
    assert RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=AHORA + timedelta(minutes=1))[0]
    foto(cuenta(usdt=USDT_TRAS_COMPRA, btc=btc, btc_bloq=bloq), list(ordenes), ahora=DIA2 - timedelta(minutes=5))
    capsys.readouterr()
    assert RR.correr(r, DIA2, cliente=object(), memes=[]) == 0
    return r, b, _boletos(r, "2026-11-16"), capsys.readouterr().out


def test_btc_libre_sin_anotar_sale_venta_urgente(mundo, capsys):
    r, _, foto, correr = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    assert correr() == 0
    (v,) = _boletos(r)
    assert v["accion"] == "CERRAR" and v["modo"] == "REAL" and v["motivo"] == "SIN_ANOTAR" and v["urgente"] is True
    assert v["boleto_id"].startswith("20261115-RA-CER-BTC-") and v["apalancamiento"] == 1 and v["vence_utc"] is None
    assert v["orden_venta"] == {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.00013",
                                "newClientOrderId": RE.id_venta(v["boleto_id"]),        # arreglo 181
                                "newOrderRespType": "FULL"}
    assert "orden_cancelar" not in v and v["posicion_id"] is None and v["compras_sin_anotar"] == []
    assert v["valor_venta_usdt"] == pytest.approx(9.10) and RE.revisar_boleto_real(r, v, FILTROS) == []
    salida = capsys.readouterr().out
    assert salida.startswith("❌ URGENTE: BTC sin anotar y sin stop en BTCUSDT — EJECUTOR debe venderlo ya")
    assert v["texto"] in salida and "VENDE 0.00013 BTC a MERCADO" in v["texto"]
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"].startswith("SIN STOP: BTC")
    assert RE.cargar_estado(r)["posiciones"] == []                     # no se inventa una posición


def test_compra_enviada_sin_anotar_y_btc_libre(compra, capsys):
    r, b, boletos, salida = _enviada_y_btc_libre(compra, capsys)
    assert not [x for x in boletos if x["accion"] == "COMPRAR"]
    (v,) = _ventas(boletos)
    assert v["compras_sin_anotar"] == [b["boleto_id"]] and v["posicion_id"] == b["boleto_id"]
    assert v["orden_venta"]["quantity"] == "0.00012" and v["cantidad"] == 0.00012        # hacia abajo al paso
    assert f"compra enviada sin anotar: boleto {b['boleto_id']}" in v["texto"]
    assert salida.startswith("❌ URGENTE: BTC sin anotar y sin stop")


def test_lo_bloqueado_no_se_vende(compra, capsys):
    otra = orden_stop(cantidad="0.00012000", client="spdesconocido0000", order_id=999)
    r, b, boletos, salida = _enviada_y_btc_libre(compra, capsys, btc=0.0001, bloq=0.00012, ordenes=[otra])
    (v,) = _ventas(boletos)
    assert v["orden_venta"]["quantity"] == "0.0001" and "orden_cancelar" not in v      # solo lo libre


def test_todo_bloqueado_no_sale_venta_y_avisa(compra, capsys):
    otra = orden_stop(cantidad="0.00012000", client="spdesconocido0000", order_id=999)
    r, b, boletos, salida = _enviada_y_btc_libre(compra, capsys, btc=0.0, bloq=0.00012, ordenes=[otra])
    assert boletos == []
    assert "❌ URGENTE: hay 0.00012 BTC sin anotar bloqueados en órdenes abiertas" in salida
    assert "nada libre" in salida and RE.cargar_estado(r)["bloqueo_compras"]


def test_menos_del_minimo_no_sale_venta_y_avisa(mundo, capsys):
    r, _, foto, correr = mundo
    foto(cuenta(usdt=139.04, btc=0.00005))                             # unos 3.50 USDT: más de 1, menos de 5
    assert correr() == 0 and _boletos(r) == []
    salida = capsys.readouterr().out
    assert "❌ URGENTE: hay 0.00005 BTC libres sin anotar y sin stop" in salida and "MIN_NOTIONAL" in salida
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"].startswith("SIN STOP: BTC")


def test_sin_btc_en_la_foto_no_sale_venta(compra, capsys):
    r, b, foto = compra
    RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=AHORA + timedelta(minutes=1))
    foto(cuenta(), [], ahora=DIA2 - timedelta(minutes=5))              # la compra no se llenó
    capsys.readouterr()
    assert RR.correr(r, DIA2, cliente=object(), memes=[]) == 0
    assert _boletos(r, "2026-11-16") == [] and "❌ URGENTE" not in capsys.readouterr().out


def test_sin_foto_fresca_no_se_vende_a_ciegas(compra, capsys):
    r, b, foto = compra
    RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=AHORA + timedelta(minutes=1))
    capsys.readouterr()
    assert RR.correr(r, DIA2, cliente=object(), memes=[]) == 0         # la foto es de ayer
    assert _boletos(r, "2026-11-16") == []
    salida = capsys.readouterr().out
    assert salida.startswith(f"❌ URGENTE: puede haber BTC sin stop (compra enviada sin anotar: boleto {b['boleto_id']}) "
                             f"y sin una foto de saldo fresca no sé cuánto hay: no sale venta urgente")


def test_foto_vieja_con_btc_no_vende(mundo, capsys):
    r, _, foto, correr = mundo
    foto(cuenta(usdt=133.44, btc=0.00013), ahora=AHORA - timedelta(minutes=130))
    assert correr() == 0 and _boletos(r) == []


def test_btc_sin_anotar_con_foto_rara_no_da_nada(mundo):
    r = mundo[0]
    est = RE.cargar_estado(r)
    assert RE.btc_sin_anotar(r, est, None, AHORA) == {}
    assert RE.btc_sin_anotar(r, est, {"sin_estado": {"BTC": 1.0}, "hora_utc": "raro"}, AHORA) == {}
    assert RE.btc_sin_anotar(r, est, {"sin_estado": {"BTC": 1.0}}, AHORA) == {}


def _venta(r):
    return RE.boleto_venta_sin_anotar(r, "2026-11-15", "BTCUSDT", 0.00013, 70000.0, FILTROS)


@pytest.mark.parametrize("cambio, pedazo", [
    (lambda v: v["orden_venta"].update(type="LIMIT", price="69000"), "no es una VENTA a MERCADO"),
    (lambda v: v["orden_venta"].update(side="BUY"), "no es una VENTA a MERCADO"),
    (lambda v: v["orden_venta"].update(price="69000"), "va a MERCADO, sin precio límite"),
    (lambda v: v.update(simbolo="ETHUSDT") or v["orden_venta"].update(symbol="ETHUSDT"), "no es de la moneda del real"),
    (lambda v: v["orden_venta"].update(quantity="0.000125"), "LOT_SIZE"),
    (lambda v: v["orden_venta"].update(quantity="0.00005"), "MIN_NOTIONAL"),
    (lambda v: v["orden_venta"].update(quantity="0"), "la cantidad a vender es 0"),
    (lambda v: v.update(orden_compra={"side": "BUY"}), "no compra ni cancela"),
    (lambda v: v.update(accion="COMPRAR"), "tiene que ser un CERRAR"),
    (lambda v: v.update(precio_referencia=None), "no trae precio de referencia"),
])
def test_la_revision_rechaza_ventas_raras(mundo, cambio, pedazo):
    r = mundo[0]
    v = _venta(r)
    assert RE.revisar_boleto_real(r, v, FILTROS) == []
    cambio(v)
    assert any(pedazo in e for e in RE.revisar_boleto_real(r, v, FILTROS)), RE.revisar_boleto_real(r, v, FILTROS)


def test_market_lot_size_se_respeta(mundo):
    r = mundo[0]
    f = dataclasses.replace(FILTROS, paso_mercado=0.0001, cantidad_min_mercado=0.0002, cantidad_max_mercado=0.0003)
    v = RE.boleto_venta_sin_anotar(r, "2026-11-15", "BTCUSDT", 0.00013, 70000.0, f)
    assert v["orden_venta"]["quantity"] == "0.0001"                    # también al paso de MARKET_LOT_SIZE
    assert any("MARKET_LOT_SIZE minQty" in e for e in RE.revisar_boleto_real(r, v, f))
    v["orden_venta"]["quantity"] = "0.00013"
    assert any("(MARKET_LOT_SIZE)" in e for e in RE.revisar_boleto_real(r, v, f))
    v["orden_venta"]["quantity"] = "0.0004"
    assert any("MARKET_LOT_SIZE maxQty" in e for e in RE.revisar_boleto_real(r, v, f))
    assert RE.revisar_boleto_real(r, v, None) == []                    # sin reglas: lo de Binance lo revisa verificar


def test_verificar_real_aprueba_la_venta_urgente(mundo, capsys):
    r, _, foto, correr = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    assert correr() == 0
    (v,) = _boletos(r)
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 0
    assert f"✅ {v['boleto_id']}" in capsys.readouterr().out


def test_venta_llenada_se_anota_y_cierra_la_compra_enviada(compra, capsys):
    r, b, boletos, _ = _enviada_y_btc_libre(compra, capsys)
    (v,) = _ventas(boletos)
    ok, msgs = RE.registrar_llenado(r, v["boleto_id"], "VENTA_LLENADA", cantidad=0.00012, precio=69900.0,
                                    comision=0.0084, moneda_comision="USDT", ahora=DIA2 + timedelta(minutes=5))
    assert ok and msgs[0].startswith("👍 Venta urgente anotada: 0.00012 BTC a 69900")
    assert "solo Ángelo la resuelve" in msgs[1]
    est = RE.cargar_estado(r)
    (venta,) = est["ventas_sin_anotar"]
    assert venta["cubre"] == [b["boleto_id"]] and venta["usdt_neto"] == pytest.approx(0.00012 * 69900.0 - 0.0084)
    assert est["posiciones"] == [] and est["cerradas"] == [] and est["bloqueo_compras"]   # sigue bloqueado
    assert RE.leer_llenados(r)[-1]["cubre"] == [b["boleto_id"]] and RE.compras_sin_anotar(r) == []
    assert "ya está registrado" in RE.registrar_llenado(r, v["boleto_id"], "VENTA_LLENADA", cantidad=0.00012,
                                                        precio=69900.0)[1][0]
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-16", DIA2 + timedelta(minutes=6), Cli()) == 1
    assert f"❌ {v['boleto_id']}: YA REGISTRADO" in capsys.readouterr().out
    # La foto de después: ya no hay BTC sin stop; queda la diferencia de USDT (la resuelve Ángelo)
    foto = compra[2]
    foto(cuenta(usdt=USDT_TRAS_COMPRA + 0.00012 * 69900.0 - 0.0084, btc=0.00000987), [],
         ahora=DIA2 + timedelta(minutes=7))
    res = RE.conciliar(r, DIA2 + timedelta(minutes=8))
    assert res["sin_stop"] == [] and "compra_sin_anotar" not in res["diferencias"] and "usdt" in res["diferencias"]
    assert not res["ok"]


@pytest.mark.parametrize("evento, kw, pedazo", [
    ("CIERRE_DE_EMERGENCIA", dict(cantidad=0.00012, precio=69900.0), "solo se anota VENTA_LLENADA"),
    ("STOP_EJECUTADO", dict(cantidad=0.00012, precio=69900.0), "solo se anota VENTA_LLENADA"),
    ("VENTA_LLENADA", dict(cantidad=0.0002, precio=69900.0), "es mayor que la de la venta urgente"),
    ("VENTA_LLENADA", dict(cantidad=0.00012), "faltan --cantidad y --precio"),
    (ENVIADA, {}, "no es de compra"),
])
def test_la_venta_urgente_solo_acepta_su_venta(compra, capsys, evento, kw, pedazo):
    r, b, boletos, _ = _enviada_y_btc_libre(compra, capsys)
    (v,) = _ventas(boletos)
    antes = RE.leer_llenados(r)
    ok, msgs = RE.registrar_llenado(r, v["boleto_id"], evento, ahora=DIA2 + timedelta(minutes=5), **kw)
    assert not ok and pedazo in msgs[0]
    assert RE.leer_llenados(r) == antes and "ventas_sin_anotar" not in RE.cargar_estado(r)


def test_si_la_compra_ya_se_anoto_la_venta_cierra_la_posicion(compra, capsys):
    r, b, boletos, _ = _enviada_y_btc_libre(compra, capsys)
    (v,) = _ventas(boletos)
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", orden_id=777, cantidad=0.00013, precio=70100.0,
                                comision=0.00000013, moneda_comision="BTC", ahora=DIA2 + timedelta(minutes=3))[0]
    ok, msgs = RE.registrar_llenado(r, v["boleto_id"], "VENTA_LLENADA", cantidad=0.00012, precio=69900.0,
                                    comision=0.0084, moneda_comision="USDT", ahora=DIA2 + timedelta(minutes=5))
    assert ok and msgs[0].startswith("👍 Salida anotada")
    est = RE.cargar_estado(r)
    assert est["posiciones"] == [] and est["cerradas"][0]["boleto_cierre"] == v["boleto_id"]
    assert "ventas_sin_anotar" not in est


def test_simular_no_escribe(mundo, capsys):
    r, _, foto, correr = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    assert correr(simular=True) == 0
    salida = capsys.readouterr().out
    assert "Boletos REALES que saldrían" in salida and "VENTA URGENTE de BTC SIN ANOTAR" in salida
    assert not RR.archivo_boletos(r, "2026-11-15").exists() and RE.cargar_estado(r)["bloqueo_compras"] is None


def test_texto_del_ejecutor():
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso = ej[ej.index("5b. Boleto de VENTA URGENTE"):ej.index("6. Foto final")]
    assert ej.index("5. Boleto de CIERRE") < ej.index("5b. Boleto de VENTA URGENTE")
    for frase in ("`SIN_ANOTAR`", "No hay stop que cancelar", "`orden_venta`", "nunca más de lo que tengas libre",
                  "No toques lo bloqueado", "No pongas un stop en vez de vender", "--evento VENTA_LLENADA",
                  "reintenta una vez"):
        assert frase in paso, frase
    assert "futuros" not in ej and "F1" not in ej
