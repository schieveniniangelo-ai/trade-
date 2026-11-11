"""Arreglo 72 (banco de filtros, fase 4): métricas por filtro en las ventanas de prueba.

Con pocas operaciones falsas, las cifras deben coincidir con `metricas.resumen_r` y `caida_maxima_pct`, y cada
señal bloqueada debe traer el R de la simulación que ya tenía el candidato. Sin red y sin llaves."""
import pandas as pd
import pytest

from sobreviviente import banco_filtros as BF
from sobreviviente import descartes as DS
from sobreviviente.metricas import caida_maxima_pct, resumen_r

from test_arreglo71_banco_filtros_fase3 import CFG, FILTROS, _dos_ventanas, _fila, _pool

JULIO = pd.Timestamp("2023-07-01", tz="UTC")


@pytest.fixture
def wf(reg):
    return BF.walk_forward(_dos_ventanas(reg), CFG, _pool(), FILTROS)


# ---------------- Las cifras coinciden con resumen_r y caida_maxima_pct ----------------

def test_metricas_de_la_linea_base_a_mano(wf):
    base = wf.corridas["A"][BF.BASE]
    ops = base.resultado.operaciones
    # Capital 1000, riesgo 1 %, stop a 5 de distancia: AUSDT 2 × +10 = +20; BUSDT 2.04 × −5 = −10.2; CUSDT 2.019 × +10
    assert list(ops["simbolo"]) == ["AUSDT", "BUSDT", "CUSDT", "DUSDT"]
    assert list(ops["ganancia_usdt"].round(2)) == [20.0, -10.2, 20.19, -10.3]
    m = BF.metricas_corrida(wf, base)
    assert list(m) == [BF.TODAS, "2023-01", "2023-04", "prueba final"]
    todas = m[BF.TODAS]
    en_wf = ops[ops["t_decision"] < JULIO]
    esperado = resumen_r(en_wf["r"].to_numpy(float))
    assert todas["operaciones"] == 3 == esperado["operaciones"]
    assert todas["pct_ganadoras"] == pytest.approx(esperado["pct_ganadoras"]) == pytest.approx(200 / 3)
    assert todas["expectativa_r"] == pytest.approx(esperado["expectativa_r"]) == pytest.approx(1.0)      # (+2 −1 +2) / 3
    assert todas["factor_ganancia"] == pytest.approx(esperado["factor_ganancia"]) == pytest.approx(4.0)  # 4R ÷ 1R
    assert todas["ganancia_usdt"] == pytest.approx(en_wf["ganancia_usdt"].sum()) == pytest.approx(29.99)
    assert todas["expectativa_usdt"] == pytest.approx(en_wf["ganancia_usdt"].mean())
    curva = BF.curva_de(base, pd.Timestamp("2023-01-01", tz="UTC"), JULIO)
    assert todas["caida_max_pct"] == pytest.approx(caida_maxima_pct(curva.to_numpy(float))) == pytest.approx(1.0)  # 1020 → 1009.8
    # Cada ventana por separado
    assert (m["2023-01"]["operaciones"], m["2023-01"]["pct_ganadoras"], m["2023-01"]["expectativa_r"]) == (2, 50.0, 0.5)
    assert (m["2023-04"]["operaciones"], m["2023-04"]["expectativa_r"]) == (1, 2.0)
    assert m["2023-04"]["factor_ganancia"] == float("inf") and m["2023-04"]["caida_max_pct"] == pytest.approx(1.0)
    assert (m["prueba final"]["operaciones"], m["prueba final"]["expectativa_r"]) == (1, -1.0)
    assert m["prueba final"]["ganancia_usdt"] == pytest.approx(-10.3, abs=0.01)


def test_metricas_sin_operaciones():
    m = BF.metricas(None)
    assert m == {"operaciones": 0, "pct_ganadoras": 0.0, "expectativa_r": 0.0, "factor_ganancia": 0.0,
                 "expectativa_usdt": 0.0, "ganancia_usdt": 0.0}
    assert BF.metricas(pd.DataFrame(), pd.Series([100.0, 90.0, 95.0]))["caida_max_pct"] == pytest.approx(10.0)


