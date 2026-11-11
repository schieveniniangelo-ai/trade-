"""Arreglo 69 (banco de filtros, fase 1): registro de descartes con un código estable por cada motivo.

El registro SOLO anota. Estas pruebas revisan dos cosas: que cada motivo quede con su código, y que la ronda de
papel y el backtest den exactamente lo mismo con registro y sin él. Todo con velas falsas: sin red y sin llaves."""
import json
from datetime import timedelta

import pandas as pd
import pytest

from sobreviviente import backtest as B
from sobreviviente import datos as D
from sobreviviente import descartes as DS
from sobreviviente import diario as DI
from sobreviviente import papel as P
from sobreviviente import regimen as RG
from sobreviviente import riesgo as R
from sobreviviente.exchange import Filtros

from conftest import hacer_cand, hacer_estado
from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_estrategias_backtest import PARAMS_SUELTOS, velas_sinteticas
from test_papel import _buscar_dia_con_compra, _datos_dia, _reg_papel
from test_v2 import diarias

DIA = pd.Timedelta(days=1)


# ---------------- El catálogo ----------------

def test_catalogo_tiene_todos_los_codigos_y_el_registro_su_esquema():
    codigos = {v for k, v in vars(DS).items() if k.isupper() and isinstance(v, str)}
    assert codigos == set(DS.CATALOGO)                       # ningún código sin explicación, ninguna explicación de más
    assert all(k == k.upper() and " " not in k for k in codigos)
    r = DS.registro(DS.CALOR_LLENO, "calor lleno", "SOLUSDT", pd.Timestamp("2026-11-10", tz="UTC"), "A", "M1")
    assert tuple(r) == DS.CAMPOS
    assert r["fecha"] == "2026-11-10T00:00:00+00:00" and r["aprobada"] is False
    assert DS.registro(DS.SIN_SENAL, "x", "BTCUSDT", "2026-11-10", "C", "M0")["fecha"] == "2026-11-10"


# ---------------- A) Motor de riesgo: cada "no" con su código ----------------

def _pos(simbolo="SOLUSDT", lado="LARGO", mercado="SPOT", cubeta="normales", stop=95.0):
    return R.Posicion(simbolo, mercado, lado, "E2", cubeta, 100, stop, 1, 2 if mercado == "FUTUROS" else 1)


CASOS = [
    (DS.FRENO_TOTAL, dict(estado=dict(detenido=True))),
    (DS.PAUSA_TOPE, dict(estado=dict(pausa_motivo="tope diario: se perdió 3.1 % hoy (tope 3.0 %)"), pausa=True)),
    (DS.CONCILIACION, dict(estado=dict(conciliacion_ok=False))),
    (DS.DATOS_NO_CONFIABLES, dict(estado=dict(datos_ok=False))),
    (DS.ESTRATEGIA_APAGADA, dict(apagada=True)),
    (DS.RACHA_PERDIDAS, dict(estado=dict(saltar_rondas={"E1": 1}))),
    (DS.RACHA_PERDIDAS, dict(pausa_estrategia=True)),
    (DS.VETO_NOTICIAS, dict(kw=dict(vetos=[{"simbolo": "GLOBAL", "razon": "pánico"}]))),
    (DS.EVENTO_FUERTE, dict(evento=True)),
    (DS.VOL_EXTREMA, dict(kw=dict(vol_moneda="EXTREMA"))),
    (DS.VOL_EXTREMA, dict(kw=dict(vol_btc="EXTREMA", regimen_btc="BAJISTA"))),      # las dos: gana la volatilidad
    (DS.BTC_BAJISTA, dict(kw=dict(regimen_btc="BAJISTA"))),
    (DS.YA_HAY_POSICION, dict(estado=dict(posiciones=[_pos()]))),
    (DS.YA_HAY_POSICION, dict(estado=dict(posiciones=[_pos(lado="CORTO", mercado="FUTUROS", cubeta="futuros", stop=105)]))),
    (DS.MAX_POSICIONES, dict(estado=dict(posiciones=[_pos(f"X{i}USDT", stop=100) for i in range(3)]))),
    (DS.STOP_INVALIDO, dict(cand=dict(stop=105.0))),
    (DS.EXPOSICION_O_MARGEN, dict(estado=dict(efectivo_spot=0.0))),
    (DS.TAMANO_O_CAPITAL, dict(estado=dict(capital=10.0))),
    (DS.CALOR_LLENO, dict(estado=dict(posiciones=[_pos(f"X{i}USDT", stop=85.0) for i in range(2)]))),
    (DS.COSTOS, dict(cand=dict(meta=100.2))),
    (DS.APROBADA, dict()),
]


