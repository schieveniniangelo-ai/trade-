"""Arreglo 173: no se manda una segunda compra real mientras haya una sin anotar.

`_por_que_no_comprar` (la puerta de COMPRA_ENVIADA, arreglo 171) no revisaba `compras_sin_anotar`: si el EJECUTOR se caía
entre COMPRA_ENVIADA y el resultado, y nadie había corrido conciliar --real (que es quien pone `bloqueo_compras`), podía
anotar y mandar OTRA compra encima. Ahora lo primero que revisa es si hay un COMPRA_ENVIADA sin COMPRA_LLENADA,
COMPRA_PARCIAL ni COMPRA_NO_LLENADA (ni una venta urgente que lo cubra, arreglo 172): si lo hay, «NO mandes la compra»
con el boleto pendiente y qué anotar. Los demás motivos del 171 quedan igual.
"""
import json
from datetime import timedelta

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

DIA2 = AHORA + timedelta(days=1)
ENVIADA = "COMPRA_ENVIADA"
MOTIVO = "hay una compra enviada sin anotar"


def _otro_boleto(r, dia="2026-11-16"):
    """Un boleto de compra de otro día, como lo armaría la ronda (la ronda no se corre: su conciliación lo frenaría)."""
    b2 = RE.boleto_compra_real(r, dia, "BTCUSDT", 70000.0, 59500.0, 0.00013, FILTROS, DIA2)
    RR.archivo_boletos(r, dia).write_text(json.dumps([b2]), encoding="utf-8")
    return b2


def _enviar(r, b, cuando):
    return RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=cuando, precio_actual=70000.0)    # arreglo 182


def test_la_segunda_compra_enviada_se_rechaza_aunque_nadie_haya_conciliado(compra):
    r, b, _ = compra
    assert _enviar(r, b, AHORA + timedelta(minutes=1))[0]
    assert RE.cargar_estado(r)["bloqueo_compras"] is None              # nadie corrió conciliar --real
    b2 = _otro_boleto(r)
    ok, msgs = _enviar(r, b2, DIA2 + timedelta(minutes=1))
    assert not ok
    assert msgs[0].startswith(f"NO mandes la compra: {MOTIVO} (boleto {b['boleto_id']}, COMPRA_ENVIADA, ")
    assert "anota primero cómo terminó (COMPRA_LLENADA, COMPRA_PARCIAL o COMPRA_NO_LLENADA)" in msgs[0]
    assert "no se manda otra compra" in msgs[0] and "Avisa a THE BOSS" in msgs[0]
    assert [(x["boleto_id"], x["evento"]) for x in RE.leer_llenados(r)] == [(b["boleto_id"], ENVIADA)]


def test_por_la_linea_de_comandos_sale_con_x(compra, monkeypatch, capsys):
    r, b, _ = compra
    assert _enviar(r, b, AHORA + timedelta(minutes=1))[0]
    b2 = _otro_boleto(r)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b2["boleto_id"], "--evento", ENVIADA]) == 1
    assert capsys.readouterr().out.startswith(f"❌ NO mandes la compra: {MOTIVO} (boleto {b['boleto_id']}")


def test_con_la_compra_no_llenada_anotada_ya_se_puede(compra):
    r, b, _ = compra
    assert _enviar(r, b, AHORA + timedelta(minutes=1))[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", ahora=AHORA + timedelta(minutes=2),
                                motivo="EXPIRED")[0]
    b2 = _otro_boleto(r)
    ok, msgs = _enviar(r, b2, DIA2 + timedelta(minutes=1))
    assert ok and msgs[0].startswith(f"👍 Compra ENVIADA anotada ({b2['boleto_id']})")


def test_con_la_compra_llenada_anotada_manda_el_motivo_del_171(compra):
    r, b, _ = compra
    assert _enviar(r, b, AHORA + timedelta(minutes=1))[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", orden_id=777, cantidad=0.00013, precio=70100.0,
                                comision=0.00000013, moneda_comision="BTC", ahora=AHORA + timedelta(minutes=2))[0]
    ok, msgs = _enviar(r, _otro_boleto(r), DIA2 + timedelta(minutes=1))
    assert not ok and MOTIVO not in msgs[0] and "no tiene su stop ACTIVO" in msgs[0]     # ya no está sin anotar


def test_la_venta_urgente_anotada_tambien_la_cierra(compra, capsys):
    r, b, foto = compra
    assert _enviar(r, b, AHORA + timedelta(minutes=1))[0]
    foto(cuenta(usdt=142.54 - 0.00013 * 70100.0, btc=0.00012987), [], ahora=DIA2 - timedelta(minutes=5))
    assert RR.correr(r, DIA2, cliente=object(), memes=[]) == 0           # conciliar bloquea y sale la venta urgente
    (v,) = [x for x in json.loads(RR.archivo_boletos(r, "2026-11-16").read_text(encoding="utf-8"))
            if x.get("motivo") == RE.MOTIVO_SIN_ANOTAR]
    b3 = _otro_boleto(r, "2026-11-17")
    ok, msgs = _enviar(r, b3, DIA2 + timedelta(minutes=2))
    assert not ok and MOTIVO in msgs[0]                                  # va primero, aunque también haya bloqueo
    assert RE.registrar_llenado(r, v["boleto_id"], "VENTA_LLENADA", cantidad=0.00012, precio=69900.0,
                                ahora=DIA2 + timedelta(minutes=3))[0]
    ok, msgs = _enviar(r, b3, DIA2 + timedelta(minutes=4))
    assert not ok and MOTIVO not in msgs[0] and "compras reales bloqueadas" in msgs[0]   # el bloqueo: solo Ángelo


@pytest.mark.parametrize("filas, pedazo", [
    ([{"evento": ENVIADA, "boleto_id": "20261114-RA-COM-BTC-00000000"}], "COMPRA_ENVIADA, sin hora"),
    ([{"evento": ENVIADA, "boleto_id": "20261114-RA-COM-BTC-00000000", "hora_utc": "no se entiende"}],
     "COMPRA_ENVIADA, sin hora"),
    ([{"evento": ENVIADA, "boleto_id": "20261113-RA-COM-BTC-00000000", "hora_utc": "2026-11-14T00:13:00+00:00"},
      {"evento": ENVIADA, "boleto_id": "20261114-RA-COM-BTC-00000000"}],
     "(boleto 20261113-RA-COM-BTC-00000000 y 1 más, COMPRA_ENVIADA, 6:13 p. m. del 13/11/2026 (hora CDMX))"),
])
def test_el_motivo_dice_cual_y_cuantas(compra, filas, pedazo):
    r, b, _ = compra
    arch = RE.archivo_llenados(r)
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text("".join(json.dumps(x) + "\n" for x in filas), encoding="utf-8")
    ok, msgs = _enviar(r, b, AHORA + timedelta(minutes=1))
    assert not ok and MOTIVO in msgs[0] and pedazo in msgs[0]
    assert RE._por_que_no_comprar(RE.cargar_estado(r)) == ""            # sin `reg` queda como en el 171
