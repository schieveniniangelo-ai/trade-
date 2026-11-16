"""Arreglo 133: compuertas y ronda real, parte 1 (cierra R5).

En vez de un solo bloqueo, `compuertas_real` dice cada causa con ❌ y qué hacer. Las de puerta (M0 vivo, los demás
motores APAGADOS y nada de Futuros, la decisión escrita de Ángelo, el estado real legible) detienen todo; las de
compra (foto y conciliación, hora, freno o pausa) solo frenan compras. Prueba de oro: con las mismas velas y el mismo
reglamento, la ronda de papel da los mismos boletos y estados que antes de esta tanda (e216bd5)."""
import gzip
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import doctor
from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

import oro_papel_escenario as ORO
from apoyo_real import AHORA, reg_real
from test_papel import _datos_dia

RAIZ = Path(__file__).resolve().parent.parent


def reg_vivo(tmp_path):
    r = reg_real(tmp_path, **{"real.decision_angelo": "2026-11-15"})
    for k in r.estrategias:
        r.datos["estrategias"][k]["estado"] = "APAGADA"
    r.datos["estrategias"]["M0"]["estado"] = "VIVA_MINI"
    return r


def test_puerta_con_el_reglamento_de_hoy_dice_que_falta(tmp_path):
    r = reg_real(tmp_path)
    malos = RR.compuertas_puerta(r)
    assert any(m.startswith("M0 está en PAPEL") for m in malos)
    assert any("real.decision_angelo" in m for m in malos)
    assert all("→" in m for m in malos)                      # cada causa dice qué hacer


def test_puerta_en_orden(tmp_path):
    assert RR.compuertas_puerta(reg_vivo(tmp_path)) == []


def test_puerta_cada_compuerta_por_separado(tmp_path):
    r = reg_vivo(tmp_path)
    r.datos["estrategias"]["E5"]["estado"] = "PAPEL"
    assert RR.compuertas_puerta(r) == ["E5 está en PAPEL (un motor de Futuros): en real solo corre M0 → déjalo APAGADA."]
    r = reg_vivo(tmp_path)
    r.datos["estrategias"]["M1"]["estado"] = "PAPEL"
    assert RR.compuertas_puerta(r) == ["M1 está en PAPEL (un motor): en real solo corre M0 → déjalo APAGADA."]
    r = reg_vivo(tmp_path)
    r.datos["carteras"]["A"]["posiciones_max"]["futuros"] = 1
    assert "posiciones_max" in RR.compuertas_puerta(r)[0]
    r = reg_vivo(tmp_path)
    r.datos["real"]["decision_angelo"] = "2026-11-16"
    assert "decisión escrita" in RR.compuertas_puerta(r)[0]
    r = reg_vivo(tmp_path)
    RE.archivo_estado(r).parent.mkdir(parents=True)
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert "dañado" in RR.compuertas_puerta(r)[0]
    r = reg_vivo(tmp_path / "otro")
    r.datos["estrategias"]["M0"]["estado"] = "VIVA"
    assert RR.compuertas_puerta(r) == []


def test_compuertas_de_compra(tmp_path):
    r = reg_vivo(tmp_path)
    ok_hora = {"estado": "OK", "retraso_min": 2}
    bien = {"ok": True, "errores": [], "diferencias": {}}
    assert RR.compuertas_compra(r, AHORA, ok_hora, bien, RE.estado_nuevo(142.54, "")) == []
    assert "FUERA DE HORA" in RR.compuertas_compra(r, AHORA, {"estado": "FUERA_DE_HORA", "retraso_min": 300}, bien, None)[0]
    assert "conciliación" in RR.compuertas_compra(r, AHORA, ok_hora, {"ok": False, "errores": ["no hay foto"],
                                                                        "diferencias": {}}, None)[0]
    assert "DETENIDA" in RR.compuertas_compra(r, AHORA, ok_hora, bien, {**RE.estado_nuevo(1, ""), "detenido": True})[0]
    pausa = {**RE.estado_nuevo(1, ""), "pausa_hasta": (AHORA + timedelta(hours=5)).isoformat(), "pausa_motivo": "tope"}
    assert "pausa" in RR.compuertas_compra(r, AHORA, ok_hora, bien, pausa)[0]
    # todas juntas: sin foto (no hay conciliación) y lo de la puerta
    assert any("conciliación" in m for m in RR.compuertas_real(r, AHORA))
    assert RR.compuertas_real(reg_real(tmp_path / "x"), AHORA)[0].startswith("M0 está en PAPEL")


