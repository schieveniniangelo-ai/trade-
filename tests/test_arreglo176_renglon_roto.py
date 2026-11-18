"""Arreglo 176 (C2): un renglón ilegible de llenados.jsonl BLOQUEA las compras reales (falla cerrada).

Antes, `leer_llenados` brincaba en silencio los renglones que no se podían leer. Si el EJECUTOR se caía a la mitad de
escribir un COMPRA_ENVIADA, el renglón cortado desaparecía: nadie sabía que pudo salir una compra, y se podía anotar y
mandar otra. Ahora:
* `llenados_rotos` dice qué renglones no se leen (los vacíos no cuentan) y `por_que_llenados_rotos` da el mensaje;
* COMPRA_ENVIADA sale ❌ «NO mandes la compra: llenados.jsonl … tiene 1 renglón(es) ilegible(s) …»;
* `conciliar --real` sale ❌ con ese mensaje, la ronda real no compra y `ronda --verificar --real` no aprueba compras;
* lo que ya pasó en Binance (llenados, stops, ventas) se anota igual, con aviso;
* al escribir: si falta el salto de línea del renglón anterior se pone primero, luego la fila, flush y fsync.
Los reportes siguen contando los renglones que sí se leen (`leer_llenados`).
"""
import json
from datetime import timedelta

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import Cli, compra  # noqa: F401 - fixture

ENVIADA = "COMPRA_ENVIADA"


def _cortado(bid):
    """Un COMPRA_ENVIADA que se quedó a la mitad (sin cerrar ni salto de línea)."""
    return '{"hora_utc": "2026-11-16T00:13:00+00:00", "boleto_id": "' + bid + '", "evento": "COMPRA_ENV'


def _escribir(r, texto):
    RE.archivo_llenados(r).parent.mkdir(parents=True, exist_ok=True)
    RE.archivo_llenados(r).write_text(texto, encoding="utf-8")


def test_un_compra_enviada_cortado_no_deja_mandar_la_compra(compra):
    r, b, _ = compra
    _escribir(r, _cortado(b["boleto_id"]))
    antes = RE.archivo_llenados(r).read_bytes()
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=AHORA + timedelta(minutes=2))
    assert not ok
    assert msgs[0].startswith("NO mandes la compra: llenados.jsonl (datos/real) tiene 1 renglón(es) ilegible(s) (#1): "
                              "puede ser una compra a medio anotar (un COMPRA_ENVIADA cortado)")
    assert "No se compra nada hasta que Ángelo lo revise en Binance" in msgs[0] and "THE BOSS" in msgs[0]
    assert RE.archivo_llenados(r).read_bytes() == antes                   # no se anotó nada
    assert RE.leer_llenados(r) == [] and RE.llenados_rotos(r) == [1]


def test_por_la_linea_de_comandos_sale_con_x(compra, monkeypatch, capsys):
    r, b, _ = compra
    _escribir(r, json.dumps({"evento": "COMPRA_NO_LLENADA", "boleto_id": "x"}) + "\n" + _cortado(b["boleto_id"]))
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", ENVIADA]) == 1
    assert capsys.readouterr().out.startswith("❌ NO mandes la compra: llenados.jsonl (datos/real) tiene 1 renglón(es) "
                                              "ilegible(s) (#2)")


def test_los_renglones_vacios_no_cuentan_y_los_raros_si(compra):
    r, b, _ = compra
    _escribir(r, "\n\n" + json.dumps({"evento": "X", "boleto_id": "y"}) + "\n   \n")
    assert RE.llenados_rotos(r) == [] and RE.por_que_llenados_rotos(r) == ""
    _escribir(r, "[1, 2]\n\"texto\"\n{roto\n" + "{\n" * 5)
    assert RE.llenados_rotos(r) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert "8 renglón(es) ilegible(s) (#1, #2, #3, #4, #5 y 3 más)" in RE.por_que_llenados_rotos(r)


def test_sin_archivo_no_hay_rotos(compra):
    r, _, _ = compra
    assert not RE.archivo_llenados(r).exists() and RE.llenados_rotos(r) == [] and RE.leer_llenados(r) == []


