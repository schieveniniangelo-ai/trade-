"""Arreglo 176: un renglón ilegible en llenados.jsonl BLOQUEA las compras reales (falla cerrada).

Antes, `leer_llenados` brincaba en silencio los renglones que no podía leer. Si el renglón cortado era un COMPRA_ENVIADA
(el EJECUTOR se cayó a la mitad de escribirlo), la compra enviada desaparecía: nadie la marcaba SIN STOP y se podía
mandar otra compra encima. Ahora:
* `real.llenados_rotos` dice qué renglones no se leen (los vacíos no cuentan);
* COMPRA_ENVIADA sale ❌ «NO mandes la compra: llenados.jsonl tiene … renglón(es) ilegible(s) …»;
* `conciliar --real` sale ❌ con el mismo aviso (y la ronda real no compra);
* al escribir un renglón nuevo, si el último quedó sin salto de línea, primero se cierra; luego flush y fsync.
Lo que protege (STOP_PUESTO, ventas) se sigue anotando igual.
"""
import json
from datetime import timedelta

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA
from test_arreglo134_entradas_real import FILTROS, mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

DIA2 = AHORA + timedelta(days=1)
LLENADA = dict(orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013, moneda_comision="BTC")


def _cortado(boleto_id):
    """Un COMPRA_ENVIADA que quedó a la mitad (sin cerrar el JSON ni el renglón)."""
    fila = json.dumps({"hora_utc": "2026-11-16T00:13:00+00:00", "boleto_id": boleto_id, "evento": "COMPRA_ENVIADA"})
    return fila[:len(fila) // 2]


def _escribir(r, texto):
    arch = RE.archivo_llenados(r)
    arch.parent.mkdir(parents=True, exist_ok=True)
    arch.write_text(texto, encoding="utf-8")


def _otro_boleto(r, dia="2026-11-16"):
    b2 = RE.boleto_compra_real(r, dia, "BTCUSDT", 70000.0, 59500.0, 0.00013, FILTROS, DIA2)
    RR.archivo_boletos(r, dia).write_text(json.dumps([b2]), encoding="utf-8")
    return b2


def test_renglon_cortado_de_compra_enviada_no_permite_otra_compra(compra):
    r, b, _ = compra
    _escribir(r, _cortado(b["boleto_id"]))
    assert RE.leer_llenados(r) == [] and RE.llenados_rotos(r) == [1]
    b2 = _otro_boleto(r)
    ok, msgs = RE.registrar_llenado(r, b2["boleto_id"], "COMPRA_ENVIADA", ahora=DIA2 + timedelta(minutes=1))
    assert not ok
    assert msgs[0].startswith("NO mandes la compra: llenados.jsonl tiene 1 renglón(es) ilegible(s) (renglón 1): puede "
                              "ser una COMPRA_ENVIADA cortada")
    assert "Ángelo revise y arregle datos/real/llenados.jsonl" in msgs[0]
    assert RE.leer_llenados(r) == []                                   # no se anotó nada


def test_por_la_linea_de_comandos(compra, monkeypatch, capsys):
    r, b, _ = compra
    _escribir(r, "{roto\n")
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_ENVIADA"]) == 1
    assert capsys.readouterr().out.startswith("❌ NO mandes la compra: llenados.jsonl tiene 1 renglón(es) ilegible(s)")


def test_conciliar_sale_con_x(compra):
    r, b, foto = compra
    foto()
    assert RE.conciliar(r, AHORA)["ok"]
    _escribir(r, "\n" + json.dumps({"boleto_id": "x", "evento": "COMPRA_NO_LLENADA"}) + "\n3\n" + _cortado("y"))
    res = RE.conciliar(r, AHORA)
    assert not res["ok"] and res["diferencias"]["llenados_rotos"] == [3, 4]
    assert any(not ok and t.startswith("llenados.jsonl tiene 2 renglón(es) ilegible(s) (renglón 3, 4)")
               for ok, t in res["lineas"])


def test_muchos_renglones_rotos_dice_los_primeros(compra):
    r, b, _ = compra
    _escribir(r, "roto\n" * 7)
    assert "(renglón 1, 2, 3, 4, 5 …)" in RE.aviso_llenados_rotos(RE.llenados_rotos(r))


def test_la_ronda_real_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    foto()
    _escribir(r, _cortado("20261114-RA-COM-BTC-00000000"))
    assert correr() == 0
    assert not [x for x in json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
                if x["accion"] == "COMPRAR"]
    assert "llenados.jsonl tiene 1 renglón(es) ilegible(s)" in capsys.readouterr().out


def test_lo_que_protege_se_anota_igual_y_en_su_propio_renglon(compra):
    r, b, _ = compra
    _escribir(r, _cortado("20261114-RA-COM-BTC-00000000"))             # sin salto de línea al final
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", ahora=AHORA + timedelta(minutes=2), **LLENADA)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "STOP_PUESTO", orden_id=888, stop_id=b["id_stop"],
                                ahora=AHORA + timedelta(minutes=3))[0]
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["COMPRA_LLENADA", "STOP_PUESTO"]
    assert RE.llenados_rotos(r) == [1]                                  # el cortado sigue ahí (lo revisa Ángelo)
    assert RE.archivo_llenados(r).read_text(encoding="utf-8").endswith("\n")


def test_sin_renglones_rotos_no_cambia_nada(compra):
    r, b, _ = compra
    assert RE.llenados_rotos(r) == []                                   # no existe el archivo
    _escribir(r, "\n\n")
    assert RE.llenados_rotos(r) == []
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1))
    assert ok and msgs[0].startswith("👍 Compra ENVIADA anotada")
    assert RE.archivo_llenados(r).read_text(encoding="utf-8").startswith("\n\n{")
