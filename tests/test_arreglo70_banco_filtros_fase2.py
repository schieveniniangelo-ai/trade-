"""Arreglo 70 (banco de filtros, fase 2): motor de ablación, SOLO en el backtest y apagado por defecto.

Un experimento cambia UN filtro contra la línea base (el reglamento sin tocar). La ronda de papel no lee nada de
esto. Todo con datos falsos: sin red y sin llaves."""
import copy
import hashlib
import inspect
from pathlib import Path

import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente import banco_filtros as BF
from sobreviviente import cli_ronda as CR
from sobreviviente import descartes as DS
from sobreviviente import diario as DI
from sobreviviente import papel as P
from sobreviviente import riesgo as R
from sobreviviente.exchange import Filtros

from conftest import hacer_cand, hacer_estado
from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo69_banco_filtros_fase1 import CASOS, _mercado_diario
from test_papel import _datos_dia

RAIZ = Path(__file__).resolve().parent.parent
H = pd.Timedelta(hours=4)
T0 = pd.Timestamp("2024-03-04 16:00", tz="UTC")
FILTROS = {s: Filtros(s, 0.01, 0.001, 0.001, 5) for s in ("AUSDT", "BUSDT", "CUSDT", "DUSDT", "EUSDT", "FUSDT")}
CFG = BF.ConfigBanco(carteras=("A",), motores=("M1",), encendidos=("M1",), capital=1000.0)


def _fila(simbolo, horas, pnl=10.0, dura=2, **cambios):
    t = T0 + horas * H
    base = dict(estrategia="M1", mercado="SPOT", lado="LARGO", cubeta="normales", precio_plan=100.0, stop=95.0,
                meta=None, fuerza=1.0, comision_pct=0.1, desliz_pct=0.0, regimen_btc="ALCISTA", vol_btc=50.0,
                vol_moneda=50.0, pnl_unidad=pnl, r=pnl / 5.0, comision_unidad=0.2, stops_t=[], stops=[],
                entrada=100.0, simbolo=simbolo, t_senal=t - pd.Timedelta(days=1), t_decision=t, t_entrada=t,
                t_salida=t + dura * H)
    base.update(cambios)
    return base


def _pool():
    """A entra; A otra vez (ya hay posición); B entra; C con BTC bajista; D con volatilidad extrema."""
    base = pd.DataFrame([
        _fila("AUSDT", 0), _fila("AUSDT", 1), _fila("BUSDT", 1, pnl=-5.0),
        _fila("CUSDT", 1, regimen_btc="BAJISTA"), _fila("DUSDT", 4, vol_moneda=99.9),
    ])
    fuera = _fila("EUSDT", 5)
    previos = [DS.registro(DS.FUERA_DE_UNIVERSO, "fuera", "EUSDT", fuera["t_decision"], "", "M1", origen="generacion",
                           r=fuera["r"], pnl_unidad=fuera["pnl_unidad"], candidato=fuera),
               DS.registro(DS.STOP_O_SIMULACION, "sin stop", "FUSDT", T0, "", "M1", origen="generacion")]
    return BF.Pool(base=base, previos=previos, veto_estela={"BUSDT": {base["t_senal"].iloc[2]}})


def _ops(corrida):
    return 0 if corrida.resultado.operaciones.empty else len(corrida.resultado.operaciones)


# ---------------- El interruptor en el motor de riesgo ----------------

def _decidir(reg, filtros, ahora, caso, apagar=()):
    from datetime import timedelta
    args_estado = dict(caso.get("estado", {}))
    capital = args_estado.pop("capital", 1000.0)
    if caso.get("pausa"):
        args_estado["pausa_hasta"] = ahora + timedelta(hours=1)
    if caso.get("pausa_estrategia"):
        args_estado["pausa_estrategia_hasta"] = {"E1": ahora + timedelta(hours=2)}
    if caso.get("apagada"):
        reg.datos["estrategias"]["E1"]["estado"] = "APAGADA"
    kw = dict(caso.get("kw", {}))
    if caso.get("evento"):
        kw["eventos"] = [{"nombre": "Fed", "importancia": "ALTA", "fecha_hora": (ahora + timedelta(minutes=20)).isoformat()}]
    return R.evaluar_candidato(reg, hacer_estado(capital, **args_estado), hacer_cand(**caso.get("cand", {})), filtros,
                               ahora, apagar_en_banco=apagar, **kw)


