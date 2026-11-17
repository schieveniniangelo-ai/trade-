"""Arreglo 154: el estado de papel de F1 (datos/papel_futuros/) no entra al repositorio."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _lineas() -> list[str]:
    return [x.strip() for x in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()]


def test_gitignore_ignora_papel_futuros_y_conserva_lo_demas():
    lineas = _lineas()
    assert "datos/papel_futuros/" in lineas
    for otra in ("datos/papel/", "datos/real/", "datos/estela/", "datos/bots/", ".env", "*.key"):
        assert otra in lineas, otra


def test_papel_futuros_va_en_el_bloque_del_estado_de_papel():
    lineas = _lineas()
    i = lineas.index("datos/papel_futuros/")
    assert lineas.index("datos/papel/") < i < lineas.index("datos/real/")

