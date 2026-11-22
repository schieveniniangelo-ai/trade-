"""Arreglo 156: registro de variantes de F1 (Hipótesis 004) y barra por pruebas múltiples. SOLO PAPEL.

Variantes declaradas ANTES de medir (MECÁNICO por delegación de Ángelo, 2026-11-17): F1, F1-L, F1-LC y F1-LT. Cuentan 4
pruebas en la familia F1 → 8 + 4 = 12 ideas: azar ≥ 100 − 10/12 = 99.17 % y t ≥ 2.2414 (Bonferroni α = 0.05/4).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sobreviviente import reglamento as RGL
from sobreviviente.estrategias import f1 as F1
from sobreviviente.futuros import variantes as VR

RAIZ = Path(__file__).resolve().parent.parent


def test_las_cuatro_variantes_existen_con_su_dict_fijo():
    assert set(VR.VARIANTES) == {"F1", "F1-L", "F1-LC", "F1-LT"}
    assert VR.variante("F1") == {"lados": "ambos", "tiempo_max_velas": None}
    assert VR.variante("F1-L") == {"lados": "largo", "tiempo_max_velas": None}
    assert VR.variante("F1-LC") == {"lados": "largo+corto_fuerte", "tiempo_max_velas": None}
    assert VR.variante("F1-LT") == {"lados": "largo", "tiempo_max_velas": 30}
    for v in VR.VARIANTES.values():
        assert v["lados"] in ("ambos", "largo", "largo+corto_fuerte") and v["tiempo_max_velas"] in (None, 30)
    # copia: nadie cambia la variante por accidente
    d = VR.variante("F1-LT")
    d["tiempo_max_velas"] = 99
    assert VR.variante("F1-LT")["tiempo_max_velas"] == 30
    # no son parámetros de F1: no entran a la rejilla ni a la robustez
    assert not set(F1.PARAMETROS) & {"lados", "tiempo_max_velas", "variante"}
    assert VR.PRUEBAS_FAMILIA == 4 == len(VR.VARIANTES)


@pytest.mark.parametrize("nombre", ["F2", "f1-l", "", "F1-LCT", None])
def test_una_variante_desconocida_es_error(nombre):
    with pytest.raises(VR.ErrorVariante):
        VR.variante(nombre)


def test_barras_por_pruebas_multiples():
    reg = RGL.cargar()
    assert reg.get("validacion.ronda2.ideas_probadas") == 8          # el reglamento NO cambia
    assert VR.ideas_totales(reg) == 12
    assert VR.azar_min(reg) == pytest.approx(99.1667, abs=1e-4)
    assert VR.t_min() == pytest.approx(2.2414, abs=1e-4)


def _fila(variante, veredicto="NO PASA", tipo="completa"):
    return {"fecha_utc": "2026-11-17 20:00", "commit": "abc1234", "variante": variante, "tipo": tipo,
            "veredicto": veredicto, "pasa_sin_escalones": False, "compuertas": "3/15", "operaciones": 126,
            "expectativa_r": -0.034, "factor": 0.93, "t": -0.4, "azar_pct": 52.4, "estres_r": -0.071,
            "largo_r": 0.114, "corto_r": -0.353}


def test_el_registro_solo_crece(tmp_path):
    ruta = tmp_path / "VARIANTES_FUTUROS.md"
    VR.registrar_corrida(ruta, _fila("F1"))
    primero = ruta.read_text(encoding="utf-8")
    VR.registrar_corrida(ruta, _fila("F1-L", "PASA SIN ESCALONES VERIFICADOS → no se puede activar"))
    segundo = ruta.read_text(encoding="utf-8")
    assert segundo.startswith(primero) and len(segundo) > len(primero)      # agrega, no reemplaza
    filas = VR.leer_registro(ruta)
    assert [f["variante"] for f in filas] == ["F1", "F1-L"]
    assert filas[0]["veredicto"] == "NO PASA" and filas[0]["pasa_sin_escalones"] is False
    assert filas[1]["tipo"] == "completa" and filas[0]["commit"] == "abc1234"
    # una tercera con la misma variante también agrega (nunca se reemplaza un renglón)
    VR.registrar_corrida(ruta, _fila("F1"))
    assert [f["variante"] for f in VR.leer_registro(ruta)] == ["F1", "F1-L", "F1"]
    assert ruta.read_text(encoding="utf-8").startswith(segundo)


def test_un_registro_sin_tabla_conserva_su_texto_y_agrega_la_tabla(tmp_path):
    ruta = tmp_path / "VARIANTES_FUTUROS.md"
    ruta.write_text("# notas de Ángelo", encoding="utf-8")
    VR.registrar_corrida(ruta, _fila("F1-LC"))
    texto = ruta.read_text(encoding="utf-8")
    assert texto.startswith("# notas de Ángelo\n") and "| Fecha UTC |" in texto
    assert [f["variante"] for f in VR.leer_registro(ruta)] == ["F1-LC"]
    assert VR.leer_registro(tmp_path / "no_existe.md") == []


def test_el_registro_del_repositorio_existe_y_se_lee():
    ruta = RAIZ / "VARIANTES_FUTUROS.md"
    assert ruta.exists()
    texto = ruta.read_text(encoding="utf-8")
    assert "solo se agregan renglones" in texto.lower()
    assert isinstance(VR.leer_registro(ruta), list)


def test_hipotesis_004_registrada_antes_de_medir():
    texto = (RAIZ / "HIPOTESIS.md").read_text(encoding="utf-8")
    assert "### Hipótesis 004 — variantes F1-L, F1-LC y F1-LT" in texto
    h = texto[texto.index("### Hipótesis 004"):]
    for frase in ("2026-11-17", "5619f84", "| F1 (base, ya medida) | nada |", "| F1-L | sin cortos |",
                  "| F1-LT | F1-L + salida por tiempo", "99.17 %", "2.24", "Bailey y López de Prado",
                  "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551", "ADAUSDT, LINKUSDT, AVAXUSDT y LTCUSDT"):
        assert frase in h, frase


def test_hipotesis_005_registrada_antes_de_medir():
    texto = (RAIZ / "HIPOTESIS.md").read_text(encoding="utf-8")
    assert "### Hipótesis 005 — Ruptura de rango de 20 días en 4 h" in texto
    h = texto[texto.index("### Hipótesis 005"):]
    for frase in ("2026-11-22", "c6ad0ef", "120 cierres", "2.5 × ATR(14)", "99.545 %", "2.576",
                  "ADAUSDT, LINKUSDT, AVAXUSDT y LTCUSDT", "PASA FRÁGIL"):
        assert frase in h, frase
