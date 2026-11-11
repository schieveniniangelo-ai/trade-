"""Arreglo 86 (B10): descarga.py y auditoria.py con un cliente falso y un mercado falso (sin red)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from sobreviviente import auditoria as AU
from sobreviviente import datos as D
from sobreviviente import descarga as DE

from test_arreglo69_banco_filtros_fase1 import _mercado_v1
from test_v2 import diarias


# ---------------- descarga ----------------

class ClienteFalso:
    def __init__(self, cache: Path, simbolos):
        self.cache = cache
        self.simbolos = simbolos
        self.pedidas_largo = []

    def exchange_info(self, mercado, forzar=False):
        return {"symbols": [{"symbol": s, "baseAsset": s[:-4], "quoteAsset": "USDT", "status": st}
                            for s, st in self.simbolos.items()]}

    def velas_api(self, simbolo, intervalo, inicio_ms, fin_ms=None, mercado="SPOT"):
        self.pedidas_largo.append((simbolo, intervalo))
        return diarias(50)


@pytest.fixture
def descarga_falsa(monkeypatch, tmp_path):
    """actualizar_spot / actualizar_futuros escriben velas falsas en la caché en vez de ir a Binance."""
    llamadas = {"spot": [], "fut": []}
    volumen = {"BTCUSDT": 5e9, "AUSDT": 8e7, "BUSDT": 1e3}            # BUSDT nunca entra al universo

    def spot(cliente, simbolo, intervalo, inicio, fin=None):
        llamadas["spot"].append((simbolo, intervalo))
        df = diarias(400)
        df["quote_volume"] = volumen[simbolo]
        D.guardar(df, D.ruta_cache(cliente, "spot", intervalo, simbolo))
        return df

    def futuros(cliente, simbolo, intervalo, inicio, fin):
        llamadas["fut"].append(simbolo)
        return pd.DataFrame(), pd.Series(dtype=float)

    monkeypatch.setattr(D, "actualizar_spot", spot)
    monkeypatch.setattr(D, "actualizar_futuros", futuros)
    cli = ClienteFalso(tmp_path, {"BTCUSDT": "TRADING", "AUSDT": "BREAK", "BUSDT": "TRADING"})
    return cli, llamadas


def test_descargar_todo(reg, descarga_falsa):
    cli, llamadas = descarga_falsa
    r = reg.copia_con({"datos.inicio_historicos": "2022-01-01", "backtest.inicio": "2022-03-01", "backtest.fin": "2023-01-31"})
    res = DE.descargar_todo(r, cli, avisar=lambda *_: None)
    assert res["candidatos"] == 3
    assert res["universo_alguna_vez"] == ["AUSDT", "BTCUSDT"]
    assert res["deslistados_incluidos"] == ["AUSDT"]                 # deslistada: entra al backtest igual
    assert res["futuros"] == ["AUSDT", "BTCUSDT"] and sorted(llamadas["fut"]) == ["AUSDT", "BTCUSDT"]
    assert sorted(s for s, i in llamadas["spot"] if i == "1h") == ["AUSDT", "BTCUSDT"]
    assert cli.pedidas_largo == [("BTCUSDT", "1d"), ("ETHUSDT", "1d")]
    assert (cli.cache / "spot" / "1d_largo" / "BTCUSDT.csv.gz").exists()
    guardado = json.loads((cli.cache / "resumen_descarga.json").read_text())
    assert guardado["universo_alguna_vez"] == res["universo_alguna_vez"]


def test_descargar_todo_sin_futuros(reg, descarga_falsa):
    cli, llamadas = descarga_falsa
    r = reg.copia_con({"datos.inicio_historicos": "2022-01-01", "backtest.inicio": "2022-03-01", "backtest.fin": "2023-01-31"})
    res = DE.descargar_todo(r, cli, avisar=lambda *_: None, con_futuros=False)
    assert res["futuros"] == [] and llamadas["fut"] == []


def test_descargar_largo_sin_velas_no_guarda(tmp_path):
    cli = ClienteFalso(tmp_path, {})
    cli.velas_api = lambda *a, **k: pd.DataFrame()
    DE.descargar_largo(cli, "2024-01-01")
    assert not (tmp_path / "spot").exists()


# ---------------- auditoría ----------------

def test_cierres_diarios_se_ven_al_dia_siguiente(reg):
    m = _mercado_v1(reg)
    m.spot1d = {"XUSDT": diarias(10)}
    c = AU.cierres_diarios(m)["XUSDT"]
    assert c.index[0] == m.spot1d["XUSDT"].index[0] + pd.Timedelta(days=1)
    assert c.tolist() == m.spot1d["XUSDT"]["close"].tolist()


def test_auditoria_ejecutar_con_mercado_falso(reg):
    r = reg.copia_con({"backtest.inicio": "2023-01-01", "backtest.fin": "2023-06-10", "validacion.holdout_meses": 1,
                       "validacion.wf_entrenamiento_meses": 2, "validacion.wf_prueba_meses": 1,
                       "validacion.montecarlo_n": 40, "validacion.lentos.orden_azar_n": 2,
                       "validacion.lentos.comisiones_sensibilidad": [0.1, 0.15]})
    m = _mercado_v1(r)
    m.spot1d = {s: D.resamplear(df, "1D") for s, df in m.spot1h.items()}
    out = AU.ejecutar(m, avisar=lambda *_: None, n_azar=1)
    assert out["params"] == AU.E1_PARAMS_V1
    assert set(out["A3"]) == set(AU.VARIANTES_SALIDA)
    assert out["A1"]["operaciones"] == out["A2"]["operaciones_mercado"]
    assert set(out["A9"]) == {0.1, 0.15}
    assert m.reg is r                                                 # A9 deja el reglamento como estaba
    assert out["A1"]["operaciones"] > 0 and out["A8"]["senales"] > 0
    assert out["A9"][0.1]["operaciones"] == out["A9"][0.15]["operaciones"] > 0       # mismas señales…
    assert out["A9"][0.15]["expectativa_r"] < out["A9"][0.1]["expectativa_r"]       # …más comisión, menos R
