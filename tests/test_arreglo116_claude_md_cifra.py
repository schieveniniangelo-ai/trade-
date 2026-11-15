"""Arreglo 116: CLAUDE.md dice la cifra de pruebas de esta tanda (antes decía 746, la de f26c219).

En 7c0799f (arreglo 121) pasan 855 pruebas en Linux (GitHub, 0 saltadas) y 854 en Windows con 1 saltada (la de enlaces
simbólicos de tests/test_arreglo43_respaldo.py, que no se afloja). El formato lo fija test_arreglo102.
Arreglo 124: la cifra pasa a la de fe3aa8c (arreglo 123; el 124 no agrega pruebas): 862 en Linux y 861 más 1 saltada
en Windows.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_cifra_nueva():
    regla = next(x for x in (RAIZ / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
                 if x.startswith("* No borres ni aflojes pruebas."))
    assert "En fe3aa8c pasan 862 pruebas en Linux (GitHub, 0 saltadas) y 861 en Windows con 1 saltada" in regla
    assert "746" not in regla and "855" not in regla and "tests/test_arreglo43_respaldo.py; no la aflojes." in regla
