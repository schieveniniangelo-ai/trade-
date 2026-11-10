"""Arreglo 10: si la ronda corrió fuera de hora, `ronda --verificar` lo dice y no da 👍."""
import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _correr(reg, tmp_path, monkeypatch, horas_tarde):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10) + pd.Timedelta(hours=horas_tarde)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    return r, f"{dd.dia:%Y-%m-%d}", ahora


def test_ronda_fuera_de_hora_verificar_no_da_pulgar(reg, tmp_path, monkeypatch, capsys):
    r, fecha, ahora = _correr(reg, tmp_path, monkeypatch, horas_tarde=5)
    capsys.readouterr()
    assert CR.verificar_boletos(r, fecha, ahora=ahora) == 0
    salida = capsys.readouterr().out
    assert f"⚠️ La ronda del {fecha} corrió FUERA DE HORA (sin compras)" in salida
    assert "👍" not in salida


def test_ronda_a_tiempo_sin_boletos_si_da_pulgar(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path)
    r.datos["estrategias"]["M0"]["estado"] = "APAGADA"          # nada encendido: ronda a tiempo y sin boletos
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    capsys.readouterr()
    assert CR.verificar_boletos(r, f"{dd.dia:%Y-%m-%d}", ahora=ahora) == 0
    salida = capsys.readouterr().out
    assert "👍" in salida and "FUERA DE HORA" not in salida
