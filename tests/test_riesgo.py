"""Pruebas del motor de riesgo (objetivo: cobertura ~100 %)."""
from datetime import datetime, timedelta

import pytest

from conftest import CDMX, hacer_cand, hacer_estado
from sobreviviente import riesgo as R
from sobreviviente.exchange import Filtros


# ---------------- Tamaño ----------------

def test_tamano_basico(filtros):
    c = hacer_cand()  # entrada 100, stop 95 → distancia 5
    t = R.calcular_tamano(1000, 1.0, 1.0, c, filtros, tope_valor_usdt=300)
    # riesgo 10 USDT / 5 = 2 unidades = 200 USDT
    assert t.ok and t.cantidad == 2.0 and t.valor_usdt == 200.0
    assert t.riesgo_usdt == pytest.approx(10.0) and t.riesgo_pct == pytest.approx(1.0)
    assert not t.recortada


def test_tamano_redondea_hacia_abajo():
    f = Filtros("X", 0.01, 0.1, 0.1, 5.0)
    c = hacer_cand(precio_entrada=100.0, stop=97.0)  # 10/3 = 3.333 → 3.3
    t = R.calcular_tamano(1000, 1.0, 1.0, c, f, 1000)
    assert t.cantidad == 3.3
    assert t.riesgo_usdt <= 10.0  # nunca se pasa del riesgo


def test_tamano_recorta_por_exposicion(filtros):
    c = hacer_cand(precio_entrada=100.0, stop=99.0)  # 10/1 = 10 unidades = 1000 USDT
    t = R.calcular_tamano(1000, 1.0, 1.0, c, filtros, tope_valor_usdt=300)
    assert t.ok and t.recortada and t.valor_usdt == pytest.approx(300.0)
    assert t.riesgo_usdt == pytest.approx(3.0)


def test_tamano_factor_regimen(filtros):
    c = hacer_cand()
    t = R.calcular_tamano(1000, 1.0, 0.5, c, filtros, 300)
    assert t.cantidad == 1.0


def test_saltada_por_capital_compra_minima():
    f = Filtros("X", 0.01, 0.001, 0.001, 5.0)
    c = hacer_cand(precio_entrada=100.0, stop=80.0)  # 0.46 / 20 = 0.023 → 2.3 USDT < 5
    t = R.calcular_tamano(46.18, 1.0, 1.0, c, f, 13.85)
    assert not t.ok and t.saltada_por_capital
    assert "mínimo" in t.razon
    # capital necesario: cantidad mínima 5/80 = 0.0625 × 20 = 1.25 USDT de riesgo → 125 USDT
    assert t.capital_necesario == pytest.approx(125.0, rel=0.01)


def test_saltada_por_venta_en_stop():
    """La compra sí llega al mínimo pero la venta en el stop no."""
    f = Filtros("X", 0.01, 0.001, 0.001, 5.0)
    c = hacer_cand(precio_entrada=10.0, stop=8.0, precio_limite_stop=7.9)
    # riesgo 1.2 / 2 = 0.6 → valor 6 USDT ≥ 5, pero en stop 0.6 × 7.9 = 4.74 < 5
    t = R.calcular_tamano(120, 1.0, 1.0, c, f, 100)
    assert not t.ok and t.saltada_por_capital and "venta en el stop" in t.razon


def test_tamano_entradas_invalidas(filtros):
    assert not R.calcular_tamano(0, 1, 1, hacer_cand(), filtros, 100).ok
    assert "equivocado" in R.calcular_tamano(1000, 1, 1, hacer_cand(stop=101), filtros, 100).razon
    assert "cero" in R.calcular_tamano(1000, 1, 0, hacer_cand(), filtros, 100).razon


def test_capital_necesario_por_exposicion():
    f = Filtros("X", 0.01, 0.001, 0.001, 5.0)
    c = hacer_cand(precio_entrada=100.0, stop=99.9)  # stop muy cerca → manda la exposición
    n = R.capital_necesario(1.0, c, f, capital=10.0, tope_actual=3.0)
    # cantidad mínima 5/99.9 ≈ 0.05005 × 100 = 5.005 USDT / 30 % = 16.68
    assert n == pytest.approx(16.68, abs=0.02)
    assert R.capital_necesario(1.0, c, f, capital=10.0, tope_actual=0) > 0


