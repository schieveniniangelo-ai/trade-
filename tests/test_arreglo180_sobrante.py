"""Arreglo 180: con una posición anotada y BTC DE MÁS en la cuenta, venta urgente solo del sobrante.

Antes, el BTC sin anotar solo se veía si NO había posición de BTC (172): con una posición anotada, el BTC de más
quedaba sin stop y nadie lo vendía (la conciliación solo decía que la cantidad no coincidía). Además el paso 5 de
bots/4_EJECUTOR_REAL.md decía vender «la cantidad libre» al cerrar, y con BTC de más eso vendía también el sobrante.
Ahora:
* registrar-saldo deja en la foto `sobrante` lo que hay de más sobre lo anotado (más que el paso y más de 1 USDT);
* conciliar --real lo marca SIN STOP, bloquea las compras y avisa a THE BOSS;
* la ronda real arma una VENTA URGENTE (motivo SIN_ANOTAR) SOLO del sobrante (nunca más que lo libre), aparte del
  cierre de la posición si toca;
* el cierre vende la cantidad que dice el boleto, no «todo lo libre».
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


@pytest.fixture
def con_pos(mundo):  # noqa: F811
    r, cfg, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    return r, cfg, foto, correr


def _boletos(r):
    return json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))


def _ventas(r):
    return [b for b in _boletos(r) if b.get("motivo") == RE.MOTIVO_SIN_ANOTAR]


def test_la_foto_marca_el_sobrante_y_sigue_sirviendo(con_pos):
    r, _, foto, _ = con_pos
    ok, msgs = foto(cuenta(usdt=USDT_CON_POS, btc=0.0003, btc_bloq=0.00012), [orden_stop()])
    assert ok                                                           # la foto sirve: la posición se sigue revisando
    f = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert f["sobrante"] == {"BTC": pytest.approx(0.0003)} and "sin_estado" not in f
    assert any(m.startswith("ℹ️ hay 0.0003 BTC de más sobre lo anotado en la posición") for m in msgs)


def test_conciliar_lo_marca_sin_stop_y_bloquea(con_pos):
    r, _, foto, _ = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.0003, btc_bloq=0.00012), [orden_stop()])
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["sin_stop"] == ["BTC"] and res["diferencias"]["sobrante"] == {"BTC": pytest.approx(0.0003)}
    assert any(t.startswith("SIN STOP: 0.0003 BTC de más — hay 0.00042 BTC en Binance y la posición anota 0.00012")
               for _, t in res["lineas"])
    assert res["avisos"] and "URGENTE" in res["avisos"][0]
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"]["motivo"] == "SIN STOP: BTC de más en la cuenta que el estado real no conoce"
    assert est["posiciones"][0]["estado_stop"] == "ACTIVO"             # la posición sí tiene su stop


def test_la_ronda_vende_solo_el_sobrante(con_pos, capsys):
    r, _, foto, correr = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.0003, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0
    (v,) = _ventas(r)
    assert not [b for b in _boletos(r) if b["accion"] == "COMPRAR"]
    assert [b for b in _boletos(r) if b["accion"] == "CERRAR"] == [v]    # el stop de la posición está vivo: sin cierre
    assert v["orden_venta"]["quantity"] == "0.0003" and v["cantidad"] == pytest.approx(0.0003)
    assert v["sobrante"] == {"sobra": pytest.approx(0.0003), "hay": pytest.approx(0.00042), "anotado": 0.00012}
    assert v["posicion_id"] is None and "orden_cancelar" not in v and RE.revisar_boleto_real(r, v, FILTROS) == []
    assert "hay 0.00042 BTC en Binance y la posición anota 0.00012: sobran 0.0003 BTC" in v["texto"]
    assert capsys.readouterr().out.startswith("❌ URGENTE: BTC sin anotar y sin stop en BTCUSDT")


def test_posicion_sin_stop_mas_sobrante_dos_boletos_que_no_se_pisan(con_pos):
    r, _, foto, correr = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00042), [])                    # todo libre: ni el stop está
    assert correr() == 0
    cierres = [b for b in _boletos(r) if b["accion"] == "CERRAR"]
    (c,) = [b for b in cierres if b.get("motivo") == "SIN_STOP"]
    (v,) = _ventas(r)
    assert c["orden_venta"]["quantity"] == "0.00012"                   # la posición: lo que dice su boleto
    assert v["orden_venta"]["quantity"] == "0.0003"                    # el sobrante: nada más
    assert c["boleto_id"] != v["boleto_id"]


def test_sobrante_en_parte_bloqueado_vende_solo_lo_libre(con_pos):
    r, _, foto, correr = con_pos
    otra = orden_stop(cantidad="0.00020000", client="spdesconocido0000", order_id=999)
    foto(cuenta(usdt=USDT_CON_POS, btc=0.0001, btc_bloq=0.00032), [orden_stop(), otra])
    assert correr() == 0
    (v,) = _ventas(r)
    assert v["orden_venta"]["quantity"] == "0.0001" and v["libre_en_la_foto"] == pytest.approx(0.0001)


def test_polvo_o_menos_del_paso_no_es_sobrante(con_pos):
    r, _, foto, correr = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.000005, btc_bloq=0.00012), [orden_stop()])   # menos del paso
    assert "sobrante" not in json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    foto(cuenta(usdt=USDT_CON_POS, btc=0.000012, btc_bloq=0.00012), [orden_stop()])   # 0.84 USDT: polvo
    assert "sobrante" not in json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert correr() == 0 and _ventas(r) == []


def test_sin_precio_se_marca_igual(con_pos, tmp_path):
    r, _, foto, _ = con_pos
    from apoyo_real import escribir_entrada
    c, o = escribir_entrada(tmp_path, cuenta(usdt=USDT_CON_POS, btc=0.0003, btc_bloq=0.00012), [orden_stop()])
    RE.registrar_saldo(r, c, o, lambda s: None, ahora=AHORA)
    assert json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))["sobrante"] == {"BTC": pytest.approx(0.0003)}


def test_abajo_del_minimo_no_sale_venta_y_avisa(con_pos, capsys):
    r, _, foto, correr = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00005, btc_bloq=0.00012), [orden_stop()])   # 3.50 USDT
    assert correr() == 0 and _ventas(r) == []
    salida = capsys.readouterr().out
    assert "❌ URGENTE: hay 0.00005 BTC libres sin anotar y sin stop" in salida and "MIN_NOTIONAL" in salida


def test_la_venta_del_sobrante_se_anota_sin_tocar_la_posicion(con_pos):
    r, _, foto, correr = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.0003, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0
    (v,) = _ventas(r)
    ok, msgs = RE.registrar_llenado(r, v["boleto_id"], "VENTA_LLENADA", cantidad=0.0003, precio=69900.0,
                                    ahora=AHORA + timedelta(minutes=3))
    assert ok and msgs[0].startswith("👍 Venta urgente anotada: 0.0003 BTC")
    est = RE.cargar_estado(r)
    assert est["posiciones"] == [dict(POS)] and est["cerradas"] == []
    assert est["ventas_sin_anotar"][0]["boleto"] == v["boleto_id"]


def test_si_la_posicion_ya_no_esta_no_hay_sobrante(con_pos):
    r, _, foto, _ = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.0003, btc_bloq=0.00012), [orden_stop()])
    est = RE.cargar_estado(r)
    foto_ = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert RE.sobrante_en_foto(r, est, foto_, AHORA)
    est["posiciones"][0]["cantidad_neta"] = 0.00042                     # ya se anotó todo
    assert RE.sobrante_en_foto(r, est, foto_, AHORA) == {}
    assert RE.sobrante_en_foto(r, {**est, "posiciones": []}, foto_, AHORA) == {}
    assert RE.sobrante_en_foto(r, est, foto_, AHORA + timedelta(hours=5)) == {}      # foto vieja
    assert RE.sobrante_en_foto(r, est, {"sobrante": {"BTC": 1}}, AHORA) == {}         # foto rara


def test_ronda_saltada_lo_dice_como_urgente(con_pos):
    r, _, foto, _ = con_pos
    foto(cuenta(usdt=USDT_CON_POS, btc=0.0003, btc_bloq=0.00012), [orden_stop()])
    (u,) = RR.pendientes_urgentes(r, AHORA)
    assert u.startswith("❌ URGENTE: la última foto de saldo (6:07 p. m. del 15/11/2026 (hora CDMX)) trae 0.0003 BTC de "
                        "más sobre lo anotado en la posición")


def test_el_texto_del_ejecutor_vende_lo_del_boleto():
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso5 = next(x for x in ej.splitlines() if x.startswith("5. Boleto de CIERRE"))
    assert "la cantidad que dice el boleto (`orden_venta`, tal cual), NO «todo lo libre»" in paso5
    assert "la cantidad libre redondeada hacia abajo al paso." not in paso5
    assert "vende SOLO ese sobrante, arreglo 180" in ej
