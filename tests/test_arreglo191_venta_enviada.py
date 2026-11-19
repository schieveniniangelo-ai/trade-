"""Arreglo 191: VENTA_ENVIADA se anota ANTES de vender, igual que COMPRA_ENVIADA (170), para que el código frene un
reintento.

Antes, la venta de un boleto CERRAR (cierre de una posición o venta urgente) solo tenía la regla de texto del 181: «antes
de reintentar, revisa con spot.getOrder». Nada en el código frenaba un segundo intento. Ahora:
* el EJECUTOR anota `registrar-llenado --real --evento VENTA_ENVIADA` ANTES de tocar nada (antes de cancelar el stop);
* otra VENTA_ENVIADA del mismo boleto sale ❌ «NO repitas la venta» mientras la anterior no tenga resultado: la salida
  (VENTA_LLENADA, STOP_EJECUTADO o CIERRE_DE_EMERGENCIA) o VENTA_NO_LLENADA (con --motivo) si Binance dice que no existe;
* después de un VENTA_NO_LLENADA se puede reintentar UNA vez; un segundo reintento sale ❌;
* con la venta ya anotada, VENTA_ENVIADA sale ❌; una VENTA_LLENADA sin VENTA_ENVIADA se anota con aviso.
El boleto, su texto y bots/4_EJECUTOR_REAL.md (pasos 5 y 5b) lo dicen."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA
from test_arreglo131_conciliar_real import POS
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
DIA = "2026-11-20"
T0 = AHORA + timedelta(days=5)


@pytest.fixture
def cierre(mundo):
    r = mundo[0]
    RE.guardar_estado(r, {**RE.cargar_estado(r), "posiciones": [dict(POS)]})
    b = RE.boleto_cierre_real(r, DIA, POS, "SALIDA_M0")
    v = RE.boleto_venta_sin_anotar(r, DIA, "BTCUSDT", 0.00004, 70000.0, FILTROS)
    RR.archivo_boletos(r, DIA).parent.mkdir(parents=True, exist_ok=True)
    RR.archivo_boletos(r, DIA).write_text(json.dumps([b, v]), encoding="utf-8")
    return r, b, v


def _ev(r, b, evento, minutos=0, **kw):
    return RE.registrar_llenado(r, b["boleto_id"], evento, ahora=T0 + timedelta(minutes=minutos), **kw)


def test_anotar_antes_de_vender(cierre):
    r, b, _ = cierre
    ok, msgs = _ev(r, b, "VENTA_ENVIADA")
    assert ok and msgs == [f"👍 Venta ENVIADA anotada ({b['boleto_id']}). Ahora sí manda la venta: orden_venta del boleto, "
                           f"tal cual (newClientOrderId={b['id_venta']}). Cuando sepas cómo terminó, anótalo: VENTA_LLENADA "
                           f"(o la salida que corresponda) si se hizo; VENTA_NO_LLENADA con --motivo si Binance dice que no "
                           f"existe o la rechazó. Hasta entonces el programa no deja anotar otra VENTA_ENVIADA de este "
                           f"boleto."]
    fila = RE.leer_llenados(r)[-1]
    assert (fila["boleto_id"], fila["evento"]) == (b["boleto_id"], "VENTA_ENVIADA")
    assert RE.cargar_estado(r)["posiciones"] == [POS]                       # no cambia el estado


def test_el_codigo_frena_el_reintento_sin_resultado(cierre):
    r, b, _ = cierre
    assert _ev(r, b, "VENTA_ENVIADA")[0]
    ok, msgs = _ev(r, b, "VENTA_ENVIADA", 2)
    assert not ok and msgs[0].startswith("NO repitas la venta: ya hay una VENTA_ENVIADA de este boleto sin resultado (")
    assert f"revisa con spot.getOrder (origClientOrderId={b['id_venta']})" in msgs[0]
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["VENTA_ENVIADA"]   # no se anotó nada
    assert RE.ventas_sin_resultado(RE.leer_llenados(r), b["boleto_id"])[0]["evento"] == "VENTA_ENVIADA"


def test_un_reintento_despues_de_no_llenada_y_no_mas(cierre):
    r, b, _ = cierre
    assert _ev(r, b, "VENTA_ENVIADA")[0]
    ok, msgs = _ev(r, b, "VENTA_NO_LLENADA", 1)
    assert not ok and msgs[0].startswith("falta --motivo")
    ok, msgs = _ev(r, b, "VENTA_NO_LLENADA", 1, motivo="no existe en Binance (spot.getOrder)")
    assert ok and msgs == ["👍 Anotado: la venta no se hizo (no existe en Binance (spot.getOrder)). La posición sigue SIN "
                           "vender: puedes reintentar UNA vez (anota antes otra VENTA_ENVIADA)."]
    ok, msgs = _ev(r, b, "VENTA_ENVIADA", 2)
    assert ok and "Ahora sí manda el reintento" in msgs[0]
    assert _ev(r, b, "VENTA_NO_LLENADA", 3, motivo="-2010")[1][0].endswith(
        "ya no se reintenta: avisa a THE BOSS con prioridad máxima (Ángelo protege o vende a mano en Binance).")
    ok, msgs = _ev(r, b, "VENTA_ENVIADA", 4)
    assert not ok and msgs[0].startswith("NO mandes la venta otra vez: ya se mandó 2 veces")
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["VENTA_ENVIADA", "VENTA_NO_LLENADA", "VENTA_ENVIADA",
                                                          "VENTA_NO_LLENADA"]


def test_con_la_venta_anotada_no_se_envia_otra(cierre):
    r, b, _ = cierre
    assert _ev(r, b, "VENTA_ENVIADA")[0]
    ok, msgs = _ev(r, b, "VENTA_LLENADA", 1, cantidad=0.00012, precio=71000.0, comision=0.0085, moneda_comision="USDT")
    assert ok and not any("No se anotó VENTA_ENVIADA" in m for m in msgs)
    assert RE.cargar_estado(r)["posiciones"] == []
    ok, msgs = _ev(r, b, "VENTA_ENVIADA", 2)
    assert not ok and msgs == ["la venta de ese boleto ya está anotada (VENTA_LLENADA): NO la repitas"]
    assert RE.ventas_sin_resultado(RE.leer_llenados(r), b["boleto_id"]) == []
    assert not _ev(r, b, "VENTA_NO_LLENADA", 3, motivo="x")[0]


def test_venta_llenada_sin_enviada_se_anota_con_aviso(cierre):
    r, b, _ = cierre
    ok, msgs = _ev(r, b, "VENTA_LLENADA", cantidad=0.00012, precio=71000.0, comision=0.0085, moneda_comision="USDT")
    assert ok and any(m.startswith("⚠️ No se anotó VENTA_ENVIADA antes de mandar esta venta") for m in msgs)


def test_la_venta_urgente_tambien(cierre):
    r, _, v = cierre
    assert _ev(r, v, "VENTA_ENVIADA")[0]
    assert not _ev(r, v, "VENTA_ENVIADA", 1)[0]
    assert _ev(r, v, "VENTA_LLENADA", 2, cantidad=0.00004, precio=70000.0)[0]


def test_fuera_de_orden(cierre, mundo):
    r, b, _ = cierre
    ok, msgs = _ev(r, b, "VENTA_NO_LLENADA", motivo="x")
    assert not ok and msgs == ["VENTA_NO_LLENADA sin una VENTA_ENVIADA sin resultado antes (fuera de orden)"]
    RE.guardar_estado(r, {**RE.cargar_estado(r), "posiciones": []})
    assert _ev(r, b, "VENTA_ENVIADA")[1] == ["VENTA_ENVIADA de una posición que el estado real no tiene (fuera de orden)"]
    informativo = RE.boleto_cierre_real(r, DIA, POS, "STOP_EJECUTADO")
    RR.archivo_boletos(r, DIA).write_text(json.dumps([informativo]), encoding="utf-8")
    assert _ev(r, informativo, "VENTA_ENVIADA")[1] == ["ese boleto no es una venta (CERRAR con orden_venta)"]


def test_por_la_linea_de_comandos(cierre, monkeypatch, capsys):
    r, b, _ = cierre
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(RE, "ahora_utc", lambda: T0)
    args = ["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "VENTA_ENVIADA"]
    assert MAIN.main(args) == 0 and capsys.readouterr().out.startswith("👍 Venta ENVIADA anotada")
    assert MAIN.main(args) == 1 and capsys.readouterr().out.startswith("❌ NO repitas la venta")


def test_textos(cierre):
    r, b, v = cierre
    for x in (b, v):
        frase = (f"ANTES de tocar nada anota la venta: registrar-llenado --real --boleto {x['boleto_id']} --evento "
                 f"VENTA_ENVIADA; si sale ❌, NO vendas y sigue lo que dice")
        assert x["antes_de_vender"] == frase and frase in x["texto"]
        assert x["texto"].index(frase) < x["texto"].index("VENDE")
    assert b["texto"].index("VENTA_ENVIADA") < b["texto"].index("cancela el stop")
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    p5 = ej[ej.index("5. Boleto de CIERRE"):ej.index("5b. Boleto de VENTA URGENTE")]
    p5b = ej[ej.index("5b. Boleto de VENTA URGENTE"):ej.index("6. Foto final")]
    for p in (p5, p5b):
        assert "`registrar-llenado --real --boleto <ID> --evento VENTA_ENVIADA`" in p and "NO vendas" in p
        assert p.index("VENTA_ENVIADA") < p.index("vende con `spot.newOrder`")
        assert "VENTA_NO_LLENADA" in p
    assert p5.index("VENTA_ENVIADA") < p5.index("cancela el stop")


def test_venta_enviada_con_hora_ilegible_igual_frena(cierre):
    r, b, _ = cierre
    RE._escribir_renglon(RE.archivo_llenados(r), {"hora_utc": "quién sabe", "boleto_id": b["boleto_id"],
                                                  "evento": "VENTA_ENVIADA"})
    ok, msgs = _ev(r, b, "VENTA_ENVIADA", 1)
    assert not ok and "sin resultado (sin hora)" in msgs[0]
