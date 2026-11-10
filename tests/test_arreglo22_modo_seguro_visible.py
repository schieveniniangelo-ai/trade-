"""Arreglo 22: si la ronda quedó en MODO SEGURO, el resumen lo dice arriba y no da 👍."""
import json
from datetime import datetime, timedelta, timezone

from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def test_veto_a_5_dias_pone_modo_seguro_y_quita_el_pulgar(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    vence = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(timespec="seconds")
    (tmp_path / "datos" / "vetos.json").write_text(
        json.dumps({"vetos": [{"simbolo": "GLOBAL", "razon": "por si acaso", "vence": vence}]}), encoding="utf-8")
    out = P.ronda(r, _datos_dia(r, k)[0])
    assert out["modo_seguro"]
    texto = P.resumen_corto(out)
    assert "👍" not in texto
    lineas = texto.splitlines()
    assert lineas[1].startswith("⚠️ MODO SEGURO: hoy no se compra (") and "vetos.json" in lineas[1]
    assert len(lineas) <= 10


def test_sin_modo_seguro_no_aparece(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    texto = P.resumen_corto(P.ronda(r, _datos_dia(r, k)[0]))
    assert "MODO SEGURO" not in texto and "👍" in texto
