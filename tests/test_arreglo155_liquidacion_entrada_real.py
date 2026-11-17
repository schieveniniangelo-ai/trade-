"""Arreglo 155: la liquidación y el tamaño de F1 se calculan con la ENTRADA REAL (apertura siguiente ± deslizamiento),
no con el cierre de la señal; tanto en validar-futuros como en futuros-papel. SOLO PAPEL."""
from __future__ import annotations

from urllib.parse import urlparse

import numpy as np
import pandas as pd
import pytest

from apoyo_futuros import ClienteFalso, escalones_verificados
from sobreviviente import backtest as B
from sobreviviente import reglamento as RGL
from sobreviviente.estrategias import f1 as F1
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import liquidacion as LQ
from sobreviviente.futuros import tamano as T
from sobreviviente.futuros import validar as VF
from test_arreglo151_validar_futuros import _mercado, _reg


# ---------------------------------------------------------------------------- precio de entrada
@pytest.mark.parametrize("lado", ["LARGO", "CORTO"])
def test_precio_entrada_es_el_mismo_que_usa_simular_operacion(lado):
    idx = pd.date_range("2024-01-01", periods=6, freq="4h", tz="UTC")
    o = np.array([10.0, 10.4, 9.7, 10.1, 10.3, 10.2])
    arr = {"o": o, "h": o * 1.02, "l": o * 0.98, "c": o * 1.001, "atr": np.full(6, 0.3)}
    stop = 9.0 if lado == "LARGO" else 11.0
    sim = B.simular_operacion(arr, idx, 1, lado, 10.4, stop, None, F1.gestion(dict(F1.POR_DEFECTO)), 0.05, 0.07, pd.Timedelta(hours=4))
    assert sim is not None
    assert B.precio_entrada(o[2], lado, 0.07) == sim["entrada"]


# ---------------------------------------------------------------------------- validar-futuros
def _mercado_con_huecos(reg):
    """El mercado sintético del 151, pero con aperturas que NO son el cierre anterior (huecos de ±1.5 %)."""
    m = _mercado(reg)
    v = m.velas["SOLUSDT"].copy()
    hueco = 1 + 0.015 * np.sin(np.arange(len(v)) * 0.7)
    v["open"] = v["close"].shift(1).fillna(v["close"]) * hueco
    v["high"] = np.maximum(v["high"], v["open"])
    v["low"] = np.minimum(v["low"], v["open"])
    m.velas["SOLUSDT"] = v
    return m


def test_validar_pasa_la_liquidacion_calculada_en_la_entrada_real(tmp_path, monkeypatch):
    reg = _reg(tmp_path)
    m = _mercado_con_huecos(reg)
    cfg = m.cfg
    llamadas = []
    real = VF.B.simular_operacion

    def espia(*a, **k):
        r = real(*a, **k)
        llamadas.append((a, k, r))
        return r
    monkeypatch.setattr(VF.B, "simular_operacion", espia)
    filas = {"SOLUSDT": [(i, "CORTO") for i in range(400, 4000, 37)]}
    params = dict(F1.POR_DEFECTO)
    VF.candidatos(m, params, m.velas["SOLUSDT"].index[0], m.velas["SOLUSDT"].index[-1], filas_azar=filas,
                  monedas=["SOLUSDT"])
    assert len(llamadas) >= 10
    esc = LQ.cargar_escalones("SOLUSDT")
    distintas = 0
    for a, k, r in llamadas:
        if r is None:
            continue
        precio_senal, stop, lado = a[4], a[5], a[3]
        entrada = r["entrada"]
        assert entrada != pytest.approx(precio_senal, rel=1e-6)            # hay hueco: la entrada no es el cierre
        t = T.calcular(float(cfg["capital_papel"]), float(cfg["riesgo_por_operacion_pct"]), entrada, stop, lado,
                       m.filtros["SOLUSDT"], cfg, escalones=esc)
        apal = float(t.apalancamiento or 1)
        q = t.cantidad if t.cantidad > 0 else 1.0
        assert k["apalancamiento"] == apal
        assert k["precio_liq"] == pytest.approx(LQ.precio_liquidacion_aislado(entrada, q, lado, apal, esc))
        # …y no la del cierre de la señal
        t0 = T.calcular(float(cfg["capital_papel"]), float(cfg["riesgo_por_operacion_pct"]), precio_senal, stop,
                        lado, m.filtros["SOLUSDT"], cfg, escalones=esc)
        liq_cierre = LQ.precio_liquidacion_aislado(precio_senal, t0.cantidad if t0.cantidad > 0 else 1.0, lado,
                                                   float(t0.apalancamiento or 1), esc)
        distintas += k["precio_liq"] != pytest.approx(liq_cierre, rel=1e-9)
    assert distintas > 0


def _fila(t, entrada, pnl_unidad):
    return {"simbolo": "SOLUSDT", "lado": "CORTO", "t_senal": t - pd.Timedelta(hours=4), "t_decision": t,
            "precio_plan": 70.0, "stop": 73.5, "fuerza": 1.0, "entrada": entrada, "t_salida": t + pd.Timedelta(hours=8),
            "pnl_unidad": pnl_unidad, "liquidada": False}


