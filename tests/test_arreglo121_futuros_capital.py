"""Arreglo 121 (F5): comando `futuros-capital` (solo informa).

Por perpetuo: mínimo de la orden (reglas de Futuros, arreglo 92), stop típico de E5 (mediana de stop_atr × ATR ÷
cierre en las últimas velas de 4 h), capital necesario con el riesgo de cada cartera (riesgo.capital_necesario) y
si cabe con el capital real. Referencias de la tanda (corto, 1 % de riesgo; stop de 5 % y de 15 %): mínimo 5 USDT
→ 24 y 65; 20 → 95 y 261; 50 → 238 y 652; 100 → 476 y 1,304. Con 10 USDT no cabe nada. Manda lo que diga
exchangeInfo: si la cantidad mínima (minQty) pide más que el mínimo en USDT, cuenta la cantidad mínima.
"""
import json

import numpy as np
import pandas as pd
import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import futuros_capital as FC
from sobreviviente.exchange import Filtros


def _f(minimo, cant_min=0.0, paso=0.0, s="XUSDT"):
    return Filtros(simbolo=s, tick=0.0001, paso=paso, cantidad_min=cant_min, minimo_usdt=minimo)


@pytest.mark.parametrize("minimo,stop,esperado", [(5, 5, 24), (5, 15, 65), (20, 5, 95), (20, 15, 261),
                                                  (50, 5, 238), (50, 15, 652), (100, 5, 476), (100, 15, 1304)])
def test_referencias_de_la_tanda(minimo, stop, esperado):
    assert round(FC.capital_necesario_corto(_f(minimo), 100.0, stop, 1.0)) == esperado


def test_la_cantidad_minima_manda_si_pide_mas():
    # BTC con minQty 0.001 a 95,000: la orden mínima vale 95 USDT, más que los 50 de MIN_NOTIONAL
    con_qty = FC.capital_necesario_corto(_f(50, cant_min=0.001, paso=0.001), 95000.0, 5, 1.0)
    assert con_qty == pytest.approx(0.001 * 95000 * 0.05 / 0.01, abs=0.005)
    assert con_qty > FC.capital_necesario_corto(_f(50), 95000.0, 5, 1.0)


def test_stop_tipico_de_e5():
    idx = pd.date_range("2024-01-01", periods=400, freq="4h", tz="UTC")
    v = pd.DataFrame({"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0}, index=idx)
    assert FC.stop_tipico_pct(v, stop_atr=2.5) == pytest.approx(2.5 * 4 / 100 * 100)   # ATR 4 → 10 %
    assert np.isnan(FC.stop_tipico_pct(v.iloc[:10], stop_atr=2.5))                     # pocas velas: sin dato


def test_tabla_con_capital_chico_no_cabe_nada(reg):
    idx = pd.date_range("2024-01-01", periods=400, freq="4h", tz="UTC")
    v = pd.DataFrame({"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0}, index=idx)
    filtros = {"AUSDT": _f(5, s="AUSDT"), "BUSDT": _f(20, s="BUSDT")}
    filas = FC.filas(reg, filtros, {"AUSDT": v, "BUSDT": v, "SINREGLAS": v}, capital=10.0)
    assert [f["simbolo"] for f in filas] == ["AUSDT", "BUSDT"]           # sin reglas de Futuros: no sale
    assert all(not any(f["cabe"].values()) for f in filas)
    a = filas[0]
    assert a["minimo_usdt"] == 5 and a["stop_pct"] == pytest.approx(10.0)
    assert a["capital"]["A"] == pytest.approx(5 * 0.10 / 1.10 / 0.01, abs=0.005)        # capital_necesario redondea a centavos
    assert a["capital"]["B"] == pytest.approx(5 * 0.10 / 1.10 / 0.02, abs=0.005)
    con_mas = FC.filas(reg, filtros, {"AUSDT": v, "BUSDT": v}, capital=46.18)
    assert con_mas[0]["cabe"] == {"A": True, "B": True, "C": True}       # 45.45 / 22.73 / 10.10 USDT
    assert con_mas[1]["cabe"]["A"] is False


def test_comando_imprime_la_tabla(reg, tmp_path, monkeypatch, capsys):
    cache = tmp_path / "cache"
    (cache / "futuros" / "1h").mkdir(parents=True)
    idx = pd.date_range("2024-01-01", periods=1600, freq="1h", tz="UTC")
    v = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0,
                      "quote_volume": 100.0, "trades": 1}, index=idx)
    v.to_csv(cache / "futuros" / "1h" / "AUSDT.csv.gz", compression="gzip")
    info = {"symbols": [{"symbol": "AUSDT", "status": "TRADING", "filters": [
        {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.01", "maxQty": "1000"},
        {"filterType": "MIN_NOTIONAL", "notional": "5"}]}]}

    class Cliente:
        def __init__(self, r):
            self.cache = cache

        def exchange_info(self, mercado="SPOT", forzar=False):
            assert mercado == "FUTUROS"
            return info
    monkeypatch.setattr(FC.D, "ClienteBinance", Cliente)
    monkeypatch.setattr(MAIN, "_reg", lambda args: reg)
    assert MAIN.main(["futuros-capital"]) == 0
    out = capsys.readouterr().out
    assert "AUSDT" in out and "5 USDT" in out and "solo informa" in out.lower()
    assert "46.18" in out
