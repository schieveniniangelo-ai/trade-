"""Arreglo 77: la boleta semanal mide la ganancia de cada cartera (y la línea de Grok Bot de la Cartera A) contra el
último capital guardado ANTES de la semana; si no hay ninguno, contra el capital inicial.

Así, sin rondas en la semana el cambio es 0 (antes salía toda la ganancia desde que empezó el papel) y el primer
día de la semana sí cuenta. Misma ventana que test_arreglo45: `ahora` = 2026-11-15, la semana empieza el 2026-11-08.
Sin red ni llaves."""
from datetime import datetime, timezone

from sobreviviente import papel as P
from sobreviviente import reportes

AHORA = datetime(2026, 11, 15, 2, 30, tzinfo=timezone.utc)


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    return r


def _cartera(r, nombre, curva):
    est = P.estado_nuevo(nombre, 46.18, "2026-11-01")
    est["curva"] = curva
    P.guardar_estado(r, est)


def _linea(lineas, inicio):
    return next(x for x in lineas if x.startswith(inicio))


def test_sin_rondas_en_la_semana_el_cambio_es_cero(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "A", {"2026-11-01": 40.0, "2026-11-05": 50.0})          # nada desde el 2026-11-08
    lineas = reportes.semanal(r, AHORA).splitlines()
    assert _linea(lineas, "Cartera A:").startswith("Cartera A: +0.00 USDT en la semana (+0.0 %)")
    assert "la Cartera A ganó en papel unos +0.0 pesos (tipo de cambio 18.00)." in _linea(lineas, "Grok Bot")


def test_el_primer_dia_de_la_semana_si_cuenta(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "A", {"2026-11-05": 40.00, "2026-11-08": 46.18, "2026-11-14": 48.18})
    lineas = reportes.semanal(r, AHORA).splitlines()
    # El capital previo a la semana es el del 2026-11-05 (40.00), no el del 2026-11-08 (46.18).
    # 8.18 / 40 = 20.45 % exacto; con el formato de siempre (:+.1f) se muestra +20.4.
    assert _linea(lineas, "Cartera A:").startswith("Cartera A: +8.18 USDT en la semana (+20.4 %)")
    assert "la Cartera A ganó en papel unos +147.2 pesos (tipo de cambio 18.00)." in _linea(lineas, "Grok Bot")


def test_las_dos_lineas_usan_la_misma_regla(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "A", {"2026-11-03": 44.00, "2026-11-12": 45.00})
    lineas = reportes.semanal(r, AHORA).splitlines()
    assert _linea(lineas, "Cartera A:").startswith("Cartera A: +1.00 USDT en la semana")
    assert "la Cartera A ganó en papel unos +18.0 pesos" in _linea(lineas, "Grok Bot")      # 1.00 × 18


def test_sin_curva_igual_que_antes(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    _cartera(r, "A", {})
    lineas = reportes.semanal(r, AHORA).splitlines()
    for n in "ABC":
        assert _linea(lineas, f"Cartera {n}:").startswith(f"Cartera {n}: +0.00 USDT en la semana (+0.0 %)")
    assert "la Cartera A ganó en papel unos +0.0 pesos (tipo de cambio 18.00)." in _linea(lineas, "Grok Bot")