@pytest.mark.parametrize("codigo, caso", CASOS, ids=[f"{i}-{c}" for i, (c, _) in enumerate(CASOS)])
def test_cada_decision_del_motor_de_riesgo_trae_su_codigo(reg, filtros, ahora, codigo, caso):
    args_estado = dict(caso.get("estado", {}))
    capital = args_estado.pop("capital", 1000.0)
    if caso.get("pausa"):
        args_estado["pausa_hasta"] = ahora + timedelta(hours=1)
    if caso.get("pausa_estrategia"):
        args_estado["pausa_estrategia_hasta"] = {"E1": ahora + timedelta(hours=2)}
    if caso.get("apagada"):
        reg.datos["estrategias"]["E1"]["estado"] = "APAGADA"
    kw = dict(caso.get("kw", {}))
    if caso.get("evento"):
        kw["eventos"] = [{"nombre": "Fed", "importancia": "ALTA", "fecha_hora": (ahora + timedelta(minutes=20)).isoformat()}]
    d = R.evaluar_candidato(reg, hacer_estado(capital, **args_estado), hacer_cand(**caso.get("cand", {})), filtros,
                            ahora, **kw)
    assert d.codigo == codigo, d.razon
    assert d.aprobada == (codigo == DS.APROBADA)
    assert d.codigo in DS.CATALOGO
    if codigo == DS.TAMANO_O_CAPITAL:
        assert d.saltada_por_capital and "saltada por capital" in d.razon


# ---------------- backtest.cartera: con y sin registro da lo mismo ----------------

def _filas_cartera():
    t0 = pd.Timestamp("2024-03-04 16:00", tz="UTC")
    base = dict(estrategia="E1", mercado="SPOT", lado="LARGO", cubeta="normales", precio_plan=100.0, stop=95.0,
                meta=None, fuerza=1.0, comision_pct=0.1, desliz_pct=0.0, regimen_btc="ALCISTA", vol_btc=50.0,
                vol_moneda=50.0, pnl_unidad=10.0, comision_unidad=0.2, stops_t=[], stops=[], entrada=100.0,
                t_entrada=t0)
    h = pd.Timedelta(hours=4)
    return pd.DataFrame([
        {**base, "simbolo": "AUSDT", "t_decision": t0, "t_salida": t0 + 2 * h},
        {**base, "simbolo": "AUSDT", "t_decision": t0 + h, "t_salida": t0 + 3 * h},                       # ya hay posición
        {**base, "simbolo": "BUSDT", "t_decision": t0 + h, "t_salida": t0 + 3 * h, "pnl_unidad": -5.0},
        {**base, "simbolo": "CUSDT", "t_decision": t0 + h, "t_salida": t0 + 3 * h, "regimen_btc": "BAJISTA"},
        {**base, "simbolo": "DUSDT", "t_decision": t0 + 4 * h, "t_salida": t0 + 5 * h, "vol_moneda": 99.9},  # extrema
    ])


