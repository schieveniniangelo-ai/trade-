"""Pruebas de la v2 "MAREA": motores diarios, gestión por canal, curva a valor de mercado,
Monte Carlo en bloques, referencias y reglas nuevas del reglamento."""
import numpy as np
import pandas as pd
import pytest

from sobreviviente import diario as DI
from sobreviviente import referencias as RF
from sobreviviente import regimen as RG
from sobreviviente import reglamento as RGL
from sobreviviente import universo as U
from sobreviviente.backtest import cartera, curva_diaria, simular_operacion
from sobreviviente.estrategias import ESTRATEGIAS
from sobreviviente.estrategias.base import Contexto
from sobreviviente.exchange import Filtros
from sobreviviente.gestion import EstadoGestion, vela
from sobreviviente.metricas import calmar, concentracion, topes_en_curva
from sobreviviente.validacion import bootstrap_diario, montecarlo_bloques
from sobreviviente.validacion_v2 import azar_calendario_posicion

from test_estrategias_backtest import velas_sinteticas


def diarias(n=900, semilla=5, tendencia=0.001):
    return velas_sinteticas(n, semilla=semilla, freq="1D", tendencia=tendencia, onda=0.01, inicio="2022-01-01")


def ctx_diario(df, marea=None, extra=None):
    marea = marea if marea is not None else pd.Series("ALCISTA", index=df.index, dtype=object)
    return Contexto("XUSDT", df, pd.Series(None, index=df.index, dtype=object), marea, extra or {})


# ---------------- M1 y M2: sin ver el futuro ----------------

@pytest.mark.parametrize("n", [20, 50, 100])
def test_m1_sin_adelanto(n):
    df = diarias()
    mod = ESTRATEGIAS["M1"]
    completo = mod.senales(ctx_diario(df), {"n": n})
    assert completo["entrada"].sum() >= 3
    for corte in (400, 650, 899):
        parcial = mod.senales(ctx_diario(df.iloc[:corte]), {"n": n})
        comun = parcial.index[:-1]
        pd.testing.assert_frame_equal(completo.loc[comun, ["entrada", "stop"]], parcial.loc[comun, ["entrada", "stop"]])


def test_m1_stop_con_tope_y_marea():
    df = diarias()
    s = ESTRATEGIAS["M1"].senales(ctx_diario(df), {"n": 50})
    e = s[s["entrada"]]
    assert ((e["precio"] - e["stop"]) / e["precio"] <= 0.15 + 1e-12).all()
    assert (e["stop"] < e["precio"]).all()
    baja = pd.Series("BAJISTA", index=df.index, dtype=object)
    assert ESTRATEGIAS["M1"].senales(ctx_diario(df, baja), {"n": 50})["entrada"].sum() == 0


def _tabla_m2(dfs, L):
    cierres = pd.DataFrame({k: d["close"] for k, d in dfs.items()})
    grandes = pd.DataFrame(True, index=cierres.index, columns=cierres.columns)
    return ESTRATEGIAS["M2"].ranking(cierres, grandes, L)


def test_m2_sin_adelanto_y_solo_domingos():
    dfs = {f"C{i}": diarias(700, semilla=i, tendencia=0.0005 * i) for i in range(1, 6)}
    mod = ESTRATEGIAS["M2"]
    tabla = _tabla_m2(dfs, 30)
    df = dfs["C5"]
    s = mod.senales(ctx_diario(df, extra={"lugar_30": tabla["C5"]}), {"L": 30})
    assert s["entrada"].sum() > 0
    assert (s.index[s["entrada"]].day_of_week == 6).all()
    corte = 500
    tabla_p = _tabla_m2({k: d.iloc[:corte] for k, d in dfs.items()}, 30)
    sp = mod.senales(ctx_diario(df.iloc[:corte], extra={"lugar_30": tabla_p["C5"]}), {"L": 30})
    comun = sp.index[:-1]
    pd.testing.assert_series_equal(s.loc[comun, "entrada"], sp.loc[comun, "entrada"])
    pd.testing.assert_series_equal(s.loc[comun, "salir"], sp.loc[comun, "salir"])


def test_m2_stop_catastrofe():
    df = diarias(300)
    s = ESTRATEGIAS["M2"].senales(ctx_diario(df), {"L": 21})
    assert np.allclose(s["stop"], df["close"] * 0.8)


# ---------------- Gestión por canal ----------------

