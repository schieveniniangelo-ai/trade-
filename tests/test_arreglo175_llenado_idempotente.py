"""Arreglo 175 (C1): registrar un llenado real es idempotente.

Antes, `registrar_llenado` guardaba el estado (cartera_REAL.json) y DESPUÉS escribía el renglón de llenados.jsonl. Si el
programa se caía entre los dos pasos, el estado ya tenía la posición pero el renglón no existía: el reintento no veía el
evento como «ya registrado» y agregaba la posición OTRA vez (posición duplicada, el doble de BTC en libros).

Ahora primero se escribe el renglón (con flush y fsync) y después el estado. Si el mismo evento del mismo boleto ya
tiene renglón, no se agrega nada: si el estado ya lo tiene, ❌ «ya está registrado»; si no (se cayó entre los dos pasos),
se completa el estado con ESE renglón. Si el estado ya lo tiene y falta el renglón (la caída del orden viejo), solo se
escribe el renglón. Una orden de Binance (--orden-id) que ya está en otro renglón o en otra posición se rechaza.
"""
import json
from datetime import timedelta

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")


class SeFueLaLuz(Exception):
    pass


def _caer_al_guardar(monkeypatch, veces=1):
    """La próxima llamada a guardar_estado truena (el programa se cae justo después del renglón)."""
    original = RE.guardar_estado
    quedan = [veces]

    def guardar(reg, est):
        if quedan[0] > 0:
            quedan[0] -= 1
            raise SeFueLaLuz("se fue la luz entre el renglón y el estado")
        return original(reg, est)
    monkeypatch.setattr(RE, "guardar_estado", guardar)


def _llenar(r, bid, evento, minutos=2, **kw):
    return RE.registrar_llenado(r, bid, evento, ahora=AHORA + timedelta(minutes=minutos), **kw)


def _eventos(r, bid=None):
    return [x["evento"] for x in RE.leer_llenados(r) if bid is None or x["boleto_id"] == bid]


def test_caida_entre_los_dos_pasos_y_reintento_deja_una_sola_posicion(compra, monkeypatch):
    r, b, _ = compra
    _caer_al_guardar(monkeypatch)
    with pytest.raises(SeFueLaLuz):
        _llenar(r, b["boleto_id"], "COMPRA_LLENADA", **LLENADA)
    assert _eventos(r) == ["COMPRA_LLENADA"]                    # el renglón ya quedó
    assert RE.cargar_estado(r)["posiciones"] == []             # el estado no alcanzó
    ok, msgs = _llenar(r, b["boleto_id"], "COMPRA_LLENADA", minutos=3, **LLENADA)
    assert ok and msgs[0].startswith(f"⚠️ El renglón de COMPRA_LLENADA del boleto {b['boleto_id']} ya estaba en "
                                     "llenados.jsonl, pero el estado real no lo tenía")
    assert "No se agregó otro renglón" in msgs[0] and msgs[1].startswith("👍 Compra anotada: 0.00012 BTC")
    (p,) = RE.cargar_estado(r)["posiciones"]
    assert p["id"] == b["boleto_id"] and p["cantidad_neta"] == 0.00012 and p["orden_id_compra"] == 777
    assert p["t_entrada"] == (AHORA + timedelta(minutes=2)).isoformat(timespec="seconds")   # la hora es la del renglón
    assert _eventos(r) == ["COMPRA_LLENADA"]
    ok, msgs = _llenar(r, b["boleto_id"], "COMPRA_LLENADA", minutos=4, **LLENADA)      # otro reintento: nada
    assert not ok and msgs == [f"COMPRA_LLENADA del boleto {b['boleto_id']} ya está registrado: no se registra dos "
                               f"veces (no se agregó nada)"]
    assert len(RE.cargar_estado(r)["posiciones"]) == 1 and _eventos(r) == ["COMPRA_LLENADA"]


def test_el_renglon_va_primero_y_bajado_al_disco(compra, monkeypatch):
    r, b, _ = compra
    visto = []
    fsyncs = []
    original = RE.guardar_estado
    monkeypatch.setattr(RE.os, "fsync", lambda fd: fsyncs.append(fd))
    monkeypatch.setattr(RE, "guardar_estado", lambda reg, est: (visto.append((_eventos(r), len(fsyncs))),
                                                                 original(reg, est)))
    assert _llenar(r, b["boleto_id"], "COMPRA_LLENADA", **LLENADA)[0]
    assert visto == [(["COMPRA_LLENADA"], 1)]       # al guardar el estado, el renglón ya estaba y con fsync


def test_la_caida_del_orden_viejo_solo_completa_el_renglon(compra):
    """Antes del 175 el estado iba primero: si se cayó antes del renglón, el reintento NO duplica la posición."""
    r, b, _ = compra
    assert _llenar(r, b["boleto_id"], "COMPRA_LLENADA", **LLENADA)[0]
    RE.archivo_llenados(r).write_text("", encoding="utf-8")           # el renglón nunca se escribió
    ok, msgs = _llenar(r, b["boleto_id"], "COMPRA_LLENADA", minutos=3, **LLENADA)
    assert ok and msgs == [f"⚠️ El estado real ya tenía COMPRA_LLENADA del boleto {b['boleto_id']}, pero faltaba su "
                           f"renglón en llenados.jsonl: solo anoté el renglón; no se agregó nada al estado (arreglo 175)."]
    assert len(RE.cargar_estado(r)["posiciones"]) == 1 and _eventos(r) == ["COMPRA_LLENADA"]


