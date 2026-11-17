"""Arreglo 162: holdout de MONEDAS sellado (Hipótesis 004). SOLO PAPEL.

Monedas declaradas el 2026-11-17 y nunca usadas en F1: las de `variantes.MONEDAS_HOLDOUT`. Mismo periodo, mismos datos,
mismas reglas y mismo filtro de liquidez. `validar-futuros --variante X --holdout` solo corre si el renglón más reciente
de X en VARIANTES_FUTUROS.md pasó las 15 compuertas sin contar «escalones», y UNA sola vez por variante. Pasa con ≥ 30
operaciones, expectativa ≥ 0R normal y ≥ 0R con estrés; con menos de 30 es «sin veredicto» (no cuenta como pasar).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from apoyo_futuros import ClienteFalso
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import liquidacion as LQ
from sobreviviente.futuros import validar as VF
from sobreviviente.futuros import variantes as VR
from test_arreglo151_validar_futuros import _mercado

RAIZ = Path(__file__).resolve().parent.parent
HOLDOUT = ("ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT")


def test_las_monedas_del_holdout_estan_declaradas_y_no_son_de_f1():
    assert VR.MONEDAS_HOLDOUT == HOLDOUT
    assert not set(HOLDOUT) & set(config.MONEDAS_PERMITIDAS)
    assert not set(HOLDOUT) & set(LQ._tabla()["monedas"])
    for s in HOLDOUT:
        r = VR.RESPALDO_HOLDOUT[s]
        assert r["filtros"].simbolo == s and r["filtros"].minimo_usdt >= 5.0
        assert r["escalones"][0]["mmr_pct"] == 1.0 and r["tarifa_liq_pct"] >= 1.25    # supuestos conservadores


def test_ninguna_otra_parte_del_codigo_lee_esas_monedas():
    hallazgos = []
    archivos = [p for p in (RAIZ / "sobreviviente").rglob("*") if p.is_file() and "__pycache__" not in p.parts
                and p.suffix in (".py", ".json", ".yaml", ".yml", ".md", ".txt") and p.name != "variantes.py"]
    archivos += [RAIZ / "reglamento.yaml"] + sorted((RAIZ / "bots").glob("*.md"))
    assert len(archivos) > 20
    for p in archivos:
        texto = p.read_text(encoding="utf-8", errors="replace").upper()
        for s in HOLDOUT:
            if s in texto or s[:-4] + "/USDT" in texto:
                hallazgos.append(f"{p.relative_to(RAIZ)}: {s}")
    assert not hallazgos, hallazgos


@pytest.mark.parametrize("n,e,ee,esperado", [(30, 0.0, 0.0, "PASA"), (120, 0.2, 0.05, "PASA"),
                                              (30, 0.1, -0.01, "NO PASA"), (30, -0.01, 0.2, "NO PASA"),
                                              (29, 1.0, 1.0, "SIN VEREDICTO"), (0, 0.0, 0.0, "SIN VEREDICTO")])
def test_veredicto_del_holdout(n, e, ee, esperado):
    assert VF.veredicto_holdout(n, e, ee) == esperado


def _fila(variante, pasa_sin_escalones, tipo="completa", veredicto=None):
    return {"fecha_utc": "2026-11-17 21:00", "commit": "abc1234", "variante": variante, "tipo": tipo,
            "veredicto": veredicto or (VF.VEREDICTO_SIN_ESCALONES if pasa_sin_escalones else "NO PASA"),
            "pasa_sin_escalones": pasa_sin_escalones, "compuertas": "14/15", "operaciones": 120,
            "expectativa_r": 0.2, "factor": 1.5, "t": 2.5, "azar_pct": 99.5, "estres_r": 0.1, "largo_r": 0.2,
            "corto_r": float("nan")}


def test_puede_holdout_lee_el_registro(tmp_path):
    ruta = tmp_path / "VARIANTES_FUTUROS.md"
    ok, razon = VR.puede_holdout(VR.leer_registro(ruta), "F1-L")
    assert not ok and "no tiene corrida completa" in razon
    VR.registrar_corrida(ruta, _fila("F1-L", True))
    VR.registrar_corrida(ruta, _fila("F1-L", False))           # el renglón MÁS RECIENTE es el que cuenta
    ok, razon = VR.puede_holdout(VR.leer_registro(ruta), "F1-L")
    assert not ok and "no pasó" in razon
    VR.registrar_corrida(ruta, _fila("F1-L", True))
    assert VR.puede_holdout(VR.leer_registro(ruta), "F1-L") == (True, "")
    assert not VR.puede_holdout(VR.leer_registro(ruta), "F1-LT")[0]   # otra variante no hereda el pase
    VR.registrar_corrida(ruta, _fila("F1-L", False, tipo="holdout", veredicto="SIN VEREDICTO"))
    ok, razon = VR.puede_holdout(VR.leer_registro(ruta), "F1-L")
    assert not ok and "una sola vez" in razon


def _mercado_holdout(reg):
    """El mercado sintético del 151 con las monedas renombradas a las del holdout."""
    m = _mercado(reg)
    nombres = dict(zip(m.cfg["monedas"], HOLDOUT))
    cfg = {**m.cfg, "monedas": list(HOLDOUT)}
    r = VR.RESPALDO_HOLDOUT
    return VF.MercadoF1(reg, cfg, {nombres[s]: x for s, x in m.velas.items()},
                        {nombres[s]: x for s, x in m.funding.items()}, {nombres[s]: x for s, x in m.marca4h.items()},
                        {nombres[s]: x for s, x in m.precio_funding.items()}, m.btc1d,
                        {nombres[s]: x for s, x in m.liquido.items()}, {s: r[s]["filtros"] for s in HOLDOUT},
                        {s: r[s]["tarifa_liq_pct"] for s in HOLDOUT}, escalones={s: r[s]["escalones"] for s in HOLDOUT})


def _preparar(tmp_path, monkeypatch):
    yaml = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    (tmp_path / "reglamento.yaml").write_text(yaml, encoding="utf-8")
    reg = RGL.cargar(tmp_path / "reglamento.yaml").copia_con(
        {"datos.carpeta": str(tmp_path / "datos"), "backtest.inicio": "2023-01-01", "backtest.fin": "2024-06-30",
         "validacion.azar_n": 30, "validacion.montecarlo_n": 100})
    pedidos = []

    def cargar(r, c, cfg, **k):
        pedidos.append((list(cfg["monedas"]), k))
        return _mercado_holdout(reg)
    monkeypatch.setattr(VF, "cargar_mercado", cargar)
    args = type("A", (), {"sin_robustez": True, "commit": "abc1234", "variante": "F1-L", "holdout": True})()
    return reg, args, pedidos


def test_se_niega_sin_el_pase_previo(tmp_path, monkeypatch, capsys):
    reg, args, pedidos = _preparar(tmp_path, monkeypatch)
    assert FC.comando_validar(reg, args, ClienteFalso(reg)) == 1
    assert "no tiene corrida completa" in capsys.readouterr().out and pedidos == []     # ni siquiera abre los datos
    VR.registrar_corrida(tmp_path / "VARIANTES_FUTUROS.md", _fila("F1-L", False))
    assert FC.comando_validar(reg, args, ClienteFalso(reg)) == 1
    assert "no pasó" in capsys.readouterr().out and pedidos == []
    assert not list(tmp_path.glob("*holdout*"))


def test_corre_una_vez_con_menos_de_30_es_sin_veredicto_y_se_niega_la_segunda(tmp_path, monkeypatch, capsys):
    reg, args, pedidos = _preparar(tmp_path, monkeypatch)
    ruta = tmp_path / "VARIANTES_FUTUROS.md"
    VR.registrar_corrida(ruta, _fila("F1-L", True))
    assert FC.comando_validar(reg, args, ClienteFalso(reg)) == 0
    salida = capsys.readouterr().out
    assert pedidos and pedidos[0][0] == list(HOLDOUT) and "respaldo" in pedidos[0][1]
    texto = (tmp_path / "VALIDACION_FUTUROS_F1-L_holdout.md").read_text(encoding="utf-8")
    filas = VR.leer_registro(ruta)
    assert [f["tipo"] for f in filas] == ["completa", "holdout"]
    h = filas[-1]
    assert int(h["operaciones"]) < 30 and h["veredicto"] == "SIN VEREDICTO" and h["pasa_sin_escalones"] is False
    assert "SIN VEREDICTO" in texto and "no cuenta como pasar" in texto and "SIN VEREDICTO" in salida
    for s in HOLDOUT:
        assert s in texto
    # la segunda vez se niega (aunque haya otro pase completo después)
    VR.registrar_corrida(ruta, _fila("F1-L", True))
    assert FC.comando_validar(reg, args, ClienteFalso(reg)) == 1
    assert "una sola vez" in capsys.readouterr().out and len(pedidos) == 1
    assert len(VR.leer_registro(ruta)) == 3


def test_evaluar_holdout_usa_las_mismas_reglas(tmp_path):
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "d"), "backtest.inicio": "2023-01-01",
                                  "backtest.fin": "2024-06-30"})
    m = _mercado_holdout(reg)
    res = VF.evaluar_holdout(m, "F1")
    assert res.resumen["operaciones"] == 25                     # mismas señales y selección que F1 en esas series
    assert set(res.oos["simbolo"]) <= set(HOLDOUT) and res.veredicto == "SIN VEREDICTO" and not res.pasa
    assert res.estres["operaciones"] == 25
