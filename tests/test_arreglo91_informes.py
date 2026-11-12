"""Arreglo 91: fija la salida de informe.py, ronda2.py, ejecutar_v2.py e informe_v2.py (estaban en 0 %).

Los cuatro se usan desde `python -m sobreviviente validar` (y estela/ronda2/informe_v2 los importan), así que no se
borran: se prueban con datos falsos chicos, sin red ni llaves. Las gráficas se prueban por la rama "sin matplotlib"
(así da igual si está instalado) y la fecha de "Generado el" se fija. Las salidas de referencia están en
tests/datos_arreglo91/ y salieron del código tal como estaba (antes de partir informe_v2.escribir, E4.5).
"""
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sobreviviente import ejecutar_v2, informe, informe_v2, ronda2
from sobreviviente.validacion import ResultadoValidacion

REFERENCIAS = Path(__file__).parent / "datos_arreglo91"


class _Fijo(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 11, 18, 30)


@pytest.fixture
def sin_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)       # `import matplotlib` → ImportError


@pytest.fixture
def fecha_fija(monkeypatch):
    for mod in (informe, ronda2, informe_v2):
        monkeypatch.setattr(mod, "datetime", _Fijo)


def _igual_a_referencia(generado: Path, nombre: str) -> None:
    esperado = (REFERENCIAS / nombre).read_text(encoding="utf-8")
    assert generado.read_text(encoding="utf-8") == esperado


# ---------------------------------------------------------------- informe.py

def _resultado(clave, pasa, robustez, **kw) -> ResultadoValidacion:
    r = ResultadoValidacion(clave=clave, nombre=f"Estrategia {clave}", ronda_ajuste=2, combos=12)
    r.pasa = pasa
    r.params_finales = {"n": 20, "stop_atr": 2.0}
    r.compuertas = {"ops": (True, "Al menos 100 operaciones fuera de muestra"),
                    "exp": (pasa, "Expectativa mayor que +0.05R")}
    r.oos_r = {"operaciones": 140, "pct_ganadoras": 41.5, "ganancia_prom_r": 2.1, "perdida_prom_r": -1.0,
               "expectativa_r": 0.1234 if pasa else -0.05, "factor_ganancia": 1.45, "racha_perdedora_max": 9,
               "ventanas_positivas_pct": 64.0}
    r.oos_cartera = {"rendimiento_pct": 18.4, "caida_max_pct": 9.7, "comisiones_pct_bruto": 22.0}
    r.mc = {"rend_p5": -3.2, "rend_p95": 41.0, "rend_p50": 17.5, "caida_p50": 8.1, "caida_p95": 14.9,
            "prob_caida_alerta": 4.2, "racha_p50": 7, "racha_p95": 12, "_caidas": [1.0, 2.0]}
    r.azar = {"exp_azar_p50": -0.02, "exp_azar_p90": 0.04, "percentil_estrategia": 96.0}
    r.btc = {"oos": {"rend_pct": 55.0, "caida_pct": 30.2}, "holdout": {"rend_pct": -4.0}}
    r.por_regimen = {"ALCISTA": {"operaciones": 100, "expectativa_r": 0.2, "factor_ganancia": 1.7},
                     "LATERAL": {"operaciones": 40, "expectativa_r": float("nan"), "factor_ganancia": None}}
    r.holdout = {"operaciones": 21, "expectativa_r": 0.08, "factor_ganancia": 1.2, "rendimiento_pct": 3.3}
    r.real = {"candidatos": 50, "ejecutadas": 20, "saltadas_capital": 30, "capital_necesario_mediana": 120.0,
              "capital_necesario_p75": 260.0}
    r.robustez = robustez
    r.ventanas = [{"prueba": "2023-01 a 2023-03", "params": {"n": 20}, "n_prueba": 11, "r_prueba": 2.5},
                  {"prueba": "2023-04 a 2023-06", "params": {"n": 30}}]
    r.notas = ["una nota de prueba"]
    r.curva_oos = pd.Series([100.0, 101.0, 99.0], index=pd.date_range("2023-01-01", periods=3, tz="UTC"))
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def _resultados_informe():
    rb = lambda vals, todas: {"ejes": ["n", "stop_atr"], "pasos": [-20, 0, 20], "minimo": min(vals),
                              "todas_positivas": todas, "tabla": {(i, 0): [v, 10] for i, v in enumerate(vals)}}
    return [_resultado("E1", True, rb([0.1, 0.2], True)),
            _resultado("E2", False, rb([-0.1, float("nan"), 0.0], False), real={"candidatos": 5, "ejecutadas": 5,
                                                                                    "saltadas_capital": 0}),
            _resultado("E3", False, rb([-0.1, 0.3], False)),
            _resultado("E4", False, {}, mc={}, azar={}, btc={}, por_regimen={}, real={}, notas=[])]


