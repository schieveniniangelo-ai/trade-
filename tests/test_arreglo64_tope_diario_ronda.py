"""Arreglo 64 (PROPUESTAS.md A1, decisión de Ángelo): el tope diario de pérdida sí frena con una ronda al día.

La pérdida del día es el capital de ESTA ronda contra el capital de la ronda anterior. El "día" es el día UTC de la
hora oficial de la ronda (00:10 UTC). Al tocar el tope no se abren compras nuevas hasta las 00:00 UTC del día UTC
siguiente; lo abierto sigue con su stop. Todo con velas falsas: sin red y sin llaves."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from sobreviviente import backtest as BT
from sobreviviente import papel as P
from sobreviviente import riesgo as R

from conftest import CDMX, hacer_cand, hacer_estado
from test_arreglo1_papel import _reg_m0
from test_papel import _buscar_dia_con_compra, _datos_dia, _reg_papel

DIA = pd.Timedelta(days=1)


def _hora_ronda(dd):
    """Hora oficial de la ronda que procesa el día `dd.dia`: 00:10 UTC del día siguiente."""
    return (dd.dia + DIA + pd.Timedelta(minutes=10)).to_pydatetime()


def _dos_dias_de_marea_alta(reg):
    for k in range(260, 650, 5):
        if all(_datos_dia(reg, j)[0].md.marea.get(_datos_dia(reg, j)[0].dia) == "ALCISTA" for j in (k, k + 1)):
            return k
    pytest.skip("los datos sintéticos no dieron dos días seguidos de marea alta")


def _dejar_cartera(r, cartera, dd, anterior, hoy, **extra):
    """Deja la cartera como si la ronda anterior (ayer, en UTC) hubiera terminado con `anterior` USDT y hoy, sin
    posiciones abiertas, tuviera `hoy` USDT."""
    ahora = _hora_ronda(dd)
    est = P.cargar_estado(r, cartera, "")
    est.update({"efectivo": hoy, "pico": anterior, "capital_inicio_dia": anterior,
                "dia_ref": (R.inicio_dia_utc(ahora) - timedelta(days=1)).isoformat(),
                "capital_inicio_semana": anterior, "semana_ref": R.inicio_semana(r, ahora).isoformat()})
    est.update(extra)
    P.guardar_estado(r, est)


def _compras(c):
    return [b for b in c["boletos"] if b["accion"] == "COMPRAR"]


def _resumen(c):
    return P.resumen_corto({"dia": c["dia"], "carteras": {c["cartera"]: c}, "referencias": {}, "avisos": []})


# ---------------- La ronda de papel ----------------

def test_perdida_menor_que_el_tope_si_compra(reg, tmp_path):
    """Ayer 100, hoy 97.1: se perdió 2.9 %, menos que el tope de 3 % de la Cartera A. La compra sale."""
    r = _reg_m0(reg, tmp_path, capital=100.0)
    dd = _datos_dia(r, _dos_dias_de_marea_alta(r))[0]
    _dejar_cartera(r, "A", dd, 100.0, 97.1)
    c = P.ronda_cartera(r, "A", dd, [], [])
    assert _compras(c), c["mensajes"]
    assert c["pausa"] == ""
    texto = _resumen(c)
    assert "tope diario" not in texto and texto.endswith("👍 No necesito nada de ti.")
    est = P.cargar_estado(r, "A", "")
    # Después de medir, el capital de esta ronda queda como referencia de la ronda siguiente
    assert est["capital_inicio_dia"] == pytest.approx(97.1)
    assert est["dia_ref"] == R.inicio_dia_utc(_hora_ronda(dd)).isoformat()


@pytest.mark.parametrize("hoy, perdida", [(97.0, "3.0"), (96.0, "4.0")])
def test_al_tocar_o_pasar_el_tope_no_hay_compras_y_avisa(reg, tmp_path, hoy, perdida):
    r = _reg_m0(reg, tmp_path, capital=100.0)
    dd = _datos_dia(r, _dos_dias_de_marea_alta(r))[0]
    _dejar_cartera(r, "A", dd, 100.0, hoy)
    c = P.ronda_cartera(r, "A", dd, [], [])
    assert _compras(c) == []
    assert any("PAUSA activa (tope diario" in m for m in c["mensajes"]), c["mensajes"]   # había señal y no entró
    assert c["pausa"] == f"tope diario: se perdió {perdida} % hoy (tope 3.0 %)"
    texto = _resumen(c)
    assert f"⚠️ Cartera A sin compras nuevas hoy por tope diario: se perdió {perdida} % hoy (tope 3.0 %)" in texto
    assert "👍" not in texto and texto.endswith("Solo para que sepas; no tienes que contestar.")
    est = P.cargar_estado(r, "A", "")
    # La pausa dura hasta las 00:00 UTC del día UTC siguiente al de la ronda
    assert datetime.fromisoformat(est["pausa_hasta"]) == (dd.dia + 2 * DIA).to_pydatetime()
    assert est["capital_inicio_dia"] == pytest.approx(hoy)


def test_reintento_el_mismo_dia_utc_sigue_sin_compras(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=100.0)
    dd = _datos_dia(r, _dos_dias_de_marea_alta(r))[0]
    _dejar_cartera(r, "A", dd, 100.0, 97.0)
    primera = P.ronda_cartera(r, "A", dd, [], [])
    repetida = P.ronda_cartera(r, "A", dd, [], [])
    assert _compras(primera) == [] and repetida == primera
    assert "👍" not in _resumen(repetida)
    # Reintento "de verdad": se borra la marca de que el día ya se procesó y la ronda se vuelve a calcular.
    est = P.cargar_estado(r, "A", "")
    est["ultimo_dia"] = None
    est["rondas"].pop(primera["dia"])
    est["efectivo"] = 96.9
    P.guardar_estado(r, est)
    otra = P.ronda_cartera(r, "A", dd, [], [])
    assert _compras(otra) == [] and otra["pausa"].startswith("tope diario")
    assert "👍" not in _resumen(otra)
    # La referencia del día NO se pisa en el reintento: sigue siendo el capital de la primera pasada
    assert P.cargar_estado(r, "A", "")["capital_inicio_dia"] == pytest.approx(97.0)


def test_el_dia_utc_siguiente_vuelven_las_compras(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=100.0)
    k = _dos_dias_de_marea_alta(r)
    dd = _datos_dia(r, k)[0]
    _dejar_cartera(r, "A", dd, 100.0, 96.0)
    assert _compras(P.ronda_cartera(r, "A", dd, [], [])) == []                 # hoy: tope diario, sin compras
    manana = P.ronda_cartera(r, "A", _datos_dia(r, k + 1)[0], [], [])          # mañana: 96 contra 96, sin pérdida
    assert _compras(manana), manana["mensajes"]
    assert manana["pausa"] == ""
    texto = _resumen(manana)
    assert "tope diario" not in texto and texto.endswith("👍 No necesito nada de ti.")


def test_con_tope_diario_una_posicion_abierta_si_sube_su_stop(reg, tmp_path):
    """Con el tope diario tocado no hay compras, pero el stop de lo abierto sí se sube a favor."""
    r = _reg_papel(reg, tmp_path)                       # motor M1, capital 1000
    k = _buscar_dia_con_compra(r)
    c = P.ronda_cartera(r, "A", _datos_dia(r, k)[0], [], [])
    assert _compras(c), c["mensajes"]
    stops = []
    for j in range(k + 1, k + 60):
        est = P.cargar_estado(r, "A", "")
        if stops or not est["posiciones"]:
            break
        est["capital_inicio_dia"] = c["capital"] * 1.05          # la ronda anterior "dejó" 5 % más que hoy
        P.guardar_estado(r, est)
        c = P.ronda_cartera(r, "A", _datos_dia(r, j)[0], [], [])
        assert _compras(c) == [], j
        assert c["pausa"].startswith("tope diario: se perdió"), (j, c["pausa"])
        assert "👍" not in _resumen(c)
        stops = [b for b in c["boletos"] if b["accion"] == "MODIFICAR_STOP"]
    assert stops, "ninguna posición subió su stop con el tope diario tocado"


def test_con_tope_diario_una_posicion_abierta_si_se_cierra(reg, tmp_path, monkeypatch):
    """Con el tope diario tocado, si a una posición abierta le toca salir, su boleto CERRAR sí sale."""
    r = _reg_m0(reg, tmp_path, capital=100.0)
    k = _dos_dias_de_marea_alta(r)
    c = P.ronda_cartera(r, "A", _datos_dia(r, k)[0], [], [])
    assert _compras(c), c["mensajes"]
    est = P.cargar_estado(r, "A", "")
    est["capital_inicio_dia"] = c["capital"] * 1.05              # la ronda anterior "dejó" 5 % más que hoy
    P.guardar_estado(r, est)
    original = P._senales

    def pide_salir(dd, clave, simbolo, params):
        sen = original(dd, clave, simbolo, params)
        if sen is not None:
            sen = sen.copy()
            sen["salir"], sen["entrada"] = True, False
        return sen

    monkeypatch.setattr(P, "_senales", pide_salir)
    c = P.ronda_cartera(r, "A", _datos_dia(r, k + 1)[0], [], [])
    cierres = [b for b in c["boletos"] if b["accion"] == "CERRAR"]
    assert cierres and cierres[0]["tipo_orden"] == "MARKET", c["boletos"]
    assert _compras(c) == [] and c["pausa"].startswith("tope diario: se perdió")
    texto = _resumen(c)
    assert "vende BTCUSDT" in texto and "⚠️ Cartera A sin compras nuevas hoy por tope diario" in texto
    assert "👍" not in texto


def test_el_tope_semanal_sigue_y_la_referencia_diaria_no_pisa_la_semanal(reg, tmp_path):
    """Semana empezó en 100, ayer terminó en 95, hoy 93.9: en el día se perdió 1.2 % (no toca el diario), pero en
    la semana 6.1 % (sí toca el semanal de 6 %)."""
    r = _reg_m0(reg, tmp_path, capital=100.0)
    dd = _datos_dia(r, _dos_dias_de_marea_alta(r))[0]
    _dejar_cartera(r, "A", dd, 95.0, 93.9, capital_inicio_semana=100.0, pico=100.0)
    c = P.ronda_cartera(r, "A", dd, [], [])
    assert _compras(c) == []
    assert c["pausa"].startswith("tope semanal: se perdió 6.1 %")
    assert "Cartera A en pausa: tope semanal" in _resumen(c)
    est = P.cargar_estado(r, "A", "")
    assert est["capital_inicio_semana"] == pytest.approx(100.0)       # la semanal no se tocó
    assert est["capital_inicio_dia"] == pytest.approx(93.9)           # la diaria sí avanzó
    lunes = R.siguiente_lunes(r, _hora_ronda(dd))
    assert datetime.fromisoformat(est["pausa_hasta"]) == lunes and lunes.tzinfo == CDMX   # la semana sigue en CDMX


def test_semana_nueva_reinicia_la_referencia_semanal_como_antes(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=100.0)
    dd = _datos_dia(r, _dos_dias_de_marea_alta(r))[0]
    semana_pasada = (R.inicio_semana(r, _hora_ronda(dd)) - timedelta(days=7)).isoformat()
    _dejar_cartera(r, "A", dd, 95.0, 93.9, capital_inicio_semana=100.0, pico=100.0, semana_ref=semana_pasada)
    c = P.ronda_cartera(r, "A", dd, [], [])
    assert c["pausa"] == "" and _compras(c), c["mensajes"]
    assert P.cargar_estado(r, "A", "")["capital_inicio_semana"] == pytest.approx(93.9)


def test_la_caida_desde_el_pico_sigue_deteniendo(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=100.0)
    dd = _datos_dia(r, _dos_dias_de_marea_alta(r))[0]
    _dejar_cartera(r, "A", dd, 100.0, 100.0, pico=120.0)             # 16.7 % abajo del pico; hoy no perdió nada
    c = P.ronda_cartera(r, "A", dd, [], [])
    assert c["detenido"] is True and _compras(c) == []
    texto = _resumen(c)
    assert "⚠️ Cartera A DETENIDA por caída máxima: necesita tu OK." in texto
    assert texto.endswith("Necesito tu respuesta (ver arriba).")


# ---------------- El motor de riesgo ----------------

def test_el_dia_del_tope_diario_es_el_dia_utc():
    ronda = datetime(2026, 11, 10, 18, 10, tzinfo=CDMX)              # 6:10 p. m. CDMX = 00:10 UTC del día 11
    assert R.inicio_dia_utc(ronda) == datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)
    assert R.siguiente_dia_utc(ronda) == datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)


def test_la_pausa_cubre_los_reintentos_del_dia_y_se_acaba_en_la_ronda_siguiente(reg, filtros):
    ronda = datetime(2026, 11, 11, 0, 10, tzinfo=timezone.utc)
    e = hacer_estado(1000)
    e.capital = 970                                                  # justo 3 %: tocar el tope también cuenta
    msgs = R.aplicar_topes(reg, e, ronda)
    assert "tope diario: se perdió 3.0 % hoy (tope 3.0 %)" in msgs[0]
    assert e.pausa_hasta == datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)
    for reintento in (ronda, ronda + timedelta(hours=5), datetime(2026, 11, 11, 23, 59, tzinfo=timezone.utc)):
        d = R.evaluar_candidato(reg, e, hacer_cand(), filtros, reintento)
        assert not d.aprobada and "PAUSA activa (tope diario" in d.razon
    e.capital_inicio_dia = e.capital                                 # lo que hace la ronda después de medir
    siguiente = datetime(2026, 11, 12, 0, 10, tzinfo=timezone.utc)
    assert R.aplicar_topes(reg, e, siguiente) == []
    assert R.evaluar_candidato(reg, e, hacer_cand(), filtros, siguiente).aprobada


def test_por_debajo_del_tope_no_hay_pausa(reg):
    e = hacer_estado(1000)
    e.capital = 971                                                  # 2.9 %
    assert R.aplicar_topes(reg, e, datetime(2026, 11, 11, 0, 10, tzinfo=timezone.utc)) == []
    assert e.pausa_hasta is None


# ---------------- El backtest ----------------

def _fila(simbolo, t, pnl_unidad):
    return {"estrategia": "E1", "simbolo": simbolo, "t_senal": t - DIA, "t_decision": t, "precio_plan": 100.0,
            "stop": 95.0, "meta": None, "fuerza": 1.0, "comision_pct": 0.1, "desliz_pct": 0.05, "liquidez": "ALTA",
            "regimen_btc": None, "vol_btc": float("nan"), "vol_moneda": float("nan"), "mercado": "SPOT",
            "lado": "LARGO", "cubeta": "normales", "t_entrada": t, "t_salida": t + pd.Timedelta(hours=12),
            "entrada": 100.05, "pnl_unidad": pnl_unidad, "stops_t": [], "stops": []}


def test_backtest_mide_contra_el_dia_utc_anterior(reg):
    """Día 1: una operación pierde 3 % o más. Día 2 (UTC): la señal NO entra por el tope diario. Día 3: sí entra."""
    d1 = pd.Timestamp("2026-11-10 00:00", tz="UTC")
    cands = pd.DataFrame([_fila("AAAUSDT", d1, -20.0), _fila("BBBUSDT", d1 + DIA, 1.0),
                          _fila("CCCUSDT", d1 + 2 * DIA, 1.0)])
    res = BT.cartera(reg, cands, 1000.0, {})
    dec = res.decisiones.sort_values("t_decision")
    assert list(dec["aprobada"]) == [True, False, True], list(dec["razon"])
    assert "PAUSA activa (tope diario" in dec["razon"].iloc[1]
    perdida = (1000.0 - dec["capital"].iloc[1]) / 1000.0 * 100.0
    assert 3.0 <= perdida < 6.0                                      # tocó el diario y no el semanal
    assert res.pausas == 1
