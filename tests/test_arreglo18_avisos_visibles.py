"""Arreglo 18: los avisos "⚠️" de cada cartera se ven en el resumen y en la salida de la ronda."""
import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _cantidad_diminuta(monkeypatch):
    original = P.R.evaluar_candidato

    def diminuta(reg_, estado, cand, filtros, *a, **kw):
        d = original(reg_, estado, cand, filtros, *a, **kw)
        if d.aprobada:
            d.cantidad = filtros.paso / 10
        return d
    monkeypatch.setattr(P.R, "evaluar_candidato", diminuta)


def test_aviso_de_cantidad_minima_se_ve_en_pantalla(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    _cantidad_diminuta(monkeypatch)
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    salida = capsys.readouterr().out
    assert "cantidad menor que el mínimo de Binance, no se compra" in salida
    assert "BTCUSDT" in salida


def test_resumen_incluye_los_avisos_de_las_carteras(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    _cantidad_diminuta(monkeypatch)
    out = P.ronda(r, _datos_dia(r, k)[0])
    texto = P.resumen_corto(out)
    assert "⚠️ Cartera" in texto and "cantidad menor que el mínimo de Binance" in texto
    assert len(texto.splitlines()) <= 10