# ---------------- Costos ----------------

def test_costos(reg):
    c = hacer_cand(precio_entrada=100, stop=99.5)  # meta nominal 2R = 1 % ; costo 0.3 % × 3 = 0.9 %
    assert R.revisar_costos(reg, c)[0]
    c2 = hacer_cand(precio_entrada=100, stop=99.8)  # 2R = 0.4 % < 0.9 %
    ok, msg = R.revisar_costos(reg, c2)
    assert not ok and "cuesta" in msg
    c3 = hacer_cand(precio_entrada=100, stop=95, meta=100.5)
    assert not R.revisar_costos(reg, c3)[0]
    assert R.costo_ida_vuelta_pct(c) == pytest.approx(0.3)


# ---------------- Régimen ----------------

def test_factor_regimen(reg):
    assert R.factor_regimen(reg, "LARGO", "normales", "ALCISTA") == (1.0, None)
    f, b = R.factor_regimen(reg, "LARGO", "normales", "BAJISTA")
    assert f == 0 and "BAJISTA" in b
    assert R.factor_regimen(reg, "CORTO", "futuros", "BAJISTA") == (1.0, None)
    assert R.factor_regimen(reg, "LARGO", "memes", "BAJISTA") == (0.5, None)
    assert R.factor_regimen(reg, "LARGO", "memes", "BAJISTA", vol_moneda="ALTA") == (0.25, None)
    assert R.factor_regimen(reg, "LARGO", "normales", "ALCISTA", vol_btc="ALTA") == (0.5, None)
    assert R.factor_regimen(reg, "LARGO", "normales", "ALCISTA", vol_btc="EXTREMA")[0] == 0


def test_clasificar_volatilidad(reg):
    assert R.clasificar_volatilidad(reg, None) == "NORMAL"
    assert R.clasificar_volatilidad(reg, 96) == "EXTREMA"
    assert R.clasificar_volatilidad(reg, 85) == "ALTA"
    assert R.clasificar_volatilidad(reg, 50) == "NORMAL"
    assert R.clasificar_volatilidad(reg, 10) == "BAJA"


# ---------------- Decisión completa ----------------

def test_aprobada(reg, filtros, ahora):
    d = R.evaluar_candidato(reg, hacer_estado(), hacer_cand(), filtros, ahora, regimen_btc="ALCISTA")
    assert d.aprobada and d.cantidad == 2.0 and d.solo_papel
    for v in ["minimo_binance_ok", "calor_ok", "tope_diario_ok", "sin_veto", "sin_evento", "costos_ok"]:
        assert v in d.verificaciones
    assert d.razon == "aprobada"


def test_aprobada_recortada_viva(reg, filtros, ahora):
    reg.datos["estrategias"]["E1"]["estado"] = "VIVA_MINI"
    d = R.evaluar_candidato(reg, hacer_estado(), hacer_cand(stop=99.0), filtros, ahora)
    assert d.aprobada and not d.solo_papel and "recortada" in d.razon


def _no(reg, filtros, ahora, estado=None, cand=None, **kw):
    d = R.evaluar_candidato(reg, estado or hacer_estado(), cand or hacer_cand(), filtros, ahora, **kw)
    assert not d.aprobada
    return d.razon


def test_rechazos_globales(reg, filtros, ahora):
    assert "DETENIDO" in _no(reg, filtros, ahora, hacer_estado(detenido=True))
    e = hacer_estado(pausa_hasta=ahora + timedelta(hours=1), pausa_motivo="x")
    assert "PAUSA" in _no(reg, filtros, ahora, e)
    assert "conciliación" in _no(reg, filtros, ahora, hacer_estado(conciliacion_ok=False))
    assert "datos" in _no(reg, filtros, ahora, hacer_estado(datos_ok=False))


def test_pausa_vencida_no_bloquea(reg, filtros, ahora):
    e = hacer_estado(pausa_hasta=ahora - timedelta(hours=1))
    assert R.evaluar_candidato(reg, e, hacer_cand(), filtros, ahora).aprobada


