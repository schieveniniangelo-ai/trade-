"""Arreglo 101: las pruebas de GitHub dejan su resultado a la vista sin iniciar sesión.

GitHub pide iniciar sesión (con permisos de administrador) para leer los logs; los avisos del workflow (annotations)
se ven en la página del run y en la API pública. El último paso publica el resumen de pytest y la cobertura como aviso.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = RAIZ / ".github" / "workflows" / "pruebas.yml"

SALIDA_PYTEST = """\
sobreviviente/validacion_v2.py            369      4    99%
-----------------------------------------------------------
TOTAL                                    7236    917    87%

======================= 2 failed, 740 passed in 351.20s (0:05:51) =======================
"""


def _bash() -> str | None:
    """Un bash que sí corre (en Windows, `bash` puede ser el lanzador de WSL sin distribución)."""
    b = shutil.which("bash")
    if b is None:
        return None
    try:
        r = subprocess.run([b, "-c", "echo ok"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return b if r.stdout.strip() == "ok" else None


BASH = _bash()


def _pasos() -> list[dict]:
    return yaml.safe_load(FLUJO.read_text(encoding="utf-8"))["jobs"]["pytest"]["steps"]


def _paso(nombre: str) -> dict:
    return next(p for p in _pasos() if p.get("name") == nombre)


def test_pytest_guarda_su_salida_sin_esconder_una_falla():
    paso = _paso("pytest completo con cobertura del paquete")
    assert paso["shell"] == "bash"                     # GitHub corre `shell: bash` con pipefail: si pytest falla, el paso falla
    assert paso["run"].endswith("| tee pytest-salida.txt")


def test_el_ultimo_paso_publica_el_resultado_aunque_falle_pytest():
    paso = _pasos()[-1]
    assert paso["name"] == "Resultado a la vista" and paso["if"] == "always()" and paso["shell"] == "bash"
    assert "::notice title=pytest::" in paso["run"] and "pytest-salida.txt" in paso["run"]


@pytest.mark.skipif(BASH is None, reason="hace falta bash para correr el paso como en GitHub")
def test_el_aviso_dice_el_resumen_y_la_cobertura(tmp_path):
    (tmp_path / "pytest-salida.txt").write_text(SALIDA_PYTEST, encoding="utf-8")
    r = subprocess.run([BASH, "-eo", "pipefail", "-c", _pasos()[-1]["run"]], cwd=tmp_path, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ("::notice title=pytest::2 failed, 740 passed in 351.20s (0:05:51); "
                                "cobertura del paquete 87.33 % (7236 sentencias, 917 sin cubrir)")


@pytest.mark.skipif(BASH is None, reason="hace falta bash para correr el paso como en GitHub")
def test_sin_salida_de_pytest_el_aviso_lo_dice(tmp_path):
    (tmp_path / "pytest-salida.txt").write_text("", encoding="utf-8")
    r = subprocess.run([BASH, "-eo", "pipefail", "-c", _pasos()[-1]["run"]], cwd=tmp_path, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert re.fullmatch(r"::notice title=pytest::sin resumen; cobertura del paquete sin dato\s*", r.stdout)