def test_el_dinero_usa_el_pnl_ya_simulado_sin_otra_comision(wf):
    ops = wf.corridas["A"][BF.BASE].resultado.operaciones
    assert (ops["ganancia_usdt"] == ops["cantidad"] * ops["pnl_unidad"]).all()
    m = BF.metricas(ops)
    assert m["ganancia_usdt"] == pytest.approx(float((ops["cantidad"] * ops["pnl_unidad"]).sum()))


def test_tabla_de_metricas_con_la_diferencia_contra_la_base(wf):
    t = BF.tabla_metricas(wf)
    assert len(t) == 3 * 4                                   # BASE + 2 filtros pedidos, × (TODAS, 2 ventanas, prueba final)
    assert set(t["experimento"]) == {BF.BASE, DS.YA_HAY_POSICION, DS.FUERA_DE_UNIVERSO} and set(t["cartera"]) == {"A"}
    base = t[t["experimento"] == BF.BASE]
    assert (base[[c for c in t.columns if c.startswith("dif_")]] == 0).all().all() and (base["accion"] == "").all()
    fila = t[(t["experimento"] == DS.YA_HAY_POSICION) & (t["ventana"] == BF.TODAS)].iloc[0]
    assert fila["accion"] == "apagar" and fila["operaciones"] == 4 and fila["dif_operaciones"] == 1
    assert fila["dif_ganancia_usdt"] == pytest.approx(fila["ganancia_usdt"] - 29.99)
    solo_abril = t[(t["experimento"] == DS.YA_HAY_POSICION) & (t["ventana"] == "2023-04")].iloc[0]
    assert solo_abril["dif_operaciones"] == 1                # la operación de más cayó en la segunda ventana
    enero = t[(t["experimento"] == DS.YA_HAY_POSICION) & (t["ventana"] == "2023-01")].iloc[0]
    assert enero["dif_operaciones"] == 0 and enero["dif_expectativa_r"] == 0
    for col in ("operaciones", "pct_ganadoras", "expectativa_r", "expectativa_usdt", "factor_ganancia", "caida_max_pct"):
        assert col in t.columns


# ---------------- Señales bloqueadas: cuántas y qué habría pasado (operación suelta) ----------------

def test_la_senal_bloqueada_trae_el_r_de_su_simulacion(wf):
    b = BF.senales_bloqueadas(wf, "A", DS.YA_HAY_POSICION)
    assert len(b) == 1
    fila = b.iloc[0]
    cand = wf.pool.base[(wf.pool.base["simbolo"] == "BUSDT") & (wf.pool.base["t_decision"] == fila["t_decision"])].iloc[0]
    assert (fila["simbolo"], str(fila["t_decision"].date())) == ("BUSDT", "2023-04-05")
    assert fila["r"] == cand["r"] == 2.0 and fila["pnl_unidad"] == cand["pnl_unidad"] == 10.0
    # En USDT: r × capital de ese momento (1020, tras ganar 20 con AUSDT) × 1 % de riesgo de la Cartera A
    assert fila["capital"] == pytest.approx(1020.0) and fila["usdt_nominal"] == pytest.approx(2.0 * 1020.0 * 0.01)
    r = BF.resumen_bloqueadas(b)
    assert (r["senales"], r["con_simulacion"], r["sueltas_expectativa_r"], r["sueltas_suma_r"]) == (1, 1, 2.0, 2.0)
    assert r["sueltas_pct_ganadoras"] == 100.0 and r["sueltas_usdt_nominal"] == pytest.approx(20.4)
    # Y con ese filtro apagado, la cartera sí hizo esa operación (el efecto completo lo da la corrida, no la suelta)
    ops = wf.corridas["A"][DS.YA_HAY_POSICION].resultado.operaciones
    assert ((ops["simbolo"] == "BUSDT") & (ops["t_decision"] == fila["t_decision"])).any()


