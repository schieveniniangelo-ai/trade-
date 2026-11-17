"""Arreglo 147: tamaño de F1 por riesgo; el apalancamiento (1x o 2x) sale como consecuencia."""
from __future__ import annotations

import numpy as np
import pytest

from apoyo_futuros import exchange_info_falso
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import config
from sobreviviente.futuros import tamano as T

CAP = 42.54
CFG = dict(config.POR_DEFECTO)
INFO = {x["symbol"]: x for x in exchange_info_falso()["symbols"]}


def _f(s):
    return T.filtros_moneda(INFO[s])


def _t(s, precio, stop_pct, lado="LARGO", **kw):
    stop = precio * (1 - stop_pct / 100) if lado == "LARGO" else precio * (1 + stop_pct / 100)
    return T.calcular(CAP, 1.0, precio, stop, lado, _f(s), CFG, **kw)


def test_sol_cabe_a_1x():
    t = _t("SOLUSDT", 71.63, 5.0)
    assert t.cabe and t.cantidad == pytest.approx(0.11) and t.valor == pytest.approx(7.8793, abs=1e-3)
    assert t.apalancamiento == 1 and t.margen == pytest.approx(t.valor)
    assert t.riesgo_pedido_usdt == pytest.approx(0.4254)
    assert t.riesgo_usdt == pytest.approx(0.394, abs=1e-3) and t.riesgo_usdt <= 0.4254


def test_xrp_va_a_2x():
    t = _t("XRPUSDT", 0.9547, 2.0)
    assert t.cabe and t.cantidad == pytest.approx(22.2) and t.valor == pytest.approx(21.194, abs=1e-3)
    assert t.apalancamiento == 2 and t.margen == pytest.approx(10.597, abs=1e-3)


def test_bnb_cabe_con_el_minimo_de_5():
    t = _t("BNBUSDT", 591.45, 4.0)
    assert t.cabe and t.cantidad == pytest.approx(0.01) and t.valor == pytest.approx(5.9145, abs=1e-3)
    assert t.riesgo_usdt == pytest.approx(0.237, abs=1e-3)


def test_eth_no_cabe():
    t = _t("ETHUSDT", 1817.76, 3.0)
    assert not t.cabe and "no cabe" in t.razon and t.valor == pytest.approx(12.724, abs=1e-3) and t.valor < 20


@pytest.mark.parametrize("stop_pct", [1.5, 2.0, 3.0, 5.0, 8.0])
@pytest.mark.parametrize("lado", ["LARGO", "CORTO"])
def test_btc_nunca_cabe(stop_pct, lado):
    t = _t("BTCUSDT", 64674.80, stop_pct, lado)
    assert not t.cabe and "no cabe" in t.razon


def test_segunda_posicion_no_cabe_por_margen():
    # XRP con stop de 2 %: 21.194 USDT a 2x = 10.597 de margen; 21 + 10.597 > 25.52
    t = _t("XRPUSDT", 0.9547, 2.0, margen_abierto=21.0)
    assert not t.cabe and "no cabe por margen" in t.razon
    # SOL a 5 %: 7.879 de margen > 4.52
    assert not _t("SOLUSDT", 71.63, 5.0, margen_abierto=21.0).cabe
    # BNB a 4 %: 5.9145 > 4.52
    assert not _t("BNBUSDT", 591.45, 4.0, margen_abierto=21.0).cabe
    # justo en el límite: 21 + 4.52 = 25.52 ≤ 25.524 cabe; un poco más, no
    f = T.Filtros(simbolo="SOLUSDT", tick=0.01, paso=1.0, cantidad_min=1.0, minimo_usdt=1.0)
    precio = 4.52                                       # paso de 1: la posición vale exactamente 4.52 a 1x
    assert T.calcular(CAP, 1.0, precio, precio * 0.95, "LARGO", f, CFG, margen_abierto=21.0).margen == pytest.approx(4.52)
    assert T.calcular(CAP, 1.0, precio, precio * 0.95, "LARGO", f, CFG, margen_abierto=21.0).cabe
    assert not T.calcular(CAP, 1.0, precio, precio * 0.95, "LARGO", f, CFG, margen_abierto=21.01).cabe


def test_el_apalancamiento_nunca_pasa_de_2_y_el_riesgo_real_nunca_pasa_del_pedido():
    rng = np.random.default_rng(int(RGL.cargar().get("validacion.semilla")))
    vistos = set()
    for _ in range(3000):
        s = str(rng.choice(["SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]))
        precio = float(INFO_PRECIO[s] * rng.uniform(0.3, 3.0))
        stop_pct = float(rng.uniform(0.2, 12.0))
        lado = str(rng.choice(["LARGO", "CORTO"]))
        cap = float(rng.uniform(10, 200))
        riesgo = float(rng.uniform(0.1, 2.0))
        stop = precio * (1 - stop_pct / 100) if lado == "LARGO" else precio * (1 + stop_pct / 100)
        t = T.calcular(cap, riesgo, precio, stop, lado, _f(s), CFG, margen_abierto=float(rng.uniform(0, cap * 0.5)))
        if t.cabe:
            vistos.add(t.apalancamiento)
            assert t.apalancamiento <= 2
            assert t.riesgo_usdt <= cap * riesgo / 100 + 1e-9
            assert t.margen <= cap * 0.30 + 1e-9 and t.valor <= cap * 0.60 + 1e-9
    assert vistos == {1, 2}


ESC_BAJO = [{"escalon": 1, "nocional_min": 0.0, "nocional_max": 1e9, "mmr_pct": 0.5, "cum": 0.0,
             "apalancamiento_max": 50}]
INFO_PRECIO = {"SOLUSDT": 71.63, "XRPUSDT": 0.9547, "BNBUSDT": 591.45, "DOGEUSDT": 0.05885}


def test_tope_de_1x_y_liquidacion_cercana():
    cfg1 = {**CFG, "apalancamiento_tope": 1}
    t = T.calcular(CAP, 1.0, 0.9547, 0.9547 * 0.98, "LARGO", _f("XRPUSDT"), cfg1)
    assert not t.cabe and "tope es 1x" in t.razon
    # con un escalón absurdo (MMR 49 %) la liquidación a 2x queda pegada al stop
    esc = [{"escalon": 1, "nocional_min": 0.0, "nocional_max": 1e9, "mmr_pct": 49.0, "cum": 0.0, "apalancamiento_max": 2}]
    t = T.calcular(CAP, 1.0, 0.9547, 0.9547 * 0.98, "LARGO", _f("XRPUSDT"), CFG, escalones=esc)
    assert not t.cabe and "liquidación" in t.razon
    assert not T.calcular(CAP, 1.0, 10.0, 11.0, "LARGO", _f("XRPUSDT"), CFG).cabe    # stop del lado equivocado
    f = T.Filtros(simbolo="X", tick=0.01, paso=0.01, cantidad_min=0.01, minimo_usdt=1.0)
    cfg_raro = {**CFG, "margen_posicion_max_pct": 10.0}                               # 2x pide más del 10 %
    assert "por posición" in T.calcular(CAP, 1.0, 5.0, 4.9, "LARGO", f, cfg_raro, escalones=ESC_BAJO).razon
