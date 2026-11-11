"""Arreglo 86 (B10): pruebas de validacion_v2 con velas falsas y pocas repeticiones (sin red).

Se fijan propiedades (reproducibilidad, rangos, sin ver el futuro, que el costo empeore el resultado),
no números del pasado. El reglamento se copia con fechas que caben en las velas falsas y con pocas
repeticiones de azar y Monte Carlo; eso es solo para que la prueba sea rápida, no cambia el reglamento.
"""
import math

import numpy as np
import pandas as pd
import pytest

from sobreviviente import diario as DI
from sobreviviente import reglamento
from sobreviviente import validacion_v2 as V2

from test_v2 import diarias

FECHAS_CHICAS = {
    "backtest.inicio": "2022-01-01", "backtest.fin": "2024-02-29",
    "validacion.montecarlo_n": 40, "validacion.lentos.azar_calendario_n": 30, "validacion.lentos.bootstrap_n": 30,
    "validacion.lentos.orden_azar_n": 2, "validacion.lentos.comisiones_sensibilidad": [0.1, 0.15],
    "validacion.lentos.wf_min_operaciones_entrenamiento": 1,
    "estrategias.M1.rejilla": {"n": [20, 50]},
}


def _reg_chico():
    r = reglamento.cargar()
    for k in r.estrategias:
        r.datos["estrategias"][k]["estado"] = "PAPEL"
    return r.copia_con({**FECHAS_CHICAS, "universo.grandes_n": 3})


@pytest.fixture(scope="module")
def md():
    r = _reg_chico()
    velas = {s: diarias(800, semilla=i + 10, tendencia=0.0008 + 0.0003 * i)
             for i, s in enumerate(["BTCUSDT", "AUSDT", "BUSDT", "CUSDT"])}
    for i, df in enumerate(velas.values()):
        df["quote_volume"] = 5e8 / (i + 1)
    return DI.preparar(r, velas, None, [], exchange_info={"symbols": []}, btc_largo=velas["BTCUSDT"])


@pytest.fixture(scope="module")
def refs(md):
    return V2.referencias(md)


# ---------------- costo y periodos ----------------

def test_costo_referencias_es_comision_mas_deslizamiento_grande(md):
    r = md.reg
    assert V2.costo_referencias(r) == pytest.approx(
        float(r.costos["comision_spot_pct"]) + float(r.costos["deslizamiento_pct"]["grande"]))


def test_periodos_en_orden_y_sin_traslape(md):
    p = V2.periodos(md.reg)
    a, b = p["todo"]
    oa, ob = p["fuera_de_muestra"]
    ha, hb = p["prueba_final"]
    assert a < oa < ob < ha <= hb == b
    assert ha - ob == pd.Timedelta(minutes=1)          # fuera de muestra termina justo antes de la prueba final


# ---------------- referencias ----------------

def test_referencias_tienen_las_tres_curvas_por_periodo(refs):
    assert set(refs) == {"R0", "R1", "R2"}
    for ref in refs.values():
        assert set(ref.curvas) == set(ref.metricas) == {"todo", "fuera_de_muestra", "prueba_final"}
        for per, c in ref.curvas.items():
            assert len(c) and np.isfinite(c.to_numpy(float)).all()
            assert ref.invertido[per].between(0, 1).all()
        assert ref.por_anio


def test_aguantar_btc_esta_siempre_invertido(refs):
    assert refs["R0"].invertido["todo"].iloc[1:].eq(1).all()


def test_mas_costo_da_peor_resultado(md, refs):
    caro = V2.referencias(md, costo_pct=1.0)
    for k in ("R1", "R2"):
        barato = refs[k].metricas["todo"]["rend_total_pct"]
        assert caro[k].metricas["todo"]["rend_total_pct"] < barato


# ---------------- azar calendario ----------------

def test_azar_posicion_reproducible_y_en_rango(md, refs):
    pos = refs["R1"].invertido["fuera_de_muestra"]
    a = V2.azar_calendario_posicion(md.btc, pos, 0.15, 50, 7)
    b = V2.azar_calendario_posicion(md.btc, pos, 0.15, 50, 7)
    assert a == b
    assert 0 <= a["percentil"] <= 100 and a["n"] == 50
    assert a["tiempo_invertido_pct"] == pytest.approx(pos.mean() * 100)
    assert a["azar_p50"] <= a["azar_p90"]


def test_azar_posicion_siempre_fuera_no_gana_ni_pierde(md):
    idx = md.btc.index[-100:]
    a = V2.azar_calendario_posicion(md.btc, pd.Series(0.0, index=idx), 0.15, 10, 1)
    assert a["real"] == 0.0 and a["entradas"] == 0 and a["azar_p90"] == 0.0


def test_azar_operaciones_vacio_regresa_vacio(md):
    assert V2.azar_calendario_operaciones(md, pd.DataFrame(), None, None, 10, 1) == {}
    assert V2.azar_calendario_operaciones(md, None, None, None, 10, 1) == {}


