"""Arreglo 134: ronda real, parte 2 (entradas).

La misma decisión que la Cartera A de papel (riesgo.evaluar_candidato), con el capital y el efectivo REALES de la foto
de saldo y las posiciones del estado real. No simula llenados ni cambia el efectivo. Un boleto por día, solo BTCUSDT."""
import json
import os
from datetime import timedelta

import pandas as pd
import pytest

from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR
from sobreviviente.exchange import filtros_desde_exchangeinfo

from apoyo_real import AHORA, cuenta, escribir_entrada, orden_stop
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo132_boleto_real import FIXTURE
from test_arreglo133_compuertas_real import reg_vivo
from test_papel import _datos_dia

FILTROS = filtros_desde_exchangeinfo(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    """Ronda real con datos falsos: señal de M0 a 70,000 con stop de 59,500 y marea alta, salvo que se cambie."""
    r = reg_vivo(tmp_path)
    cfg = {"entrada": True, "marea": "ALCISTA", "vol": 50.0}

    def preparar(reg, cli, memes, ahora=None, **kw):
        dd, _ = _datos_dia(reg, 400)
        v = dd.md.velas["BTCUSDT"]
        dd.md.velas["BTCUSDT"] = v.assign(close=v["close"] * 70000.0 / float(v["close"].iloc[-1]))   # BTC cerró en 70,000
        dd.md.filtros["BTCUSDT"] = FILTROS
        dd.md.marea = {dd.dia: cfg["marea"]}
        dd.md.vol_pct = {"BTCUSDT": pd.Series({dd.dia: cfg["vol"]})}   # también es la volatilidad de BTC (btc_vol)
        return dd

    def senales(dd, clave, s, params):
        return pd.DataFrame({"entrada": [cfg["entrada"]], "salir": [False], "precio": [70000.0], "stop": [59500.0],
                             "fuerza": [1.0]}, index=[dd.dia])
    monkeypatch.setattr(P, "preparar_datos", preparar)
    monkeypatch.setattr(P, "_senales", senales)

    def foto(cta=None, ordenes=(), ahora=AHORA - timedelta(minutes=5)):
        c, o = escribir_entrada(tmp_path, cta or cuenta(), list(ordenes))
        for p in (c, o):
            os.utime(p, (ahora.timestamp() - 60, ahora.timestamp() - 60))
        return RE.registrar_saldo(r, c, o, lambda s: 70000.0, ahora=ahora)

    def correr(ahora=AHORA, simular=False):
        return RR.correr(r, ahora, cliente=object(), memes=[], simular=simular)
    return r, cfg, foto, correr


def _boletos(r):
    return json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))


def test_con_senal_sale_un_boleto_de_compra(mundo, capsys):
    r, _, foto, correr = mundo
    foto()
    assert correr() == 0
    (b,) = _boletos(r)
    assert b["boleto_id"].startswith("20261115-RA-COM-BTC-") and b["vence_utc"] == "2026-11-16T02:10:00Z"
    assert b["accion"] == "COMPRAR" and b["modo"] == "REAL" and b["orden_compra"]["quantity"] == "0.00013"
    assert b["orden_compra"]["price"] == "70210" and b["valor_compra_usdt"] == pytest.approx(9.10)
    salida = capsys.readouterr().out
    assert "████ REAL ████" in salida and b["texto"] in salida
    est = RE.cargar_estado(r)
    assert est["posiciones"] == [] and est["capital_inicial"] == 142.54   # no simula llenados
    assert est["dia_ref"] and est["semana_ref"]                            # solo lleva las cuentas del riesgo
    desc = json.loads((RE.ruta_real(r) / "descartes" / "descartes_2026-11-15.json").read_text(encoding="utf-8"))
    assert desc["carteras"]["REAL"][0]["codigo"] == "APROBADA" and desc["carteras"]["REAL"][0]["origen"] == "real"


