"""Arreglo 181: las ventas a mercado llevan un newClientOrderId FIJO por boleto, para revisarlas antes de reintentar.

Antes, `orden_venta` (cierre de una posición y venta urgente) no traía newClientOrderId: Binance le ponía uno al azar.
Si la respuesta de la venta se perdía (red, caída del EJECUTOR), reintentar podía vender DOS veces. Ahora:
* `real.id_venta(boleto)` = «bv» + 16 hex, siempre el mismo para el mismo boleto;
* el cierre y la venta urgente lo traen en `orden_venta`, y el texto del boleto dice que, antes de reintentar, se busque
  con spot.getOrder (origClientOrderId) y, si ya existe y se llenó, no se repita;
* `revisar_boleto_real` (y `ronda --verificar --real`) rechaza una venta sin ese id o con otro;
* bots/4_EJECUTOR_REAL.md lo dice en los pasos 5 y 5b.
"""
import json
import re
from pathlib import Path

import pytest

from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, reg_real
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import Cli

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def r(tmp_path):
    return reg_real(tmp_path)


def test_el_id_es_fijo_corto_y_distinto(r):
    a = RE.id_venta("20261115-RA-CER-BTC-1a2b3c4d")
    assert a == RE.id_venta("20261115-RA-CER-BTC-1a2b3c4d") and re.fullmatch(r"bv[0-9a-f]{16}", a)
    assert a != RE.id_venta("20261116-RA-CER-BTC-1a2b3c4d")
    assert a != RE.id_compra("20261115-RA-CER-BTC-1a2b3c4d")            # no choca con el de la compra


@pytest.mark.parametrize("motivo", ["SALIDA_M0", "SIN_STOP", "STOP_SIN_LLENAR"])
def test_el_cierre_lo_trae(r, motivo):
    b = RE.boleto_cierre_real(r, "2026-11-15", dict(POS), motivo, FILTROS)
    assert b["orden_venta"]["newClientOrderId"] == RE.id_venta(b["boleto_id"])
    assert f"spot.getOrder (origClientOrderId={RE.id_venta(b['boleto_id'])})" in b["texto"]
    assert "NO la repitas" in b["texto"] and "mismo newClientOrderId" in b["texto"]
    assert RE.revisar_boleto_real(r, b, FILTROS) == []


def test_el_stop_ejecutado_no_vende(r):
    b = RE.boleto_cierre_real(r, "2026-11-15", dict(POS), "STOP_EJECUTADO", FILTROS)
    assert "orden_venta" not in b and RE.revisar_boleto_real(r, b, FILTROS) == []


def test_la_venta_urgente_lo_trae(r):
    b = RE.boleto_venta_sin_anotar(r, "2026-11-15", "BTCUSDT", 0.00013, 70000.0, FILTROS)
    assert b["orden_venta"]["newClientOrderId"] == RE.id_venta(b["boleto_id"])
    assert f"origClientOrderId={RE.id_venta(b['boleto_id'])}" in b["texto"]
    assert RE.revisar_boleto_real(r, b, FILTROS) == []


@pytest.mark.parametrize("cambio", [None, "bv0000000000000000", "otro"])
def test_sin_el_id_o_con_otro_no_pasa(r, cambio):
    for b in (RE.boleto_cierre_real(r, "2026-11-15", dict(POS), "SIN_STOP", FILTROS),
              RE.boleto_venta_sin_anotar(r, "2026-11-15", "BTCUSDT", 0.00013, 70000.0, FILTROS)):
        if cambio is None:
            b["orden_venta"].pop("newClientOrderId")
        else:
            b["orden_venta"]["newClientOrderId"] = cambio
        errores = RE.revisar_boleto_real(r, b, FILTROS)
        assert any(e.startswith("la venta no trae su newClientOrderId fijo") for e in errores)


def test_la_ronda_real_lo_pone_y_verificar_lo_revisa(mundo, capsys):
    r, _, foto, correr = mundo
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [])                    # sin stop: cierre SIN_STOP
    assert correr() == 0
    arch = RR.archivo_boletos(r, "2026-11-15")
    (b,) = [x for x in json.loads(arch.read_text(encoding="utf-8")) if x["accion"] == "CERRAR"]
    assert b["orden_venta"]["newClientOrderId"] == RE.id_venta(b["boleto_id"])
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, Cli()) == 0
    b["orden_venta"]["newClientOrderId"] = "x"
    arch.write_text(json.dumps([b]), encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, Cli()) == 1
    assert "la venta no trae su newClientOrderId fijo" in capsys.readouterr().out


def test_el_texto_del_ejecutor():
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso5 = ej[ej.index("5. Boleto de CIERRE"):ej.index("5b. Boleto de VENTA URGENTE")]
    paso5b = ej[ej.index("5b. Boleto de VENTA URGENTE"):ej.index("6. Foto final")]
    for paso in (paso5, paso5b):
        assert "ANTES de reintentar búscala con `spot.getOrder` por `origClientOrderId`" in paso
        assert "NO la repitas" in paso and "arreglo 181" in paso and "mismo `newClientOrderId`" in paso
    assert "empieza con `bv`" in paso5