def test_informe_formatos():
    assert informe._f(None) == "—" and informe._f(float("nan")) == "—" and informe._f(float("inf")) == "—"
    assert informe._f(1.23456) == "1.23" and informe._f(0.5, 1, True) == "+0.5" and informe._f(-2, 0) == "-2"
    assert informe._mes(pd.Timestamp("2026-11-01")) == "noviembre de 2026"


def test_informe_graficas_sin_matplotlib(sin_matplotlib, tmp_path):
    assert informe.graficas(_resultados_informe()[0], tmp_path / "img") == {}
    assert not (tmp_path / "img").exists()


def test_informe_escribir_igual_a_referencia(reg, tmp_path, sin_matplotlib, fecha_fija):
    ruta = tmp_path / "VALIDACION.md"
    informe.escribir(_resultados_informe(), reg, ruta, ["nota de datos uno", "nota de datos dos"])
    _igual_a_referencia(ruta, "VALIDACION.md")


def test_informe_escribir_sin_ninguna_que_pase(reg, tmp_path, sin_matplotlib, fecha_fija):
    ruta = tmp_path / "VALIDACION.md"
    informe.escribir(_resultados_informe()[1:], reg, ruta, [])
    texto = ruta.read_text(encoding="utf-8")
    assert "**Ninguna estrategia pasó todas las pruebas.**" in texto and "Pasaron las pruebas" not in texto


# ---------------------------------------------------------------- ronda2.py

_CLAVES_ANIO = ["Comprar y aguantar BTC", "DCA: comprar BTC cada lunes", "Tendencia pura: solo BTC (media 200 días)",
                "Tendencia pura: BTC + ETH (media 200 días)", "Rotación pura: top 3, fuerza de 60 días",
                "Rotación pura: top 5, fuerza de 60 días"]


def _refs_ronda2():
    idx = pd.date_range("2022-01-01", "2026-10-31", freq="D", tz="UTC")
    curvas = {k: pd.Series(100.0 * (1 + 0.0002 * (i + 1)) ** np.arange(len(idx)), index=idx)
              for i, k in enumerate(_CLAVES_ANIO)}
    mt = {"rend_total_pct": 120.0, "rend_anual_pct": 18.2, "caida_max_pct": 55.0, "volatilidad_pct": 60.0,
          "sharpe": 0.31}
    metricas = {"Comprar y aguantar BTC": mt, "DCA: comprar BTC cada lunes": {**mt, "tiempo_invertido_pct": 100.0},
                "Tendencia pura: solo BTC (media 200 días)": {**mt, "tiempo_invertido_pct": 54.0},
                "Rotación pura: top 3, fuerza de 60 días": {**mt, "rend_total_pct": float("nan")},
                "Vacía": {}}
    return {"2022-01 a 2026-10 (principal)": {"curvas": curvas, "metricas": metricas, "operaciones": {}},
            "2026-05 a 2026-10 (ya abierto)": {"curvas": {}, "metricas": {"Comprar y aguantar BTC": mt},
                                               "operaciones": {}}}


