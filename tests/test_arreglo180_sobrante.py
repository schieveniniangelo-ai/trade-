"""Arreglo 180 (I4): con una posición anotada MÁS BTC de sobra, la venta urgente es solo del SOBRANTE.

Antes, el BTC de una moneda con posición nunca se contaba como «sin anotar»: si además de los 0.00012 BTC de la posición
había 0.00013 BTC que el estado real no conocía (sin stop), solo salía la diferencia en `conciliar --real` y ningún
boleto los vendía. Y el paso 5 de bots/4_EJECUTOR_REAL.md decía vender «la cantidad libre», que con BTC de sobra vendía
también lo que no era de la posición.

Ahora:
* `registrar-saldo` deja el sobrante (lo que pasa del paso y vale más de 1 USDT) en `sin_estado`; la foto se guarda
  igual (sirve para revisar el stop de la posición);
* `conciliar --real` marca «SIN STOP: BTC — hay … BTC DE MÁS en Binance, además de los … anotados» y bloquea;
* la ronda real arma la venta urgente SOLO de lo que sobra (lo libre, redondeado al paso), además del cierre de la
  posición si le falta el stop;
* el boleto de cierre y bots/4_EJECUTOR_REAL.md (paso 5) venden la cantidad del boleto, no «todo lo libre».
"""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
EXTRA = 0.00013                                    # BTC de más (unos 9.10 USDT a 70,000)


def _con_posicion(r):
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})


def _boletos(r):
    return json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))


def test_la_foto_guarda_el_sobrante_y_sigue_sirviendo(mundo):
    r, _, foto, _ = mundo
    _con_posicion(r)
    ok, msgs = foto(cuenta(usdt=USDT_CON_POS - 9.10, btc=EXTRA, btc_bloq=0.00012), [orden_stop()])
    assert ok                                                             # la foto sirve para revisar el stop
    f = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert f["ok"] is True and f["sin_estado"] == {"BTC": EXTRA}
    assert msgs == ["hay 0.00013 BTC DE MÁS en la cuenta (además de los 0.00012 anotados en la posición) que el estado "
                    "real no conoce y no tienen stop: conciliar --real lo marca SIN STOP y bloquea las compras, y la "
                    "ronda real arma la venta urgente de lo que sobra (la foto sí se guarda: sirve para revisar el stop "
                    "de la posición)"]


def test_conciliar_marca_sin_stop_el_sobrante_y_revisa_el_stop(mundo):
    r, _, foto, _ = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS - 9.10, btc=EXTRA, btc_bloq=0.00012), [orden_stop()])
    res = RE.conciliar(r, AHORA - timedelta(minutes=1))
    textos = [t for _, t in res["lineas"]]
    assert ("SIN STOP: BTC — hay 0.00013 BTC DE MÁS en Binance, además de los 0.00012 anotados en la posición, que el "
            "estado real no conoce (no tienen stop)") in textos
    assert "stop de BTC vivo (0.00012 a 59500.0)" in textos              # el stop de la posición se sigue revisando
    assert res["sin_stop"] == ["BTC"] and res["diferencias"]["sin_estado"] == {"BTC": EXTRA}
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"]["motivo"] == "SIN STOP: BTC de más en la cuenta que el estado real no conoce"
    assert est["posiciones"][0]["estado_stop"] == "ACTIVO"               # la posición tiene su stop: no se toca


def test_la_ronda_vende_solo_el_sobrante(mundo, capsys):
    r, _, foto, correr = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS - 9.10, btc=EXTRA, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0
    (v,) = _boletos(r)                                                    # ni compra ni cierre de la posición
    assert v["motivo"] == "SIN_ANOTAR" and v["orden_venta"]["quantity"] == "0.00013" and v["cantidad"] == EXTRA
    assert v["anotado_en_posicion"] == 0.00012 and v["libre_en_la_foto"] == EXTRA
    assert "hay 0.00013 BTC libres DE MÁS en Binance, además de los 0.00012 BTC anotados en la posición" in v["texto"]
    assert "la cantidad del boleto, no todo lo libre" in v["texto"]
    assert RE.revisar_boleto_real(r, v, FILTROS) == []
    assert capsys.readouterr().out.startswith("❌ URGENTE: BTC sin anotar y sin stop en BTCUSDT")


def test_sin_el_stop_de_la_posicion_salen_el_cierre_y_la_venta_del_sobrante(mundo):
    r, _, foto, correr = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS - 9.10, btc=0.00012 + EXTRA), [])      # todo libre: el stop no está
    assert correr() == 0
    cierre, venta = _boletos(r)
    assert (cierre["motivo"], cierre["orden_venta"]["quantity"]) == ("SIN_STOP", "0.00012")
    assert (venta["motivo"], venta["orden_venta"]["quantity"]) == ("SIN_ANOTAR", "0.00013")     # juntos: todo