def test_gestion_canal_sube_stop_y_sale_por_cierre():
    e = EstadoGestion(lado="LARGO", entrada=100, entrada_plan=100, stop_inicial=90, stop=90, meta=None,
                      modo="canal", params={"canal_velas": 3, "_canal_prev": 90.0}, en_r=None)
    ev = vela(e, 100, 105, 99, 104, 1.0, canal=95.0)          # el piso del canal sube a 95
    assert e.stop == 95.0 and not ev.salio
    vela(e, 104, 104, 96, 97, 1.0, canal=94.0)                # el canal baja: el stop NO baja
    assert e.stop == 95.0
    vela(e, 97, 98, 95.5, 95.6, 1.0, canal=95.5)              # el cierre (95.6) no cae bajo el piso previo
    assert not e.salir_en_apertura
    e2 = EstadoGestion(lado="LARGO", entrada=100, entrada_plan=100, stop_inicial=80, stop=80, meta=None,
                       modo="canal", params={"canal_velas": 3, "_canal_prev": 90.0}, en_r=None)
    vela(e2, 100, 100, 89, 89.5, 1.0, canal=89.0)             # cerró bajo el piso previo (90) → sale en la apertura
    ev = vela(e2, 88, 90, 87, 89, 1.0, canal=87.0)
    assert ev.salio and ev.precio == 88 and "canal" in ev.motivo


def test_simular_canal_a_mano():
    """Señal en la vela 0 (cierre 100, canal 95). Entra a 100 en la vela 1; el canal sube a 98 en la vela 2
    y la vela 3 toca 98 → sale en el stop 98. Sin costos: R = (98 − 100) / (100 − 95) = −0.4."""
    a = np.array([[99, 100, 95, 100], [100, 103, 99, 102], [102, 106, 101, 105], [105, 105, 97, 99]], dtype=float)
    arr = {"o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3], "atr": np.ones(4),
           "canal": np.array([95.0, 95.0, 98.0, 97.0])}
    idx = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    s = simular_operacion(arr, idx, 0, "LARGO", 100.0, 95.0, None, {"modo": "canal", "canal_velas": 2,
                          "sin_breakeven": True}, 0.0, 0.0, pd.Timedelta(days=1))
    assert s["salida"] == 98.0 and s["r"] == pytest.approx(-0.4)


# ---------------- A2: curva a valor de mercado ----------------

def test_curva_diaria_a_mano():
    """Compra 2 unidades a 100 a las 00:00 del día 2; cierres siguientes 90 y 120; vende con +20."""
    idx = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    cierres = {"X": pd.Series([100.0, 90.0, 120.0, 110.0], index=idx + pd.Timedelta(days=1))}
    ops = pd.DataFrame([{"simbolo": "X", "lado": "LARGO", "t_entrada": idx[1], "t_salida": idx[3] + pd.Timedelta(days=1),
                         "entrada": 100.0, "cantidad": 2.0, "comision_pct": 0.0, "ganancia_usdt": 20.0}])
    c = curva_diaria(ops, 1000.0, cierres, idx[0], idx[3] + pd.Timedelta(days=1))
    assert list(c.index) == list(pd.date_range(idx[0], periods=5, freq="D"))
    assert c.loc[idx[1]] == 1000.0                     # justo entra, todavía sin cierre posterior
    assert c.loc[idx[2]] == pytest.approx(1000 - 20)   # primer cierre después de entrar: 90 → −20 sin cerrar
    assert c.loc[idx[3]] == pytest.approx(1000 + 40)   # cierre 120
    assert c.iloc[-1] == pytest.approx(1020)           # vendió: +20 ya realizado


