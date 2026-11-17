"""Arreglo 158: los costos entran al riesgo en futuros/tamano.py (SOLO PAPEL).

Al tocar el stop se pierde la distancia al stop MÁS la comisión de entrada y salida, el deslizamiento y el funding.
distancia efectiva = |precio − stop| + precio × (2 × comisión taker + 2 × deslizamiento grande) ÷ 100
                     + precio × max(0, funding en contra por 8 h) × 3 ÷ 100
Comisión 0.05 % (reglamento costos.comision_futuros_taker_pct) y deslizamiento grande 0.05 %. Con costos=None, como hoy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apoyo_futuros import ClienteFalso, exchange_info_falso
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import tamano as T
from sobreviviente.futuros import validar as VF
from test_arreglo151_validar_futuros import _mercado, _reg

CAP = 42.54
CFG = dict(config.POR_DEFECTO)
INFO = {x["symbol"]: x for x in exchange_info_falso()["symbols"]}
SIN_FUNDING = {"comision_pct": 0.05, "desliz_pct": 0.05, "funding_8h_pct": 0.0}


def _t(s, precio, stop_pct, lado="LARGO", costos=SIN_FUNDING, **kw):
    stop = precio * (1 - stop_pct / 100) if lado == "LARGO" else precio * (1 + stop_pct / 100)
    return T.calcular(CAP, 1.0, precio, stop, lado, T.filtros_moneda(INFO[s]), CFG, costos=costos, **kw)


def test_costos_salen_del_reglamento():
    c = T.costos_reglamento(RGL.cargar(), 0.01)
    assert c == {"comision_pct": 0.05, "desliz_pct": 0.05, "funding_8h_pct": 0.01}
    assert T.costos_reglamento(RGL.cargar(), float("nan"))["funding_8h_pct"] == 0.0     # sin dato: 0


def test_sol_con_stop_de_5_pct_sigue_en_011():
    t = _t("SOLUSDT", 71.63, 5.0)
    assert T.distancia_efectiva(71.63, 71.63 * 0.95, "LARGO", SIN_FUNDING) == pytest.approx(71.63 * 0.052)
    assert t.cabe and t.cantidad == pytest.approx(0.11)          # valor 0.4254 ÷ 5.2 % = 8.181 → 0.11 SOL, como antes
    assert 0.4254 / 0.052 == pytest.approx(8.181, abs=1e-3)
    assert t.riesgo_usdt == pytest.approx(0.11 * 71.63 * 0.052)  # riesgo con costos
    assert t.riesgo_usdt <= 0.4254


def test_xrp_con_stop_de_2_pct_baja_a_202():
    t = _t("XRPUSDT", 0.9547, 2.0)
    assert t.cabe and t.cantidad == pytest.approx(20.2) and t.valor == pytest.approx(19.285, abs=1e-3)   # antes 22.2
    assert _t("XRPUSDT", 0.9547, 2.0, costos=None).cantidad == pytest.approx(22.2)
    assert t.riesgo_usdt == pytest.approx(20.2 * 0.9547 * 0.022) and t.riesgo_usdt <= 0.4254


def test_el_funding_en_contra_suma_y_a_favor_no():
    caro = {**SIN_FUNDING, "funding_8h_pct": 0.03}               # positivo: pagan los largos
    assert T.distancia_efectiva(100.0, 95.0, "LARGO", caro) == pytest.approx(5.0 + 0.2 + 0.09)
    assert T.distancia_efectiva(100.0, 105.0, "CORTO", caro) == pytest.approx(5.0 + 0.2)       # el corto cobra
    barato = {**SIN_FUNDING, "funding_8h_pct": -0.03}            # negativo: pagan los cortos
    assert T.distancia_efectiva(100.0, 105.0, "CORTO", barato) == pytest.approx(5.0 + 0.2 + 0.09)
    assert T.distancia_efectiva(100.0, 95.0, "LARGO", None) == pytest.approx(5.0)
    assert _t("XRPUSDT", 0.9547, 2.0, costos=caro).cantidad < _t("XRPUSDT", 0.9547, 2.0).cantidad


def test_el_riesgo_con_costos_nunca_pasa_del_pedido():
    rng = np.random.default_rng(int(RGL.cargar().get("validacion.semilla")))
    precios = {"SOLUSDT": 71.63, "XRPUSDT": 0.9547, "BNBUSDT": 591.45, "DOGEUSDT": 0.05885}
    cuantas = 0
    for _ in range(3000):
        s = str(rng.choice(list(precios)))
        precio = float(precios[s] * rng.uniform(0.3, 3.0))
        lado = str(rng.choice(["LARGO", "CORTO"]))
        costos = {**SIN_FUNDING, "funding_8h_pct": float(rng.uniform(-0.1, 0.1))}
        t = _t(s, precio, float(rng.uniform(0.5, 10.0)), lado, costos=costos)
        if t.cabe:
            cuantas += 1
            assert t.riesgo_usdt <= 0.4254 + 1e-12 and t.apalancamiento <= 2
    assert cuantas > 500


def test_sin_costos_el_comportamiento_es_el_de_hoy():
    a = _t("SOLUSDT", 71.63, 5.0, costos=None)
    assert a.cantidad == pytest.approx(0.11) and a.riesgo_usdt == pytest.approx(0.394, abs=1e-3)


# ---------------------------------------------------------------------------- quién pasa los costos
@pytest.fixture
def espia(monkeypatch):
    llamadas = []
    real = T.calcular

    def calcular(*a, **k):
        llamadas.append(k.get("costos"))
        return real(*a, **k)
    monkeypatch.setattr(T, "calcular", calcular)
    return llamadas


def test_cartera_pasa_los_costos(espia):
    est = C.estado_nuevo(CFG)
    C.cabe(CFG, est, "SOLUSDT", "LARGO", 71.63, 68.0, T.filtros_moneda(INFO["SOLUSDT"]), costos=SIN_FUNDING)
    assert espia == [SIN_FUNDING]


def test_futuros_papel_pasa_los_costos(espia, tmp_path, monkeypatch):
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})
    real = FC.F1.senales

    def senales(ctx, p, *a, **k):
        s = real(ctx, p, *a, **k)
        if ctx.simbolo == "SOLUSDT":
            i = s.index[-2]
            s.loc[i, "entrada"], s.loc[i, "lado"] = True, "LARGO"
            s.loc[i, "stop"], s.loc[i, "stop_pct"] = s.loc[i, "precio"] * 0.95, 5.0
        return s
    monkeypatch.setattr(FC.F1, "senales", senales)
    FC.correr(reg, ClienteFalso(reg))
    assert espia and all(c is not None and c["comision_pct"] == 0.05 and c["desliz_pct"] == 0.05 for c in espia)


def test_validar_pasa_los_costos_en_candidatos_y_en_la_cartera(espia, tmp_path):
    m = _mercado(_reg(tmp_path))
    v = m.velas["SOLUSDT"]
    cands = VF.candidatos(m, dict(FC.F1.POR_DEFECTO), v.index[0], v.index[-1])
    assert espia and all(c is not None for c in espia)
    assert "funding_8h_pct" in cands
    espia.clear()
    VF.simular_cartera(cands, m)
    assert espia and all(c is not None and c["desliz_pct"] == 0.05 for c in espia)
    assert all(isinstance(c["funding_8h_pct"], float) for c in espia)
    assert not pd.isna(cands["funding_8h_pct"]).any()
