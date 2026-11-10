"""Pruebas de estrategias, gestión y backtester.

Lo más importante: las señales en la vela t NO cambian si se agregan datos del futuro.
"""
import numpy as np
import pandas as pd
import pytest

from sobreviviente import calidad, datos as D, regimen as RG, universo as U
from sobreviviente.backtest import cartera, simular_operacion
from sobreviviente.estrategias import ESTRATEGIAS
from sobreviviente.estrategias.base import Contexto
from sobreviviente.estrategias.e4 import fuerza_relativa
from sobreviviente.exchange import Filtros
from sobreviviente.gestion import EstadoGestion, vela
from sobreviviente.metricas import caida_maxima_pct, resumen_r


def velas_sinteticas(n=3000, semilla=1, inicio="2023-01-01", freq="1h", tendencia=0.0002, onda=0.002):
    rng = np.random.default_rng(semilla)
    ret = rng.normal(tendencia, 0.01, n)
    # tramos de tendencia alcista y bajista para que haya señales de todo tipo
    ret += np.sin(np.arange(n) / 300) * onda
    c = 100 * np.exp(np.cumsum(ret))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.006, n))
    l = np.minimum(o, c) * (1 - rng.uniform(0, 0.006, n))
    vol = rng.lognormal(10, 0.6, n)
    vol[rng.integers(0, n, 30)] *= 8  # picos de volumen
    idx = pd.date_range(inicio, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": vol, "quote_volume": vol * c,
                         "trades": 1}, index=idx)


def ctx_para(clave, df1h, reg, btc_bajista=False):
    mod = ESTRATEGIAS[clave]
    df4h = D.resamplear(df1h, "4h")
    reg4 = RG.tendencia(df4h, reg)
    if btc_bajista:
        reg_btc4 = pd.Series("BAJISTA", index=df4h.index, dtype=object)
    else:
        reg_btc4 = reg4
    if mod.TEMPORALIDAD == "4h":
        extra = {}
        if clave == "E5":
            extra["funding"] = pd.Series(0.0001, index=df4h.index)
        return Contexto("XUSDT", df4h, reg4, reg_btc4, extra)
    reg1 = RG.a_intervalo_menor(reg4, df1h.index)
    extra = {"regimen_moneda_4h": reg1}
    if clave == "E4":
        extra["fuerza_relativa"] = pd.Series(95.0, index=df1h.index)
    return Contexto("XUSDT", df1h, reg1, RG.a_intervalo_menor(reg_btc4, df1h.index), extra)


# Parámetros más sueltos SOLO para que los datos sintéticos generen varias señales.
PARAMS_SUELTOS = {
    "E3": {"rsi2_max": 30, "stop_atr": 2.0, "salida_media": 5},
    "E4": {"vol_mult": 1.2, "respiro_pct": 0.3, "stop_atr": 2.0},
}


@pytest.mark.parametrize("clave", ["E1", "E2", "E3", "E4", "E5"])
def test_sin_adelanto_de_informacion(clave, reg):
    """Recortar los datos en t no cambia ninguna señal anterior a t."""
    # E3 solo opera en rango: para ella se usan datos sin tendencia.
    df = velas_sinteticas(3000, semilla=7, tendencia=0.0, onda=0.0) if clave == "E3" else velas_sinteticas(3000, semilla=7)
    params = PARAMS_SUELTOS.get(clave, reg.estrategias[clave]["parametros"])
    mod = ESTRATEGIAS[clave]
    completo = mod.senales(ctx_para(clave, df, reg, btc_bajista=(clave == "E5")), params)
    assert completo["entrada"].sum() >= 3, "la prueba necesita señales reales para comparar"
    for corte in (1500, 2200, 2999):
        parcial_df = df.iloc[:corte]
        parcial = mod.senales(ctx_para(clave, parcial_df, reg, btc_bajista=(clave == "E5")), params)
        # Solo comparamos hasta la última vela COMPLETA de la temporalidad de la estrategia
        comun = parcial.index[:-2]
        a = completo.loc[comun, ["entrada", "stop", "meta"]]
        b = parcial.loc[comun, ["entrada", "stop", "meta"]]
        pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)


