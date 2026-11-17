"""Arreglo 169: la conciliación del papel tiene que ser de hoy o de ayer (hora de CDMX) y decir ok.

Antes `papel.estado_conciliacion` leía `.get("ok", True)`: un conciliacion.json sin "ok" contaba como bueno y un ok viejo
servía para siempre. Ahora:
* sin "ok" (o con algo que no sea true) → "no dice ok" (falla cerrado);
* con ok, la `fecha` (la escribe `conciliar` en UTC) pasada a hora de CDMX tiene que ser de hoy o de ayer; si no trae
  fecha, es rara, no dice su zona horaria, es más vieja o es del futuro → "vieja" (falla cerrado);
* ok:false sigue siendo "no cuadró"; si falta el archivo, todo sigue como en el arreglo 167 (con su excepción del primer
  día después de `reiniciar-papel`).
El mensaje dice qué falta y qué comando corre el CONTADOR; el resumen lo dice una vez y sin 👍.
"""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P
from sobreviviente import python_actual

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

DIA = pd.Timedelta(days=1)
AHORA = datetime(2026, 11, 18, 0, 10, tzinfo=timezone.utc)      # 6:10 p. m. CDMX del martes 17 nov
COMANDO = f"CONTADOR: corre {python_actual()} -m sobreviviente conciliar."