def _resultados_ronda2():
    a = _resultado("E6", True, {}, ic_inferior=0.012, ya_abierto={"operaciones": 7, "expectativa_r": 0.05},
                   por_anio={"2023": {"operaciones": 30, "expectativa_r": 0.11},
                             "2024": {"operaciones": 25, "expectativa_r": -0.02}})
    b = _resultado("E7", False, {}, ic_inferior=None, mc={}, azar={}, btc={}, por_regimen={}, real={}, notas=[])
    return [a, b]


def test_ronda2_formato_y_grafica_sin_matplotlib(sin_matplotlib, tmp_path):
    assert ronda2._f(None) == "—" and ronda2._f(1.25) == "1.2" and ronda2._f(3, 0, True) == "+3"
    assert ronda2.grafica_referencias(_refs_ronda2(), tmp_path) is None


def test_ronda2_escribir_igual_a_referencia(reg, tmp_path, sin_matplotlib, fecha_fija):
    ruta = tmp_path / "VALIDACION_RONDA2.md"
    ronda2.escribir(_resultados_ronda2(), _refs_ronda2(), reg, ruta)
    _igual_a_referencia(ruta, "VALIDACION_RONDA2.md")


def test_ronda2_ninguna_pasa(reg, tmp_path, sin_matplotlib, fecha_fija):
    ruta = tmp_path / "R2.md"
    ronda2.escribir(_resultados_ronda2()[1:], _refs_ronda2(), reg, ruta)
    assert "**Ninguna estrategia de la ronda 2 pasó todas las compuertas" in ruta.read_text(encoding="utf-8")


