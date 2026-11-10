"""Arreglo 24: un veto GLOBAL o de BTC vigente que hoy no frenó compras se informa (ℹ️) sin quitar el 👍."""
import json
from datetime import datetime, timedelta, timezone

from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _ronda(reg, tmp_path, motores_encendidos: bool):
    r = _reg_m0(reg, tmp_path)
    if not motores_encendidos:
        r.datos["estrategias"]["M0"]["estado"] = "APAGADA"      # día sin señal
    k = _dia_marea_alta(r)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    vence = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")
    (tmp_path / "datos" / "vetos.json").write_text(
        json.dumps({"vetos": [{"simbolo": "GLOBAL", "razon": "hackeo grande", "vence": vence}]}), encoding="utf-8")
    return P.ronda(r, _datos_dia(r, k)[0])


def test_veto_sin_senal_se_informa_y_hay_pulgar(reg, tmp_path):
    out = _ronda(reg, tmp_path, motores_encendidos=False)
    texto = P.resumen_corto(out)
    assert "ℹ️ Veto activo de Noticias hasta" in texto and "hackeo grande" in texto and "hoy no cambió nada" in texto
    assert "👍" in texto


def test_veto_que_si_frena_sigue_sin_pulgar(reg, tmp_path):
    texto = P.resumen_corto(_ronda(reg, tmp_path, motores_encendidos=True))
    assert "⚠️ Veto activo de Noticias: hoy no se compra" in texto and "ℹ️" not in texto and "👍" not in texto
