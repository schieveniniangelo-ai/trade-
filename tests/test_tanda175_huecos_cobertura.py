"""Tanda 175–184: pruebas para los caminos del dinero real que ninguna prueba recorría.

En 94a17e0 quedaban sin cubrir (números de línea de ese commit): cli_real.py 87-89, 108-109, 128 y 132; ronda_real.py
125-128, 197, 217-219, 244-245, 249-251, 330 y 332; real.py 885-886; archivos.py 79-82. Cada prueba dice qué camino
recorre y qué tiene que pasar (no solo que se ejecute): todos son caminos de falla cerrada o de aviso.
"""
import dataclasses
import json
import os
from datetime import timedelta

import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_real
from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import riesgo as R
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, reg_real
from test_arreglo131_conciliar_real import POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import INFO, Cli, compra  # noqa: F401 - fixture


def _boletos(r, dia="2026-11-15"):
    return json.loads(RR.archivo_boletos(r, dia).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- cli_real (ronda --verificar --real)

def test_verificar_real_con_el_archivo_danado_no_aprueba_nada(tmp_path, capsys):
    """cli_real 87-89: el archivo de boletos reales está dañado y no hay copia: ❌ y no se pone nada."""
    r = reg_real(tmp_path)
    RR.archivo_boletos(r, "2026-11-15").parent.mkdir(parents=True)
    RR.archivo_boletos(r, "2026-11-15").write_text("{roto", encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA, Cli()) == 1
    salida = capsys.readouterr().out
    assert salida.startswith("❌ El archivo boletos_real_2026-11-15.json está dañado") and "No pongas nada" in salida


def test_verificar_real_boleto_mal_formado_no_tumba_la_revision(compra, capsys):
    """cli_real 108-109: un boleto que hace tronar la revisión sale ❌ «mal formado» y los demás se siguen revisando."""
    r, b, _ = compra
    malo = {"modo": "REAL", "accion": "CERRAR", "simbolo": "BTCUSDT", "apalancamiento": 1, "vence_utc": "mañana",
            "boleto_id": "malo", "version_reglamento": r.version}
    RR.archivo_boletos(r, "2026-11-15").write_text(json.dumps([malo, b]), encoding="utf-8")
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 1
    salida = capsys.readouterr().out
    assert "❌ malo: boleto mal formado (ValueError): no lo pongas" in salida and f"✅ {b['boleto_id']}" in salida


def test_verificar_real_stop_ejecutado_solo_informa(tmp_path, capsys):
    """cli_real 128: el boleto informativo de STOP_EJECUTADO no vende nada: no se le revisan venta ni vencimiento."""
    r = reg_real(tmp_path)
    b = RE.boleto_cierre_real(r, "2026-11-15", dict(POS), "STOP_EJECUTADO")
    RR.archivo_boletos(r, "2026-11-15").parent.mkdir(parents=True)
    RR.archivo_boletos(r, "2026-11-15").write_text(json.dumps([b]), encoding="utf-8")
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(days=5), Cli()) == 0
    assert f"✅ {b['boleto_id']}" in capsys.readouterr().out


def test_verificar_real_moneda_no_trading(compra, capsys):
    """cli_real 132: Binance tiene BTCUSDT en BREAK: el boleto no se pone."""
    r, b, _ = compra

    class EnBreak(Cli):
        def exchange_info(self, mercado="SPOT", forzar=False):
            return {"symbols": [{**INFO["symbols"][0], "status": "BREAK"}]}
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), EnBreak()) == 1
    assert "Binance tiene esta moneda en estado BREAK (no TRADING)" in capsys.readouterr().out


# ---------------------------------------------------------------- ronda_real

def test_archivos_de_los_bots(tmp_path):
    """ronda_real 125-128: un archivo de bot roto pone MODO SEGURO; los válidos dan sus vetos y eventos."""
    r = reg_real(tmp_path)
    carpeta = AR.carpeta_datos(r)
    carpeta.mkdir(parents=True)
    assert RR._archivos_bots(r) == (False, [], [])                     # sin archivos: nada que leer
    (carpeta / "vetos.json").write_text(json.dumps({"vetos": []}), encoding="utf-8")
    (carpeta / "eventos.json").write_text(json.dumps({"eventos": []}), encoding="utf-8")
    assert RR._archivos_bots(r) == (False, [], [])
    (carpeta / "exclusiones.json").write_text("{roto", encoding="utf-8")
    assert RR._archivos_bots(r)[0] is True


