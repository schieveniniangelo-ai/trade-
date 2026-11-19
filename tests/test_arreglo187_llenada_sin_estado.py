"""Arreglo 187 (R97): una compra LLENADA en llenados.jsonl que el estado real no tiene es un pendiente.

registrar-llenado --real escribe primero el renglón (con fsync) y después el estado (arreglo 175). Si el EJECUTOR se cae
entre los dos, llenados.jsonl dice COMPRA_LLENADA (o COMPRA_PARCIAL) pero cartera_REAL.json no tiene la posición ni la
cerrada: en Binance hay BTC que el estado no conoce. Antes nadie lo veía (compras_sin_anotar solo miraba los
COMPRA_ENVIADA sin resultado). Ahora cuenta como pendiente:
* conciliar --real lo marca SIN STOP, bloquea las compras y avisa a THE BOSS;
* COMPRA_ENVIADA de otra compra sale ❌ «NO mandes la compra» (aunque nadie haya conciliado);
* la ronda real (normal o saltada) lo dice como URGENTE.
Repetir el mismo registrar-llenado completa el estado con ese renglón y el pendiente desaparece."""
from datetime import timedelta

import pytest

from sobreviviente import ronda_real as RR
from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")


def _se_cae_entre_renglon_y_estado(r, b, monkeypatch, evento="COMPRA_LLENADA"):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]

    def cae(*a, **k):
        raise OSError("se fue la luz")
    with monkeypatch.context() as m:
        m.setattr(RE, "guardar_estado", cae)
        with pytest.raises(OSError):
            RE.registrar_llenado(r, b["boleto_id"], evento, ahora=AHORA + timedelta(minutes=2), **LLENADA)
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["COMPRA_ENVIADA", evento]      # el renglón sí quedó
    assert RE.cargar_estado(r)["posiciones"] == []                                       # el estado no


@pytest.mark.parametrize("evento", ["COMPRA_LLENADA", "COMPRA_PARCIAL"])
def test_la_caida_deja_un_pendiente(compra, monkeypatch, evento):
    r, b, _ = compra
    _se_cae_entre_renglon_y_estado(r, b, monkeypatch, evento)
    (x,) = RE.llenadas_sin_estado(r)
    assert x["boleto_id"] == b["boleto_id"] and x["evento"] == evento
    assert RE.compras_sin_anotar(r) == []                # el COMPRA_ENVIADA sí tiene resultado: antes nadie lo veía


def test_conciliar_lo_marca_sin_stop_y_bloquea(compra, monkeypatch):
    r, b, foto = compra
    _se_cae_entre_renglon_y_estado(r, b, monkeypatch)
    res = RE.conciliar(r, AHORA + timedelta(minutes=3))
    assert not res["ok"] and res["sin_stop"] == ["BTC"] and res["diferencias"]["llenada_sin_estado"] == [b["boleto_id"]]
    (linea,) = [t for ok, t in res["lineas"] if "llenados.jsonl" in t]
    assert linea.startswith(f"SIN STOP: BTC — el COMPRA_LLENADA del boleto {b['boleto_id']} (")
    assert ("está en llenados.jsonl, pero el estado real no tiene su posición (se cayó entre el renglón y el estado): "
            "puede haber BTC SIN STOP anotado. EJECUTOR: repite el mismo registrar-llenado --real --boleto "
            f"{b['boleto_id']} --evento COMPRA_LLENADA (completa el estado con ese renglón, no agrega otro)") in linea
    assert res["avisos"] == [RE.AVISO_SIN_ANOTAR.format(m="BTC")]
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == RE.motivo_llenada_sin_estado("BTC", b["boleto_id"]) == \
        f"SIN STOP: BTC (compra llenada que el estado real no tiene, boleto {b['boleto_id']})"


def test_no_se_manda_otra_compra_aunque_nadie_concilie(compra, monkeypatch):
    r, b, _ = compra
    _se_cae_entre_renglon_y_estado(r, b, monkeypatch)
    por_que = RE._por_que_no_comprar(RE.cargar_estado(r), r)
    assert por_que.startswith(f"el COMPRA_LLENADA del boleto {b['boleto_id']} (") and \
        por_que.endswith("No se compra nada más → no se manda otra compra")
    assert RE.cargar_estado(r).get("bloqueo_compras") is None             # sin conciliar, sin bloqueo: igual frena


def test_la_ronda_saltada_lo_dice_urgente(compra, monkeypatch):
    r, b, _ = compra
    _se_cae_entre_renglon_y_estado(r, b, monkeypatch)
    urg = RR.pendientes_urgentes(r)
    assert any(u.startswith(f"❌ URGENTE: el COMPRA_LLENADA del boleto {b['boleto_id']}") for u in urg)


