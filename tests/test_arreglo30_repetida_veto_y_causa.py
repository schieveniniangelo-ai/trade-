"""Arreglo 30: la ronda repetida el mismo día muestra el veto (⚠️ o ℹ️) y la causa real del MODO SEGURO."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _repetir(reg, tmp_path, monkeypatch, capsys, horas_veto: int, motores_encendidos: bool = True) -> str:
    r = _reg_m0(reg, tmp_path)
    if not motores_encendidos:
        r.datos["estrategias"]["M0"]["estado"] = "APAGADA"      # día sin señal: el veto no cambia nada
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    vence = (datetime.now(timezone.utc) + timedelta(hours=horas_veto)).isoformat(timespec="seconds")
    (tmp_path / "datos" / "vetos.json").write_text(
        json.dumps({"vetos": [{"simbolo": "GLOBAL", "razon": "hackeo grande", "vence": vence}]}), encoding="utf-8")
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    capsys.readouterr()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0     # misma ronda, otra vez
    salida = capsys.readouterr().out
    assert "ya corrió" in salida
    return salida


def test_repetida_con_veto_que_frena_compras(reg, tmp_path, monkeypatch, capsys):
    salida = _repetir(reg, tmp_path, monkeypatch, capsys, horas_veto=24)
    assert "⚠️ Veto activo de Noticias: hoy no se compra (hackeo grande" in salida
    assert "👍" not in salida


def test_repetida_con_veto_informativo(reg, tmp_path, monkeypatch, capsys):
    salida = _repetir(reg, tmp_path, monkeypatch, capsys, horas_veto=24, motores_encendidos=False)
    assert "ℹ️ Veto activo de Noticias hasta" in salida and "hackeo grande" in salida
    assert "👍 No necesito nada de ti." in salida


def test_repetida_en_modo_seguro_dice_la_causa_real(reg, tmp_path, monkeypatch, capsys):
    salida = _repetir(reg, tmp_path, monkeypatch, capsys, horas_veto=24 * 5)    # veto a 5 días → MODO SEGURO
    assert "⚠️ MODO SEGURO: hoy no se compra (vetos.json viene mal" in salida
    assert "sus avisos están en la bitácora" not in salida and "👍" not in salida