def test_rechazos_estrategia(reg, filtros, ahora):
    reg.datos["estrategias"]["E1"]["estado"] = "APAGADA"
    assert "APAGADA" in _no(reg, filtros, ahora)
    reg.datos["estrategias"]["E1"]["estado"] = "PAPEL"
    e = hacer_estado(pausa_estrategia_hasta={"E1": ahora + timedelta(hours=2)})
    assert "pausa" in _no(reg, filtros, ahora, e)
    assert "salta" in _no(reg, filtros, ahora, hacer_estado(saltar_rondas={"E1": 1}))


def test_memes_sin_permiso_van_a_papel(reg, ahora):
    reg.datos["estrategias"]["E4"]["estado"] = "VIVA"
    reg.datos["estrategias"]["E4"]["permitir_vivo"] = False
    f = Filtros("PEPEUSDT", 1e-8, 1, 1, 1.0)
    c = hacer_cand(simbolo="PEPEUSDT", estrategia="E4", cubeta="memes", precio_entrada=0.00001, stop=0.0000085,
                   deslizamiento_pct=0.3)
    d = R.evaluar_candidato(reg, hacer_estado(), c, f, ahora)
    assert d.aprobada and d.solo_papel


def test_veto_y_evento(reg, filtros, ahora):
    vetos = [{"simbolo": "SOLUSDT", "razon": "hackeo", "vence": (ahora + timedelta(hours=1)).isoformat()}]
    assert "hackeo" in _no(reg, filtros, ahora, vetos=vetos)
    assert "Noticias" in _no(reg, filtros, ahora, vetos=[{"simbolo": "GLOBAL", "razon": "pánico"}])
    vencido = [{"simbolo": "SOLUSDT", "vence": "2020-01-01T00:00:00"}]
    assert R.evaluar_candidato(reg, hacer_estado(), hacer_cand(), filtros, ahora, vetos=vencido).aprobada
    ev = [{"nombre": "Fed", "importancia": "ALTA", "fecha_hora": (ahora + timedelta(minutes=20)).isoformat()}]
    assert "Fed" in _no(reg, filtros, ahora, eventos=ev)


def test_eventos_detalle(reg, ahora):
    lejos = [{"nombre": "x", "importancia": "ALTA", "fecha_hora": ahora + timedelta(hours=3)}]
    assert R.evento_activo(reg, lejos, ahora) is None
    bajo = [{"nombre": "x", "importancia": "MEDIA", "fecha_hora": ahora}]
    assert R.evento_activo(reg, bajo, ahora) is None
    sin_fecha = [{"nombre": "x", "importancia": "ALTA"}]
    assert R.evento_activo(reg, sin_fecha, ahora) is None
    naive = [{"nombre": "y", "importancia": "ALTA", "fecha_hora": "2026-11-10T12:25:00"}]
    assert R.evento_activo(reg, naive, ahora)["nombre"] == "y"


def test_regimen_bloquea(reg, filtros, ahora):
    assert "BAJISTA" in _no(reg, filtros, ahora, regimen_btc="BAJISTA")


def test_una_por_moneda(reg, filtros, ahora):
    p = R.Posicion("SOLUSDT", "SPOT", "LARGO", "E2", "normales", 100, 95, 1)
    assert "promediar" in _no(reg, filtros, ahora, hacer_estado(posiciones=[p]))
    p2 = R.Posicion("SOLUSDT", "FUTUROS", "CORTO", "E5", "futuros", 100, 105, 1, 2)
    assert "contraria" in _no(reg, filtros, ahora, hacer_estado(posiciones=[p2]))


def test_maximo_posiciones(reg, filtros, ahora):
    ps = [R.Posicion(f"X{i}USDT", "SPOT", "LARGO", "E1", "normales", 10, 10, 1) for i in range(3)]
    assert "máximo" in _no(reg, filtros, ahora, hacer_estado(posiciones=ps))


def test_stop_equivocado_y_corto_spot(reg, filtros, ahora):
    assert "equivocado" in _no(reg, filtros, ahora, cand=hacer_cand(stop=105))
    c = hacer_cand(lado="CORTO", stop=105)
    assert "corto en Spot" in _no(reg, filtros, ahora, cand=c)


