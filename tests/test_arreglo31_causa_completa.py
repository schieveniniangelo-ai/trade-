"""Arreglo 31: la causa del MODO SEGURO llega hasta 160 caracteres; si aun así se corta, el aviso completo va abajo."""
import json
from datetime import datetime, timedelta, timezone

from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def test_modo_seguro_por_veto_a_5_dias_dice_centinela(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    vence = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(timespec="seconds")
    (tmp_path / "datos" / "vetos.json").write_text(
        json.dumps({"vetos": [{"simbolo": "GLOBAL", "razon": "hackeo grande", "vence": vence}]}), encoding="utf-8")
    texto = P.resumen_corto(P.ronda(r, _datos_dia(r, k)[0]))
    assert "MODO SEGURO" in texto and "CENTINELA" in texto