def test_comando_ronda_real_se_niega_y_dice_que_falta(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(MAIN, "_reg", lambda args: reg_real(tmp_path))
    assert MAIN.main(["ronda", "--modo", "real"]) == 2
    salida = capsys.readouterr().out
    assert "❌ M0 está en PAPEL" in salida and "ninguna estrategia ha pasado las compuertas" not in salida
    assert MAIN.main(["ronda", "--modo", "papel", "--simular"]) == 2
    assert "solo para la ronda real" in capsys.readouterr().out


@pytest.fixture
def ronda_falsa(monkeypatch):
    def preparar(reg, cli, memes, ahora=None, **kw):
        dd, _ = _datos_dia(reg, 400)
        return dd
    monkeypatch.setattr(P, "preparar_datos", preparar)
    return object()


def test_simular_corre_y_no_escribe_nada(tmp_path, ronda_falsa, capsys):
    r = reg_vivo(tmp_path)
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[], simular=True) == 0
    salida = capsys.readouterr().out
    assert "████ REAL ████ Ronda REAL del 2026-11-15" in salida and "SIMULACIÓN: no se escribió nada" in salida
    assert "❌ Sin compras: la conciliación real no cuadra" in salida      # no hay foto de saldo
    assert not RE.ruta_real(r).exists() and not RR.archivo_boletos(r, "2026-11-15").exists()


def test_ronda_real_escribe_y_repetida_no_crea_nada(tmp_path, ronda_falsa, capsys):
    r = reg_vivo(tmp_path)
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 0
    assert json.loads(RR.archivo_boletos(r, "2026-11-15").read_text(encoding="utf-8")) == []
    fila = json.loads((RE.ruta_real(r) / "bitacora_real.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert fila["dia_procesado"] == "2026-11-15" and fila["conciliacion_ok"] is False and fila["boletos"] == 0
    assert RE.archivo_conciliacion(r).exists() and (RE.ruta_real(r) / "ronda.lock").exists()
    assert not (tmp_path / "datos" / "papel" / "ronda.lock").exists()   # el candado real va aparte
    capsys.readouterr()
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 0
    assert "ya corrió" in capsys.readouterr().out
    RR.archivo_boletos(r, "2026-11-15").write_text("{roto", encoding="utf-8")
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 1


def test_temprano_fuera_de_hora_y_falla(tmp_path, ronda_falsa, monkeypatch, capsys):
    r = reg_vivo(tmp_path)
    assert RR.correr(r, AHORA.replace(minute=2), cliente=ronda_falsa, memes=[], simular=True) == 1
    assert "muy temprano" in capsys.readouterr().out
    assert RR.correr(r, AHORA.replace(hour=5), cliente=ronda_falsa, memes=[], simular=True) == 0
    assert "FUERA DE HORA" in capsys.readouterr().out
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **k: (_ for _ in ()).throw(OSError("sin red")))
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 1
    salida = capsys.readouterr().out
    assert "❌ La ronda real NO corrió: sin red" in salida and not RR.archivo_boletos(r, "2026-11-15").exists()


def test_doctor_informa_el_real_sin_bloquear(tmp_path, monkeypatch):
    r = reg_real(tmp_path)
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    salida = []
    codigo = doctor.revisar(r, imprimir=salida.append)
    texto = "\n".join(salida)
    assert "ℹ️ Real: M0 está en PAPEL" in texto and "ℹ️ Real: no hay foto de saldo" in texto
    assert "ℹ️ Real: conciliación real NO ok" in texto and codigo == 0
    import os
    from apoyo_real import cuenta, escribir_entrada
    c, o = escribir_entrada(tmp_path, cuenta(), [])
    RE.registrar_saldo(r, c, o, lambda s: 70000.0)
    salida.clear()
    doctor.revisar(r, imprimir=salida.append)
    assert any(x.startswith("ℹ️ Real: foto de saldo de hace") for x in salida)


def test_oro_el_papel_da_lo_mismo_que_antes_de_la_tanda():
    with gzip.open(Path(__file__).parent / "datos_arreglo133" / "oro_papel_e216bd5.json.gz", "rt", encoding="utf-8") as f:
        antes = json.load(f)
    ahora = ORO.normalizar(ORO.correr(RAIZ))
    assert sorted({b["accion"] for v in antes["boletos"].values() for b in v}) == ["CERRAR", "COMPRAR", "MODIFICAR_STOP"]
    assert ahora["boletos"] == antes["boletos"]
    assert ORO.diferencias(ahora["resumenes"], antes["resumenes"]) == []    # números: tolerancia de 1 ULP (142)
    assert ORO.diferencias(ahora["estados"], antes["estados"]) == []