def test_stop_puesto_caido_y_reintentado(compra, monkeypatch):
    r, b, _ = compra
    assert _llenar(r, b["boleto_id"], "COMPRA_LLENADA", **LLENADA)[0]
    _caer_al_guardar(monkeypatch)
    with pytest.raises(SeFueLaLuz):
        _llenar(r, b["boleto_id"], "STOP_PUESTO", minutos=3, orden_id=888, stop_id=b["id_stop"])
    assert RE.cargar_estado(r)["posiciones"][0]["estado_stop"] == "SIN_STOP"
    ok, msgs = _llenar(r, b["boleto_id"], "STOP_PUESTO", minutos=4, orden_id=888, stop_id=b["id_stop"])
    assert ok and "completé el estado" in msgs[0] and msgs[1].startswith("👍 Stop anotado como ACTIVO")
    est = RE.cargar_estado(r)
    assert est["posiciones"][0]["estado_stop"] == "ACTIVO" and est["posiciones"][0]["orden_id_stop"] == 888
    assert est[RE.REVISION]["desde"] == (AHORA + timedelta(minutes=3)).isoformat(timespec="seconds")
    assert _eventos(r) == ["COMPRA_LLENADA", "STOP_PUESTO"]
    assert "ya está registrado" in _llenar(r, b["boleto_id"], "STOP_PUESTO", minutos=5, orden_id=888,
                                           stop_id=b["id_stop"])[1][0]