@pytest.mark.parametrize("clave", ["E1", "E2", "E3", "E4", "E5"])
def test_determinismo(clave, reg):
    df = velas_sinteticas(2500, semilla=3)
    params = reg.estrategias[clave]["parametros"]
    mod = ESTRATEGIAS[clave]
    a = mod.senales(ctx_para(clave, df, reg, clave == "E5"), params)
    b = mod.senales(ctx_para(clave, df.copy(), reg, clave == "E5"), params)
    pd.testing.assert_frame_equal(a, b)


def test_hay_senales_en_datos_sinteticos(reg):
    df = velas_sinteticas(4000, semilla=11)
    total = sum(int(ESTRATEGIAS[k].senales(ctx_para(k, df, reg, k == "E5"), reg.estrategias[k]["parametros"])
                    ["entrada"].sum()) for k in ESTRATEGIAS)
    assert total > 0


def test_regimen_4h_a_1h_sin_futuro():
    idx4 = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
    s4 = pd.Series(["A", "B", "C"], index=idx4)
    idx1 = pd.date_range("2024-01-01", periods=12, freq="1h", tz="UTC")
    s1 = RG.a_intervalo_menor(s4, idx1)
    assert pd.isna(s1.iloc[2])                         # 02:00 todavía no cierra la vela de 4 h
    assert s1.loc["2024-01-01 03:00"] == "A"           # la vela 00:00–04:00 ya cerró al terminar la de 03:00
    assert s1.loc["2024-01-01 06:00"] == "A"
    assert s1.loc["2024-01-01 07:00"] == "B"


def test_resample_4h():
    df = velas_sinteticas(9, freq="1h")
    r = D.resamplear(df, "4h")
    assert len(r) == 2  # la tercera vela de 4 h está incompleta
    assert r["high"].iloc[0] == df["high"].iloc[:4].max()
    assert r["close"].iloc[1] == df["close"].iloc[7]


# ---------------- Gestión ----------------

def _est(**kw):
    base = dict(lado="LARGO", entrada=100.0, entrada_plan=100.0, stop_inicial=95.0, stop=95.0, meta=None,
                modo="chandelier", params={"chandelier_atr": 3.0}, costo_pct=0.3)
    base.update(kw)
    return EstadoGestion(**base)


def test_gestion_stop_y_hueco():
    e = _est()
    assert vela(e, 100, 101, 94, 96, 1).precio == 95
    e = _est()
    ev = vela(e, 90, 91, 89, 90, 1)
    assert ev.salio and ev.precio == 90 and "hueco" in ev.motivo


def test_gestion_breakeven_y_chandelier():
    e = _est()
    ev = vela(e, 100, 105.5, 99, 105, 1.0)    # +1R → stop a 100.3 ; chandelier 105.5−3 = 102.5
    assert ev.stop_nuevo == pytest.approx(102.5)
    ev = vela(e, 105, 105, 104, 104.5, 1.0)   # sin nuevo máximo: el stop no baja
    assert ev.stop_nuevo is None and e.stop == pytest.approx(102.5)


def test_gestion_corto():
    e = _est(lado="CORTO", stop_inicial=105.0, stop=105.0)
    ev = vela(e, 100, 100.5, 94, 95, 1.0)     # -1R a favor: stop baja a 99.7 y chandelier 94+3 = 97
    assert e.stop == pytest.approx(97.0)
    ev = vela(e, 98, 98, 97, 97.5, 1.0)
    assert ev.salio and ev.precio == 98 and "hueco" in ev.motivo


def test_gestion_meta_luego_chandelier():
    e = _est(modo="meta_luego_chandelier", meta=110.0, params={"chandelier_atr": 3.0})
    vela(e, 100, 108, 100, 107, 1.0)
    assert not e.meta_tocada and e.stop == pytest.approx(100.3)
    vela(e, 107, 111, 106, 110, 1.0)          # toca la meta: stop ≥ +1R (105) y chandelier 111−3=108
    assert e.meta_tocada and e.stop == pytest.approx(108.0)


def test_gestion_media_y_tiempo():
    e = _est(modo="media", params={"max_velas": 10})
    vela(e, 100, 101, 99, 100.5, 1.0, media=100.2)
    ev = vela(e, 101, 102, 100, 101, 1.0, media=100.2)
    assert ev.salio and ev.precio == 101 and "promedio" in ev.motivo
    e = _est(modo="tiempo", params={"max_velas": 2})
    vela(e, 100, 101, 99, 100, 1.0)
    vela(e, 100, 101, 99, 100, 1.0)
    ev = vela(e, 100.5, 101, 99, 100, 1.0)
    assert ev.salio and ev.precio == 100.5 and "tiempo" in ev.motivo


