"""Arreglo 143: F1 v2 de Futuros es SOLO PAPEL. Guardián «sin órdenes» y configuración propia (futuros_papel).

El paquete sobreviviente/futuros/ y estrategias/f1.py no pueden tener rutas que cambien algo en Binance, llaves ni
firmas, ni mandar nada que no sea un GET. Tampoco se cruzan con el código de Spot (real ni papel).
"""
from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

from sobreviviente import reglamento as RGL

RAIZ = Path(__file__).resolve().parent.parent
PKG = RAIZ / "sobreviviente"
PROHIBIDOS = ("/fapi/v1/order", "algoorder", "batchorders", "/fapi/v1/leverage", "margintype", "positionside/dual",
              "listenkey", "signature", "x-mbx-apikey", "api_key", "secret", "hmac",
              ".post(", ".delete(", ".put(")
SPOT = ("real", "ronda_real", "cli_real", "papel", "cli_ronda")


def _archivos_f1() -> list[Path]:
    out = sorted((PKG / "futuros").rglob("*.py"))
    f1 = PKG / "estrategias" / "f1.py"
    if f1.exists():
        out.append(f1)
    return out


def _sin_comentarios(fuente: str) -> str:
    """El código sin comentarios, con los tokens pegados (así «.post(» se encuentra aunque tenga espacios)."""
    piezas = [t.string for t in tokenize.generate_tokens(io.StringIO(fuente).readline) if t.type != tokenize.COMMENT]
    return "".join(piezas).lower()


def _importa(arch: Path) -> set[str]:
    """Nombres de módulos de sobreviviente que importa un archivo (relativos o absolutos)."""
    arbol = ast.parse(arch.read_text(encoding="utf-8-sig"))
    out: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                out.update(a.name.split("."))
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                out.update(nodo.module.split("."))
            out.update(a.name for a in nodo.names)
    return out


def test_el_paquete_existe_y_es_solo_papel():
    from sobreviviente import futuros
    assert futuros.SOLO_PAPEL is True
    assert (PKG / "futuros" / "config.py").exists()


def test_sin_rutas_de_ordenes_llaves_ni_metodos_que_cambian_algo():
    hallazgos = []
    archivos = _archivos_f1()
    assert archivos, "no hay archivos de F1"
    for arch in archivos:
        codigo = _sin_comentarios(arch.read_text(encoding="utf-8-sig"))
        for p in PROHIBIDOS:
            if p in codigo:
                hallazgos.append(f"{arch.relative_to(RAIZ)}: {p}")
    assert not hallazgos, "F1 es SOLO PAPEL: " + "; ".join(hallazgos)


def test_futuros_no_se_cruza_con_spot_en_ningun_sentido():
    for arch in _archivos_f1():
        cruces = _importa(arch) & set(SPOT)
        assert not cruces, f"{arch.relative_to(RAIZ)} importa {cruces}"
    for nombre in SPOT:
        imps = _importa(PKG / f"{nombre}.py")
        assert "futuros" not in imps and "f1" not in imps, f"{nombre}.py importa futuros"


def test_con_el_reglamento_actual_la_configuracion_es_la_por_defecto():
    from sobreviviente.futuros import config
    reg = RGL.cargar()
    assert reg.get("futuros_papel") == config.POR_DEFECTO   # arreglo 152: el bloque es igual a los valores por defecto
    cfg = config.leer(reg)
    assert cfg == config.POR_DEFECTO
    assert cfg is not config.POR_DEFECTO                # copia: nadie cambia los valores por defecto por accidente
    assert cfg["capital_papel"] == 42.54
    assert cfg["monedas"] == ["SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]
    assert cfg["riesgo_por_operacion_pct"] == 1.0
    assert cfg["activo"] is False
    assert cfg["apalancamiento_tope"] == 2 and cfg["margen"] == "AISLADO" and cfg["modo_posicion"] == "ONE_WAY"
    assert reg.get("carteras.capital_inicial") == 142.54   # el papel de Spot NO cambia
    for k in cfg:                                       # cada cifra dice quién la decidió (sale en el reporte)
        assert k in config.ORIGEN, k


@pytest.mark.parametrize("cambio", [
    {"apalancamiento_tope": 3}, {"apalancamiento_tope": 0.5}, {"margen": "CRUZADO"}, {"modo_posicion": "HEDGE"},
    {"riesgo_por_operacion_pct": 2.5}, {"capital_papel": 0}, {"capital_papel": -1},
    {"monedas": ["SOLUSDT", "PEPEUSDT"]}, {"monedas": ["BTCUSDT"]},
])
def test_leer_rechaza_valores_fuera_de_los_limites(cambio):
    from sobreviviente.futuros import config
    reg = RGL.cargar().copia_con({f"futuros_papel.{k}": v for k, v in cambio.items()})
    with pytest.raises(config.ErrorConfigFuturos):
        config.leer(reg)


def test_leer_mezcla_un_bloque_valido():
    from sobreviviente.futuros import config
    reg = RGL.cargar().copia_con({"futuros_papel.monedas": ["SOLUSDT", "XRPUSDT"]})
    cfg = config.leer(reg)
    assert cfg["monedas"] == ["SOLUSDT", "XRPUSDT"]
    assert cfg["capital_papel"] == 42.54


def test_leer_rechaza_bloques_mal_formados_y_reporta_el_origen():
    from sobreviviente.futuros import config
    base = RGL.cargar()
    for cambios in ({"futuros_papel": "si"}, {"futuros_papel.monedas": "SOLUSDT"},
                    {"futuros_papel.apalancamiento_tope": "2"}, {"futuros_papel.riesgo_por_operacion_pct": True}):
        with pytest.raises(config.ErrorConfigFuturos):
            config.leer(base.copia_con(cambios))
    renglones = config.renglones_origen(config.leer(base))
    assert any(r.startswith("capital_papel: 42.54 — DECISIÓN DE ÁNGELO 2026-11-16") for r in renglones)
    assert any(r.startswith("riesgo_por_operacion_pct: 1.0 — MECÁNICO por delegación de Ángelo") for r in renglones)
