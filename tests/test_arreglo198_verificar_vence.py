"""Arreglo 198: `ronda --verificar --real` revisa `vence_utc` igual que el arreglo 194, sin tronar con TypeError.

Antes, un boleto real con `vence_utc` sin zona horaria (sin la Z ni +00:00) hacía que la comparación con la hora UTC
tronara (TypeError) y la revisión decía «boleto mal formado (TypeError)». Ahora, sin zona o con una fecha rara, dice
«boleto vencido o sin fecha válida: no lo pongas»; con zona, igual que antes."""
import copy
import json
from datetime import timedelta

import pytest

from sobreviviente import cli_real
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import Cli, compra  # noqa: F401 - fixture


def _con_vence(r, b, vence):
    b = copy.deepcopy(b)
    b["vence_utc"] = vence
    RR.archivo_boletos(r, "2026-11-15").write_text(json.dumps([b]), encoding="utf-8")
    return b


@pytest.mark.parametrize("vence", ["2026-11-16T02:10:00", "mañana", 12345, "2026-13-40T99:00:00Z"])
def test_sin_zona_o_raro_no_lo_pongas(compra, capsys, vence):
    r, b, _ = compra
    b = _con_vence(r, b, vence)
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 1
    salida = capsys.readouterr().out
    assert f"❌ {b['boleto_id']}: boleto vencido o sin fecha válida: no lo pongas" in salida
    assert "TypeError" not in salida and "mal formado" not in salida


def test_con_zona_sigue_igual(compra, capsys):
    r, b, _ = compra
    b = _con_vence(r, b, "2026-11-15T20:10:00-06:00")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 0
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(hours=3), Cli()) == 1
    salida = capsys.readouterr().out
    assert f"❌ {b['boleto_id']}: boleto vencido: no lo pongas" in salida and "sin fecha válida" not in salida
