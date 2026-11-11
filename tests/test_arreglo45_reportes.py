"""Arreglo 45: pruebas del reporte diario y de la boleta semanal (lo que lee Ángelo)."""
import json
from argparse import Namespace
from datetime import datetime, timezone

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P
from sobreviviente import reportes

AHORA = datetime(2026, 11, 15, 2, 30, tzinfo=timezone.utc)      # la semana empieza el 2026-11-08


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    return r


def _cartera(r, nombre, **cambios):
    est = P.estado_nuevo(nombre, 46.18, "2026-11-01")
    est.update(cambios)
    P.guardar_estado(r, est)
    return est


# ---------------- Reporte diario ----------------

def test_diario_sin_nada_que_reportar(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    lineas = reportes.diario(r).splitlines()
    assert lineas[0].startswith("Reporte del día ") and "PAPEL" in lineas[0]
    for n in "ABC":
        assert f"Cartera {n}: 46.18 USDT (+0.0 % desde que empezó el papel) · 0 abiertas" in lineas
    assert lineas[-1] == "👍 No necesito nada de ti." and len(lineas) <= 10


def test_diario_con_ganancia_y_posicion_abierta(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "C", curva={"2026-11-09": 46.18, "2026-11-10": 50.80}, posiciones=[{"simbolo": "BTCUSDT"}])
    assert "Cartera C: 50.80 USDT (+10.0 % desde que empezó el papel) · 1 abiertas" in reportes.diario(r)


def test_diario_cartera_detenida_pide_respuesta(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "B", detenido=True)
    lineas = reportes.diario(r).splitlines()
    assert "⚠️ Cartera B detenida por caída máxima: necesito tu OK para seguir." in lineas
    assert lineas[-1] == "Necesito tu respuesta." and "👍" not in "".join(lineas)


def test_diario_cartera_que_no_opera_por_capital(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "A", ultimo_dia="2026-11-10", rondas={"2026-11-10": {"opera": False, "capital_necesario": 177.4}})
    _cartera(r, "B", ultimo_dia="2026-11-10", rondas={"2026-11-10": {"opera": False, "capital_necesario": None}})
    texto = reportes.diario(r)
    assert "Cartera A NO opera con el capital actual: sus señales no llegan al mínimo de Binance (necesita unos 177 USDT)." in texto
    assert "Cartera B NO opera con el capital actual: sus señales no llegan al mínimo de Binance." in texto
    assert texto.splitlines()[-1] == "👍 No necesito nada de ti."        # no operar por capital no pide respuesta


def test_diario_muestra_las_referencias_mas_nuevas(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    AR.escribir_json_seguro(P.ruta_papel(r) / "referencias.json",
                            {"2026-11-09": {"R0": 46.18, "R1": 46.18, "R2": 46.18},
                             "2026-11-10": {"R0": 47.5, "R1": 46.9, "R2": 45.02}})
    assert "Para comparar (2026-11-10): BTC 47.50 · BTC con marea 46.90 · canasta 45.02" in reportes.diario(r)


def test_diario_dice_que_bots_tuvieron_errores(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, "RADAR", "verificar", True)
    assert "Bots con errores hoy" not in reportes.diario(r)
    AR.registrar_tarea(r, "CENTINELA", "vetos.json", False, "veto #1: falta la razón")
    AR.registrar_tarea(r, "EJECUTOR", "registrar-llenado", True, "cantidad 2 en vez de 1", diferencias=1)
    linea = next(x for x in reportes.diario(r).splitlines() if x.startswith("Bots con errores hoy"))
    assert "CENTINELA" in linea and "EJECUTOR" in linea and "RADAR" not in linea


def test_diario_nunca_pasa_de_10_lineas(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    for n in "ABC":
        _cartera(r, n, detenido=True, ultimo_dia="2026-11-10", rondas={"2026-11-10": {"opera": False}})
    lineas = reportes.diario(r).splitlines()
    assert len(lineas) <= 10 and lineas[-1] == "Necesito tu respuesta."


# ---------------- Boleta semanal ----------------

def test_semanal_sin_historia(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    lineas = reportes.semanal(r, AHORA).splitlines()
    assert lineas[0] == "BOLETA SEMANAL (papel, sin dinero real)"
    for n in "ABC":
        assert f"Cartera {n}: +0.00 USDT en la semana (+0.0 %), 0 operaciones cerradas, 0 señales saltadas por capital" in lineas
    assert "Grok Bot cuesta unos 70 pesos por semana; la Cartera A ganó en papel unos +0.0 pesos (tipo de cambio 18.00)." in lineas
    assert lineas[-2].startswith("Recuerda: esto es papel.") and lineas[-1] == "👍 No necesito nada de ti."


def test_semanal_cuenta_solo_la_ultima_semana(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "A",
             curva={"2026-11-05": 40.00, "2026-11-08": 46.18, "2026-11-14": 48.18},
             cerradas=[{"t_salida": "2026-11-03 00:00:00+00:00"}, {"t_salida": "2026-11-10 00:00:00+00:00"}],
             saltadas_capital=[{"dia": "2026-11-02", "capital_necesario": 999.0},
                               {"dia": "2026-11-09", "capital_necesario": 150.0},
                               {"dia": "2026-11-10", "capital_necesario": 200.0},
                               {"dia": "2026-11-11", "capital_necesario": 177.0}])
    AR.escribir_json_seguro(P.ruta_papel(r) / "referencias.json",
                            {"2026-11-01": {"R0": 10.0, "R1": 10.0, "R2": 10.0},
                             "2026-11-08": {"R0": 46.18, "R1": 46.18, "R2": 46.18},
                             "2026-11-14": {"R0": 47.1036, "R1": 46.6418, "R2": 46.0}})
    lineas = reportes.semanal(r, AHORA).splitlines()
    assert "Cartera A: +8.18 USDT en la semana (+20.4 %), 1 operaciones cerradas, 3 señales saltadas por capital" in lineas
    assert "   Para no saltarlas habrían hecho falta unos 177 USDT." in lineas          # la de en medio (mediana)
    assert "Referencias en la semana: BTC +2.0 % · BTC con marea +1.0 %" in lineas
    assert "Grok Bot cuesta unos 70 pesos por semana; la Cartera A ganó en papel unos +147.2 pesos (tipo de cambio 18.00)." in lineas


def test_semanal_usa_el_tipo_de_cambio_guardado(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "A", curva={"2026-11-08": 46.18, "2026-11-14": 45.18})
    AR.escribir_json_seguro(tmp_path / "datos" / "tipo_cambio.json", {"mxn_por_usdt": 20.5})
    assert "la Cartera A ganó en papel unos -20.5 pesos (tipo de cambio 20.50)." in reportes.semanal(r, AHORA)
    AR.escribir_json_seguro(tmp_path / "datos" / "tipo_cambio.json", {"mxn_por_usdt": "no es número"})
    AR.escribir_json_seguro(tmp_path / "datos" / "tipo_cambio.json", {"otra_cosa": 1})
    assert "(tipo de cambio 18.00)" in reportes.semanal(r, AHORA)                  # dato raro: se usa el de respaldo


def test_cmd_reporte_registra_la_tarea_del_contador(reg, tmp_path, monkeypatch, capsys):
    r = _reg_tmp(reg, tmp_path)
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    assert CR.cmd_reporte(Namespace(tipo="diario", reglamento=None)) == 0
    assert CR.cmd_reporte(Namespace(tipo="semanal", reglamento=None)) == 0
    salida = capsys.readouterr().out
    assert "Reporte del día" in salida and "BOLETA SEMANAL" in salida
    filas = [json.loads(x) for x in (tmp_path / "datos" / "bots" / "registro.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(f["bot"], f["tarea"], f["ok"]) for f in filas] == [("CONTADOR", "reporte diario", True),
                                                                ("CONTADOR", "reporte semanal", True)]


# ---------------- Arreglo 54: la fecha del reporte es la de CDMX ----------------

def test_diario_usa_la_fecha_de_cdmx_aunque_la_computadora_este_en_utc(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    # 8:30 p. m. del 10 de noviembre en CDMX = 02:30 UTC del día 11: el reporte es del día 10
    noche = datetime(2026, 11, 11, 2, 30, tzinfo=timezone.utc)
    assert reportes.diario(r, noche).splitlines()[0].startswith("Reporte del día 10/11/2026 ")
    manana = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)      # 9:00 a. m. CDMX del 11
    assert reportes.diario(r, manana).splitlines()[0].startswith("Reporte del día 11/11/2026 ")
