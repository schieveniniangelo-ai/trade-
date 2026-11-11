"""Arreglo 73 (banco de filtros, fase 5): protección contra sobreajuste.

Con menos de N operaciones no hay veredicto, solo el aviso. Se reporta la variación entre ventanas y un
remuestreo sencillo con semilla fija. El banco no elige parámetros ni busca combinaciones. Sin red y sin llaves."""
import inspect

import numpy as np
import pandas as pd
import pytest

from sobreviviente import banco_filtros as BF
from sobreviviente import descartes as DS
from sobreviviente import validacion as V
from sobreviviente import validacion_v2 as V2

from test_arreglo69_banco_filtros_fase1 import _mercado_diario
from test_arreglo71_banco_filtros_fase3 import _dos_ventanas, _fila

PROBADOS = (DS.VOL_EXTREMA, DS.BTC_BAJISTA, DS.YA_HAY_POSICION, DS.CALOR_LLENO)


def _cfg(**cambios):
    base = dict(carteras=("A",), motores=("M1",), encendidos=("M1",), capital=1000.0, filtros=PROBADOS,
                min_operaciones=3, bootstrap_n=300, semilla=7)
    base.update(cambios)
    return BF.ConfigBanco(**base)


def _pool():
    """Cuatro operaciones normales; cuatro señales con BTC bajista que perdían; cuatro con volatilidad extrema que
    ganaban; y XUSDT abierta 100 días con tres señales repetidas encima (una gana, una pierde, una casi nada)."""
    filas = []
    for k, (mes, pnl) in enumerate([("01", 10.0), ("02", -5.0), ("04", 10.0), ("05", -5.0)]):
        filas.append(_fila(f"P{k}USDT", f"2023-{mes}-10", pnl=pnl))
        filas.append(_fila(f"Q{k}USDT", f"2023-{mes}-20", pnl=[-5.0, -4.0, -6.0, -3.0][k], regimen_btc="BAJISTA"))
        filas.append(_fila(f"V{k}USDT", f"2023-{mes}-25", pnl=[10.0, 7.5, 15.0, 5.0][k], vol_moneda=99.9))
    filas.append(_fila("XUSDT", "2023-03-01", pnl=10.0, dias=100))
    filas += [_fila("XUSDT", "2023-03-10", pnl=10.0, dias=3), _fila("XUSDT", "2023-03-20", pnl=-10.0, dias=4),
              _fila("XUSDT", "2023-04-01", pnl=0.5, dias=5)]
    return BF.Pool(base=pd.DataFrame(filas))


@pytest.fixture
def wf(reg):
    return BF.walk_forward(_dos_ventanas(reg), _cfg(), _pool(), {})


# ---------------- Por debajo de N: solo el aviso ----------------

def test_por_debajo_de_n_no_hay_veredicto_solo_el_aviso(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), _cfg(min_operaciones=20), _pool(), {})      # N = 20, el de por defecto
    assert BF.ConfigBanco().min_operaciones == 20
    for filtro in (DS.VOL_EXTREMA, DS.BTC_BAJISTA, DS.YA_HAY_POSICION):
        v = BF.veredicto(wf, "A", filtro)
        assert v["estado"] == BF.SIN_DATOS and v["texto"].startswith("Sin datos suficientes: ")
        assert "(se piden al menos 20)" in v["texto"] and "No se opina sobre este filtro." in v["texto"]
        assert v["intervalo"] is None and v["variacion"] is None                      # ni rango ni comparación
        assert v["senales_afectadas"] > 0 and v["min_operaciones"] == 20
    t = BF.tabla_veredictos(wf)
    con_senales = t[t["senales_afectadas"] > 0]
    assert set(con_senales["estado"]) == {BF.SIN_DATOS}
    assert con_senales[["suelta_r_p5", "suelta_r_p95", "mejor_en", "peor_en"]].isna().all().all()
    base = BF.linea_base(wf, "A")
    assert base["intervalo"] is None and base["aviso"].startswith("Sin datos suficientes: 5 operaciones")


def test_el_aviso_dice_que_falta(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), _cfg(min_operaciones=6), _pool(), {})
    v = BF.veredicto(wf, "A", DS.BTC_BAJISTA)                                           # base 5, experimento 9, 4 episodios
    assert v["estado"] == BF.SIN_DATOS
    assert "la línea base tiene 5 operaciones" in v["texto"] and "el experimento tiene" not in v["texto"]
    assert "el filtro bloqueó 4 señales que son 4 episodios distintos con simulación" in v["texto"]


