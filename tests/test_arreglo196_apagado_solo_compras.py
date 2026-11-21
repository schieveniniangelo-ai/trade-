"""Arreglo 196: con real.activo: false solo se bloquean las COMPRAS; lo que protege una posición que ya existe sigue.

Antes (arreglo 186), con el interruptor apagado, `registrar-llenado --real` no anotaba NADA y `ronda --modo real` salía
sin decir nada más: si había una posición real abierta y su stop se ejecutaba, no había cómo anotarlo, y lo urgente
(una posición sin stop, BTC sin anotar) no salía en la ronda. Ahora:

* `registrar-llenado --real` sigue rechazando COMPRA_ENVIADA (y los demás eventos de compra), pero anota STOP_PUESTO,
  STOP_EJECUTADO, VENTA_ENVIADA, VENTA_LLENADA, VENTA_NO_LLENADA y CIERRE_DE_EMERGENCIA (con el candado de la ronda real).
* `ronda --modo real` imprime primero los pendientes urgentes y los boletos de cierre o venta urgente (los escribe en
  salida/boletos_real_<día>.json para poder verificarlos y anotarlos) y después sale con el ⛔. Nunca sale una compra.
* `ronda --verificar --real` nunca aprueba un COMPRAR, pero sí revisa los CERRAR."""
import json
from datetime import timedelta

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import Cli, compra  # noqa: F401 - fixture

APAGADO = "⛔ El dinero real está APAGADO (real.activo: false en reglamento.yaml, DECISIÓN DE ÁNGELO): "
USDT_DESPUES = USDT_CON_POS + 0.00012 * 59300.0 - 0.0071


def _con_posicion(r, **cambios):
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"),
                          "posiciones": [{**POS, "id": "20261114-RA-COM-BTC-abcd1234", **cambios}]})


def test_posicion_abierta_apagado_el_stop_ejecutado_se_anota(mundo, monkeypatch, capsys):
    r, _, foto, correr = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_DESPUES, btc=0.000009), [])            # el stop se ejecutó: sin órdenes y polvo
    r.datos["real"]["activo"] = False
    capsys.readouterr()
    assert correr() == 2                                          # sale con el ⛔
    salida = capsys.readouterr().out
    lineas = salida.splitlines()
    (b,) = json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
    assert b["accion"] == "CERRAR" and b["motivo"] == "STOP_EJECUTADO"
    assert "  " + b["texto"] in lineas                            # el boleto que protege sale impreso…
    i = lineas.index("  " + b["texto"])
    j = next(k for k, x in enumerate(lineas) if x.startswith(f"{RR.ENCABEZADO} La ronda real NO corre: {APAGADO}"))
    assert i < j                                                  # …antes del ⛔
    assert "COMPRAR" not in salida
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "STOP_EJECUTADO",
                      "--cantidad", "0.00012", "--precio", "59300", "--comision", "0.0071",
                      "--moneda-comision", "USDT"]) == 0
    assert RE.leer_llenados(r)[-1]["evento"] == "STOP_EJECUTADO"
    est = RE.cargar_estado(r)
    assert est["posiciones"] == [] and len(est["cerradas"]) == 1
    assert AR.leer_registro(r)[-1]["tarea"] == "registrar-llenado --real"


def test_apagado_la_ronda_muestra_lo_urgente_y_el_cierre(mundo, capsys):
    r, _, foto, correr = mundo
    _con_posicion(r, estado_stop="SIN_STOP")
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00013), [])               # BTC en la cuenta y ningún stop
    r.datos["real"]["activo"] = False
    capsys.readouterr()
    assert correr(simular=True) == 2
    salida = capsys.readouterr().out
    assert "❌ URGENTE: BTC no tiene stop confirmado (estado SIN_STOP)" in salida
    assert "❌ URGENTE: SIN_STOP en BTCUSDT — EJECUTOR debe cerrar ya" in salida
    assert salida.index("URGENTE") < salida.index(APAGADO)
    assert not RR.archivo_boletos(r, "2026-11-15").exists()       # con --simular no se escribe
    assert correr() == 2
    (b,) = json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
    assert b["accion"] == "CERRAR" and b["motivo"] == "SIN_STOP" and b["urgente"] is True
    capsys.readouterr()
    assert correr() == 2                                          # repetida: se muestran, no se rehacen
    assert "  " + b["texto"] in capsys.readouterr().out.splitlines()


