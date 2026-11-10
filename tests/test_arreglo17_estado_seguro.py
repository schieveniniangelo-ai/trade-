"""Arreglo 17: estado, registrar-llenado y el tipo de cambio del reporte con archivo dañado → "❌ …" y código 1."""
from argparse import Namespace

from sobreviviente import cli_ronda as CR


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    return r


def test_estado_con_cartera_danada(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / "papel" / "cartera_B.json").write_text("{dañado", encoding="utf-8")
    assert CR.mostrar_estado(r) == 1
    salida = capsys.readouterr().out
    assert "❌ El archivo cartera_B.json está dañado" in salida and "Traceback" not in salida


def test_estado_normal(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    assert CR.mostrar_estado(r) == 0
    assert "Cartera A" in capsys.readouterr().out


def test_registrar_llenado_con_boletos_danados(reg, tmp_path, monkeypatch, capsys):
    r = _reg_tmp(reg, tmp_path)
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    monkeypatch.setattr(CR, "RAIZ", tmp_path)
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text("[{roto", encoding="utf-8")
    args = Namespace(boleto="20261109-C-COM-BTC-abc", ensayo=True, simbolo=None, cantidad=None, precio=None, stop=None,
                     bot="EJECUTOR", reglamento=None)
    assert CR.cmd_registrar_llenado(args) == 1
    assert "❌ El archivo boletos_2026-11-09.json está dañado" in capsys.readouterr().out


def test_reporte_semanal_con_tipo_de_cambio_danado(reg, tmp_path, monkeypatch, capsys):
    r = _reg_tmp(reg, tmp_path)
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    (tmp_path / "datos" / "tipo_cambio.json").write_text("{dañado", encoding="utf-8")
    assert CR.cmd_reporte(Namespace(tipo="semanal", reglamento=None)) == 1
    salida = capsys.readouterr().out
    assert "❌" in salida and "tipo_cambio.json está dañado" in salida
