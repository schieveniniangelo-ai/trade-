"""Arreglo 97: dependencias fijas en requirements.lock y la instalación sale de ese archivo."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _paquetes(archivo: str) -> dict[str, str]:
    """{nombre normalizado: resto de la línea} de un archivo de requisitos (sin comentarios ni vacías)."""
    out = {}
    for linea in (RAIZ / archivo).read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        nombre = re.split(r"[<>=!~\[; ]", linea, maxsplit=1)[0]
        out[re.sub(r"[-_.]+", "-", nombre).lower()] = linea[len(nombre):]
    return out


def test_cada_paquete_del_lock_tiene_version_exacta():
    lock = _paquetes("requirements.lock")
    assert lock, "requirements.lock está vacío"
    for nombre, resto in lock.items():
        assert re.fullmatch(r"==[0-9][0-9A-Za-z.+!-]*", resto), f"{nombre} no tiene versión exacta: {resto!r}"


def test_el_lock_cubre_todo_lo_que_piden_las_pruebas_y_el_programa():
    lock = _paquetes("requirements.lock")
    faltan = [p for p in _paquetes("requirements.txt") if p not in lock]
    assert not faltan, f"requirements.lock no trae: {faltan}"
    assert "pytest-cov" in lock                                   # la cobertura también se mide con versiones fijas


def test_instalacion_instala_desde_el_lock():
    texto = (RAIZ / "INSTALACION.md").read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python.exe -m pip install -r requirements.lock" in texto
    assert "pip install -r requirements.txt" not in texto
