"""Arreglo 151: validar-futuros (backtest walk-forward y compuertas estrictas de F1) con un mercado SINTÉTICO."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apoyo_futuros import ClienteFalso
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import datos_publicos as DP
from sobreviviente.futuros import validar as VF

CLAVES = ["operaciones", "factor_ganancia", "expectativa", "ventanas", "caida_p95", "azar", "robustez",
          "liquidaciones", "estres", "largo_y_corto", "concentracion", "sin_una_moneda", "no_caben"]


def _reg(tmp_path):
    return RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos"), "backtest.inicio": "2023-01-01",
                                   "backtest.fin": "2024-06-30", "validacion.azar_n": 60,
                                   "validacion.montecarlo_n": 200})


def _serie(n, semilla, base, tendencia):
    rng = np.random.default_rng(semilla)
    ruido = rng.normal(0, 0.012, n)
    return base * np.exp(np.cumsum(tendencia + ruido))


def _mercado(reg, liquidar: str | None = None) -> VF.MercadoF1:
    cfg = config.leer(reg)
    idx = pd.date_range("2022-01-01", "2024-06-30 20:00", freq="4h", tz="UTC")
    n = len(idx)
    fase = (np.arange(n) // 700) % 2                       # tramos de ~4 meses al alza y a la baja
    tendencia = np.where(fase == 0, 0.0012, -0.0012)
    velas, marca, fund, pf, liquido = {}, {}, {}, {}, {}
    for k, s in enumerate(cfg["monedas"]):
        c = _serie(n, 10 + k, [70.0, 0.9, 590.0, 0.06][k], tendencia)
        o = np.r_[c[0], c[:-1]]
        h, lo = np.maximum(o, c) * 1.006, np.minimum(o, c) * 0.994
        v = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": 1e6, "quote_volume": 5e7},
                         index=idx)
        velas[s] = v
        mk = v[["open", "high", "low", "close"]].copy()
        if s == liquidar:
            mk.loc[mk.index >= "2024-02-01", "low"] = mk["low"] * 0.01      # la marca se desploma: liquida largos
            mk.loc[mk.index >= "2024-02-01", "high"] = mk["high"] * 100.0   # y cortos
        marca[s] = mk
        fund[s] = pd.Series(0.0001, index=pd.date_range("2022-01-01", "2024-06-30", freq="8h", tz="UTC"))
        pf[s] = pd.Series(c, index=idx + pd.Timedelta(hours=4))
        liquido[s] = VF.liquidez_diaria(v, float(cfg["volumen_mediano_min_usdt"]))
    btc = _serie(n, 99, 40000.0, tendencia)
    btc4 = pd.DataFrame({"open": np.r_[btc[0], btc[:-1]], "high": btc * 1.005, "low": btc * 0.995, "close": btc,
                         "quote_volume": 1e9}, index=idx)
    return VF.MercadoF1(reg, cfg, velas, fund, marca, pf, VF.diarias_desde_4h(btc4), liquido,
                        dict(VF.FILTROS_2026_11_16), {s: 1.25 for s in cfg["monedas"]})


def test_las_compuertas_se_calculan_y_el_informe_dice_el_veredicto(tmp_path):
    reg = _reg(tmp_path)
    m = _mercado(reg)
    res = VF.evaluar(m)
    assert list(res.compuertas) == CLAVES
    assert all(isinstance(ok, bool) and txt for ok, txt in res.compuertas.values())
    assert res.pasa == all(ok for ok, _ in res.compuertas.values())
    assert res.resumen["operaciones"] > 0 and set(res.oos["lado"]) <= {"LARGO", "CORTO"}
    assert len(res.ventanas) == 2 and res.robustez["tabla"] and res.capital["capital_inicial"] == 42.54
    assert res.resumen["liquidaciones"] == 0 and res.compuertas["liquidaciones"][0]
    # una moneda nunca tiene dos posiciones a la vez y nunca hay más de 2 abiertas
    o = res.oos.sort_values("t_decision")
    for _, f in o.iterrows():
        abiertas = o[(o["t_decision"] <= f["t_decision"]) & (o["t_salida"] > f["t_decision"])]
        assert len(abiertas) <= 2 and abiertas["simbolo"].is_unique
    texto = VF.informe(res, m, tmp_path / "VALIDACION_FUTUROS.md", "abc1234")
    veredicto = "**Veredicto: F1 PASA.**" if res.pasa else "**Veredicto: F1 NO PASA.**"
    assert veredicto in texto and "abc1234" in texto
    assert "Nada de esto promete ganancias" in texto
    assert "DECISIÓN DE ÁNGELO 2026-11-16" in texto and "MECÁNICO por delegación" in texto
    assert (tmp_path / "VALIDACION_FUTUROS.md").read_text(encoding="utf-8") == texto


def test_una_liquidacion_hace_fallar_su_compuerta(tmp_path):
    reg = _reg(tmp_path)
    res = VF.evaluar(_mercado(reg, liquidar="SOLUSDT"), robustez_on=False)
    assert res.resumen["liquidaciones"] > 0
    ok, txt = res.compuertas["liquidaciones"]
    assert not ok and "CERO" in txt and not res.pasa


def test_el_resultado_se_repite_con_la_semilla(tmp_path):
    reg = _reg(tmp_path)
    a = VF.evaluar(_mercado(reg), robustez_on=False)
    b = VF.evaluar(_mercado(reg), robustez_on=False)
    assert a.compuertas == b.compuertas and a.azar == b.azar
    assert a.mc["caida_p95"] == b.mc["caida_p95"]
    pd.testing.assert_frame_equal(a.oos, b.oos)


def test_compuertas_estrictas_a_mano():
    res = VF.ResultadoF1(
        resumen={"operaciones": 150, "factor_ganancia": 1.5, "expectativa_r": 0.2, "ventanas_positivas_pct": 70,
                 "liquidaciones": 0},
        mc={"caida_p95": 20.0}, mc_bloques={"caida_p95": 24.0}, azar={"percentil_estrategia": 99.0},
        robustez={"todas_positivas": True, "minimo": 0.05}, estres={"operaciones": 150, "expectativa_r": 0.06},
        por_lado={"LARGO": {"operaciones": 80, "expectativa_r": 0.1}, "CORTO": {"operaciones": 70, "expectativa_r": 0.3}},
        por_moneda={s: {"parte_pct": 25.0} for s in config.MONEDAS_PERMITIDAS},
        sin_moneda={s: 0.15 for s in config.MONEDAS_PERMITIDAS}, capital={"no_caben_pct": 10.0})
    reg = RGL.cargar()
    cfg = dict(config.POR_DEFECTO)
    minimo = VF.azar_min_pct(reg)
    assert minimo == pytest.approx(100 - 10 / 9)
    c = VF.compuertas(res, cfg, 25.0, minimo)
    assert all(ok for ok, _ in c.values()), c
    for cambio in ({"resumen": {**res.resumen, "liquidaciones": 1}}, {"mc_bloques": {"caida_p95": 25.1}},
                   {"azar": {"percentil_estrategia": 98.8}}, {"capital": {"no_caben_pct": 20.1}},
                   {"por_moneda": {**res.por_moneda, "SOLUSDT": {"parte_pct": 51.0}}},
                   {"sin_moneda": {**res.sin_moneda, "XRPUSDT": 0.04}},
                   {"estres": {"operaciones": 150, "expectativa_r": 0.049}},
                   {"por_lado": {**res.por_lado, "CORTO": {"operaciones": 70, "expectativa_r": -0.01}}},
                   {"resumen": {**res.resumen, "operaciones": 99}}):
        otro = VF.ResultadoF1(**{**res.__dict__, **cambio})
        assert not all(ok for ok, _ in VF.compuertas(otro, cfg, 25.0, minimo).values()), cambio


def test_solo_se_piden_rutas_de_la_lista_blanca_y_sin_datos_no_valida(tmp_path, capsys):
    reg = _reg(tmp_path)
    cli = ClienteFalso(reg)
    assert FC.comando_validar(reg, None, cli) == 1          # data.binance.vision del cliente falso: 404 → sin velas
    assert "No hay datos de Futuros para validar" in capsys.readouterr().out
    assert cli.urls and all(DP.ruta_permitida(u) for u in cli.urls), [u for u in cli.urls if not DP.ruta_permitida(u)]
    assert any("data.binance.vision" in u for u in cli.urls)


def test_validar_escribe_el_informe_junto_al_reglamento(tmp_path, monkeypatch, capsys):
    (tmp_path / "reglamento.yaml").write_text((VF.Path(FC.__file__).parents[2] / "reglamento.yaml")
                                              .read_text(encoding="utf-8"), encoding="utf-8")
    reg = RGL.cargar(tmp_path / "reglamento.yaml").copia_con(
        {"backtest.inicio": "2023-01-01", "backtest.fin": "2024-06-30", "validacion.azar_n": 30,
         "validacion.montecarlo_n": 100})
    monkeypatch.setattr(VF, "cargar_mercado", lambda r, c, cfg: _mercado(reg))
    assert FC.comando_validar(reg, type("A", (), {"sin_robustez": True, "commit": "x"})(), ClienteFalso(reg)) == 0
    texto = (tmp_path / "VALIDACION_FUTUROS.md").read_text(encoding="utf-8")
    salida = capsys.readouterr().out
    assert "Veredicto: F1" in texto and ("F1 PASA." in salida or "F1 NO PASA." in salida)


def test_cargar_mercado_con_cache_y_reglas_de_exchangeinfo(tmp_path, monkeypatch):
    reg = _reg(tmp_path)
    m0 = _mercado(reg)
    def futuros(cli, s, iv, a, b):
        assert iv == "4h"
        v = m0.velas.get(s)
        if v is None:      # BTC: velas de 4 h armadas desde las diarias del mercado sintético
            d = m0.btc1d
            idx = pd.date_range(d.index[0], d.index[-1] + pd.Timedelta(hours=20), freq="4h", tz="UTC")
            v = d.reindex(idx, method="ffill").assign(volume=1.0)
        return v, m0.funding.get(s, pd.Series(dtype=float))
    monkeypatch.setattr(VF.D, "actualizar_futuros", futuros)
    monkeypatch.setattr(VF.D, "actualizar_precio_marca",
                        lambda cli, s, a, b: pd.DataFrame() if s == "DOGEUSDT" else
                        m0.velas[s][["open", "high", "low", "close"]].resample("1h").ffill())
    m = VF.cargar_mercado(reg, ClienteFalso(reg), config.leer(reg))
    assert set(m.velas) == set(config.MONEDAS_PERMITIDAS) and not m.btc1d.empty
    assert m.filtros["SOLUSDT"].paso == 0.01 and m.tarifa_liq["SOLUSDT"] == pytest.approx(1.5)
    assert "DOGEUSDT" not in m.marca4h and any("sin precio de marca" in a for a in m.avisos)
    assert not any("exchangeInfo" in a for a in m.avisos)
    reg2 = reg.copia_con({"datos.carpeta": str(tmp_path / "otra")})      # sin la copia guardada de exchangeInfo
    m2 = VF.cargar_mercado(reg2, ClienteFalso(reg2, estado=451), config.leer(reg2))
    assert any("exchangeInfo de Futuros no disponible" in a for a in m2.avisos)
    assert m2.filtros["XRPUSDT"] == VF.FILTROS_2026_11_16["XRPUSDT"]
