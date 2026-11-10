"""Arreglo 2: la ronda revisa la hora real contra `ronda.hora_utc` (00:10 UTC = 6:10 p. m. CDMX)."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

CDMX = ZoneInfo("America/Mexico_City")


def _utc(h, m):
    return datetime(2026, 11, 10, h, m, tzinfo=timezone.utc)


def test_revisar_hora(reg):
    assert CR.revisar_hora(reg, _utc(0, 3))["estado"] == "TEMPRANO"
    assert CR.revisar_hora(reg, _utc(0, 7))["estado"] == "OK"          # 3 minutos antes de la hora: se vale
    assert CR.revisar_hora(reg, _utc(0, 10))["estado"] == "OK"
    assert CR.revisar_hora(reg, _utc(2, 10))["estado"] == "OK"         # 120 minutos justos
    assert CR.revisar_hora(reg, _utc(2, 11))["estado"] == "FUERA_DE_HORA"
    # El caso real: la primera ronda corrió a las 23:04 de CDMX (05:04 UTC): 294 minutos tarde
    h = CR.revisar_hora(reg, datetime(2026, 11, 9, 23, 4, tzinfo=CDMX))
    assert h["estado"] == "FUERA_DE_HORA" and h["retraso_min"] == 294


def test_revisar_hora_lee_el_reglamento(reg):
    r = reg.copia_con({"ronda.hora_utc": "01:00"})
    assert CR.revisar_hora(r, _utc(2, 59))["estado"] == "OK"
    assert CR.revisar_hora(r, _utc(3, 1))["estado"] == "FUERA_DE_HORA"


def _preparar_con(dd):
    def falso(reg, cli, memes, ahora=None, **kw):
        return dd
    return falso


def test_ronda_fuera_de_hora_no_compra(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", _preparar_con(dd))
    ahora = (dd.dia + pd.Timedelta(days=1, hours=5, minutes=4)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    salida = capsys.readouterr().out
    assert "FUERA DE HORA" in salida
    boletos = json.loads((tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json").read_text(encoding="utf-8"))
    assert not [b for b in boletos if b["accion"] == "COMPRAR"]
    bit = [json.loads(x) for x in (tmp_path / "datos" / "papel" / "bitacora_rondas.jsonl").read_text(encoding="utf-8").splitlines()]
    assert bit[-1]["fuera_de_hora"] is True and bit[-1]["dia_procesado"] == f"{dd.dia:%Y-%m-%d}"
    assert bit[-1]["hora_real_utc"].startswith(f"{dd.dia + pd.Timedelta(days=1):%Y-%m-%d}T05:04")
    assert "duracion_s" in bit[-1]
    reg_bots = AR.leer_registro(r)
    assert "fuera_de_hora" in reg_bots[-1]["detalle"] and reg_bots[-1]["a_tiempo"] is False


def test_ronda_a_tiempo_si_compra_y_guarda_bitacora(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", _preparar_con(dd))
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    boletos = json.loads((tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json").read_text(encoding="utf-8"))
    assert [b for b in boletos if b["accion"] == "COMPRAR"]          # la Cartera C sí compra
    bit = json.loads((tmp_path / "datos" / "papel" / "bitacora_rondas.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert bit["fuera_de_hora"] is False


def test_ronda_temprano_se_niega(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)

    def no_llamar(*a, **k):
        raise AssertionError("no debe bajar datos")
    monkeypatch.setattr(P, "preparar_datos", no_llamar)
    assert CR.correr_ronda(r, ahora=_utc(0, 2), cliente=object(), memes=[]) == 1
    assert not (tmp_path / "datos" / "papel").exists()
    assert AR.leer_registro(r)[-1]["ok"] is False