def test_senales_repetidas_del_mismo_movimiento_cuentan_como_un_episodio(reg):
    filas = [_fila(f"P{k}USDT", f"2023-0{k + 1}-10") for k in range(4)]
    filas.append(_fila("XUSDT", "2023-03-01", dias=100))
    sale = pd.Timestamp("2023-06-09", tz="UTC")
    filas += [_fila("XUSDT", f"2023-03-{d:02d}", t_salida=sale) for d in range(10, 16)]   # la misma señal, 6 días seguidos
    wf = BF.walk_forward(_dos_ventanas(reg), _cfg(), BF.Pool(base=pd.DataFrame(filas)), {})
    b = BF.senales_bloqueadas(wf, "A", DS.YA_HAY_POSICION)
    epi = BF.episodios(b)
    assert len(b) == 6 and len(epi) == 1 and epi["senales"].iloc[0] == 6 and epi["r"].iloc[0] == 2.0
    v = BF.veredicto(wf, "A", DS.YA_HAY_POSICION)
    assert v["estado"] == BF.SIN_DATOS and (v["senales_afectadas"], v["episodios"]) == (6, 1)
    assert "6 señales que son 1 episodios distintos" in v["texto"]


# ---------------- Con muestra suficiente: descripción, variación entre ventanas e intervalo ----------------

def test_veredictos_con_muestra_suficiente(wf):
    perdian = BF.veredicto(wf, "A", DS.BTC_BAJISTA)
    ganaban = BF.veredicto(wf, "A", DS.VOL_EXTREMA)
    mixto = BF.veredicto(wf, "A", DS.YA_HAY_POSICION)
    nada = BF.veredicto(wf, "A", DS.CALOR_LLENO)
    assert (perdian["estado"], ganaban["estado"], mixto["estado"], nada["estado"]) == \
        (BF.PERDIAN, BF.GANABAN, BF.NO_SE_DISTINGUE, BF.SIN_EFECTO)
    assert perdian["intervalo"]["p95"] < 0 < ganaban["intervalo"]["p5"]
    assert mixto["intervalo"]["p5"] < 0 < mixto["intervalo"]["p95"]
    assert (perdian["operaciones_base"], perdian["operaciones_experimento"], perdian["episodios"]) == (5, 9, 4)
    assert perdian["intervalo"]["muestras"] == 4 and perdian["intervalo"]["repeticiones"] == 300
    for v in (perdian, ganaban, mixto):
        assert "no una promesa ni una recomendación" in v["texto"] and "DECISIÓN DE ÁNGELO" in v["texto"]
        assert "cada una por su cuenta" in v["texto"] or "No se distingue" in v["texto"]
    assert nada["intervalo"] is None and "sale lo mismo que la línea base" in nada["texto"]


def test_variacion_entre_ventanas_no_solo_el_promedio(wf):
    var = BF.variacion_entre_ventanas(wf, "A", DS.BTC_BAJISTA)
    assert [x["ventana"] for x in var["por_ventana"]] == ["2023-01", "2023-04"]
    assert (var["ventanas"], var["mejor_en"], var["peor_en"], var["igual_en"]) == (2, 0, 2, 0)   # perdió en las dos
    difs = [x["dif_ganancia_usdt"] for x in var["por_ventana"]]
    assert var["dif_usdt_min"] == pytest.approx(min(difs)) and var["dif_usdt_max"] == pytest.approx(max(difs))
    assert var["dif_usdt_mediana"] == pytest.approx(np.median(difs)) and var["dif_usdt_desviacion"] > 0
    assert all(x["dif_operaciones"] == 2 for x in var["por_ventana"])
    al_reves = BF.variacion_entre_ventanas(wf, "A", DS.VOL_EXTREMA)
    assert (al_reves["mejor_en"], al_reves["peor_en"]) == (2, 0)
    igual = BF.variacion_entre_ventanas(wf, "A", DS.CALOR_LLENO)
    assert (igual["mejor_en"], igual["peor_en"], igual["igual_en"]) == (0, 0, 2) and igual["dif_usdt_desviacion"] == 0.0
    v = BF.veredicto(wf, "A", DS.BTC_BAJISTA)
    assert "mejor en 0 de 2 ventanas, peor en 2 e igual en 0" in v["texto"]


def test_la_tabla_de_veredictos_no_es_un_ranking(wf):
    t = BF.tabla_veredictos(wf)
    assert list(t["filtro"]) == [c for c in DS.CATALOGO if c in PROBADOS]               # orden del catálogo, no por resultado
    assert not any(palabra in col for col in t.columns for palabra in ("ranking", "lugar", "puesto", "mejor_filtro"))
    assert list(t["estado"]) == [BF.GANABAN, BF.PERDIAN, BF.NO_SE_DISTINGUE, BF.SIN_EFECTO]
    fila = t[t["filtro"] == DS.BTC_BAJISTA].iloc[0]
    assert fila["suelta_r_p95"] < 0 and fila["peor_en"] == 2 and fila["episodios"] == 4


