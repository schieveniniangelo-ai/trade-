"""Arreglo 27: repetir el mismo día una ronda que quedó en MODO SEGURO lo sigue diciendo (sin 👍)."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def test_ronda_repetida_en_modo_seguro(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    vence = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(timespec="seconds")   # veto inválido → modo seguro
    (tmp_path / "datos" / "vetos.json").write_text(
        json.dumps({"vetos": [{"simbolo": "GLOBAL", "razon": "x", "vence": vence}]}), encoding="utf-8")
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    capsys.readouterr()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0     # misma ronda, otra vez
    salida = capsys.readouterr().out
    assert "ya corrió" in salida
    assert "MODO SEGURO" in salida and "👍" not in salida
