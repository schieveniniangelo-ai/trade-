"""Arreglo 23: cada error de un veto dice de qué veto se trata (moneda y vence) y pide a CENTINELA corregirlo."""
from datetime import datetime, timedelta, timezone

from sobreviviente import archivos as AR

AHORA = datetime(2026, 11, 10, 0, 10, tzinfo=timezone.utc)


def test_mensaje_dice_moneda_vence_y_que_hacer(reg):
    err = AR.validar_vetos({"vetos": [{"simbolo": "GLOBAL", "razon": "x", "vence": "2099-01-01T00:00:00+00:00"}]}, reg, AHORA)
    assert len(err) == 1
    assert err[0].startswith("veto #1 (GLOBAL, vence 2099-01-01T00:00:00+00:00): vence en más de 72 horas")
    assert err[0].endswith("pide a CENTINELA que lo corrija")


def test_varios_errores_todos_identificados(reg):
    vence = (AHORA + timedelta(hours=10)).isoformat()
    vetos = {"vetos": [{"simbolo": "SOLUSDT", "razon": "bien", "vence": vence},
                       {"simbolo": "?", "razon": "uno" + chr(10) + "dos", "vence": vence}]}
    err = AR.validar_vetos(vetos, reg, AHORA)
    assert err and all(m.startswith(f"veto #2 (?, vence {vence})") for m in err)
    assert all(m.endswith("pide a CENTINELA que lo corrija") for m in err)
    assert any("símbolo" in m for m in err) and any("saltos de línea" in m for m in err)
