"""Huecos de cobertura del dinero real (pedidos junto con la tanda 175–184; números de línea de 94a17e0).

* cli_real.py 87-89, 108-109, 128, 132: `ronda --verificar --real` con el archivo de boletos dañado, un boleto que truena
  al revisarlo, el boleto informativo (STOP_EJECUTADO) y BTCUSDT fuera de TRADING;
* ronda_real.py 125-128, 197, 217-219, 244-245, 249-251, 330, 332: los archivos de los bots (MODO SEGURO, vetos y
  eventos), la pausa del estado real, sin reglas de Binance, la cantidad que redondeada queda en 0, el boleto que no pasa
  su revisión y la venta urgente sin reglas o sin precio;
* real.py 885-886: `buscar_boleto` con el archivo de boletos dañado y sin copia;
* archivos.py 79-82: `escribir_json_seguro` que falla a la mitad borra su temporal y avisa (no deja el archivo a medias).
Solo pruebas: no cambia nada del paquete.
"""
import copy
import json
from datetime import timedelta

import pandas as pd
import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_real
from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import riesgo as R
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta
from test_arreglo131_conciliar_real import POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import INFO, Cli, compra  # noqa: F401 - fixture


def _boletos(r, dia="2026-11-15"):
    return json.loads(RR.archivo_boletos(r, dia).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------- cli_real.py

def test_verificar_con_el_archivo_de_boletos_danado_y_sin_copia(compra, capsys):
    r, _, _ = compra
    arch = RR.archivo_boletos(r, "2026-11-15")
    arch.write_text("{roto", encoding="utf-8")
    assert not arch.with_name(arch.name + ".bak").exists()
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 1
    salida = capsys.readouterr().out
    assert salida.startswith("❌ El archivo boletos_real_2026-11-15.json está dañado") and "No pongas nada" in salida


def test_verificar_un_boleto_que_truena_al_revisarlo_no_se_aprueba(compra, capsys):
    r, b, _ = compra
    malo = copy.deepcopy(b)
    malo["orden_compra"]["quantity"] = "no es número"
    RR.archivo_boletos(r, "2026-11-15").write_text(json.dumps([malo]), encoding="utf-8")
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), Cli()) == 1
    assert f"❌ {b['boleto_id']}: boleto mal formado (ValueError): no lo pongas" in capsys.readouterr().out


def test_verificar_el_boleto_informativo_y_btcusdt_fuera_de_trading(compra, capsys):
    r, b, _ = compra
    info = RE.boleto_cierre_real(r, "2026-11-16", POS, "STOP_EJECUTADO")
    RR.archivo_boletos(r, "2026-11-16").write_text(json.dumps([info]), encoding="utf-8")

    class EnBreak(Cli):
        def exchange_info(self, mercado="SPOT", forzar=False):
            x = copy.deepcopy(INFO)
            x["symbols"][0]["status"] = "BREAK"
            return x
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-16", AHORA + timedelta(days=1), EnBreak()) == 0   # informativo: solo él
    assert f"✅ {info['boleto_id']}" in capsys.readouterr().out
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=1), EnBreak()) == 1
    assert "Binance tiene esta moneda en estado BREAK (no TRADING)" in capsys.readouterr().out


# ----------------------------------------------------------------------------------------------- ronda_real.py

def test_archivos_de_los_bots_modo_seguro_vetos_y_eventos(mundo, monkeypatch):
    r = mundo[0]
    veto, evento = {"simbolo": "BTCUSDT"}, {"nombre": "Fed"}
    monkeypatch.setattr(AR, "leer_todos", lambda reg: {"vetos.json": ({"vetos": [veto]}, []),
                                                       "eventos.json": ({"eventos": [evento]}, []),
                                                       "exclusiones.json": (None, ["no existe datos/exclusiones.json"])})
    assert RR._archivos_bots(r) == (False, [veto], [evento])
    monkeypatch.setattr(AR, "leer_todos", lambda reg: {"vetos.json": (None, ["formato raro: falta 'vetos'"])})
    assert RR._archivos_bots(r) == (True, [], [])


def test_con_la_cartera_real_en_pausa_no_compra(mundo, capsys):
    r, _, foto, correr = mundo
    hasta = (AHORA + timedelta(days=2)).isoformat()
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "pausa_hasta": hasta, "pausa_motivo": "tope diario"})
    foto()
    assert correr() == 0 and _boletos(r) == []
    salida = capsys.readouterr().out
    assert f"la cartera REAL está en pausa (tope diario) hasta {hasta}" in salida
    assert RE.cargar_estado(r)["pausa_hasta"] == hasta


