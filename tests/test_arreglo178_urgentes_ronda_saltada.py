"""Arreglo 178: si la ronda real se salta (Binance en mantenimiento o la red caída), primero van los pendientes URGENTES.

Antes, con la ronda saltada (166) solo se decían las posiciones sin stop confirmado, y con la red caída (cualquier otra
falla) ni eso. Pero sin ronda no hay boletos: ni venta urgente (172) ni cierre. Ahora, en los dos casos, justo debajo
del encabezado y antes del «❌ La ronda real NO corrió», se dicen como URGENTE los pendientes de los archivos locales
(sin red): una COMPRA_ENVIADA sin resultado anotado, BTC que la última foto de saldo trae y el estado no conoce, y las
posiciones SIN STOP. También un llenados.jsonl con renglones ilegibles (176).
"""
from datetime import timedelta

import pytest

from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo135_salidas_real import POS, USDT_CON_POS
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

DIA2 = AHORA + timedelta(days=1)
FALLAS = {"mantenimiento": (P.BinanceNoOpera("BTCUSDT está en estado HALT (no TRADING)"), "se saltó completa porque"),
          "red_caida": (OSError("sin red"), "❌ La ronda real NO corrió: sin red")}


def _saltar(monkeypatch, falla):
    error, _ = FALLAS[falla]

    def preparar(*a, **k):
        raise error
    monkeypatch.setattr(P, "preparar_datos", preparar)


def _correr_saltada(r, monkeypatch, capsys, falla, ahora=AHORA):
    _saltar(monkeypatch, falla)
    capsys.readouterr()
    assert RR.correr(r, ahora, cliente=object(), memes=[]) == 1
    lineas = capsys.readouterr().out.splitlines()
    assert lineas[0] == "████ REAL ████"
    return lineas


def _resto(lineas, falla):
    """Las líneas después de los urgentes: el mensaje de siempre."""
    i = next(i for i, x in enumerate(lineas) if FALLAS[falla][1] in x)
    return lineas[1:i], lineas[i:]


@pytest.mark.parametrize("falla", FALLAS)
def test_compra_enviada_sin_llenado(compra, monkeypatch, capsys, falla):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    urgentes, resto = _resto(_correr_saltada(r, monkeypatch, capsys, falla, DIA2), falla)
    (u,) = urgentes
    assert u.startswith(f"❌ URGENTE: la compra del boleto {b['boleto_id']} se mandó (COMPRA_ENVIADA, 6:13 p. m. del "
                        f"15/11/2026 (hora CDMX)) y no tiene resultado anotado: puede haber BTC SIN STOP en Binance")
    assert f"spot.getOrder (origClientOrderId={b['orden_compra']['newClientOrderId']})" in u
    assert "avisa a Ángelo con prioridad" in u and resto


@pytest.mark.parametrize("falla", FALLAS)
def test_btc_sin_anotar(mundo, monkeypatch, capsys, falla):
    r, _, foto, _ = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    urgentes, resto = _resto(_correr_saltada(r, monkeypatch, capsys, falla), falla)
    (u,) = urgentes
    assert u.startswith("❌ URGENTE: la última foto de saldo (6:07 p. m. del 15/11/2026 (hora CDMX)) trae 0.00013 BTC que "
                        "el estado real no tiene anotado: no tiene stop y hoy no hay boletos")
    assert "él decide en Binance" in u


@pytest.mark.parametrize("falla", FALLAS)
def test_posicion_sin_stop(mundo, monkeypatch, capsys, falla):
    r, _, foto, _ = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [{**POS, "estado_stop": "SIN_STOP"}]})
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    urgentes, _ = _resto(_correr_saltada(r, monkeypatch, capsys, falla), falla)
    (u,) = urgentes
    assert u.startswith("❌ URGENTE: BTC no tiene stop confirmado (estado SIN_STOP) y hoy no hay boletos")


@pytest.mark.parametrize("falla", FALLAS)
def test_los_tres_juntos_en_orden(compra, monkeypatch, capsys, falla):
    r, b, foto = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    est = RE.cargar_estado(r)
    est["posiciones"] = [{**POS, "simbolo": "ETHUSDT", "estado_stop": "SIN_STOP"}]
    RE.guardar_estado(r, est)
    foto(cuenta(usdt=133.44, btc=0.00013), [], ahora=DIA2 - timedelta(minutes=5))
    urgentes, _ = _resto(_correr_saltada(r, monkeypatch, capsys, falla, DIA2), falla)
    assert [u.split(":")[1].strip()[:20] for u in urgentes] == [
        "la compra del boleto", "la última foto de sa", "ETH no tiene stop co"]


@pytest.mark.parametrize("falla", FALLAS)
def test_sin_pendientes_no_dice_urgente(mundo, monkeypatch, capsys, falla):
    r, _, foto, _ = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    lineas = _correr_saltada(r, monkeypatch, capsys, falla)
    assert not [x for x in lineas if "URGENTE" in x]


def test_btc_en_posicion_no_sale_como_sin_anotar(mundo):
    r, _, foto, _ = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))                               # la foto trae sin_estado BTC…
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})   # …y ya se anotó
    assert RR.pendientes_urgentes(r, AHORA) == []


def test_llenados_rotos_y_estado_danado(mundo, monkeypatch):
    r, _, foto, _ = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    arch = RE.archivo_llenados(r)
    arch.write_text("{roto\n", encoding="utf-8")
    u, btc = RR.pendientes_urgentes(r, AHORA)
    assert u.startswith("❌ URGENTE: llenados.jsonl tiene 1 renglón(es) ilegible(s)") and "0.00013 BTC" in btc
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    urgentes = RR.pendientes_urgentes(r, AHORA)                         # sin estado no se sabe qué está anotado
    assert urgentes[-1].startswith("❌ URGENTE: no pude leer el estado real") and len(urgentes) == 2


def test_compra_enviada_con_hora_rara_y_llenados_que_no_se_leen(mundo, monkeypatch):
    r, _, _, _ = mundo
    RE.archivo_llenados(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_llenados(r).write_text('{"evento": "COMPRA_ENVIADA", "boleto_id": "20261114-RA-COM-BTC-00000000", '
                                      '"hora_utc": "no se entiende"}\n', encoding="utf-8")
    (u,) = RR.pendientes_urgentes(r, AHORA)
    assert "(COMPRA_ENVIADA, sin hora)" in u
    monkeypatch.setattr(RE, "llenados_rotos", lambda reg: (_ for _ in ()).throw(PermissionError("sin permiso")))
    (u,) = RR.pendientes_urgentes(r, AHORA)
    assert u.startswith("❌ URGENTE: no pude leer datos/real/llenados.jsonl (PermissionError)")


def test_foto_con_hora_rara(mundo, monkeypatch):
    r, _, _, _ = mundo
    monkeypatch.setattr(RE, "leer_foto", lambda reg, ahora=None: ({"sin_estado": {"BTC": "mucho"}}, "rara"))
    (u,) = RR.pendientes_urgentes(r, AHORA)
    assert u.startswith("❌ URGENTE: la última foto de saldo (sin hora) trae mucho BTC")
