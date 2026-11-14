"""Arreglo 114: en VALIDACION_RONDA2.md (y VALIDACION.md) el dato que falta dice «sin dato», no «—R» ni «— %».

En la ronda 2 la prueba final ya es una ventana del walk-forward: no hay rendimiento aparte de BTC ni de la
estrategia, y antes salía «En la prueba final BTC hizo — %». Los números que sí existen salen igual que antes.
"""
import re
from pathlib import Path

import pytest

from sobreviviente import informe, ronda2

from test_arreglo91_informes import (_refs_ronda2, _resultado, _resultados_informe, _resultados_ronda2,  # noqa: F401
                                     fecha_fija, sin_matplotlib)

RAIZ = Path(__file__).resolve().parent.parent
GUION = re.compile(r"—\s?(%|R\b)")


@pytest.mark.parametrize("x", [None, float("nan"), float("inf"), float("-inf")])
def test_fu_sin_dato(x):
    assert informe._fu(x, 1, True, u=" %") == "sin dato" and ronda2._fu(x, 3, u="R") == "sin dato"


def test_fu_con_dato_igual_que_antes():
    assert informe._fu(3.25, 1, True, u=" %") == informe._f(3.25, 1, True) + " %" == "+3.2 %"
    assert ronda2._fu(0.5, 3, True, u="R") == "+0.500R"
    assert informe._f(None) == "—"                       # _f sigue igual (celdas sin unidad)


def test_ronda2_prueba_final_sin_rendimiento(reg, tmp_path, sin_matplotlib, fecha_fija):
    a, b = _resultados_ronda2()
    a.btc = {"oos": {"rend_pct": 369.4, "caida_pct": 53.7}, "holdout": {"rend_pct": None}}   # como en la ronda 2 real
    a.holdout = {"operaciones": 7, "expectativa_r": 0.279, "factor_ganancia": 1.47}
    ruta = tmp_path / "R2.md"
    ronda2.escribir([a, b], _refs_ronda2(), reg, ruta)
    texto = ruta.read_text(encoding="utf-8")
    assert not GUION.search(texto)
    assert "En la prueba final BTC hizo sin dato." in texto
    assert "expectativa +0.279R, factor 1.47, rendimiento sin dato." in texto
    assert "BTC hizo +369.4 % con una caída de 53.7 %" in texto


def test_informe_ronda1_sin_guion_con_unidad(reg, tmp_path, sin_matplotlib, fecha_fija):
    ruta = tmp_path / "V.md"
    informe.escribir(_resultados_informe(), reg, ruta, [])
    assert not GUION.search(ruta.read_text(encoding="utf-8"))


def test_validacion_ronda2_del_repo_sin_guion():
    texto = (RAIZ / "VALIDACION_RONDA2.md").read_text(encoding="utf-8")
    assert not GUION.search(texto)