def test_la_cartera_de_validar_no_arriesga_mas_de_lo_pedido_con_la_entrada_real(tmp_path):
    reg = _reg(tmp_path)
    m = _mercado(reg)
    cfg = m.cfg
    t0 = pd.Timestamp("2024-01-10 04:00", tz="UTC")
    # 1) Hueco a la baja: 68.5 → stop a 5.0 (no a 3.5). Con el cierre serían 0.12 SOL y 0.60 USDT de riesgo (> 0.4254).
    # 2) Hueco más grande: 67 → con la entrada real ya no llega al mínimo de Binance: no cabe, no se cuenta.
    cands = pd.DataFrame([_fila(t0, 68.5, -5.0), _fila(t0 + pd.Timedelta(days=2), 67.0, -6.5)])
    r = VF.simular_cartera(cands, m)
    ops = r["_ops"]
    assert r["operaciones"] == 1 and r["no_caben"] == 1
    op = ops.iloc[0]
    pedido = float(cfg["capital_papel"]) * float(cfg["riesgo_por_operacion_pct"]) / 100.0
    assert op["cantidad"] * abs(op["entrada"] - op["stop"]) <= pedido + 1e-9
    assert op["cantidad"] == pytest.approx(0.08)


def test_la_cartera_de_validar_sin_entrada_usa_el_precio_del_plan(tmp_path):
    """Candidatos viejos (sin columna `entrada`) se dimensionan como antes, con el precio del plan."""
    reg = _reg(tmp_path)
    m = _mercado(reg)
    t0 = pd.Timestamp("2024-01-10 04:00", tz="UTC")
    fila = _fila(t0, 70.0, -3.5)
    del fila["entrada"]
    r = VF.simular_cartera(pd.DataFrame([fila]), m)
    assert r["operaciones"] == 1 and r["_ops"].iloc[0]["cantidad"] == pytest.approx(0.12)


# ---------------------------------------------------------------------------- futuros-papel
class ClienteHueco(ClienteFalso):
    """Como ClienteFalso, pero la ÚLTIMA vela de 4 h de `simbolo` abre `factor` veces su apertura normal."""

    def __init__(self, reg, simbolo="SOLUSDT", factor=0.98, **kw):
        super().__init__(reg, **kw)
        self.simbolo, self.factor = simbolo, factor

    def _get(self, url, params=None, intentos=3):
        r = super()._get(url, params, intentos)
        params = params or {}
        if (urlparse(url).path == "/fapi/v1/klines" and params.get("symbol") == self.simbolo
                and params.get("interval") == "4h" and r._cuerpo):
            fila = list(r._cuerpo[-1])
            o = float(fila[1]) * self.factor
            fila[1] = str(o)
            fila[2] = str(max(float(fila[2]), o))
            fila[3] = str(min(float(fila[3]), o))
            r._cuerpo = r._cuerpo[:-1] + [fila]
        return r


@pytest.fixture
def activo(tmp_path, monkeypatch):
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos"), "futuros_papel.activo": True})
    monkeypatch.setattr(FC, "validacion_pasa", lambda r: True)
    escalones_verificados(monkeypatch)          # Arreglo 159 (DECISIÓN DE ÁNGELO 2026-11-17)
    real = FC.F1.senales

    def senales(ctx, p):                     # señal CORTO forzada en la penúltima vela de SOLUSDT, stop a +5 %
        s = real(ctx, p)
        if ctx.simbolo == "SOLUSDT":
            k = s.index[-2]
            s.loc[k, "entrada"], s.loc[k, "lado"] = True, "CORTO"
            s.loc[k, "stop"] = s.loc[k, "precio"] * 1.05
            s.loc[k, "stop_pct"] = 5.0
        return s
    monkeypatch.setattr(FC.F1, "senales", senales)
    return reg


def test_futuros_papel_guarda_la_liquidacion_de_su_entrada(activo):
    cfg = config.leer(activo)
    out = FC.correr(activo, ClienteHueco(activo, factor=0.98))
    assert out["modo"] == "papel" and len(out["aperturas"]) == 1
    sen = [f for f in out["senales"] if f["simbolo"] == "SOLUSDT"][0]
    est = C.cargar_estado(activo, cfg)
    pos = est["posiciones"][0]
    esc = LQ.cargar_escalones("SOLUSDT")
    assert pos["entrada"] < sen["precio"] * 0.99                            # abrió en el hueco, no en el cierre
    liq_entrada = LQ.precio_liquidacion_aislado(pos["entrada"], pos["cantidad"], "CORTO", pos["apalancamiento"], esc)
    liq_senal = LQ.precio_liquidacion_aislado(sen["precio"], pos["cantidad"], "CORTO", pos["apalancamiento"], esc)
    assert pos["liquidacion"] == pytest.approx(liq_entrada)
    assert pos["liquidacion"] != pytest.approx(liq_senal, rel=1e-6)
    assert out["aperturas"][0]["liquidacion"] == pytest.approx(liq_entrada)
    pedido = float(cfg["capital_papel"]) * float(cfg["riesgo_por_operacion_pct"]) / 100.0
    assert pos["cantidad"] * abs(pos["entrada"] - pos["stop"]) <= pedido + 1e-9


def test_futuros_papel_no_abre_si_con_la_entrada_real_ya_no_cabe(activo):
    """La vela siguiente abre MÁS ALLÁ del stop del corto: con la entrada real no cabe y no se abre nada."""
    cfg = config.leer(activo)
    out = FC.correr(activo, ClienteHueco(activo, factor=1.06))
    assert out["aperturas"] == []
    sen = [f for f in out["senales"] if f["simbolo"] == "SOLUSDT"][0]
    assert sen["cabe"] is True and sen["abre"] is False and sen["razon_entrada"]
    assert any("entrada real" in a for a in out["avisos"])
    est = C.cargar_estado(activo, cfg)
    assert est["posiciones"] == [] and est["capital"] == pytest.approx(float(cfg["capital_papel"]))
