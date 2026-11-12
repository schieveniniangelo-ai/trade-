"""Arreglo 98: las pruebas corren solas en GitHub en cada push a codex/marea-v2, con requirements.lock."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = RAIZ / ".github" / "workflows" / "pruebas.yml"


def _flujo() -> dict:
    datos = yaml.safe_load(FLUJO.read_text(encoding="utf-8"))
    datos["on"] = datos.pop(True, datos.get("on"))                 # YAML 1.1 lee la llave `on` como True
    return datos


def _pasos() -> list[dict]:
    return _flujo()["jobs"]["pytest"]["steps"]


def test_corre_en_cada_push_a_la_rama_de_marea():
    assert _flujo()["on"] == {"push": {"branches": ["codex/marea-v2"]}}


def test_instala_desde_el_lock_y_corre_pytest_completo():
    comandos = [p["run"] for p in _pasos() if "run" in p]
    assert comandos[0] == "python -m pip install -r requirements.lock"
    assert re.match(r"python -m pytest\b", comandos[1]) and "--cov=sobreviviente" in comandos[1]
    assert not re.search(r"\s(-k|-m|--deselect|--ignore)\b|tests/\S+\.py", comandos[1].split("pytest", 1)[1])   # nada se deja fuera


def test_misma_version_de_python_que_el_lock():
    version = [p["with"]["python-version"] for p in _pasos() if "setup-python" in p.get("uses", "")]
    cabecera = re.search(r"Python (\d+\.\d+)", (RAIZ / "requirements.lock").read_text(encoding="utf-8")).group(1)
    assert version == [cabecera]


def test_sin_secretos_ni_permisos_de_escritura():
    texto = FLUJO.read_text(encoding="utf-8")
    assert "secrets." not in texto and "BINANCE" not in texto.upper()
    assert _flujo()["permissions"] == {"contents": "read"}
