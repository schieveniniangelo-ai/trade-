"""Arreglo 183: COMPRA_NO_LLENADA con motivo, para cuando Binance rechaza la compra; quita la falsa alarma SIN STOP.

Antes, si Binance RECHAZABA la compra (un error, sin orden creada), bots/4_EJECUTOR_REAL.md no decía qué anotar: la
COMPRA_ENVIADA quedaba sin resultado, `conciliar --real` la contaba SIN STOP y ponía `bloqueo_compras` (que solo quita
Ángelo), aunque no hubiera BTC. Ahora:
* COMPRA_NO_LLENADA lleva `--motivo` (el status o el mensaje de error de Binance, tal cual), que queda en
  llenados.jsonl; sin motivo se anota igual (nunca se rechaza anotar lo que pasó en Binance), con un ⚠️;
* cierra la compra enviada: ya no hay SIN STOP, y si el bloqueo de compras lo puso ESA compra sin anotar, se quita
  (queda constancia en `bloqueos_quitados`); con BTC sin anotar en la última foto, o con otro bloqueo, sigue;
* bots/4_EJECUTOR_REAL.md (paso 4e) dice cuándo y cómo anotarla.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
RECHAZO = "-2010 Account has insufficient balance for requested action."


def _enviada_y_conciliada(r, b):
    """COMPRA_ENVIADA, Binance rechaza la compra y el EJECUTOR no alcanza a anotarla: conciliar bloquea."""
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    res = RE.conciliar(r, AHORA + timedelta(minutes=2))
    assert res["sin_stop"] == ["BTC"]
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == f"SIN STOP: BTC (compra enviada sin anotar, boleto " \
                                                               f"{b['boleto_id']})"


def _no_llenada(r, b, motivo=RECHAZO, minutos=3):
    return RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", motivo=motivo,
                                ahora=AHORA + timedelta(minutes=minutos))


def test_rechazo_de_binance_quita_la_alarma_y_el_bloqueo(compra):
    r, b, _ = compra
    _enviada_y_conciliada(r, b)
    ok, msgs = _no_llenada(r, b)
    assert ok and msgs[0] == f"👍 Anotado: la compra no se llenó; no hay posición (no se reintenta). Motivo: {RECHAZO}."
    assert msgs[1].startswith("👍 Quité la falsa alarma: el bloqueo de compras («SIN STOP: BTC (compra enviada sin "
                              "anotar, boleto")
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"] is None and est["posiciones"] == []
    assert est["bloqueos_quitados"][0]["por"] == f"COMPRA_NO_LLENADA {b['boleto_id']}"
    assert RE.leer_llenados(r)[-1]["motivo"] == RECHAZO
    res = RE.conciliar(r, AHORA + timedelta(minutes=4))                # ya no hay SIN STOP
    assert res["ok"] and res["sin_stop"] == [] and res["avisos"] == []


def test_la_siguiente_compra_ya_no_se_frena(compra):
    r, b, _ = compra
    _enviada_y_conciliada(r, b)
    assert _no_llenada(r, b)[0]
    b2 = RE.boleto_compra_real(r, "2026-11-16", "BTCUSDT", 70000.0, 59500.0, 0.00013, FILTROS,
                               AHORA + timedelta(days=1))
    RR.archivo_boletos(r, "2026-11-16").write_text(json.dumps([b2]), encoding="utf-8")
    ok, msgs = RE.registrar_llenado(r, b2["boleto_id"], "COMPRA_ENVIADA", precio_actual=70000.0,
                                    ahora=AHORA + timedelta(days=1, minutes=1))
    assert ok, msgs


def test_sin_motivo_se_anota_igual_con_aviso(compra):
    r, b, _ = compra
    _enviada_y_conciliada(r, b)
    ok, msgs = _no_llenada(r, b, motivo="")
    assert ok and msgs[0] == "👍 Anotado: la compra no se llenó; no hay posición (no se reintenta)."
    assert msgs[1].startswith("⚠️ Sin --motivo: la próxima vez di por qué no se llenó")
    assert RE.cargar_estado(r)["bloqueo_compras"] is None


def test_otro_bloqueo_no_se_quita(compra):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    RE.guardar_estado(r, {**RE.cargar_estado(r), "bloqueo_compras": {"desde": "x", "motivo": "SIN STOP: BTC"}})
    ok, msgs = _no_llenada(r, b)
    assert ok and len(msgs) == 1 and RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == "SIN STOP: BTC"


def test_el_bloqueo_de_otra_compra_no_se_quita(compra):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    otro = RE.motivo_bloqueo_compra_sin_anotar("BTC", "20261114-RA-COM-BTC-00000000")
    RE.guardar_estado(r, {**RE.cargar_estado(r), "bloqueo_compras": {"desde": "x", "motivo": otro}})
    assert _no_llenada(r, b)[0] and RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == otro


def test_con_btc_sin_anotar_en_la_foto_el_bloqueo_sigue(compra):
    r, b, foto = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    foto(cuenta(usdt=133.44, btc=0.00013), [], ahora=AHORA + timedelta(minutes=2))   # sí hay BTC
    RE.conciliar(r, AHORA + timedelta(minutes=2))
    ok, msgs = _no_llenada(r, b)
    assert ok and msgs[-1].startswith("⚠️ El bloqueo de compras sigue: la última foto de saldo trae BTC que el estado "
                                      "real no conoce")
    assert RE.cargar_estado(r)["bloqueo_compras"] is not None


def test_por_la_linea_de_comandos(compra, monkeypatch, capsys):
    r, b, _ = compra
    _enviada_y_conciliada(r, b)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return AHORA + timedelta(minutes=3)
    monkeypatch.setattr(RE, "datetime", Reloj)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA",
                      "--motivo", RECHAZO]) == 0
    salida = capsys.readouterr().out
    assert f"Motivo: {RECHAZO}." in salida and "Quité la falsa alarma" in salida
    assert RE.cargar_estado(r)["bloqueo_compras"] is None


def test_el_texto_del_ejecutor():
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso4 = ej[ej.index("4. Boleto de COMPRA"):ej.index("5. Boleto de CIERRE")]
    assert "Binance RECHAZÓ la compra" in paso4
    assert "--evento COMPRA_NO_LLENADA --motivo \"<status o el mensaje de error de Binance, tal cual>\"" in paso4
    assert "quita la falsa alarma SIN STOP y el bloqueo que puso esa compra sin anotar (arreglo 183)" in paso4