@pytest.fixture
def mundo(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    carpeta = tmp_path / "datos" / "papel"
    carpeta.mkdir(parents=True, exist_ok=True)
    return r, dd, carpeta


def _escribir(carpeta, **datos):
    (carpeta / "conciliacion.json").write_text(json.dumps(datos), encoding="utf-8")


def _con_rondas_de_ayer(r, dd):
    ayer = (dd.dia - DIA).strftime("%Y-%m-%d")
    for n in P.CARTERAS:
        P.guardar_estado(r, {**P.estado_nuevo(n, 46.18, "2026-01-01"), "ultimo_dia": ayer, "rondas": {ayer: {}}})


def _compras(out):
    return [(n, b["simbolo"]) for n, c in out["carteras"].items() for b in c["boletos"] if b["accion"] == "COMPRAR"]


@pytest.mark.parametrize("fecha, esperado", [
    ("2026-11-18T00:05:00+00:00", (True, "")),          # hoy, 6:05 p. m. CDMX (la de hace un rato)
    ("2026-11-17T00:30:00+00:00", (True, "")),          # ayer, 6:30 p. m. CDMX (la del CONTADOR de ayer)
    ("2026-11-16T06:00:00+00:00", (True, "")),          # ayer a las 00:00 CDMX en punto
    ("2026-11-17T05:59:00Z", (True, "")),               # ayer 11:59 p. m. CDMX (con Z)
    ("2026-11-16T05:30:00+00:00", (False, "vieja")),    # en UTC es del 16, pero en CDMX es del 15 a las 11:30 p. m.
    ("2026-11-15T00:30:00+00:00", (False, "vieja")),    # antier en CDMX
    ("2026-10-01T00:30:00+00:00", (False, "vieja")),    # un ok viejo ya no sirve para siempre
])
def test_solo_sirve_la_de_hoy_o_la_de_ayer_en_hora_de_cdmx(mundo, fecha, esperado):
    r, _, carpeta = mundo
    _escribir(carpeta, fecha=fecha, ok=True)
    assert P.estado_conciliacion(r, ahora=AHORA) == esperado
    assert P.conciliacion_ok(r, ahora=AHORA) is esperado[0]


@pytest.mark.parametrize("datos", [
    {"ok": True},                                                     # sin fecha
    {"ok": True, "fecha": None},
    {"ok": True, "fecha": 1763340000},
    {"ok": True, "fecha": "ayer"},
    {"ok": True, "fecha": "2026-11-17T18:00:00"},                     # sin zona horaria: no se adivina
    {"ok": True, "fecha": "2026-11-19T00:30:00+00:00"},               # del futuro (18 nov en CDMX)
])
def test_sin_fecha_rara_sin_zona_o_del_futuro_cuenta_como_vieja(mundo, datos):
    r, _, carpeta = mundo
    _escribir(carpeta, **datos)
    assert P.estado_conciliacion(r, ahora=AHORA) == (False, "vieja")


@pytest.mark.parametrize("datos", [
    {"fecha": "2026-11-18T00:05:00+00:00"},                           # sin "ok": antes contaba como bueno
    {"fecha": "2026-11-18T00:05:00+00:00", "ok": None},
    {"fecha": "2026-11-18T00:05:00+00:00", "ok": "true"},
    {"fecha": "2026-11-18T00:05:00+00:00", "ok": 1},
])
def test_sin_ok_no_cuenta_como_buena(mundo, datos):
    r, _, carpeta = mundo
    _escribir(carpeta, **datos)
    assert P.estado_conciliacion(r, ahora=AHORA) == (False, "no dice ok")
    assert P.conciliacion_ok(r, ahora=AHORA) is False


def test_ok_false_sigue_saliendo_no_cuadro_aunque_sea_vieja(mundo):
    r, _, carpeta = mundo
    _escribir(carpeta, fecha="2026-10-01T00:30:00+00:00", ok=False)
    assert P.estado_conciliacion(r, ahora=AHORA) == (False, "no cuadró")
    _escribir(carpeta, fecha="2026-11-18T00:05:00+00:00", ok=False)
    assert P.estado_conciliacion(r, ahora=AHORA) == (False, "no cuadró")


def test_los_avisos_dicen_que_falta_y_que_comando_corre_el_contador(mundo):
    r, _, carpeta = mundo
    _escribir(carpeta, fecha="2026-11-15T00:30:00+00:00", ok=True)
    assert P.aviso_conciliacion(r, "vieja") == (
        "⚠️ Falta la conciliación del papel de hoy o de ayer (hora de CDMX): la de datos/papel/conciliacion.json es del "
        f"2026-11-14. Hoy no se abren posiciones nuevas. {COMANDO}")
    _escribir(carpeta, ok=True)
    assert "datos/papel/conciliacion.json no trae fecha" in P.aviso_conciliacion(r, "vieja")
    assert P.aviso_conciliacion(r, "no dice ok") == (
        '⚠️ Falta la conciliación del papel: datos/papel/conciliacion.json no dice "ok". Hoy no se abren posiciones '
        f"nuevas. {COMANDO}")
    assert P.aviso_conciliacion(r, "falta") == P.aviso_falta_conciliacion()      # el del 167, igualito


@pytest.mark.parametrize("datos, pedazo", [
    ({"ok": True, "fecha": "2026-01-01T00:30:00+00:00"}, "es del 2025-12-31"),
    ({"fecha": "2026-01-01T00:30:00+00:00"}, 'no dice "ok"'),
])
def test_la_ronda_con_conciliacion_vieja_o_sin_ok_no_compra_y_lo_dice_una_vez(mundo, datos, pedazo):
    r, dd, carpeta = mundo
    _con_rondas_de_ayer(r, dd)
    _escribir(carpeta, **datos)
    out = P.ronda(r, dd)
    assert not _compras(out) and not any(c["conciliacion_ok"] for c in out["carteras"].values())
    for c in out["carteras"].values():
        avisos = [m for m in c["mensajes"] if m.startswith("⚠️") and "conciliación" in m]
        assert len(avisos) == 1 and pedazo in avisos[0] and avisos[0].endswith(COMANDO)
    texto = P.resumen_corto(out)
    assert texto.count("Falta la conciliación del papel") == 1 and "CONTADOR debe correr conciliar" in texto
    assert "no cuadró" not in texto and "👍" not in texto and len(texto.splitlines()) <= 10


def test_un_conciliar_recien_corrido_si_deja_comprar(mundo, capsys):
    r, dd, carpeta = mundo
    _con_rondas_de_ayer(r, dd)
    assert CR.conciliar(r) == 0
    capsys.readouterr()
    guardado = json.loads((carpeta / "conciliacion.json").read_text(encoding="utf-8"))
    assert guardado["ok"] is True and datetime.fromisoformat(guardado["fecha"]).tzinfo is not None
    assert P.estado_conciliacion(r, dd.dia.strftime("%Y-%m-%d")) == (True, "")
    # Ese mismo archivo, dos días después, ya no sirve
    assert P.estado_conciliacion(r, ahora=datetime.now(timezone.utc) + timedelta(days=2)) == (False, "vieja")
    assert _compras(P.ronda(r, dd))


def test_reiniciar_papel_sigue_dejando_pasar_el_primer_dia_aunque_la_vieja_estuviera(mundo, capsys):
    r, dd, carpeta = mundo
    _con_rondas_de_ayer(r, dd)
    _escribir(carpeta, fecha="2026-10-01T00:30:00+00:00", ok=True)
    assert P.conciliacion_ok(r) is False
    assert CR.reiniciar_papel(r, si=True) == 0
    capsys.readouterr()
    assert not (carpeta / "conciliacion.json").exists()
    assert P.estado_conciliacion(r, dd.dia.strftime("%Y-%m-%d")) == (True, "")     # excepción del 167, igual
    assert _compras(P.ronda(r, dd))
