"""Arreglo 194 (R103): un `vence_utc` sin zona horaria no truena con TypeError: COMPRA_ENVIADA responde «NO mandes».

`_por_que_no_mandar` (arreglo 182) comparaba la hora UTC de ahora con `datetime.fromisoformat(vence_utc)`. Si el boleto
traía el vencimiento sin la Z ni +00:00 (por ejemplo, editado a mano), Python no puede comparar una hora con zona y otra
sin zona: TypeError, y registrar-llenado se caía en lugar de decir qué hacer. Ahora sale ❌ «NO mandes la compra» y no se
anota nada."""
import copy
import json
from datetime import timedelta

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture


def _sin_zona(r, b):
    b = copy.deepcopy(b)
    b["vence_utc"] = b["vence_utc"].removesuffix("Z")             # 2026-11-16T02:10:00, sin zona
    RR.archivo_boletos(r, "2026-11-15").write_text(json.dumps([b]), encoding="utf-8")
    return b


def test_por_que_no_mandar_no_truena(compra):
    _, b, _ = compra
    b = {**b, "vence_utc": "2026-11-16T02:10:00"}
    assert RE._por_que_no_mandar(b, 70000.0, AHORA) == (
        "el vencimiento del boleto (2026-11-16T02:10:00) no dice su zona horaria (le falta la Z o el +00:00): no se puede "
        "revisar si ya venció")


@pytest.mark.parametrize("vence", ["2026-11-16T02:10:00Z", "2026-11-16T02:10:00+00:00", "2026-11-15T20:10:00-06:00"])
def test_con_zona_sigue_igual(compra, vence):
    _, b, _ = compra
    assert RE._por_que_no_mandar({**b, "vence_utc": vence}, 70000.0, AHORA) == ""
    assert RE._por_que_no_mandar({**b, "vence_utc": vence}, 70000.0, AHORA + timedelta(hours=3)).startswith(
        "el boleto venció")


def test_compra_enviada_dice_no_mandes_y_no_anota(compra):
    r, b, _ = compra
    b = _sin_zona(r, b)
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                    precio_actual=70000.0)
    assert not ok and msgs == ["NO mandes la compra: el vencimiento del boleto (2026-11-16T02:10:00) no dice su zona "
                               "horaria (le falta la Z o el +00:00): no se puede revisar si ya venció. No se anotó nada. "
                               "Avisa a THE BOSS con este mensaje."]
    assert RE.leer_llenados(r) == []


def test_por_la_linea_de_comandos(compra, monkeypatch, capsys):
    r, b, _ = compra
    b = _sin_zona(r, b)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(RE, "ahora_utc", lambda: AHORA + timedelta(minutes=1))
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_ENVIADA",
                      "--precio-actual", "70000"]) == 1
    assert capsys.readouterr().out.startswith("❌ NO mandes la compra: el vencimiento del boleto")
