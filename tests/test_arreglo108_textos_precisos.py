"""Arreglo 108: los textos de los bots dicen cuándo el MODO SEGURO protege la ronda y quién numera las hipótesis.

Hallazgos de la revisión del 12/11/2026: el MODO SEGURO cubre fallas de conexión, datos y archivos de los bots, pero
si a la computadora le falta un paquete, tiene un Python viejo o no deja escribir en datos/, la ronda truena. Y si
THE BOSS pone "el número que sigue" sin poder editar HIPOTESIS.md, dos propuestas pueden salir con el mismo número.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _plano(texto: str) -> str:
    return re.sub(r"\s+", " ", texto)


def _paso1(nombre: str) -> str:
    texto = (RAIZ / "bots" / nombre).read_text(encoding="utf-8")
    rutina = texto[texto.index("## Tu rutina diaria"):]
    return _plano(rutina[rutina.index("1. "):rutina.index("\n2. ")])


def test_the_boss_sabe_cuando_el_modo_seguro_no_alcanza():
    paso1 = _paso1("THE_BOSS.md")
    assert "Si el problema es de conexión, de datos o de los archivos de los bots" in paso1 and "MODO SEGURO" in paso1
    assert "falta un paquete, Python viejo o no se puede escribir en `datos/`" in paso1
    assert "la ronda va a tronar con ❌: no improvises" in paso1
    assert "mensaje de `doctor` que te mandó RADAR, completo" in paso1


def test_radar_y_migracion_no_prometen_de_mas():
    assert "si el problema es de datos, entra en MODO SEGURO; si es de la computadora, THE BOSS lo reporta" in \
        _paso1("1_RADAR.md")
    fila = next(x for x in (RAIZ / "bots" / "MIGRACION.md").read_text(encoding="utf-8").splitlines()
                if x.startswith("| 6:00 p. m. | RADAR |"))
    assert "entra en MODO SEGURO si el problema es de datos; si es de la computadora, truena con ❌" in fila


def test_las_hipotesis_las_numera_quien_las_registra():
    boss = _plano((RAIZ / "bots" / "THE_BOSS.md").read_text(encoding="utf-8"))
    assert "número (pon «por asignar»: lo pone Ángelo al registrarla" in boss
    assert "el que sigue en el archivo" not in boss
    assert "- **Número:** NNN (el que sigue; lo pone quien la registra en este archivo)" in \
        (RAIZ / "HIPOTESIS.md").read_text(encoding="utf-8")
