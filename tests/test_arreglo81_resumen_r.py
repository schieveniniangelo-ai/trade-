"""Arreglo 81: `metricas.resumen_r` ya no da factor de ganancia infinito cuando no hubo ninguna ganancia.

Antes, sin pérdidas el factor salía infinito aunque tampoco hubiera ganancias (todas las operaciones en 0 R), y la
compuerta "factor de ganancia ≥ mínimo" de la validación pasaba con cero ganancia. Ahora sale 0.0, igual que sin
operaciones. Aquí también queda fija la convención del acierto: ganadora = r > 0, con r ya neto de comisión,
deslizamiento y funding; un empate exacto (r = 0) no es ganadora. Sin red y sin llaves."""
import math

import pytest

from sobreviviente import validacion as V
from sobreviviente.metricas import resumen_r


def test_sin_ganancias_ni_perdidas_el_factor_es_cero():
    m = resumen_r([0.0, 0.0, 0.0])
    assert m["factor_ganancia"] == 0.0
    assert m["pct_ganadoras"] == 0.0 and m["expectativa_r"] == 0.0


def test_la_compuerta_del_factor_no_pasa_con_cero_ganancia(reg):
    res = V.ResultadoValidacion("E1", "prueba", oos_r=resumen_r([0.0] * 150))
    ok, texto = V.compuertas(reg, res)["factor_ganancia"]
    assert not ok and "0.00" in texto


def test_sin_perdidas_y_con_ganancias_sigue_infinito():
    assert math.isinf(resumen_r([1.0, 0.5])["factor_ganancia"])


def test_convencion_del_acierto_y_del_empate():
    m = resumen_r([2.0, 0.0, -1.0])
    assert m["pct_ganadoras"] == pytest.approx(100 / 3)      # el empate no cuenta como ganadora
    assert m["perdida_prom_r"] == pytest.approx(-0.5)        # y entra en la pérdida promedio (r <= 0)
    assert m["factor_ganancia"] == pytest.approx(2.0)
    assert m["expectativa_r"] == pytest.approx(1 / 3)        # la expectativa no depende de cómo se cuente el empate
    assert m["racha_perdedora_max"] == 1                     # la racha solo cuenta pérdidas de verdad (r < 0)


def test_sin_operaciones():
    assert resumen_r([]) == {"operaciones": 0, "pct_ganadoras": 0.0, "expectativa_r": 0.0, "factor_ganancia": 0.0,
                             "ganancia_prom_r": 0.0, "perdida_prom_r": 0.0, "racha_perdedora_max": 0}
