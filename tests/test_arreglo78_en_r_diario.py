"""Arreglo 78: los motores diarios suben el stop a la entrada en la R que dice el reglamento, igual que el backtest y
el papel.

Antes, `diario.generar` no le pasaba `en_r` a `simular_operacion` y simulaba "+1R → entrada" siempre en 1.0 R. Con el
reglamento de hoy no se notaba (M0, M1 y M2 tienen `mover_a_entrada: false` y el valor es 1.0), pero si cambiaba, el
banco de filtros y la validación v2 habrían medido otra regla de salida que la del papel. Velas falsas: sin red."""
import pandas as pd

from sobreviviente import backtest as B
from sobreviviente import diario as DI
from sobreviviente.estrategias import ESTRATEGIAS

from test_arreglo69_banco_filtros_fase1 import _mercado_diario

PERIODO = ("2022-06-01", "2024-02-01")
COLUMNAS_ENTRADA = ["simbolo", "t_decision", "precio_plan", "stop", "entrada"]


def _m1(reg, cambios):
    return DI.generar(_mercado_diario(reg.copia_con(cambios), grandes_n=15), "M1", {"n": 20}, *PERIODO)


def test_diario_sube_el_stop_en_la_r_del_reglamento(reg):
    con_breakeven = {"estrategias.M1.mover_a_entrada": True}
    en_1 = _m1(reg, {**con_breakeven, "riesgo.gestion.mover_a_entrada_en_r": 1.0})
    en_medio = _m1(reg, {**con_breakeven, "riesgo.gestion.mover_a_entrada_en_r": 0.5})
    assert len(en_1) >= 5 and len(en_1) == len(en_medio)
    # Mismas señales, misma entrada y mismo stop inicial: solo cambia en qué R sube el stop a la entrada.
    pd.testing.assert_frame_equal(en_1[COLUMNAS_ENTRADA], en_medio[COLUMNAS_ENTRADA])
    assert (en_1["r"] != en_medio["r"]).any()


def test_sin_breakeven_la_r_del_reglamento_no_cambia_nada(reg):
    # Así está hoy el reglamento para M1: `mover_a_entrada: false`. Ahí `en_r` no se usa.
    hoy = _m1(reg, {})
    otra_r = _m1(reg, {"riesgo.gestion.mover_a_entrada_en_r": 0.5})
    assert not hoy.empty
    pd.testing.assert_frame_equal(hoy, otra_r)


def test_gestion_simulada_es_la_misma_regla_para_los_dos_generadores(reg):
    r = reg.copia_con({"riesgo.gestion.mover_a_entrada_en_r": 1.5})
    gest, en_r = B.gestion_simulada(ESTRATEGIAS["M1"], r.estrategias["M1"], r, {"n": 20})
    assert en_r == 1.5 and gest == {**ESTRATEGIAS["M1"].gestion({"n": 20}), "sin_breakeven": True}
    gest, _ = B.gestion_simulada(ESTRATEGIAS["E1"], {"mover_a_entrada": True}, r, {"chandelier_atr": 3.0},
                                 {"modo": "canal", "canal_velas": 27})
    assert gest == {"modo": "canal", "chandelier_atr": 3.0, "canal_velas": 27}