def test_linea_base_con_muestra_suficiente(wf):
    base = BF.linea_base(wf, "A")
    assert base["operaciones"] == 5 and base["aviso"] == "" and base["intervalo"]["muestras"] == 5
    assert base["intervalo"]["p5"] <= base["expectativa_r"] <= base["intervalo"]["p95"]
    assert base["detenciones"] == 0 and base["pausas"] == 0


def test_notas_de_lo_que_el_backtest_no_puede_medir(reg):
    cfg = _cfg(filtros=(DS.VETO_NOTICIAS, DS.EVENTO_FUERTE, DS.FRENO_TOTAL, DS.CONCILIACION, DS.DATOS_NO_CONFIABLES))
    wf = BF.walk_forward(_dos_ventanas(reg), cfg, _pool(), {})
    for filtro in cfg.filtros:
        v = BF.veredicto(wf, "A", filtro)
        assert v["estado"] == BF.SIN_EFECTO and v["nota"] == BF.NOTAS_BACKTEST[filtro] and v["nota"] in v["texto"]


# ---------------- El remuestreo es reproducible ----------------

def test_el_remuestreo_con_la_misma_semilla_da_lo_mismo():
    r = [2.0, -1.0, 0.5, -1.0, 3.0, -0.8, 1.2]
    a, b = BF.intervalo_expectativa(r, 500, 7), BF.intervalo_expectativa(r, 500, 7)
    otra = BF.intervalo_expectativa(r, 500, 8)
    assert a == b and a != otra
    assert a["p5"] < np.mean(r) < a["p95"] and (a["repeticiones"], a["muestras"]) == (500, 7)
    assert abs(a["p50"] - otra["p50"]) < 0.3                                             # otra semilla: parecido, no igual
    assert BF.intervalo_expectativa([], 500, 7) is None and BF.intervalo_expectativa([1.0], 0, 7) is None
    assert BF.intervalo_expectativa([1.0, float("nan"), 3.0], 50, 1)["muestras"] == 2   # lo que no tiene valor no cuenta


def test_dos_corridas_completas_con_la_misma_semilla_dan_el_mismo_veredicto(reg):
    r = _dos_ventanas(reg)
    uno = BF.tabla_veredictos(BF.walk_forward(r, _cfg(), _pool(), {}))
    dos = BF.tabla_veredictos(BF.walk_forward(r, _cfg(), _pool(), {}))
    pd.testing.assert_frame_equal(uno, dos)
    otra = BF.tabla_veredictos(BF.walk_forward(r, _cfg(semilla=8), _pool(), {}))
    assert list(otra["estado"]) == list(uno["estado"])                                  # la conclusión no depende de la semilla
    assert otra["suelta_r_p50"].notna().sum() == uno["suelta_r_p50"].notna().sum() == 3
    assert BF.semilla_del_banco(reg, BF.ConfigBanco()) == int(reg.get("validacion.semilla"))
    assert BF.semilla_del_banco(reg, _cfg()) == 7


# ---------------- Nada de optimizar ----------------

def test_el_banco_no_elige_parametros_ni_busca_combinaciones(reg, monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("el banco no debe elegir parámetros ni llamar a la validación oficial")

    for modulo, nombre in ((V, "evaluar"), (V, "combinaciones"), (V, "robustez"), (V, "pool_azar"),
                           (V, "filtro_reglas_baratas"), (V2, "evaluar_lento"), (V2, "robustez_lento")):
        monkeypatch.setattr(modulo, nombre, prohibido)
    md = _mercado_diario(_dos_ventanas(reg), grandes_n=3)
    cfg = BF.ConfigBanco(carteras=("A",), motores=("M0", "M1"), encendidos=("M0", "M1"), min_operaciones=3,
                         bootstrap_n=100, semilla=1)
    pool = BF.generar_pool(md, cfg, "2022-01-01", "2023-12-31")
    wf = BF.walk_forward(md.reg, cfg, pool, md.filtros, md.cierres())
    assert not BF.tabla_metricas(wf).empty and not BF.tabla_veredictos(wf).empty
    assert BF.linea_base(wf, "A")["operaciones"] > 0
    # Los parámetros son los del reglamento, tal cual: una sola corrida por motor, sin rejilla
    fuente = inspect.getsource(BF)
    for palabra in ("rejilla", "combinaciones(", ".evaluar(", "evaluar_lento", "elegir("):
        assert palabra not in fuente, palabra
    assert md.reg.estrategias["M1"]["parametros"] == reg.estrategias["M1"]["parametros"]
