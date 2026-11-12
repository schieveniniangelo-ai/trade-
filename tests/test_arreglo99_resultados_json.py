"""Arreglo 99: ejecutar_v2 guarda y lee los resultados en JSON (sin pickle) y los tipos regresan iguales."""
from __future__ import annotations

import ast
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sobreviviente import ejecutar_v2

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def salida_v2(tmp_path, monkeypatch):
    carpeta = tmp_path / "v2"
    monkeypatch.setattr(ejecutar_v2, "SALIDA", carpeta)
    return carpeta


def _igual(a, b) -> None:
    """Igualdad estricta: mismo tipo y mismo valor, también dentro de Series, DataFrame y contenedores."""
    assert type(a) is type(b), (a, b)
    if isinstance(a, pd.Series):
        pd.testing.assert_series_equal(a, b, check_freq=False)
    elif isinstance(a, pd.DataFrame):
        pd.testing.assert_frame_equal(a, b, check_freq=False)
    elif isinstance(a, pd.Index):
        pd.testing.assert_index_equal(a, b)
    elif isinstance(a, np.ndarray):
        assert a.dtype == b.dtype and np.array_equal(a, b)
    elif isinstance(a, dict):
        assert list(a) == list(b)
        for k in a:
            assert type(k) is type(next(x for x in b if x == k))
            _igual(a[k], b[k])
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            _igual(x, y)
    elif isinstance(a, float) and math.isnan(a):
        assert math.isnan(b)
    elif a is pd.NaT:
        assert b is pd.NaT
    else:
        assert a == b
        if isinstance(a, pd.Timestamp):
            assert str(a.tz) == str(b.tz)


def _resultado_como_los_reales():
    fechas = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    return {
        "nombre": "Marea", "pasa": False, "combos": 12, "concentracion_top5": float("nan"),
        "calmar_r1_oos": float("inf"), "peor": float("-inf"),
        "curva_oos": pd.Series([1.0, 1.1, float("nan"), 0.9], index=fechas, name="curva"),
        "curvas": {"fuera_de_muestra": pd.Series([100.0, 101.5], index=fechas[:2])},
        "por_anio": {2024: 1.5, 2025: -0.25},                     # llaves enteras
        "comisiones": {0.001: {"calmar": 0.4}, 0.002: {"calmar": 0.3}},   # llaves flotantes
        "compuertas": {"expectativa": (True, "expectativa ≥ 0"), "azar": (False, "le gana al azar")},
        "ventanas": [{"inicio": fechas[0], "fin": fechas[2], "params": {"n": np.int64(20), "x": np.float64(0.5)}}],
        "ops": pd.DataFrame({"simbolo": ["BTCUSDT", "ETHUSDT"], "r": [1.25, -1.0], "t": fechas[:2],
                             "gano": [True, False], "n": [3, 4]}),
        "vacio": pd.DataFrame(), "serie_vacia": pd.Series([], dtype=float),
        "sin_fecha": pd.NaT, "dia": date(2026, 10, 31), "hora": datetime(2026, 11, 1, 18, 10, tzinfo=timezone.utc),
        "naive": pd.Timestamp("2026-11-01 18:10"), "cdmx": pd.Timestamp("2026-11-01 18:10", tz="America/Mexico_City"),
        "duracion": pd.Timedelta(hours=36), "arreglo": np.array([1.5, 2.5]), "simbolos": {"BTCUSDT"},
        "booleano_np": np.bool_(True), "nan_np": np.float64("nan"), "entero_np": np.int32(-7), "anidado": [[1, (2, 3)], {"__tipo__": "texto que parece marca"}],
        "btc_desde": None,
    }


def test_guarda_json_y_los_tipos_regresan_iguales(salida_v2):
    obj = _resultado_como_los_reales()
    ejecutar_v2._guardar("M1", obj)
    assert sorted(p.name for p in salida_v2.iterdir()) == ["M1.json"]
    _igual(obj, ejecutar_v2.cargar_resultado("M1"))


def test_el_archivo_es_json_estricto(salida_v2):
    ejecutar_v2._guardar("M1", _resultado_como_los_reales())

    def sin_constantes(c):
        raise AssertionError(f"JSON no estricto: {c}")

    json.loads((salida_v2 / "M1.json").read_text(encoding="utf-8"), parse_constant=sin_constantes)


def test_un_tipo_desconocido_es_error_y_no_deja_archivo(salida_v2):
    class Raro:
        pass

    with pytest.raises(TypeError, match="Raro"):
        ejecutar_v2._guardar("M1", {"x": Raro()})
    assert not salida_v2.exists() or list(salida_v2.iterdir()) == []
    assert ejecutar_v2.cargar_resultado("M1") is None


def test_una_marca_desconocida_es_error(salida_v2):
    salida_v2.mkdir()
    (salida_v2 / "M1.json").write_text('{"__tipo__": "pickle"}', encoding="utf-8")
    with pytest.raises(ValueError, match="pickle"):
        ejecutar_v2.cargar_resultado("M1")


def test_volver_a_guardar_reemplaza_el_archivo(salida_v2):
    ejecutar_v2._guardar("M0", {"pasa": False})
    ejecutar_v2._guardar("M0", {"pasa": True})
    assert ejecutar_v2.cargar_resultado("M0") == {"pasa": True}
    assert sorted(p.name for p in salida_v2.iterdir()) == ["M0.json"]


def test_ejecutar_v2_e_informe_v2_no_usan_pickle():
    for modulo in ("ejecutar_v2.py", "informe_v2.py"):
        arbol = ast.parse((RAIZ / "sobreviviente" / modulo).read_text(encoding="utf-8"))
        importados = {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        importados |= {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
        assert not importados & {"pickle", "cPickle", "dill", "joblib", "shelve"}, modulo