def test_cartera_con_y_sin_registro_da_exactamente_lo_mismo(reg):
    filt = {s: Filtros(s, 0.01, 0.001, 0.001, 5) for s in ("AUSDT", "BUSDT", "CUSDT", "DUSDT")}
    sin = B.cartera(reg, _filas_cartera(), 1000.0, filt, ["E1"])
    registro = []
    con = B.cartera(reg, _filas_cartera(), 1000.0, filt, ["E1"], registro=registro, nombre_cartera="A")
    pd.testing.assert_frame_equal(sin.decisiones, con.decisiones)
    pd.testing.assert_frame_equal(sin.operaciones, con.operaciones)
    pd.testing.assert_series_equal(sin.curva, con.curva)
    assert (sin.pausas, sin.detenido_en, sin.detenciones) == (con.pausas, con.detenido_en, con.detenciones)
    assert [r["codigo"] for r in registro] == [DS.APROBADA, DS.YA_HAY_POSICION, DS.APROBADA, DS.BTC_BAJISTA,
                                               DS.VOL_EXTREMA]
    assert [r["aprobada"] for r in registro] == list(con.decisiones["aprobada"])
    assert [r["texto"] for r in registro] == list(con.decisiones["razon"])
    uno = registro[1]
    assert (uno["simbolo"], uno["estrategia"], uno["cartera"], uno["origen"]) == ("AUSDT", "E1", "A", "riesgo")
    assert uno["fecha"] == "2024-03-04T20:00:00+00:00"
    assert all(set(DS.CAMPOS) <= set(r) for r in registro)


def test_cartera_registra_la_saltada_por_capital(reg):
    filt = {s: Filtros(s, 0.01, 0.001, 0.001, 5) for s in ("AUSDT", "BUSDT", "CUSDT", "DUSDT")}
    registro = []
    res = B.cartera(reg, _filas_cartera().iloc[:1], 10.0, filt, ["E1"], registro=registro)
    assert res.operaciones.empty
    assert registro[0]["codigo"] == DS.TAMANO_O_CAPITAL and registro[0]["aprobada"] is False
    assert registro[0]["capital_necesario"] == res.decisiones["capital_necesario"].iloc[0] > 10.0


# ---------------- B) Generación de candidatos: lo que antes se descartaba en silencio ----------------

def _mercado_diario(reg, grandes_n=2):
    """Cuatro monedas con velas falsas; solo caben `grandes_n` en "grandes", así que alguna queda fuera del universo."""
    r = reg.copia_con({"universo.grandes_n": grandes_n})
    velas = {s: diarias(800, semilla=i + 10, tendencia=0.0008 + 0.0003 * i)
             for i, s in enumerate(["BTCUSDT", "AUSDT", "BUSDT", "CUSDT"])}
    for i, df in enumerate(velas.values()):
        df["quote_volume"] = 5e8 / (i + 1)                   # BTC la más grande, CUSDT la más chica
    velas["NUEVAUSDT"] = diarias(30, semilla=99)             # muy pocas velas: no alcanza para calcular nada
    return DI.preparar(r, velas, None, [], exchange_info={"symbols": []}, btc_largo=velas["BTCUSDT"])


def test_generar_diario_con_y_sin_registro_da_los_mismos_candidatos(reg):
    md = _mercado_diario(reg)
    sin = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01")
    descartes = []
    con = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01", descartes=descartes)
    assert not sin.empty
    pd.testing.assert_frame_equal(sin, con)
    codigos = {d["codigo"] for d in descartes}
    assert DS.FUERA_DE_UNIVERSO in codigos and DS.SIN_VELAS in codigos
    assert [d["simbolo"] for d in descartes if d["codigo"] == DS.SIN_VELAS] == ["NUEVAUSDT"]
    fuera = [d for d in descartes if d["codigo"] == DS.FUERA_DE_UNIVERSO and "candidato" in d]
    assert fuera
    for d in fuera:
        assert d["estrategia"] == "M1" and d["cartera"] == "" and d["origen"] == "generacion" and d["aprobada"] is False
        dia = pd.Timestamp(d["fecha"])
        assert not bool(md.grandes.at[dia, d["simbolo"]])                 # de verdad estaba fuera ese día
        assert d["r"] == d["candidato"]["r"] and d["pnl_unidad"] == d["candidato"]["pnl_unidad"]
        assert set(sin.columns) == set(d["candidato"])                    # misma forma que un candidato normal
        # y no se coló entre los candidatos
        assert not ((sin["simbolo"] == d["simbolo"]) & (sin["t_decision"] == dia)).any()


