"""Arreglo 167: el papel falla cerrado si falta la conciliación.

Antes, sin datos/papel/conciliacion.json, `papel.conciliacion_ok` daba True. Ahora da False (como el real), salvo el
primer día después de `reiniciar-papel`: mientras ninguna cartera tenga una ronda de un día ANTERIOR al que se procesa,
no hay nada que conciliar y la primera ronda compra normal (las tres carteras: que A guarde la ronda de hoy no bloquea a
B ni a C). El mensaje dice qué falta y qué comando corre el CONTADOR. Una cartera dañada cuenta como que sí hubo rondas.
"""
import json

import pandas as pd
import pytest

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P
from sobreviviente import python_actual

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

DIA = pd.Timedelta(days=1)


@pytest.fixture
def mundo(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    return r, dd, tmp_path / "datos" / "papel"


def _con_rondas_de_ayer(r, dd):
    """Las tres carteras ya corrieron ayer (como cualquier día normal), sin posiciones."""
    ayer = (dd.dia - DIA).strftime("%Y-%m-%d")
    for n in P.CARTERAS:
        P.guardar_estado(r, {**P.estado_nuevo(n, 46.18, "2026-01-01"), "ultimo_dia": ayer, "rondas": {ayer: {}}})


def _compras(out):
    return [(n, b["simbolo"]) for n, c in out["carteras"].items() for b in c["boletos"] if b["accion"] == "COMPRAR"]


def test_primer_dia_sin_conciliacion_compran_las_tres_carteras(mundo):
    r, dd, carpeta = mundo
    assert P.estado_conciliacion(r, dd.dia.strftime("%Y-%m-%d")) == (True, "")
    out = P.ronda(r, dd)
    assert all(c["conciliacion_ok"] for c in out["carteras"].values())            # A no bloquea a B ni a C
    assert _compras(out) and not any("conciliación" in m for c in out["carteras"].values() for m in c["mensajes"])
    assert not (carpeta / "conciliacion.json").exists()


def test_sin_conciliacion_despues_de_una_ronda_no_compra_y_dice_que_falta(mundo):
    r, dd, _ = mundo
    _con_rondas_de_ayer(r, dd)
    ok, motivo = P.estado_conciliacion(r, dd.dia.strftime("%Y-%m-%d"))
    assert (ok, motivo) == (False, "falta") and P.conciliacion_ok(r) is False
    out = P.ronda(r, dd)
    assert not _compras(out) and not any(c["conciliacion_ok"] for c in out["carteras"].values())
    aviso = (f"⚠️ Falta la conciliación del papel (datos/papel/conciliacion.json): hoy no se abren posiciones nuevas. "
             f"CONTADOR: corre {python_actual()} -m sobreviviente conciliar.")
    assert all(aviso in c["mensajes"] for c in out["carteras"].values())
    texto = P.resumen_corto(out)
    assert texto.count("Falta la conciliación del papel") == 1 and "no cuadró" not in texto
    assert "CONTADOR debe correr conciliar" in texto and "👍" not in texto and len(texto.splitlines()) <= 10


def test_con_conciliacion_buena_vuelve_a_comprar(mundo, capsys):
    r, dd, carpeta = mundo
    _con_rondas_de_ayer(r, dd)
    assert CR.conciliar(r) == 0 and json.loads((carpeta / "conciliacion.json").read_text(encoding="utf-8"))["ok"]
    capsys.readouterr()
    out = P.ronda(r, dd)
    assert _compras(out) and all(c["conciliacion_ok"] for c in out["carteras"].values())


def test_no_cuadra_sigue_igual(mundo):
    r, dd, carpeta = mundo
    _con_rondas_de_ayer(r, dd)
    (carpeta / "conciliacion.json").write_text('{"ok": false}', encoding="utf-8")
    assert P.estado_conciliacion(r) == (False, "no cuadró")
    out = P.ronda(r, dd)
    assert not _compras(out)
    assert all(any("La conciliación no cuadró" in m for m in c["mensajes"]) for c in out["carteras"].values())
    texto = P.resumen_corto(out)
    assert "⚠️ La conciliación no cuadró: hoy no se compra." in texto and "Falta la conciliación" not in texto


def test_reiniciar_papel_deja_pasar_el_primer_dia(mundo, capsys):
    r, dd, carpeta = mundo
    _con_rondas_de_ayer(r, dd)
    (carpeta / "conciliacion.json").write_text('{"ok": true}', encoding="utf-8")
    assert CR.reiniciar_papel(r, si=True) == 0
    capsys.readouterr()
    assert not (carpeta / "conciliacion.json").exists()                 # se archivó con todo lo demás
    assert P.conciliacion_ok(r) is True                                 # primer día después de reiniciar
    assert _compras(P.ronda(r, dd))


def test_la_ronda_de_hoy_no_cuenta_como_ronda_anterior(mundo):
    r, dd, _ = mundo
    hoy = dd.dia.strftime("%Y-%m-%d")
    P.guardar_estado(r, {**P.estado_nuevo("A", 46.18, "2026-01-01"), "ultimo_dia": hoy, "rondas": {hoy: {}}})
    assert P.estado_conciliacion(r, hoy) == (True, "")                  # B y C corren después de A el mismo día
    assert P.estado_conciliacion(r) == (False, "falta")                 # sin día: cualquier ronda ya cuenta


def test_una_cartera_danada_cuenta_como_que_si_hubo_rondas(mundo):
    r, dd, carpeta = mundo
    carpeta.mkdir(parents=True)
    (carpeta / "cartera_B.json").write_text("{roto", encoding="utf-8")
    assert P.estado_conciliacion(r, dd.dia.strftime("%Y-%m-%d")) == (False, "falta")
    (carpeta / "cartera_B.json").write_text('["no es una cartera"]', encoding="utf-8")
    assert P.conciliacion_ok(r) is False


def test_sin_reglamento_no_estorba():
    assert P.conciliacion_ok(None) is True and P.estado_conciliacion(None) == (True, "")
