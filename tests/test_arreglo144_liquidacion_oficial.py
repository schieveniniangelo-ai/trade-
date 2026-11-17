"""Arreglo 144: precio de liquidación con la fórmula oficial de Binance (margen aislado, modo ONE_WAY).

LP = (WB + cum − lado·Q·EP) ÷ (Q·MMR − lado·Q), con WB = nocional ÷ apalancamiento y lado +1 (largo) o −1 (corto).
Módulo nuevo: riesgo.precio_liquidacion no cambia.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apoyo_futuros import escalones_sin_verificar
from sobreviviente import riesgo as R
from sobreviviente.futuros import liquidacion as LQ

RAIZ = Path(__file__).resolve().parent.parent
BTC_E1 = [{"escalon": 1, "nocional_min": 0.0, "nocional_max": 300000.0, "mmr_pct": 0.40, "cum": 0.0,
           "apalancamiento_max": 125}]
EP = 64609.32


@pytest.mark.parametrize("apal,lado,esperado", [
    (1, "LARGO", 0.0), (1, "CORTO", 128704.0), (2, "LARGO", 32434.0), (2, "CORTO", 96528.0),
])
def test_btc_escalon_1(apal, lado, esperado):
    lp = LQ.precio_liquidacion_aislado(EP, 0.001, lado, apal, BTC_E1)
    assert lp == pytest.approx(esperado, abs=1.0)


def test_no_depende_de_la_cantidad_dentro_del_mismo_escalon():
    a = LQ.precio_liquidacion_aislado(EP, 0.001, "LARGO", 2, BTC_E1)
    b = LQ.precio_liquidacion_aislado(EP, 0.5, "LARGO", 2, BTC_E1)
    assert a == pytest.approx(b, rel=1e-12)


def test_cambio_de_escalon_recalcula():
    esc = [
        {"escalon": 1, "nocional_min": 0.0, "nocional_max": 5000.0, "mmr_pct": 0.40, "cum": 0.0, "apalancamiento_max": 125},
        {"escalon": 2, "nocional_min": 5000.0, "nocional_max": 25000.0, "mmr_pct": 0.50, "cum": 5.0, "apalancamiento_max": 100},
    ]
    q = 4000.0 / EP                           # nocional de entrada 4,000 (escalón 1)
    lp = LQ.precio_liquidacion_aislado(EP, q, "CORTO", 1, esc)
    # Con el escalón 1 saldría ~2·EP: nocional ~8,000, que cae en el escalón 2 → se recalcula con MMR 0.5 % y cum 5
    con_e1 = (4000.0 + 0.0 + q * EP) / (q * 0.004 + q)
    con_e2 = (4000.0 + 5.0 + q * EP) / (q * 0.005 + q)
    assert q * con_e1 > 5000.0
    assert lp == pytest.approx(con_e2, rel=1e-9)
    assert LQ.escalon_de(q * lp, esc)["escalon"] == 2


def test_nocional_fuera_de_la_tabla_falla():
    with pytest.raises(LQ.ErrorEscalones):
        LQ.escalon_de(10_000_000.0, BTC_E1)


def test_tabla_de_escalones_de_las_seis_monedas():
    datos = json.loads((RAIZ / "sobreviviente" / "futuros" / "escalones.json").read_text(encoding="utf-8"))
    assert datos["fecha"] and "leverageBracket" in datos["nota_fuente"]
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"):
        esc = LQ.cargar_escalones(s)
        assert esc and esc[0]["nocional_min"] == 0.0
        assert LQ.escalon_de(25.52, esc)["escalon"] == 1     # la posición más grande de F1 cae en el escalón 1
    assert LQ.cargar_escalones("BTCUSDT")[0]["mmr_pct"] == 0.40


def test_tarifa_de_liquidacion_sale_de_exchangeinfo():
    assert LQ.tarifa_liquidacion("SOLUSDT", {"symbol": "SOLUSDT", "liquidationFee": "0.015000"}) == pytest.approx(1.5)
    assert LQ.tarifa_liquidacion("XRPUSDT", {"symbol": "XRPUSDT", "liquidationFee": "0.012500"}) == pytest.approx(1.25)
    # Sin exchangeInfo (Futuros bloqueado), la cifra consultada el 2026-11-16
    assert LQ.tarifa_liquidacion("DOGEUSDT") == pytest.approx(1.5)
    assert LQ.tarifa_liquidacion("BNBUSDT") == pytest.approx(1.25)


def test_riesgo_precio_liquidacion_no_cambia():
    assert R.precio_liquidacion(100.0, "LARGO", 2.0, 0.5) == pytest.approx(50.5)
    assert R.precio_liquidacion(100.0, "CORTO", 2.0, 0.5) == pytest.approx(149.5)


def test_errores_y_respaldos(monkeypatch):
    # Arreglo 164 (DECISIÓN DE ÁNGELO 2026-11-17): la intención era «sin verificar»
    escalones_sin_verificar(monkeypatch)
    with pytest.raises(LQ.ErrorEscalones):
        LQ.cargar_escalones("PEPEUSDT")
    with pytest.raises(LQ.ErrorEscalones):
        LQ.tarifa_liquidacion("PEPEUSDT")
    with pytest.raises(ValueError):
        LQ.precio_liquidacion_aislado(0.0, 1.0, "LARGO", 1, BTC_E1)
    assert LQ.verificado("BTCUSDT") is True and LQ.verificado("SOLUSDT") is False and LQ.verificado("X") is False
    # liquidationFee ilegible → la cifra de respaldo
    assert LQ.tarifa_liquidacion("SOLUSDT", {"symbol": "SOLUSDT", "liquidationFee": "n/a"}) == pytest.approx(1.5)


def test_si_la_liquidacion_sale_de_la_tabla_se_queda_con_el_ultimo_calculo():
    esc = [{"escalon": 1, "nocional_min": 0.0, "nocional_max": 5000.0, "mmr_pct": 0.40, "cum": 0.0,
            "apalancamiento_max": 125}]
    q = 4000.0 / EP
    lp = LQ.precio_liquidacion_aislado(EP, q, "CORTO", 1, esc)     # ~2·EP → nocional 8,000 fuera de la tabla
    assert lp == pytest.approx((4000.0 + q * EP) / (q * 0.004 + q), rel=1e-9)