def test_pausa_de_la_cartera_real_llega_al_motor(mundo, monkeypatch):
    """ronda_real 197: la pausa anotada en el estado real pasa al motor de riesgo."""
    r, _, foto, correr = mundo
    hasta = (AHORA + timedelta(days=2)).isoformat()
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "pausa_hasta": hasta, "pausa_motivo": "tope"})
    foto()
    vistos = []
    original = R.evaluar_candidato

    def espia(rg, er, *a, **k):
        vistos.append((er.pausa_hasta, er.pausa_motivo))
        return original(rg, er, *a, **k)
    monkeypatch.setattr(R, "evaluar_candidato", espia)
    assert correr() == 0
    assert not [b for b in _boletos(r) if b["accion"] == "COMPRAR"]
    assert RE.cargar_estado(r)["pausa_hasta"] == hasta


def _sin_filtros(monkeypatch):
    original = P.preparar_datos

    def preparar(reg, cli, memes, ahora=None, **kw):
        dd = original(reg, cli, memes, ahora=ahora, **kw)
        dd.md.filtros.pop("BTCUSDT", None)
        return dd
    monkeypatch.setattr(P, "preparar_datos", preparar)


def test_sin_reglas_de_binance_no_compra(mundo, monkeypatch, capsys):
    """ronda_real 217-219: sin filtros de BTCUSDT no hay boleto de compra (falla cerrada)."""
    r, _, foto, correr = mundo
    foto()
    _sin_filtros(monkeypatch)
    assert correr() == 0 and _boletos(r) == []
    assert "⚠️ No hay reglas de Binance para BTCUSDT: hoy no se compra en real." in capsys.readouterr().out


def test_cantidad_que_redondeada_queda_en_cero(mundo, monkeypatch, capsys):
    """ronda_real 244-245: el motor aprueba una cantidad que al paso de Binance queda en 0: no hay boleto."""
    r, _, foto, correr = mundo
    foto()
    original = R.evaluar_candidato
    monkeypatch.setattr(R, "evaluar_candidato",
                        lambda *a, **k: dataclasses.replace(original(*a, **k), cantidad=0.000001))
    assert correr() == 0 and _boletos(r) == []
    desc = json.loads((RE.ruta_real(r) / "descartes" / "descartes_2026-11-15.json").read_text(encoding="utf-8"))
    assert "queda en 0" in json.dumps(desc, ensure_ascii=False)


def test_boleto_de_compra_que_no_pasa_su_revision_no_sale(mundo, monkeypatch, capsys):
    """ronda_real 249-251: si el boleto armado no pasa revisar_boleto_real, no se emite y se dice por qué."""
    r, _, foto, correr = mundo
    foto()
    monkeypatch.setattr(RE, "revisar_boleto_real", lambda reg, b, f: ["el stop no es STOP_LOSS_LIMIT de venta"])
    assert correr() == 0 and _boletos(r) == []
    assert "❌ El boleto de compra real no pasa su revisión: el stop no es STOP_LOSS_LIMIT de venta. No se emite." \
        in capsys.readouterr().out


def test_venta_urgente_sin_reglas_de_binance(mundo, monkeypatch, capsys):
    """ronda_real 330: hay BTC sin anotar pero no hay filtros: no se vende a ciegas, sale ❌ URGENTE."""
    r, _, foto, correr = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    _sin_filtros(monkeypatch)
    assert correr() == 0 and _boletos(r) == []
    salida = capsys.readouterr().out
    assert "❌ URGENTE: hay 0.00013 BTC libres sin anotar y sin stop, pero no sale venta urgente: no hay reglas de " \
           "Binance (filtros) para BTCUSDT" in salida
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"].startswith("SIN STOP: BTC")


