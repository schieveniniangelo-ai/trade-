"""Arreglo 71 (banco de filtros, fase 3): walk-forward con ventanas de entrenamiento y de prueba anotadas.

Se reporta SOLO lo de fuera de muestra. Del entrenamiento solo se anota qué había; no se elige ni se busca nada.
Todo con datos falsos: sin red y sin llaves."""
import pandas as pd
import pytest

from sobreviviente import banco_filtros as BF
from sobreviviente import descartes as DS
from sobreviviente.exchange import Filtros
from sobreviviente.validacion import fechas, ventanas_wf

DIA = pd.Timedelta(days=1)
FILTROS = {s: Filtros(s, 0.01, 0.001, 0.001, 5) for s in ("AUSDT", "BUSDT", "CUSDT", "DUSDT", "EUSDT", "ZUSDT")}
CFG = BF.ConfigBanco(carteras=("A",), motores=("M1",), encendidos=("M1",), capital=1000.0,
                     filtros=(DS.YA_HAY_POSICION, DS.FUERA_DE_UNIVERSO))


def _dos_ventanas(reg):
    """Recorte: entrenamiento de 12 meses desde 2022-01 → pruebas ene–mar y abr–jun de 2023; prueba final jul–dic 2023."""
    return reg.copia_con({"backtest.inicio": "2022-01-01", "backtest.fin": "2023-12-31"})


def _fila(simbolo, fecha, pnl=10.0, dias=2, **cambios):
    t = pd.Timestamp(fecha, tz="UTC")
    base = dict(estrategia="M1", mercado="SPOT", lado="LARGO", cubeta="normales", precio_plan=100.0, stop=95.0,
                meta=None, fuerza=1.0, comision_pct=0.1, desliz_pct=0.0, regimen_btc="ALCISTA", vol_btc=50.0,
                vol_moneda=50.0, pnl_unidad=pnl, r=pnl / 5.0, comision_unidad=0.2, stops_t=[], stops=[],
                entrada=100.0, simbolo=simbolo, t_senal=t - DIA, t_decision=t, t_entrada=t, t_salida=t + dias * DIA)
    base.update(cambios)
    return base


def _pool():
    filas = [
        _fila("ZUSDT", "2022-06-15", pnl=500.0),            # SOLO entrenamiento: una ganancia enorme (100 R)
        _fila("AUSDT", "2023-02-10"),                       # ventana 2023-01
        _fila("BUSDT", "2023-03-20", pnl=-5.0, dias=30),    # ventana 2023-01, y sigue abierta al empezar la siguiente
        _fila("BUSDT", "2023-04-05"),                       # ventana 2023-04: BUSDT sigue abierta → no entra
        _fila("CUSDT", "2023-05-15"),                       # ventana 2023-04
        _fila("DUSDT", "2023-09-01", pnl=-5.0),             # prueba final
    ]
    fuera = [_fila("EUSDT", "2022-09-01", pnl=500.0), _fila("EUSDT", "2023-05-20")]
    previos = [DS.registro(DS.FUERA_DE_UNIVERSO, "fuera", "EUSDT", f["t_decision"], "", "M1", origen="generacion",
                           r=f["r"], pnl_unidad=f["pnl_unidad"], candidato=f) for f in fuera]
    previos.append(DS.registro(DS.SIN_VELAS, "sin velas", "NUEVAUSDT", None, "", "M1", origen="generacion"))
    return BF.Pool(base=pd.DataFrame(filas), previos=previos)


# ---------------- Las ventanas ----------------

def test_las_ventanas_son_las_de_la_validacion(reg):
    vs = BF.ventanas(reg, con_prueba_final=False)
    assert [(v.entrenamiento[0], v.entrenamiento[1], v.prueba[0], v.prueba[1]) for v in vs] == ventanas_wf(reg)
    assert len(vs) >= 2 and not any(v.final for v in vs)
    ent, pru = int(reg.get("validacion.wf_entrenamiento_meses")), int(reg.get("validacion.wf_prueba_meses"))
    v = vs[0]
    assert v.entrenamiento[0] + pd.DateOffset(months=ent) == v.entrenamiento[1] == v.prueba[0]
    assert v.prueba[0] + pd.DateOffset(months=pru) == v.prueba[1]
    assert v.nombre == f"{v.prueba[0]:%Y-%m}"
    # Las pruebas van una tras otra, sin huecos y sin encimarse; y nunca tocan la prueba final
    for a, b in zip(vs, vs[1:]):
        assert a.prueba[1] == b.prueba[0]
    assert vs[-1].prueba[1] <= fechas(reg)["holdout"]


