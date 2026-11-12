"""Arreglo 109: CLAUDE.md pide el mismo Python mínimo que doctor y requirements.lock (3.12; autorizado por Ángelo)."""
from __future__ import annotations

import re
from pathlib import Path

from sobreviviente import doctor

RAIZ = Path(__file__).resolve().parent.parent


def test_claude_md_dice_el_python_minimo_de_doctor():
    texto = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
    mayor, menor = doctor.PYTHON_MINIMO
    assert f"Python {mayor}.{menor}+" in texto.splitlines()[2]                 # la línea que describe el proyecto
    assert not re.search(r"Python 3\.(?:[0-9]|1[01])\+", texto)                # ninguna versión menor