# ---------------- tramos y dinero ----------------

def _ops():
    t = pd.to_datetime(["2023-01-05", "2023-02-10"], utc=True)
    return pd.DataFrame({"t_decision": t, "t_entrada": t, "t_salida": t + pd.Timedelta(days=3)})


def test_tramo_corta_por_t_decision_sin_incluir_el_final():
    ops = _ops()
    a, b = ops["t_decision"].iloc[0], ops["t_decision"].iloc[1]
    assert len(V2._tramo(ops, a, b)) == 1
    assert V2._tramo(pd.DataFrame(), a, b).empty


def test_dias_invertido_cuenta_los_dias_abiertos():
    ops = _ops()
    idx = pd.date_range("2023-01-01", "2023-03-01", freq="D", tz="UTC")
    s = V2._dias_invertido(ops, idx)
    assert s.sum() == 6                                   # 3 días por operación (entrada exclusiva, salida inclusiva)
    assert s[pd.Timestamp("2023-01-05", tz="UTC")] == 0 and s[pd.Timestamp("2023-01-08", tz="UTC")] == 1


def test_resumen_dinero_sin_operaciones_es_plano(md):
    a, b = V2.periodos(md.reg)["fuera_de_muestra"]
    curva, din = V2.resumen_dinero(pd.DataFrame(), 1000.0, md.cierres(), a, b)
    assert (curva == 1000.0).all()
    assert din["rend_total_pct"] == pytest.approx(0.0)


# ---------------- compuertas ----------------

def _res(**kw):
    base = dict(clave="M1", nombre="x", calmar_r1_oos=0.5,
                oos_r={"operaciones": 200, "factor_ganancia": 2.0, "expectativa_r": 0.3, "ventanas_positivas_pct": 80},
                oos_curva={"calmar": 1.0}, mc={"caida_p95": 10.0}, mc_bloques={"caida_p95": 12.0},
                azar={"percentil": 95.0}, robustez={"todas_positivas": True, "minimo": 0.1})
    base.update(kw)
    return V2.ResultadoLento(**base)


def test_compuertas_lento_todo_bien_pasa(md):
    c = V2.compuertas_lento(md.reg, _res())
    assert all(ok for ok, _ in c.values()), c


@pytest.mark.parametrize("cambio,compuerta", [
    ({"oos_r": {"operaciones": 5, "factor_ganancia": 2.0, "expectativa_r": 0.3, "ventanas_positivas_pct": 80}}, "operaciones"),
    ({"mc_bloques": {"caida_p95": 40.0}}, "montecarlo"),          # cuenta la peor de las dos versiones
    ({"azar": {"percentil": 50.0}}, "azar"),
    ({"oos_curva": {"calmar": float("nan")}}, "contra_r1"),      # sin Calmar no le gana a R1
    ({"robustez": {}}, "robustez"),
])
def test_compuertas_lento_cada_una_falla_sola(md, cambio, compuerta):
    c = V2.compuertas_lento(md.reg, _res(**cambio))
    assert [k for k, (ok, _) in c.items() if not ok] == [compuerta]


# ---------------- marea, M0 y motor lento completos ----------------

def test_rf_marea_cambia_con_la_media(md):
    m200, m100 = V2.RF_marea(md, 200), V2.RF_marea(md, 100)
    assert m200.index.equals(m100.index)
    assert not m200.equals(m100)


def test_evaluar_m0_completo(md, refs):
    out = V2.evaluar_m0(md, refs)
    assert set(out["robustez"]) == {-20, -10, 0, 10, 20}
    assert [out["robustez"][d]["sma"] for d in (-20, 0, 20)] == [160, 200, 240]
    assert set(out["comisiones"]) == {0.1, 0.15}
    assert set(out["carteras"]) == {"A", "B"}
    assert 0 <= out["ventanas_positivas_pct"] <= 100
    assert out["pasa"] == all(ok for ok, _ in out["compuertas"].values())


def test_evaluar_lento_completo_y_reproducible(md, refs):
    calmar_r1 = refs["R1"].metricas["fuera_de_muestra"]["calmar"]
    a = V2.evaluar_lento(md, "M1", calmar_r1, avisar=lambda *_: None)
    assert a.combos == 2 and len(a.ventanas) == len(V2.ventanas_wf(md.reg))
    assert set(a.compuertas) >= {"operaciones", "azar", "contra_r1", "robustez"}
    assert a.pasa == all(ok for ok, _ in a.compuertas.values())
    assert set(a.comisiones) == {0.1, 0.15} and set(a.carteras) == {"A", "B"}
    for w in a.ventanas:                                   # parámetros elegidos solo con datos de entrenamiento
        assert w["params"]["n"] in (20, 50)
    b = V2.evaluar_lento(md, "M1", calmar_r1, avisar=lambda *_: None, hacer_auditoria=False)
    assert b.oos_r == a.oos_r and b.cupo == {} and b.comisiones == {}
    assert math.isnan(a.calmar_r1_oos) or a.calmar_r1_oos == calmar_r1
