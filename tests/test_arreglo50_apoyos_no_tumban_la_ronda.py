"""Arreglo 50: los archivos de apoyo (referencias, grandes, bitácora, registro) no tumban la ronda ni fallan callados."""
import json

import pandas as pd

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _ronda_completa(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    return r, dd, ahora


def test_referencias_danado_no_tumba_la_ronda_y_se_avisa(reg, tmp_path, monkeypatch, capsys):
    r, dd, ahora = _ronda_completa(reg, tmp_path, monkeypatch)
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    hist = tmp_path / "datos" / "papel" / "referencias.json"
    hist.write_text("{dañado", encoding="utf-8")
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    salida = capsys.readouterr().out
    assert "La ronda NO corrió" not in salida
    assert "⚠️ No se guardó la comparación de hoy en referencias.json" in salida
    assert "Boletos para el EJECUTOR" in salida                               # los boletos sí salieron
    boletos = json.loads((tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json").read_text(encoding="utf-8"))
    assert [b for b in boletos if b["accion"] == "COMPRAR"]
    assert hist.read_text(encoding="utf-8") == "{dañado"                       # el archivo dañado no se pisa


def test_referencias_con_formato_raro_tambien_se_avisa(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    (tmp_path / "datos" / "papel" / "referencias.json").write_text("[1, 2, 3]", encoding="utf-8")
    out = P.ronda(r, _datos_dia(r, k)[0])
    assert any("No se guardó la comparación de hoy en referencias.json" in a for a in out["avisos"])
    assert out["modo_seguro"] is False


def test_error_al_calcular_referencias_se_dice(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    monkeypatch.setattr(P, "referencias_papel", lambda *a, **kw: {"error": "faltan velas de BTC"})
    out = P.ronda(r, _datos_dia(r, k)[0])
    assert any(a.startswith("No se pudieron calcular las referencias de comparación") and "faltan velas de BTC" in a
               for a in out["avisos"])
    texto = P.resumen_corto(out)
    assert "⚠️ No se pudieron calcular las referencias" in texto and "MODO SEGURO" not in texto


def test_el_archivo_de_boletos_es_lo_ultimo_que_se_escribe(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    orden = []
    original = AR.escribir_json_seguro

    def espia(ruta, datos, **kw):
        orden.append(ruta.name)
        return original(ruta, datos, **kw)

    monkeypatch.setattr(AR, "escribir_json_seguro", espia)
    P.ronda(r, _datos_dia(r, k)[0])
    assert orden[-1].startswith("boletos_") and "referencias.json" in orden[:-1]


def test_bitacora_que_no_se_puede_escribir_no_tumba_la_ronda(reg, tmp_path, monkeypatch, capsys):
    r, dd, ahora = _ronda_completa(reg, tmp_path, monkeypatch)

    def sin_permiso(reg_, fila):
        raise PermissionError("solo lectura")

    monkeypatch.setattr(CR, "_guardar_bitacora", sin_permiso)
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    salida = capsys.readouterr().out
    assert "⚠️ No pude escribir la bitácora de rondas (PermissionError)" in salida
    assert "Ronda del " in salida and "Boletos para el EJECUTOR" in salida


def test_registrar_tarea_no_tumba_si_no_puede_escribir(reg, tmp_path, capsys):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "bots").write_text("soy un archivo, no una carpeta", encoding="utf-8")
    AR.registrar_tarea(r, "RADAR", "verificar", True)                           # no truena
    assert "⚠️ No pude anotar la tarea 'verificar' de RADAR en registro.jsonl" in capsys.readouterr().out
    assert AR.leer_registro(r) == []
