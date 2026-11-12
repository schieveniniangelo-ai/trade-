"""Arreglo 96: los avisos del programa dicen el Python que sí tiene los paquetes (el del .venv), no `python`.

Un bot que copie un aviso al pie de la letra («corre …», «Usa: …», la ayuda) usaba el `python` del sistema, que no
tiene pandas. `python_actual()` da el Python que está corriendo el programa, listo para copiar. Sin red ni llaves.
"""
import importlib
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

import sobreviviente
from sobreviviente import __main__ as MAIN
from sobreviviente import cli_ronda as CR
from sobreviviente import doctor
from sobreviviente import reglamento
from sobreviviente import respaldo as RESP

from test_arreglo48_doctor import _correr, _internet, _reg_tmp

RAIZ = Path(__file__).resolve().parent.parent
VENV_WINDOWS = RAIZ / ".venv" / "Scripts" / "python.exe"


def test_dentro_del_proyecto_da_la_ruta_relativa_del_venv(monkeypatch):
    monkeypatch.setattr(sys, "executable", str(VENV_WINDOWS))
    assert sobreviviente.python_actual() == str(Path(".venv", "Scripts", "python.exe"))
    monkeypatch.setattr(sys, "executable", str(RAIZ / ".venv" / "bin" / "python"))       # Linux o Mac
    assert sobreviviente.python_actual() == str(Path(".venv", "bin", "python"))


def test_fuera_del_proyecto_da_la_ruta_completa_y_con_espacios_entre_comillas(monkeypatch, tmp_path):
    otro = tmp_path / "python3"
    monkeypatch.setattr(sys, "executable", str(otro))
    assert sobreviviente.python_actual() == (f'"{otro}"' if " " in str(otro) else str(otro))
    con_espacios = tmp_path / "Program Files" / "python.exe"
    monkeypatch.setattr(sys, "executable", str(con_espacios))
    assert sobreviviente.python_actual() == f'"{con_espacios}"'
    monkeypatch.setattr(sys, "executable", "")
    assert sobreviviente.python_actual() == "python"


def test_el_aviso_de_respaldo_dice_el_python_del_venv(monkeypatch):
    monkeypatch.setattr(sys, "executable", str(VENV_WINDOWS))
    venv = str(Path(".venv", "Scripts", "python.exe"))
    assert RESP.aviso_sin_respaldo(reglamento.cargar()) == [
        f"ℹ️ Sin respaldo de datos todavía: corre '{venv} -m sobreviviente respaldo'"]


def test_doctor_dice_como_instalar_en_el_mismo_python(reg, tmp_path, monkeypatch):
    original = importlib.import_module

    def sin_yaml(nombre, *a, **kw):
        if nombre == "yaml":
            raise ImportError("no hay yaml")
        return original(nombre, *a, **kw)

    monkeypatch.setattr(doctor.importlib, "import_module", sin_yaml)
    _internet(monkeypatch)
    codigo, texto = _correr(_reg_tmp(reg, tmp_path))
    assert codigo == 1 and "❌ Falta el paquete yaml" in texto
    assert f"→ Corre: {sobreviviente.python_actual()} -m pip install -r requirements.txt" in texto


def test_estela_sin_foto_dice_el_comando_completo(tmp_path, capsys):
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")
    assert CR.cmd_estela(Namespace(foto=False, reglamento=str(tmp_path / "reglamento.yaml"))) == 2
    assert capsys.readouterr().out.strip() == f"Usa: {sobreviviente.python_actual()} -m sobreviviente estela --foto"


def test_la_ayuda_dice_el_comando_completo(capsys):
    with pytest.raises(SystemExit) as fin:
        MAIN.main(["--help"])
    assert fin.value.code == 0
    assert capsys.readouterr().out.startswith(f"usage: {sobreviviente.python_actual()} -m sobreviviente")
