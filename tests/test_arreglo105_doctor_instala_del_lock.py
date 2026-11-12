"""Arreglo 105: cuando falta un paquete, `doctor` manda a instalar desde el mismo archivo que INSTALACION.md.

INSTALACION.md instala desde requirements.lock (Arreglo 97) y RADAR corre `doctor` a diario (Arreglo 103). Si el
aviso dijera otro archivo, el bot instalaría versiones distintas de las que pasan las pruebas. Sin red ni llaves.
"""
import importlib
import re
from pathlib import Path

import pytest

import sobreviviente
from sobreviviente import doctor

from test_arreglo48_doctor import _correr, _internet, _reg_tmp

RAIZ = Path(__file__).resolve().parent.parent


def _archivo_de_instalacion() -> str:
    texto = (RAIZ / "INSTALACION.md").read_text(encoding="utf-8")
    archivos = set(re.findall(r"-m pip install -r (\S+)", texto))
    assert len(archivos) == 1, archivos                          # un solo archivo para instalar
    return archivos.pop()


@pytest.mark.parametrize("paquete", ["pandas", "numpy", "yaml", "requests"])
def test_el_aviso_de_doctor_usa_el_archivo_de_instalacion(reg, tmp_path, monkeypatch, paquete):
    original = importlib.import_module

    def sin_paquete(nombre, *a, **kw):
        if nombre == paquete:
            raise ImportError(f"no hay {paquete}")
        return original(nombre, *a, **kw)

    monkeypatch.setattr(doctor.importlib, "import_module", sin_paquete)
    _internet(monkeypatch)
    codigo, texto = _correr(_reg_tmp(reg, tmp_path))
    archivo = _archivo_de_instalacion()
    assert archivo == "requirements.lock"
    assert codigo == 1 and f"❌ Falta el paquete {paquete}" in texto
    assert f"→ Corre: {sobreviviente.python_actual()} -m pip install -r {archivo}" in texto
    assert "requirements.txt" not in texto
