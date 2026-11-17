"""Arreglo 160: las variantes de la Hipótesis 004 en la señal (estrategias/f1.py) y en la salida (F1-LT). SOLO PAPEL.

- F1-L: sin cortos. F1-LC: los cortos de F1 solo si, al cierre DIARIO ya conocido, BTC cierra abajo de su SMA200, esa
  SMA200 está más baja que hace 20 días y la moneda está BAJISTA en 4 h (sin mirar el futuro).
- F1-LT: si van 30 velas desde la entrada y el máximo a favor no llegó a +1R, sale en la apertura siguiente («tiempo»),
  igual en backtest.simular_operacion y en futuros/cartera.procesar_vela (apagada por defecto).
- F1 base da exactamente lo mismo que en 5619f84.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente import reglamento as RGL
from sobreviviente.estrategias import f1 as F1
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import config
from sobreviviente.futuros import tamano as T
from test_arreglo151_validar_futuros import _mercado, _reg

P = dict(F1.POR_DEFECTO)
DIA0 = pd.Timestamp("2022-01-01", tz="UTC")


# ---------------------------------------------------------------------------- F1 base: huella de 5619f84
HUELLA = {"SOLUSDT": (139, "6c61d166b6303f12", 3414.934114067517, 3285, 3009),
          "XRPUSDT": (100, "f245ef502d6b7824", 194.78463105241633, 2792, 3536),
          "BNBUSDT": (131, "6c4893cd4c1ee006", 170216.17980896082, 2706, 3256),
          "DOGEUSDT": (150, "3146725ae47e3a6b", 37.70643135372978, 2870, 3133)}


def _huella(sen):
    e = sen[sen["entrada"]]
    clave = ";".join(f"{t.isoformat()}|{lado}" for t, lado in zip(e.index, e["lado"]))
    return len(e), hashlib.sha256(clave.encode()).hexdigest()[:16], float(e["stop"].sum()), \
        int(sen["salir_largo"].sum()), int(sen["salir_corto"].sum())


@pytest.mark.parametrize("variante", [None, "F1"])
def test_f1_base_da_exactamente_lo_mismo_que_en_5619f84(tmp_path, variante):
    m = _mercado(_reg(tmp_path))
    for s, (n, h, stops, sl, sc) in HUELLA.items():
        ctx, _ = m.senales(s, P)
        sen = F1.senales(ctx, P) if variante is None else F1.senales(ctx, P, variante)
        n2, h2, stops2, sl2, sc2 = _huella(sen)
        assert (n2, h2, sl2, sc2) == (n, h, sl, sc), s
        assert stops2 == pytest.approx(stops, rel=1e-12)


def test_f1_l_no_tiene_cortos_y_sus_largos_son_los_de_f1(tmp_path):
    m = _mercado(_reg(tmp_path))
    hubo_cortos = False
    for s in m.cfg["monedas"]:
        ctx, base = m.senales(s, P)
        sen = F1.senales(ctx, P, "F1-L")
        hubo_cortos |= bool((base["lado"] == "CORTO").any())
        assert not (sen["lado"] == "CORTO").any()
        assert (sen["entrada"] == (base["lado"] == "LARGO")).all()
        pd.testing.assert_series_equal(sen.loc[sen["entrada"], "stop"], base.loc[sen["entrada"], "stop"])
    assert hubo_cortos                                    # la prueba sí tenía cortos que quitar


def test_una_variante_desconocida_es_error(tmp_path):
    m = _mercado(_reg(tmp_path))
    ctx, _ = m.senales("SOLUSDT", P)
    with pytest.raises(ValueError):
        F1.senales(ctx, P, "F9")


# ---------------------------------------------------------------------------- F1-LC
def _btc(escenario: str, dias: int = 451) -> pd.DataFrame:
    d = np.arange(dias, dtype=float)
    if escenario == "sma_sube":      # sube 100 → 300 en 400 días y cae a 220: abajo de la SMA200, pero la SMA sigue subiendo
        c = np.where(d < 400, 100 + 200 * d / 400, 220.0)
    else:                            # sube hasta el día 300 y luego baja sin parar: la SMA200 baja
        c = np.where(d < 300, 100 + 200 * d / 300, 300 - 180 * (d - 300) / 150)
    idx = pd.date_range(DIA0, periods=dias, freq="1D")
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "quote_volume": 1e9}, index=idx)


def _moneda(dias: int = 451) -> pd.DataFrame:
    t = np.arange(dias * 6, dtype=float)
    c = 100 * np.exp(-0.0008 * t) * (1 + 0.04 * np.sin(t / 9))       # baja con rebotes: rompe mínimos una y otra vez
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range(DIA0, periods=len(t), freq="4h")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.005, "low": np.minimum(o, c) * 0.995, "close": c,
                         "volume": 1.0, "quote_volume": 5e8}, index=idx)


def _funding(dias: int = 451) -> pd.Series:
    return pd.Series(0.0001, index=pd.date_range(DIA0, periods=dias * 3, freq="8h"))   # sin funding, F1 no entra


def _cortos(sen, desde, hasta):
    e = sen[(sen["lado"] == "CORTO") & (sen.index >= desde) & (sen.index < hasta)]
    return set(e.index)


def test_bajista_fuerte_pide_la_sma200_bajando():
    reg = RGL.cargar()
    a = F1.bajista_fuerte_diario(_btc("sma_sube"), reg)
    b = F1.bajista_fuerte_diario(_btc("sma_baja"), reg)
    dias = pd.date_range(DIA0 + pd.Timedelta(days=401), DIA0 + pd.Timedelta(days=425), freq="1D")
    assert not a.reindex(dias).any()                      # cierre < SMA200 pero la SMA200 sube: NO es fuerte
    assert b.reindex(pd.date_range(DIA0 + pd.Timedelta(days=401), DIA0 + pd.Timedelta(days=449), freq="1D")).all()
    assert not a.iloc[:220].any() and not b.iloc[:220].any()   # sin SMA200 (y la de hace 20 días) no hay «fuerte»


def test_f1_lc_no_corta_con_la_sma200_subiendo_y_si_cuando_baja():
    reg = RGL.cargar()
    v = _moneda()
    desde, hasta = DIA0 + pd.Timedelta(days=402), DIA0 + pd.Timedelta(days=426)
    ctx_a = F1.armar_contexto("SOLUSDT", v, _btc("sma_sube"), _funding(), reg)
    base_a = F1.senales(ctx_a, P)
    assert _cortos(base_a, desde, hasta)                  # F1 sí corta ahí (BTC abajo de su SMA200, moneda BAJISTA)
    assert not _cortos(F1.senales(ctx_a, P, "F1-LC"), desde, hasta)
    ctx_b = F1.armar_contexto("SOLUSDT", v, _btc("sma_baja"), _funding(), reg)
    base_b, lc_b = F1.senales(ctx_b, P), F1.senales(ctx_b, P, "F1-LC")
    hasta_b = DIA0 + pd.Timedelta(days=450)
    assert _cortos(lc_b, desde, hasta_b) and _cortos(lc_b, desde, hasta_b) <= _cortos(base_b, desde, hasta_b)
    # los largos de F1-LC son los de F1, y fuera de «bajista fuerte» no hay cortos
    assert ((lc_b["lado"] == "LARGO") == (base_b["lado"] == "LARGO")).all()
    fuerte = ctx_b.extra["btc_bajista_fuerte"]
    assert fuerte[lc_b["lado"] == "CORTO"].all()
    # sin la serie (un contexto armado a mano), F1-LC no tiene cortos
    sin = F1.Contexto(simbolo="SOLUSDT", velas=v, regimen_moneda=ctx_b.regimen_moneda, regimen_btc=ctx_b.regimen_btc,
                      extra={k: x for k, x in ctx_b.extra.items() if k != "btc_bajista_fuerte"})
    assert not (F1.senales(sin, P, "F1-LC")["lado"] == "CORTO").any()


def test_f1_lc_no_mira_el_futuro():
    reg = RGL.cargar()
    corte = DIA0 + pd.Timedelta(days=430)
    v, btc = _moneda(), _btc("sma_baja")
    sen = F1.senales(F1.armar_contexto("SOLUSDT", v, btc, _funding(), reg), P, "F1-LC")
    rng = np.random.default_rng(7)
    v2, btc2 = v.copy(), btc.copy()
    f4 = rng.uniform(0.5, 1.5, (v2.index >= corte).sum())
    for c in ("open", "high", "low", "close"):
        v2.loc[v2.index >= corte, c] *= f4
    btc2.loc[btc2.index >= corte, ["open", "high", "low", "close"]] *= 3.0     # BTC se dispara: ya no sería bajista
    ctx2 = F1.armar_contexto("SOLUSDT", v2, btc2, _funding(), reg)
    sen2 = F1.senales(ctx2, P, "F1-LC")
    antes = sen.index < corte
    assert sen.loc[antes, "entrada"].sum() > 0
    pd.testing.assert_series_equal(sen.loc[antes, "entrada"], sen2.loc[antes, "entrada"])
    pd.testing.assert_series_equal(sen.loc[antes, "lado"], sen2.loc[antes, "lado"])
    ctx = F1.armar_contexto("SOLUSDT", v, btc, _funding(), reg)
    pd.testing.assert_series_equal(ctx.extra["btc_bajista_fuerte"][antes], ctx2.extra["btc_bajista_fuerte"][antes])


# ---------------------------------------------------------------------------- F1-LT: salida por tiempo
N = 50
IDX = pd.date_range("2026-01-01", periods=N, freq="4h", tz="UTC")
GEST = F1.gestion(P)


def _arr(maximo_en=None):
    o = np.full(N, 100.0) + np.linspace(0, 1, N)          # aperturas distintas para saber en cuál salió
    h = o + 3.0
    if maximo_en is not None:
        h = h.copy()
        h[maximo_en] = 111.0                              # +1R con stop en 90 y entrada planeada en 100
    return {"o": o, "h": h, "l": o - 3.0, "c": o + 0.5, "atr": np.full(N, 20.0), "salir": np.zeros(N, bool)}


def test_f1_lt_sale_en_la_vela_31_si_nunca_llego_a_1r():
    r = B.simular_operacion(_arr(), IDX, 0, "LARGO", 100.0, 90.0, None, GEST, 0.05, 0.0, pd.Timedelta(hours=4),
                            tiempo_max_velas=30)
    assert r["motivo"] == "tiempo" and r["velas"] == 31
    assert r["salida"] == pytest.approx(_arr()["o"][1 + 30])       # la apertura de la vela 31 (la entrada es la 1)
    assert r["t_salida"] == IDX[31] + pd.Timedelta(hours=4)


def test_f1_lt_no_sale_por_tiempo_si_llego_a_1r_y_apagada_no_existe():
    r = B.simular_operacion(_arr(maximo_en=10), IDX, 0, "LARGO", 100.0, 90.0, None, GEST, 0.05, 0.0,
                            pd.Timedelta(hours=4), tiempo_max_velas=30)
    assert r["motivo"] != "tiempo" and r["velas"] > 31
    sin = B.simular_operacion(_arr(), IDX, 0, "LARGO", 100.0, 90.0, None, GEST, 0.05, 0.0, pd.Timedelta(hours=4))
    assert sin["motivo"] != "tiempo" and sin["abierta"]
    assert sin == B.simular_operacion(_arr(), IDX, 0, "LARGO", 100.0, 90.0, None, GEST, 0.05, 0.0,
                                      pd.Timedelta(hours=4), tiempo_max_velas=None)


def test_f1_lt_en_corto_mide_el_minimo():
    a = _arr()
    a["h"], a["l"] = a["o"] + 3.0, a["o"] - 3.0              # nunca baja a 90 (= −1R desde 100 con stop en 110)
    r = B.simular_operacion(a, IDX, 0, "CORTO", 100.0, 110.0, None, GEST, 0.05, 0.0, pd.Timedelta(hours=4),
                            tiempo_max_velas=30)
    assert r["motivo"] == "tiempo" and r["velas"] == 31


def _pos():
    est = C.estado_nuevo(dict(config.POR_DEFECTO))
    t = T.Tamano(True, "cabe", 0.1, 10.0, 1, 10.0, 1.0, 0.4254, None)
    return C.abrir(est, "SOLUSDT", "LARGO", 100.0, 100.0, 90.0, t, datetime(2026, 1, 1, tzinfo=timezone.utc),
                   GEST, 0.05)


@pytest.mark.parametrize("maximo_en,sale", [(None, True), (10, False)])
def test_la_misma_regla_en_la_cartera(maximo_en, sale):
    a = _arr(maximo_en)
    p = _pos()
    salidas = []
    for j in range(1, 40):                                # la vela 1 es la de entrada
        salio, precio, motivo = C.procesar_vela(p, a["o"][j], a["h"][j], a["l"][j], a["c"][j], 20.0, None, None,
                                                False, tiempo_max_velas=30)
        if salio:
            salidas.append((j, precio, motivo))
            break
    if sale:
        assert salidas == [(31, pytest.approx(a["o"][31]), "tiempo")]
    else:
        assert not salidas
    q = _pos()                                            # apagada por defecto
    for j in range(1, 40):
        assert C.procesar_vela(q, a["o"][j], a["h"][j], a["l"][j], a["c"][j], 20.0, None, None, False)[0] is False