def test_calor_lleno(reg, filtros, ahora):
    # 2.5 % ya en riesgo; el nuevo pide 1 % → 3.5 % > 3 %
    p = R.Posicion("ETHUSDT", "SPOT", "LARGO", "E1", "normales", 100, 75, 1)  # 25 USDT
    d = _no(reg, filtros, ahora, hacer_estado(posiciones=[p]))
    assert "calor" in d


def test_costos_rechazo(reg, filtros, ahora):
    c = hacer_cand(precio_entrada=100, stop=99.8)
    assert "cuesta" in _no(reg, filtros, ahora, cand=c)


def test_saltada_por_capital_en_decision(reg, ahora):
    f = Filtros("X", 0.01, 0.001, 0.001, 5.0)
    c = hacer_cand(precio_entrada=100.0, stop=80.0)
    d = R.evaluar_candidato(reg, hacer_estado(46.18), c, f, ahora)
    assert not d.aprobada and d.saltada_por_capital and d.capital_necesario > 46.18


def test_memes_cubeta_y_efectivo(reg, ahora):
    f = Filtros("PEPEUSDT", 1e-8, 1, 1, 1.0)
    c = hacer_cand(simbolo="PEPEUSDT", estrategia="E4", cubeta="memes", precio_entrada=1.0, stop=0.85,
                   deslizamiento_pct=0.3)
    llena = R.Posicion("DOGEUSDT", "SPOT", "LARGO", "E4", "memes", 1, 0.9, 100)  # 100 USDT = 10 %
    assert "llena" in _no(reg, f, ahora, hacer_estado(posiciones=[llena]), cand=c)
    assert "USDT libre" in _no(reg, f, ahora, hacer_estado(efectivo_spot=0), cand=c)
    d = R.evaluar_candidato(reg, hacer_estado(efectivo_spot=20), c, f, ahora)
    assert d.aprobada and d.valor_usdt <= 20


def _cand_fut(**kw):
    base = dict(simbolo="ETHUSDT", mercado="FUTUROS", lado="CORTO", estrategia="E5", cubeta="futuros",
                precio_entrada=100.0, stop=105.0, apalancamiento=2, comision_pct=0.05)
    base.update(kw)
    return hacer_cand(**base)


def test_futuros(reg, filtros, ahora):
    d = R.evaluar_candidato(reg, hacer_estado(), _cand_fut(), filtros, ahora, regimen_btc="BAJISTA")
    assert d.aprobada and "liquidacion_ok" in d.verificaciones
    assert d.valor_usdt <= 1000 * 0.25 * 2
    assert "máximo es 2x" in _no(reg, filtros, ahora, cand=_cand_fut(apalancamiento=3))
    assert "liquidación" in _no(reg, filtros, ahora, cand=_cand_fut(stop=130))
    assert "margen libre" in _no(reg, filtros, ahora, hacer_estado(efectivo_futuros=0), cand=_cand_fut())
    usado = R.Posicion("BTCUSDT", "FUTUROS", "CORTO", "E5", "otra", 100, 100, 5, 2)  # margen 250
    assert "margen libre" in _no(reg, filtros, ahora, hacer_estado(posiciones=[usado]), cand=_cand_fut())


def test_liquidacion_estimada():
    assert R.precio_liquidacion(100, "CORTO", 2, 0.5) == pytest.approx(149.5)
    assert R.precio_liquidacion(100, "LARGO", 2, 0.5) == pytest.approx(50.5)


def test_posicion_propiedades():
    p = R.Posicion("A", "SPOT", "LARGO", "E1", "normales", 100, 110, 1)
    assert p.riesgo_usdt == 0 and p.margen == 0 and p.valor == 100
    c = R.Posicion("A", "FUTUROS", "CORTO", "E5", "futuros", 100, 105, 2, 2)
    assert c.riesgo_usdt == 10 and c.margen == 100


# ---------------- Topes ----------------

def test_tope_diario(reg, ahora):
    e = hacer_estado(1000, capital_inicio_dia=1000)
    e.capital = 969  # -3.1 %
    msgs = R.aplicar_topes(reg, e, ahora)
    assert "mañana" in msgs[0]
    assert e.pausa_hasta == datetime(2026, 11, 11, 0, 0, tzinfo=CDMX)
    assert R.aplicar_topes(reg, e, ahora) == []  # no repite


