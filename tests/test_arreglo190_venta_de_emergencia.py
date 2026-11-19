"""Arreglo 190 (R101 + I5): el boleto de COMPRA real trae ya lista su `orden_venta_emergencia`.

Antes, si el stop no se podía poner (ni con un reintento), bots/4_EJECUTOR_REAL.md (paso 4j) decía «VENDE TODO lo
comprado a MERCADO (cantidad libre redondeada…)»: el EJECUTOR calculaba la cantidad en el peor momento, podía vender BTC
que no era de esa compra (un sobrante sin anotar, 180) y la venta no tenía un newClientOrderId fijo para revisar con
spot.getOrder antes de reintentar (181). Ahora el boleto trae la venta lista: SELL MARKET por la cantidad NETA (la del
stop) y con su newClientOrderId fijo (`real.id_venta_emergencia`); el paso 4j dice copiarla tal cual, sin vender «todo
lo libre». La revisión del boleto real la exige."""
import copy
import dataclasses
from pathlib import Path

import pytest

from sobreviviente import real as RE
from sobreviviente import reglamento

from apoyo_real import AHORA
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent


def test_el_boleto_trae_la_venta_lista(compra):
    r, b, _ = compra
    ve = b["orden_venta_emergencia"]
    assert ve == {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": b["orden_stop"]["quantity"],
                  "newClientOrderId": RE.id_venta_emergencia(b["boleto_id"]), "newOrderRespType": "FULL"}
    assert float(ve["quantity"]) == b["cantidad_stop"] < b["cantidad"]          # la NETA (comisión en BTC), no la comprada
    assert RE.revisar_boleto_real(r, b, FILTROS) == []


def test_el_id_es_fijo_y_propio():
    a = RE.id_venta_emergencia("20261115-RA-COM-BTC-1a2b3c4d")
    assert a == RE.id_venta_emergencia("20261115-RA-COM-BTC-1a2b3c4d") and a.startswith("be") and len(a) == 18
    assert a != RE.id_venta_emergencia("20261116-RA-COM-BTC-1a2b3c4d")
    assert a not in (RE.id_venta("20261115-RA-COM-BTC-1a2b3c4d"), RE.id_compra("20261115-RA-COM-BTC-1a2b3c4d"))


def test_respeta_el_paso_de_mercado():
    f = dataclasses.replace(FILTROS, paso_mercado=0.0001)
    b = RE.boleto_compra_real(reglamento.cargar(), "2026-11-15", "BTCUSDT", 70000.0, 59500.0, 0.00033, f, AHORA)
    assert float(b["orden_stop"]["quantity"]) == pytest.approx(0.00032)
    assert float(b["orden_venta_emergencia"]["quantity"]) == pytest.approx(0.0003)   # hacia abajo al paso de mercado


@pytest.mark.parametrize("cambio,error", [
    (lambda ve: None, "falta orden_venta_emergencia"),
    (lambda ve: {**ve, "type": "LIMIT"}, "no es una VENTA a MERCADO sin precio"),
    (lambda ve: {**ve, "side": "BUY"}, "no es una VENTA a MERCADO sin precio"),
    (lambda ve: {**ve, "price": "70000"}, "no es una VENTA a MERCADO sin precio"),
    (lambda ve: {**ve, "symbol": "ETHUSDT"}, "no es de la moneda del boleto"),
    (lambda ve: {**ve, "quantity": "0.00013"}, "no es por la cantidad neta"),
    (lambda ve: {**ve, "quantity": "0"}, "no es por la cantidad neta"),
    (lambda ve: {**ve, "newClientOrderId": "be0000000000000000"}, "no trae su newClientOrderId fijo"),
])
def test_la_revision_la_exige(compra, cambio, error):
    r, b, _ = compra
    b = copy.deepcopy(b)
    nuevo = cambio(b["orden_venta_emergencia"])
    if nuevo is None:
        b.pop("orden_venta_emergencia")
    else:
        b["orden_venta_emergencia"] = nuevo
    assert any(error in e for e in RE.revisar_boleto_real(r, b, FILTROS))


def test_el_texto_del_boleto_lo_dice(compra):
    _, b, _ = compra
    idv = RE.id_venta_emergencia(b["boleto_id"])
    assert (f"Si el stop no se puede poner ni con un reintento, VENDE con orden_venta_emergencia tal cual (0.00012 BTC a "
            f"MERCADO, newClientOrderId={idv}; no todo lo libre) y si la venta falla o no sabes si llegó") in b["texto"]
    assert f"revisa con spot.getOrder (origClientOrderId={idv}) si ya existe" in b["texto"]


def test_el_aviso_de_stop_no_puesto():
    t = RE.AVISOS_EVENTO["STOP_NO_PUESTO"]
    assert "orden_venta_emergencia" in t and "no todo lo libre" in t and "VENDE TODO" not in t


def test_ejecutor_paso_4j():
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso4 = ej[ej.index("4. Boleto de COMPRA"):ej.index("5. Boleto de CIERRE")]
    j = paso4[paso4.index("j. Si el stop se rechaza"):]
    assert "copiando TAL CUAL `orden_venta_emergencia` del boleto" in j and "su `newClientOrderId` FIJO" in j
    assert "No vendas «todo lo libre»" in j and "revisa con `spot.getOrder` por `origClientOrderId`" in j
    assert "VENDE TODO" not in j and "cantidad libre redondeada hacia abajo al paso" not in j
    assert j.index("orden_venta_emergencia") < j.index("CIERRE_DE_EMERGENCIA")
