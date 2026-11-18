"""Arreglo 174: un archivo de boletos de papel por cartera.

Antes, A, B y C escribían sus boletos en un solo archivo (salida/boletos_<día>.json). Ahora la ronda escribe, además,
salida/boletos_<día>_A.json, _B.json y _C.json, cada uno solo con los boletos de su cartera, y al final (como siempre)
boletos_<día>.json con los de todas: sigue siendo lo último que se escribe y la marca de «la ronda terminó».
* `ronda --verificar` revisa el archivo de cada cartera: un boleto de otra cartera, un archivo que falta o que no coincide
  con el de todas es ❌ «no pongas nada». Las rondas de antes (solo el de todas) se revisan igual que siempre.
* `registrar-llenado --ensayo` busca el boleto en el archivo de su cartera (si no está, en el de todas).
* El CONTADOR sigue igual: `conciliar` no lee boletos y el reporte no cuenta dos veces los de cada cartera.
* La ronda del día siguiente corre normal y escribe sus propios archivos.
Sin red ni llaves: datos sintéticos y reglas de Binance falsas.
"""
import json
from argparse import Namespace

import pandas as pd
import pytest

from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P
from sobreviviente import reportes as RP

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

FILTROS = [{"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
           {"filterType": "LOT_SIZE", "stepSize": "0.0001", "minQty": "0.0001"},
           {"filterType": "NOTIONAL", "minNotional": "5"}]


def _leer(arch):
    return json.loads(arch.read_text(encoding="utf-8"))


def _ronda(r, monkeypatch, k):
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    info = {"symbols": [{"symbol": s, "status": "TRADING", "filters": FILTROS} for s in dd.md.velas]}
    monkeypatch.setattr(D.ClienteBinance, "exchange_info", lambda self, mercado="SPOT", forzar=False: info)
    return f"{dd.dia:%Y-%m-%d}", ahora


@pytest.fixture
def ronda(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    fecha, ahora = _ronda(r, monkeypatch, k)
    capsys.readouterr()
    return r, k, fecha, ahora


def _quitar(arch):
    for a in (arch, arch.with_name(arch.name + ".bak")):
        a.unlink(missing_ok=True)


def test_archivo_boletos_da_el_de_cada_cartera_y_el_de_todas(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    salida = tmp_path / "salida"
    assert P.archivo_boletos(r, "2026-11-17") == salida / "boletos_2026-11-17.json"
    assert [P.archivo_boletos(r, "2026-11-17", n).name for n in P.CARTERAS] == \
        ["boletos_2026-11-17_A.json", "boletos_2026-11-17_B.json", "boletos_2026-11-17_C.json"]


def test_la_cartera_de_un_boleto_sale_del_boleto_o_de_su_id():
    assert P.cartera_del_boleto({"boleto_id": "20261116-B-COM-BTC-1a2b3c4d", "cartera": "B"}) == "B"
    assert P.cartera_del_boleto({"boleto_id": "20261116-C-CER-AUSDT-1a2b3c4d", "accion": "CERRAR"}) == "C"   # sin campo
    assert P.cartera_del_boleto({"boleto_id": "20261116-RA-CER-BTC-1a2b3c4d"}) is None          # uno real no es de papel
    assert P.cartera_del_boleto({"boleto_id": "raro"}) is None and P.cartera_del_boleto("hola") is None


def test_la_ronda_escribe_un_archivo_por_cartera(ronda):
    r, _, fecha, _ = ronda
    todos = _leer(P.archivo_boletos(r, fecha))
    assert todos, "la ronda de prueba tiene que dar boletos"
    juntos = []
    for n in P.CARTERAS:
        propios = _leer(P.archivo_boletos(r, fecha, n))
        assert all(P.cartera_del_boleto(b) == n for b in propios)      # una no pisa a la otra
        assert [b["boleto_id"] for b in propios] == [b["boleto_id"] for b in todos if P.cartera_del_boleto(b) == n]
        juntos += propios
    assert sorted(b["boleto_id"] for b in juntos) == sorted(b["boleto_id"] for b in todos)
    assert CR.ronda_ya_corrio(r, fecha)


def test_verificar_revisa_el_archivo_de_cada_cartera(ronda, capsys):
    r, _, fecha, ahora = ronda
    assert CR.verificar_boletos(r, fecha, ahora=ahora) == 0
    con_archivos = capsys.readouterr().out
    assert "👍 Todos los boletos cumplen el reglamento." in con_archivos
    for b in _leer(P.archivo_boletos(r, fecha)):
        assert con_archivos.count(b["boleto_id"]) == 1                 # cada boleto una sola vez
    # Una ronda de antes del 174 (solo el archivo de todas) se revisa igual que siempre
    for n in P.CARTERAS:
        _quitar(P.archivo_boletos(r, fecha, n))
    assert CR.verificar_boletos(r, fecha, ahora=ahora) == 0
    assert sorted(capsys.readouterr().out.splitlines()) == sorted(con_archivos.splitlines())


def _boleto_de(r, fecha):
    return next(b for b in _leer(P.archivo_boletos(r, fecha)))


def test_verificar_detecta_un_archivo_pisado(ronda, capsys):
    r, _, fecha, ahora = ronda
    b = _boleto_de(r, fecha)
    otra = next(n for n in P.CARTERAS if n != P.cartera_del_boleto(b))
    arch = P.archivo_boletos(r, fecha, otra)
    arch.write_text(json.dumps(_leer(arch) + [b]), encoding="utf-8")    # el boleto quedó en el archivo de otra cartera
    assert CR.verificar_boletos(r, fecha, ahora=ahora) == 1
    salida = capsys.readouterr().out
    assert f"❌ {arch.name} trae un boleto de la cartera {P.cartera_del_boleto(b)} ({b['boleto_id']})" in salida
    assert "no pongas nada y avisa a THE BOSS" in salida and "✅" not in salida


def test_verificar_detecta_que_falta_uno(ronda, capsys):
    r, _, fecha, ahora = ronda
    _quitar(P.archivo_boletos(r, fecha, "C"))
    assert CR.verificar_boletos(r, fecha, ahora=ahora) == 1
    assert f"❌ falta boletos_{fecha}_C.json (el archivo de boletos de la cartera C)" in capsys.readouterr().out


def test_verificar_detecta_que_no_coinciden_con_el_de_todas(ronda, capsys):
    r, _, fecha, ahora = ronda
    b = _boleto_de(r, fecha)
    arch = P.archivo_boletos(r, fecha, P.cartera_del_boleto(b))
    arch.write_text(json.dumps([x for x in _leer(arch) if x["boleto_id"] != b["boleto_id"]]), encoding="utf-8")
    assert CR.verificar_boletos(r, fecha, ahora=ahora) == 1
    assert f"❌ los archivos de A, B y C no coinciden con boletos_{fecha}.json" in capsys.readouterr().out


@pytest.mark.parametrize("contenido", ["{roto", '{"no": "es lista"}'])
def test_verificar_con_un_archivo_de_cartera_danado(ronda, capsys, contenido):
    r, _, fecha, ahora = ronda
    arch = P.archivo_boletos(r, fecha, "A")
    arch.write_text(contenido, encoding="utf-8")
    arch.with_name(arch.name + ".bak").unlink(missing_ok=True)          # sin copia buena de respaldo
    assert CR.verificar_boletos(r, fecha, ahora=ahora) == 1
    salida = capsys.readouterr().out
    assert f"boletos_{fecha}_A.json" in salida and "Traceback" not in salida


def _ensayo(r, monkeypatch, b):
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    args = {"boleto": b["boleto_id"], "ensayo": True, "simbolo": b["simbolo"], "cantidad": float(b["cantidad"]),
            "precio": float(b.get("precio_entrada") or b["stop"]), "stop": b.get("stop"), "bot": "EJECUTOR",
            "reglamento": None, "real": False}
    return CR.cmd_registrar_llenado(Namespace(**args))


def test_el_ensayo_busca_en_el_archivo_de_su_cartera(ronda, monkeypatch, capsys):
    r, _, fecha, _ = ronda
    b = _boleto_de(r, fecha)
    todos = P.archivo_boletos(r, fecha)
    original = todos.read_text(encoding="utf-8")
    todos.write_text(json.dumps([x for x in _leer(todos) if x["boleto_id"] != b["boleto_id"]]), encoding="utf-8")
    assert _ensayo(r, monkeypatch, b) == 0                               # lo encontró en el de su cartera
    assert "👍 Copiado igualito al boleto." in capsys.readouterr().out
    todos.write_text(original, encoding="utf-8")                        # ronda de antes del 174: el de todas
    for n in P.CARTERAS:
        _quitar(P.archivo_boletos(r, fecha, n))
    assert _ensayo(r, monkeypatch, b) == 0


def test_el_contador_sigue_igual(ronda, capsys):
    r, _, _, _ = ronda
    assert CR.conciliar(r) == 0                                          # conciliar no lee boletos
    assert "👍 Las cuentas cuadran." in capsys.readouterr().out


def test_el_reporte_no_cuenta_dos_veces(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    salida = tmp_path / "salida"
    salida.mkdir()
    a = {"boleto_id": "x-A", "cartera": "A", "dif_apertura_pct": 0.5}
    c = {"boleto_id": "x-C", "cartera": "C", "dif_apertura_pct": 0.1}
    (salida / "boletos_2026-11-16.json").write_text(json.dumps([a, c]), encoding="utf-8")
    (salida / "boletos_2026-11-16_A.json").write_text(json.dumps([a]), encoding="utf-8")
    (salida / "boletos_2026-11-16_B.json").write_text("[]", encoding="utf-8")
    (salida / "boletos_2026-11-16_C.json").write_text(json.dumps([c]), encoding="utf-8")
    (linea,) = RP.apertura_vs_precio(r, "2026-11-10")
    assert "1 de 2 boletos con más de 0.3 %" in linea and "promedio 0.3 %" in linea


def test_la_ronda_del_dia_siguiente_no_se_bloquea(ronda, monkeypatch, capsys):
    r, k, fecha, _ = ronda
    antes = {n: P.archivo_boletos(r, fecha, n).read_bytes() for n in (*P.CARTERAS, None)}
    fecha2, _ = _ronda(r, monkeypatch, k + 1)
    salida = capsys.readouterr().out
    assert fecha2 > fecha and "ya corrió" not in salida
    assert CR.ronda_ya_corrio(r, fecha2)
    todos2 = _leer(P.archivo_boletos(r, fecha2))
    juntos2 = []
    for n in P.CARTERAS:
        propios = _leer(P.archivo_boletos(r, fecha2, n))
        assert all(P.cartera_del_boleto(b) == n for b in propios)
        juntos2 += propios
    assert sorted(b["boleto_id"] for b in juntos2) == sorted(b["boleto_id"] for b in todos2)
    assert {n: P.archivo_boletos(r, fecha, n).read_bytes() for n in (*P.CARTERAS, None)} == antes   # ayer, intacto
    for n in P.CARTERAS:                                                 # cada cartera avanzó al día nuevo
        assert P.cargar_estado(r, n, "")["ultimo_dia"] == fecha2
