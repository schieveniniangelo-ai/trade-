"""Arreglo 19: los vetos tienen límites (72 h, razón corta sin saltos ni enlaces) y un veto que frena todo se ve."""
import json
from datetime import datetime, timedelta, timezone

from sobreviviente import archivos as AR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

AHORA = datetime(2026, 11, 10, 0, 10, tzinfo=timezone.utc)


def _veto(**kw):
    base = {"simbolo": "GLOBAL", "razon": "hackeo grande en un exchange", "vence": (AHORA + timedelta(hours=24)).isoformat()}
    base.update(kw)
    return {"vetos": [base]}


def test_veto_global_a_5_dias_rechazado(reg):
    err = AR.validar_vetos(_veto(vence=(AHORA + timedelta(days=5)).isoformat()), reg, AHORA)
    assert err and "72 horas" in err[0]
    assert AR.validar_vetos(_veto(), reg, AHORA) == []                      # 24 h sí se vale


def test_razon_larga_saltos_y_enlaces_rechazados(reg):
    assert any("500 caracteres" in e for e in AR.validar_vetos(_veto(razon="x" * 500), reg, AHORA))
    assert any("saltos de línea" in e for e in AR.validar_vetos(_veto(razon="uno\ndos"), reg, AHORA))
    assert any("http" in e for e in AR.validar_vetos(_veto(nota="ver https://ejemplo.com"), reg, AHORA))


def _ronda_con_vetos(reg, tmp_path, vetos):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "datos" / "vetos.json").write_text(json.dumps(vetos), encoding="utf-8")
    return P.ronda(r, _datos_dia(r, k)[0])


def test_veto_global_de_24h_quita_el_pulgar(reg, tmp_path):
    vence = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")   # válido hoy (≤ 72 h)
    out = _ronda_con_vetos(reg, tmp_path, {"vetos": [{"simbolo": "GLOBAL", "razon": "hackeo grande", "vence": vence}]})
    assert not out["modo_seguro"]
    assert not [b for c in out["carteras"].values() for b in c["boletos"] if b["accion"] == "COMPRAR"]
    texto = P.resumen_corto(out)
    assert "Veto activo" in texto and "hackeo grande" in texto and "👍" not in texto


def test_veto_de_otra_moneda_no_cambia_nada(reg, tmp_path):
    vence = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")
    out = _ronda_con_vetos(reg, tmp_path, {"vetos": [{"simbolo": "SOLUSDT", "razon": "demanda", "vence": vence}]})
    assert [b for c in out["carteras"].values() for b in c["boletos"] if b["accion"] == "COMPRAR"]
    texto = P.resumen_corto(out)
    assert "Veto activo" not in texto and "👍" in texto


def test_razon_del_veto_llega_recortada_y_sin_saltos(reg, tmp_path):
    from sobreviviente import riesgo as R
    from sobreviviente.exchange import Filtros
    from conftest import hacer_cand, hacer_estado
    veto = [{"simbolo": "GLOBAL", "razon": "línea uno\nlínea dos " + "x" * 400, "vence": "2099-01-01T00:00:00+00:00"}]
    d = R.evaluar_candidato(reg, hacer_estado(), hacer_cand(), Filtros("SOLUSDT", 0.01, 0.001, 0.001, 5.0), AHORA, vetos=veto)
    assert not d.aprobada and "\n" not in d.razon and len(d.razon) <= len("vetada por Noticias: ") + 200
