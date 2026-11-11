"""Arreglo 80: un solo criterio de "stop válido" para el backtest y los motores diarios.

Antes, `diario.generar` descartaba una señal con el stop pegado al precio o del lado equivocado, pero el backtest
de la v1 la simulaba igual: con el stop en el precio, 1R vale cero y `simular_operacion` reportaba r = 0.0, un
resultado inventado (y el motor de riesgo después la rechazaba como STOP_INVALIDO). Ahora las dos rutas usan
`backtest.stop_valido` y la descartan antes de simular, con el mismo código. Velas falsas: sin red y sin llaves."""
import math

import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente import descartes as DS
from sobreviviente import diario as DI
from sobreviviente.estrategias import ESTRATEGIAS

from test_arreglo69_banco_filtros_fase1 import _mercado_diario, _mercado_v1
from test_estrategias_backtest import PARAMS_SUELTOS

NAN = math.nan


@pytest.mark.parametrize("lado,precio,stop,atr,esperado", [
    ("LARGO", 100.0, 95.0, 2.0, True),
    ("LARGO", 100.0, 100.0, 2.0, False),     # pegado al precio: 1R = 0
    ("LARGO", 100.0, 101.0, 2.0, False),     # del lado equivocado
    ("LARGO", 100.0, NAN, 2.0, False),
    ("LARGO", 100.0, 95.0, NAN, False),
    ("CORTO", 100.0, 105.0, 2.0, True),
    ("CORTO", 100.0, 100.0, 2.0, False),
    ("CORTO", 100.0, 95.0, 2.0, False),
])
def test_stop_valido(lado, precio, stop, atr, esperado):
    assert B.stop_valido(lado, precio, stop, atr) is esperado


def _pegar_stop(monkeypatch, clave, simbolo, desde):
    """La primera señal de `simbolo` desde `desde` sale con el stop EN el precio. Regresa la lista donde se anota."""
    original = ESTRATEGIAS[clave].senales
    pegadas = []
    desde = pd.Timestamp(desde)
    desde = desde.tz_localize("UTC") if desde.tzinfo is None else desde

    def senales(ctx, p):
        sen = original(ctx, p)
        if ctx.simbolo == simbolo:
            t = sen.index[sen["entrada"] & (sen.index >= desde)][0]
            sen.loc[t, "stop"] = sen.loc[t, "precio"]
            pegadas.append(t)
        return sen

    monkeypatch.setattr(ESTRATEGIAS[clave], "senales", senales)
    return pegadas


def _sin(df, simbolo, t_senal):
    return df[~((df["simbolo"] == simbolo) & (df["t_senal"] == t_senal))].reset_index(drop=True)


def test_backtest_descarta_el_stop_pegado_como_los_motores_diarios(reg, monkeypatch):
    B._CTX_CACHE.clear()
    try:
        m = _mercado_v1(reg)
        args = (m, "E3", PARAMS_SUELTOS["E3"], "2023-01-01", "2023-07-01")
        antes = B.generar_candidatos(*args, procesos=1)
        pegadas = _pegar_stop(monkeypatch, "E3", "BUSDT", "2023-01-01")
        descartes = []
        ahora = B.generar_candidatos(*args, procesos=1, descartes=descartes)
    finally:
        B._CTX_CACHE.clear()
    t = pegadas[0]
    assert ((antes["simbolo"] == "BUSDT") & (antes["t_senal"] == t)).sum() == 1   # con su stop normal era candidato
    # Con el stop pegado ya no se simula (antes salía como candidato con r = 0.0); las demás quedan idénticas.
    pd.testing.assert_frame_equal(ahora, _sin(antes, "BUSDT", t))
    decision = t + B.DURACION[ESTRATEGIAS["E3"].TEMPORALIDAD]
    reg_stop = [d for d in descartes if d["simbolo"] == "BUSDT" and d["fecha"] == decision.isoformat()]
    assert [d["codigo"] for d in reg_stop] == [DS.STOP_O_SIMULACION] and "r" not in reg_stop[0]


def test_diario_descarta_el_stop_pegado_con_el_mismo_codigo(reg, monkeypatch):
    md = _mercado_diario(reg, grandes_n=15)
    antes = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01")
    t0 = antes.iloc[0]
    pegadas = _pegar_stop(monkeypatch, "M1", t0["simbolo"], t0["t_senal"])
    descartes = []
    ahora = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01", descartes=descartes)
    assert pegadas[0] == t0["t_senal"]
    pd.testing.assert_frame_equal(ahora, _sin(antes, t0["simbolo"], t0["t_senal"]))
    reg_stop = [d for d in descartes if d["simbolo"] == t0["simbolo"] and d["fecha"] == t0["t_decision"].isoformat()]
    assert [d["codigo"] for d in reg_stop] == [DS.STOP_O_SIMULACION] and "r" not in reg_stop[0]
