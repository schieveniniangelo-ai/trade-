"""Arreglo 102: CLAUDE.md da los comandos con el Python del .venv e instala desde requirements.lock."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = ".venv\\Scripts\\python.exe"


def _texto() -> str:
    return (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")


def _comandos() -> str:
    texto = _texto()
    inicio = texto.index("## Comandos")
    return texto[inicio:texto.index("\n## ", inicio + 1)]


def test_cada_comando_usa_el_python_del_venv():
    seccion = _comandos()
    for m in re.finditer(r"(\S+) -m (pytest|pip|sobreviviente)\b", seccion):
        assert m.group(1) == PY, m.group(0)
    assert not re.search(r"(?<![\w.\\-])(pytest|pip install|python -m)\b", re.sub(re.escape(PY) + r" -m \w+", "", seccion))


def test_instala_desde_el_lock():
    assert f"{PY} -m pip install -r requirements.lock" in _comandos()


def test_el_flujo_de_un_arreglo_tambien_usa_el_venv():
    flujo = _texto()[_texto().index("## Flujo de un arreglo"):]
    assert f"{PY} -m pytest --cov=sobreviviente" in flujo


def test_dice_cuantas_pruebas_pasan_en_linux_y_en_windows():
    regla = next(x for x in _texto().splitlines() if x.startswith("* No borres ni aflojes pruebas."))
    assert re.search(r"En [0-9a-f]{7} pasan \d+ pruebas en Linux", regla)
    assert re.search(r"\d+ en Windows con 1 saltada", regla) and "tests/test_arreglo43_respaldo.py" in regla
