"""Arreglo 95: ninguna prueba escribe en los datos reales del papel.

Una prueba usaba el reglamento real y cada corrida de pytest agregaba una fila a datos/bots/registro.jsonl: la
calificación de los bots y el reporte diario mostraban errores del EJECUTOR que nunca pasaron. La guarda de
conftest toma la huella (tamaño y hora) de datos/ (sin datos/cache/, las copias de Binance) y de salida/ antes y
después de cada prueba, y falla si algo cambió. Aquí se prueba la huella con una raíz falsa.
"""
from pathlib import Path

from conftest import huella_datos_reales


def _raiz(tmp_path):
    for d in ("datos/bots", "datos/papel", "datos/cache/spot", "salida"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "datos" / "bots" / "registro.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "datos" / "vetos.json").write_text("{}", encoding="utf-8")
    (tmp_path / "salida" / "boletos_2026-11-11.json").write_text("[]", encoding="utf-8")
    return tmp_path


def _cambiados(antes, despues):
    return sorted(k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k))


def test_la_huella_ve_archivos_cambiados_y_nuevos_en_datos_y_salida(tmp_path):
    raiz = _raiz(tmp_path)
    antes = huella_datos_reales(raiz)
    assert set(antes) == {str(Path("datos", "bots", "registro.jsonl")), str(Path("datos", "vetos.json")),
                          str(Path("salida", "boletos_2026-11-11.json"))}
    with open(raiz / "datos" / "bots" / "registro.jsonl", "a", encoding="utf-8") as f:
        f.write("{}\n")
    (raiz / "datos" / "papel" / "cartera_C.json").write_text("{}", encoding="utf-8")
    (raiz / "salida" / "boletos_2026-11-12.json").write_text("[]", encoding="utf-8")
    assert _cambiados(antes, huella_datos_reales(raiz)) == sorted([
        str(Path("datos", "bots", "registro.jsonl")), str(Path("datos", "papel", "cartera_C.json")),
        str(Path("salida", "boletos_2026-11-12.json"))])


def test_la_huella_no_mira_las_copias_de_binance(tmp_path):
    raiz = _raiz(tmp_path)
    antes = huella_datos_reales(raiz)
    (raiz / "datos" / "cache" / "spot" / "BTCUSDT.csv.gz").write_bytes(b"velas")
    (raiz / "datos" / "cache" / "exchangeinfo_spot.json").write_text("{}", encoding="utf-8")
    assert huella_datos_reales(raiz) == antes


def test_sin_carpetas_la_huella_queda_vacia(tmp_path):
    assert huella_datos_reales(tmp_path) == {}
