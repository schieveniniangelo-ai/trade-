"""Arreglo 49: ningún comando termina con un error técnico sin avisar (red de seguridad en `main`)."""
import json
import shutil
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_ronda as CR

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def reglamento_tmp(tmp_path):
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")       # así "datos/" queda en la carpeta temporal
    return str(tmp_path / "reglamento.yaml")


def test_los_comandos_normales_siguen_igual(reglamento_tmp, tmp_path, capsys):
    assert MAIN.main(["--reglamento", reglamento_tmp, "estado"]) == 0
    assert "Cartera A: 46.18 USDT" in capsys.readouterr().out
    assert MAIN.main(["--reglamento", reglamento_tmp, "conciliar"]) == 0
    assert "👍 Las cuentas cuadran." in capsys.readouterr().out
    assert not (tmp_path / "datos" / "bots" / "errores.log").exists()


def test_comando_que_truena_avisa_anota_y_regresa_1(reglamento_tmp, tmp_path, monkeypatch, capsys):
    def tronar(*a, **kw):
        raise KeyError("curva")

    monkeypatch.setattr(CR, "mostrar_estado", tronar)
    assert MAIN.main(["--reglamento", reglamento_tmp, "estado"]) == 1
    salida = capsys.readouterr().out
    assert salida.startswith("❌ El comando 'estado' falló y NO terminó: KeyError: 'curva'")
    assert "avisa a THE BOSS" in salida and "Traceback" not in salida
    fila = json.loads((tmp_path / "datos" / "bots" / "registro.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert fila["bot"] == "THE BOSS" and fila["tarea"] == "comando estado" and fila["ok"] is False
    detalle = (tmp_path / "datos" / "bots" / "errores.log").read_text(encoding="utf-8")
    assert "comando estado" in detalle and "Traceback" in detalle and "KeyError" in detalle


def test_si_tampoco_se_puede_anotar_el_aviso_sale_igual(tmp_path, monkeypatch, capsys):
    def tronar(args):
        raise RuntimeError("algo raro")

    monkeypatch.setattr(CR, "cmd_estado", tronar)
    monkeypatch.setattr(MAIN.RGL, "cargar", lambda ruta=None: (_ for _ in ()).throw(OSError("sin disco")))
    import argparse
    assert MAIN._comando_caido(argparse.Namespace(comando="estado", reglamento=None), RuntimeError("algo raro")) == 1
    assert "❌ El comando 'estado' falló y NO terminó: RuntimeError: algo raro" in capsys.readouterr().out
