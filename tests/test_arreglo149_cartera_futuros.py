"""Arreglo 149: Cartera F de papel de Futuros (estado propio, frenos, calor, rachas, vetos y gestión)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from sobreviviente import archivos as AR
from sobreviviente import reglamento as RGL
from sobreviviente.estrategias import f1 as F1
from sobreviviente.exchange import Filtros
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import config
from sobreviviente.futuros import tamano as T

CFG = dict(config.POR_DEFECTO)
AHORA = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)      # miércoles
F_SOL = Filtros(simbolo="SOLUSDT", tick=0.01, paso=0.01, cantidad_min=0.01, minimo_usdt=5.0)
F_XRP = Filtros(simbolo="XRPUSDT", tick=0.0001, paso=0.1, cantidad_min=0.1, minimo_usdt=5.0)


@pytest.fixture
def reg(tmp_path):
    return RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})


def _est(**cambios):
    e = C.estado_nuevo(CFG, AHORA)
    e.update(cambios)
    return e


def _pos(simbolo="SOLUSDT", lado="LARGO", entrada=100.0, stop=95.0, cantidad=0.1, margen=10.0, liq=None):
    e = C.estado_nuevo(CFG, AHORA)
    t = T.Tamano(True, "cabe", cantidad, entrada * cantidad, 1, margen, cantidad * abs(entrada - stop), 0.0, liq)
    return C.abrir(e, simbolo, lado, entrada, entrada, stop, t, AHORA, F1.gestion(F1.POR_DEFECTO), 0.05)


def test_tope_diario_pausa_hasta_las_00_utc(reg):
    rf = C.reglamento_f1(reg, CFG)
    e = _est(dia_utc=C.R.inicio_dia_utc(AHORA).isoformat(), semana=C.R.inicio_semana(rf, AHORA).isoformat(),
             capital=42.54 * 0.97)
    msgs = C.aplicar_frenos(rf, e, AHORA)
    assert msgs and e["pausa_hasta"] == "2026-11-19T00:00:00+00:00"
    assert C.bloqueos_entrada(rf, e, "SOLUSDT", AHORA)
    assert not C.bloqueos_entrada(rf, e, "SOLUSDT", datetime(2026, 11, 19, 0, 1, tzinfo=timezone.utc))


def test_tope_semanal_pausa_hasta_el_lunes(reg):
    rf = C.reglamento_f1(reg, CFG)
    cap = 42.54 * 0.94
    e = _est(dia_utc=C.R.inicio_dia_utc(AHORA).isoformat(), semana=C.R.inicio_semana(rf, AHORA).isoformat(),
             capital=cap, capital_inicio_dia=cap)
    C.aplicar_frenos(rf, e, AHORA)
    hasta = datetime.fromisoformat(e["pausa_hasta"])
    assert hasta.weekday() == 0 and "semanal" in e["pausa_motivo"]
    assert hasta == C.R.siguiente_lunes(rf, AHORA)


def test_quince_por_ciento_desde_el_pico_lo_detiene_todo(reg):
    rf = C.reglamento_f1(reg, CFG)
    e = _est(pico=50.0, capital=42.5, capital_inicio_dia=42.5, capital_inicio_semana=42.5,
             dia_utc=C.R.inicio_dia_utc(AHORA).isoformat(), semana=C.R.inicio_semana(rf, AHORA).isoformat())
    C.aplicar_frenos(rf, e, AHORA)
    assert e["detenido"] is True
    assert any("DETENIDO" in b for b in C.bloqueos_entrada(rf, e, "XRPUSDT", AHORA + timedelta(days=30)))


def test_los_frenos_de_f1_no_cambian_los_del_reglamento(reg):
    rf = C.reglamento_f1(reg, {**CFG, "tope_diario_pct": 2.0})
    assert rf.riesgo["tope_diario_pct"] == 2.0
    assert reg.riesgo["tope_diario_pct"] == 3.0 and RGL.cargar().riesgo["tope_diario_pct"] == 3.0


def test_cuatro_perdidas_seguidas_pausan_24_horas(reg):
    rf = C.reglamento_f1(reg, CFG)
    e = _est()
    for k in range(3):
        assert not C.registrar_racha(e, -0.4, AHORA, CFG)
    assert C.registrar_racha(e, -0.4, AHORA, CFG)
    assert e["pausa_racha_hasta"] == (AHORA + timedelta(hours=24)).isoformat(timespec="seconds")
    assert C.bloqueos_entrada(rf, e, "SOLUSDT", AHORA + timedelta(hours=23))
    assert not C.bloqueos_entrada(rf, e, "SOLUSDT", AHORA + timedelta(hours=24, minutes=1))
    e2 = _est()
    C.registrar_racha(e2, -0.4, AHORA, CFG)
    C.registrar_racha(e2, 0.2, AHORA, CFG)          # una ganadora reinicia la cuenta
    assert e2["perdidas_seguidas"] == 0


def test_tercera_posicion_y_misma_moneda_no_caben():
    e = _est()
    e["posiciones"] = [_pos("SOLUSDT", margen=5.0), _pos("XRPUSDT", margen=5.0)]
    t = C.cabe(CFG, e, "BNBUSDT", "LARGO", 591.45, 591.45 * 0.96, F_SOL)
    assert not t.cabe and "máximo 2" in t.razon
    e["posiciones"] = e["posiciones"][:1]
    t = C.cabe(CFG, e, "SOLUSDT", "CORTO", 71.63, 71.63 * 1.05, F_SOL)
    assert not t.cabe and "1 por moneda" in t.razon


def test_calor_de_mas_de_2_por_ciento_no_cabe():
    e = _est()
    e["posiciones"] = [_pos("XRPUSDT", entrada=1.0, stop=0.9, cantidad=6.0, margen=6.0)]   # arriesga 0.60 USDT
    t = C.cabe(CFG, e, "SOLUSDT", "LARGO", 71.63, 71.63 * 0.95, F_SOL)                    # pide 0.394
    assert not t.cabe and "calor" in t.razon
    e["posiciones"] = [_pos("XRPUSDT", entrada=1.0, stop=0.95, cantidad=6.0, margen=6.0)]  # arriesga 0.30
    assert C.cabe(CFG, e, "SOLUSDT", "LARGO", 71.63, 71.63 * 0.95, F_SOL).cabe
    assert C.calor_usdt(e) == pytest.approx(0.30)


def test_veto_global_bloquea_largo_y_corto_y_evento_fuerte(reg):
    rf = C.reglamento_f1(reg, CFG)
    e = _est()
    vetos = [{"simbolo": "GLOBAL", "razon": "hackeo", "vence": (AHORA + timedelta(hours=5)).isoformat()}]
    for s in CFG["monedas"]:
        assert any("veto" in b for b in C.bloqueos_entrada(rf, e, s, AHORA, vetos=vetos))
    eventos = [{"nombre": "Fed", "importancia": "ALTA", "fecha_hora": (AHORA + timedelta(minutes=10)).isoformat()}]
    assert any("evento" in b for b in C.bloqueos_entrada(rf, e, "SOLUSDT", AHORA, eventos=eventos))
    assert not C.bloqueos_entrada(rf, e, "SOLUSDT", AHORA)


def test_vetos_danado_no_hay_entradas(reg):
    carpeta = AR.carpeta_datos(reg)
    carpeta.mkdir(parents=True)
    (carpeta / "vetos.json").write_text("{esto no es json", encoding="utf-8")
    vetos, eventos, danado, avisos = C.leer_vetos_eventos(reg)
    assert danado and avisos
    assert any("dañado" in b for b in C.bloqueos_entrada(C.reglamento_f1(reg, CFG), _est(), "SOLUSDT", AHORA,
                                                           archivos_danados=danado))


def test_vetos_y_eventos_validos_se_leen(reg):
    carpeta = AR.carpeta_datos(reg)
    carpeta.mkdir(parents=True)
    hoy = AHORA.isoformat()
    (carpeta / "vetos.json").write_text(json.dumps({"actualizado": hoy, "vetos": []}), encoding="utf-8")
    vetos, eventos, danado, _ = C.leer_vetos_eventos(reg)
    assert not danado and vetos == []


def test_el_estado_vive_aparte_de_datos_papel(reg):
    papel = AR.carpeta_datos(reg) / "papel"
    papel.mkdir(parents=True)
    (papel / "cartera_A.json").write_text('{"capital": 142.54}', encoding="utf-8")
    antes = {p.name: p.read_bytes() for p in papel.iterdir()}
    e = C.cargar_estado(reg, CFG)
    e["capital"] = 40.0
    arch = C.guardar_estado(reg, e)
    assert arch == AR.carpeta_datos(reg) / "papel_futuros" / "F.json"
    assert C.cargar_estado(reg, CFG)["capital"] == 40.0
    assert {p.name: p.read_bytes() for p in papel.iterdir()} == antes
    arch.write_text("{roto", encoding="utf-8")
    (arch.parent / "F.json.bak").unlink(missing_ok=True)
    with pytest.raises(AR.ArchivoDanado):
        C.cargar_estado(reg, CFG)


def test_vela_liquidacion_con_marca_stop_con_max_min_y_funding():
    # Liquidación: la marca toca 60 (liq 61) aunque el último precio no toque el stop (50)
    p = _pos(entrada=100.0, stop=50.0, liq=61.0)
    salio, precio, motivo = C.procesar_vela(p, 100, 101, 70, 99, 1.0, 101, 60, False)
    assert salio and precio == 61.0 and motivo == "liquidación"
    # Stop: el mínimo de 4 h del último precio toca 95
    p = _pos(entrada=100.0, stop=95.0, liq=40.0)
    assert C.procesar_vela(p, 100, 104, 96, 103, 1.0, 104, 96, False) == (False, 0.0, "")
    assert p["stop"] == pytest.approx(101.0)                         # chandelier: 104 − 3 × 1
    salio, precio, motivo = C.procesar_vela(p, 103, 103, 100, 101, 1.0, 103, 100, False)
    assert salio and precio == pytest.approx(101.0) and motivo == "stop"
    # Corto: liquidación con el máximo de la marca
    p = _pos(lado="CORTO", entrada=100.0, stop=150.0, liq=140.0)
    assert C.procesar_vela(p, 100, 120, 99, 110, 1.0, 141, 99, False)[2] == "liquidación"
    # Funding: positivo → el largo paga y el corto cobra, sobre el valor a precio de marca
    p = _pos(cantidad=2.0)
    cobros = pd.Series([0.0001, 0.0002], index=pd.to_datetime(["2026-11-18 00:00", "2026-11-18 08:00"], utc=True))
    assert C.cobrar_funding(p, cobros, 50.0) == pytest.approx(-0.03)
    q = _pos(lado="CORTO", cantidad=2.0)
    assert C.cobrar_funding(q, cobros, 50.0) == pytest.approx(0.03) and q["funding"] == pytest.approx(0.03)


def test_cerrar_liquidacion_pierde_margen_y_tarifa_y_un_cierre_normal_suma():
    e = _est()
    t = T.Tamano(True, "cabe", 0.1, 10.0, 2, 5.0, 0.5, 0.4254, 52.0)
    p = C.abrir(e, "SOLUSDT", "LARGO", 100.0, 100.0, 95.0, t, AHORA, F1.gestion(F1.POR_DEFECTO), 0.05)
    assert e["capital"] == pytest.approx(42.54 - 0.005)
    neta = C.cerrar(e, p, 52.0, "liquidación", AHORA, CFG, 0.05, 0.05, tarifa_liq_pct=1.5)
    # Arreglo 157 (cambio A PROPÓSITO; https://www.binance.com/en/support/faq/binance-futures-liquidation-protocols-360033525271):
    # min(margen 5.0, 48 × 0.1 hasta la liquidación + 52 × 0.1 × 1.5 %) = 4.878, más la comisión de entrada.
    assert neta == pytest.approx(-(48.0 * 0.1 + 52.0 * 0.1 * 0.015) - 0.005)
    assert e["posiciones"] == [] and e["cerradas"][-1]["motivo"] == "liquidación"
    p = C.abrir(e, "XRPUSDT", "CORTO", 1.0, 1.0, 1.05, T.Tamano(True, "", 10.0, 10.0, 1, 10.0, 0.5), AHORA,
                F1.gestion(F1.POR_DEFECTO), 0.05)
    antes = e["capital"] + p["comisiones"]
    neta = C.cerrar(e, p, 0.9, "stop", AHORA, CFG, 0.05, 0.0)
    assert neta == pytest.approx((1.0 - 0.9) * 10 - 0.9 * 10 * 0.0005 - 1.0 * 10 * 0.0005)
    assert e["capital"] == pytest.approx(antes + neta)


def test_el_dia_y_la_semana_nuevos_reinician_sus_referencias(reg):
    rf = C.reglamento_f1(reg, CFG)
    e = _est()
    C.aplicar_frenos(rf, e, AHORA)
    assert e["dia_utc"] == "2026-11-18T00:00:00+00:00" and e["semana"]
    e["capital"] = 41.0
    C.aplicar_frenos(rf, e, AHORA + timedelta(days=7))           # otra semana y otro día: las referencias se mueven
    assert e["capital_inicio_semana"] == 41.0 and e["capital_inicio_dia"] == 41.0


def test_si_el_tamano_no_cabe_se_dice_por_que():
    f_btc = Filtros(simbolo="BTCUSDT", tick=0.1, paso=0.001, cantidad_min=0.001, minimo_usdt=100.0)
    t = C.cabe(CFG, _est(), "BTCUSDT", "LARGO", 64674.8, 64674.8 * 0.97, f_btc)
    assert not t.cabe and "mínimo de Binance" in t.razon