def test_lo_que_ya_paso_en_binance_se_anota_igual_en_su_propio_renglon(compra):
    r, b, _ = compra
    _escribir(r, _cortado(b["boleto_id"]))
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", cantidad=0.00013, precio=70100.0,
                                    comision=0.00000013, moneda_comision="BTC", ahora=AHORA + timedelta(minutes=2))
    assert ok and any(m.startswith("⚠️ Se anotó igual (ya pasó en Binance), pero llenados.jsonl") for m in msgs)
    texto = RE.archivo_llenados(r).read_text(encoding="utf-8")
    assert texto.startswith(_cortado(b["boleto_id"]) + "\n{") and texto.endswith("}\n")   # salto antes de la fila
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["COMPRA_LLENADA"] and RE.llenados_rotos(r) == [1]
    assert len(RE.cargar_estado(r)["posiciones"]) == 1


def test_al_escribir_salto_previo_flush_y_fsync(compra, monkeypatch):
    r, b, _ = compra
    _escribir(r, json.dumps({"evento": "X", "boleto_id": "y"}))         # el último renglón sin salto de línea
    fsyncs = []
    monkeypatch.setattr(RE.os, "fsync", lambda fd: fsyncs.append(fd))
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", ahora=AHORA + timedelta(minutes=2))[0]
    assert len(fsyncs) == 2          # el renglón y el estado (escribir_json_seguro)
    renglones = RE.archivo_llenados(r).read_text(encoding="utf-8").split("\n")
    assert len(renglones) == 3 and renglones[-1] == "" and json.loads(renglones[1])["evento"] == "COMPRA_NO_LLENADA"
    assert RE.llenados_rotos(r) == []
    RE._escribir_renglon(RE.archivo_llenados(r), {"a": 1})            # con salto al final: no agrega otro
    assert RE.archivo_llenados(r).read_text(encoding="utf-8").count("\n\n") == 0


def test_conciliar_sale_con_x_y_la_ronda_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    foto()
    _escribir(r, _cortado("20261114-RA-COM-BTC-00000000"))
    res = RE.conciliar(r, AHORA - timedelta(minutes=1))
    assert not res["ok"] and any("llenados.jsonl (datos/real) tiene 1 renglón(es) ilegible(s)" in e
                                 for e in res["errores"])
    assert RE.cargar_estado(r)["bloqueo_compras"] is None                 # no inventa un bloqueo: frena mientras siga roto
    assert any("renglón(es) ilegible(s)" in m for m in RR.compuertas_real(r, AHORA))
    assert correr() == 0
    salida = capsys.readouterr().out
    assert "❌ Sin compras: llenados.jsonl (datos/real) tiene 1 renglón(es) ilegible(s)" in salida
    assert not [b for b in json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8"))
                if b["accion"] == "COMPRAR"]


def test_conciliar_por_la_linea_de_comandos(compra, capsys):
    r, b, foto = compra
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=1))
    _escribir(r, "{roto\n")
    capsys.readouterr()
    assert cli_real.conciliar_real(r) == 1
    salida = capsys.readouterr().out
    assert "❌ llenados.jsonl (datos/real) tiene 1 renglón(es) ilegible(s) (#1)" in salida
    assert salida.splitlines()[-1].startswith("❌ Lo real NO cuadra")


def test_verificar_no_aprueba_compras_pero_si_cierres(compra, capsys):
    r, b, foto = compra
    _escribir(r, "{roto\n")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 1
    salida = capsys.readouterr().out
    assert f"❌ {b['boleto_id']}: NO compres: llenados.jsonl (datos/real) tiene 1 renglón(es) ilegible(s)" in salida
    # Un CIERRE (protege) sí se aprueba aunque haya renglones rotos
    pos = {"id": b["boleto_id"], "simbolo": "BTCUSDT", "estrategia": "M0", "cantidad_neta": 0.00012,
           "id_stop": b["id_stop"], "orden_id_stop": 888, "paso_cantidad": 0.00001}
    cierre = RE.boleto_cierre_real(r, "2026-11-16", pos, "SALIDA_M0")
    RR.archivo_boletos(r, "2026-11-16").write_text(json.dumps([cierre]), encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-16", AHORA + timedelta(days=1), Cli()) == 0
    assert f"✅ {cierre['boleto_id']}" in capsys.readouterr().out


def test_arreglado_el_renglon_se_puede_comprar_otra_vez(compra):
    r, b, foto = compra
    _escribir(r, "{roto\n")
    assert not RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=AHORA + timedelta(minutes=1))[0]
    _escribir(r, "")                                                       # Ángelo lo revisó y lo arregló
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=AHORA + timedelta(minutes=2))
    assert ok and msgs[0].startswith("👍 Compra ENVIADA anotada")