def test_generar_diario_registra_el_veto_de_estela(reg):
    md = _mercado_diario(reg, grandes_n=15)
    sin = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01")
    vetado = sin.iloc[0]
    md.veto = {vetado["simbolo"]: {vetado["t_senal"]}}
    descartes = []
    con = DI.generar(md, "M1", {"n": 20}, "2022-06-01", "2024-02-01", descartes=descartes)
    assert len(con) == len(sin) - 1
    estela = [d for d in descartes if d["codigo"] == DS.VETO_ESTELA]
    assert len(estela) == 1 and estela[0]["simbolo"] == vetado["simbolo"]
    assert estela[0]["fecha"] == vetado["t_decision"].isoformat() and estela[0]["r"] == pytest.approx(vetado["r"])


def _mercado_v1(reg):
    """Mercado mínimo de la v1 (velas de 1 hora falsas): BTC, AUSDT (fuera del universo) y BUSDT (dentro)."""
    spot1h = {s: velas_sinteticas(4000, semilla=i + 11) for i, s in enumerate(["BTCUSDT", "AUSDT", "BUSDT"])}
    spot4h = {s: D.resamplear(df, "4h") for s, df in spot1h.items()}
    dias = pd.date_range("2022-12-31", periods=200, freq="D", tz="UTC")
    pertenece = pd.DataFrame(True, index=dias, columns=list(spot1h))
    pertenece["AUSDT"] = False
    btc4 = spot4h["BTCUSDT"]
    m = B.Mercado(reg=reg, spot1h=spot1h, spot4h=spot4h, fut4h={}, funding={}, volumen=pd.DataFrame(),
                  pertenece=pertenece, vol_mediano=pd.DataFrame(1e9, index=dias, columns=list(spot1h)),
                  fut_liquido=pd.DataFrame(), btc_reg4h=RG.tendencia(btc4, reg),
                  btc_vol4h=RG.percentil_volatilidad(btc4, reg))
    for s, df in spot4h.items():
        m.reg4h[s] = RG.tendencia(df, reg)
        m.vol4h[s] = RG.percentil_volatilidad(df, reg)
    return m


def test_generar_candidatos_v1_con_y_sin_registro(reg):
    B._CTX_CACHE.clear()
    try:
        m = _mercado_v1(reg)
        args = (m, "E3", PARAMS_SUELTOS["E3"], "2023-01-01", "2023-07-01")
        sin = B.generar_candidatos(*args, procesos=1)
        descartes = []
        con = B.generar_candidatos(*args, procesos=1, descartes=descartes)
    finally:
        B._CTX_CACHE.clear()
    assert not sin.empty and set(sin["simbolo"]) <= {"BTCUSDT", "BUSDT"}
    pd.testing.assert_frame_equal(sin, con)
    fuera = [d for d in descartes if d["codigo"] == DS.FUERA_DE_UNIVERSO]
    assert fuera and {d["simbolo"] for d in fuera} == {"AUSDT"}
    con_sim = [d for d in fuera if "candidato" in d]
    assert con_sim and all(d["candidato"]["simbolo"] == "AUSDT" and d["r"] == d["candidato"]["r"] for d in con_sim)
    assert all(d["origen"] == "generacion" and d["estrategia"] == "E3" and not d["aprobada"] for d in descartes)


def test_generar_candidatos_v1_sin_velas_suficientes(reg):
    B._CTX_CACHE.clear()
    try:
        m = _mercado_v1(reg)
        m.spot1h["CORTAUSDT"] = velas_sinteticas(100, semilla=5)          # menos de las 300 velas que pide la v1
        m.reg4h["CORTAUSDT"] = RG.tendencia(D.resamplear(m.spot1h["CORTAUSDT"], "4h"), reg)
        descartes = []
        B.generar_candidatos(m, "E3", PARAMS_SUELTOS["E3"], "2023-01-01", "2023-07-01", procesos=1, descartes=descartes)
    finally:
        B._CTX_CACHE.clear()
    assert [d["simbolo"] for d in descartes if d["codigo"] == DS.SIN_VELAS] == ["CORTAUSDT"]


# ---------------- C) La ronda de papel ----------------

def _descartes(r, dia, cartera):
    return DS.leer_del_dia(r, dia).get(cartera, [])