@pytest.fixture
def ronda_con(mundo, monkeypatch):
    """La ronda real del `mundo` con un cambio en los datos del día."""
    r, cfg, foto, correr = mundo
    preparar = P.preparar_datos

    def con(cambio):
        def otro(reg, cli, memes, ahora=None, **kw):
            dd = preparar(reg, cli, memes, ahora=ahora, **kw)
            cambio(dd)
            return dd
        monkeypatch.setattr(P, "preparar_datos", otro)
    return r, foto, correr, con


def test_sin_reglas_de_binance_no_compra(ronda_con, capsys):
    r, foto, correr, con = ronda_con
    con(lambda dd: dd.md.filtros.pop("BTCUSDT"))
    foto()
    assert correr() == 0 and _boletos(r) == []
    assert "⚠️ No hay reglas de Binance para BTCUSDT: hoy no se compra en real." in capsys.readouterr().out
    desc = json.loads((RE.ruta_real(r) / "descartes" / "descartes_2026-11-15.json").read_text(encoding="utf-8"))
    assert desc["carteras"]["REAL"][-1]["codigo"] == "SIN_FILTROS_O_PRECIO"


def test_la_cantidad_que_redondeada_queda_en_cero(mundo, monkeypatch):
    r, _, foto, correr = mundo
    original = R.evaluar_candidato

    def diminuta(*a, **k):
        dec = original(*a, **k)
        dec.aprobada, dec.cantidad = True, 0.000001          # menos que el paso de 0.00001
        return dec
    monkeypatch.setattr(R, "evaluar_candidato", diminuta)
    foto()
    assert correr() == 0 and _boletos(r) == []
    desc = json.loads((RE.ruta_real(r) / "descartes" / "descartes_2026-11-15.json").read_text(encoding="utf-8"))
    assert desc["carteras"]["REAL"][-1]["codigo"] == "CANTIDAD_CERO"


def test_el_boleto_que_no_pasa_su_revision_no_se_emite(mundo, monkeypatch, capsys):
    r, _, foto, correr = mundo
    monkeypatch.setattr(RE, "revisar_boleto_real", lambda reg, b, f: ["la compra no es LIMIT FOK"])
    foto()
    assert correr() == 0 and _boletos(r) == []
    assert "❌ El boleto de compra real no pasa su revisión: la compra no es LIMIT FOK. No se emite." in \
        capsys.readouterr().out


@pytest.mark.parametrize("cambio, motivo", [
    (lambda dd: dd.md.filtros.pop("BTCUSDT"), "no hay reglas de Binance (filtros) para BTCUSDT"),
    (lambda dd: dd.md.velas.pop("BTCUSDT"), "no hay precio de BTCUSDT para revisar el mínimo de Binance"),
    (lambda dd: dd.md.velas.update(BTCUSDT=pd.DataFrame({"close": []}, index=pd.DatetimeIndex([], tz="UTC"))),
     "no hay precio de BTCUSDT para revisar el mínimo de Binance"),
])
def test_venta_urgente_sin_reglas_o_sin_precio_avisa(ronda_con, capsys, cambio, motivo):
    r, foto, correr, con = ronda_con
    con(cambio)
    foto(cuenta(usdt=133.44, btc=0.00013))
    assert correr() == 0
    assert not [b for b in _boletos(r) if b.get("motivo") == RE.MOTIVO_SIN_ANOTAR]
    salida = capsys.readouterr().out
    assert (f"❌ URGENTE: hay 0.00013 BTC libres sin anotar y sin stop, pero no sale venta urgente: {motivo}. Avisa a "
            f"Ángelo con prioridad") in salida
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == "SIN STOP: BTC en la cuenta que el estado real no conoce"


# ------------------------------------------------------------------------------------------- real.py y archivos.py

def test_buscar_boleto_con_el_archivo_danado_y_sin_copia(compra):
    r, b, _ = compra
    assert RE.buscar_boleto(r, b["boleto_id"])["boleto_id"] == b["boleto_id"]
    arch = RR.archivo_boletos(r, "2026-11-15")
    arch.write_text("{roto", encoding="utf-8")
    assert RE.buscar_boleto(r, b["boleto_id"]) is None
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", motivo="EXPIRED")
    assert not ok and msgs == [f"no existe el boleto real {b['boleto_id']}"]


def test_escribir_json_seguro_que_falla_no_deja_nada_a_medias(tmp_path, monkeypatch):
    arch = tmp_path / "estado.json"
    AR.escribir_json_seguro(arch, {"v": 1})

    def falla(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(AR.os, "replace", falla)
    with pytest.raises(OSError, match="disco lleno"):
        AR.escribir_json_seguro(arch, {"v": 2})
    assert json.loads(arch.read_text(encoding="utf-8")) == {"v": 1}           # el de antes sigue entero
    assert list(tmp_path.glob("*.tmp")) == []                                   # su temporal se borró
