"""Arreglo 1: la Cartera C (tamaño por exposición) sí opera con 46.18 USDT, el aviso de "saltada por capital"
no se repite a diario, y el papel llena como Binance (límite de la compra y límite del stop)."""
import numpy as np
import pandas as pd
import pytest

from sobreviviente import papel as P
from sobreviviente import reglamento as RGL
from sobreviviente.exchange import Filtros
from sobreviviente.gestion import EstadoGestion, vela
from sobreviviente.riesgo import Candidato, calcular_tamano

from test_papel import _datos_dia


def _reg_m0(reg, tmp_path, capital=46.18):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos"), "carteras.capital_inicial": capital})
    for k in r.estrategias:
        r.datos["estrategias"][k]["estado"] = "APAGADA"
    r.datos["estrategias"]["M0"]["estado"] = "PAPEL"
    r.ruta = tmp_path / "reglamento.yaml"
    return r


def _dia_marea_alta(reg):
    for k in range(260, 650, 5):
        dd, velas = _datos_dia(reg, k)
        if dd.md.marea.get(dd.dia) == "ALCISTA":
            return k
    pytest.skip("los datos sintéticos no dieron marea alta")


# ---------------- Tamaño por exposición ----------------

def test_tamano_por_exposicion_llega_al_minimo():
    """46.18 USDT, BTC a 75,000, stop de catástrofe 15 %: por riesgo (1 %) la compra sale de ~3 USDT (no cabe);
    por exposición (30 %) sale de ~13.85 USDT, y su riesgo (≈ 2.08 USDT = 4.5 %) cabe en el riesgo de la Cartera C."""
    f = Filtros("BTCUSDT", 0.01, 0.00001, 0.00001, 5.0)
    c = Candidato("BTCUSDT", "SPOT", "LARGO", "M0", "normales", 75000.0, 63750.0, precio_limite_stop=63431.25)
    tope = 46.18 * 0.30
    por_riesgo = calcular_tamano(46.18, 1.0, 1.0, c, f, tope)
    assert not por_riesgo.ok and por_riesgo.saltada_por_capital
    por_expo = calcular_tamano(46.18, 4.5, 1.0, c, f, tope, "exposicion")
    assert por_expo.ok
    assert 13.0 < por_expo.valor_usdt <= tope                    # 13.50: redondeado al paso de 0.00001 BTC
    assert por_expo.riesgo_usdt <= 46.18 * 0.045 + 1e-9
    mitad = calcular_tamano(46.18, 4.5, 0.5, c, f, tope, "exposicion")   # volatilidad ALTA: a la mitad
    assert mitad.ok and 6.5 < mitad.valor_usdt < 7.0


def test_reglamento_cartera_c():
    r = RGL.cargar()
    c = r.para_cartera("C")
    assert c.riesgo["tamano"] == "exposicion" and c.riesgo["posiciones_max"]["normales"] == 1
    assert r.para_cartera("A").riesgo["tamano"] == "riesgo"
    assert r.para_cartera("B").riesgo["tamano"] == "riesgo"
    assert c.riesgo["caida_max_desde_pico_pct"] == 30.0          # exenta de la regla de 15× (decisión de Ángelo)
    with pytest.raises(RGL.ErrorReglamento):                     # A y B siguen con la regla
        RGL.validar(r.copia_con({"carteras.A.caida_max_desde_pico_pct": 10.0}))