def test_la_ronda_normal_lo_dice_urgente_y_no_compra(mundo, monkeypatch, capsys):
    r, cfg, foto, correr = mundo
    foto()
    assert correr() == 0
    capsys.readouterr()
    import json
    (b,) = json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
    _se_cae_entre_renglon_y_estado(r, b, monkeypatch)
    foto(cuenta(usdt=142.54 - 0.00013 * 70100.0, btc_bloq=0.00012), [orden_stop(client=b["id_stop"], order_id=888)],
         ahora=AHORA + timedelta(days=1, minutes=-5))
    assert correr(AHORA + timedelta(days=1)) == 0
    salida = capsys.readouterr().out
    assert f"❌ URGENTE: el COMPRA_LLENADA del boleto {b['boleto_id']}" in salida
    assert "❌ Sin compras: compras bloqueadas por SIN STOP: BTC" in salida
    assert not any(x.get("accion") == "COMPRAR" for x in
                   json.loads(RR.archivo_boletos(r, "2026-11-16").read_text(encoding="utf-8")))


def test_repetir_el_registro_lo_completa(compra, monkeypatch):
    r, b, foto = compra
    _se_cae_entre_renglon_y_estado(r, b, monkeypatch)
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", ahora=AHORA + timedelta(minutes=4), **LLENADA)
    assert ok and "se cayó entre los dos pasos" in msgs[0]
    assert [p["id"] for p in RE.cargar_estado(r)["posiciones"]] == [b["boleto_id"]]
    assert RE.llenadas_sin_estado(r) == []
    assert len(RE.leer_llenados(r)) == 2                                   # no se duplicó el renglón


def test_las_cerradas_y_la_venta_urgente_no_cuentan(compra):
    r, b, _ = compra
    est = RE.cargar_estado(r)
    fila = {"hora_utc": AHORA.isoformat(), "boleto_id": b["boleto_id"], "evento": "COMPRA_LLENADA"}
    RE._escribir_renglon(RE.archivo_llenados(r), fila)
    assert len(RE.llenadas_sin_estado(r, est)) == 1
    assert RE.llenadas_sin_estado(r, {**est, "cerradas": [{"id": b["boleto_id"]}]}) == []
    RE._escribir_renglon(RE.archivo_llenados(r), {"boleto_id": "x", "evento": "VENTA_LLENADA", "cubre": [b["boleto_id"]]})
    assert RE.llenadas_sin_estado(r, est) == []


def test_con_el_estado_danado_no_inventa_nada(compra):
    r, b, _ = compra
    RE._escribir_renglon(RE.archivo_llenados(r), {"boleto_id": b["boleto_id"], "evento": "COMPRA_LLENADA"})
    RE.archivo_estado(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert RE.llenadas_sin_estado(r) == []                 # el estado dañado ya frena todo por su lado
    assert any("URGENTE" in u for u in RR.pendientes_urgentes(r))


def test_la_simulacion_tambien_bloquea_en_memoria(mundo, monkeypatch, capsys):
    """Con --simular, conciliar no escribe el bloqueo: la ronda lo pone ella misma (sin guardarlo)."""
    import json
    r, cfg, foto, correr = mundo
    foto()
    assert correr() == 0
    (b,) = json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
    _se_cae_entre_renglon_y_estado(r, b, monkeypatch)
    capsys.readouterr()
    assert correr(AHORA + timedelta(days=1), simular=True) == 0
    salida = capsys.readouterr().out
    assert (f"❌ Sin compras: compras bloqueadas por SIN STOP: BTC (compra llenada que el estado real no tiene, boleto "
            f"{b['boleto_id']})") in salida
    assert RE.cargar_estado(r).get("bloqueo_compras") is None                # la simulación no escribe nada


@pytest.mark.parametrize("hora", ["no es una hora", 123])
def test_sin_hora_entendible(compra, hora):
    r, b, _ = compra
    t = RE.texto_llenada_sin_estado(r, {"boleto_id": b["boleto_id"], "evento": "COMPRA_PARCIAL", "hora_utc": hora})
    assert t.startswith(f"el COMPRA_PARCIAL del boleto {b['boleto_id']} (sin hora) está en llenados.jsonl")


def test_la_ronda_saltada_sin_poder_leer_llenados(compra, monkeypatch):
    r, b, _ = compra
    monkeypatch.setattr(RE, "llenadas_sin_estado", lambda *a, **k: (_ for _ in ()).throw(OSError("disco")))
    assert not any("llenados.jsonl, pero" in u for u in RR.pendientes_urgentes(r))
