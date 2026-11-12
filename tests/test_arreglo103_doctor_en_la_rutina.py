"""Arreglo 103: el bot que arranca la rutina diaria (RADAR, 6:00 p. m.) corre primero `doctor`.

Si `doctor` no sale 👍, avisa a THE BOSS con el mensaje completo y la ronda se corre igual (tiene su MODO SEGURO).
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BOTS = RAIZ / "bots"
DOCTOR = ".venv\\Scripts\\python.exe -m sobreviviente doctor"
VERIFICAR = ".venv\\Scripts\\python.exe -m sobreviviente verificar"


def _texto(nombre: str) -> str:
    return (BOTS / nombre).read_text(encoding="utf-8")


def _seccion(texto: str, titulo: str) -> str:
    inicio = texto.index(titulo)
    fin = texto.find("\n## ", inicio + len(titulo))
    return texto[inicio:] if fin == -1 else texto[inicio:fin]


def _horario() -> list[list[str]]:
    filas = _seccion(_texto("MIGRACION.md"), "## Paso 4").splitlines()
    return [[c.strip() for c in f.strip().strip("|").split("|")] for f in filas if f.startswith("| ") and "---" not in f]


def test_radar_es_quien_arranca_la_rutina_diaria():
    horas = [f for f in _horario()[1:]]                        # sin el encabezado
    primera = horas[0]
    assert primera[0] == "6:00 p. m." and primera[1] == "RADAR"


def test_la_rutina_de_radar_empieza_con_doctor_y_despues_verificar():
    rutina = _seccion(_texto("1_RADAR.md"), "## Tu rutina diaria")
    pasos = re.findall(r"^(\d+)\. ", rutina, flags=re.M)
    assert pasos == [str(i) for i in range(1, len(pasos) + 1)]  # pasos numerados sin huecos
    paso1 = rutina[rutina.index("1. "):rutina.index("\n2. ")]
    assert DOCTOR in paso1 and VERIFICAR not in paso1
    assert rutina.index(DOCTOR) < rutina.index(VERIFICAR)
    assert "👍 Todo listo." in paso1                              # lo que imprime doctor cuando todo está bien
    assert "THE BOSS" in paso1 and "COMPLETO" in paso1           # si no sale 👍: el mensaje completo a THE BOSS
    assert "MODO SEGURO" in paso1 and "se corre igual" in paso1


def test_el_horario_de_migracion_pone_doctor_antes_de_verificar():
    radar = next(f for f in _horario() if f[1] == "RADAR")
    assert radar[2].index(DOCTOR) < radar[2].index(VERIFICAR)
    assert "THE BOSS" in radar[2] and "se corre igual" in radar[2]


def test_the_boss_corre_la_ronda_aunque_doctor_no_salga_bien():
    texto = _texto("THE_BOSS.md")
    rutina = _seccion(texto, "## Tu rutina diaria")
    paso1 = rutina[rutina.index("1. "):rutina.index("\n2. ")]
    assert "doctor" in paso1 and "MODO SEGURO" in paso1 and "aunque" in paso1
    radar = next(f for f in _seccion(texto, "## Qué espero de cada bot").splitlines() if f.startswith("| RADAR"))
    assert "doctor" in radar


def test_doctor_imprime_el_pulgar_que_esperan_los_bots():
    assert '"👍 Todo listo."' in (RAIZ / "sobreviviente" / "doctor.py").read_text(encoding="utf-8")
