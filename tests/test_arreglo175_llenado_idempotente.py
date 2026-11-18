"""Arreglo 175: registrar un llenado real es idempotente.

Antes, `registrar_llenado` guardaba el estado (cartera_REAL.json) y DESPUÉS anotaba el renglón en llenados.jsonl. Si el
EJECUTOR se caía entre los dos pasos, el estado ya tenía la posición pero el renglón no estaba: al reintentar, no veía
el evento repetido y agregaba OTRA posición (el doble de BTC anotado). Ahora:
* primero se anota el renglón (flush + fsync) y después el estado;
* si el evento ya está en llenados.jsonl y el estado no lo tiene (caída entre los dos pasos), el reintento completa el
  estado con lo que ya estaba anotado, sin agregar otro renglón;
* si el estado ya lo tiene y falta el renglón (estado viejo, de antes del 175), solo se anota el renglón;
* si ese id de orden ya está anotado con ese evento, no se agrega nada.
"""
import json
from datetime import timedelta

import pytest

from sobreviviente import real as RE

from apoyo_real import AHORA
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")


def _llenar(r, b, evento, minutos=2, **kw):
    return RE.registrar_llenado(r, b["boleto_id"], evento, ahora=AHORA + timedelta(minutes=minutos), **kw)


def _eventos(r):
    return [(x["boleto_id"], x["evento"]) for x in RE.leer_llenados(r)]


def _caer_al_guardar(monkeypatch):
    """El proceso se cae justo después de anotar el renglón, antes de guardar el estado."""
    def caida(reg, est):
        raise KeyboardInterrupt("se cayó el EJECUTOR")
    monkeypatch.setattr(RE, "guardar_estado", caida)


def test_caida_entre_los_dos_pasos_y_reintento_deja_una_sola_posicion(compra, monkeypatch):
    r, b, _ = compra
    with monkeypatch.context() as m:
        _caer_al_guardar(m)
        with pytest.raises(KeyboardInterrupt):
            _llenar(r, b, "COMPRA_LLENADA", **LLENADA)
    assert _eventos(r) == [(b["boleto_id"], "COMPRA_LLENADA")]      # el renglón ya quedó
    assert RE.cargar_estado(r)["posiciones"] == []                  # el estado no
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", 3, **LLENADA)        # reintento
    assert ok and "se cortó entre los dos pasos" in msgs[0] and "sin agregar otro renglón" in msgs[0]
    (p,) = RE.cargar_estado(r)["posiciones"]
    assert p["id"] == b["boleto_id"] and p["cantidad_comprada"] == 0.00013 and p["orden_id_compra"] == 777
    assert p["t_entrada"] == (AHORA + timedelta(minutes=2)).isoformat(timespec="seconds")   # la hora anotada
    assert _eventos(r) == [(b["boleto_id"], "COMPRA_LLENADA")]
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", 4, **LLENADA)        # un tercer intento ya no hace nada
    assert not ok and "ya está registrado" in msgs[0]
    assert len(RE.cargar_estado(r)["posiciones"]) == 1 and len(RE.leer_llenados(r)) == 1


def test_estado_guardado_sin_renglon_solo_anota_el_renglon(compra):
    """Como quedaba antes del 175 si se caía después de guardar el estado: el reintento no agrega otra posición."""
    r, b, _ = compra
    assert _llenar(r, b, "COMPRA_LLENADA", **LLENADA)[0]
    RE.archivo_llenados(r).write_text("", encoding="utf-8")         # se perdió el renglón
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", 3, **LLENADA)
    assert ok and "anoté solo el renglón" in msgs[0]
    assert len(RE.cargar_estado(r)["posiciones"]) == 1
    assert _eventos(r) == [(b["boleto_id"], "COMPRA_LLENADA")]


def test_id_de_orden_de_la_posicion_aunque_cambie_el_boleto_de_lugar(compra):
    r, b, _ = compra
    assert _llenar(r, b, "COMPRA_LLENADA", **LLENADA)[0]
    est = RE.cargar_estado(r)
    est["posiciones"][0]["id"] = "otro-id"                          # solo coincide el id de orden
    RE.guardar_estado(r, est)
    RE.archivo_llenados(r).write_text("", encoding="utf-8")
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", 3, **LLENADA)
    assert ok and "anoté solo el renglón" in msgs[0] and len(RE.cargar_estado(r)["posiciones"]) == 1


def test_stop_puesto_caida_y_reintento(compra, monkeypatch):
    r, b, _ = compra
    assert _llenar(r, b, "COMPRA_LLENADA", **LLENADA)[0]
    with monkeypatch.context() as m:
        _caer_al_guardar(m)
        with pytest.raises(KeyboardInterrupt):
            _llenar(r, b, "STOP_PUESTO", 3, orden_id=888, stop_id=b["id_stop"])
    assert RE.cargar_estado(r)["posiciones"][0]["estado_stop"] == "SIN_STOP"
    ok, msgs = _llenar(r, b, "STOP_PUESTO", 4, orden_id=888, stop_id=b["id_stop"])
    assert ok and "completé el estado" in msgs[0]
    est = RE.cargar_estado(r)
    assert est["posiciones"][0]["estado_stop"] == "ACTIVO" and est["posiciones"][0]["orden_id_stop"] == 888
    assert est[RE.REVISION]["boleto"] == b["boleto_id"]
    assert [e for _, e in _eventos(r)] == ["COMPRA_LLENADA", "STOP_PUESTO"]
    assert not _llenar(r, b, "STOP_PUESTO", 5, orden_id=888, stop_id=b["id_stop"])[0]


