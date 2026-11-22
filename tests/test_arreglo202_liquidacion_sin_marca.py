"""Arreglo 202: la liquidación no se salta cuando falta la vela de precio de marca.

Antes, con la vela de marca en NaN (backtest y validar-futuros) o en None (papel), la comparación con la liquidación daba
falso y la revisión se saltaba: la operación salía por el stop aunque el precio hubiera pasado la liquidación. Ahora,
si falta la vela de marca, se revisa con el máximo y el mínimo del ÚLTIMO precio de esa vela (lo más prudente), y si a
una moneda le falta toda la serie de marca, validar-futuros hace lo mismo en todas sus velas (el aviso «la liquidación
se revisa con el último precio» ya es verdad). Se cuenta cuántas velas se revisaron así y sale en el informe de
validar-futuros y en el resumen de papel. Con la vela de marca presente, nada cambia.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from apoyo_futuros import ClienteFalso, escalones_verificados
from sobreviviente import backtest as B
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import datos_publicos as DP
from sobreviviente.futuros import validar as VF

from test_arreglo149_cartera_futuros import _pos
from test_arreglo151_validar_futuros import _mercado, _reg

IDX = pd.date_range("2026-01-01", periods=6, freq="4h", tz="UTC")
GEST = {"modo": "chandelier", "chandelier_atr": 3.0, "sin_breakeven": True}


def _arr(lado="LARGO", marca_nan=False):
    """La vela 3 cae a 40 (LARGO) o sube a 160 (CORTO); ATR 20."""
    h = np.full(6, 101.0)
    lo = np.full(6, 99.0)
    if lado == "LARGO":
        lo[3] = 40.0
    else:
        h[3] = 160.0
    a = {"o": np.full(6, 100.0), "h": h, "l": lo, "c": np.full(6, 100.0), "atr": np.full(6, 20.0),
         "marca_h": h.copy(), "marca_l": lo.copy()}
    if marca_nan:
        a["marca_h"][3] = np.nan
        a["marca_l"][3] = np.nan
    return a


def _sim(arr, lado="LARGO"):
    stop, liq = (41.0, 55.0) if lado == "LARGO" else (159.0, 145.0)
    return B.simular_operacion(arr, IDX, 0, lado, 100.0, stop, None, GEST, 0.05, 0.05, pd.Timedelta(hours=4),
                               apalancamiento=2.0, precio_liq=liq, tarifa_liq_pct=1.25)


# ---------------------------------------------------------------------------- backtest.simular_operacion
def test_con_la_vela_de_marca_se_liquida_y_nada_cambia():
    r = _sim(_arr())
    assert r["liquidada"] is True and r["motivo"] == "liquidación" and r["salida"] == 55.0
    assert "velas_liq_ultimo_precio" not in r                    # con la marca presente, el resultado de siempre


def test_sin_la_vela_de_marca_tambien_se_liquida_con_el_ultimo_precio():
    r = _sim(_arr(marca_nan=True))
    assert r["liquidada"] is True and r["motivo"] == "liquidación" and r["salida"] == 55.0   # antes: stop en 40.98
    assert r["velas_liq_ultimo_precio"] == 1
    assert r == {**_sim(_arr()), "velas_liq_ultimo_precio": 1}  # lo mismo que con la marca, más la cuenta


def test_corto_sin_la_vela_de_marca_tambien_se_liquida():
    r = _sim(_arr("CORTO", marca_nan=True), "CORTO")
    assert r["liquidada"] is True and r["salida"] == 145.0 and r["velas_liq_ultimo_precio"] == 1


def test_solo_cuentan_las_velas_sin_marca_que_se_revisaron():
    a = _arr()
    a["l"][3] = a["marca_l"][3] = 98.0                           # nadie se liquida: la operación sigue abierta
    a["marca_h"][[1, 2]] = np.nan
    a["marca_l"][[1, 2]] = np.nan
    r = _sim(a)
    assert r["liquidada"] is False and r["abierta"] and r["velas_liq_ultimo_precio"] == 2


# ---------------------------------------------------------------------------- papel: cartera.procesar_vela
@pytest.mark.parametrize("marca", [None, float("nan")])
def test_papel_sin_vela_de_marca_revisa_con_el_ultimo_precio(marca):
    p = _pos(entrada=100.0, stop=50.0, liq=61.0)
    assert C.procesar_vela(p, 100, 101, 60, 99, 1.0, marca, marca, False) == (True, 61.0, "liquidación")
    q = _pos(lado="CORTO", entrada=100.0, stop=150.0, liq=140.0)
    assert C.procesar_vela(q, 100, 141, 99, 110, 1.0, marca, marca, False) == (True, 140.0, "liquidación")
    s = _pos(entrada=100.0, stop=50.0, liq=61.0)                 # sin tocar la liquidación: sigue igual que antes
    assert C.procesar_vela(s, 100, 101, 62, 99, 1.0, marca, marca, False) == (False, 0.0, "")


def test_papel_con_la_marca_manda_la_marca():
    p = _pos(entrada=100.0, stop=50.0, liq=61.0)
    # el último precio baja a 60 pero la marca no pasa de 62: no hay liquidación (como siempre)
    assert C.procesar_vela(p, 100, 101, 60, 99, 1.0, 101, 62, False) == (False, 0.0, "")


class SinMarca(ClienteFalso):
    """Futuros contesta todo menos las velas del precio de marca (llegan vacías)."""

    def _get(self, url, params=None, intentos=3):
        if url.endswith("/fapi/v1/markPriceKlines"):
            self.urls.append(url)
            from apoyo_futuros import Respuesta
            return Respuesta(200, [])
        return super()._get(url, params, intentos)


def test_papel_de_punta_a_punta_cuenta_las_velas_y_lo_dice_el_resumen(tmp_path, monkeypatch):
    escalones_verificados(monkeypatch)
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos"), "futuros_papel.activo": True})
    monkeypatch.setattr(FC, "validacion_pasa", lambda r: True)
    cfg = config.leer(reg)
    cli = SinMarca(reg)
    v = DP.cargar(cli, cfg).velas["SOLUSDT"]
    est = C.estado_nuevo(cfg)
    precio = float(v["close"].iloc[-4])
    liq = float(v["low"].iloc[-3]) * 1.001                       # el mínimo del último precio de la vela la cruza
    t = C.T.Tamano(True, "cabe", 0.1, 7.0, 1, 7.0, 0.3, 0.4254, liq)
    pos = C.abrir(est, "SOLUSDT", "LARGO", precio, precio, precio * 0.5, t, datetime.now(timezone.utc),
                  FC.F1.gestion(FC.F1.POR_DEFECTO), 0.05)
    pos["vela_abierta"] = v.index[-3].isoformat()
    est["ultima_vela"] = v.index[-4].isoformat()
    C.guardar_estado(reg, est)
    out = FC.correr(reg, cli)
    assert [c["motivo"] for c in out["cierres"] if c["simbolo"] == "SOLUSDT"] == ["liquidación"]
    assert out["velas_liq_ultimo_precio"] == 1
    assert "Velas revisadas con el último precio (faltaba la marca): 1." in FC.resumen(out)


def test_papel_con_marca_no_cuenta_nada(tmp_path):
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})
    out = FC.correr(reg, ClienteFalso(reg))
    assert out.get("velas_liq_ultimo_precio", 0) == 0
    assert not any("faltaba la marca" in x for x in FC.resumen(out))


# ---------------------------------------------------------------------------- validar-futuros
def _sin_marca_y_desplome(reg, simbolo="SOLUSDT"):
    """El mercado sintético del 151 sin ninguna serie de marca de `simbolo` y con su último precio desplomándose a
    partir de 2024-02-01 (mínimos al 1 % y máximos al 10 000 %): con la liquidación revisada, liquida."""
    m = _mercado(reg)
    del m.marca4h[simbolo]
    v = m.velas[simbolo].copy()
    v.loc[v.index >= "2024-02-01", "low"] = v["low"] * 0.01
    v.loc[v.index >= "2024-02-01", "high"] = v["high"] * 100.0
    m.velas[simbolo] = v
    return m


def test_validar_moneda_sin_serie_de_marca_revisa_la_liquidacion_en_todas_sus_velas(tmp_path):
    reg = _reg(tmp_path)
    m = _sin_marca_y_desplome(reg)
    idx = m.velas["SOLUSDT"].index
    filas = {"SOLUSDT": [(i, lado) for i in range(4000, len(idx) - 50, 40) for lado in ("LARGO", "CORTO")]}
    c = VF.candidatos(m, dict(VF.F1.POR_DEFECTO), idx[0], idx[-1], filas_azar=filas, monedas=["SOLUSDT"])
    assert len(c) and "liquidada" in c and c["liquidada"].fillna(False).astype(bool).any()   # antes: nunca se revisaba
    assert (c["velas_liq_ultimo_precio"] >= 1).all()
    assert (c["velas_liq_ultimo_precio"] == c["velas"]).all()   # TODAS sus velas se revisaron con el último precio


def test_validar_con_marca_no_cambia_y_el_informe_dice_la_cuenta(tmp_path):
    reg = _reg(tmp_path)
    m = _mercado(reg)
    res = VF.evaluar(m, robustez_on=False)
    assert "velas_liq_ultimo_precio" not in res.oos and res.resumen["velas_liq_ultimo_precio"] == 0
    texto = VF.informe(res, m, tmp_path / "V.md")
    assert "- Velas revisadas con el último precio (faltaba la marca): 0." in texto
    m2 = _mercado(reg)
    del m2.marca4h["SOLUSDT"]
    res2 = VF.evaluar(m2, robustez_on=False)
    n = res2.resumen["velas_liq_ultimo_precio"]
    assert n > 0 and n == int(res2.oos.loc[res2.oos["simbolo"] == "SOLUSDT", "velas"].sum())
    assert f"- Velas revisadas con el último precio (faltaba la marca): {n}." in VF.informe(res2, m2, tmp_path / "W.md")
