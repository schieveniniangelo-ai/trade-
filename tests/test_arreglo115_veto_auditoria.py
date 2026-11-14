"""Arreglo 115 (parte 1): los pasos `veto` y `auditoria` de ejecutar_v2, con datos falsos, sin red ni velas.

veto: M1 y M2 con el veto de ESTELA (H2), cuenta señales con y sin veto en las mismas ventanas de la corrida sin veto,
guarda M{1,2}_veto con esos conteos y sin las listas internas de Monte Carlo, y deja el mercado sin veto al final.
auditoria: carga el mercado de 1 h, corre A1–A9 y guarda el resultado.
"""
from types import SimpleNamespace

import pandas as pd
import pytest

from sobreviviente import ejecutar_v2


@pytest.fixture
def salida_v2(tmp_path, monkeypatch):
    carpeta = tmp_path / "v2"
    monkeypatch.setattr(ejecutar_v2, "SALIDA", carpeta)
    monkeypatch.setattr(ejecutar_v2.D, "ClienteBinance", lambda reg: "cliente-falso")   # sin red
    return carpeta


def _ventanas(n):
    return [{"params": {"sma": 100 + i}, "inicio": pd.Timestamp(f"2024-0{i + 1}-01", tz="UTC"),
             "fin": pd.Timestamp(f"2024-0{i + 2}-01", tz="UTC")} for i in range(n)]


def _fakes(monkeypatch):
    from sobreviviente import estela as ES
    from sobreviviente import validacion_v2 as V2
    idx = pd.date_range("2024-01-01", periods=3, tz="UTC")
    md = SimpleNamespace(veto=None, _ctx={"viejo": 1}, velas={"BTCUSDT": 1},
                         grandes=pd.DataFrame({"ETHUSDT": [False, True, False], "BTCUSDT": [True, True, True],
                                               "DOGEUSDT": [False, False, False]}, index=idx))
    vistos = {"veto_pedido": None, "conteos": [], "lentos": []}
    refs = {k: SimpleNamespace(nombre=k, por_anio={}, curvas={}, invertido=None,
                               metricas={"fuera_de_muestra": {"calmar": 0.7 if k == "R1" else 0.1,
                                                              "rend_total_pct": 1.0, "caida_max_pct": 2.0}})
            for k in ("R0", "R1", "R2")}
    monkeypatch.setattr(ejecutar_v2, "mercado_diario", lambda reg: md)
    monkeypatch.setattr(V2, "referencias", lambda m: refs)

    def dias_veto(reg, cli, simbolos):
        vistos["veto_pedido"] = (cli, simbolos)
        return {"ETHUSDT": ["2024-01-02"], "BTCUSDT": []}
    monkeypatch.setattr(ES, "dias_veto_h2", dias_veto)

    def conteo(m, clave, params, a, b, con_veto):
        vistos["conteos"].append((clave, params["sma"], con_veto, m.veto is not None))
        return [0] * (3 if con_veto else 5)
    monkeypatch.setattr(ejecutar_v2, "DI_generar_conteo", conteo)

    def evaluar_lento(m, clave, calmar_r1, avisar):
        vistos["lentos"].append((clave, calmar_r1, sorted(m.veto), dict(m._ctx)))
        return SimpleNamespace(pasa=clave == "M2", ventanas=[], mc={"caida_p95": 8.0, "_caidas": [1.0]},
                               mc_bloques={"racha_p95": 9, "_interno": 0})
    monkeypatch.setattr(V2, "evaluar_lento", evaluar_lento)
    return md, vistos