@pytest.mark.parametrize("codigo, caso", CASOS, ids=[f"{i}-{c}" for i, (c, _) in enumerate(CASOS)])
def test_apagar_un_filtro_en_el_motor_de_riesgo(reg, filtros, ahora, codigo, caso):
    base = _decidir(copy.deepcopy(reg), filtros, ahora, caso)
    exp = _decidir(copy.deepcopy(reg), filtros, ahora, caso, apagar={codigo})
    if codigo == DS.APROBADA:
        assert exp.aprobada and exp.cantidad == base.cantidad
    elif codigo in DS.APAGABLES_RIESGO:
        if caso.get("kw", {}).get("regimen_btc") == "BAJISTA" and codigo == DS.VOL_EXTREMA:
            assert not exp.aprobada and exp.codigo == DS.BTC_BAJISTA     # se apagó UNO: el otro bloqueo sigue mandando
        else:
            assert exp.aprobada and exp.codigo == DS.APROBADA, exp.razon
        assert exp.solo_papel and "EXPERIMENTO_BANCO" in exp.verificaciones
    else:
        # Límites de verdad (stop inválido, mínimo de Binance, sin dinero libre): no se apagan ni pidiéndolo
        assert not exp.aprobada and exp.codigo == codigo and exp.razon == base.razon
        assert "EXPERIMENTO_BANCO" not in exp.verificaciones


def test_por_defecto_no_hay_nada_apagado(reg, filtros, ahora):
    for _, caso in CASOS:
        a = _decidir(copy.deepcopy(reg), filtros, ahora, caso)
        b = _decidir(copy.deepcopy(reg), filtros, ahora, caso, apagar=frozenset())
        assert (a.aprobada, a.codigo, a.razon, a.cantidad, a.solo_papel, a.verificaciones) == \
            (b.aprobada, b.codigo, b.razon, b.cantidad, b.solo_papel, b.verificaciones)
        assert "EXPERIMENTO_BANCO" not in a.verificaciones


def test_sin_el_bloqueo_de_volatilidad_extrema_el_tamano_va_reducido(reg, filtros, ahora):
    normal = R.evaluar_candidato(reg, hacer_estado(), hacer_cand(), filtros, ahora)
    exp = R.evaluar_candidato(reg, hacer_estado(), hacer_cand(), filtros, ahora, vol_moneda="EXTREMA",
                              apagar_en_banco={DS.VOL_EXTREMA})
    assert exp.aprobada and exp.factor == float(reg.riesgo["ajustes"]["vol_alta_factor"]) < 1.0
    assert exp.cantidad < normal.cantidad                           # EXTREMA cuenta como ALTA, no como normal


def test_codigos_desconocidos_o_no_apagables_se_ignoran(reg, filtros, ahora):
    d = R.evaluar_candidato(reg, hacer_estado(), hacer_cand(stop=105.0), filtros, ahora,
                            apagar_en_banco={DS.STOP_INVALIDO, DS.TAMANO_O_CAPITAL, DS.EXPOSICION_O_MARGEN, "INVENTADO"})
    assert not d.aprobada and d.codigo == DS.STOP_INVALIDO
    assert "EXPERIMENTO_BANCO" not in d.verificaciones              # no se apagó nada: no es un experimento
    assert {DS.STOP_INVALIDO, DS.TAMANO_O_CAPITAL, DS.EXPOSICION_O_MARGEN}.isdisjoint(DS.APAGABLES_RIESGO)


# ---------------- La línea base y los experimentos ----------------

def test_la_linea_base_es_el_reglamento_sin_tocar(reg):
    pool = _pool()
    base = BF.correr(reg, CFG, pool, BF.Experimento(BF.BASE), "A", FILTROS)
    directo = B.cartera(reg.para_cartera("A"), pool.base, 1000.0, FILTROS, ["M1"])
    pd.testing.assert_frame_equal(base.resultado.decisiones, directo.decisiones)
    pd.testing.assert_frame_equal(base.resultado.operaciones, directo.operaciones)
    pd.testing.assert_series_equal(base.resultado.curva, directo.curva)
    assert [r["codigo"] for r in base.registro] == [DS.APROBADA, DS.YA_HAY_POSICION, DS.APROBADA, DS.BTC_BAJISTA,
                                                    DS.VOL_EXTREMA]
    assert all(r["cartera"] == "A" for r in base.registro)


