"""Arreglo 146: la señal F1 de 4 h es una función pura (estilo e5.py) y respeta su diseño registrado."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sobreviviente import reglamento as RGL
from sobreviviente.estrategias import ESTRATEGIAS
from sobreviviente.estrategias import f1 as F1
from sobreviviente.estrategias.base import Contexto
from sobreviviente.gestion import EstadoGestion, vela

P = dict(F1.POR_DEFECTO)
ANCHO = {"stop_min_pct": 0.0, "stop_max_pct": 100.0}


def _velas(n: int = 400, semilla: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.01, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.01, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": 1.0}, index=idx)


def _ctx(v, marea="ALCISTA", tend="ALCISTA", extra=None) -> Contexto:
    def serie(x):
        return x if isinstance(x, pd.Series) else pd.Series(x, index=v.index, dtype=object)
    return Contexto("SOLUSDT", v, serie(tend), serie(marea), extra=dict(ANCHO if extra is None else extra))


def _invertir(v: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"open": 1 / v["open"], "high": 1 / v["low"], "low": 1 / v["high"], "close": 1 / v["close"],
                         "volume": v["volume"]}, index=v.index)


def test_temporalidad_parametros_y_fuera_del_registro():
    assert F1.TEMPORALIDAD == "4h" and len(F1.PARAMETROS) == 4
    assert set(F1.PARAMETROS) == set(F1.POR_DEFECTO)
    assert F1.POR_DEFECTO == {"donchian_n": 55, "stop_atr": 2.5, "chandelier_atr": 3.0, "funding_extremo_pct": 0.05}
    assert "F1" not in ESTRATEGIAS and F1 not in ESTRATEGIAS.values()
    reg = RGL.cargar()
    assert "F1" not in reg.estrategias and "F" not in (reg.get("carteras") or {})


def test_no_mira_el_futuro():
    v = _velas()
    completo = F1.senales(_ctx(v), P)
    for corte in (150, 233, 301, 399):
        parcial = F1.senales(_ctx(v.iloc[:corte]), P)
        a, b = completo.iloc[:corte], parcial
        assert (a["entrada"].to_numpy() == b["entrada"].to_numpy()).all()
        assert (a["lado"].fillna("-").to_numpy() == b["lado"].fillna("-").to_numpy()).all()
        assert np.allclose(a["stop"].to_numpy(), b["stop"].to_numpy(), equal_nan=True)


def test_espejo_cada_largo_pasa_a_corto():
    v = _velas(semilla=11)
    largos = F1.senales(_ctx(v, "ALCISTA", "ALCISTA"), P)
    cortos = F1.senales(_ctx(_invertir(v), "BAJISTA", "BAJISTA"), P)
    assert largos["entrada"].sum() > 3
    assert (largos["entrada"].to_numpy() == cortos["entrada"].to_numpy()).all()
    assert set(largos.loc[largos["entrada"], "lado"]) == {"LARGO"}
    assert set(cortos.loc[cortos["entrada"], "lado"]) == {"CORTO"}
    e = largos["entrada"]
    assert (cortos.loc[e, "stop"] > cortos.loc[e, "precio"]).all() and (largos.loc[e, "stop"] < largos.loc[e, "precio"]).all()


def test_solo_la_primera_vela_del_rompimiento():
    idx = pd.date_range("2025-01-01", periods=80, freq="4h", tz="UTC")
    c = np.r_[np.full(60, 100.0), np.linspace(101, 120, 20)]        # rompe en la vela 60 y sigue rompiendo
    v = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1.0}, index=idx)
    s = F1.senales(_ctx(v), P)
    assert list(np.flatnonzero(s["entrada"].to_numpy())) == [60]


def test_regimen_doble():
    v = _velas(semilla=11)
    assert F1.senales(_ctx(v, "ALCISTA", "ALCISTA"), P)["entrada"].any()
    for marea, tend in (("ALCISTA", "BAJISTA"), ("BAJISTA", "ALCISTA"), ("ALCISTA", "LATERAL"), ("LATERAL", "ALCISTA")):
        s = F1.senales(_ctx(v, marea, tend), P)
        assert not (s["lado"] == "LARGO").any(), (marea, tend)
    vi = _invertir(v)
    assert not F1.senales(_ctx(vi, "BAJISTA", "ALCISTA"), P)["entrada"].any()


def test_funding_en_los_dos_lados():
    v = _velas(semilla=11)
    caro = pd.Series(0.06, index=v.index)       # los largos pagan 0.06 % cada 8 h
    barato = pd.Series(-0.06, index=v.index)    # los cortos pagan 0.06 %
    assert not F1.senales(_ctx(v, extra={**ANCHO, "funding_8h": caro}), P)["entrada"].any()
    assert F1.senales(_ctx(v, extra={**ANCHO, "funding_8h": barato}), P)["entrada"].any()
    vi = _invertir(v)
    assert not F1.senales(_ctx(vi, "BAJISTA", "BAJISTA", {**ANCHO, "funding_8h": barato}), P)["entrada"].any()
    assert F1.senales(_ctx(vi, "BAJISTA", "BAJISTA", {**ANCHO, "funding_8h": caro}), P)["entrada"].any()
    justo = pd.Series(0.05, index=v.index)      # exactamente en el límite: sí se permite
    assert F1.senales(_ctx(v, extra={**ANCHO, "funding_8h": justo}), P)["entrada"].any()
    sin_dato = pd.Series(np.nan, index=v.index)  # sin funding conocido: no se entra (falla cerrada)
    assert not F1.senales(_ctx(v, extra={**ANCHO, "funding_8h": sin_dato}), P)["entrada"].any()


def test_stop_fuera_de_1_5_a_8_por_ciento_descarta_la_senal():
    v = _velas(semilla=11)
    base = F1.senales(_ctx(v), P)
    e = base["entrada"]
    assert e.any()
    sp = base.loc[e, "stop_pct"]
    bajo = F1.senales(_ctx(v, extra={"stop_min_pct": float(sp.max()) + 0.01, "stop_max_pct": 100.0}), P)
    alto = F1.senales(_ctx(v, extra={"stop_min_pct": 0.0, "stop_max_pct": float(sp.min()) - 0.01}), P)
    assert not bajo["entrada"].any() and not alto["entrada"].any()
    normal = F1.senales(_ctx(v, extra={}), P)       # 1.5–8 % por defecto
    assert ((normal.loc[normal["entrada"], "stop_pct"] >= 1.5) & (normal.loc[normal["entrada"], "stop_pct"] <= 8.0)).all()


def test_volatilidad_extrema_sin_entradas():
    v = _velas(semilla=11)
    assert not F1.senales(_ctx(v, extra={**ANCHO, "vol_percentil": pd.Series(95.0, index=v.index)}), P)["entrada"].any()
    assert F1.senales(_ctx(v, extra={**ANCHO, "vol_percentil": pd.Series(94.9, index=v.index)}), P)["entrada"].any()


def test_salida_por_regimen_y_chandelier():
    g = F1.gestion(P)
    assert g == {"modo": "chandelier_senal", "chandelier_atr": 3.0, "sin_breakeven": True}
    est = EstadoGestion(lado="LARGO", entrada=100, entrada_plan=100, stop_inicial=95, stop=95, meta=None, modo=g["modo"],
                        params={"chandelier_atr": 3.0}, en_r=None)
    ev = vela(est, 100, 110, 99, 109, 1.0)
    assert est.stop == pytest.approx(107.0) and not ev.salio            # chandelier: 110 − 3 × 1
    assert not vela(est, 109, 111, 108, 110, 1.0, salida_externa=True).salio
    ev = vela(est, 110, 112, 109, 111, 1.0)
    assert ev.salio and ev.precio == 110 and "régimen" in ev.motivo        # sale en la apertura siguiente
    v = _velas(semilla=11)
    idx = v.index
    s = F1.senales(_ctx(v, pd.Series(["ALCISTA"] * 200 + ["BAJISTA"] * 200, index=idx, dtype=object)), P)
    assert not s["salir_largo"].iloc[:200].any() and s["salir_largo"].iloc[200:].all()
    assert s["salir_corto"].iloc[:200].all()


def test_contexto_sin_mirar_el_futuro():
    reg = RGL.cargar()
    v = _velas(n=1500, semilla=3)
    dias = pd.date_range("2024-01-01", periods=600, freq="1D", tz="UTC")
    btc = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": np.linspace(50, 150, 600)}, index=dias)
    fund_idx = pd.date_range("2024-12-20", periods=900, freq="8h", tz="UTC")
    fund = pd.Series(0.0001, index=fund_idx)
    ctx = F1.armar_contexto("SOLUSDT", v, btc, fund, reg)
    assert set(ctx.regimen_btc.dropna()) == {"ALCISTA"}
    assert ctx.extra["funding_8h"].dropna().iloc[-1] == pytest.approx(0.01)
    assert ctx.extra["vol_extrema"] == 95
    s = F1.senales(ctx, P)
    assert len(s) == len(v)
    # la marea del día D solo se usa desde su cierre
    marea_d = F1.RG.marea_diaria(btc, reg)
    t = pd.Timestamp("2025-01-10 16:00", tz="UTC")
    assert ctx.regimen_btc.loc[t] == marea_d.loc[pd.Timestamp("2025-01-09", tz="UTC")]
    assert F1.funding_8h_por_vela(None, v.index).isna().all()
