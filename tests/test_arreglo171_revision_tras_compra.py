"""Arreglo 171: revisar justo después de cada compra real.

Antes, después de STOP_PUESTO nadie revisaba hasta la ronda del día siguiente (~24 h). Ahora:
* STOP_PUESTO deja pendiente la «revisión justo después de la compra» y dice qué correr EN SEGUIDA: foto de saldo nueva
  (registrar-saldo) y `conciliar --real`.
* `conciliar --real` con una foto tomada DESPUÉS de la compra hace la revisión: si cuadra, la borra; si no cuadra,
  bloquea las compras (solo Ángelo las reanuda): no se compra nada más.
* Con una foto de ANTES de la compra no juzga (da ❌ y pide repetir la foto): así no marca un SIN STOP falso que haría
  que la ronda siguiente mandara vender. Si el EJECUTOR no revisa, la conciliación de la ronda siguiente es la revisión.
* COMPRA_ENVIADA sale ❌ («NO mandes la compra») con compras bloqueadas, cartera detenida, revisión pendiente o una
  posición sin stop ACTIVO.
El código no vende solo: solo marca, bloquea y avisa. El texto del boleto y bots/4_EJECUTOR_REAL.md lo dicen.
"""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo131_conciliar_real import POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
DIA2 = AHORA + timedelta(days=1)
USDT = 142.54 - 0.00013 * 70100
CLAVE = "revision_despues_de_compra"


def _comprar(r, b):
    """El EJECUTOR siguiendo el paso 4: COMPRA_ENVIADA, compra, stop en el acto, COMPRA_LLENADA y STOP_PUESTO."""
    def llenar(evento, **kw):
        ok, msgs = RE.registrar_llenado(r, b["boleto_id"], evento, ahora=AHORA + timedelta(minutes=2), **kw)
        assert ok, msgs
        return msgs
    llenar("COMPRA_ENVIADA", precio_actual=70000.0)          # arreglo 182
    llenar("COMPRA_LLENADA", orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")
    return llenar("STOP_PUESTO", orden_id=888, stop_id=b["id_stop"])


def _stop(b, cantidad="0.00012000"):
    return orden_stop(cantidad=cantidad, client=b["id_stop"], order_id=888)


def test_stop_puesto_deja_la_revision_pendiente_y_dice_que_correr(compra):
    r, b, _ = compra
    msgs = _comprar(r, b)
    assert RE.cargar_estado(r)[CLAVE] == {"boleto": b["boleto_id"],
                                          "desde": (AHORA + timedelta(minutes=2)).isoformat(timespec="seconds")}
    aviso = next(m for m in msgs if "AHORA MISMO" in m)
    assert "registrar-saldo" in aviso and "conciliar --real" in aviso and "SIN STOP" in aviso
    assert "no se compra nada más" in aviso


def test_con_foto_nueva_que_cuadra_se_borra_la_revision(compra):
    r, b, foto = compra
    _comprar(r, b)
    foto(cuenta(usdt=USDT, btc_bloq=0.00012), [_stop(b)], ahora=AHORA + timedelta(minutes=5))
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    assert res["ok"], res["lineas"]
    assert f"revisión justo después de la compra (boleto {b['boleto_id']}): cuadra" in [t for _, t in res["lineas"]]
    est = RE.cargar_estado(r)
    assert CLAVE not in est and est["bloqueo_compras"] is None and est["posiciones"][0]["estado_stop"] == "ACTIVO"


def test_con_foto_nueva_que_no_cuadra_bloquea_y_avisa(compra, monkeypatch, capsys):
    r, b, foto = compra
    _comprar(r, b)
    foto(cuenta(usdt=USDT, btc_bloq=0.00012), [_stop(b, "0.00011000")], ahora=AHORA + timedelta(minutes=5))
    original = RE.conciliar
    monkeypatch.setattr(RE, "conciliar", lambda reg, ahora=None, escribir=True:
                        original(reg, AHORA + timedelta(minutes=6), escribir))
    capsys.readouterr()
    assert cli_real.conciliar_real(r) == 1
    salida = capsys.readouterr().out
    motivo = f"la revisión justo después de la compra (boleto {b['boleto_id']}) no cuadró"
    assert f"❌ {motivo}: no se compra nada más hasta que Ángelo revise (reanudar --cartera REAL)" in salida
    assert "el stop de BTC no es el anotado" in salida and "Avisa a THE BOSS de inmediato" in salida
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"]["motivo"] == motivo and CLAVE not in est
    assert est["posiciones"][0]["estado_stop"] == "ACTIVO"        # no se marca SIN STOP: el stop sí existe


def test_con_la_foto_de_antes_de_la_compra_no_juzga(compra):
    r, b, _ = compra                    # la única foto es la de las 6:07 p. m., de antes de la compra
    _comprar(r, b)
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    assert not res["ok"] and res["sin_stop"] == [] and res["diferencias"] == {}
    assert any(f"es de antes de la compra del boleto {b['boleto_id']}" in e and "registrar-saldo" in e
               for e in res["errores"])
    est = RE.cargar_estado(r)
    assert est["posiciones"][0]["estado_stop"] == "ACTIVO" and est["bloqueo_compras"] is None   # sin SIN STOP falso
    assert est[CLAVE]["boleto"] == b["boleto_id"]                                              # sigue pendiente


def test_si_no_se_revisa_la_ronda_siguiente_es_la_revision(compra, capsys):
    r, b, foto = compra
    _comprar(r, b)
    foto(cuenta(usdt=USDT, btc_bloq=0.00012), [_stop(b)], ahora=DIA2 - timedelta(minutes=5))
    capsys.readouterr()
    assert RR.correr(r, DIA2, cliente=object(), memes=[]) == 0
    est = RE.cargar_estado(r)
    assert CLAVE not in est and est["bloqueo_compras"] is None
    assert not [x for x in json.loads(RR.archivo_boletos(r, "2026-11-16").read_text(encoding="utf-8"))
                if x.get("urgente")]


@pytest.mark.parametrize("desde", ["no se entiende", "2026-11-16T00:14:00"])     # rara, o sin zona horaria
def test_una_revision_con_hora_rara_no_se_queda_pegada(compra, desde):
    r, b, foto = compra
    RE.guardar_estado(r, {**RE.cargar_estado(r), CLAVE: {"boleto": b["boleto_id"], "desde": desde}})
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=5))
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    assert res["ok"] and CLAVE not in RE.cargar_estado(r)          # se revisó con la foto válida que había