def test_bloqueadas_antes_del_motor_de_riesgo(wf):
    b = BF.senales_bloqueadas(wf, "A", DS.FUERA_DE_UNIVERSO)
    assert [(x.simbolo, str(x.t_decision.date()), x.r) for x in b.itertuples()] == [("EUSDT", "2023-05-20", 2.0)]
    assert b["usdt_nominal"].iloc[0] == pytest.approx(2.0 * 1000.0 * 0.01)        # sin capital anotado: el inicial
    assert BF.senales_bloqueadas(wf, "A", DS.CALOR_LLENO).empty                   # un filtro que no bloqueó nada
    assert BF.resumen_bloqueadas(BF.senales_bloqueadas(wf, "A", DS.CALOR_LLENO))["senales"] == 0


def test_bloqueada_sin_simulacion_cuenta_pero_no_inventa_resultado(reg):
    pool = _pool()
    pool.previos.append(DS.registro(DS.STOP_O_SIMULACION, "sin stop", "CUSDT", pd.Timestamp("2023-02-01", tz="UTC"), "",
                                    "M1", origen="generacion"))
    wf = BF.walk_forward(_dos_ventanas(reg), CFG, pool, FILTROS)
    r = BF.resumen_bloqueadas(BF.senales_bloqueadas(wf, "A", DS.STOP_O_SIMULACION))
    assert (r["senales"], r["con_simulacion"], r["sueltas_suma_r"], r["sueltas_expectativa_r"]) == (1, 0, 0.0, 0.0)


def test_lo_que_bloquearia_estela_si_se_enciende(reg):
    pool = _pool()
    cusdt = pool.base[pool.base["simbolo"] == "CUSDT"].iloc[0]
    pool.veto_estela = {"CUSDT": {cusdt["t_senal"]}}
    cfg = BF.ConfigBanco(carteras=("A",), motores=("M1",), encendidos=("M1",), capital=1000.0, filtros=(DS.VETO_ESTELA,))
    wf = BF.walk_forward(_dos_ventanas(reg), cfg, pool, FILTROS)
    b = BF.senales_bloqueadas(wf, "A", DS.VETO_ESTELA)
    assert [(x.simbolo, x.r, x.pnl_unidad) for x in b.itertuples()] == [("CUSDT", 2.0, 10.0)]
    assert b["capital"].iloc[0] == pytest.approx(1009.8)                           # el capital que había al decidir
    t = BF.tabla_metricas(wf)
    fila = t[(t["experimento"] == DS.VETO_ESTELA) & (t["ventana"] == BF.TODAS)].iloc[0]
    assert fila["accion"] == "encender" and fila["dif_operaciones"] == -1


def test_tabla_de_bloqueadas(wf):
    t = BF.tabla_bloqueadas(wf)
    assert set(t["ventana"]) == {BF.TODAS, "prueba final"} and set(t["cartera"]) == {"A"}
    assert BF.codigos_con_bloqueos(wf, "A") == [DS.YA_HAY_POSICION, DS.FUERA_DE_UNIVERSO]
    uno = t[(t["filtro"] == DS.YA_HAY_POSICION) & (t["ventana"] == BF.TODAS)].iloc[0]
    assert (uno["senales"], uno["con_simulacion"], uno["sueltas_expectativa_r"]) == (1, 1, 2.0)
    final = t[(t["filtro"] == DS.YA_HAY_POSICION) & (t["ventana"] == "prueba final")].iloc[0]
    assert final["senales"] == 0
    for col in ("senales", "con_simulacion", "sueltas_pct_ganadoras", "sueltas_expectativa_r", "sueltas_suma_r",
                "sueltas_usdt_nominal", "sueltas_factor_ganancia"):
        assert col in t.columns


def test_bloqueadas_por_tramo(wf):
    v1, v2, final = wf.ventanas
    assert BF.senales_bloqueadas(wf, "A", DS.YA_HAY_POSICION, v1.prueba).empty
    assert len(BF.senales_bloqueadas(wf, "A", DS.YA_HAY_POSICION, v2.prueba)) == 1
    assert [n for n, _ in BF.tramos(wf)] == [BF.TODAS, "2023-01", "2023-04", "prueba final"]
