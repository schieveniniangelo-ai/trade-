"""Arreglo 132: formato del boleto real y su revisión (cierra R3, R6, R8, R9).

Con las reglas reales de BTCUSDT guardadas (tests/datos_arreglo132/btcusdt_filtros.json), sin llamar a Binance:
con 142.54 USDT y BTC a 70,000, la compra de la Cartera A es 0.00013 BTC = 9.10 USDT, riesgo 1.365 USDT y un stop de
0.00012 BTC que vale 7.10 USDT; con volatilidad ALTA, A se salta por capital (4.20 USDT); B da 18.90 y C 42.70."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import reglamento
from sobreviviente import riesgo as R
from sobreviviente.exchange import Filtros, filtros_desde_exchangeinfo

FIXTURE = Path(__file__).parent / "datos_arreglo132" / "btcusdt_filtros.json"
EMITIDO = datetime(2026, 11, 16, 0, 11, tzinfo=timezone.utc)


@pytest.fixture
def f():
    return filtros_desde_exchangeinfo(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def reg():
    r = reglamento.cargar()
    r.datos["estrategias"]["M0"]["estado"] = "VIVA_MINI"
    return r


def test_filtros_lee_las_reglas_nuevas_sin_cambiar_las_viejas(f):
    assert (f.tick, f.paso, f.cantidad_min, f.minimo_usdt, f.estado) == (0.01, 0.00001, 0.00001, 5.0, "TRADING")
    assert (f.bid_mult_up, f.bid_mult_down, f.ask_mult_up, f.ask_mult_down) == (1.2, 0.5, 2.0, 0.8)
    assert f.minimo_a_mercado is True and f.max_algo == 5
    viejo = Filtros("XUSDT", 0.01, 0.001, 0.001, 5.0)          # sin los filtros nuevos: valores por defecto
    assert (viejo.ask_mult_down, viejo.minimo_a_mercado, viejo.max_algo) == (0.0, False, 0)


def _decision(reg, cartera, f, vol="NORMAL", capital=142.54):
    rgc = reg.para_cartera(cartera)
    lim = P._limite_stop(59500.0, f, P.limites_ejecucion(reg)[1])
    c = R.Candidato("BTCUSDT", "SPOT", "LARGO", "M0", "normales", 70000.0, 59500.0, None, lim, 0.1, 0.05)
    e = R.EstadoCartera(capital=capital, pico=capital, capital_inicio_dia=capital, capital_inicio_semana=capital,
                        efectivo_spot=capital)
    return R.evaluar_candidato(rgc, e, c, f, EMITIDO, regimen_btc="ALCISTA", vol_moneda=vol, vol_btc="NORMAL")


def test_cifras_fijas_de_a_b_y_c(reg, f):
    a = _decision(reg, "A", f)
    assert a.aprobada and a.cantidad == 0.00013 and round(a.cantidad * 70000, 2) == 9.10
    assert round(a.riesgo_usdt, 3) == 1.365
    alta = _decision(reg, "A", f, vol="ALTA")
    assert not alta.aprobada and alta.saltada_por_capital and "4.20 USDT" in alta.razon
    assert round(_decision(reg, "B", f).valor_usdt, 2) == 18.90
    assert round(_decision(reg, "C", f).valor_usdt, 2) == 42.70


def test_boleto_de_compra_real(reg, f):
    a = _decision(reg, "A", f)
    b = RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, a.cantidad, f, EMITIDO)
    assert b["boleto_id"].startswith("20261115-RA-COM-BTC-") and len(b["boleto_id"]) == len("20261115-RA-COM-BTC-") + 8
    assert (b["modo"], b["cartera"], b["reglas_de"], b["accion"], b["estrategia"]) == ("REAL", "REAL", "A", "COMPRAR", "M0")
    assert b["version_reglamento"] == reg.version and b["precio_referencia"] == 70000.0
    assert b["emitido_utc"] == "2026-11-16T00:11:00Z" and b["vence_utc"] == "2026-11-16T02:10:00Z"
    oc = b["orden_compra"]
    assert oc == {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT", "timeInForce": "FOK", "quantity": "0.00013",
                  "price": "70210", "newClientOrderId": oc["newClientOrderId"], "newOrderRespType": "FULL"}
    assert oc["newClientOrderId"].startswith("bp") and len(oc["newClientOrderId"]) == 18
    st = b["orden_stop"]
    assert st == {"symbol": "BTCUSDT", "side": "SELL", "type": "STOP_LOSS_LIMIT", "timeInForce": "GTC",
                  "quantity": "0.00012", "stopPrice": "59500", "price": "59202.5", "newClientOrderId": b["id_stop"]}
    assert b["id_stop"] == P.id_stop(b["boleto_id"], 0)
    assert b["valor_compra_usdt"] == pytest.approx(9.10) and round(b["valor_venta_stop_usdt"], 2) == 7.10
    assert b["riesgo_usdt"] == pytest.approx(1.365) and b["stop_pct"] == pytest.approx(15.0)
    assert b["riesgo_pct"] == pytest.approx(1.365 / 142.54 * 100, abs=1e-4)
    assert (b["paso_cantidad"], b["tick_precio"], b["minimo_usdt"], b["cantidad_minima"], b["apalancamiento"]) == \
        (0.00001, 0.01, 5.0, 0.00001, 1)
    ns = b["no_comprar_si"]
    assert ns["precio_actual_mayor_que"] == 70210.0 and ns["precio_actual_menor_o_igual_que"] == pytest.approx(60690.0)
    assert ns["precio_actual_mayor_que_por_percent_price"] == pytest.approx(59202.5 / 0.8)
    assert ns["multiplicador_percent_price"] == 0.8 and ns["valor_menor_que_usdt"] == pytest.approx(5.25)
    assert "executedQty − commission" in b["reglas_para_la_cantidad_del_stop"] and "HACIA ABAJO" in \
        b["reglas_para_la_cantidad_del_stop"] and "BNB" in b["reglas_para_la_cantidad_del_stop"]
    assert "llenado_papel" not in b and b["texto"].startswith("[REAL] [") and "FOK" in b["texto"]
    assert "ganancia" in b["texto"] and "promesa" in b["texto"]       # no promete ganancias
    assert RE.revisar_boleto_real(reg, b, f) == []
    b2 = RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, a.cantidad, f, EMITIDO)
    assert b2["boleto_id"] == b["boleto_id"] and b2["orden_compra"]["newClientOrderId"] == oc["newClientOrderId"]


def test_revision_rechaza_lo_que_no_cumple(reg, f):
    b = RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, 0.00013, f, EMITIDO)
    chico = RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, 0.00007, f, EMITIDO)
    assert any("mínimo + margen" in e for e in RE.revisar_boleto_real(reg, chico, f))   # 4.90 USDT < 5.25
    lejos = json.loads(json.dumps(b))
    lejos["orden_stop"]["price"] = "50000"
    lejos["orden_stop"]["stopPrice"] = "50100"
    assert any("PERCENT_PRICE_BY_SIDE" in e for e in RE.revisar_boleto_real(reg, lejos, f))
    for cambio, palabra in ((("modo", "PAPEL"), "no es un boleto REAL"), (("accion", "MODIFICAR_STOP"), "no permitida"),
                            (("apalancamiento", 2), "apalancamiento"), (("version_reglamento", "1.0"), "reglamento")):
        x = {**b, cambio[0]: cambio[1]}
        assert any(palabra in e for e in RE.revisar_boleto_real(reg, x, f))
    mal = json.loads(json.dumps(b))
    mal["orden_compra"]["timeInForce"] = "GTC"
    mal["orden_stop"]["type"] = "STOP_LOSS"
    mal["orden_compra"]["quantity"] = "0.000001"
    errores = RE.revisar_boleto_real(reg, mal, f)
    assert any("FOK" in e for e in errores) and any("STOP_LOSS_LIMIT" in e for e in errores)
    assert any("cantidad mínima" in e for e in errores)
    al_reves = json.loads(json.dumps(b))
    al_reves["orden_stop"]["stopPrice"] = "71000"
    assert any("entre su límite" in e for e in RE.revisar_boleto_real(reg, al_reves, f))
    assert RE.revisar_boleto_real(reg, "hola", f) == ["no es un boleto (formato raro): no lo pongas"]


POS = {"id": "20261115-RA-COM-BTC-abcd1234", "simbolo": "BTCUSDT", "estrategia": "M0", "cantidad_neta": 0.000129,
       "id_stop": "sp0123456789abcdef", "orden_id_stop": 123, "paso_cantidad": 0.00001}


@pytest.mark.parametrize("motivo, urgente", [("SALIDA_M0", False), ("STOP_SIN_LLENAR", True), ("SIN_STOP", True)])
def test_boleto_de_cierre_real(reg, motivo, urgente):
    b = RE.boleto_cierre_real(reg, "2026-11-20", POS, motivo)
    assert b["accion"] == "CERRAR" and b["modo"] == "REAL" and b["motivo"] == motivo and b["urgente"] is urgente
    assert b["boleto_id"].startswith("20261120-RA-CER-BTC-")
    assert b["orden_cancelar"] == {"symbol": "BTCUSDT", "origClientOrderId": "sp0123456789abcdef", "orderId": 123}
    assert b["orden_venta"] == {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.00012",
                                "newOrderRespType": "FULL"}
    assert ("URGENTE" in b["texto"]) is urgente and b["apalancamiento"] == 1
    assert RE.revisar_boleto_real(reg, b, None) == []


def test_cierre_informativo_y_motivo_desconocido(reg):
    b = RE.boleto_cierre_real(reg, "2026-11-20", POS, "STOP_EJECUTADO")
    assert b["solo_informativo"] is True and "orden_venta" not in b and "NO vendas" in b["texto"]
    with pytest.raises(ValueError):
        RE.boleto_cierre_real(reg, "2026-11-20", POS, "PORQUE_SI")


def test_en_real_nunca_hay_modificar_stop_ni_cancel_replace(reg, f):
    assert RE.ACCIONES_REALES == ("COMPRAR", "CERRAR")
    todos = [RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, 0.00013, f, EMITIDO)]
    todos += [RE.boleto_cierre_real(reg, "2026-11-20", POS, m) for m in RE.MOTIVOS_CIERRE]
    texto = json.dumps(todos, ensure_ascii=False)
    assert "MODIFICAR_STOP" not in texto and "cancelReplace" not in texto.replace("cancelar", "")
    fuente = (Path(RE.__file__)).read_text(encoding="utf-8")
    assert "def boleto_modificar" not in fuente and '"MODIFICAR_STOP"' not in fuente


def test_boletos_de_papel_dicen_papel(reg, tmp_path):
    from test_arreglo1_papel import _dia_marea_alta, _reg_m0
    from test_papel import _datos_dia
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    c = P.ronda_cartera(r, "C", dd, [], [])
    assert c["boletos"]
    for b in c["boletos"]:
        assert b["modo"] == "PAPEL" and b["texto"] == "[PAPEL — NO PONER] " + P.texto_boleto(b)