def test_cartera_a_mercado_frena_con_perdida_abierta(reg):
    """Con valor a mercado, una posición abierta que va perdiendo SÍ cuenta para los topes."""
    t0 = pd.Timestamp("2024-03-05 00:00", tz="UTC")  # lunes 6 p. m. en CDMX: todo pasa en la misma semana
    base = dict(estrategia="E1", mercado="SPOT", lado="LARGO", cubeta="normales", precio_plan=100.0, stop=99.0,
                meta=None, fuerza=1.0, comision_pct=0.0, desliz_pct=0.0, regimen_btc="ALCISTA", vol_btc=50.0,
                vol_moneda=50.0, pnl_unidad=0.0, comision_unidad=0.0, stops_t=[], stops=[], entrada=100.0)
    filas = [{**base, "simbolo": "A", "t_decision": t0, "t_entrada": t0, "t_salida": t0 + pd.Timedelta(days=10)},
             {**base, "simbolo": "B", "t_decision": t0 + pd.Timedelta(days=2), "t_entrada": t0 + pd.Timedelta(days=2),
              "t_salida": t0 + pd.Timedelta(days=5)}]
    idx = pd.date_range(t0, periods=12, freq="D")
    cierres = {"A": pd.Series(np.r_[100.0, 30.0, np.full(10, 30.0)], index=idx + pd.Timedelta(days=1)),
               "B": pd.Series(100.0, index=idx + pd.Timedelta(days=1))}
    filt = {s: Filtros(s, 0.01, 0.001, 0.001, 5) for s in ("A", "B")}
    r = reg.copia_con({"riesgo.calor_total_max_pct": 3.0})
    # Sin valor a mercado nadie "ve" que A va perdiendo (en este caso su stop no se simuló): B entra.
    sin = cartera(r, pd.DataFrame(filas), 1000.0, filt, ["E1"])
    con = cartera(r, pd.DataFrame(filas), 1000.0, filt, ["E1"], cierres=cierres)
    assert sin.decisiones["aprobada"].tolist() == [True, True]
    # A vale 300 USDT (tope de 30 %) y cae 70 %: −210 USDT sin cerrar → tope semanal → B no entra.
    assert con.decisiones["aprobada"].tolist() == [True, False]
    assert "PAUSA" in con.decisiones["razon"].iloc[1] or "DETENIDO" in con.decisiones["razon"].iloc[1]


# ---------------- A1: Monte Carlo en bloques ----------------

def test_montecarlo_bloques_mantiene_juntas_las_perdidas():
    t = pd.date_range("2024-01-01", periods=60, freq="D", tz="UTC")
    r = np.r_[np.full(10, -1.0), np.full(50, 0.3)]          # 10 pérdidas seguidas al inicio
    ops = pd.DataFrame({"t_salida": t, "r": r})
    mb = montecarlo_bloques(ops, 1.0, 400, 1, 15.0, dias_bloque=10)
    assert mb["bloques"] == 6
    assert mb["racha_p95"] >= 10                             # los bloques conservan la racha completa


def test_bootstrap_diario_rango():
    idx = pd.date_range("2022-01-01", periods=400, freq="D", tz="UTC")
    rng = np.random.default_rng(3)
    c = pd.Series(np.cumprod(1 + rng.normal(0.001, 0.02, 400)), index=idx)
    b = bootstrap_diario(c, 200, 1, 20)
    assert b["caida_p5"] <= b["caida_p50"] <= b["caida_p95"]
    assert b["calmar_p5"] <= b["calmar_p95"]


# ---------------- Métricas nuevas ----------------

def caida_pct(c):
    pico = np.maximum.accumulate(c.values)
    return float(((pico - c.values) / pico).max())


def test_calmar_y_concentracion_y_topes():
    idx = pd.date_range("2022-01-01", periods=366, freq="D", tz="UTC")
    c = pd.Series(np.linspace(100, 120, 366), index=idx)
    c.iloc[100:110] = 80
    assert calmar(c) == pytest.approx(0.2 / caida_pct(c), rel=1e-2)
    assert concentracion(np.array([5, 1, 1, -2, 1, 1, 1]), 1) == pytest.approx(5 / 8 * 100)
    t = topes_en_curva(c, 3.0, 6.0, 15.0)
    assert t["dias_tope_diario"] == 1 and t["veces_freno"] == 1 and t["semanas_tope_semanal"] >= 1


# ---------------- Referencias ----------------

def test_r1_a_mano():
    """BTC sube 10 % al día siguiente de que la marea se pone alta. Costo 0.15 % por lado."""
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    btc = pd.DataFrame({"open": [100, 100, 100, 110, 110], "close": [100, 100, 100, 110, 110]}, index=idx, dtype=float)
    marea = pd.Series(["BAJISTA", "ALCISTA", "ALCISTA", "ALCISTA", "ALCISTA"], index=idx, dtype=object)
    c, pos, ops = RF.r1_marea(btc, marea, idx[0], idx[-1], 0.15)
    assert pos.tolist() == [0, 0, 1, 1, 1]          # decide al cierre del día 2 → dentro desde la apertura del día 3
    assert ops == 1
    assert c.iloc[2] == pytest.approx(1 + 0.10 - 0.0015)   # día 3: +10 % de apertura a apertura, menos la compra


