"""Arreglo 161: validar-futuros --variante {F1,F1-L,F1-LC,F1-LT} con las mismas compuertas más dos. SOLO PAPEL.

Mismas 13 compuertas del 151 con: azar ≥ 99.17 % (156); en F1-L y F1-LT «largo» > 0R en vez de «largo y corto» (el corto
se sigue reportando si lo hay); y dos nuevas: «significancia» (t = expectativa ÷ (desviación ÷ √n) ≥ 2.2414) y
«escalones» (todas las monedas verificadas: hoy falla a propósito). Mismas ventanas y mismas 4 monedas. Nada escribe
`activo`. Cada corrida agrega un renglón a VARIANTES_FUTUROS.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from apoyo_futuros import ClienteFalso
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import liquidacion as LQ
from sobreviviente.futuros import validar as VF
from sobreviviente.futuros import variantes as VR
from test_arreglo151_validar_futuros import _mercado, _reg

RAIZ = Path(__file__).resolve().parent.parent
BASE13 = ["operaciones", "factor_ganancia", "expectativa", "ventanas", "caida_p95", "azar", "robustez",
          "liquidaciones", "estres", "largo_y_corto", "concentracion", "sin_una_moneda", "no_caben"]


def _claves(variante):
    lado = "largo" if VR.variante(variante)["lados"] == "largo" else "largo_y_corto"
    return [lado if k == "largo_y_corto" else k for k in BASE13] + ["significancia", "escalones"]


@pytest.fixture(scope="module")
def corridas(tmp_path_factory):
    reg = _reg(tmp_path_factory.mktemp("v"))
    m = _mercado(reg)
    return {v: VF.evaluar(m, robustez_on=False, variante=v) for v in sorted(VR.VARIANTES)}


def test_cada_variante_corre_con_sus_15_compuertas(corridas):
    for v, res in corridas.items():
        assert res.variante == v and list(res.compuertas) == _claves(v), v
        assert all(isinstance(ok, bool) and txt for ok, txt in res.compuertas.values())
        assert "99.2 %" in res.compuertas["azar"][1]                     # la barra de 12 ideas
        assert res.compuertas["escalones"][0] is False                     # hoy no hay escalones verificados
        assert res.pasa is False                                           # sin escalones nunca PASA del todo
        sin = all(ok for k, (ok, _) in res.compuertas.items() if k != "escalones")
        assert res.pasa_sin_escalones == sin
        assert res.veredicto == ("PASA SIN ESCALONES VERIFICADOS → no se puede activar" if sin else "NO PASA")
    for v in ("F1-L", "F1-LT"):
        assert not (corridas[v].oos["lado"] == "CORTO").any() if len(corridas[v].oos) else True
    assert (corridas["F1-LT"].oos["motivo"] == "tiempo").any()            # la salida por tiempo sí actúa
    assert not (corridas["F1-L"].oos["motivo"] == "tiempo").any()


def test_f1_con_variante_tiene_las_mismas_operaciones_que_sin_variante(corridas, tmp_path):
    viejo = VF.evaluar(_mercado(_reg(tmp_path)), robustez_on=False)
    assert list(viejo.compuertas) == BASE13 and viejo.variante is None    # sin variante: el 151 tal cual
    nuevo = corridas["F1"]
    assert list(nuevo.oos["t_senal"]) == list(viejo.oos["t_senal"])
    assert np.allclose(nuevo.oos["r"].to_numpy(float), viejo.oos["r"].to_numpy(float))


def test_t_y_significancia(corridas):
    res = corridas["F1"]
    r = res.oos["r"].to_numpy(float)
    assert res.resumen["t"] == pytest.approx(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))))
    assert np.isnan(VF.estadistico_t(np.array([0.5])))          # n = 1: sin t
    assert np.isnan(VF.estadistico_t(np.array([])))


def _res_que_pasa(**cambios):
    base = dict(
        resumen={"operaciones": 150, "factor_ganancia": 1.5, "expectativa_r": 0.2, "ventanas_positivas_pct": 70,
                 "liquidaciones": 0, "t": 2.5},
        mc={"caida_p95": 20.0}, mc_bloques={"caida_p95": 24.0}, azar={"percentil_estrategia": 99.5},
        robustez={"todas_positivas": True, "minimo": 0.05}, estres={"operaciones": 150, "expectativa_r": 0.06},
        por_lado={"LARGO": {"operaciones": 150, "expectativa_r": 0.2}, "CORTO": {"operaciones": 0, "expectativa_r": 0.0}},
        por_moneda={s: {"parte_pct": 25.0} for s in config.MONEDAS_PERMITIDAS},
        sin_moneda={s: 0.15 for s in config.MONEDAS_PERMITIDAS}, capital={"no_caben_pct": 10.0})
    base.update(cambios)
    return VF.ResultadoF1(**base)


def test_una_t_de_2_falla_la_significancia_y_2_25_pasa():
    reg = RGL.cargar()
    cfg = dict(config.POR_DEFECTO)
    c = VF.compuertas_variante(_res_que_pasa(), cfg, 25.0, reg, "F1-L")
    assert all(ok for k, (ok, _) in c.items() if k != "escalones"), c
    assert "largo" in c and "largo_y_corto" not in c
    r2 = _res_que_pasa(resumen={**_res_que_pasa().resumen, "t": 2.0})
    c2 = VF.compuertas_variante(r2, cfg, 25.0, reg, "F1-L")
    assert c2["significancia"][0] is False and "2.24" in c2["significancia"][1]
    assert VF.compuertas_variante(_res_que_pasa(resumen={**r2.resumen, "t": 2.25}), cfg, 25.0, reg,
                                  "F1-L")["significancia"][0]
    # azar: 99.0 pasaba con 9 ideas (98.9 %) y ya no con 12 (99.17 %)
    assert not VF.compuertas_variante(_res_que_pasa(azar={"percentil_estrategia": 99.0}), cfg, 25.0, reg,
                                      "F1-L")["azar"][0]
    # en F1 y F1-LC sigue «largo y corto»: sin cortos falla
    assert VF.compuertas_variante(_res_que_pasa(), cfg, 25.0, reg, "F1")["largo_y_corto"][0] is False
    # en F1-L el corto se sigue REPORTANDO si lo hay
    con_corto = _res_que_pasa(por_lado={"LARGO": {"operaciones": 140, "expectativa_r": 0.2},
                                        "CORTO": {"operaciones": 10, "expectativa_r": -0.3}})
    ok, txt = VF.compuertas_variante(con_corto, cfg, 25.0, reg, "F1-L")["largo"]
    assert ok and "corto" in txt and "-0.300R" in txt


def test_escalones_verificados_cambian_esa_compuerta(monkeypatch):
    tabla = LQ._tabla()
    falsa = {**tabla, "monedas": {s: {**x, "verificado": True} for s, x in tabla["monedas"].items()}}
    assert not LQ.todas_verificadas(config.MONEDAS_PERMITIDAS)
    assert LQ.sin_verificar(config.MONEDAS_PERMITIDAS) == list(config.MONEDAS_PERMITIDAS)
    monkeypatch.setattr(LQ, "_tabla", lambda: falsa)
    assert LQ.todas_verificadas(config.MONEDAS_PERMITIDAS) and LQ.sin_verificar(["SOLUSDT"]) == []
    c = VF.compuertas_variante(_res_que_pasa(), dict(config.POR_DEFECTO), 25.0, RGL.cargar(), "F1-L")
    assert all(ok for ok, _ in c.values())


def test_validar_variante_escribe_su_informe_y_un_renglon_por_corrida(tmp_path, monkeypatch, capsys):
    yaml = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    (tmp_path / "reglamento.yaml").write_text(yaml, encoding="utf-8")
    reg = RGL.cargar(tmp_path / "reglamento.yaml").copia_con(
        {"datos.carpeta": str(tmp_path / "datos"), "backtest.inicio": "2023-01-01", "backtest.fin": "2024-06-30",
         "validacion.azar_n": 30, "validacion.montecarlo_n": 100})
    monkeypatch.setattr(VF, "cargar_mercado", lambda r, c, cfg, **k: _mercado(reg))
    args = type("A", (), {"sin_robustez": True, "commit": "abc1234", "variante": "F1-L", "holdout": False})()
    assert FC.comando_validar(reg, args, ClienteFalso(reg)) == 0
    salida = capsys.readouterr().out
    texto = (tmp_path / "VALIDACION_FUTUROS_F1-L.md").read_text(encoding="utf-8")
    assert "**Veredicto: F1-L " in texto and "Hipótesis 004" in texto and "abc1234" in texto
    assert "significancia" in texto and "escalones" in texto and "Nada de esto promete ganancias" in texto
    assert not (tmp_path / "VALIDACION_FUTUROS.md").exists()             # solo F1 base escribe el de futuros-papel
    assert "F1-L" in salida and "VARIANTES_FUTUROS.md" in salida
    filas = VR.leer_registro(tmp_path / "VARIANTES_FUTUROS.md")
    assert len(filas) == 1 and filas[0]["variante"] == "F1-L" and filas[0]["tipo"] == "completa"
    assert filas[0]["commit"] == "abc1234" and filas[0]["compuertas"].endswith("/15")
    args.variante = "F1"
    assert FC.comando_validar(reg, args, ClienteFalso(reg)) == 0
    assert [f["variante"] for f in VR.leer_registro(tmp_path / "VARIANTES_FUTUROS.md")] == ["F1-L", "F1"]
    f1 = (tmp_path / "VALIDACION_FUTUROS.md").read_text(encoding="utf-8")
    assert f1 == (tmp_path / "VALIDACION_FUTUROS_F1.md").read_text(encoding="utf-8")
    assert not FC.validacion_pasa(reg)                                     # sin escalones nunca dice «F1 PASA.»
    # el veredicto nunca escribe activo
    assert (tmp_path / "reglamento.yaml").read_text(encoding="utf-8") == yaml
    for arch in tmp_path.glob("*.md"):
        assert "activo: true" not in arch.read_text(encoding="utf-8").lower()
    assert config.leer(reg)["activo"] is False


def test_variante_desconocida_en_la_linea_de_comandos(capsys):
    from sobreviviente import __main__ as M
    with pytest.raises(SystemExit):
        M.main(["validar-futuros", "--variante", "F9"])
    assert "F1-LT" in capsys.readouterr().err
