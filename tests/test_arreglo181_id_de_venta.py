"""Arreglo 181 (I5): las ventas a mercado llevan un newClientOrderId FIJO por boleto; antes de reintentar, spot.getOrder.

Antes, `orden_venta` (cierre de una posición y venta urgente) no traía newClientOrderId. Si la venta llegaba a Binance
pero la respuesta se perdía (se cortó la conexión), el EJECUTOR «reintentaba una vez» y vendía DOS veces. Para una
orden a mercado, Binance solo exige que el newClientOrderId no se repita entre las órdenes ABIERTAS: una venta ya
llenada no frena otra con el mismo id. Por eso la regla es revisar con spot.getOrder ANTES de reintentar.

Ahora `orden_venta` trae `newClientOrderId` = `real.id_venta(boleto)` (bv + 16 hex, el mismo siempre para el mismo
boleto), `revisar_boleto_real` no aprueba una venta sin ese id, y el texto del boleto y bots/4_EJECUTOR_REAL.md (pasos 5
y 5b) dicen: antes de reintentar, spot.getOrder por origClientOrderId; si ya existe, no se repite.
"""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA
from test_arreglo131_conciliar_real import POS
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import Cli

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def r(mundo):
    return mundo[0]


def test_el_id_es_fijo_por_boleto_y_distinto_entre_boletos(r):
    c1 = RE.boleto_cierre_real(r, "2026-11-20", POS, "SALIDA_M0")
    c2 = RE.boleto_cierre_real(r, "2026-11-20", POS, "SALIDA_M0")
    v = RE.boleto_venta_sin_anotar(r, "2026-11-20", "BTCUSDT", 0.00013, 70000.0, FILTROS)
    idc, idv = c1["orden_venta"]["newClientOrderId"], v["orden_venta"]["newClientOrderId"]
    assert idc == c2["orden_venta"]["newClientOrderId"] == c1["id_venta"] == RE.id_venta(c1["boleto_id"])
    assert idv == v["id_venta"] == RE.id_venta(v["boleto_id"]) and idc != idv
    assert idc.startswith("bv") and len(idc) == 18 and idc.isascii() and idc != RE.id_compra(c1["boleto_id"])
    assert RE.id_venta("20261121-RA-CER-BTC-00000000") != idc                   # otro día, otro id


def test_revisar_no_aprueba_una_venta_sin_su_id(r):
    for b in (RE.boleto_cierre_real(r, "2026-11-20", POS, "SIN_STOP"),
              RE.boleto_venta_sin_anotar(r, "2026-11-20", "BTCUSDT", 0.00013, 70000.0, FILTROS)):
        assert RE.revisar_boleto_real(r, b, FILTROS) == []
        sin = {**b, "orden_venta": {k: v for k, v in b["orden_venta"].items() if k != "newClientOrderId"}}
        otro = {**b, "orden_venta": {**b["orden_venta"], "newClientOrderId": "bv0000000000000000"}}
        for malo in (sin, otro):
            assert "la venta no trae su newClientOrderId fijo (el de su boleto)" in \
                "; ".join(RE.revisar_boleto_real(r, malo, FILTROS))
    informativo = RE.boleto_cierre_real(r, "2026-11-20", POS, "STOP_EJECUTADO")
    assert "orden_venta" not in informativo and RE.revisar_boleto_real(r, informativo, FILTROS) == []


def test_verificar_real_lo_revisa(r, capsys):
    b = RE.boleto_cierre_real(r, "2026-11-20", POS, "SALIDA_M0")
    RR.archivo_boletos(r, "2026-11-20").parent.mkdir(parents=True, exist_ok=True)
    RR.archivo_boletos(r, "2026-11-20").write_text(json.dumps([b]), encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-20", AHORA + timedelta(days=5), Cli()) == 0
    b["orden_venta"].pop("newClientOrderId")
    RR.archivo_boletos(r, "2026-11-20").write_text(json.dumps([b]), encoding="utf-8")
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-20", AHORA + timedelta(days=5), Cli()) == 1
    assert "newClientOrderId fijo" in capsys.readouterr().out


def test_los_textos_dicen_revisar_con_getorder_antes_de_reintentar(r):
    for b in (RE.boleto_cierre_real(r, "2026-11-20", POS, "SALIDA_M0"),
              RE.boleto_venta_sin_anotar(r, "2026-11-20", "BTCUSDT", 0.00013, 70000.0, FILTROS)):
        t = b["texto"]
        frase = f"ANTES de reintentar revisa con spot.getOrder (origClientOrderId={b['id_venta']}) si ya existe"
        assert frase in t and "si existe, NO la repitas" in t
        assert t.index(frase) < t.index("reintenta una vez con el mismo newClientOrderId")
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    for inicio, fin in (("5. Boleto de CIERRE", "5b. Boleto de VENTA URGENTE"), ("5b. Boleto de VENTA URGENTE",
                                                                                 "6. Foto final")):
        paso = ej[ej.index(inicio):ej.index(fin)]
        assert "`newClientOrderId` FIJO" in paso and "ANTES de reintentar revisa con `spot.getOrder`" in paso
        assert paso.index("spot.getOrder") < paso.index("reintenta una vez")
        assert "si existe, NO la repitas" in paso


class Binance:
    """Binance falso: una venta a mercado se llena al instante; un id ya LLENADO no frena otra venta (solo valen las
    órdenes abiertas). La primera respuesta se pierde (se corta la conexión) aunque la venta sí entró."""

    def __init__(self):
        self.ordenes = {}
        self.ventas = 0
        self.cortar = True

    def nueva_orden(self, o):
        self.ventas += 1
        self.ordenes[o["newClientOrderId"]] = {"status": "FILLED", "executedQty": o["quantity"]}
        if self.cortar:
            self.cortar = False
            raise TimeoutError("se cortó la conexión")
        return self.ordenes[o["newClientOrderId"]]

    def consultar(self, client_id):
        return self.ordenes.get(client_id)


def ejecutor(b, bn, revisar_antes=True):
    """El EJECUTOR siguiendo el paso 5/5b: manda orden_venta tal cual; si falla, revisa con getOrder antes de reintentar."""
    for _ in range(2):
        try:
            return bn.nueva_orden(b["orden_venta"])
        except TimeoutError:
            if revisar_antes and (ya := bn.consultar(b["orden_venta"]["newClientOrderId"])) is not None:
                return ya
    return None


@pytest.mark.parametrize("hacer", [lambda r: RE.boleto_cierre_real(r, "2026-11-20", POS, "SIN_STOP"),
                                   lambda r: RE.boleto_venta_sin_anotar(r, "2026-11-20", "BTCUSDT", 0.00013, 70000.0,
                                                                        FILTROS)])
def test_con_la_respuesta_perdida_se_vende_una_sola_vez(r, hacer):
    b = hacer(r)
    bn = Binance()
    assert ejecutor(b, bn)["status"] == "FILLED" and bn.ventas == 1
    bn2 = Binance()
    ejecutor(b, bn2, revisar_antes=False)                                   # sin revisar: vende dos veces
    assert bn2.ventas == 2
