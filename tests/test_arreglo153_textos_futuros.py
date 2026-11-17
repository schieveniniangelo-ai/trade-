"""Arreglo 153: textos y cifras de la tanda F1 (se hace ANTES del 152)."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LINEA_BOSS = "Futuros F1 es SOLO PAPEL con 42.54 USDT propios; nunca pases nada de futuros a EJECUTOR"


def _leer(nombre: str) -> str:
    return (RAIZ / nombre).read_text(encoding="utf-8")


def test_the_boss_tiene_la_linea_una_sola_vez():
    assert _leer("bots/THE_BOSS.md").count(LINEA_BOSS) == 1


def test_ejecutor_real_no_menciona_futuros_de_f1():
    texto = _leer("bots/4_EJECUTOR_REAL.md")
    # Su «Nunca Futuros» (con mayúscula) ya estaba y es una prohibición; aquí no puede aparecer F1 ni «futuros».
    assert "futuros" not in texto
    assert "F1" not in texto and "papel_futuros" not in texto and "futuros-papel" not in texto


def test_propuestas_seccion_n():
    texto = _leer("PROPUESTAS.md")
    assert "## N. Tanda Futuros F1 v2 (143–153)" in texto
    n = texto[texto.index("## N. Tanda Futuros F1 v2 (143–153)"):]
    for frase in ("DECISIÓN DE ÁNGELO 2026-11-16", "MECÁNICO por delegación de Ángelo 2026-11-16",
                  "| SOLUSDT | 71.63", "142.54", "domingo 22 nov", "VALIDACION_FUTUROS.md", "Veredicto: F1",
                  "real.py:89", "ronda_real.py:184-186"):
        assert frase in n, frase


def test_claude_md_dice_la_cifra_de_la_tanda_f1():
    regla = next(x for x in _leer("CLAUDE.md").splitlines() if x.startswith("* No borres ni aflojes pruebas."))
    assert "La tanda F1 (143–153) suma" in regla
    cob = next(x for x in _leer("CLAUDE.md").splitlines() if x.startswith("* La cobertura del paquete"))
    assert "89.7 %" in cob
