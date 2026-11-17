"""Arreglo 164: escalones reales de Binance en escalones.json (DECISIÓN DE ÁNGELO 2026-11-17). SOLO PAPEL.

MECÁNICO copió el 2026-11-17 las tablas de la página PÚBLICA Leverage & Margin de Binance (sin entrar a ninguna cuenta):
SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT y ETHUSDT. BTCUSDT sigue con el escalón 1 dado por Ángelo. Verificar escalones NO
activa nada: `activo` sigue en false y validar-futuros sigue diciendo NO PASA por sus otras compuertas.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import liquidacion as LQ
from sobreviviente.futuros import validar as VF
from test_arreglo151_validar_futuros import _mercado, _reg

RAIZ = Path(__file__).resolve().parent.parent

COPIADAS = ("SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT")
URL = "https://www.binance.com/en/futures/trading-parameters/perpetual/leverage-margin"


def test_las_monedas_de_f1_ya_estan_verificadas():
    assert LQ.todas_verificadas(config.MONEDAS_PERMITIDAS) is True
    assert LQ.sin_verificar(config.MONEDAS_PERMITIDAS) == []
    tabla = LQ._tabla()
    for s in COPIADAS:
        m = tabla["monedas"][s]
        assert m["verificado"] is True and URL in m["fuente"] and "2026-11-17" in m["fuente"], s
    assert tabla["fecha"] == "2026-11-17"
    assert URL in tabla["nota_fuente"] and "leverageBracket" in tabla["nota_fuente"]
    # lo que no cambia
    assert tabla["monedas"]["BTCUSDT"]["fuente"] == "Ángelo, 2026-11-16 (escalón 1)"
    assert tabla["tarifa_liquidacion_pct_2026_11_16"]["SOLUSDT"] == 1.5


@pytest.mark.parametrize("simbolo", COPIADAS)
def test_escalones_seguidos_y_cum_cuadra(simbolo):
    esc = LQ.cargar_escalones(simbolo)
    assert len(esc) >= 10
    assert esc[0]["nocional_min"] == 0.0 and esc[0]["cum"] == 0.0
    for i, e in enumerate(esc):
        assert e["escalon"] == i + 1
        assert e["nocional_max"] > e["nocional_min"]
    for ant, e in zip(esc, esc[1:]):
        assert e["nocional_min"] == ant["nocional_max"], (simbolo, e["escalon"])
        assert e["mmr_pct"] > ant["mmr_pct"] and e["apalancamiento_max"] < ant["apalancamiento_max"]
        esperado = ant["cum"] + e["nocional_min"] * (e["mmr_pct"] - ant["mmr_pct"]) / 100.0
        assert e["cum"] == pytest.approx(esperado, abs=0.5), (simbolo, e["escalon"])


def test_valores_puntuales():
    sol = LQ.cargar_escalones("SOLUSDT")[0]
    assert sol["mmr_pct"] == 0.5 and sol["nocional_max"] == 50000.0
    doge = LQ.cargar_escalones("DOGEUSDT")[0]
    assert doge["mmr_pct"] == 0.65 and doge["nocional_max"] == 80000.0
    eth = LQ.cargar_escalones("ETHUSDT")[0]
    assert eth["mmr_pct"] == 0.4 and eth["nocional_max"] == 300000.0 and eth["apalancamiento_max"] == 150


def test_la_posicion_mas_grande_de_f1_cae_en_el_escalon_1():
    cfg = dict(config.POR_DEFECTO)
    mas_grande = cfg["capital_papel"] * cfg["margen_total_max_pct"] / 100.0      # 60 % de 42.54 a 1x
    assert mas_grande == pytest.approx(25.52, abs=0.01)
    for s in config.MONEDAS_PERMITIDAS:
        assert LQ.escalon_de(25.52, LQ.cargar_escalones(s))["escalon"] == 1, s
        assert LQ.escalon_de(mas_grande, LQ.cargar_escalones(s))["escalon"] == 1, s


def test_verificar_escalones_no_activa_nada(tmp_path):
    assert config.POR_DEFECTO["activo"] is False
    reg = RGL.cargar()
    assert reg.get("futuros_papel") is None and config.leer(reg)["activo"] is False
    # el informe real de F1 (sin red aquí: no se vuelve a correr) sigue diciendo NO PASA por otras compuertas
    texto = (RAIZ / "VALIDACION_FUTUROS.md").read_text(encoding="utf-8")
    assert "**Veredicto: F1 NO PASA.**" in texto and FC.validacion_pasa(reg) is False
    otras = [x for x in texto.splitlines() if x.startswith("| ") and "| ❌ |" in x and not x.startswith("| escalones")]
    assert len(otras) >= 5
    # con datos sintéticos, la compuerta «escalones» ya pasa y el veredicto sale solo de las otras
    res = VF.evaluar(_mercado(_reg(tmp_path)), robustez_on=False, variante="F1")
    assert res.compuertas["escalones"][0] is True
    otras_ok = all(ok for k, (ok, _) in res.compuertas.items() if k != "escalones")
    assert res.pasa == otras_ok and res.veredicto == ("PASA" if otras_ok else "NO PASA")