def test_un_experimento_por_filtro_y_la_base_primero(reg):
    pool = _pool()
    exps = BF.experimentos(reg, CFG, pool)
    assert exps[0] == BF.Experimento(BF.BASE) and len({e.nombre for e in exps}) == len(exps)
    por = {e.nombre: e for e in exps}
    assert set(por) - {BF.BASE} == set(DS.APAGABLES_RIESGO) | set(BF.APAGABLES_GENERACION) | {DS.VETO_ESTELA}
    assert por[DS.VETO_ESTELA].accion == "encender"                 # hoy el veto de ESTELA está apagado en el reglamento
    assert all(e.accion == "apagar" for n, e in por.items() if n not in (BF.BASE, DS.VETO_ESTELA))
    assert reg.estrategias["M3"]["veto_activo"] is False
    al_reves = reg.copia_con({"estrategias.M3.veto_activo": True})
    assert {e.nombre: e for e in BF.experimentos(al_reves, CFG, pool)}[DS.VETO_ESTELA].accion == "apagar"
    # Sin datos de ESTELA no hay experimento de ESTELA; con `filtros` solo se corren los pedidos
    assert DS.VETO_ESTELA not in {e.nombre for e in BF.experimentos(reg, CFG, BF.Pool(base=pool.base))}
    solo = BF.ConfigBanco(carteras=("A",), motores=("M1",), encendidos=("M1",), filtros=(DS.CALOR_LLENO,))
    assert [e.nombre for e in BF.experimentos(reg, solo, pool)] == [BF.BASE, DS.CALOR_LLENO]
    # Todo código del catálogo o se prueba, o tiene escrita la razón por la que no
    assert set(DS.CATALOGO) - {DS.APROBADA} == (set(por) - {BF.BASE}) | set(BF.NO_SE_PRUEBAN)


def test_apagar_un_filtro_aumenta_o_deja_igual_las_operaciones(reg):
    pool = _pool()
    corridas = BF.ablacion(reg, CFG, pool, FILTROS)["A"]
    base = corridas[BF.BASE]
    assert _ops(base) == 2
    for nombre, c in corridas.items():
        if c.experimento.accion == "apagar":
            assert _ops(c) >= _ops(base), nombre
    assert _ops(corridas[DS.YA_HAY_POSICION]) == 3                  # la segunda señal de AUSDT ahora sí entra
    assert _ops(corridas[DS.BTC_BAJISTA]) == 3                      # entra CUSDT
    assert _ops(corridas[DS.VOL_EXTREMA]) == 3                      # entra DUSDT (con tamaño reducido)
    assert _ops(corridas[DS.FUERA_DE_UNIVERSO]) == 3                # entra EUSDT, que estaba fuera del universo
    assert "EUSDT" in set(corridas[DS.FUERA_DE_UNIVERSO].resultado.operaciones["simbolo"])
    dusdt = corridas[DS.VOL_EXTREMA].resultado.operaciones.set_index("simbolo").loc["DUSDT"]
    ausdt = base.resultado.operaciones.set_index("simbolo").loc["AUSDT"]
    assert dusdt["riesgo_usdt"] < ausdt["riesgo_usdt"]


def test_apagar_un_filtro_que_no_descarto_nada_deja_todo_igual(reg):
    pool = _pool()
    corridas = BF.ablacion(reg, CFG, pool, FILTROS)["A"]
    base = corridas[BF.BASE]
    usados = {r["codigo"] for r in base.registro}
    sin_efecto = [n for n, c in corridas.items() if c.experimento.accion == "apagar" and n not in usados
                  and n not in BF.APAGABLES_GENERACION]
    assert {DS.COSTOS, DS.CALOR_LLENO, DS.MAX_POSICIONES, DS.PAUSA_TOPE, DS.ESTRATEGIA_APAGADA} <= set(sin_efecto)
    for n in sin_efecto:
        pd.testing.assert_frame_equal(corridas[n].resultado.operaciones, base.resultado.operaciones)
        pd.testing.assert_series_equal(corridas[n].resultado.curva, base.resultado.curva)
        pd.testing.assert_frame_equal(corridas[n].resultado.decisiones, base.resultado.decisiones)


def test_encender_el_veto_de_estela_quita_solo_sus_senales(reg):
    pool = _pool()
    corridas = BF.ablacion(reg, CFG, pool, FILTROS)["A"]
    base, estela = corridas[BF.BASE], corridas[DS.VETO_ESTELA]
    assert len(estela.candidatos) == len(base.candidatos) - 1 and "BUSDT" not in set(estela.candidatos["simbolo"])
    assert _ops(estela) == _ops(base) - 1
    assert list(BF.marca_estela(pool.base, pool.veto_estela)) == [False, False, True, False, False]
    m0 = pool.base.assign(estrategia="M0")                           # el veto no aplica a M0
    assert not BF.marca_estela(m0, pool.veto_estela).any()


