"""Arreglo 94: el programa escribe en UTF-8 aunque la salida esté en otra codificación.

En Windows, cuando la salida no va a una ventana sino a otro programa (un bot que la lee, un log), Python usa cp1252,
que no tiene ✅ ❌ 👍 ni →: los comandos tronaban con UnicodeEncodeError (hasta el aviso ❌ de la red de seguridad).
Aquí se reproduce en cualquier sistema forzando PYTHONIOENCODING=cp1252. Sin red ni llaves: el reglamento se copia
a una carpeta temporal, así que todo lo que el comando escriba queda ahí.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _correr(tmp_path, *args):
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")
    entorno = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    entorno.update({"PYTHONIOENCODING": "cp1252", "HOME": str(tmp_path / "casa"), "USERPROFILE": str(tmp_path / "casa")})
    p = subprocess.run([sys.executable, "-m", "sobreviviente", "--reglamento", str(tmp_path / "reglamento.yaml"), *args],
                       cwd=RAIZ, env=entorno, capture_output=True, timeout=120)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def test_conciliar_con_la_salida_en_cp1252_ya_no_truena(tmp_path):
    codigo, salida, errores = _correr(tmp_path, "conciliar")
    assert codigo == 0, errores[-800:]
    assert "👍 Las cuentas cuadran." in salida and "✅ Cartera A" in salida
    assert "UnicodeEncodeError" not in errores


def test_main_pasa_a_utf8_una_salida_en_cp1252_en_el_mismo_proceso(tmp_path, monkeypatch):
    import io
    from sobreviviente import __main__ as MAIN
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")
    crudo = io.BytesIO()
    salida = io.TextIOWrapper(crudo, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", salida)
    assert MAIN.main(["--reglamento", str(tmp_path / "reglamento.yaml"), "conciliar"]) == 0
    salida.flush()
    assert salida.encoding == "utf-8" and "👍 Las cuentas cuadran." in crudo.getvalue().decode("utf-8")


def test_la_ayuda_con_la_salida_en_cp1252_ya_no_truena(tmp_path):
    codigo, salida, errores = _correr(tmp_path, "--help")
    assert codigo == 0, errores[-800:]
    assert "→" in salida and "UnicodeEncodeError" not in errores