def test_r2_canasta_sale_a_usdt():
    idx = pd.date_range("2024-01-01", periods=40, freq="D", tz="UTC")
    velas = {s: pd.DataFrame({"open": np.linspace(10, 20, 40) * (k + 1)}, index=idx) for k, s in enumerate("AB")}
    grandes = pd.DataFrame(True, index=idx, columns=["A", "B"])
    vm = pd.DataFrame({"A": 2.0, "B": 1.0}, index=idx)
    marea = pd.Series("ALCISTA", index=idx, dtype=object)
    marea.iloc[20:] = "BAJISTA"
    c, inv, ops = RF.r2_canasta(velas, grandes, vm, marea, idx[0], idx[-1], 0.0, n=2)
    assert inv.iloc[5] == pytest.approx(1.0) and inv.iloc[-1] == 0.0
    assert c.iloc[21] == pytest.approx(c.iloc[-1])     # en USDT ya no se mueve


def test_azar_calendario_posicion_conserva_tiempo():
    idx = pd.date_range("2023-01-01", periods=300, freq="D", tz="UTC")
    precios = pd.DataFrame({"open": np.linspace(100, 200, 300)}, index=idx)
    pos = pd.Series(([1.0] * 30 + [0.0] * 20) * 6, index=idx)
    r = azar_calendario_posicion(precios, pos, 0.1, 100, 1)
    assert r["entradas"] == 6 and r["tiempo_invertido_pct"] == pytest.approx(60.0)
    assert 0 <= r["percentil"] <= 100


# ---------------- Universo grandes y marea ----------------

def test_grandes_sin_memes_y_sin_futuro(reg):
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    vm = pd.DataFrame({"A": [3, 3, 3, 1, 1], "B": [2, 2, 2, 2, 2], "DOGE": [9, 9, 9, 9, 9], "C": [1, 1, 1, 3, 3]},
                      index=idx, dtype=float)
    per = pd.DataFrame(True, index=idx, columns=vm.columns)
    g = U.grandes(vm, per, {"DOGE"}, n=2)
    assert "DOGE" not in g.columns
    assert g.loc[idx[0], ["A", "B"]].all() and not g.loc[idx[0], "C"]
    assert g.loc[idx[4], ["B", "C"]].all() and not g.loc[idx[4], "A"]


def test_marea_diaria(reg):
    idx = pd.date_range("2023-01-01", periods=260, freq="D", tz="UTC")
    btc = pd.DataFrame({"close": np.r_[np.full(230, 100.0), np.full(30, 120.0)]}, index=idx)
    m = RG.marea_diaria(btc, reg)
    assert m.iloc[198] is None and m.iloc[220] == "BAJISTA" and m.iloc[-1] == "ALCISTA"


# ---------------- Reglamento 2.0.0 ----------------

def test_reglamento_v2_carteras_validas():
    r = RGL.cargar()
    assert r.version.startswith("2.")
    a, b = r.para_cartera("A"), r.para_cartera("B")
    assert a.riesgo["riesgo_por_operacion_pct"] == 1.0 and b.riesgo["riesgo_por_operacion_pct"] == 2.0
    assert b.riesgo["posiciones_max"]["normales"] == 2
    for k in ("E1", "E2", "E3", "E4", "E5", "M0", "M1", "M2", "M3"):
        assert r.estrategias[k]["estado"] in ("APAGADA", "PAPEL")
    for k in ("M0", "M1", "M2"):
        assert r.estrategias[k]["mover_a_entrada"] is False


def test_freno_minimo_15_veces_el_riesgo():
    r = RGL.cargar()
    malo = r.copia_con({"carteras.B.caida_max_desde_pico_pct": 15.0})
    with pytest.raises(RGL.ErrorReglamento) as e:
        RGL.validar(malo)
    assert "15 veces" in str(e.value) and "Cartera B" in str(e.value)


def test_cartera_b_con_3_posiciones_choca_con_tope_diario():
    r = RGL.cargar()
    malo = r.copia_con({"carteras.B.posiciones_max": {"normales": 3, "memes": 0, "futuros": 0}})
    with pytest.raises(RGL.ErrorReglamento) as e:
        RGL.validar(malo)
    assert "tope diario" in str(e.value)


# ---------------- ESTELA ----------------

def test_estela_indicadores_sin_futuro():
    from sobreviviente import estela as ES
    assert ES.parte_larga(pd.Series([1.0, 3.0])).tolist() == [0.5, 0.75]
    rng = np.random.default_rng(1)
    s = pd.Series(rng.normal(0.5, 0.05, 300), index=pd.date_range("2022-01-01", periods=300, freq="D", tz="UTC"))
    z_completo = ES.z_movil(s, 90)
    z_corto = ES.z_movil(s.iloc[:200], 90)
    pd.testing.assert_series_equal(z_completo.iloc[:200], z_corto)
    p_completo = ES.percentil_previo(s, 90)
    pd.testing.assert_series_equal(p_completo.iloc[:200], ES.percentil_previo(s.iloc[:200], 90))


