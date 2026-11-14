"""Arreglo 111: lo que la ronda anota sin hora medida queda «sin medir» (a_tiempo = null), como en el arreglo 89.

La ronda nueva mide su hora (OK = a tiempo; FUERA DE HORA o TEMPRANO = tarde) y eso no cambia. Pero la ronda
repetida («ya existía») y la repetida que no pudo leer lo guardado no tienen una hora que medir: antes caían en el
«a tiempo» por defecto de las tareas sin horario.
"""
import pandas as pd

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _filas_ronda(r):
    return [f for f in AR.leer_registro(r) if f["bot"] == "THE BOSS" and f["tarea"] == "ronda"]


def _preparar(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    return r, dd, (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()


def test_ronda_repetida_queda_sin_medir(reg, tmp_path, monkeypatch):
    r, dd, ahora = _preparar(reg, tmp_path, monkeypatch)
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    assert CR.correr_ronda(r, ahora=ahora + pd.Timedelta(minutes=30).to_pytimedelta(), cliente=object(), memes=[]) == 0
    nueva, repetida = _filas_ronda(r)
    assert nueva["a_tiempo"] is True                      # la ronda nueva sí midió su hora (OK)
    assert repetida["detalle"] == "ya existía" and repetida["a_tiempo"] is None


def test_ronda_repetida_con_archivo_danado_queda_sin_medir(reg, tmp_path, monkeypatch, capsys):
    r, dd, ahora = _preparar(reg, tmp_path, monkeypatch)
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    arch = tmp_path / "datos" / "papel" / "referencias.json"
    arch.write_text("{roto", encoding="utf-8")
    bak = arch.with_name(arch.name + ".bak")
    if bak.exists():
        bak.unlink()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 1
    assert "❌" in capsys.readouterr().out
    ultima = _filas_ronda(r)[-1]
    assert ultima["ok"] is False and ultima["a_tiempo"] is None


def test_ronda_caida_mide_su_hora(reg, tmp_path, monkeypatch):
    """La ronda que truena sí tenía hora medida: queda a tiempo si no era FUERA DE HORA."""
    r, dd, ahora = _preparar(reg, tmp_path, monkeypatch)

    def truena(*a, **kw):
        raise RuntimeError("sin red")
    monkeypatch.setattr(P, "preparar_datos", truena)
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 1
    fila = _filas_ronda(r)[-1]
    assert fila["ok"] is False and fila["a_tiempo"] is True
    tarde = ahora + pd.Timedelta(hours=5).to_pytimedelta()
    assert CR.correr_ronda(r, ahora=tarde, cliente=object(), memes=[]) == 1
    assert _filas_ronda(r)[-1]["a_tiempo"] is False


def test_registrar_tarea_sin_medir_explicito(reg, tmp_path):
    from test_arreglo47_conciliar_ensayo_estado import _reg_tmp
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, "THE BOSS", "ronda", True, "x", medir=False)
    assert AR.leer_registro(r)[-1]["a_tiempo"] is None
    AR.registrar_tarea(r, "THE BOSS", "reanudar", True)          # las demás sin horario: como antes
    assert AR.leer_registro(r)[-1]["a_tiempo"] is True