def test_stop_puesto_activo_sin_renglon_solo_anota_el_renglon(compra):
    r, b, _ = compra
    assert _llenar(r, b, "COMPRA_LLENADA", **LLENADA)[0]
    assert _llenar(r, b, "STOP_PUESTO", 3, orden_id=888, stop_id=b["id_stop"])[0]
    filas = RE.archivo_llenados(r).read_text(encoding="utf-8").splitlines()
    RE.archivo_llenados(r).write_text(filas[0] + "\n", encoding="utf-8")    # se perdió el renglón del stop
    ok, msgs = _llenar(r, b, "STOP_PUESTO", 4, orden_id=888, stop_id=b["id_stop"])
    assert ok and "anoté solo el renglón" in msgs[0]
    assert [e for _, e in _eventos(r)] == ["COMPRA_LLENADA", "STOP_PUESTO"]


def test_stop_repetido_sin_compra_en_el_estado_pide_la_compra(compra, monkeypatch):
    r, b, _ = compra
    with monkeypatch.context() as m:
        _caer_al_guardar(m)
        with pytest.raises(KeyboardInterrupt):
            _llenar(r, b, "COMPRA_LLENADA", **LLENADA)
    arch = RE.archivo_llenados(r)
    with open(arch, "a", encoding="utf-8") as f:
        f.write(json.dumps({"boleto_id": b["boleto_id"], "evento": "STOP_PUESTO", "orden_id": 888}) + "\n")
    ok, msgs = _llenar(r, b, "STOP_PUESTO", 4, orden_id=888, stop_id=b["id_stop"])
    assert not ok and "reintenta primero COMPRA_LLENADA" in msgs[0]


def test_salida_caida_y_reintento_no_cierra_dos_veces(compra, monkeypatch):
    r, b, _ = compra
    assert _llenar(r, b, "COMPRA_LLENADA", **LLENADA)[0]
    assert _llenar(r, b, "STOP_PUESTO", 3, orden_id=888, stop_id=b["id_stop"])[0]
    with monkeypatch.context() as m:
        _caer_al_guardar(m)
        with pytest.raises(KeyboardInterrupt):
            _llenar(r, b, "CIERRE_DE_EMERGENCIA", 4, cantidad=0.00012, precio=70000.0)
    assert len(RE.cargar_estado(r)["posiciones"]) == 1
    fila = json.loads(RE.archivo_llenados(r).read_text(encoding="utf-8").splitlines()[-1])
    fila["hora_utc"] = "no se entiende"                             # sin hora: usa la de ahora
    lineas = RE.archivo_llenados(r).read_text(encoding="utf-8").splitlines()[:-1] + [json.dumps(fila)]
    RE.archivo_llenados(r).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    ok, msgs = _llenar(r, b, "CIERRE_DE_EMERGENCIA", 5, cantidad=0.00012, precio=70000.0)
    assert ok and "completé el estado" in msgs[0]
    est = RE.cargar_estado(r)
    assert est["posiciones"] == [] and len(est["cerradas"]) == 1
    assert est["cerradas"][0]["t_salida"] == (AHORA + timedelta(minutes=5)).isoformat(timespec="seconds")
    # el estado ya la tiene y se pierde el renglón: solo el renglón
    lineas = RE.archivo_llenados(r).read_text(encoding="utf-8").splitlines()[:-1]
    RE.archivo_llenados(r).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    ok, msgs = _llenar(r, b, "CIERRE_DE_EMERGENCIA", 6, cantidad=0.00012, precio=70000.0)
    assert ok and "anoté solo el renglón" in msgs[0] and len(RE.cargar_estado(r)["cerradas"]) == 1


def test_orden_ya_anotada_en_otro_boleto_no_agrega_nada(compra):
    r, b, _ = compra
    arch = RE.archivo_llenados(r)
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text(json.dumps({"boleto_id": "otro", "evento": "COMPRA_LLENADA", "orden_id": "777"}) + "\n",
                    encoding="utf-8")
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", **LLENADA)
    assert not ok and msgs == ["la orden 777 ya está anotada como COMPRA_LLENADA en llenados.jsonl: no agrego nada "
                               "(arreglo 175)"]
    assert RE.cargar_estado(r)["posiciones"] == [] and len(RE.leer_llenados(r)) == 1


def test_parcial_anotada_y_luego_llenada_sigue_rechazada(compra):
    r, b, _ = compra
    assert _llenar(r, b, "COMPRA_PARCIAL", **LLENADA)[0]
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", 3, **{**LLENADA, "orden_id": 778})
    assert not ok and msgs == ["la compra de ese boleto ya está registrada"]
    assert len(RE.cargar_estado(r)["posiciones"]) == 1


def test_el_renglon_se_baja_a_disco_antes_que_el_estado(compra, monkeypatch):
    r, b, _ = compra
    import os
    orden = []
    monkeypatch.setattr(os, "fsync", lambda fd: orden.append("fsync"))
    guardar = RE.guardar_estado
    monkeypatch.setattr(RE, "guardar_estado", lambda reg, est: (orden.append("estado"), guardar(reg, est)))
    assert _llenar(r, b, "COMPRA_LLENADA", **LLENADA)[0]
    assert orden[:2] == ["fsync", "estado"]