def test_estela_rendimiento_desde_apertura_siguiente():
    from sobreviviente import estela as ES
    idx = pd.date_range("2022-01-01", periods=200, freq="D")
    serie = pd.DataFrame({"dia": idx.strftime("%Y-%m-%d"), "top_posiciones": 1.0, "masa_cuentas": 1.0})
    velas = pd.DataFrame({"open": np.arange(1.0, 201.0)}, index=idx.tz_localize("UTC"))
    t = ES.tabla_simbolo(serie, velas)
    # Señal el día 0 → entra en la apertura del día 1 (precio 2) → mide hasta la del día 4 (precio 5)
    assert t["ret_3"].iloc[0] == pytest.approx(5 / 2 - 1)


# ---------------- Backtester diario: de punta a punta con datos sintéticos ----------------

def test_generar_diario_punta_a_punta(reg):
    velas = {s: diarias(800, semilla=i + 10, tendencia=0.0008 + 0.0003 * i) for i, s in enumerate(["BTCUSDT", "AUSDT", "BUSDT"])}
    for df in velas.values():
        df["quote_volume"] = 5e8
    md = DI.preparar(reg, velas, None, [], exchange_info={"symbols": []}, btc_largo=velas["BTCUSDT"])
    c = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01")
    assert not c.empty
    assert (c["t_decision"] == c["t_senal"] + pd.Timedelta(days=1)).all()
    assert (c["t_entrada"] == c["t_decision"]).all()
    rc = cartera(reg.para_cartera("A"), c, 10000.0, md.filtros, ["M1"], cierres=md.cierres())
    assert not rc.operaciones.empty
    c2 = DI.generar(md, "M2", {"L": 21}, "2022-06-01", "2024-02-01")
    assert c2.empty or (c2["t_senal"].dt.day_of_week == 6).all()
    # Error que hubo: con la caché de contextos, la segunda L no veía su tabla y salía sin señales.
    c3 = DI.generar(md, "M2", {"L": 30}, "2022-06-01", "2024-02-01")
    md2 = DI.preparar(reg, velas, None, [], exchange_info={"symbols": []}, btc_largo=velas["BTCUSDT"])
    c3_limpio = DI.generar(md2, "M2", {"L": 30}, "2022-06-01", "2024-02-01")
    assert len(c3) == len(c3_limpio)


def test_excluir_bases_del_reglamento(reg):
    r = reg.copia_con({"universo.excluir_bases": ["SOXLB"]})
    assert not U.nombre_permitido(r, "SOXLBUSDT", {"SOXLB"})[0]
    assert U.nombre_permitido(reg, "SOXLBUSDT", {"SOXLB"})[0]   # vacía por defecto: no cambia nada


def test_veto_estela_en_backtest_quita_solo_los_dias_vetados(reg):
    velas = {s: diarias(800, semilla=i + 10, tendencia=0.0008 + 0.0003 * i) for i, s in enumerate(["BTCUSDT", "AUSDT", "BUSDT"])}
    for df in velas.values():
        df["quote_volume"] = 5e8
    md = DI.preparar(reg, velas, None, [], exchange_info={"symbols": []}, btc_largo=velas["BTCUSDT"])
    sin = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01")
    assert len(sin) >= 2
    vetado = sin.iloc[0]
    # Fechas como las da la serie de ESTELA (otra resolución de tiempo que las velas): deben coincidir igual
    dia = pd.Timestamp(vetado["t_senal"].strftime("%Y-%m-%d"), tz="UTC")
    md.veto = {vetado["simbolo"]: {dia}}
    con = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01")
    assert len(con) == len(sin) - 1
    assert not ((con["simbolo"] == vetado["simbolo"]) & (con["t_senal"] == vetado["t_senal"])).any()


def test_dias_veto_h2_igual_que_en_vivo():
    from sobreviviente import estela as ES
    idx = pd.date_range("2025-01-01", periods=150, freq="D", tz="UTC")
    rng = np.random.default_rng(4)
    s = pd.Series(rng.normal(0.6, 0.03, 150), index=idx)
    p = ES.percentil_previo(s, 90)
    dias = set(p.index[p >= 90])
    for d in idx[100:]:
        assert (d in dias) == bool(ES.veto_h2(s, d))
