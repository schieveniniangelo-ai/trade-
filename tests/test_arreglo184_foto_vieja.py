"""Arreglo 184 (I9): la foto de saldo se rechaza si su updateTime es de ANTES del último llenado anotado.

Antes, `registrar_saldo` solo miraba la fecha del ARCHIVO (cuenta.json guardado hace menos de 120 min). Si el EJECUTOR
copiaba otra vez una respuesta vieja de spot.getAccount (de antes de la compra), el archivo era «nuevo» y la foto pasaba,
aunque no trajera la compra: la conciliación y la ronda trabajaban con un saldo que ya no existía.

Ahora también se compara la hora de la cuenta en Binance (`updateTime`) con el último llenado anotado. Como Binance cambia
el saldo ANTES de que el EJECUTOR lo anote, no se usa la hora en que se anotó sino la más temprana posible: la del
COMPRA_ENVIADA (se anota antes de mandar la compra) y, como piso, el inicio de la ronda que emitió el boleto. Hay
`MARGEN_RELOJ_S` (5 min) de margen por los relojes.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, escribir_entrada, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")
USDT_DESPUES = 142.54 - 0.00013 * 70100.0


def _ms(t):
    return int(t.timestamp() * 1000)


def _foto_tal_cual(r, tmp_path, cta, ordenes, ahora):
    """Lo que hace registrar-saldo con los archivos tal cual (la fecha del archivo es la de `ahora`: «recién copiado»)."""
    c, o = escribir_entrada(tmp_path / "copia", cta, ordenes)
    for p in (c, o):
        os.utime(p, (ahora.timestamp() - 30, ahora.timestamp() - 30))
    return RE.registrar_saldo(r, c, o, lambda s: 70000.0, ahora=ahora)


def _comprar(r, b):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", ahora=AHORA + timedelta(minutes=3), **LLENADA)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "STOP_PUESTO", ahora=AHORA + timedelta(minutes=3), orden_id=888,
                                stop_id=b["id_stop"])[0]


def test_foto_vieja_copiada_de_nuevo_se_rechaza(compra, tmp_path):
    r, b, _ = compra
    vieja = {**cuenta(), "updateTime": _ms(AHORA - timedelta(hours=20))}      # la de ayer, sin la compra
    _comprar(r, b)
    ok, msgs = _foto_tal_cual(r, tmp_path, vieja, [], AHORA + timedelta(minutes=10))
    assert not ok
    (m,) = [x for x in msgs if "updateTime" in x]
    assert m == (f"cuenta.json es de antes del último llenado anotado: su hora en Binance (updateTime) es 10:12 p. m. del "
                 f"14/11/2026 (hora CDMX) y el COMPRA_LLENADA del boleto {b['boleto_id']} pasó después de 6:13 p. m. "
                 f"del 15/11/2026 (hora CDMX). Parece una foto vieja copiada otra vez (la fecha del archivo no basta): "
                 f"vuelve a pedir spot.getAccount y repite registrar-saldo")
    f = json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert f["ok"] is False and m in f["errores"]
    res = RE.conciliar(r, AHORA + timedelta(minutes=11))
    assert not res["ok"] and any("salió con ❌" in e for e in res["errores"])        # no se concilia con ella


def test_la_foto_nueva_de_despues_de_la_compra_sirve(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b)
    # Binance actualizó la cuenta al poner el stop (antes de que se anotara): sigue siendo después del COMPRA_ENVIADA
    nueva = {**cuenta(usdt=USDT_DESPUES, btc_bloq=0.00012), "updateTime": _ms(AHORA + timedelta(minutes=2))}
    ok, msgs = _foto_tal_cual(r, tmp_path, nueva, [orden_stop(client=b["id_stop"], order_id=888)],
                              AHORA + timedelta(minutes=10))
    assert ok, msgs
    assert RE.conciliar(r, AHORA + timedelta(minutes=11))["ok"]


def test_margen_de_reloj(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b)                                              # COMPRA_ENVIADA a las 00:13 UTC
    casi = {**cuenta(usdt=USDT_DESPUES, btc_bloq=0.00012), "updateTime": _ms(AHORA + timedelta(minutes=1)) - 299_000}
    assert _foto_tal_cual(r, tmp_path, casi, [orden_stop(client=b["id_stop"])], AHORA + timedelta(minutes=10))[0]
    fuera = {**casi, "updateTime": _ms(AHORA + timedelta(minutes=1)) - 301_000}
    assert not _foto_tal_cual(r, tmp_path, fuera, [orden_stop(client=b["id_stop"])], AHORA + timedelta(minutes=10))[0]
    assert RE.MARGEN_RELOJ_S == 300


def test_sin_llenados_no_se_compara(compra, tmp_path):
    r, b, _ = compra
    assert RE.ultimo_llenado(r) is None
    assert _foto_tal_cual(r, tmp_path, {**cuenta(), "updateTime": 1}, [], AHORA)[0]       # nada contra qué comparar
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    assert RE.ultimo_llenado(r) is None                         # COMPRA_ENVIADA sola no cambia el saldo


def test_una_venta_cuenta_desde_la_ronda_que_emitio_su_boleto(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b)
    pos = RE.cargar_estado(r)["posiciones"][0]
    cierre = RE.boleto_cierre_real(r, "2026-11-20", pos, "SALIDA_M0")
    RR.archivo_boletos(r, "2026-11-20").write_text(json.dumps([cierre]), encoding="utf-8")
    assert RE.registrar_llenado(r, cierre["boleto_id"], "VENTA_LLENADA", cantidad=0.00012, precio=75000.0,
                                ahora=datetime(2026, 11, 21, 0, 30, tzinfo=timezone.utc))[0]
    desde, fila = RE.ultimo_llenado(r)
    assert desde == datetime(2026, 11, 21, tzinfo=timezone.utc) and fila["boleto_id"] == cierre["boleto_id"]
    ahora = datetime(2026, 11, 21, 0, 40, tzinfo=timezone.utc)
    de_antes = {**cuenta(usdt=USDT_DESPUES, btc_bloq=0.00012), "updateTime": _ms(AHORA + timedelta(minutes=2))}
    assert not _foto_tal_cual(r, tmp_path, de_antes, [], ahora)[0]                    # todavía con la posición
    despues = {**cuenta(usdt=USDT_DESPUES + 9.0), "updateTime": _ms(datetime(2026, 11, 21, 0, 15, tzinfo=timezone.utc))}
    assert _foto_tal_cual(r, tmp_path, despues, [], ahora)[0]


def test_stop_ejecutado_cuenta_desde_la_compra_de_su_posicion(compra, tmp_path):
    r, b, _ = compra
    _comprar(r, b)
    pos = RE.cargar_estado(r)["posiciones"][0]
    info = RE.boleto_cierre_real(r, "2026-11-18", pos, "STOP_EJECUTADO")
    RR.archivo_boletos(r, "2026-11-18").write_text(json.dumps([info]), encoding="utf-8")
    assert RE.registrar_llenado(r, info["boleto_id"], "STOP_EJECUTADO", cantidad=0.00012, precio=59300.0,
                                ahora=datetime(2026, 11, 19, 0, 30, tzinfo=timezone.utc))[0]
    desde, fila = RE.ultimo_llenado(r)
    assert fila["evento"] == "STOP_EJECUTADO"
    assert desde == AHORA + timedelta(minutes=1)              # el stop pudo ejecutarse en cuanto se puso (antes del 18)
    # Sin su boleto no se sabe de qué posición es: no pone piso
    RR.archivo_boletos(r, "2026-11-18").unlink()
    assert RE.ultimo_llenado(r)[1]["evento"] == "COMPRA_LLENADA"


@pytest.mark.parametrize("ut", [None, True, "1763251900000"])
def test_sin_updatetime_entero_no_se_compara_aqui(compra, ut):
    r, b, _ = compra
    _comprar(r, b)
    assert RE._foto_de_antes_del_llenado(r, {"update_time_cuenta": ut}, "cuenta.json") == ""


def test_renglones_raros_no_ponen_piso(compra):
    r, b, _ = compra
    RE.archivo_llenados(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_llenados(r).write_text(json.dumps({"evento": "VENTA_LLENADA", "boleto_id": "raro"}) + "\n",
                                      encoding="utf-8")
    assert RE.ultimo_llenado(r) is None
    assert RE._hora("no es hora") is None and RE._inicio_de_la_ronda(None) is None
