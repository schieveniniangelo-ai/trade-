"""Arreglo 157: la liquidación no se cuenta dos veces (SOLO PAPEL).

Fuente oficial: https://www.binance.com/en/support/faq/binance-futures-liquidation-protocols-360033525271 — la tarifa de
liquidación «se descuenta de los activos que sostienen la posición» y no se cobra si la posición queda en quiebra. En
margen AISLADO la pérdida máxima es el margen de esa posición. Antes se cobraba el margen MÁS la tarifa (en
backtest.simular_operacion y en futuros/cartera.cerrar). Ahora: pérdida = min(margen, pérdida hasta la liquidación +
tarifa sobre el nocional). Con precio_liq=None todo queda igual (Arreglo 148).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente.estrategias import f1 as F1
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import config
from sobreviviente.futuros import liquidacion as LQ
from sobreviviente.futuros import tamano as T
from sobreviviente.futuros import validar as VF
from apoyo_futuros import escalones_supuesto_viejo
from test_arreglo151_validar_futuros import _mercado, _reg

IDX = pd.date_range("2026-01-01", periods=6, freq="4h", tz="UTC")
GEST = {"modo": "chandelier", "chandelier_atr": 3.0, "sin_breakeven": True}
AHORA = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
CFG = dict(config.POR_DEFECTO)


def _arr(precio, marca_l=None, marca_h=None):
    o = np.full(6, precio)
    a = {"o": o, "h": o * 1.01, "l": o * 0.99, "c": o, "atr": np.full(6, precio * 0.3),
         "marca_h": o * 1.01, "marca_l": o * 0.99}
    if marca_l is not None:
        a["marca_l"] = a["marca_l"].copy()
        a["marca_l"][3] = marca_l
    if marca_h is not None:
        a["marca_h"] = a["marca_h"].copy()
        a["marca_h"][3] = marca_h
    return a


def test_sol_a_2x_con_valor_21_pierde_exactamente_el_margen_en_la_simulacion(monkeypatch):
    escalones_supuesto_viejo(monkeypatch)      # Arreglo 164: la intención era el supuesto conservador de 1 %
    entrada, q = 70.0, 0.3                                     # 21 USDT de valor, 10.5 de margen a 2x
    esc = LQ.cargar_escalones("SOLUSDT")
    liq = LQ.precio_liquidacion_aislado(entrada, q, "LARGO", 2, esc)
    assert liq == pytest.approx(entrada * 0.5 / 0.99)           # MMR supuesto de 1 %, cum 0
    r = B.simular_operacion(_arr(entrada, marca_l=liq * 0.98), IDX, 0, "LARGO", entrada, 5.0, None, GEST, 0.05, 0.0,
                            pd.Timedelta(hours=4), apalancamiento=2.0, precio_liq=liq, tarifa_liq_pct=1.5)
    assert r["liquidada"] is True and r["motivo"] == "liquidación"
    perdida = -(r["pnl_unidad"] + r["comision_unidad"]) * q   # sin la comisión de entrada (esa siempre se paga)
    assert perdida == pytest.approx(10.5)                      # exactamente el margen…
    assert perdida != pytest.approx(10.5 + 0.315)              # …no el margen más la tarifa (21 × 1.5 %)
    assert r["tarifa_liq_unidad"] == pytest.approx(liq * 1.5 / 100)   # la tarifa nominal se sigue reportando


def test_si_la_perdida_hasta_la_liquidacion_mas_la_tarifa_es_menor_que_el_margen_se_cobra_esa():
    # Corto a 1x con la liquidación puesta a mano en 150 (margen 100): 50 hasta la liquidación + 1.5 % de 150 = 52.25
    r = B.simular_operacion(_arr(100.0, marca_h=160.0), IDX, 0, "CORTO", 100.0, 190.0, None, GEST, 0.05, 0.0,
                            pd.Timedelta(hours=4), apalancamiento=1.0, precio_liq=150.0, tarifa_liq_pct=1.5)
    assert r["liquidada"] is True
    assert r["pnl_unidad"] + r["comision_unidad"] == pytest.approx(-(50.0 + 150.0 * 0.015))


def test_sin_precio_liq_nada_cambia():
    a = _arr(100.0, marca_l=40.0)
    viejo = B.simular_operacion(a, IDX, 0, "LARGO", 100.0, 5.0, None, GEST, 0.05, 0.0, pd.Timedelta(hours=4),
                                apalancamiento=2.0, mantenimiento_pct=0.5)
    assert viejo["liquidada"] is True                           # liquidación estimada (Arreglo 120): margen completo
    assert viejo["pnl_unidad"] == pytest.approx(-50.0 - 100.0 * 0.0005)
    assert "tarifa_liq_unidad" not in viejo


def test_la_misma_regla_en_la_cartera():
    e = C.estado_nuevo(CFG, AHORA)
    esc = LQ.cargar_escalones("SOLUSDT")
    liq = LQ.precio_liquidacion_aislado(70.0, 0.3, "LARGO", 2, esc)
    t = T.Tamano(True, "cabe", 0.3, 21.0, 2, 10.5, 0.3 * 5, 0.4254, liq)
    p = C.abrir(e, "SOLUSDT", "LARGO", 70.0, 70.0, 65.0, t, AHORA, F1.gestion(F1.POR_DEFECTO), 0.05)
    comision_entrada = p["comisiones"]
    neta = C.cerrar(e, p, liq, "liquidación", AHORA, CFG, 0.05, 0.05, tarifa_liq_pct=1.5)
    assert neta == pytest.approx(-10.5 - comision_entrada)       # el margen, sin la tarifa encima
    assert e["capital"] == pytest.approx(42.54 - comision_entrada - 10.5)
    # Corto con liquidación a mano: pierde lo que hay hasta la liquidación más la tarifa (menos que el margen)
    e2 = C.estado_nuevo(CFG, AHORA)
    t2 = T.Tamano(True, "cabe", 0.1, 10.0, 1, 10.0, 0.5, 0.4254, 150.0)
    p2 = C.abrir(e2, "SOLUSDT", "CORTO", 100.0, 100.0, 190.0, t2, AHORA, F1.gestion(F1.POR_DEFECTO), 0.05)
    neta2 = C.cerrar(e2, p2, 150.0, "liquidación", AHORA, CFG, 0.05, 0.05, tarifa_liq_pct=1.5)
    assert neta2 == pytest.approx(-(50.0 * 0.1 + 150.0 * 0.1 * 0.015) - p2["comisiones"])


def test_el_resultado_de_f1_no_cambia_porque_no_hay_liquidaciones(tmp_path):
    """Huella de F1 base en 5619f84 (antes de este arreglo) en la corrida corta del mercado sintético."""
    res = VF.evaluar(_mercado(_reg(tmp_path)), robustez_on=False)
    assert res.resumen["liquidaciones"] == 0
    r = res.oos["r"].to_numpy(float)
    clave = ";".join(f"{a}|{b.isoformat()}|{c}" for a, b, c in zip(res.oos["simbolo"], res.oos["t_senal"],
                                                                    res.oos["lado"]))
    assert len(r) == 25 and hashlib.sha256(clave.encode()).hexdigest()[:16] == "a4143ed548c34d03"
    assert float(r.sum()) == pytest.approx(13.36894547064314, rel=1e-9)
    assert res.estres["operaciones"] == 25 and res.estres["expectativa_r"] == pytest.approx(0.48954954354560243, rel=1e-9)
