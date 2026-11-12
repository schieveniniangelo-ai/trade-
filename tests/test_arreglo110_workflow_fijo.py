"""Arreglo 110: el workflow de pruebas fija la máquina y usa acciones de Node 24.

Hallazgo de la revisión del 12/11/2026: `ubuntu-latest` cambia sola de versión (GitHub avisó que pasa a Ubuntu 26) y
`actions/checkout@v4` y `actions/setup-python@v5` son de Node 20 (GitHub avisaba en cada corrida).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = RAIZ / ".github" / "workflows" / "pruebas.yml"


def _job() -> dict:
    return yaml.safe_load(FLUJO.read_text(encoding="utf-8"))["jobs"]["pytest"]


def test_la_maquina_es_una_version_fija():
    assert re.fullmatch(r"ubuntu-\d{2}\.\d{2}", _job()["runs-on"])


def test_acciones_de_node_24():
    usos = [p["uses"] for p in _job()["steps"] if "uses" in p]
    assert usos == ["actions/checkout@v7", "actions/setup-python@v7"]
