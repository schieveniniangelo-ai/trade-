"""Arreglo 115 (parte 2): referencias.py, ronda2.referencias e informe con números hechos a mano, sin red.

Fija lo que hoy calculan las referencias (comprar y aguantar, DCA, tendencia pura, R0, R1, R2, por año) para que
un cambio de código que mueva una cifra de VALIDACION_RONDA2.md o VALIDACION_V2.md se vea en una prueba.
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sobreviviente import informe, ronda2
from sobreviviente import referencias as RF

from test_arreglo91_informes import _resultado


def _df(aperturas, inicio="2024-01-01", cierres=None):
    idx = pd.date_range(inicio, periods=len(aperturas), freq="D", tz="UTC")
    o = pd.Series(aperturas, index=idx, dtype=float)
    return pd.DataFrame({"open": o, "close": o if cierres is None else pd.Series(cierres, index=idx, dtype=float)})


# ---------------------------------------------------------------- referencias.py

def test_metricas_curva_a_mano():
    idx = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    c = pd.Series([100.0, 110.0, 99.0, 121.0], index=idx)
    m = RF.metricas_curva(c, invertido=pd.Series([1.0, 0.0], index=idx[:2]))
    assert m["rend_total_pct"] == pytest.approx(21.0)
    assert m["caida_max_pct"] == pytest.approx(10.0)                 # de 110 a 99
    assert m["tiempo_invertido_pct"] == pytest.approx(25.0)          # 1 de 4 días; lo que falta cuenta como fuera
    r = c.pct_change().dropna()
    assert m["volatilidad_pct"] == pytest.approx(r.std() * np.sqrt(365) * 100)
    assert m["sharpe"] == pytest.approx(r.mean() / r.std() * np.sqrt(365))
    assert RF.metricas_curva(c.iloc[:1]) == {} and RF.metricas_curva(pd.Series([np.nan, 1.0], index=idx[:2])) == {}
    plana = RF.metricas_curva(pd.Series(1.0, index=idx))
    assert np.isnan(plana["sharpe"]) and "tiempo_invertido_pct" not in plana


def test_comprar_aguantar_con_pesos_y_costo():
    dfs = {"A": _df([10, 20, 15]), "B": _df([100, 100, 50])}
    a, b = dfs["A"].index[0], dfs["A"].index[-1]
    c = RF.comprar_aguantar(dfs, {"A": 0.5, "B": 0.5}, a, b, costo_pct=1.0)
    assert list(c.round(6)) == [0.99, 1.485, 0.99]                   # (0.5·x/10 + 0.5·y/100) × 0.99


def test_dca_reparte_entre_los_lunes():
    df = _df([10.0] * 14, inicio="2024-01-01")                         # 2024-01-01 y 01-08 son lunes
    c = RF.dca_semanal(df, df.index[0], df.index[-1], costo_pct=0.0)
    assert c.iloc[-1] == pytest.approx(1.0) and len(c) == 14
    df2 = _df([10.0] * 7 + [20.0] * 7)
    c2 = RF.dca_semanal(df2, df2.index[0], df2.index[-1], costo_pct=0.0)
    assert c2.iloc[-1] == pytest.approx(0.5 * 2 + 0.5)                 # la mitad se compró a 10 y vale el doble


def test_tendencia_pura_entra_un_dia_despues_de_la_senal():
    # media de 2 días: el cierre queda arriba desde el día 2 → dentro desde la apertura del día 3
    df = _df([10, 10, 10, 11, 12, 13], cierres=[10, 9, 12, 13, 14, 15])
    c, inv = RF.tendencia_pura({"A": df}, ["A"], 2, df.index[0], df.index[-1], costo_pct=0.0)
    assert list(inv) == [0, 0, 0, 1, 1, 1]
    assert c.iloc[-1] == pytest.approx(13 / 11)                        # de la apertura 11 a la 13 (la última no tiene siguiente)


def test_r0_aguantar_y_r1_marea():
    btc = _df([100, 110, 121, 110, 121])
    curva, inv, ops = RF.r0_aguantar(btc, btc.index[0], btc.index[-1], 0.0)
    assert ops == 1 and (inv == 1.0).all() and curva.iloc[-1] == pytest.approx(1.21)
    marea = pd.Series(["ALCISTA", "ALCISTA", "BAJISTA", "BAJISTA", "ALCISTA"], index=btc.index)
    c1, pos, n = RF.r1_marea(btc, marea, btc.index[0], btc.index[-1], costo_pct=1.0)
    assert list(pos) == [0, 1, 1, 0, 0]                                # decidida al cierre de D, vigente en D+1
    assert n == 2                                                      # entra el día 1 y sale el día 3
    assert list(c1.round(10)) == pytest.approx([1.0, 1.09, 1.09 * 110 / 121, 1.09 * 110 / 121 * 0.99,
                                                1.09 * 110 / 121 * 0.99])
    c0, _, _ = RF.r1_marea(btc, marea, btc.index[0], btc.index[-1], costo_pct=0.0)
    assert c0.iloc[-1] == pytest.approx(1.1 * 110 / 121)               # dentro de la apertura 1 a la 3


def test_r1_marea_primer_dia_dentro_cuenta_como_compra():
    btc = _df([100, 100, 100])
    marea = pd.Series("ALCISTA", index=btc.index)
    c, pos, n = RF.r1_marea(btc, marea, btc.index[1], btc.index[-1], costo_pct=1.0)
    assert pos.iloc[0] == 1 and n == 1 and c.iloc[0] == pytest.approx(0.99)


def test_r2_canasta_elige_por_volumen_y_vende_al_dejar_de_cotizar():
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    velas = {"A": _df([10, 11, 12, 13, 14]), "B": _df([5, 5, 5, np.nan, np.nan])}
    grandes = pd.DataFrame(True, index=idx, columns=["A", "B"])
    vol = pd.DataFrame({"A": [1.0] * 5, "B": [2.0] * 5}, index=idx)
    marea = pd.Series("ALCISTA", index=idx - pd.Timedelta(days=1))
    curva, inv, ops = RF.r2_canasta(velas, grandes, vol, marea, idx[0], idx[-1], costo_pct=0.0, n=1)
    # el día 0 compra B (más volumen); el 3 B deja de cotizar → se vende a 5 y queda en efectivo
    assert list(curva.round(6)) == [1.0, 1.0, 1.0, 1.0, 1.0]
    assert list(inv) == [1.0, 1.0, 1.0, 0.0, 0.0] and ops == 2
    curva2, inv2, ops2 = RF.r2_canasta(velas, grandes, vol, marea, idx[0], idx[-1], costo_pct=0.0, n=2)
    assert curva2.iloc[2] == pytest.approx(0.5 * 12 / 10 + 0.5)        # mitad en A, mitad en B
    baja = pd.Series(["ALCISTA", "BAJISTA", "BAJISTA", "BAJISTA", "BAJISTA"], index=idx - pd.Timedelta(days=1))
    c3, inv3, ops3 = RF.r2_canasta(velas, grandes, vol, baja, idx[0], idx[-1], costo_pct=1.0, n=1)
    assert list(inv3) == [1.0, 0.0, 0.0, 0.0, 0.0] and ops3 == 2       # compra y luego todo a USDT
    assert list(c3) == pytest.approx([0.99, 0.9801, 0.9801, 0.9801, 0.9801])  # el costo de la compra sale de la posición


def test_por_anio_encadena_desde_el_cierre_del_anio_anterior():
    idx = pd.to_datetime(["2023-12-30", "2023-12-31", "2024-06-01", "2024-12-31"], utc=True)
    c = pd.Series([100.0, 110.0, 121.0, 132.0], index=idx)
    pa = RF.por_anio(c)
    assert pa[2023] == pytest.approx(10.0) and pa[2024] == pytest.approx(20.0)


# ---------------------------------------------------------------- ronda2.referencias

def test_ronda2_referencias_tres_periodos_y_rotaciones_solo_en_el_principal(reg, monkeypatch):
    idx = pd.date_range("2017-12-01", "2026-11-05", freq="D", tz="UTC")
    o = pd.Series(np.linspace(100, 300, len(idx)), index=idx)
    df = pd.DataFrame({"open": o, "close": o})
    vistos = []
    monkeypatch.setattr(ronda2, "preparar_rotacion", lambda m, vs: vistos.append(list(vs)))
    monkeypatch.setattr(ronda2.RG, "a_intervalo", lambda *a: pd.Series("ALCISTA", index=idx))
    lugar = pd.DataFrame({"BTCUSDT": 1.0, "ETHUSDT": 2.0}, index=idx)
    m = SimpleNamespace(reg=reg, largo1d={"BTCUSDT": df, "ETHUSDT": df}, spot1d={"BTCUSDT": df, "ETHUSDT": df},
                        btc_reg4h=None, lugar_rotacion={30: lugar, 60: lugar, 90: lugar})
    refs = ronda2.referencias(m)
    assert vistos == [[30, 60, 90]]
    assert list(refs) == ["2022-01 a 2026-10 (principal)", "2018-01 a 2021-12 (antes, solo BTC/ETH)",
                          "2026-05 a 2026-10 (ya abierto)"]
    principal = refs["2022-01 a 2026-10 (principal)"]
    rot = [k for k in principal["curvas"] if k.startswith("Rotación pura")]
    assert len(rot) == 6 and set(principal["operaciones"]) == set(rot)
    assert not any(k.startswith("Rotación") for k in refs["2018-01 a 2021-12 (antes, solo BTC/ETH)"]["curvas"])
    assert principal["metricas"]["Comprar y aguantar BTC"]["rend_total_pct"] > 0
    assert "tiempo_invertido_pct" in principal["metricas"]["Tendencia pura: solo BTC (media 200 días)"]


# ---------------------------------------------------------------- informe.py

def test_texto_de_robustez_tres_casos():
    assert informe._texto_robustez({"todas_positivas": True, "tabla": {0: [0.1, 5]}}) == "sigue positiva en todos los casos"
    assert informe._texto_robustez({"todas_positivas": False, "tabla": {0: [-0.1, 5], 1: [float("nan"), 0]}}) == \
        "negativa en todos los casos: no hay una zona de parámetros que funcione"
    assert informe._texto_robustez({"todas_positivas": False, "tabla": {0: [-0.1, 5], 1: [0.2, 3]}}) == \
        "en algunos casos se vuelve negativa"


def test_seccion_sin_monte_carlo_ni_azar_ni_btc():
    r = _resultado("E9", False, {}, mc={}, azar={}, btc={}, por_regimen={}, real={}, holdout={})
    texto = "\n".join(informe._seccion(r, {}))
    assert "Monte Carlo" not in texto and "Contra el azar" not in texto and "Contra comprar y aguantar" not in texto
    assert "**Prueba final intocable:** 0 operaciones, expectativa sin dato, factor —, rendimiento sin dato." in texto