@pytest.mark.parametrize("cambio, pedazo", [
    ({"bloqueo_compras": {"desde": "2026-11-16T00:00:00+00:00", "motivo": "SIN STOP: BTC"}}, "compras reales bloqueadas"),
    ({"detenido": True}, "DETENIDA"),
    ({CLAVE: {"boleto": "20261114-RA-COM-BTC-00000000", "desde": "2026-11-15T00:20:00+00:00"}},
     "falta la revisión después de la compra"),
    ({"posiciones": [{**POS, "estado_stop": "SIN_STOP", "paso_cantidad": 0.00001}]}, "no tiene su stop ACTIVO"),
])
def test_compra_enviada_se_rechaza_si_no_se_puede_comprar(compra, monkeypatch, capsys, cambio, pedazo):
    r, b, _ = compra
    RE.guardar_estado(r, {**RE.cargar_estado(r), **cambio})
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                    precio_actual=70000.0)
    assert not ok and msgs[0].startswith("NO mandes la compra") and pedazo in msgs[0] and "THE BOSS" in msgs[0]
    assert RE.leer_llenados(r) == []
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_ENVIADA"]) == 1
    assert capsys.readouterr().out.startswith("❌ NO mandes la compra")


def test_textos_del_boleto_y_del_ejecutor(compra):
    r, b, _ = compra
    assert b["despues_del_stop"] == RE.REVISION_DESPUES_DEL_STOP
    assert "registrar-saldo" in b["despues_del_stop"] and "conciliar --real" in b["despues_del_stop"]
    t = b["texto"]
    assert t.index("registra COMPRA_LLENADA y STOP_PUESTO") < t.index("conciliar --real") < t.index("Vence a las")
    assert "no se compra nada más" in t and "promesa de ganancia" in t
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso4 = ej[ej.index("4. Boleto de COMPRA"):ej.index("5. Boleto de CIERRE")]
    revision = paso4.index("-m sobreviviente conciliar --real")
    assert paso4.index("--evento STOP_PUESTO") < revision < paso4.index("Si el stop se rechaza")
    assert "SIN STOP" in paso4[revision:] and "no se compra nada más" in paso4[revision:]
    contesta = next(x for x in ej.splitlines() if x.startswith("7. Contesta a THE BOSS"))
    assert "conciliar --real" in contesta
