"""Arreglo 178 (I2): si la ronda real se salta (mantenimiento de Binance o red caída), lo pendiente del estado LOCAL sale
primero, como URGENTE.

Antes (166) solo se decían las posiciones sin stop confirmado, y solo con Binance en mantenimiento; con la red caída
(cualquier otra falla) no se decía nada. Ahora, en los dos casos, antes del mensaje de la ronda saltada salen:
* un renglón ilegible de llenados.jsonl (176);
* cada COMPRA_ENVIADA sin su resultado (puede haber BTC sin stop);
* el BTC que la última foto de saldo trae y el estado real no conoce;
* cada posición SIN STOP (sin stop confirmado).
Todo sin red y sin escribir nada: vender sin boleto solo lo decide Ángelo.
"""
import json
from datetime import timedelta

import pytest

from sobreviviente import archivos as AR
from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

DIA2 = AHORA + timedelta(days=1)
MANTENIMIENTO = "Binance tiene BTCUSDT en estado BREAK (no TRADING)"


@pytest.fixture(params=["mantenimiento", "red_caida"])
def saltar(request, monkeypatch):
    """La ronda real se salta: Binance en mantenimiento (BinanceNoOpera) o la red caída (cualquier otra falla)."""
    def preparar(reg, cli, memes, ahora=None, **kw):
        if request.param == "mantenimiento":
            raise P.BinanceNoOpera(MANTENIMIENTO)
        raise ConnectionError("sin red: no se pudo conectar con api.binance.com")

    def activar():
        monkeypatch.setattr(P, "preparar_datos", preparar)
    activar.caso = request.param
    return activar


def _correr(r, saltar, capsys, simular=False, ahora=AHORA):
    saltar()
    capsys.readouterr()
    assert RR.correr(r, ahora, cliente=object(), memes=[], simular=simular) == 1
    lineas = capsys.readouterr().out.splitlines()
    assert lineas[0] == "████ REAL ████"
    final = "se saltó completa porque" if saltar.caso == "mantenimiento" else "❌ La ronda real NO corrió: sin red"
    i = next(n for n, x in enumerate(lineas) if final in x)
    return lineas[1:i], lineas[i:]


def test_compra_enviada_sin_llenado_sale_urgente_primero(compra, saltar, capsys):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1))[0]
    antes = RE.archivo_estado(r).read_bytes()
    urgentes, _ = _correr(r, saltar, capsys, ahora=DIA2)          # la ronda del 15 ya corrió (la del boleto)
    assert urgentes == [f"❌ URGENTE: compra enviada sin anotar (boleto {b['boleto_id']}, COMPRA_ENVIADA, 6:13 p. m. del "
                        f"15/11/2026 (hora CDMX)): puede haber BTC SIN STOP en Binance. EJECUTOR: revisa esa compra con "
                        f"spot.getOrder y anota cómo terminó (COMPRA_LLENADA, COMPRA_PARCIAL o COMPRA_NO_LLENADA); avisa "
                        f"a Ángelo con prioridad: vender sin boleto solo lo decide él."]
    assert RE.archivo_estado(r).read_bytes() == antes                   # no se escribió nada (ni el bloqueo)


def test_btc_sin_anotar_en_la_ultima_foto_sale_urgente(mundo, saltar, capsys):
    r, _, foto, _ = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    urgentes, _ = _correr(r, saltar, capsys)
    assert urgentes == ["❌ URGENTE: la última foto de saldo (6:07 p. m. del 15/11/2026 (hora CDMX)) trae 0.00013 BTC "
                        "que el estado real no conoce: no tiene stop anotado. Avisa a Ángelo con prioridad: vender sin "
                        "boleto solo lo decide él."]


def test_posicion_sin_stop_sale_urgente(mundo, saltar, capsys):
    r, _, foto, _ = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [{**POS, "estado_stop": "SIN_STOP"}]})
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    urgentes, _ = _correr(r, saltar, capsys)
    assert len(urgentes) == 1
    assert urgentes[0].startswith("❌ URGENTE: BTC no tiene stop confirmado (estado SIN_STOP) y hoy no hay boletos")