# ---------------- Backtester: caso calculado a mano ----------------

def _arr(filas):
    a = np.array(filas, dtype=float)
    return {"o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3], "atr": np.full(len(a), 1.0)}


def test_caso_a_mano_stop():
    """Señal en la vela 0 (cierre 100), entra en la apertura de la 1 a 100, sale en el stop 95.
    Comisión 0.1 % por lado, sin deslizamiento:
      pérdida por unidad = 95 − 100 − (100 + 95) × 0.001 = −5.195  →  R = −5.195 / 5 = −1.039
    """
    arr = _arr([[99, 100, 98, 100], [100, 101, 99, 100], [100, 100, 94, 96]])
    idx = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
    s = simular_operacion(arr, idx, 0, "LARGO", 100.0, 95.0, None, {"modo": "chandelier", "chandelier_atr": 10},
                          0.1, 0.0, pd.Timedelta(hours=4))
    assert s["entrada"] == 100 and s["salida"] == 95
    assert s["pnl_unidad"] == pytest.approx(-5.195)
    assert s["r"] == pytest.approx(-1.039)
    assert s["t_salida"] == idx[2] + pd.Timedelta(hours=4)


def test_caso_a_mano_deslizamiento_y_hueco():
    arr = _arr([[99, 100, 98, 100], [100, 101, 99, 100], [90, 91, 88, 89]])
    idx = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
    s = simular_operacion(arr, idx, 0, "LARGO", 100.0, 95.0, None, {"modo": "chandelier", "chandelier_atr": 10},
                          0.1, 0.1, pd.Timedelta(hours=4))
    # entrada 100 × 1.001 = 100.1 ; salida 90 × 0.999 = 89.91 ; comisiones (100.1 + 89.91) × 0.001
    assert s["entrada"] == pytest.approx(100.1) and s["salida"] == pytest.approx(89.91)
    assert s["pnl_unidad"] == pytest.approx(89.91 - 100.1 - 0.19001)
    assert "hueco" in s["motivo"]


def test_caso_a_mano_corto_con_funding():
    arr = _arr([[101, 101, 99, 100], [100, 100.5, 99, 99.5], [99, 99, 90, 91], [91, 106, 90, 105]])
    idx = pd.date_range("2024-01-01", periods=4, freq="4h", tz="UTC")
    funding = pd.Series([0.001], index=[idx[2]])
    s = simular_operacion(arr, idx, 0, "CORTO", 100.0, 105.0, None, {"modo": "chandelier", "chandelier_atr": 10},
                          0.05, 0.0, pd.Timedelta(hours=4), funding)
    # Vela 2: mínimo 90 = −2R → stop a 100 × (1 − 0.1 %) = 99.9 ; Vela 3 abre en 91 y sube a 106 → stop 99.9
    assert s["salida"] == pytest.approx(99.9)
    assert s["funding_unidad"] == pytest.approx(0.1)
    assert s["pnl_unidad"] == pytest.approx(100 - 99.9 - (100 + 99.9) * 0.0005 + 0.1)


def test_sin_vela_siguiente():
    arr = _arr([[99, 100, 98, 100]])
    idx = pd.date_range("2024-01-01", periods=1, freq="4h", tz="UTC")
    assert simular_operacion(arr, idx, 0, "LARGO", 100, 95, None, {"modo": "chandelier"}, 0.1, 0, pd.Timedelta(hours=4)) is None


def test_cartera_usa_motor_de_riesgo(reg):
    t0 = pd.Timestamp("2024-03-04 16:00", tz="UTC")
    base = dict(estrategia="E1", mercado="SPOT", lado="LARGO", cubeta="normales", precio_plan=100.0, stop=95.0,
                meta=None, fuerza=1.0, comision_pct=0.1, desliz_pct=0.0, regimen_btc="ALCISTA", vol_btc=50.0,
                vol_moneda=50.0, pnl_unidad=10.0, comision_unidad=0.2, stops_t=[], stops=[])
    filas = [
        {**base, "simbolo": "AUSDT", "t_decision": t0, "t_salida": t0 + pd.Timedelta(hours=8)},
        {**base, "simbolo": "AUSDT", "t_decision": t0 + pd.Timedelta(hours=4), "t_salida": t0 + pd.Timedelta(hours=12)},
        {**base, "simbolo": "BUSDT", "t_decision": t0 + pd.Timedelta(hours=4), "t_salida": t0 + pd.Timedelta(hours=12),
         "pnl_unidad": -5.0},
    ]
    filt = {"AUSDT": Filtros("AUSDT", 0.01, 0.001, 0.001, 5), "BUSDT": Filtros("BUSDT", 0.01, 0.001, 0.001, 5)}
    res = cartera(reg, pd.DataFrame(filas), 1000.0, filt, ["E1"])
    dec = res.decisiones
    assert dec["aprobada"].tolist() == [True, False, True]
    assert "promediar" in dec["razon"].iloc[1]
    # A: 2 unidades × 10 = +20 ; B: 2 unidades (capital 1000 → riesgo 10 / 5) × −5 = −10
    assert res.operaciones["ganancia_usdt"].tolist() == [pytest.approx(20.0), pytest.approx(-10.0)]
    assert res.curva.iloc[-1] == pytest.approx(1010.0)


def test_cartera_vacia(reg):
    res = cartera(reg, pd.DataFrame(), 100.0, {})
    assert res.operaciones.empty


# ---------------- Universo, calidad y métricas ----------------

def test_universo_nombres(reg):
    bases = {"BTC", "ETH", "BNB", "JUP"}
    assert U.nombre_permitido(reg, "BTCUSDT", bases)[0]
    assert not U.nombre_permitido(reg, "USDCUSDT", bases)[0]
    assert not U.nombre_permitido(reg, "EURUSDT", bases)[0]
    assert U.nombre_permitido(reg, "BTCUPUSDT", bases)[1] == "token apalancado"
    assert U.nombre_permitido(reg, "JUPUSDT", bases)[0]
    assert not U.nombre_permitido(reg, "BTCBNB", bases)[0]


def test_universo_pertenencia(reg):
    idx = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
    vol = pd.DataFrame({"A": 20e6, "B": 5e6}, index=idx)
    vol.loc[idx[:40], "C"] = np.nan
    vol.loc[idx[40:], "C"] = 50e6
    p = U.pertenencia(reg, vol)
    assert not p["A"].iloc[29] and p["A"].iloc[31]
    assert not p["B"].any()
    assert not p["C"].iloc[69] and p["C"].iloc[70]  # necesita 30 días listada


def test_calidad(reg):
    df = velas_sinteticas(600)
    ahora = df.index[-1] + pd.Timedelta(hours=1, minutes=5)
    assert calidad.revisar_velas(reg, df, "X", "1h", ahora).confiable
    viejo = calidad.revisar_velas(reg, df, "X", "1h", ahora + pd.Timedelta(hours=5))
    assert not viejo.confiable and "viejos" in viejo.motivos[0]
    huecos = df.drop(df.index[100:120])
    assert not calidad.revisar_velas(reg, huecos, "X").confiable
    malo = df.copy()
    malo.iloc[-3, malo.columns.get_loc("close")] *= 3
    r = calidad.revisar_velas(reg, malo, "X")
    assert not r.confiable and r.saltos >= 1
    assert not calidad.revisar_velas(reg, pd.DataFrame(), "X").confiable


def test_fuerza_relativa():
    idx = pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC")
    c = pd.DataFrame({"A": np.linspace(1, 2, 30), "B": np.linspace(1, 1.1, 30), "C": np.linspace(1, 0.9, 30)},
                     index=idx)
    fr = fuerza_relativa(c)
    assert fr["A"].iloc[-1] == 100 and fr["C"].iloc[-1] < fr["B"].iloc[-1]


def test_metricas():
    m = resumen_r(np.array([1.0, -1.0, 2.0, -1.0, -1.0]))
    assert m["operaciones"] == 5 and m["expectativa_r"] == pytest.approx(0.0)
    assert m["factor_ganancia"] == pytest.approx(1.0) and m["racha_perdedora_max"] == 2
    assert resumen_r(np.array([]))["operaciones"] == 0
    assert caida_maxima_pct([100, 120, 90, 130]) == pytest.approx(25.0)