def test_venta_urgente_sin_precio(mundo, monkeypatch, capsys):
    """ronda_real 332: hay BTC sin anotar pero no hay precio para revisar el mínimo: ❌ URGENTE."""
    r, _, foto, correr = mundo
    foto(cuenta(usdt=133.44, btc=0.00013))
    original = P.preparar_datos

    def preparar(reg, cli, memes, ahora=None, **kw):
        dd = original(reg, cli, memes, ahora=ahora, **kw)
        dd.md.velas["BTCUSDT"] = dd.md.velas["BTCUSDT"].iloc[:0]
        return dd
    monkeypatch.setattr(P, "preparar_datos", preparar)
    assert correr() == 0 and _boletos(r) == []
    assert "no sale venta urgente: no hay precio de BTCUSDT para revisar el mínimo de Binance" in capsys.readouterr().out


# ---------------------------------------------------------------- real y archivos

def test_buscar_boleto_con_el_archivo_danado(tmp_path):
    """real 885-886: el archivo de boletos reales dañado y sin copia: el boleto no existe (no se anota nada)."""
    r = reg_real(tmp_path)
    arch = RR.archivo_boletos(r, "2026-11-15")
    arch.parent.mkdir(parents=True)
    arch.write_text("{roto", encoding="utf-8")
    assert RE.buscar_boleto(r, "20261115-RA-COM-BTC-1a2b3c4d") is None
    ok, msgs = RE.registrar_llenado(r, "20261115-RA-COM-BTC-1a2b3c4d", "COMPRA_NO_LLENADA")
    assert not ok and msgs == ["no existe el boleto real 20261115-RA-COM-BTC-1a2b3c4d"]


def test_escribir_json_seguro_si_falla_no_deja_temporales(tmp_path, monkeypatch):
    """archivos 79-82: si el último paso falla, se borra el temporal, el archivo de antes queda igual y el error sube."""
    arch = tmp_path / "estado.json"
    AR.escribir_json_seguro(arch, {"v": 1})
    original = os.replace
    llamadas = []

    def falla_al_final(origen, destino):
        llamadas.append(str(destino))
        if str(destino) == str(arch):                  # la copia .bak sí se hace; el reemplazo final falla
            raise OSError("disco lleno")
        return original(origen, destino)
    monkeypatch.setattr(os, "replace", falla_al_final)
    with pytest.raises(OSError, match="disco lleno"):
        AR.escribir_json_seguro(arch, {"v": 2})
    monkeypatch.undo()
    assert json.loads(arch.read_text(encoding="utf-8")) == {"v": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["estado.json", "estado.json.bak"]
    assert llamadas[-1] == str(arch)


def test_stop_no_puesto_repetido(compra):
    """real (175): STOP_NO_PUESTO ya anotado y reflejado en el estado: no se anota dos veces."""
    r, b, _ = compra
    t = AHORA + timedelta(minutes=2)
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", orden_id=777, cantidad=0.00013, precio=70100.0,
                                comision=0.00000013, moneda_comision="BTC", ahora=t)[0]
    assert RE.registrar_llenado(r, b["boleto_id"], "STOP_NO_PUESTO", ahora=t)[0]
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "STOP_NO_PUESTO", ahora=t)
    assert not ok and "ya está registrado" in msgs[0]
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["COMPRA_LLENADA", "STOP_NO_PUESTO"]


def test_registrar_saldo_sin_hora_de_cuenta_no_compara(compra, tmp_path):
    """real (184): sin updateTime la foto ya sale ❌ por eso, y la comparación con el último llenado no truena."""
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_LLENADA", orden_id=777, cantidad=0.00013, precio=70100.0,
                                comision=0.00000013, moneda_comision="BTC", ahora=AHORA + timedelta(minutes=2))[0]
    from apoyo_real import escribir_entrada
    cta = cuenta()
    cta.pop("updateTime")
    c, o = escribir_entrada(tmp_path, cta, [])
    ok, msgs = RE.registrar_saldo(r, c, o, lambda s: 70000.0, ahora=AHORA + timedelta(minutes=5))
    assert not ok and any("no trae la hora ('updateTime')" in m for m in msgs)
    assert not any("de antes del último llenado" in m for m in msgs)