def test_papel_registra_aprobada_y_saltada_por_capital(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)                                   # 46.18 USDT: C compra BTC, A no llega al mínimo
    dd = _datos_dia(r, _dia_marea_alta(r))[0]
    a = P.ronda_cartera(r, "A", dd, [], [])
    c = P.ronda_cartera(r, "C", dd, [], [])
    assert not a["boletos"] and [b["accion"] for b in c["boletos"]] == ["COMPRAR"]
    da, dc = _descartes(r, a["dia"], "A"), _descartes(r, c["dia"], "C")
    assert [(d["codigo"], d["simbolo"], d["estrategia"], d["cartera"], d["aprobada"]) for d in da] == \
        [(DS.TAMANO_O_CAPITAL, "BTCUSDT", "M0", "A", False)]
    assert "saltada por capital" in da[0]["texto"] and da[0]["fecha"] == a["dia"] and da[0]["origen"] == "papel"
    assert [(d["codigo"], d["simbolo"], d["cartera"], d["aprobada"]) for d in dc] == [(DS.APROBADA, "BTCUSDT", "C", True)]
    # Las dos carteras quedan en el mismo archivo del día
    arch = tmp_path / "datos" / "papel" / "descartes" / f"descartes_{a['dia']}.json"
    assert set(json.loads(arch.read_text(encoding="utf-8"))["carteras"]) == {"A", "C"}


def test_papel_registra_veto_modo_seguro_y_compras_bloqueadas(reg, tmp_path):
    for nombre, kw, codigo, texto in [
        ("veto", dict(vetos=[{"simbolo": "GLOBAL", "razon": "hackeo grande"}]), DS.VETO_NOTICIAS, "vetada por Noticias: hackeo grande"),
        ("seguro", dict(forzar_seguro=True), DS.MODO_SEGURO, "MODO SEGURO: los datos no son confiables"),
        ("tarde", dict(bloquear_compras="ronda FUERA DE HORA"), DS.COMPRAS_BLOQUEADAS, "hoy no se compra (ronda FUERA DE HORA)"),
    ]:
        r = _reg_m0(reg, tmp_path / nombre)
        dd = _datos_dia(r, _dia_marea_alta(r))[0]
        c = P.ronda_cartera(r, "C", dd, kw.pop("vetos", []), [], **kw)
        assert not c["boletos"], nombre
        d = _descartes(r, c["dia"], "C")
        assert [(x["codigo"], x["texto"], x["simbolo"], x["aprobada"]) for x in d] == [(codigo, texto, "BTCUSDT", False)], nombre


def test_papel_registra_sin_senal(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)                                 # motor M1: revisa todas las "grandes" del día
    dd = _datos_dia(r, _buscar_dia_con_compra(r))[0]
    c = P.ronda_cartera(r, "A", dd, [], [])
    d = _descartes(r, c["dia"], "A")
    grandes_hoy = {s for s in dd.md.grandes.columns if bool(dd.md.grandes.at[dd.dia + DIA, s])}
    sin = {x["simbolo"] for x in d if x["codigo"] == DS.SIN_SENAL}
    con = {x["simbolo"] for x in d if x["codigo"] != DS.SIN_SENAL}
    assert sin and con and sin | con == grandes_hoy and not (sin & con)   # cada moneda del día queda anotada una vez
    assert all(x["estrategia"] == "M1" and not x["aprobada"] and x["texto"] == "sin señal hoy"
               for x in d if x["codigo"] == DS.SIN_SENAL)


def test_papel_registra_la_senal_fuera_del_universo(reg, tmp_path):
    con = _reg_papel(reg, tmp_path / "con")                       # motor M1, capital 1000
    k = _buscar_dia_con_compra(con)
    dd = _datos_dia(con, k)[0]
    normal = P.ronda_cartera(con, "A", dd, [], [])
    comprada = next(b["simbolo"] for b in normal["boletos"] if b["accion"] == "COMPRAR")
    assert DS.FUERA_DE_UNIVERSO not in {d["codigo"] for d in _descartes(con, normal["dia"], "A")}
    # Mismo día, pero esa moneda ya no está en "grandes": la señal existe y se anota; no se compra
    sin = _reg_papel(reg, tmp_path / "sin")
    dd2 = _datos_dia(sin, k)[0]
    dd2.md.grandes.loc[dd2.dia + DIA, comprada] = False
    res = P.ronda_cartera(sin, "A", dd2, [], [])
    assert comprada not in [b["simbolo"] for b in res["boletos"]]
    fuera = [d for d in _descartes(sin, res["dia"], "A") if d["codigo"] == DS.FUERA_DE_UNIVERSO]
    assert [(d["simbolo"], d["estrategia"], d["aprobada"]) for d in fuera] == [(comprada, "M1", False)]


