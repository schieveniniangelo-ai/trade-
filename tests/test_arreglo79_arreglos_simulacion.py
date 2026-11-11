"""Arreglo 79: el backtest y los motores diarios arman con la MISMA función los arreglos que simulan cada señal.

Antes había dos copias (backtest._candidatos_simbolo y diario.generar): velas, ATR y lo que pide la regla de salida
(media, señal de salida o piso del canal). Aquí se revisa que la función única dé, modo por modo, lo mismo que las dos
copias, y que los candidatos salgan idénticos. Velas falsas: sin red y sin llaves."""
import numpy as np
import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente import diario as DI
from sobreviviente.estrategias import ESTRATEGIAS

from test_arreglo69_banco_filtros_fase1 import _mercado_diario
from test_v2 import ctx_diario, diarias


def _como_antes(ctx, gest, sen):
    """Las copias que había antes, juntas: lo que debe salir igual."""
    v = ctx.velas
    arr = {"o": v["open"].to_numpy(float), "h": v["high"].to_numpy(float), "l": v["low"].to_numpy(float),
           "c": v["close"].to_numpy(float), "atr": ctx.atr().to_numpy(float)}
    if gest["modo"] == "media":
        arr["media"] = ctx.sma(int(gest["salida_media"])).to_numpy(float)
    if gest["modo"] in ("senal_salida", "ranking"):
        arr["salir"] = sen["salir"].to_numpy(bool)
    if gest["modo"] == "canal":
        arr["canal"] = v["low"].rolling(int(gest["canal_velas"])).min().to_numpy(float)
    return arr


@pytest.mark.parametrize("gest", [
    {"modo": "chandelier", "chandelier_atr": 3.0},
    {"modo": "meta_luego_chandelier", "chandelier_atr": 3.0},
    {"modo": "media", "salida_media": 20},
    {"modo": "tiempo", "max_velas": 10},
    {"modo": "senal_salida"},
    {"modo": "ranking"},
    {"modo": "canal", "canal_velas": 10},
])
def test_arreglos_iguales_en_cada_modo_de_salida(gest):
    ctx = ctx_diario(diarias(300))
    sen = ESTRATEGIAS["M0"].senales(ctx, {"sma": 200})
    nuevo, antes = B.arrays_simulacion(ctx, gest, sen), _como_antes(ctx, gest, sen)
    assert nuevo.keys() == antes.keys()
    for k in antes:
        np.testing.assert_array_equal(nuevo[k], antes[k])


@pytest.mark.parametrize("clave,params", [("M0", {"sma": 200}), ("M1", {"n": 20}), ("M2", {"L": 30})])
def test_candidatos_diarios_iguales_con_la_funcion_unica(reg, clave, params, monkeypatch):
    md = _mercado_diario(reg, grandes_n=15)
    nuevo = DI.generar(md, clave, params, "2022-06-01", "2024-02-01")
    monkeypatch.setattr(DI, "arrays_simulacion", _como_antes)
    antes = DI.generar(md, clave, params, "2022-06-01", "2024-02-01")
    if clave != "M2":   # en estas velas falsas M2 casi no da señales: basta con que salga igual
        assert not nuevo.empty
    pd.testing.assert_frame_equal(nuevo, antes)