def test_simular_imprime_el_boleto_y_no_escribe(mundo, capsys):
    r, _, foto, correr = mundo
    foto()
    antes = RE.archivo_saldo(r).read_bytes()
    assert correr(simular=True) == 0
    assert "Boletos REALES que saldrían (simulación: NO se ponen)" in capsys.readouterr().out
    assert not RR.archivo_boletos(r, "2026-11-15").exists() and not RE.archivo_estado(r).exists()
    assert not (RE.ruta_real(r) / "descartes").exists() and RE.archivo_saldo(r).read_bytes() == antes


def test_sin_senal(mundo, capsys):
    r, cfg, foto, correr = mundo
    cfg["entrada"] = False
    foto()
    assert correr() == 0 and _boletos(r) == []
    assert "M0 sin señal de compra hoy." in capsys.readouterr().out


def test_volatilidad_alta_se_salta_por_capital(mundo, capsys):
    r, cfg, foto, correr = mundo
    cfg["vol"] = 85.0
    foto()
    assert correr() == 0 and _boletos(r) == []
    salida = capsys.readouterr().out
    assert "M0 no compra hoy en real: saltada por capital" in salida and "4.20 USDT" in salida


def test_btc_bajista_no_compra(mundo, capsys):
    r, cfg, foto, correr = mundo
    cfg["marea"] = "BAJISTA"
    foto()
    assert correr() == 0 and _boletos(r) == []
    assert "BTC BAJISTA" in capsys.readouterr().out


def test_ya_hay_posicion_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    assert correr() == 0 and _boletos(r) == []
    assert "ya hay una posición abierta en esta moneda" in capsys.readouterr().out


def test_btc_en_la_cuenta_sin_posicion_anotada_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    assert correr() == 0 and _boletos(r) == []
    salida = capsys.readouterr().out
    assert "❌ Sin compras: la conciliación real no cuadra" in salida and "que el estado real no conoce" in salida


def test_foto_vieja_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    foto(ahora=AHORA - timedelta(minutes=130))
    assert correr() == 0 and _boletos(r) == []
    assert "min (máximo 120)" in capsys.readouterr().out


def test_saldo_distinto_del_reglamento_sin_ajuste_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "capital_inicial": 150.0, "pico": 150.0})
    foto(cuenta(usdt=150.0))
    assert correr() == 0 and _boletos(r) == []
    assert "nadie lo ha ajustado" in capsys.readouterr().out


def test_ronda_repetida_no_crea_nada_nuevo(mundo, capsys):
    r, _, foto, correr = mundo
    foto()
    assert correr() == 0
    primero = RR.archivo_boletos(r, "2026-11-15").read_bytes()
    capsys.readouterr()
    assert correr() == 0
    salida = capsys.readouterr().out
    assert "ya corrió" in salida and "NO se vuelven a poner" in salida
    assert RR.archivo_boletos(r, "2026-11-15").read_bytes() == primero


def test_fuera_de_hora_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    foto(ahora=AHORA.replace(hour=4))
    assert correr(ahora=AHORA.replace(hour=4, minute=5)) == 0 and _boletos(r) == []
    assert "FUERA DE HORA" in capsys.readouterr().out


def test_decision_solo_papel_nunca_da_boleto_real(mundo, monkeypatch, capsys):
    r, _, foto, correr = mundo
    from sobreviviente import riesgo as R
    original = R.evaluar_candidato

    def solo_papel(*a, **k):
        d = original(*a, **k)
        d.solo_papel = True
        return d
    monkeypatch.setattr(R, "evaluar_candidato", solo_papel)
    foto()
    assert correr() == 0 and _boletos(r) == []
    assert "solo de papel" in capsys.readouterr().out


def test_resumen_de_papel_dice_papel():
    texto = P.resumen_corto({"dia": "2026-11-15", "carteras": {}, "referencias": {}, "avisos": []})
    assert texto.splitlines()[0] == "Ronda del 2026-11-15 (PAPEL)."
