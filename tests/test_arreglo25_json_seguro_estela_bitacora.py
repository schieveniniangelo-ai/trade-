"""Arreglo 25: fotos de ESTELA con lectura segura y bitácora de rondas que no se puede leer → "❌ …" y código 1."""
import json

import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import estela as ES


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    return r


class _Cli:
    def __init__(self, carpeta):
        self.cache = carpeta / "cache"


def test_foto_de_estela_danada_sin_copia_da_error_claro(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / "estela").mkdir(parents=True)
    (tmp_path / "datos" / "estela" / "2026-11-09.json").write_text("{dañado", encoding="utf-8")
    with pytest.raises(AR.ArchivoDanado, match="2026-11-09.json está dañado"):
        ES.serie_masa(r, _Cli(tmp_path), "BTCUSDT")


def test_foto_de_estela_danada_usa_su_copia(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    arch = tmp_path / "datos" / "estela" / "2026-11-09.json"
    foto = {"fecha": "2026-11-09", "simbolos": {"BTCUSDT": {"top_posiciones": 1.9, "masa_cuentas": 3.0}}}
    AR.escribir_json_seguro(arch, foto)
    AR.escribir_json_seguro(arch, foto)
    arch.write_text("{dañado", encoding="utf-8")
    s = ES.serie_masa(r, _Cli(tmp_path), "BTCUSDT")
    assert s.iloc[-1] == pytest.approx(0.75)                   # 3 / (1 + 3)


def test_verificar_con_bitacora_de_bytes_invalidos(reg, tmp_path, capsys):
    # Arreglo 28: ya no es un error; el renglón con bytes inválidos se salta y se avisa
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text("[]", encoding="utf-8")
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    (tmp_path / "datos" / "papel" / "bitacora_rondas.jsonl").write_bytes(bytes([0xFF, 0xFE, 0x00, 0x81]))
    assert CR.verificar_boletos(r, "2026-11-09") == 0
    salida = capsys.readouterr().out
    assert "⚠️ bitacora_rondas.jsonl: 1 renglón(es) dañado(s) saltado(s)" in salida and "Traceback" not in salida


def test_bitacora_con_un_renglon_roto_sigue_funcionando(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text("[]", encoding="utf-8")
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    filas = ["{roto", json.dumps({"dia_procesado": "2026-11-09", "fuera_de_hora": True})]
    (tmp_path / "datos" / "papel" / "bitacora_rondas.jsonl").write_text(chr(10).join(filas), encoding="utf-8")
    assert CR.verificar_boletos(r, "2026-11-09") == 0
    assert "FUERA DE HORA" in capsys.readouterr().out
