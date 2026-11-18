"""Arreglo 182: COMPRA_ENVIADA pide --precio-actual y revisa el boleto EN CÓDIGO antes de anotar.

Antes, las reglas `no_comprar_si` del boleto (precio arriba del límite, muy cerca del stop, PERCENT_PRICE, abajo del
mínimo) y el vencimiento solo los revisaba el EJECUTOR a mano (paso 4b). Ahora `registrar-llenado --real --evento
COMPRA_ENVIADA` exige `--precio-actual` (el de spot.tickerPrice) y revisa:
* que el boleto no esté vencido (vence_utc);
* cada regla de `no_comprar_si` con ese precio.
Si algo falla, no anota nada y sale ❌ «NO mandes la compra: … Avisa a THE BOSS». El precio queda en el renglón.
"""
import json
from datetime import datetime, timedelta

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE

from apoyo_real import AHORA
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

ENVIADA = "COMPRA_ENVIADA"


def _enviar(r, b, precio, cuando=AHORA + timedelta(minutes=1)):
    return RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=cuando, precio_actual=precio)


def test_con_precio_bueno_se_anota_y_queda_el_precio(compra):
    r, b, _ = compra
    ok, msgs = _enviar(r, b, 70050.5)
    assert ok and msgs[0].startswith("👍 Compra ENVIADA anotada")
    (fila,) = RE.leer_llenados(r)
    assert fila["precio_actual"] == 70050.5


@pytest.mark.parametrize("precio", [None, 0, -1, "no", float("nan")])
def test_sin_precio_no_se_anota(compra, precio):
    r, b, _ = compra
    ok, msgs = _enviar(r, b, precio)
    assert not ok and msgs[0].startswith("NO mandes la compra: falta --precio-actual (el precio de spot.tickerPrice")
    assert "No se anotó nada. Avisa a THE BOSS" in msgs[0] and RE.leer_llenados(r) == []


def test_boleto_vencido(compra):
    r, b, _ = compra
    ok, msgs = _enviar(r, b, 70000.0, cuando=AHORA + timedelta(hours=3))     # vence a las 02:10 UTC
    assert not ok and msgs[0].startswith("NO mandes la compra: el boleto venció a las 8:10 p. m. del 15/11/2026")
    assert RE.leer_llenados(r) == []


@pytest.mark.parametrize("regla, delta, pedazo", [
    ("precio_actual_mayor_que", 0.01, "es mayor que el límite de compra"),
    ("precio_actual_menor_o_igual_que", 0.0, "está muy cerca del stop"),
    ("precio_actual_menor_o_igual_que", -100.0, "está muy cerca del stop"),
])
def test_reglas_de_no_comprar_si(compra, regla, delta, pedazo):
    r, b, _ = compra
    ok, msgs = _enviar(r, b, b["no_comprar_si"][regla] + delta)
    assert not ok and msgs[0].startswith("NO mandes la compra: el precio actual") and pedazo in msgs[0]
    assert RE.leer_llenados(r) == []


def test_justo_en_el_limite_si_se_puede(compra):
    r, b, _ = compra
    assert _enviar(r, b, b["no_comprar_si"]["precio_actual_mayor_que"])[0]


def test_percent_price(compra):
    r, b, _ = compra
    b2 = json.loads(json.dumps(b))
    b2["no_comprar_si"]["precio_actual_mayor_que_por_percent_price"] = 70000.0     # más estricto que el límite
    _guardar(r, b2)
    ok, msgs = _enviar(r, b2, 70100.0)
    assert not ok and "Binance rechazaría el stop por PERCENT_PRICE_BY_SIDE" in msgs[0]


def test_abajo_del_minimo(compra):
    r, b, _ = compra
    b2 = json.loads(json.dumps(b))
    b2["no_comprar_si"]["valor_menor_que_usdt"] = 50.0
    _guardar(r, b2)
    ok, msgs = _enviar(r, b2, 70000.0)
    assert not ok and "la compra valdría 9.10 USDT, menos que el mínimo con margen (50.00 USDT)" in msgs[0]


@pytest.mark.parametrize("cambio, pedazo", [
    ({"no_comprar_si": None}, "el boleto no trae no_comprar_si"),
    ({"no_comprar_si": {"precio_actual_mayor_que": 1}}, "el boleto trae no_comprar_si incompleto"),
    ({"vence_utc": None}, "no trae una hora de vencimiento que se entienda"),
    ({"vence_utc": "mañana"}, "no trae una hora de vencimiento que se entienda"),
])
def test_boleto_raro_no_se_anota(compra, cambio, pedazo):
    r, b, _ = compra
    b2 = {**b, **cambio}
    _guardar(r, b2)
    ok, msgs = _enviar(r, b2, 70000.0)
    assert not ok and pedazo in msgs[0] and RE.leer_llenados(r) == []


def test_los_bloqueos_del_171_y_173_van_antes(compra):
    r, b, _ = compra
    RE.guardar_estado(r, {**RE.cargar_estado(r), "bloqueo_compras": {"motivo": "SIN STOP: BTC"}})
    ok, msgs = _enviar(r, b, None)
    assert not ok and "compras reales bloqueadas" in msgs[0] and "precio-actual" not in msgs[0]


def test_por_la_linea_de_comandos(compra, monkeypatch, capsys):
    r, b, _ = compra
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return AHORA + timedelta(minutes=1)
    monkeypatch.setattr(RE, "datetime", Reloj)
    base = ["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", ENVIADA]
    capsys.readouterr()
    assert MAIN.main(base) == 1
    assert capsys.readouterr().out.startswith("❌ NO mandes la compra: falta --precio-actual")
    assert MAIN.main(base + ["--precio-actual", "80000"]) == 1
    assert "es mayor que el límite de compra" in capsys.readouterr().out
    assert MAIN.main(base + ["--precio-actual", "70000"]) == 0
    assert RE.leer_llenados(r)[0]["precio_actual"] == 70000.0


def test_el_boleto_y_el_ejecutor_lo_dicen(compra):
    from pathlib import Path
    r, b, _ = compra
    assert "--evento COMPRA_ENVIADA --precio-actual <precio de spot.tickerPrice>" in b["antes_de_comprar"]
    assert "registra COMPRA_ENVIADA con --precio-actual" in b["texto"]
    ej = (Path(__file__).resolve().parent.parent / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    assert "--evento COMPRA_ENVIADA --precio-actual <precio de spot.tickerPrice>" in ej and "arreglo 182" in ej


def _guardar(r, b):
    from sobreviviente import ronda_real as RR
    RR.archivo_boletos(r, "2026-11-15").write_text(json.dumps([b]), encoding="utf-8")
