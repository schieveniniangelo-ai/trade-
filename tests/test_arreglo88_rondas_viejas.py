"""Arreglo 88 (B5): las rondas de más de 90 días pasan de cartera_X.json a rondas_viejas_X.json, sin borrar nada.

Nadie lee rondas de hace más de 90 días (solo la de hoy o la última), así que moverlas no cambia ningún resultado.
"""
import json

import pandas as pd

from sobreviviente import papel as P

from test_papel import _buscar_dia_con_compra, _datos_dia, _reg_papel

HACE = (200, 91, 90, 10)


def _preparar(reg, tmp_path, con_viejas=True):
    """Corre el día k y, si se pide, mete rondas falsas de hace 200, 91, 90 y 10 días (contadas desde el día k+1)."""
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    dd, _ = _datos_dia(r, k)
    P.ronda_cartera(r, "A", dd, [], [])
    dd2, _ = _datos_dia(r, k + 1)
    falsas = {}
    if con_viejas:
        est = P.cargar_estado(r, "A", "")
        for d in HACE:
            dia = (dd2.dia - pd.Timedelta(days=d)).strftime("%Y-%m-%d")
            falsas[dia] = {"dia": dia, "cartera": "A", "capital": 1000.0 + d, "mensajes": [f"hace {d} días"]}
        est["rondas"].update(falsas)
        P.guardar_estado(r, est)
    return r, dd2, falsas


def _dia(dd, hace):
    return (dd.dia - pd.Timedelta(days=hace)).strftime("%Y-%m-%d")


def _viejas(r, nombre="A"):
    return json.loads((P.ruta_papel(r) / f"rondas_viejas_{nombre}.json").read_text(encoding="utf-8"))


def test_las_rondas_de_mas_de_90_dias_pasan_a_otro_archivo(reg, tmp_path):
    r, dd, falsas = _preparar(reg, tmp_path)
    antes = dict(P.cargar_estado(r, "A", "")["rondas"])
    P.ronda_cartera(r, "A", dd, [], [])
    est = P.cargar_estado(r, "A", "")
    viejas = _viejas(r)
    assert set(viejas) == {_dia(dd, 200), _dia(dd, 91)}
    assert {_dia(dd, 90), _dia(dd, 10), dd.dia.strftime("%Y-%m-%d")} <= set(est["rondas"])
    assert not set(viejas) & set(est["rondas"])
    for dia, resumen in antes.items():                   # nada se perdió ni cambió
        assert (viejas.get(dia) or est["rondas"][dia]) == resumen


def test_archivar_otra_vez_no_duplica_ni_cambia(reg, tmp_path):
    r, dd, falsas = _preparar(reg, tmp_path)
    P.ronda_cartera(r, "A", dd, [], [])
    primera = _viejas(r)
    est = P.cargar_estado(r, "A", "")                    # como si se cortara la luz entre los dos pasos:
    est["rondas"].update(primera)                        # las rondas quedan en los dos archivos
    est["ultimo_dia"] = None
    del est["rondas"][dd.dia.strftime("%Y-%m-%d")]
    P.guardar_estado(r, est)
    P.ronda_cartera(r, "A", dd, [], [])
    assert _viejas(r) == primera
    assert not set(primera) & set(P.cargar_estado(r, "A", "")["rondas"])


def test_archivo_viejo_danado_no_tumba_la_ronda(reg, tmp_path):
    r, dd, falsas = _preparar(reg, tmp_path)
    (P.ruta_papel(r) / "rondas_viejas_A.json").write_text("{roto", encoding="utf-8")
    res = P.ronda_cartera(r, "A", dd, [], [])
    assert any("rondas_viejas_A.json" in m for m in res["mensajes"])
    est = P.cargar_estado(r, "A", "")
    assert set(falsas) <= set(est["rondas"])              # se quedan en la cartera
    assert (P.ruta_papel(r) / "rondas_viejas_A.json").read_text(encoding="utf-8") == "{roto"


def test_la_ronda_da_lo_mismo_con_o_sin_rondas_viejas(reg, tmp_path):
    r1, dd1, _ = _preparar(reg, tmp_path / "con")
    r2, dd2, _ = _preparar(reg, tmp_path / "sin", con_viejas=False)
    a = P.ronda_cartera(r1, "A", dd1, [], [])
    b = P.ronda_cartera(r2, "A", dd2, [], [])
    assert a == b
    e1, e2 = P.cargar_estado(r1, "A", ""), P.cargar_estado(r2, "A", "")
    for campo in ("efectivo", "posiciones", "cerradas", "curva", "saltadas_capital", "pico"):
        assert e1[campo] == e2[campo]
    assert not (P.ruta_papel(r2) / "rondas_viejas_A.json").exists()   # sin rondas viejas no se crea nada
