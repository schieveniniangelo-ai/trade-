"""Arreglo 32: un renglón de la bitácora con demasiados "[" anidados se salta como dañado (sin traceback)."""
import json

from sobreviviente import cli_ronda as CR

NL = chr(10)


def test_renglon_de_200000_corchetes_no_da_traceback(reg, tmp_path, capsys):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    (tmp_path / "datos" / "papel" / "bitacora_rondas.jsonl").write_text(
        "[" * 200000 + NL + json.dumps({"dia_procesado": "2026-11-09", "fuera_de_hora": True}) + NL, encoding="utf-8")
    fila, saltados = CR._ultima_bitacora(r, "2026-11-09")
    assert fila["fuera_de_hora"] is True and saltados == 1
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text("[]", encoding="utf-8")
    assert CR.verificar_boletos(r, "2026-11-09") == 0
    salida = capsys.readouterr().out
    assert "⚠️ bitacora_rondas.jsonl: 1 renglón(es) dañado(s) saltado(s)" in salida and "FUERA DE HORA" in salida