def test_el_sobrante_bloqueado_no_se_vende(mundo, capsys):
    r, _, foto, correr = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS - 9.10, btc_bloq=0.00012 + EXTRA), [orden_stop(), orden_stop(client="otra")])
    assert correr() == 0
    assert not [b for b in _boletos(r) if b.get("motivo") == "SIN_ANOTAR"]
    assert "hay 0.00013 BTC sin anotar bloqueados en órdenes abiertas" in capsys.readouterr().out


@pytest.mark.parametrize("extra", [0.00001, 0.000013])
def test_el_polvo_y_el_redondeo_no_son_sobrante(mundo, extra):
    r, _, foto, _ = mundo
    _con_posicion(r)
    ok, msgs = foto(cuenta(usdt=USDT_CON_POS, btc=extra, btc_bloq=0.00012), [orden_stop()])
    f = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert "sin_estado" not in f and msgs == []                         # ≤ el paso, o menos de 1 USDT


def test_una_foto_de_antes_de_anotar_la_compra_no_cuenta_la_compra_como_sobrante(mundo):
    r, _, foto, _ = mundo
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])   # sin posición todavía: todo es sin_estado
    assert json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))["sin_estado"] == {"BTC": 0.00012}
    _con_posicion(r)                                                      # después se anota la compra
    est = RE.cargar_estado(r)
    foto_guardada = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert RE.btc_sin_anotar(r, est, foto_guardada, AHORA - timedelta(minutes=1)) == {}
    res = RE.conciliar(r, AHORA - timedelta(minutes=1), escribir=False)
    assert res["sin_stop"] == [] and "sin_estado" not in res["diferencias"]
    assert RR.pendientes_urgentes(r) == []


def test_la_venta_del_sobrante_se_anota_sin_tocar_la_posicion(mundo):
    r, _, foto, correr = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS - 9.10, btc=EXTRA, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0
    (v,) = _boletos(r)
    ok, msgs = RE.registrar_llenado(r, v["boleto_id"], "VENTA_LLENADA", cantidad=EXTRA, precio=69900.0,
                                    ahora=AHORA + timedelta(minutes=3))
    assert ok and msgs[0].startswith("👍 Venta urgente anotada")
    est = RE.cargar_estado(r)
    assert len(est["posiciones"]) == 1 and est["cerradas"] == [] and est["ventas_sin_anotar"][0]["cantidad"] == EXTRA


def test_ronda_saltada_dice_el_sobrante(mundo):
    r, _, foto, _ = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS - 9.10, btc=EXTRA, btc_bloq=0.00012), [orden_stop()])
    assert RR.pendientes_urgentes(r) == [
        "❌ URGENTE: la última foto de saldo (6:07 p. m. del 15/11/2026 (hora CDMX)) trae 0.00013 BTC DE MÁS (además de "
        "los 0.00012 anotados en la posición) que el estado real no conoce: no tiene stop anotado. Avisa a Ángelo con "
        "prioridad: vender sin boleto solo lo decide él."]


def test_sin_precio_tambien_cuenta_y_sin_activos_no(mundo):
    r, _, _, _ = mundo
    _con_posicion(r)
    est = RE.cargar_estado(r)
    assert RE.sobrante(est, {"activos": {}}, "BTC") == 0.0 and RE.sobrante(est, {}, "BTC") == 0.0
    assert RE.sobrante(est, {"activos": {"BTC": {"libre": "x", "bloqueado": 0.00025}}}, "BTC") == EXTRA
    from apoyo_real import escribir_entrada
    import os
    c, o = escribir_entrada(Path(RE.ruta_real(r)) / "e", cuenta(btc=EXTRA, btc_bloq=0.00012), [orden_stop()])
    for x in (c, o):
        os.utime(x, ((AHORA).timestamp() - 60,) * 2)
    ok, msgs = RE.registrar_saldo(r, c, o, lambda s: None, ahora=AHORA)
    assert json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))["sin_estado"] == {"BTC": EXTRA}


def test_textos_del_boleto_de_cierre_y_del_ejecutor(mundo):
    r, _, _, _ = mundo
    b = RE.boleto_cierre_real(r, "2026-11-20", POS, "SALIDA_M0")
    assert "VENDE 0.00012 BTC a MERCADO (la cantidad del boleto, no todo lo libre" in b["texto"]
    assert "o lo libre, redondeado" not in b["texto"]
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso5 = ej[ej.index("5. Boleto de CIERRE"):ej.index("5b. Boleto de VENTA URGENTE")]
    assert "copiando TAL CUAL `orden_venta` del boleto (SELL MARKET, la cantidad que dice el boleto)" in paso5
    assert "No vendas «todo lo libre»" in paso5 and "la cantidad libre redondeada" not in paso5
    paso5b = ej[ej.index("5b. Boleto de VENTA URGENTE"):ej.index("6. Foto final")]
    assert "«DE MÁS»" in paso5b and "vende SOLO la cantidad del boleto" in paso5b