def test_cartera_c_opera_y_a_no(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    a = P.ronda_cartera(r, "A", dd, [], [])
    c = P.ronda_cartera(r, "C", dd, [], [])
    assert not [b for b in a["boletos"] if b["accion"] == "COMPRAR"]
    assert a["opera"] is False and a["capital_necesario"] > 46.18
    compras = [b for b in c["boletos"] if b["accion"] == "COMPRAR"]
    assert compras and compras[0]["simbolo"] == "BTCUSDT"
    assert compras[0]["valor_usdt"] <= 46.18 * 0.30 * 1.003 + 1e-6
    assert c["opera"] is True
    texto = P.resumen_corto({"dia": c["dia"], "carteras": {"A": a, "C": c}, "referencias": {}, "avisos": []})
    assert "Operan con el capital actual: C" in texto and "A (necesita" in texto


def test_saltada_por_capital_no_se_repite(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd1, _ = _datos_dia(r, k)
    m1 = P.ronda_cartera(r, "A", dd1, [], [])["mensajes"]
    assert sum("no cabe con" in m for m in m1) == 1 and "Haría falta un capital" in " ".join(m1)
    dd2, _ = _datos_dia(r, k + 1)
    if dd2.md.marea.get(dd2.dia) != "ALCISTA":
        pytest.skip("la marea cambió justo al día siguiente")
    m2 = P.ronda_cartera(r, "A", dd2, [], [])
    assert not any("no cabe con" in m for m in m2["mensajes"])    # mismo motivo: no se repite
    assert m2["opera"] is False                                   # pero el reporte sigue diciendo que no opera
    est = P.cargar_estado(r, "A", "")
    assert est["avisos_capital"]["M0:BTCUSDT"]["dias"] == 2


# ---------------- Llenado realista ----------------

def test_compra_no_se_llena_si_abre_arriba_del_limite(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    cierre = float(dd.md.velas["BTCUSDT"]["close"].iloc[-1])
    dd.apertura_hoy = lambda s: cierre * 1.01               # abre 1 % arriba; el límite es +0.3 %
    c = P.ronda_cartera(r, "C", dd, [], [])
    assert not [b for b in c["boletos"] if b["accion"] == "COMPRAR"]
    assert c["no_llenadas"] == ["BTCUSDT"] and any("NO SE LLENÓ" in m for m in c["mensajes"])
    assert not P.cargar_estado(r, "C", "")["posiciones"]


def test_compra_se_llena_dentro_del_limite_sin_pasarlo(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    cierre = float(dd.md.velas["BTCUSDT"]["close"].iloc[-1])
    dd.apertura_hoy = lambda s: cierre * 1.0029             # justo abajo del límite; con deslizamiento lo pasaría
    c = P.ronda_cartera(r, "C", dd, [], [])
    b = [x for x in c["boletos"] if x["accion"] == "COMPRAR"][0]
    assert b["llenado_papel"]["precio"] <= b["precio_entrada"] + 1e-9


def _g(**kw):
    base = dict(lado="LARGO", entrada=100.0, entrada_plan=100.0, stop_inicial=90.0, stop=90.0, meta=None,
                modo="senal_salida", params={}, en_r=None, limite_stop_pct=0.5)
    base.update(kw)
    return EstadoGestion(**base)


def test_stop_sin_llenar_si_el_hueco_pasa_el_limite():
    g = _g()
    ev = vela(g, 85.0, 89.0, 84.0, 86.0, 1.0)            # límite = 89.55; abrió en 85 y nunca regresó
    assert not ev.salio and ev.stop_sin_llenar and g.stop_pendiente == pytest.approx(89.55)
    ev = vela(g, 87.0, 90.0, 86.0, 88.0, 1.0)            # al día siguiente sube a 90 ≥ 89.55 → se llena al límite
    assert ev.salio and ev.precio == pytest.approx(89.55) and "tarde" in ev.motivo


def test_stop_con_hueco_dentro_del_limite_se_llena_a_la_apertura():
    ev = vela(_g(), 89.7, 91.0, 89.0, 90.5, 1.0)         # abrió abajo del stop pero arriba del límite
    assert ev.salio and ev.precio == 89.7
    ev = vela(_g(), 89.0, 89.8, 88.0, 89.5, 1.0)         # abrió abajo del límite pero lo tocó en el día
    assert ev.salio and ev.precio == pytest.approx(89.55)


def test_sin_limite_queda_la_regla_de_siempre():
    ev = vela(_g(limite_stop_pct=None), 85.0, 89.0, 84.0, 86.0, 1.0)
    assert ev.salio and ev.precio == 85.0 and "hueco" in ev.motivo


def test_papel_reporta_stop_sin_llenar(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    c = P.ronda_cartera(r, "C", dd, [], [])
    assert [b for b in c["boletos"] if b["accion"] == "COMPRAR"]
    stop = P.cargar_estado(r, "C", "")["posiciones"][0]["gestion"]["stop"]
    dd2, _ = _datos_dia(r, k + 1)
    v = dd2.md.velas["BTCUSDT"]
    t = v.index[-1]
    v.loc[t, ["open", "high", "low", "close"]] = [stop * 0.90, stop * 0.95, stop * 0.85, stop * 0.92]  # hueco de 10 %
    dd2.md._ctx.clear()
    c2 = P.ronda_cartera(r, "C", dd2, [], [])
    assert c2["stops_sin_llenar"] == ["BTCUSDT"]
    assert P.cargar_estado(r, "C", "")["posiciones"], "la posición debe seguir abierta"
    assert any("STOP SIN LLENAR" in m for m in c2["mensajes"])