def test_renglon_ilegible_sale_urgente(mundo, saltar, capsys):
    r, _, foto, _ = mundo
    foto()
    RE.archivo_llenados(r).write_text("{roto", encoding="utf-8")
    urgentes, _ = _correr(r, saltar, capsys)
    assert urgentes == ["❌ URGENTE: llenados.jsonl (datos/real) tiene 1 renglón(es) ilegible(s) (#1): puede ser una "
                        "compra a medio anotar (un COMPRA_ENVIADA cortado) y entonces no se sabe si hay BTC sin stop. No "
                        "se compra nada hasta que Ángelo lo revise en Binance y arregle ese renglón a mano (arreglo 176)."]


def test_todos_juntos_en_orden_y_antes_que_lo_demas(compra, saltar, capsys):
    r, b, foto = compra
    foto(cuenta(usdt=133.44, btc=0.00013), [], ahora=AHORA - timedelta(minutes=1))
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1))[0]
    with open(RE.archivo_llenados(r), "a", encoding="utf-8") as f:
        f.write("{roto\n")
    urgentes, resto = _correr(r, saltar, capsys, ahora=DIA2)
    assert [u.split(":")[1].strip()[:20] for u in urgentes] == ["llenados.jsonl (dato", "compra enviada sin a",
                                                                "la última foto de sa"]
    assert all(u.startswith("❌ URGENTE: ") for u in urgentes) and not any("URGENTE" in x for x in resto)


def test_sin_pendientes_no_dice_urgente(mundo, saltar, capsys):
    r, _, foto, _ = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    urgentes, _ = _correr(r, saltar, capsys)
    assert urgentes == []


def test_simulando_tambien_los_dice_y_no_registra(compra, saltar, capsys):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1))[0]
    filas = len(AR.leer_registro(r))
    urgentes, _ = _correr(r, saltar, capsys, simular=True, ahora=DIA2)
    assert len(urgentes) == 1 and "compra enviada sin anotar" in urgentes[0]
    assert len(AR.leer_registro(r)) == filas


def test_estado_danado_y_foto_rara(mundo, monkeypatch):
    r, _, foto, _ = mundo
    RE.archivo_estado(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    (u,) = RR.pendientes_urgentes(r)
    assert u.startswith("❌ URGENTE: no pude leer el estado real")
    RE.archivo_estado(r).unlink()
    RE.archivo_saldo(r).write_text(json.dumps({"hora_utc": "no es hora", "ok": False, "sin_estado": {"BTC": "mucho"}}),
                                   encoding="utf-8")
    assert RR.pendientes_urgentes(r) == []                                # foto dañada (sin hora): no se lee
    RE.archivo_saldo(r).write_text(json.dumps({"hora_utc": "2026-11-16T00:07:00+00:00", "ok": False,
                                               "sin_estado": {"BTC": "mucho"}}), encoding="utf-8")
    assert RR.pendientes_urgentes(r) == ["❌ URGENTE: la última foto de saldo (6:07 p. m. del 15/11/2026 (hora CDMX)) "
                                         "trae mucho BTC que el estado real no conoce: no tiene stop anotado. Avisa a "
                                         "Ángelo con prioridad: vender sin boleto solo lo decide él."]
    monkeypatch.setattr(RE, "por_que_llenados_rotos", lambda reg: (_ for _ in ()).throw(PermissionError("x")))
    assert RR.pendientes_urgentes(r)[0] == "❌ URGENTE: no pude leer llenados.jsonl (PermissionError)."


def test_hora_rara_y_btc_ya_anotado_en_una_posicion(mundo):
    """Un COMPRA_ENVIADA con hora que no se entiende dice «sin hora»; el BTC de una foto vieja (de antes de anotar la
    compra) que ya está en una posición no se repite: la posición tiene su propio renglón (si no tiene stop)."""
    r, _, foto, _ = mundo
    foto(cuenta(usdt=133.44, btc=0.00012))                              # la foto se tomó antes de anotar la compra
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    RE.archivo_llenados(r).write_text(json.dumps({"evento": "COMPRA_ENVIADA", "boleto_id": "20261114-RA-COM-BTC-00000000",
                                                  "hora_utc": "no se entiende"}) + "\n", encoding="utf-8")
    (u,) = RR.pendientes_urgentes(r)
    assert u.startswith("❌ URGENTE: compra enviada sin anotar (boleto 20261114-RA-COM-BTC-00000000, COMPRA_ENVIADA, "
                        "sin hora): puede haber BTC SIN STOP")
