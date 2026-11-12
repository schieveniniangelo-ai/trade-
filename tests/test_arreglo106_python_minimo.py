"""Arreglo 106: el Python mínimo que piden INSTALACION.md, README.md y `doctor` es el que pide requirements.lock.

numpy 2.5.4 (fijo en requirements.lock desde el Arreglo 97) pide Python 3.12 o más nuevo, pero los textos y `doctor`
aceptaban 3.11: en una computadora con 3.11 la instalación fallaba y `doctor` decía que 3.11 bastaba. Sin red ni llaves.
"""
from __future__ import annotations

import re
from collections import namedtuple
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from sobreviviente import doctor

from test_arreglo48_doctor import _correr, _internet, _reg_tmp

RAIZ = Path(__file__).resolve().parent.parent
Version_info = namedtuple("Version_info", "major minor micro releaselevel serial")


def _lock() -> dict[str, str]:
    out = {}
    for linea in (RAIZ / "requirements.lock").read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if linea:
            nombre, version = linea.split("==")
            out[nombre] = version
    return out


def _minimo_del_lock() -> tuple[int, int]:
    """El Python 3.x más viejo que aceptan TODOS los paquetes del lock (leído de los paquetes instalados)."""
    reglas = []
    for nombre, version in _lock().items():
        try:
            instalado = metadata.version(nombre)
        except metadata.PackageNotFoundError:
            pytest.skip(f"{nombre} no está instalado: este entorno no salió de requirements.lock")
        if instalado != version:
            pytest.skip(f"{nombre} {instalado} en vez de {version}: este entorno no salió de requirements.lock")
        reglas.append(SpecifierSet(metadata.metadata(nombre).get("Requires-Python") or ""))
    menor = next(m for m in range(8, 30) if all(Version(f"3.{m}") in r for r in reglas))
    return 3, menor


def test_doctor_pide_el_minimo_del_lock():
    assert doctor.PYTHON_MINIMO == _minimo_del_lock() == (3, 12)


def test_instalacion_y_readme_dicen_el_mismo_minimo():
    mayor, menor = doctor.PYTHON_MINIMO
    instalacion = (RAIZ / "INSTALACION.md").read_text(encoding="utf-8")
    assert f"**Python {mayor}.{menor} o más nuevo**" in instalacion
    assert f"Python {mayor}.{menor}+" in (RAIZ / "README.md").read_text(encoding="utf-8")
    for texto in (instalacion, (RAIZ / "README.md").read_text(encoding="utf-8")):
        assert not re.search(r"Python 3\.11\b", texto)


@pytest.mark.parametrize("version,bien", [((3, 11, 9), False), ((3, 12, 0), True), ((3, 13, 1), True)])
def test_doctor_revisa_la_version(reg, tmp_path, monkeypatch, version, bien):
    monkeypatch.setattr(doctor, "sys", SimpleNamespace(version_info=Version_info(*version, "final", 0)))
    _internet(monkeypatch)
    codigo, texto = _correr(_reg_tmp(reg, tmp_path))
    linea = f"Python {version[0]}.{version[1]}.{version[2]}"
    if bien:
        assert codigo == 0 and f"✅ {linea}" in texto and "Instala Python" not in texto
    else:
        assert codigo == 1 and f"❌ {linea}\n     → Instala Python 3.12 o más nuevo." in texto
