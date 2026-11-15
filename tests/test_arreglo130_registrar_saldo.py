"""Arreglo 130: `registrar-saldo --cuenta … --ordenes …` convierte la respuesta tal cual del conector en la foto de saldo.

Nadie teclea números. Sin canTrade, con un archivo roto o sin la hora: ❌. Regla anti-doble-compra: BTC con valor de
más de 1 USDT en la cuenta y sin posición real anotada → ❌ y la ronda real no compra."""
import json
import os
import time
from datetime import timedelta

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_real
from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta, escribir_entrada, orden_stop, reg_real
from test_arreglo129_base_real import POSICION

PRECIO = lambda s: 70000.0   # noqa: E731


@pytest.fixture
def r(tmp_path):
    return reg_real(tmp_path)


def _correr(r, tmp_path, cta, ordenes, precio=PRECIO, ahora=None):
    c, o = escribir_entrada(tmp_path, cta, ordenes)
    ahora = ahora or AHORA
    for p in (c, o):                                    # los archivos se "guardaron" un minuto antes
        os.utime(p, (ahora.timestamp() - 60, ahora.timestamp() - 60))
    return RE.registrar_saldo(r, c, o, precio, ahora=ahora)


def test_cuenta_limpia_queda_la_foto(r, tmp_path):
    ok, msgs = _correr(r, tmp_path, cuenta(BNB=0.001), [], ahora=AHORA)
    assert ok and msgs == []
    foto = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert foto["ok"] is True and foto["usdt_libre"] == 142.54 and foto["usdt_bloqueado"] == 0.0
    assert foto["hora_utc"] == "2026-11-16T00:12:00+00:00" and foto["update_time_cuenta"] == 1763251900000
    assert foto["activos"] == {"USDT": {"libre": 142.54, "bloqueado": 0.0}, "BNB": {"libre": 0.001, "bloqueado": 0.0}}
    assert foto["otros"] == ["BNB"] and foto["ordenes_abiertas"] == []
    assert (RE.ruta_real(r) / "saldos" / "2026-11-16_001.json").exists()
    assert RE.leer_foto(r, AHORA + timedelta(minutes=30)) == (foto, "")
    _correr(r, tmp_path, cuenta(), [])
    assert (RE.ruta_real(r) / "saldos" / "2026-11-16_002.json").exists()   # la foto del día se numera


def test_respuesta_envuelta_y_ordenes(r, tmp_path):
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, ""), "posiciones": [dict(POSICION)]})
    ok, _ = _correr(r, tmp_path, cuenta(usdt=133.43, btc=0.0, btc_bloq=0.00012, envolver=True),
                    {"data": [orden_stop()]})
    assert ok
    foto = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert foto["ordenes_abiertas"] == [{"simbolo": "BTCUSDT", "id": 123, "clientOrderId": "sp0123456789abcdef",
                                         "lado": "SELL", "tipo": "STOP_LOSS_LIMIT", "estado": "NEW",
                                         "cantidad": 0.00012, "stopPrice": 59500.0, "precio": 59202.5}]
    assert foto["otros"] == []                          # BTC es de una posición real anotada


@pytest.mark.parametrize("cta, ordenes, palabra", [
    (cuenta(can_trade=False), [], "canTrade"),
    ({k: v for k, v in cuenta().items() if k != "updateTime"}, [], "hora"),
    ({"hola": 1}, [], "balances"),
    (cuenta(), {"x": 1}, "no es una lista"),
    (cuenta(), [{"symbol": "BTCUSDT"}], "formato raro"),
    ({**cuenta(), "accountType": "MARGIN"}, [], "no SPOT"),
    ({**cuenta(), "balances": [{"asset": "USDT", "free": "mucho", "locked": "0"}]}, [], "formato raro"),
])
def test_formato_malo_dice_no_y_la_foto_no_sirve(r, tmp_path, cta, ordenes, palabra):
    _correr(r, tmp_path, cuenta(), [])                  # una foto buena anterior…
    ok, msgs = _correr(r, tmp_path, cta, ordenes)
    assert not ok and any(palabra in m for m in msgs)
    foto, por_que = RE.leer_foto(r, AHORA)              # …ya no se usa: la última salió con ❌
    assert foto["ok"] is False and "❌" in por_que


def test_archivo_roto_o_que_falta(r, tmp_path):
    c, o = escribir_entrada(tmp_path, cuenta(), [])
    c.write_text("{roto", encoding="utf-8")
    ok, msgs = RE.registrar_saldo(r, c, tmp_path / "no_existe.json", PRECIO, ahora=None)
    assert not ok and any("roto" in m for m in msgs) and any("no existe" in m for m in msgs)


def test_archivos_viejos_no_sirven(r, tmp_path):
    c, o = escribir_entrada(tmp_path, cuenta(), [])
    viejo = time.time() - 3 * 3600
    os.utime(c, (viejo, viejo))
    ok, msgs = RE.registrar_saldo(r, c, o, PRECIO)
    assert not ok and any("se guardó hace" in m for m in msgs)


def test_anti_doble_compra(r, tmp_path):
    ok, msgs = _correr(r, tmp_path, cuenta(btc=0.00013), [])
    assert not ok and any("que el estado real no conoce" in m for m in msgs)
    ok, msgs = _correr(r, tmp_path, cuenta(btc=0.00013), [], precio=lambda s: None)
    assert not ok and any("no pude leer su precio" in m for m in msgs)
    ok, msgs = _correr(r, tmp_path, cuenta(btc=0.00000013), [])     # polvo de comisión: menos de 1 USDT
    assert ok and msgs and msgs[0].startswith("ℹ️")
    RE.archivo_estado(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    ok, msgs = _correr(r, tmp_path, cuenta(), [])
    assert not ok and any("dañado" in m for m in msgs)


def test_leer_foto_falla_cerrada(r, tmp_path):
    assert RE.leer_foto(r, AHORA) == (None, "no hay foto de saldo (EJECUTOR debe correr registrar-saldo)")
    _correr(r, tmp_path, cuenta(), [])
    foto, por_que = RE.leer_foto(r, AHORA + timedelta(minutes=121))
    assert foto is not None and "121 min" in por_que
    RE.archivo_saldo(r).write_text("{roto", encoding="utf-8")
    assert RE.leer_foto(r, AHORA)[1].startswith("la foto de saldo está dañada")


def test_comando(r, tmp_path, monkeypatch, capsys):
    c, o = escribir_entrada(tmp_path, cuenta(), [])
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(cli_real, "precio_publico", lambda reg: PRECIO)
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 0
    assert "👍 Foto de saldo guardada" in capsys.readouterr().out
    c.write_text(json.dumps(cuenta(can_trade=False)), encoding="utf-8")
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 1
    salida = capsys.readouterr().out
    assert salida.startswith("❌ la cuenta NO tiene permiso") and "hoy no hay compras reales" in salida


def test_precio_publico_sin_red_regresa_none(r, monkeypatch):
    class Cli:
        def __init__(self, _r):
            pass

        def spot(self, ruta, params):
            if params["symbol"] == "MALUSDT":
                raise OSError("sin red")
            return {"price": "70000.5"}
    monkeypatch.setattr("sobreviviente.datos.ClienteBinance", Cli)
    p = cli_real.precio_publico(r)
    assert p("BTCUSDT") == 70000.5 and p("MALUSDT") is None