def test_los_meses_se_leen_del_reglamento(reg):
    otro = reg.copia_con({"validacion.wf_entrenamiento_meses": 6, "validacion.wf_prueba_meses": 2})
    v = BF.ventanas(otro, con_prueba_final=False)[0]
    assert v.entrenamiento[0] + pd.DateOffset(months=6) == v.prueba[0]
    assert v.prueba[0] + pd.DateOffset(months=2) == v.prueba[1]
    assert BF.ventanas(reg, False)[0].prueba != v.prueba        # y el reglamento de verdad no se movió
    assert int(reg.get("validacion.wf_entrenamiento_meses")) == 12 and int(reg.get("validacion.wf_prueba_meses")) == 3


def test_la_prueba_final_va_aparte(reg):
    vs = BF.ventanas(reg)
    f = fechas(reg)
    assert vs[-1].final and vs[-1].nombre == "prueba final" and vs[-1].entrenamiento is None
    assert vs[-1].prueba == (f["holdout"], f["fin"] + pd.Timedelta(minutes=1))
    assert [v.final for v in vs[:-1]] == [False] * (len(vs) - 1)


def test_recorte_de_dos_ventanas(reg):
    vs = BF.ventanas(_dos_ventanas(reg))
    assert [v.nombre for v in vs] == ["2023-01", "2023-04", "prueba final"]
    assert [str(v.prueba[0].date()) for v in vs] == ["2023-01-01", "2023-04-01", "2023-07-01"]
    assert str(vs[0].entrenamiento[0].date()) == "2022-01-01" and str(vs[1].entrenamiento[0].date()) == "2022-04-01"


# ---------------- Solo se reporta fuera de muestra ----------------

def test_lo_del_entrenamiento_no_aparece_en_ningun_resultado(reg):
    r = _dos_ventanas(reg)
    pool = _pool()
    wf = BF.walk_forward(r, CFG, pool, FILTROS)
    inicio_prueba = pd.Timestamp("2023-01-01", tz="UTC")
    for corridas in wf.corridas.values():
        for nombre, c in corridas.items():
            assert (c.candidatos["t_decision"] >= inicio_prueba).all(), nombre
            assert "ZUSDT" not in set(c.candidatos["simbolo"])
            ops = c.resultado.operaciones
            assert "ZUSDT" not in set(ops["simbolo"]) and (ops["r"] < 50).all()         # la de 100 R no está
            assert all(d["simbolo"] != "ZUSDT" for d in c.registro)
            assert all(pd.Timestamp(d["fecha"]) >= inicio_prueba for d in c.registro)
            for v in wf.ventanas:
                assert "ZUSDT" not in set(BF.operaciones_de(c, v).get("simbolo", []))
    # Tampoco la señal de fuera del universo que cayó en el entrenamiento
    fuera = wf.corridas["A"][DS.FUERA_DE_UNIVERSO]
    eusdt = fuera.candidatos[fuera.candidatos["simbolo"] == "EUSDT"]
    assert list(eusdt["t_decision"].dt.strftime("%Y-%m-%d")) == ["2023-05-20"]
    assert [d["codigo"] for d in wf.pool.previos] == [DS.FUERA_DE_UNIVERSO]            # solo la de la zona de prueba
    # Lo del entrenamiento queda anotado aparte, como observación, y nada más
    assert wf.solo_observado["2023-01"] == {"senales": 1, "por_motor": {"M1": 1}}
    assert wf.solo_observado["2023-04"]["senales"] == 3                                 # abr 2022 – mar 2023: Z, A y B
    assert "prueba final" not in wf.solo_observado
    assert len(pool.base) == 6                                                          # el pool original no se tocó