def test_apagado_compra_enviada_sigue_bloqueada(compra, monkeypatch, capsys):
    r, b, _ = compra
    r.datos["real"]["activo"] = False
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_ENVIADA",
                      "--precio-actual", "70000"]) == 2
    assert capsys.readouterr().out.startswith(f"{APAGADO}registrar-llenado --real no hizo nada")
    assert not RE.archivo_llenados(r).exists() or RE.leer_llenados(r) == []
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 2
    salida = capsys.readouterr().out
    assert f"❌ {b['boleto_id']}: NO compres: el dinero real está APAGADO" in salida and "✅" not in salida


def test_apagado_verificar_aprueba_el_cierre(mundo, capsys):
    r, _, foto, correr = mundo
    _con_posicion(r, estado_stop="SIN_STOP")
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00013), [])
    r.datos["real"]["activo"] = False
    assert correr() == 2
    (b,) = json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 0
    salida = capsys.readouterr().out
    assert salida.startswith(f"{APAGADO}ronda --verificar --real no hizo nada con las compras")
    assert f"✅ {b['boleto_id']}" in salida


def test_apagado_sin_nada_real_no_crea_nada(tmp_path, capsys):
    from apoyo_real import reg_real
    r = reg_real(tmp_path)
    assert RR._proteger_apagado(r, AHORA) == []
    assert capsys.readouterr().out == "" and not RE.ruta_real(r).exists()
    assert set(RE.SE_ANOTAN_APAGADO) & {"COMPRA_ENVIADA", "COMPRA_LLENADA", "COMPRA_PARCIAL", "COMPRA_NO_LLENADA"} == set()


def test_apagado_sin_posicion_solo_dice_lo_urgente(mundo, monkeypatch, capsys):
    from sobreviviente import papel as P
    r, _, foto, correr = mundo
    RE.guardar_estado(r, RE.estado_nuevo(142.54, "2026-11-14"))   # sin posiciones
    foto()
    r.datos["real"]["activo"] = False
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no se piden datos")))
    capsys.readouterr()
    assert correr() == 2
    assert not RR.archivo_boletos(r, "2026-11-15").exists()


def test_apagado_estado_danado_no_arma_nada(mundo, capsys):
    r, _, _, correr = mundo
    RE.archivo_estado(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    r.datos["real"]["activo"] = False
    capsys.readouterr()
    assert correr() == 2
    salida = capsys.readouterr().out
    assert "❌ URGENTE: no pude leer el estado real" in salida and not RR.archivo_boletos(r, "2026-11-15").exists()


def test_apagado_si_binance_falla_lo_dice_como_urgente(mundo, monkeypatch, capsys):
    from sobreviviente import papel as P
    r, _, foto, correr = mundo
    _con_posicion(r)
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00013), [])
    r.datos["real"]["activo"] = False
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **k: type("D", (), {"no_opera": "BTCUSDT en BREAK"})())
    capsys.readouterr()
    assert correr() == 2
    salida = capsys.readouterr().out
    assert "❌ URGENTE: con el real apagado no pude armar los boletos que protegen (BTCUSDT en BREAK)" in salida
    assert not RR.archivo_boletos(r, "2026-11-15").exists() and AR.leer_registro(r) == []


def test_apagado_los_urgentes_de_la_decision_tambien_salen(mundo, monkeypatch, capsys):
    r, _, foto, correr = mundo
    RE.guardar_estado(r, RE.estado_nuevo(142.54, "2026-11-14"))
    foto(cuenta(usdt=142.54, btc=0.0005), [])                      # BTC libre que el estado no conoce
    monkeypatch.setattr(RR, "_ventas_sin_anotar",
                        lambda reg, dd, est, out, dia, ahora: out["urgentes"].append("❌ URGENTE: prueba"))
    r.datos["real"]["activo"] = False
    capsys.readouterr()
    assert correr() == 2
    assert "❌ URGENTE: prueba" in capsys.readouterr().out.splitlines()
    assert json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8")) == []