def test_papel_con_y_sin_registro_da_la_misma_ronda(reg, tmp_path, monkeypatch):
    def ronda(carpeta):
        r = _reg_papel(reg, carpeta)
        k = _buscar_dia_con_compra(r)
        res = [P.ronda_cartera(r, "A", _datos_dia(r, j)[0], [], []) for j in range(k, k + 6)]
        return res, (carpeta / "datos" / "papel" / "cartera_A.json").read_text(encoding="utf-8")

    con, estado_con = ronda(tmp_path / "con")
    monkeypatch.setattr(DS, "guardar_del_dia", lambda *a, **k: None)          # sin registro
    sin, estado_sin = ronda(tmp_path / "sin")
    assert con == sin and estado_con == estado_sin                            # boletos, capital, stops, mensajes: todo
    assert any(b["accion"] == "COMPRAR" for c in con for b in c["boletos"])
    assert (tmp_path / "con" / "datos" / "papel" / "descartes").is_dir()
    assert not (tmp_path / "sin" / "datos" / "papel" / "descartes").exists()


def test_papel_si_el_registro_no_se_puede_guardar_la_ronda_sigue_igual(reg, tmp_path, monkeypatch):
    bien = _reg_m0(reg, tmp_path / "bien")
    k = _dia_marea_alta(bien)
    normal = P.ronda_cartera(bien, "C", _datos_dia(bien, k)[0], [], [])

    def falla(*a, **kw):
        raise OSError("disco lleno")

    monkeypatch.setattr(DS, "guardar_del_dia", falla)
    mal = _reg_m0(reg, tmp_path / "mal")
    res = P.ronda_cartera(mal, "C", _datos_dia(mal, k)[0], [], [])
    assert res["boletos"] == normal["boletos"] and res["capital"] == normal["capital"]
    assert res["efectivo"] == normal["efectivo"] and res["posiciones"] == normal["posiciones"]
    extra = [m for m in res["mensajes"] if m not in normal["mensajes"]]
    assert len(extra) == 1 and "No se pudo guardar el registro de descartes de hoy (OSError)" in extra[0]
    texto = P.resumen_corto({"dia": res["dia"], "carteras": {"C": res}, "referencias": {}, "avisos": []})
    assert texto.endswith("👍 No necesito nada de ti.")                       # es solo una medición: no quita el 👍


def test_papel_repetir_la_ronda_no_duplica_el_registro(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    dd = _datos_dia(r, _dia_marea_alta(r))[0]
    c = P.ronda_cartera(r, "C", dd, [], [])
    antes = DS.leer_del_dia(r, c["dia"])
    assert P.ronda_cartera(r, "C", dd, [], []) == c
    DS.guardar_del_dia(r, c["dia"], "C", antes["C"])                          # volver a guardar reemplaza, no agrega
    assert DS.leer_del_dia(r, c["dia"]) == antes and len(antes["C"]) == 1


def test_leer_del_dia_tolera_archivo_ausente_o_danado(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    assert DS.leer_del_dia(r, "2026-11-10") == {}
    arch = DS.ruta_del_dia(r, "2026-11-10")
    arch.parent.mkdir(parents=True)
    for malo in ("{dañado", "[1, 2]", '{"carteras": 5}'):
        arch.write_text(malo, encoding="utf-8")
        assert DS.leer_del_dia(r, "2026-11-10") == {}
    DS.guardar_del_dia(r, "2026-11-10", "A", [DS.registro(DS.SIN_SENAL, "sin señal hoy", "BTCUSDT", "2026-11-10", "A", "M0")])
    assert [d["codigo"] for d in DS.leer_del_dia(r, "2026-11-10")["A"]] == [DS.SIN_SENAL]
