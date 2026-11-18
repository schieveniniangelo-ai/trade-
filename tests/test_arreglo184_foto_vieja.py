"""Arreglo 184: registrar-saldo rechaza una foto de la cuenta cuyo updateTime es de antes del último llenado anotado.

Antes, la única revisión de que la foto fuera nueva era la fecha del ARCHIVO (st_mtime). Si el EJECUTOR volvía a copiar
el cuenta.json de las 6:00 p. m. después de comprar (o lo guardaba otra vez sin pedirlo a Binance), el archivo era
«nuevo», la foto salía buena y la revisión justo después de la compra (171) comparaba contra un saldo sin la compra.
Ahora también se mira `updateTime` (la hora de Binance de la cuenta): no puede ser de antes del momento más temprano en
que pudo pasar el último llenado que mueve el saldo (compra, stop puesto, venta). Ese momento es la hora de la ronda que
emitió el boleto o, en una compra, su COMPRA_ENVIADA (que se anota antes de mandarla), menos `real.margen_reloj_min`
(2 min) por la diferencia de relojes. STOP_EJECUTADO y COMPRA_NO_LLENADA no cuentan.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta, escribir_entrada, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")
USDT_TRAS_COMPRA = 142.54 - 0.00013 * 70100.0
RONDA = datetime(2026, 11, 16, 0, 10, tzinfo=timezone.utc)       # la ronda que emitió el boleto del 15


def _ms(t):
    return int(t.timestamp() * 1000)


def _comprar(r, b, enviada=AHORA + timedelta(minutes=1)):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=enviada, precio_actual=70000.0)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", ahora=enviada + timedelta(minutes=1), **LLENADA)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "STOP_PUESTO", orden_id=888, stop_id=b["id_stop"],
                                ahora=enviada + timedelta(minutes=2))[0]


def _foto(r, tmp_path, update_time, ahora=AHORA + timedelta(minutes=10), btc_bloq=0.00012):
    cta = cuenta(usdt=USDT_TRAS_COMPRA, btc_bloq=btc_bloq)
    cta["updateTime"] = update_time
    c, o = escribir_entrada(tmp_path, cta, [orden_stop(client=RE.cargar_estado(r)["posiciones"][0]["id_stop"])
                                             if RE.cargar_estado(r)["posiciones"] else orden_stop()])
    return RE.registrar_saldo(r, c, o, lambda s: 70000.0, ahora=ahora)      # el archivo es de ahora: mtime fresco


def test_foto_vieja_copiada_otra_vez_se_rechaza(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b)
    ok, msgs = _foto(r, tmp_path, _ms(AHORA - timedelta(minutes=6)))     # el cuenta.json de las 6:00 p. m.
    assert not ok
    (m,) = [x for x in msgs if "updateTime" in x]
    assert m.startswith("la cuenta (spot.getAccount) dice updateTime 6:06 p. m. del 15/11/2026 (hora CDMX), de antes "
                        f"del último llenado anotado (STOP_PUESTO del boleto {b['boleto_id']}, que no pudo pasar antes "
                        "de 6:13 p. m. del 15/11/2026 (hora CDMX))")
    assert "¿un cuenta.json copiado otra vez?" in m and "Vuelve a pedir spot.getAccount" in m
    assert json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))["ok"] is False
    res = RE.conciliar(r, AHORA + timedelta(minutes=11))                 # la revisión del 171 sigue pendiente
    assert not res["ok"] and RE.cargar_estado(r)[RE.REVISION]["boleto"] == b["boleto_id"]


def test_foto_nueva_de_despues_del_llenado_sirve(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b)
    ok, msgs = _foto(r, tmp_path, _ms(AHORA + timedelta(minutes=3)))     # el stop se puso a las 00:15
    assert ok, msgs
    assert RE.conciliar(r, AHORA + timedelta(minutes=11))["ok"]


@pytest.mark.parametrize("antes_min, sirve", [(1.9, True), (2.1, False)])
def test_margen_de_reloj(compra, tmp_path, antes_min, sirve):
    r, b, _ = compra
    _comprar(r, b)
    ok, _ = _foto(r, tmp_path, _ms(AHORA + timedelta(minutes=1) - timedelta(minutes=antes_min)))
    assert ok is sirve


def test_la_compra_enviada_aprieta_mas_que_la_hora_de_la_ronda(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b, enviada=AHORA + timedelta(minutes=30))
    assert RE.ultimo_llenado(r)[0] == AHORA + timedelta(minutes=30)
    ok, msgs = _foto(r, tmp_path, _ms(AHORA + timedelta(minutes=20)), ahora=AHORA + timedelta(minutes=40))
    assert not ok and any("updateTime" in x for x in msgs)               # después de la ronda, pero antes de la compra


def test_sin_compra_enviada_cuenta_la_hora_de_la_ronda(compra, tmp_path):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", ahora=AHORA + timedelta(minutes=2), **LLENADA)[0]
    assert RE.ultimo_llenado(r) == (RONDA, f"COMPRA_LLENADA del boleto {b['boleto_id']}")
    assert not _foto(r, tmp_path, _ms(RONDA - timedelta(minutes=3)), btc_bloq=0.0)[0]
    ok, msgs = _foto(r, tmp_path, _ms(RONDA - timedelta(minutes=1)), btc_bloq=0.0)
    assert ok and not any("updateTime" in x for x in msgs)


def test_lo_que_no_mueve_el_saldo_no_cuenta(compra, tmp_path):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", motivo="EXPIRED",
                                ahora=AHORA + timedelta(minutes=2))[0]
    assert RE.ultimo_llenado(r) is None
    cta = cuenta()
    cta["updateTime"] = _ms(AHORA - timedelta(days=3))                   # la cuenta no cambió en días: está bien
    c, o = escribir_entrada(tmp_path, cta, [])
    assert RE.registrar_saldo(r, c, o, lambda s: 70000.0, ahora=AHORA + timedelta(minutes=5))[0]


def test_stop_ejecutado_no_cuenta(tmp_path):
    from apoyo_real import reg_real
    r = reg_real(tmp_path)
    arch = RE.archivo_llenados(r)
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text(json.dumps({"boleto_id": "20261120-RA-CER-BTC-00000000", "evento": "STOP_EJECUTADO",
                                "hora_utc": "2026-11-21T00:20:00+00:00"}) + "\n", encoding="utf-8")
    assert RE.ultimo_llenado(r) is None                                   # el stop pudo ejecutarse antes de la ronda


def test_boleto_raro_y_enviada_sin_hora(tmp_path):
    from apoyo_real import reg_real
    r = reg_real(tmp_path)
    arch = RE.archivo_llenados(r)
    arch.parent.mkdir(parents=True, exist_ok=True)
    filas = [{"boleto_id": "raro", "evento": "VENTA_LLENADA"},
             {"boleto_id": "raro2", "evento": "COMPRA_ENVIADA", "hora_utc": "2026-11-16T00:13:00+00:00"},
             {"boleto_id": "raro2", "evento": "COMPRA_LLENADA"},
             {"boleto_id": "20261114-RA-COM-BTC-00000000", "evento": "COMPRA_ENVIADA", "hora_utc": "no se entiende"},
             {"boleto_id": "20261114-RA-COM-BTC-00000000", "evento": "COMPRA_LLENADA"}]
    arch.write_text("".join(json.dumps(x) + "\n" for x in filas), encoding="utf-8")
    t, que = RE.ultimo_llenado(r)
    assert t == datetime(2026, 11, 16, 0, 13, tzinfo=timezone.utc) and que == "COMPRA_LLENADA del boleto raro2"
    assert RE._foto_de_antes_del_llenado(r, None) == "" and RE._foto_de_antes_del_llenado(r, True) == ""


def test_margen_del_reglamento(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b)
    r2 = r.copia_con({"real.margen_reloj_min": 10})
    r2.ruta = r.ruta
    assert RE._foto_de_antes_del_llenado(r2, _ms(AHORA - timedelta(minutes=5))) == ""
    assert RE._foto_de_antes_del_llenado(r, _ms(AHORA - timedelta(minutes=5))) != ""


def test_el_texto_del_ejecutor():
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    assert "Nunca vuelvas a usar un `cuenta.json` viejo" in ej and "arreglo 184" in ej
