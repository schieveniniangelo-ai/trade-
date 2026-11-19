"""Arreglo 152 (ventana del domingo 22 nov 2026): el bloque `futuros_papel:` en reglamento.yaml.

Es igual a `futuros/config.POR_DEFECTO` (no cambia ninguna cifra de F1) y F1 sigue con `activo: false`. La versión sube a
2.0.3 y CAMBIOS.md lo anota. `reglamento.validar` revisa el bloque con los mismos límites duros que `futuros.config`.
Nada de Spot (riesgo, carteras, real, estrategias) cambia por esto."""
from pathlib import Path

import pytest
import yaml

from sobreviviente import reglamento as RGL
from sobreviviente.futuros import config as FC

RAIZ = Path(__file__).resolve().parent.parent


def test_el_bloque_es_igual_a_los_valores_por_defecto():
    r = RGL.cargar()
    assert r.datos["futuros_papel"] == FC.POR_DEFECTO
    assert list(r.datos["futuros_papel"]) == list(FC.POR_DEFECTO)        # mismas claves, mismo orden
    assert r.get("futuros_papel.activo") is False                         # F1 NO PASA: sigue apagado
    assert FC.leer(r) == FC.POR_DEFECTO


def test_version_y_cambios():
    assert RGL.cargar().version == "2.0.3"
    cambios = (RAIZ / "CAMBIOS.md").read_text(encoding="utf-8")
    seccion = cambios[cambios.index("## Reglamento 2.0.3"):]
    assert "Arreglo 152" in seccion and "futuros_papel" in seccion and "**false**" in seccion


def test_cada_cifra_dice_quien_la_decidio():
    texto = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    bloque = texto[texto.index("\nfuturos_papel:\n") + 1:].split("\n\n", 1)[0].splitlines()[1:]
    assert len(bloque) == len(FC.POR_DEFECTO)
    for renglon in bloque:
        clave = renglon.strip().split(":", 1)[0]
        origen = FC.ORIGEN[clave].split(" 2026")[0]                     # DECISIÓN DE ÁNGELO o MECÁNICO
        assert origen in renglon.split("#", 1)[1], renglon


def test_nada_de_spot_cambia():
    """El bloque no toca riesgo, carteras, real ni estrategias: sin él, el reglamento es el mismo."""
    texto = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    datos = yaml.safe_load(texto)
    datos.pop("futuros_papel")
    assert "futuros_papel" not in datos
    assert datos["carteras"]["capital_inicial"] == 142.54
    assert datos["riesgo"]["futuros"]["apalancamiento_max"] == 2 and datos["estrategias"]["E5"]["estado"] == "APAGADA"


@pytest.mark.parametrize("cambio,texto", [
    ({"futuros_papel.apalancamiento_tope": 3}, "apalancamiento_tope = 3"),
    ({"futuros_papel.margen": "CRUZADO"}, "AISLADO"),
    ({"futuros_papel.modo_posicion": "HEDGE"}, "ONE_WAY"),
    ({"futuros_papel.riesgo_por_operacion_pct": 2.5}, "riesgo_por_operacion_pct"),
    ({"futuros_papel.capital_papel": 0}, "capital_papel"),
    ({"futuros_papel.monedas": ["PEPEUSDT"]}, "lista fija"),
    ({"futuros_papel.activo": "si"}, "debe ser true o false"),
    ({"futuros_papel.apalancamieto_tope": 1}, "futuros_papel.apalancamieto_tope: esa clave no existe"),
])
def test_validar_rechaza_el_bloque_fuera_de_los_limites(cambio, texto):
    r = RGL.cargar().copia_con(cambio)
    with pytest.raises(RGL.ErrorReglamento) as e:
        RGL.validar(r)
    assert any(texto in p for p in e.value.problemas), e.value.problemas


def test_validar_rechaza_un_bloque_que_no_es_de_claves():
    r = RGL.cargar().copia_con({"futuros_papel": "si"})
    with pytest.raises(RGL.ErrorReglamento) as e:
        RGL.validar(r)
    assert "futuros_papel debe ser un bloque de claves y valores (arreglo 152)." in e.value.problemas


def test_apalancamiento_de_f1_no_pasa_el_del_reglamento():
    r = RGL.cargar().copia_con({"riesgo.futuros.apalancamiento_max": 1, "estrategias.E5.apalancamiento": 1})
    with pytest.raises(RGL.ErrorReglamento) as e:
        RGL.validar(r)
    assert e.value.problemas == [
        "futuros_papel.apalancamiento_tope (2x) pasa de riesgo.futuros.apalancamiento_max (1x)."]
    assert ("futuros_papel.apalancamiento_tope (2x) pasa de riesgo.futuros.apalancamiento_max (1x)."
            in e.value.problemas)
    RGL.validar(r.copia_con({"futuros_papel.apalancamiento_tope": 1}))      # con 1x cabe


def test_sin_bloque_no_hay_nada_que_revisar():
    r = RGL.cargar()
    r.datos.pop("futuros_papel")
    RGL.validar(r)
    assert FC.leer(r) == FC.POR_DEFECTO


def test_un_bloque_valido_pasa():
    RGL.validar(RGL.cargar().copia_con({"futuros_papel.monedas": ["SOLUSDT"], "futuros_papel.apalancamiento_tope": 1}))