def test_el_stop_sin_la_compra_en_el_estado_pide_repetir_la_compra_primero(compra):
    """Los renglones de la compra y del stop quedaron, el estado no tiene nada: primero se repite la compra."""
    r, b, _ = compra
    hora = (AHORA + timedelta(minutes=2)).isoformat(timespec="seconds")
    filas = [{"hora_utc": hora, "boleto_id": b["boleto_id"], "evento": "COMPRA_LLENADA", "stop_id": None, "motivo": "",
              **LLENADA},
             {"hora_utc": hora, "boleto_id": b["boleto_id"], "evento": "STOP_PUESTO", "orden_id": 888,
              "cantidad": None, "precio": None, "comision": None, "moneda_comision": None, "stop_id": b["id_stop"],
              "motivo": ""}]
    RE.archivo_llenados(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_llenados(r).write_text("".join(json.dumps(x) + "\n" for x in filas), encoding="utf-8")
    ok, msgs = _llenar(r, b["boleto_id"], "STOP_PUESTO", minutos=4, orden_id=888, stop_id=b["id_stop"])
    assert not ok and "repite primero la compra (COMPRA_LLENADA o COMPRA_PARCIAL)" in msgs[0]
    assert "No se agregó nada" in msgs[0] and RE.cargar_estado(r)["posiciones"] == []
    assert _llenar(r, b["boleto_id"], "COMPRA_LLENADA", minutos=5, **LLENADA)[0]
    assert _llenar(r, b["boleto_id"], "STOP_PUESTO", minutos=6, orden_id=888, stop_id=b["id_stop"])[0]
    (p,) = RE.cargar_estado(r)["posiciones"]
    assert p["estado_stop"] == "ACTIVO" and _eventos(r) == ["COMPRA_LLENADA", "STOP_PUESTO"]


def test_la_venta_caida_y_reintentada_cierra_una_sola_vez(compra, monkeypatch):
    r, b, _ = compra
    assert _llenar(r, b["boleto_id"], "COMPRA_LLENADA", **LLENADA)[0]
    assert _llenar(r, b["boleto_id"], "STOP_PUESTO", minutos=3, orden_id=888, stop_id=b["id_stop"])[0]
    cierre = RE.boleto_cierre_real(r, "2026-11-20", RE.cargar_estado(r)["posiciones"][0], "SALIDA_M0")
    RR.archivo_boletos(r, "2026-11-20").write_text(json.dumps([cierre]), encoding="utf-8")
    venta = dict(orden_id=999, cantidad=0.00012, precio=75000.0, comision=0.009, moneda_comision="USDT")
    _caer_al_guardar(monkeypatch)
    with pytest.raises(SeFueLaLuz):
        _llenar(r, cierre["boleto_id"], "VENTA_LLENADA", minutos=10, **venta)
    assert len(RE.cargar_estado(r)["posiciones"]) == 1
    ok, msgs = _llenar(r, cierre["boleto_id"], "VENTA_LLENADA", minutos=11, **venta)
    assert ok and "completé el estado" in msgs[0] and "Salida anotada" in msgs[1]
    est = RE.cargar_estado(r)
    assert est["posiciones"] == [] and len(est["cerradas"]) == 1
    assert est["cerradas"][0]["ganancia_usdt"] == pytest.approx(9.0 - 0.009 - 0.00013 * 70100.0)
    assert not _llenar(r, cierre["boleto_id"], "VENTA_LLENADA", minutos=12, **venta)[0]
    assert len(RE.cargar_estado(r)["cerradas"]) == 1 and _eventos(r, cierre["boleto_id"]) == ["VENTA_LLENADA"]
    # La caída del orden viejo (cerrada en el estado, sin renglón): solo se escribe el renglón
    RE.archivo_llenados(r).write_text("".join(json.dumps(x) + "\n" for x in RE.leer_llenados(r)
                                              if x["boleto_id"] != cierre["boleto_id"]), encoding="utf-8")
    ok, msgs = _llenar(r, cierre["boleto_id"], "VENTA_LLENADA", minutos=13, **venta)
    assert ok and "solo anoté el renglón" in msgs[0] and len(RE.cargar_estado(r)["cerradas"]) == 1


def test_la_venta_urgente_caida_y_reintentada_se_anota_una_vez(compra, monkeypatch):
    r, b, _ = compra
    v = RE.boleto_venta_sin_anotar(r, "2026-11-16", "BTCUSDT", 0.00013, 70000.0, FILTROS, [b["boleto_id"]])
    RR.archivo_boletos(r, "2026-11-16").write_text(json.dumps([v]), encoding="utf-8")
    _caer_al_guardar(monkeypatch)
    with pytest.raises(SeFueLaLuz):
        _llenar(r, v["boleto_id"], "VENTA_LLENADA", cantidad=0.00013, precio=69900.0)
    ok, msgs = _llenar(r, v["boleto_id"], "VENTA_LLENADA", minutos=3, cantidad=0.00013, precio=69900.0)
    assert ok and "completé el estado" in msgs[0] and msgs[1].startswith("👍 Venta urgente anotada")
    est = RE.cargar_estado(r)
    assert [x["boleto"] for x in est["ventas_sin_anotar"]] == [v["boleto_id"]]
    assert est["ventas_sin_anotar"][0]["cubre"] == [b["boleto_id"]]
    assert not _llenar(r, v["boleto_id"], "VENTA_LLENADA", minutos=4, cantidad=0.00013, precio=69900.0)[0]
    assert len(RE.cargar_estado(r)["ventas_sin_anotar"]) == 1


def test_la_misma_orden_de_binance_no_se_anota_en_otro_boleto(compra):
    r, b, _ = compra
    assert _llenar(r, b["boleto_id"], "COMPRA_LLENADA", **LLENADA)[0]
    b2 = RE.boleto_compra_real(r, "2026-11-16", "BTCUSDT", 70000.0, 59500.0, 0.00013, FILTROS, AHORA)
    RR.archivo_boletos(r, "2026-11-16").write_text(json.dumps([b2]), encoding="utf-8")
    ok, msgs = _llenar(r, b2["boleto_id"], "COMPRA_LLENADA", minutos=3, **LLENADA)
    assert not ok and msgs == [f"la orden 777 de Binance ya está anotada en llenados.jsonl (boleto {b['boleto_id']}, "
                               f"COMPRA_LLENADA): no se agrega nada. Revisa --orden-id y --boleto"]
    RE.archivo_llenados(r).write_text("", encoding="utf-8")            # solo queda en la posición
    ok, msgs = _llenar(r, b2["boleto_id"], "COMPRA_LLENADA", minutos=4, **{**LLENADA, "orden_id": "777"})
    assert not ok and msgs == [f"la orden 777 de Binance ya está anotada en la posición {b['boleto_id']}: no se agrega "
                               f"nada. Revisa --orden-id y --boleto"]
    assert len(RE.cargar_estado(r)["posiciones"]) == 1 and RE.leer_llenados(r) == []
    # Un stop con un orderId de otra clase (el de la compra) no choca: se revisa por clase de orden
    assert RE._orden_repetida([], RE.cargar_estado(r), b["boleto_id"], b["boleto_id"], "STOP_PUESTO", 777) == ""
    assert RE._orden_repetida([], RE.cargar_estado(r), "x", "x", "COMPRA_NO_LLENADA", 777) == ""


def test_por_la_linea_de_comandos_el_reintento_sale_bien(compra, monkeypatch, capsys):
    r, b, _ = compra
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    args = ["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_LLENADA", "--orden-id",
            "777", "--cantidad", "0.00013", "--precio", "70100", "--comision", "0.00000013", "--moneda-comision", "BTC"]
    _caer_al_guardar(monkeypatch)
    with pytest.raises(SeFueLaLuz):           # se cae a la mitad (sin la línea de comandos: no ensucia datos/bots)
        _llenar(r, b["boleto_id"], "COMPRA_LLENADA", **LLENADA)
    capsys.readouterr()
    assert MAIN.main(args) == 0
    salida = capsys.readouterr().out.splitlines()
    assert salida[0].startswith("⚠️ El renglón de COMPRA_LLENADA") and len(RE.cargar_estado(r)["posiciones"]) == 1
    assert MAIN.main(args) == 1
    assert "ya está registrado" in capsys.readouterr().out and len(RE.cargar_estado(r)["posiciones"]) == 1
