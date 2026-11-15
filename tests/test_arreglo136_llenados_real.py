"""Arreglo 136: `ronda --verificar --real` y `registrar-llenado --real` (cierra R3).

registrar-llenado --real es lo único que da de alta o de baja posiciones en cartera_REAL.json. La posición nace SIN_STOP
y solo pasa a ACTIVO con STOP_PUESTO. Rechaza eventos repetidos, cantidades de más, eventos fuera de orden y compras
arriba del límite. El flujo de papel (--ensayo) queda igual y la revisión de papel nunca aprueba un boleto real."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_real
from sobreviviente import cli_ronda as CR
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, escribir_entrada, orden_stop
from test_arreglo132_boleto_real import FIXTURE
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture

INFO = {"symbols": [json.loads(FIXTURE.read_text(encoding="utf-8"))]}


class Cli:
    def __init__(self, *_):
        pass

    def exchange_info(self, mercado="SPOT", forzar=False):
        return INFO

    def spot(self, ruta, params):
        return {"price": "70000"}


@pytest.fixture
def compra(mundo, capsys):  # noqa: F811
    r, cfg, foto, correr = mundo
    foto()
    assert correr() == 0
    capsys.readouterr()
    (b,) = json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
    return r, b, foto


def _llenar(r, b, evento, **kw):
    return RE.registrar_llenado(r, b["boleto_id"], evento, ahora=AHORA + timedelta(minutes=2), **kw)


def test_verificar_real(compra, capsys):
    r, b, _ = compra
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 0
    assert f"✅ {b['boleto_id']}" in capsys.readouterr().out
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(hours=3), Cli()) == 1      # vencido
    assert "boleto vencido" in capsys.readouterr().out
    _llenar(r, b, "COMPRA_NO_LLENADA")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=3), Cli()) == 1
    assert "YA REGISTRADO: no lo pongas otra vez" in capsys.readouterr().out


def test_verificar_real_sin_ronda_vacia_y_rota(tmp_path, capsys):
    from apoyo_real import reg_real
    r = reg_real(tmp_path)
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, Cli()) == 1
    assert "NO HAY RONDA REAL" in capsys.readouterr().out
    RR.archivo_boletos(r, "2026-11-15").parent.mkdir(parents=True)
    RR.archivo_boletos(r, "2026-11-15").write_text("[]", encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, Cli()) == 0
    assert "sin boletos reales hoy" in capsys.readouterr().out
    RR.archivo_boletos(r, "2026-11-15").write_text('{"a": 1}', encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, Cli()) == 1
    RR.archivo_boletos(r, "2026-11-15").write_text('[{"modo": "PAPEL", "accion": "COMPRAR"}, 3]', encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, Cli()) == 1
    salida = capsys.readouterr().out
    assert "no es un boleto REAL" in salida and "formato raro" in salida

    class SinRed(Cli):
        def exchange_info(self, *a, **k):
            raise OSError("sin red")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, SinRed()) == 1


def test_la_revision_de_papel_nunca_aprueba_un_boleto_real(compra):
    r, b, _ = compra
    errores = CR._revisar_boleto(r, Cli(), b, {x["symbol"]: x for x in INFO["symbols"]}, AHORA)
    assert errores == ["boleto REAL: se revisa con ronda --verificar --real, no aquí"]


def test_flujo_completo_compra_stop_conciliar_cierre(compra, capsys):
    r, b, foto = compra
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013,
                       moneda_comision="BTC")
    assert ok and msgs[0].startswith("👍 Compra anotada: 0.00012 BTC")
    (p,) = RE.cargar_estado(r)["posiciones"]
    assert p["estado_stop"] == "SIN_STOP" and p["cantidad_neta"] == 0.00012 and p["cantidad_comprada"] == 0.00013
    assert p["costo_usdt"] == pytest.approx(0.00013 * 70100)
    ok, _ = _llenar(r, b, "STOP_PUESTO", orden_id=888, stop_id=b["id_stop"])
    assert ok and RE.cargar_estado(r)["posiciones"][0]["estado_stop"] == "ACTIVO"
    usdt = 142.54 - 0.00013 * 70100
    foto(cuenta(usdt=usdt, btc_bloq=0.00012), [orden_stop(client=b["id_stop"], order_id=888)],
         ahora=AHORA + timedelta(minutes=5))
    assert RE.conciliar(r, AHORA + timedelta(minutes=6))["ok"]
    # Días después, M0 manda salir: boleto de cierre y su venta
    pos = RE.cargar_estado(r)["posiciones"][0]
    cierre = RE.boleto_cierre_real(r, "2026-11-20", pos, "SALIDA_M0")
    RR.archivo_boletos(r, "2026-11-20").write_text(json.dumps([cierre]), encoding="utf-8")
    ok, msgs = RE.registrar_llenado(r, cierre["boleto_id"], "VENTA_LLENADA", cantidad=0.00012, precio=75000.0,
                                    comision=0.009, moneda_comision="USDT")
    assert ok and "Salida anotada" in msgs[0]
    est = RE.cargar_estado(r)
    assert est["posiciones"] == [] and est["cerradas"][0]["ganancia_usdt"] == pytest.approx(9.0 - 0.009 - 0.00013 * 70100)
    ahora = AHORA + timedelta(days=5)
    foto(cuenta(usdt=usdt + 9.0 - 0.009, btc=0.00000987), [], ahora=ahora)
    assert RE.conciliar(r, ahora)["ok"]
    filas = RE.leer_llenados(r)
    assert [x["evento"] for x in filas] == ["COMPRA_LLENADA", "STOP_PUESTO", "VENTA_LLENADA"]


def test_compra_parcial_avisa_primero(compra):
    r, b, _ = compra
    ok, msgs = _llenar(r, b, "COMPRA_PARCIAL", cantidad=0.00007, precio=70000.0, comision=0.01, moneda_comision="BNB")
    assert ok and msgs[0].startswith("❌ COMPRA PARCIAL")
    assert RE.cargar_estado(r)["posiciones"][0]["cantidad_neta"] == 0.00007    # comisión en BNB: no se resta


def test_stop_no_puesto_y_cierre_de_emergencia(compra):
    r, b, _ = compra
    _llenar(r, b, "COMPRA_LLENADA", cantidad=0.00013, precio=70000.0, comision=0.00000013, moneda_comision="BTC")
    ok, msgs = _llenar(r, b, "STOP_NO_PUESTO")
    assert ok and msgs[0].startswith("❌ COMPRA SIN STOP: VENDE TODO a MERCADO ya")
    ok, msgs = _llenar(r, b, "CIERRE_DE_EMERGENCIA", cantidad=0.00012, precio=69900.0, comision=0.0084,
                       moneda_comision="USDT")
    assert ok and msgs[0] == "❌ COMPRA SIN STOP, VENDIDA A MERCADO. Avisa a THE BOSS con prioridad máxima."
    assert RE.cargar_estado(r)["posiciones"] == []


def test_rechazos(compra):
    r, b, _ = compra
    assert "fuera de orden" in _llenar(r, b, "STOP_PUESTO", orden_id=1, stop_id="x")[1][0]
    assert "fuera de orden" in _llenar(r, b, "VENTA_LLENADA", cantidad=0.0001, precio=1.0)[1][0]
    assert "mayor que la del boleto" in _llenar(r, b, "COMPRA_LLENADA", cantidad=0.0002, precio=70000.0, comision=0.0,
                                                moneda_comision="BTC")[1][0]
    assert "mayor que el límite de compra" in _llenar(r, b, "COMPRA_LLENADA", cantidad=0.00013, precio=70300.0,
                                                      comision=0.0, moneda_comision="BTC")[1][0]
    assert "faltan" in _llenar(r, b, "COMPRA_LLENADA", cantidad=0.00013)[1][0]
    assert RE.registrar_llenado(r, "20261115-RA-COM-BTC-noexiste", "COMPRA_NO_LLENADA")[1][0].startswith("no existe")
    assert "evento desconocido" in _llenar(r, b, "QUIZA")[1][0]
    assert RE.cargar_estado(r)["posiciones"] == [] and RE.leer_llenados(r) == []   # nada se anotó
    assert _llenar(r, b, "COMPRA_LLENADA", cantidad=0.00013, precio=70000.0, comision=0.0, moneda_comision="BTC")[0]
    assert "ya está registrado" in _llenar(r, b, "COMPRA_LLENADA", cantidad=0.00013, precio=70000.0, comision=0.0,
                                           moneda_comision="BTC")[1][0]
    assert "ya está registrada" in _llenar(r, b, "COMPRA_PARCIAL", cantidad=0.0001, precio=70000.0, comision=0.0,
                                           moneda_comision="BTC")[1][0]
    assert "faltan --orden-id" in _llenar(r, b, "STOP_PUESTO")[1][0]
    assert "mayor que la de la posición" in _llenar(r, b, "VENTA_LLENADA", cantidad=0.001, precio=1.0)[1][0]
    assert "faltan --cantidad" in _llenar(r, b, "VENTA_LLENADA")[1][0]


def test_cierre_no_acepta_compra(compra):
    r, b, _ = compra
    pos = {**b, "id": b["boleto_id"], "cantidad_neta": 0.00012, "paso_cantidad": 0.00001, "orden_id_stop": None}
    cierre = RE.boleto_cierre_real(r, "2026-11-20", pos, "SIN_STOP")
    RR.archivo_boletos(r, "2026-11-20").write_text(json.dumps([cierre]), encoding="utf-8")
    ok, msgs = RE.registrar_llenado(r, cierre["boleto_id"], "COMPRA_LLENADA", cantidad=0.0001, precio=1.0, comision=0.0,
                                    moneda_comision="BTC")
    assert not ok and "no es de compra" in msgs[0]


def test_comandos(compra, monkeypatch, capsys):
    r, b, _ = compra
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr("sobreviviente.datos.ClienteBinance", Cli)
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_LLENADA",
                      "--cantidad", "0.00013", "--precio", "70000"]) == 1
    assert capsys.readouterr().out.startswith("❌ faltan")
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA"]) == 0
    assert "la compra no se llenó" in capsys.readouterr().out
    assert MAIN.main(["ronda", "--verificar", "--real"]) in (0, 1)    # el día lo pone el reloj: solo que no truene
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "STOP_PUESTO"]) == 1
    assert "dañado" in capsys.readouterr().out