def test_veto_valida_m1_y_m2_con_el_veto_y_cuenta_senales(reg, salida_v2, monkeypatch):
    md, vistos = _fakes(monkeypatch)
    ejecutar_v2._guardar("M1", {"ventanas": _ventanas(2)})
    ejecutar_v2._guardar("M2", {"ventanas": _ventanas(1)})
    avisos = []
    ejecutar_v2.ejecutar(reg, ["veto"], avisar=avisos.append)
    assert vistos["veto_pedido"] == ("cliente-falso", ["BTCUSDT", "ETHUSDT"])      # solo las que alguna vez fueron grandes
    assert vistos["conteos"] == [("M1", 100, False, True), ("M1", 101, False, True),
                                 ("M1", 100, True, True), ("M1", 101, True, True),
                                 ("M2", 100, False, True), ("M2", 100, True, True)]
    assert [x[:3] for x in vistos["lentos"]] == [("M1", 0.7, ["BTCUSDT", "ETHUSDT"]), ("M2", 0.7, ["BTCUSDT", "ETHUSDT"])]
    assert all(x[3] == {} for x in vistos["lentos"])                               # sin contextos de antes del veto
    m1, m2 = ejecutar_v2.cargar_resultado("M1_veto"), ejecutar_v2.cargar_resultado("M2_veto")
    assert (m1["candidatos_sin_veto"], m1["candidatos_con_veto"]) == (10, 6)
    assert (m2["candidatos_sin_veto"], m2["candidatos_con_veto"]) == (5, 3)
    assert m1["mc"] == {"caida_p95": 8.0} and m1["mc_bloques"] == {"racha_p95": 9}
    assert m1["pasa"] is False and m2["pasa"] is True
    assert md.veto is None                                                          # el mercado queda sin veto
    assert avisos[0] == "Veto de ESTELA: datos para 2 monedas"
    assert any(a.startswith("  M1 con veto: NO PASA (10 → 6 señales fuera de muestra) en ") for a in avisos)
    assert any(a.startswith("  M2 con veto: PASA (5 → 3 señales fuera de muestra) en ") for a in avisos)
    # no escribió nada más que los dos resultados nuevos (y los de entrada)
    assert sorted(p.name for p in salida_v2.glob("*.json")) == ["M1.json", "M1_veto.json", "M2.json", "M2_veto.json"]


def test_veto_reusa_el_mercado_ya_cargado(reg, salida_v2, monkeypatch):
    md, vistos = _fakes(monkeypatch)
    cargas = []
    monkeypatch.setattr(ejecutar_v2, "mercado_diario", lambda reg: cargas.append(1) or md)
    from sobreviviente import validacion_v2 as V2
    monkeypatch.setattr(V2, "evaluar_m0", lambda m, r: {"m0": True})
    ejecutar_v2._guardar("M1", {"ventanas": []})
    ejecutar_v2._guardar("M2", {"ventanas": []})
    ejecutar_v2.ejecutar(reg, ["referencias", "veto"], avisar=lambda *_: None)
    assert cargas == [1]                                                            # una sola carga de velas
    assert ejecutar_v2.cargar_resultado("M1_veto")["candidatos_con_veto"] == 0


def test_auditoria_carga_el_mercado_de_1h_y_guarda(reg, salida_v2, monkeypatch):
    from sobreviviente import auditoria as A
    from sobreviviente import backtest as B
    vistos = []
    monkeypatch.setattr(ejecutar_v2, "_memes", lambda: ["PEPEUSDT"])
    monkeypatch.setattr(B, "cargar_mercado", lambda reg, cli, memes: vistos.append((cli, memes)) or "mercado-1h")

    def auditar(m, avisar):
        vistos.append(m)
        avisar("A1 listo")
        return {"A1": {"operaciones": 12, "expectativa_r": -0.02}, "A9": {"nota": "sin cambios"}}
    monkeypatch.setattr(A, "ejecutar", auditar)
    avisos = []
    ejecutar_v2.ejecutar(reg, ["auditoria"], avisar=avisos.append)
    assert vistos == [("cliente-falso", ["PEPEUSDT"]), "mercado-1h"]
    assert ejecutar_v2.cargar_resultado("auditoria") == {"A1": {"operaciones": 12, "expectativa_r": -0.02},
                                                         "A9": {"nota": "sin cambios"}}
    assert avisos[0] == "Cargando velas de 1 h para la auditoría de la v1 (tarda)…"
    assert avisos[1].startswith("  listo en ") and avisos[2] == "A1 listo"


def test_auditoria_sola_no_carga_velas_diarias(reg, salida_v2, monkeypatch):
    from sobreviviente import auditoria as A
    from sobreviviente import backtest as B

    def no_debe(reg):
        raise AssertionError("la auditoría no usa las velas diarias")
    monkeypatch.setattr(ejecutar_v2, "mercado_diario", no_debe)
    monkeypatch.setattr(ejecutar_v2, "_memes", lambda: [])
    monkeypatch.setattr(B, "cargar_mercado", lambda reg, cli, memes: "m")
    monkeypatch.setattr(A, "ejecutar", lambda m, avisar: {"ok": True})
    ejecutar_v2.ejecutar(reg, ["auditoria"], avisar=lambda *_: None)
    assert ejecutar_v2.cargar_resultado("auditoria") == {"ok": True}
