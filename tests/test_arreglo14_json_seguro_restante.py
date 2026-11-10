"""Arreglo 14: las lecturas/escrituras de JSON que faltaban usan las funciones seguras; si el archivo y su .bak están
dañados se muestra un mensaje claro (sin traceback)."""
import json

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    return r


def test_reanudar_con_estado_danado_sin_bak(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / "papel" / "cartera_A.json").write_text("{dañado", encoding="utf-8")
    assert CR.reanudar(r, "A", "OK de Ángelo") == 1
    salida = capsys.readouterr().out
    assert "❌ No se puede reanudar: El archivo cartera_A.json está dañado" in salida
    assert "Traceback" not in salida
    assert AR.leer_registro(r)[-1]["ok"] is False


def test_reanudar_con_estado_danado_usa_el_bak(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    arch = tmp_path / "datos" / "papel" / "cartera_A.json"
    AR.escribir_json_seguro(arch, {"cartera": "A", "detenido": False, "curva": {}, "capital_inicial": 46.18})
    AR.escribir_json_seguro(arch, {"cartera": "A", "detenido": False, "curva": {}, "capital_inicial": 46.18, "x": 1})
    arch.write_text("{dañado", encoding="utf-8")
    assert CR.reanudar(r, "A", "ok") == 0
    assert "no estaba detenida" in capsys.readouterr().out


def test_verificar_con_boletos_danados(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text("[{roto", encoding="utf-8")
    assert CR.verificar_boletos(r, "2026-11-09") == 1
    salida = capsys.readouterr().out
    assert "boletos_2026-11-09.json está dañado" in salida and "Traceback" not in salida


def test_conciliar_escribe_seguro_y_avisa_si_un_estado_esta_danado(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    assert CR.conciliar(r) == 0
    assert CR.conciliar(r) == 0
    assert (tmp_path / "datos" / "papel" / "conciliacion.json.bak").exists()      # escrito con copia anterior
    (tmp_path / "datos" / "papel" / "cartera_B.json").write_text("{dañado", encoding="utf-8")
    capsys.readouterr()
    assert CR.conciliar(r) == 1
    assert "cartera_B.json está dañado" in capsys.readouterr().out
    assert json.loads((tmp_path / "datos" / "papel" / "conciliacion.json").read_text(encoding="utf-8"))["ok"] is True