def test_tope_semanal(reg, ahora):
    e = hacer_estado(1000)
    e.capital = 935
    msgs = R.aplicar_topes(reg, e, ahora)
    assert "lunes" in msgs[0]
    assert e.pausa_hasta.weekday() == 0 and e.pausa_hasta > ahora


def test_caida_maxima(reg, ahora):
    e = hacer_estado(1000, pico=1200, capital_inicio_dia=1000, capital_inicio_semana=1000)
    msgs = R.aplicar_topes(reg, e, ahora)
    assert e.detenido and "CAÍDA" in msgs[0]


def test_topes_sin_perdida(reg, ahora):
    e = hacer_estado(1000)
    e.capital = 1100
    assert R.aplicar_topes(reg, e, ahora) == [] and e.pico == 1100
    e0 = hacer_estado(0.0, pico=0.0, capital_inicio_dia=0.0, capital_inicio_semana=0.0)
    assert R.aplicar_topes(reg, e0, ahora) == []


def test_fechas(reg):
    domingo = datetime(2026, 11, 15, 23, 0, tzinfo=CDMX)
    assert R.inicio_semana(reg, domingo).day == 9
    assert R.siguiente_lunes(reg, domingo).day == 16
    assert R.siguiente_dia(reg, domingo).day == 16


# ---------------- Rachas ----------------

def test_rachas_normales(reg, ahora):
    e = hacer_estado()
    for _ in range(2):
        assert R.registrar_resultado(reg, e, "E1", -1, ahora) == []
    msgs = R.registrar_resultado(reg, e, "E1", -1, ahora)
    assert "salta" in msgs[0] and e.saltar_rondas["E1"] == 1
    R.consumir_ronda(e)
    assert "E1" not in e.saltar_rondas
    R.registrar_resultado(reg, e, "E1", -1, ahora)
    R.registrar_resultado(reg, e, "E1", +1, ahora)
    assert e.rachas["E1"] == 0


def test_consumir_ronda_varias(reg):
    e = hacer_estado(saltar_rondas={"E1": 2})
    R.consumir_ronda(e)
    assert e.saltar_rondas["E1"] == 1


def test_rachas_surfista(reg, ahora):
    e = hacer_estado()
    R.registrar_resultado(reg, e, "E4", -1, ahora)
    msgs = R.registrar_resultado(reg, e, "E4", -1, ahora)
    assert "24" in msgs[0]
    assert e.pausa_estrategia_hasta["E4"] == ahora + timedelta(hours=24)


# ---------------- Gestión ----------------

def test_mover_stop():
    assert R.mover_stop("LARGO", 95, 90) == 95
    assert R.mover_stop("LARGO", 95, 97) == 97
    assert R.mover_stop("CORTO", 105, 110) == 105
    assert R.mover_stop("CORTO", 105, 102) == 102


def test_stop_a_entrada(reg):
    assert R.stop_a_entrada(reg, "LARGO", 100, 95, 104, 95, 0.3) == 95
    assert R.stop_a_entrada(reg, "LARGO", 100, 95, 105, 95, 0.3) == pytest.approx(100.3)
    assert R.stop_a_entrada(reg, "CORTO", 100, 105, 96, 105, 0.3) == 105
    assert R.stop_a_entrada(reg, "CORTO", 100, 105, 95, 105, 0.3) == pytest.approx(99.7)


def test_apagado(reg):
    assert R.evaluar_apagado(reg, 30, 25, [])[0]
    assert not R.evaluar_apagado(reg, 10, 25, [0.1] * 30)[0]
    apagar, msg = R.evaluar_apagado(reg, 10, None, [-0.1] * 30)
    assert apagar and "negativa" in msg
    assert not R.evaluar_apagado(reg, 10, None, [-0.1] * 5)[0]


def test_cantidad_bajo_minimo():
    f = Filtros("X", 0.01, 1.0, 1.0, 0.0)
    c = hacer_cand(precio_entrada=100.0, stop=50.0)  # 10/50 = 0.2 → 0 unidades
    t = R.calcular_tamano(1000, 1.0, 1.0, c, f, 1000)
    assert not t.ok and "cantidad" in t.razon
