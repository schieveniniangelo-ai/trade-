"""Arreglo 142: la prueba de oro del papel no falla por un redondeo de 1 ULP.

Los boletos se siguen comparando al bit. En `resumenes` y `estados` los números se comparan con una tolerancia estrecha
(rel 1e-12, abs 1e-9): 1081.303914159338 y 1081.3039141593383 son lo mismo; una diferencia de 0.01 USDT, un texto, una
llave o una lista distinta siguen haciendo fallar la prueba."""
import copy
import gzip
import json
from pathlib import Path

import oro_papel_escenario as ORO

ORO_ARCHIVO = Path(__file__).parent / "datos_arreglo133" / "oro_papel_e216bd5.json.gz"


def _oro():
    with gzip.open(ORO_ARCHIVO, "rt", encoding="utf-8") as f:
        return json.load(f)


def test_un_ulp_no_es_diferencia():
    assert ORO.diferencias({"capital": 1081.303914159338}, {"capital": 1081.3039141593383}) == []
    assert ORO.diferencias([1064.484708165134, 3], [1064.4847081651342, 3]) == []
    assert ORO.diferencias(0.0, 1e-12) == []


def test_un_centavo_si_es_diferencia():
    malos = ORO.diferencias({"C": {"capital": 1081.31}}, {"C": {"capital": 1081.30}})
    assert len(malos) == 1 and malos[0].startswith("/C/capital:")
    assert ORO.diferencias(100.0, 100.01) != []
    assert ORO.diferencias(0.0, 0.01) != []


def test_textos_llaves_listas_y_tipos_siguen_exactos():
    assert ORO.diferencias("BTCUSDT (M0): entra", "BTCUSDT (M0): entra ") != []
    assert ORO.diferencias({"a": 1}, {"a": 1, "b": 2}) != []
    assert ORO.diferencias([1, 2], [1, 2, 3]) != []
    assert ORO.diferencias(None, 0.0) != []
    assert ORO.diferencias(True, 1) != []                 # un bool no es un número
    assert ORO.diferencias(False, 0.0) != []


def test_con_la_referencia_real_un_centavo_falla_y_un_ulp_no():
    antes = _oro()
    dia = "2023-03-25"
    capital = antes["resumenes"][dia]["C"]["capital"]
    ulp = copy.deepcopy(antes)
    ulp["resumenes"][dia]["C"]["capital"] = 1081.303914159338
    ulp["estados"]["C"]["curva"][dia] = 1081.303914159338
    assert abs(capital - 1081.303914159338) < 1e-9
    assert ORO.diferencias(ulp["resumenes"], antes["resumenes"]) == []
    assert ORO.diferencias(ulp["estados"], antes["estados"]) == []
    centavo = copy.deepcopy(antes)
    centavo["resumenes"][dia]["C"]["capital"] = capital + 0.01
    centavo["estados"]["C"]["curva"][dia] = capital + 0.01
    assert ORO.diferencias(centavo["resumenes"], antes["resumenes"]) == [
        f"/{dia}/C/capital: {capital + 0.01!r} != {capital!r}"]
    assert len(ORO.diferencias(centavo["estados"], antes["estados"])) == 1


def test_la_prueba_de_oro_sigue_comparando_los_boletos_al_bit():
    fuente = (Path(__file__).parent / "test_arreglo133_compuertas_real.py").read_text(encoding="utf-8")
    assert 'assert ahora["boletos"] == antes["boletos"]' in fuente
    assert 'ORO.diferencias(ahora["resumenes"], antes["resumenes"]) == []' in fuente
    assert 'ORO.diferencias(ahora["estados"], antes["estados"]) == []' in fuente
