"""Arreglo 28: la bitácora de rondas aguanta renglones dañados (los salta y avisa) y nunca pega dos filas."""
import json

from sobreviviente import cli_ronda as CR

NL = chr(10)


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    return r


def _bit(tmp_path):
    return tmp_path / "datos" / "papel" / "bitacora_rondas.jsonl"


def _fila(dia, **kw):
    return json.dumps({"dia_procesado": dia, **kw})


def test_renglon_roto_en_medio_avisa_y_conserva_el_resto(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    _bit(tmp_path).write_text(NL.join([_fila("2026-11-08"), "{roto", _fila("2026-11-09", fuera_de_hora=True)]) + NL,
                              encoding="utf-8")
    fila, saltados = CR._ultima_bitacora(r, "2026-11-09")
    assert fila["fuera_de_hora"] is True and saltados == 1
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text("[]", encoding="utf-8")
    assert CR.verificar_boletos(r, "2026-11-09") == 0
    salida = capsys.readouterr().out
    assert "⚠️ bitacora_rondas.jsonl: 1 renglón(es) dañado(s) saltado(s)" in salida and "FUERA DE HORA" in salida


def test_fila_cortada_al_final_y_fila_nueva(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _bit(tmp_path).write_text(_fila("2026-11-08") + NL + '{"dia_procesado": "2026-11-0', encoding="utf-8")   # se cortó
    CR._guardar_bitacora(r, {"dia_procesado": "2026-11-09", "modo_seguro": True})
    fila, saltados = CR._ultima_bitacora(r, "2026-11-09")
    assert fila == {"dia_procesado": "2026-11-09", "modo_seguro": True}     # la nueva NO quedó pegada a la cortada
    assert saltados == 1                                                      # la cortada se salta y se cuenta


def test_byte_invalido_lee_el_resto(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    crudo = (_fila("2026-11-08").encode() + NL.encode() + bytes([0xFF, 0xFE, 0x81]) + NL.encode()
             + _fila("2026-11-09", modo_seguro=False).encode() + NL.encode())
    _bit(tmp_path).write_bytes(crudo)
    fila, saltados = CR._ultima_bitacora(r, "2026-11-09")
    assert fila["modo_seguro"] is False and saltados == 1


def test_renglon_que_no_es_objeto_sin_traceback(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _bit(tmp_path).write_text(NL.join(["123", "[1, 2]", '"texto"', _fila("2026-11-09")]) + NL, encoding="utf-8")
    fila, saltados = CR._ultima_bitacora(r, "2026-11-09")
    assert fila == {"dia_procesado": "2026-11-09"} and saltados == 3


def test_guardar_en_archivo_sano_no_agrega_renglones_vacios(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    CR._guardar_bitacora(r, {"dia_procesado": "2026-11-08"})
    CR._guardar_bitacora(r, {"dia_procesado": "2026-11-09"})
    renglones = [x for x in _bit(tmp_path).read_text(encoding="utf-8").splitlines()]
    assert len(renglones) == 2 and all(renglones)