def test_ronda2_ejecutar_valida_las_tres_y_escribe(reg, tmp_path, monkeypatch, sin_matplotlib, fecha_fija):
    llamadas = []

    def evaluar(m, k, avisar, ronda_ajuste, ronda2):
        llamadas.append((k, ronda_ajuste, ronda2))
        return _resultado(k, k == "E6", {}, ic_inferior=0.0)

    monkeypatch.setattr(ronda2, "evaluar", evaluar)
    monkeypatch.setattr(ronda2, "referencias", lambda m: _refs_ronda2())
    avisos = []
    m = SimpleNamespace(reg=reg)
    res, refs = ronda2.ejecutar(m, tmp_path / "R2.md", avisar=avisos.append)
    assert llamadas == [("E1D", 2, True), ("E6", 1, True), ("E7", 1, True)]
    assert [r.clave for r in res] == ronda2.CLAVES and "2022-01 a 2026-10 (principal)" in refs
    assert avisos[-1] == "Calculando referencias…" and "  E6: PASA" in avisos and "  E7: NO PASA" in avisos
    assert "## E1D — Estrategia E1D: ❌ NO PASA" in (tmp_path / "R2.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- ejecutar_v2.py

@pytest.fixture
def salida_v2(tmp_path, monkeypatch):
    carpeta = tmp_path / "v2"
    monkeypatch.setattr(ejecutar_v2, "SALIDA", carpeta)
    monkeypatch.setattr(ejecutar_v2.D, "ClienteBinance", lambda reg: "cliente-falso")   # sin red
    return carpeta


def test_guardar_y_cargar_resultado(salida_v2):
    assert ejecutar_v2.cargar_resultado("M1") is None
    ejecutar_v2._guardar("M1", {"pasa": False, "oos_r": {"operaciones": 3}})
    assert (salida_v2 / "M1.pkl").exists()
    assert ejecutar_v2.cargar_resultado("M1") == {"pasa": False, "oos_r": {"operaciones": 3}}


def test_conteo_con_y_sin_veto_filtra_la_ventana_y_devuelve_el_veto(monkeypatch):
    from sobreviviente import diario as DI
    vistos = []
    a, b = pd.Timestamp("2024-01-10", tz="UTC"), pd.Timestamp("2024-01-20", tz="UTC")

    def generar(md, clave, params, inicio, fin):
        vistos.append((md.veto, clave, inicio, fin))
        return pd.DataFrame({"t_decision": pd.date_range("2024-01-08", periods=15, freq="D", tz="UTC")})

    monkeypatch.setattr(DI, "generar", generar)
    md = SimpleNamespace(veto="VETO")
    c = ejecutar_v2.DI_generar_conteo(md, "M1", {}, a, b, con_veto=False)
    assert len(c) == 10 and c["t_decision"].min() == a and c["t_decision"].max() < b
    assert vistos == [(None, "M1", a - DI.DIA, b)] and md.veto == "VETO"
    ejecutar_v2.DI_generar_conteo(md, "M1", {}, a, b, con_veto=True)
    assert vistos[-1][0] == "VETO"
    monkeypatch.setattr(DI, "generar", lambda *x: pd.DataFrame())
    assert ejecutar_v2.DI_generar_conteo(md, "M1", {}, a, b, con_veto=False).empty

    def falla(*x):
        raise RuntimeError("se cayó")
    monkeypatch.setattr(DI, "generar", falla)
    with pytest.raises(RuntimeError):
        ejecutar_v2.DI_generar_conteo(md, "M1", {}, a, b, con_veto=False)
    assert md.veto == "VETO"                                      # aunque falle, el veto regresa


def _fakes_v2(monkeypatch):
    from sobreviviente import validacion_v2 as V2
    refs = {k: SimpleNamespace(nombre=f"Ref {k}", por_anio={2024: 1.0}, curvas={}, invertido=None,
                               metricas={"fuera_de_muestra": {"rend_total_pct": 10.0, "caida_max_pct": 5.0,
                                                              "calmar": 0.8 if k == "R1" else 0.1}})
            for k in ("R0", "R1", "R2")}
    lentos = []
    monkeypatch.setattr(ejecutar_v2, "mercado_diario", lambda reg: SimpleNamespace(velas={"BTCUSDT": 1, "ETHUSDT": 2}))
    monkeypatch.setattr(V2, "referencias", lambda md: refs)
    monkeypatch.setattr(V2, "evaluar_m0", lambda md, r: {"m0": True, "refs": sorted(r)})

    def evaluar_lento(md, clave, calmar_r1, avisar):
        lentos.append((clave, calmar_r1))
        return SimpleNamespace(pasa=clave == "M1", mc={"caida_p95": 9.0, "_caidas": [1]},
                               mc_bloques={"caida_p95": 12.0, "_x": 0})

    monkeypatch.setattr(V2, "evaluar_lento", evaluar_lento)
    return lentos


def test_ejecutar_m0_solo_guarda_m0(reg, salida_v2, monkeypatch):
    _fakes_v2(monkeypatch)
    avisos = []
    ejecutar_v2.ejecutar(reg, ["m0"], avisar=avisos.append)
    assert sorted(p.name for p in salida_v2.iterdir()) == ["M0.pkl"]
    assert ejecutar_v2.cargar_resultado("M0") == {"m0": True, "refs": ["R0", "R1", "R2"]}
    assert avisos[0] == "Cargando velas diarias…" and avisos[1].startswith("  2 monedas en ")
    assert avisos[-1] == "M0 (R1 como candidata)…"


def test_ejecutar_referencias_y_motores(reg, salida_v2, monkeypatch):
    lentos = _fakes_v2(monkeypatch)
    avisos = []
    ejecutar_v2.ejecutar(reg, ["referencias", "motores"], avisar=avisos.append)
    assert sorted(p.name for p in salida_v2.iterdir()) == ["M0.pkl", "M1.pkl", "M2.pkl", "referencias.pkl"]
    assert lentos == [("M1", 0.8), ("M2", 0.8)]                  # todos contra el Calmar de R1
    m1 = ejecutar_v2.cargar_resultado("M1")
    assert m1["pasa"] is True and m1["mc"] == {"caida_p95": 9.0} and m1["mc_bloques"] == {"caida_p95": 12.0}
    assert set(ejecutar_v2.cargar_resultado("referencias")["R1"]) == {"nombre", "metricas", "por_anio", "curvas",
                                                                      "invertido"}
    assert "  R0: fuera de muestra +10.0 %, caída 5.0 %, Calmar 0.10" in avisos
    assert any(x.startswith("  M1: PASA en ") for x in avisos) and any(x.startswith("  M2: NO PASA en ") for x in avisos)


def test_ejecutar_estela_guarda_su_resultado(reg, salida_v2, monkeypatch):
    from sobreviviente import estela as ES
    monkeypatch.setattr(ES, "ejecutar", lambda reg, cli, avisar: {"cli": cli, "hay_efecto": False})
    ejecutar_v2.ejecutar(reg, ["estela"], avisar=lambda *_: None)
    assert ejecutar_v2.cargar_resultado("estela") == {"cli": "cliente-falso", "hay_efecto": False}


# ---------------------------------------------------------------- informe_v2.py

def _motor_v2(nombre, pasa, completo):
    x = {"nombre": nombre, "pasa": pasa, "combos": 4, "combinaciones": ["sma 100", "sma 200"],
         "params_finales": {"sma": 200},
         "compuertas": {"ops": (True, "Al menos 60 operaciones"), "calmar": (pasa, "Calmar mayor que el de R1")},
         "oos_r": {"operaciones": 80, "pct_ganadoras": 38.0, "ganancia_prom_r": 2.4, "perdida_prom_r": -1.0,
                   "expectativa_r": 0.091 if pasa else -0.03, "factor_ganancia": 1.35, "racha_perdedora_max": 8,
                   "ventanas_positivas_pct": 50.0},
         "oos_curva": {"calmar": 0.9, "rend_total_pct": 30.0, "caida_max_pct": 12.0, "tiempo_invertido_pct": 61.0},
         "mc": {"caida_p95": 15.0}, "mc_bloques": {"caida_p95": 19.0, "racha_p95": 11, "rend_p5": -5.0, "rend_p95": 60.0},
         "prueba_final": {"operaciones": 9, "expectativa_r": 0.02, "rend_total_pct": 1.5},
         "concentracion_top5": 85.0, "calmar_r1_oos": 0.8,
         "carteras": {"A": {"rend_total_pct": 30.0, "caida_max_pct": 12.0, "calmar": 0.9, "dias_tope_diario": 2,
                            "veces_freno": 0}},
         "ventanas": [{"prueba": "2023-01 a 2023-03", "params": {"sma": 200}, "n_prueba": 6, "r_prueba": 1.5},
                      {"prueba": "2023-04 a 2023-06", "params": {"sma": 100}}],
         "azar": {}, "bootstrap": {}, "robustez": {}, "real": {}}
    if completo:
        x.update({"azar": {"percentil": 93.0, "real": 0.012, "azar_p50": 0.003, "azar_p90": 0.009},
                  "bootstrap": {"calmar_p5": 0.2, "calmar_p95": 1.6, "caida_p5": 6.0, "caida_p95": 21.0},
                  "robustez": {"eje": "sma", "minimo": 0.04,
                               "tabla": {160: {"valor": 160, "expectativa_r": 0.04, "operaciones": 90},
                                         240: {"valor": 240, "expectativa_r": 0.1, "operaciones": 70}}},
                  "real": {"A": {"candidatos": 80, "ejecutadas": 10, "saltadas_capital": 70,
                                 "capital_necesario_mediana": 150.0},
                           "B": {"candidatos": 80, "ejecutadas": 40, "saltadas_capital": 40}},
                  "cupo": {"fuera_por_cupo": 12, "senales": 92, "rend_por_fuerza_pct": 30.0,
                           "rend_azar_p50_pct": 22.0, "percentil_fuerza": 80.0},
                  "comisiones": {0.1: {"expectativa_r": 0.09, "rend_total_pct": 30.0},
                                 0.2: {"expectativa_r": 0.05, "rend_total_pct": 18.0}},
                  "por_anio": {2023: {"operaciones": 30, "expectativa_r": 0.12}}})
    return x


def _datos_v2():
    per = lambda r: {"rend_total_pct": r, "rend_anual_pct": r / 4, "caida_max_pct": 40.0, "calmar": 0.5,
                     "tiempo_invertido_pct": 60.0, "operaciones": 12}
    refs = {k: {"nombre": f"Referencia {k}", "metricas": {p: per(v) for p in ("todo", "fuera_de_muestra", "prueba_final")},
                "por_anio": {2022: -60.0 + v, 2023: v}} for k, v in (("R0", 150.0), ("R1", 90.0), ("R2", -20.0))}
    refs["R1"]["metricas"]["fuera_de_muestra"]["calmar"] = 0.8
    m0 = {"pasa": False, "metricas": {"fuera_de_muestra": {"operaciones": 14, "calmar": 0.8},
                                      "prueba_final": {"rend_total_pct": -2.0}},
          "azar": {"percentil": 70.0, "real": 0.9, "entradas": 14, "tiempo_invertido_pct": 60.0, "azar_p50": 0.5,
                   "azar_p90": 1.1},
          "bootstrap": {"caida_p95": 45.0, "calmar_p5": 0.1, "calmar_p95": 1.4, "caida_p50": 30.0},
          "compuertas": {"azar": (False, "Le gana al 90 % de los calendarios al azar")},
          "robustez": {160: {"sma": 160, "rend_total_pct": 80.0, "caida_max_pct": 35.0, "calmar": 0.7}},
          "comisiones": {0.1: {"calmar": 0.8}, 0.2: {"calmar": 0.7}},
          "topes": {"A": {"dias_tope_diario": 3, "veces_freno": 1}},
          "carteras": {"A": {"rend_total_pct": 0.0, "caida_max_pct": 0.0, "calmar": float("nan"),
                             "bootstrap_caida_p95": None, "operaciones": 0, "real_ejecutadas": 0,
                             "real_saltadas_capital": 14}}}
    au = {"periodo": (pd.Timestamp("2023-01-01"), pd.Timestamp("2026-04-30")), "params": {"n": 20},
          "A1": {"suelto": {"caida_p50": 10.0, "caida_p95": 18.0, "racha_p95": 12, "prob_caida_alerta": 9.0},
                 "bloques": {"caida_p50": 13.0, "caida_p95": 25.0, "racha_p95": 15, "prob_caida_alerta": 20.0}},
          "A2": {"caida_cerradas_pct": 12.0, "caida_mercado_pct": 16.0, "rend_cerradas_pct": 20.0,
                 "rend_mercado_pct": 17.0,
                 "topes_cerradas": {"dias_tope_diario": 1, "semanas_tope_semanal": 0, "veces_freno": 0},
                 "topes_mercado": {"dias_tope_diario": 4, "semanas_tope_semanal": 1, "veces_freno": 1}},
          "A3": {"a": {"nombre": "la de la v1", "e1": {"operaciones": 100, "expectativa_r": 0.05, "pct_ganadoras": 40.0,
                                                       "ganancia_prom_r": 2.0},
                       "azar": {"expectativa_r": -0.01, "pct_ganadoras": 35.0}}},
          "A4": {"todas": {"operaciones": 100, "expectativa_r": 0.05, "factor_ganancia": 1.2, "rend_cartera_pct": 15.0},
                 "grandes": {"operaciones": 30, "expectativa_r": 0.15, "factor_ganancia": 1.6},
                 "chicas": {"operaciones": 70, "expectativa_r": -0.01, "factor_ganancia": 0.98}},
          "A7": {"concentracion_top5_pct": 140.0, "suma_r": 12.5},
          "A8": {"senales": 300, "fuera_por_cupo": 40, "rend_por_fuerza_pct": 15.0, "rend_azar_p50_pct": 14.0,
                 "n": 200, "percentil_fuerza": 60.0},
          "A9": {0.1: {"operaciones": 100, "expectativa_r": 0.05, "rend_cartera_pct": 15.0}}}
    es = {"ruta_existe": True, "btc_desde": "2021-12-01",
          "verificacion_api": {"ok": True, "fecha": "2026-11-09",
                               "columnas": {"top_largo": {"api": "topLongShortPositionRatio", "error_mediano": 0.0001}}},
          "desde_por_simbolo": {"ETHUSDT": "2022-01-01", "BTCUSDT": "2021-12-01"}, "sin_perpetuo": ["XYZUSDT"],
          "estudio": {"panel_filas": 9000, "n_pruebas": 2,
                      "pruebas": [{"prueba": "H1 top", "h": 3, "eventos": 50, "signo_esperado": "+", "efecto_pct": -0.4,
                                   "ic95": (-0.9, 0.1), "anios_mismo_signo_pct": 20.0, "anios_con_datos": 5, "pasa": False},
                                  {"prueba": "H2 masa", "h": 7, "eventos": 60, "signo_esperado": "−", "efecto_pct": -1.2,
                                   "ic95": (-2.0, -0.3), "anios_mismo_signo_pct": 80.0, "anios_con_datos": 5,
                                   "pasa": True}]},
          "hay_efecto": True}
    m1, m2 = _motor_v2("Tendencia lenta", True, True), _motor_v2("Rotación lenta", False, False)
    vetos = {}
    for k, x in (("M1", m1), ("M2", m2)):
        v = _motor_v2(x["nombre"], False, k == "M1")
        v.update({"candidatos_sin_veto": 92, "candidatos_con_veto": 80})
        vetos[f"{k}_veto"] = v
    return {"referencias": refs, "M0": m0, "M1": m1, "M2": m2, "auditoria": au, "estela": es, **vetos}


def test_informe_v2_formatos():
    assert informe_v2._p("x") == "—" and informe_v2._p(None) == "—" and informe_v2._p(float("nan")) == "—"
    assert informe_v2._p(float("inf")) == "∞" and informe_v2._p(float("-inf")) == "—"
    assert informe_v2._p("2.5", 2, True) == "+2.50" and informe_v2._ok(True) == "✅" and informe_v2._ok(False) == "❌"


@pytest.mark.parametrize("nombre,datos", [("VALIDACION_V2_vacio.md", {}), ("VALIDACION_V2_completo.md", None)])
def test_informe_v2_escribir_igual_a_referencia(reg, tmp_path, monkeypatch, fecha_fija, nombre, datos):
    datos = _datos_v2() if datos is None else datos
    monkeypatch.setattr(informe_v2, "cargar_resultado", datos.get)
    ruta = tmp_path / nombre
    informe_v2.escribir(reg, ruta)
    _igual_a_referencia(ruta, nombre)


def test_informe_v2_estela_sin_verificar_ni_efecto_y_concentracion_negativa(reg, tmp_path, monkeypatch, fecha_fija):
    datos = _datos_v2()
    datos["estela"].update({"verificacion_api": {"ok": False, "motivo": "sin conexión"}, "hay_efecto": False})
    datos["auditoria"]["A7"]["concentracion_top5_pct"] = float("nan")
    for k in ("M1_veto", "M2_veto"):
        datos.pop(k)
    monkeypatch.setattr(informe_v2, "cargar_resultado", datos.get)
    ruta = tmp_path / "v2.md"
    informe_v2.escribir(reg, ruta)
    texto = ruta.read_text(encoding="utf-8")
    assert "- Verificación contra la API: sin conexión" in texto
    assert "**Resultado: el posicionamiento de los top traders NO predijo nada de forma consistente.**" in texto
    assert "la suma de resultados es negativa, así que la concentración no aplica" in texto
    assert "### Paso 2" not in texto and "ESTELA: 2 pruebas (2 hipótesis × rejilla × 2 horizontes)." in texto