def test_cada_ventana_de_prueba_se_reporta_por_separado(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), CFG, _pool(), FILTROS)
    base = wf.corridas["A"][BF.BASE]
    v1, v2, final = wf.ventanas
    assert BF.ventanas_de_prueba(wf) == [v1, v2]
    por_ventana = [sorted(BF.operaciones_de(base, v)["simbolo"]) for v in wf.ventanas]
    assert por_ventana == [["AUSDT", "BUSDT"], ["CUSDT"], ["DUSDT"]]
    assert sum(len(x) for x in por_ventana) == len(base.resultado.operaciones)          # cada operación, una sola vez
    assert [sorted({d["simbolo"] for d in BF.registro_de(base, v)}) for v in wf.ventanas] == \
        [["AUSDT", "BUSDT"], ["BUSDT", "CUSDT"], ["DUSDT"]]
    # La corrida va de corrido: BUSDT se abrió en la primera ventana y sigue abierta al empezar la segunda
    rechazo = [d for d in BF.registro_de(base, v2) if d["simbolo"] == "BUSDT"]
    assert [d["codigo"] for d in rechazo] == [DS.YA_HAY_POSICION]
    sin_esa_regla = wf.corridas["A"][DS.YA_HAY_POSICION]
    assert sorted(BF.operaciones_de(sin_esa_regla, v2)["simbolo"]) == ["BUSDT", "CUSDT"]


def test_la_curva_se_corta_por_ventana(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), CFG, _pool(), FILTROS)
    base = wf.corridas["A"][BF.BASE]
    v1, v2, final = wf.ventanas
    c1 = BF.curva_de(base, *v1.prueba)
    c2 = BF.curva_de(base, *v2.prueba)
    assert c1.iloc[0] == 1000.0 and c1.index[0] == v1.prueba[0]
    assert c2.iloc[0] == c1.iloc[-1]                              # cada tramo arranca con lo que dejó el anterior
    assert (c2.index >= v2.prueba[0]).all() and (c2.index < v2.prueba[1]).all()
    toda = BF.curva_de(base, v1.prueba[0], final.prueba[1])
    assert toda.iloc[-1] == pytest.approx(base.resultado.curva.iloc[-1])


def test_anotacion_de_las_ventanas(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), CFG, _pool(), FILTROS)
    assert BF.anotacion_ventanas(wf) == [
        {"ventana": "2023-01", "entrenamiento": "2022-01-01 a 2022-12-31", "prueba": "2023-01-01 a 2023-03-31",
         "senales_vistas_en_entrenamiento": 1},
        {"ventana": "2023-04", "entrenamiento": "2022-04-01 a 2023-03-31", "prueba": "2023-04-01 a 2023-06-30",
         "senales_vistas_en_entrenamiento": 3},
        {"ventana": "prueba final", "entrenamiento": "", "prueba": "2023-07-01 a 2023-12-31",
         "senales_vistas_en_entrenamiento": None},
    ]


def test_sin_prueba_final_y_sin_ventanas(reg):
    r = _dos_ventanas(reg)
    wf = BF.walk_forward(r, CFG, _pool(), FILTROS, con_prueba_final=False)
    assert [v.nombre for v in wf.ventanas] == ["2023-01", "2023-04"]
    assert "DUSDT" not in set(wf.corridas["A"][BF.BASE].candidatos["simbolo"])
    corto = reg.copia_con({"backtest.inicio": "2022-01-01", "backtest.fin": "2022-12-31"})
    with pytest.raises(ValueError, match="No hay ninguna ventana de prueba"):
        BF.walk_forward(corto, CFG, _pool(), FILTROS, con_prueba_final=False)


def test_pool_vacio_no_truena(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), CFG, BF.Pool(base=pd.DataFrame()), FILTROS)
    base = wf.corridas["A"][BF.BASE]
    assert base.resultado.operaciones.empty and BF.operaciones_de(base, wf.ventanas[0]).empty
    assert wf.solo_observado["2023-01"] == {"senales": 0, "por_motor": {}}
    assert BF.curva_de(base, *wf.ventanas[0].prueba).iloc[0] == 1000.0
