"""Arreglo 126: el capital de arranque es el saldo real del 15 nov 2026 (142.54 USDT), no 46.18.

Solo cambian dos valores del reglamento (carteras.capital_inicial y backtest.capital_real) y sus comentarios; la versión
la sube el arreglo 140 y la cartera C se queda igual."""
from pathlib import Path

from sobreviviente import papel as P
from sobreviviente import reglamento

RAIZ = Path(__file__).resolve().parent.parent


def test_los_dos_valores_son_el_saldo_real():
    r = reglamento.cargar()
    assert r.get("carteras.capital_inicial") == 142.54
    assert r.get("backtest.capital_real") == 142.54


def test_la_version_y_la_cartera_c_no_cambian():
    r = reglamento.cargar()
    c = r.get("carteras.C")
    assert c["tamano"] == "exposicion" and c["riesgo_por_operacion_pct"] == 4.5
    assert c["caida_max_desde_pico_pct"] == 30.0 and c["posiciones_max"] == {"normales": 1, "memes": 0, "futuros": 0}
    assert r.get("carteras.A.riesgo_por_operacion_pct") == 1.0 and r.get("carteras.B.riesgo_por_operacion_pct") == 2.0


def test_los_comentarios_dicen_la_historia():
    texto = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    linea_c = next(x for x in texto.splitlines() if x.strip().startswith("# Pedida por Ángelo (10 nov 2026)"))
    assert "46.18" in linea_c and "142.54" in texto.split("tamano:")[0].split("C:")[-1]
    linea_bt = next(x for x in texto.splitlines() if x.strip().startswith("capital_real:"))
    assert "46.18" in linea_bt and "15 nov" in linea_bt


def test_una_cartera_nueva_arranca_en_142_54(tmp_path):
    r = reglamento.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})
    for n in P.CARTERAS:
        est = P.cargar_estado(r, n, "2026-11-16")
        assert est["capital_inicial"] == est["efectivo"] == est["pico"] == 142.54