def test_motor_apagado_en_el_reglamento_y_el_experimento_que_lo_enciende(reg):
    r = reg.copia_con({})
    r.datos["estrategias"]["M1"]["estado"] = "APAGADA"              # como está hoy M1 en el reglamento de verdad
    cfg = BF.ConfigBanco(carteras=("A",), motores=("M1",), capital=1000.0)     # encendidos = los del reglamento
    assert BF.motores_encendidos(r, cfg) == () and BF.es_linea_base_vigente(r, cfg)
    corridas = BF.ablacion(r, cfg, _pool(), FILTROS)["A"]
    assert _ops(corridas[BF.BASE]) == 0
    assert {x["codigo"] for x in corridas[BF.BASE].registro} == {DS.ESTRATEGIA_APAGADA}
    assert _ops(corridas[DS.ESTRATEGIA_APAGADA]) == 2               # con ese filtro apagado operan igual que la base de arriba
    estudio = BF.ConfigBanco(carteras=("A",), motores=("M1",), encendidos=("M1",), capital=1000.0)
    assert BF.motores_encendidos(r, estudio) == ("M1",) and not BF.es_linea_base_vigente(r, estudio)


def test_el_banco_no_cambia_el_reglamento(reg):
    antes_archivo = hashlib.sha256((RAIZ / "reglamento.yaml").read_bytes()).hexdigest()
    antes = copy.deepcopy(reg.datos)
    BF.ablacion(reg, CFG, _pool(), FILTROS)
    assert reg.datos == antes
    assert hashlib.sha256((RAIZ / "reglamento.yaml").read_bytes()).hexdigest() == antes_archivo
    assert BF.capital_del_banco(reg, BF.ConfigBanco()) == float(reg.get("backtest.capital_ventaja"))


# ---------------- Señales de verdad (velas falsas): parámetros del reglamento, sin buscar nada ----------------

def test_generar_pool_usa_los_parametros_del_reglamento(reg):
    md = _mercado_diario(reg)
    cfg = BF.ConfigBanco(motores=("M0", "M1"))
    pool = BF.generar_pool(md, cfg, "2022-06-01", "2024-02-01")
    esperado = pd.concat([DI.generar(md, k, md.reg.estrategias[k]["parametros"], "2022-06-01", "2024-02-01")
                          for k in ("M0", "M1")], ignore_index=True)
    assert len(pool.base) == len(esperado) > 0
    assert set(pool.base["estrategia"]) == {"M0", "M1"}
    assert pool.base["t_decision"].is_monotonic_increasing
    assert set(pool.base.loc[pool.base["estrategia"] == "M0", "simbolo"]) == {"BTCUSDT"}
    assert any(d["codigo"] == DS.FUERA_DE_UNIVERSO and "candidato" in d for d in pool.previos)
    assert md.veto is None
    # De punta a punta con la Cartera A: apagar el universo mete señales que antes no llegaban
    cfg_a = BF.ConfigBanco(carteras=("A",), motores=("M0", "M1"), encendidos=("M0", "M1"),
                           filtros=(DS.FUERA_DE_UNIVERSO, DS.MAX_POSICIONES))
    corridas = BF.ablacion(md.reg, cfg_a, pool, md.filtros, md.cierres())["A"]
    assert set(corridas) == {BF.BASE, DS.FUERA_DE_UNIVERSO, DS.MAX_POSICIONES}
    assert len(corridas[DS.FUERA_DE_UNIVERSO].candidatos) > len(corridas[BF.BASE].candidatos)
    assert _ops(corridas[BF.BASE]) > 0


# ---------------- La ronda viva no lee esa bandera ----------------

def test_la_ronda_de_papel_no_conoce_el_banco():
    for modulo in (P, CR):
        fuente = inspect.getsource(modulo)
        assert "apagar_en_banco" not in fuente and "banco_filtros" not in fuente, modulo.__name__
    assert inspect.signature(R.evaluar_candidato).parameters["apagar_en_banco"].default == ()
    assert inspect.signature(B.cartera).parameters["apagar_en_banco"].default == frozenset()


def test_la_ronda_de_papel_nunca_pasa_la_bandera(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    llamadas = []
    original = R.evaluar_candidato

    def espia(*args, **kwargs):
        llamadas.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(R, "evaluar_candidato", espia)
    c = P.ronda_cartera(r, "C", _datos_dia(r, _dia_marea_alta(r))[0], [], [])
    assert llamadas and all("apagar_en_banco" not in kw for kw in llamadas)
    assert [b["accion"] for b in c["boletos"]] == ["COMPRAR"]
    assert "EXPERIMENTO_BANCO" not in c["boletos"][0]["verificaciones"]
