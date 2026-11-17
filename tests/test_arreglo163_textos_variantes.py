"""Arreglo 163: textos y cifras de la tanda F1 variantes (156–163).

CLAUDE.md dice la cifra REAL de pruebas: se cuenta aquí mismo con `pytest --collect-only -q` (en Windows se recolectan
las mismas; pasa una menos porque la de enlaces simbólicos de tests/test_arreglo43_respaldo.py se salta).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _leer(nombre: str) -> str:
    return (RAIZ / nombre).read_text(encoding="utf-8")


def _recolectadas() -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=RAIZ,
                       capture_output=True, text=True, timeout=600, check=False)
    m = re.search(r"(\d+) tests? collected", r.stdout)
    assert m, r.stdout[-2000:] + r.stderr[-2000:]
    return int(m.group(1))


def test_claude_md_menciona_la_cifra_que_da_pytest():
    n = _recolectadas()
    regla = next(x for x in _leer("CLAUDE.md").splitlines() if x.startswith("* No borres ni aflojes pruebas."))
    assert f"pasan {n} en Linux y {n - 1} en Windows con 1 saltada" in regla, (n, regla)
    assert "La tanda F1 variantes (156–163) suma" in regla
    assert "el 154 y el 155" in regla                            # la cifra de 143–153 ya no era la final
    # lo que piden las pruebas viejas sigue ahí
    assert "La tanda F1 (143–153) suma" in regla and "tests/test_arreglo43_respaldo.py; no la aflojes." in regla


def test_propuestas_seccion_o():
    texto = _leer("PROPUESTAS.md")
    assert "## O. Tanda F1 variantes (156–163)" in texto
    o = texto[texto.index("## O. Tanda F1 variantes (156–163)"):]
    for frase in ("99.17 %", "t ≥ 2.24", "4 pruebas", "TAREA DE ÁNGELO", "escalones", "domingo 22 nov",
                  "DECISIÓN DE ÁNGELO", "VALIDACION_FUTUROS_F1-L.md", "VALIDACION_FUTUROS_F1-LC.md",
                  "VALIDACION_FUTUROS_F1-LT.md", "VARIANTES_FUTUROS.md", "Nada de esto promete ganancias"):
        assert frase in o, frase
    for arreglo in ("156", "157", "158", "160", "161", "162", "163"):
        assert re.search(rf"\| {arreglo} \| `[0-9a-f]{{7}}`|\| {arreglo} \| este commit", o), arreglo
