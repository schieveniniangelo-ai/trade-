"""Arreglo 3: una ronda caída nunca pasa desapercibida."""
import json
from datetime import datetime, timezone

import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import diario as DI
from sobreviviente import papel as P

from test_v2 import diarias

A_TIEMPO = datetime(2026, 11, 10, 0, 10, tzinfo=timezone.utc)


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    return r


def _velas_sin_btc():
    velas = {s: diarias(400, semilla=i) for i, s in enumerate(["AUSDT", "BUSDT"])}
    for v in velas.values():
        v["quote_volume"] = 5e8
    return velas


def test_preparar_sin_btc_lanza_error_de_datos(reg):
    with pytest.raises(D.ErrorDatos, match="faltan velas de BTC"):
        DI.preparar(reg, _velas_sin_btc(), None, [], exchange_info={"symbols": []})


def test_ronda_sin_btc_regresa_1_y_registra_fallo(reg, tmp_path, monkeypatch, capsys):
    r = _reg_tmp(reg, tmp_path)

    def preparar_sin_btc(reg_, cli, memes, ahora=None, **kw):
        DI.preparar(reg_, _velas_sin_btc(), None, memes, exchange_info={"symbols": []})
    monkeypatch.setattr(P, "preparar_datos", preparar_sin_btc)
    assert CR.correr_ronda(r, ahora=A_TIEMPO, cliente=object(), memes=[]) == 1
    assert "❌ La ronda NO corrió: faltan velas de BTC" in capsys.readouterr().out
    ultima = AR.leer_registro(r)[-1]
    assert ultima["bot"] == "THE BOSS" and ultima["tarea"] == "ronda" and ultima["ok"] is False
    assert "BTC" in ultima["detalle"]
    assert not list((tmp_path / "salida").glob("boletos_*.json")) if (tmp_path / "salida").exists() else True


def test_ronda_con_cualquier_error_regresa_1(reg, tmp_path, monkeypatch, capsys):
    r = _reg_tmp(reg, tmp_path)

    def explota(*a, **k):
        raise KeyError("columna rara")
    monkeypatch.setattr(P, "preparar_datos", explota)
    assert CR.correr_ronda(r, ahora=A_TIEMPO, cliente=object(), memes=[]) == 1
    assert "La ronda NO corrió" in capsys.readouterr().out
    assert AR.leer_registro(r)[-1]["ok"] is False


def test_verificar_sin_archivo_de_boletos_regresa_1(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    assert CR.verificar_boletos(r, "2026-11-09") == 1
    assert "❌ NO HAY RONDA de 2026-11-09" in capsys.readouterr().out
    ultima = AR.leer_registro(r)[-1]
    assert ultima["bot"] == "EJECUTOR" and ultima["ok"] is False


def test_verificar_con_ronda_sin_boletos_dice_pulgar(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text(json.dumps([]), encoding="utf-8")
    assert CR.verificar_boletos(r, "2026-11-09") == 0
    salida = capsys.readouterr().out
    assert "👍" in salida and "hoy no hubo boletos" in salida
    assert AR.leer_registro(r)[-1]["ok"] is True
