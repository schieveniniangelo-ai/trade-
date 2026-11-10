"""Pruebas del modo papel: ronda repetible, modo seguro, esquemas de archivos de bots, boletos claros."""
import json

import numpy as np
import pandas as pd
import pytest

from sobreviviente import archivos as AR
from sobreviviente import diario as DI
from sobreviviente import papel as P
from sobreviviente.exchange import Filtros

from test_v2 import diarias


def _reg_papel(reg, tmp_path):
    # Capital de prueba de 1000 USDT para que los mínimos de Binance no estorben (con 46 USDT casi todo se salta).
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos"), "carteras.capital_inicial": 1000.0})
    for k in r.estrategias:
        r.datos["estrategias"][k]["estado"] = "APAGADA"
    r.datos["estrategias"]["M1"]["estado"] = "PAPEL"
    r.datos["estrategias"]["M1"]["parametros"] = {"n": 20}
    r.ruta = tmp_path / "reglamento.yaml"
    return r


def _datos_dia(reg, dia_idx=500):
    velas = {s: diarias(700, semilla=i + 20, tendencia=0.0012 + 0.0004 * i) for i, s in enumerate(["BTCUSDT", "AUSDT", "BUSDT", "CUSDT"])}
    for df in velas.values():
        df["quote_volume"] = 5e8
    recorte = {s: v.iloc[:dia_idx + 1] for s, v in velas.items()}
    info = {"symbols": []}
    md = DI.preparar(reg, recorte, None, [], exchange_info=info, btc_largo=recorte["BTCUSDT"])
    md.filtros = {s: Filtros(s, 0.0001, 0.0001, 0.0001, 5.0) for s in recorte}
    dia = recorte["BTCUSDT"].index[-1]
    aperturas = {s: float(v["open"].iloc[dia_idx + 1]) for s, v in velas.items()}
    return P.DatosDia(dia=dia, md=md, apertura_hoy=lambda s: aperturas.get(s)), velas


def _buscar_dia_con_compra(reg):
    for k in range(250, 650, 3):
        dd, _ = _datos_dia(reg, k)
        md = dd.md
        dia_dec = dd.dia + pd.Timedelta(days=1)
        for s in md.grandes.columns:
            if dia_dec in md.grandes.index and md.grandes.at[dia_dec, s]:
                sen = P._senales(dd, "M1", s, {"n": 20})
                if sen is not None and bool(sen.at[dd.dia, "entrada"]):
                    return k
    pytest.skip("los datos sintéticos no dieron una señal de M1")


def test_ronda_repetible_y_boletos_claros(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    dd, _ = _datos_dia(r, k)
    a = P.ronda_cartera(r, "A", dd, [], [])
    b = P.ronda_cartera(r, "A", dd, [], [])
    assert a["boletos"] == b["boletos"]                  # repetible: mismos boletos, mismo identificador
    compras = [x for x in a["boletos"] if x["accion"] == "COMPRAR"]
    assert compras, a["mensajes"]
    est = json.loads((tmp_path / "datos" / "papel" / "cartera_A.json").read_text(encoding="utf-8"))
    assert len(est["posiciones"]) == len(compras)        # no se duplicó nada
    x = compras[0]
    assert x["stop"] < x["precio_entrada"] and x["cantidad"] > 0
    assert str(x["cantidad"]) in x["texto"] and str(x["stop"]) in x["texto"]
    assert x["riesgo_pct"] <= 1.0 + 1e-9                 # Cartera A: 1 % por operación


def test_ronda_avanza_y_conserva_cuentas(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    for j in range(k, k + 40):
        dd, _ = _datos_dia(r, j)
        P.ronda_cartera(r, "A", dd, [], [])
    est = P.cargar_estado(r, "A", "")
    cerradas = sum(c["ganancia_usdt"] for c in est["cerradas"])
    abierto = sum(p["costo_total"] for p in est["posiciones"])
    assert est["efectivo"] + abierto == pytest.approx(est["capital_inicial"] + cerradas, abs=1e-6)
    for p in est["posiciones"]:                          # los stops solo suben
        assert p["gestion"]["stop"] >= p["stop_inicial"] - 1e-12


def test_modo_seguro_sin_entradas(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    dd, _ = _datos_dia(r, k)
    a = P.ronda_cartera(r, "A", dd, [], [], forzar_seguro=True)
    assert not [x for x in a["boletos"] if x["accion"] == "COMPRAR"]
    assert any("datos no son confiables" in m for m in a["mensajes"])


def test_veto_global_bloquea(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    dd, _ = _datos_dia(r, k)
    veto = [{"simbolo": "GLOBAL", "razon": "hackeo grande", "vence": "2099-01-01T00:00:00+00:00"}]
    a = P.ronda_cartera(r, "B", dd, veto, [])
    assert not [x for x in a["boletos"] if x["accion"] == "COMPRAR"]


def test_esquemas_de_archivos(reg, tmp_path):
    assert AR.validar_vetos({"vetos": [{"simbolo": "SOLUSDT", "razon": "x", "vence": "2026-11-12T18:00:00-06:00"}]}) == []
    assert AR.validar_vetos({"vetos": [{"simbolo": "SOLUSDT", "razon": "x", "vence": "mañana"}]})
    assert AR.validar_vetos({"vetos": [{"simbolo": "SOLUSDT", "razon": "x", "vence": "2026-11-12", "comprar": True}]})
    assert AR.validar_exclusiones({"exclusiones": [{"simbolo": "sol", "razon": "MONITOREO"}]})
    assert AR.validar_eventos({"eventos": [{"nombre": "Fed", "fecha_hora": "2026-12-10T13:00:00-06:00", "importancia": "ALTA"}]}) == []
    assert AR.validar_estela({"fecha": "2026-11-09", "simbolos": {"BTCUSDT": {"top_posiciones": 1.9, "masa_cuentas": 2.4}}}) == []
    r = _reg_papel(reg, tmp_path)
    carpeta = tmp_path / "datos"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "vetos.json").write_text("{no es json", encoding="utf-8")
    d, err = AR.leer(r, "vetos.json")
    assert d is None and err


def test_archivo_de_bot_mal_escrito_pone_modo_seguro(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    k = _buscar_dia_con_compra(r)
    dd, _ = _datos_dia(r, k)
    carpeta = tmp_path / "datos"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "vetos.json").write_text(json.dumps({"vetos": [{"simbolo": "?", "razon": ""}]}), encoding="utf-8")
    (tmp_path / "salida").mkdir(exist_ok=True)
    dd.md.velas["BTCUSDT"] = dd.md.velas["BTCUSDT"]
    out = P.ronda(r, dd)
    assert out["modo_seguro"]
    assert not [b for c in out["carteras"].values() for b in c["boletos"] if b["accion"] == "COMPRAR"]
    cal = AR.calificacion_bots(r)
    assert cal["CENTINELA"]["rechazos"] == 1
    assert "👍" in P.resumen_corto(out) and len(P.resumen_corto(out).splitlines()) <= 10


def test_veto_estela_h2():
    from sobreviviente import estela as ES
    idx = pd.date_range("2025-01-01", periods=120, freq="D", tz="UTC")
    s = pd.Series(np.linspace(0.50, 0.55, 120), index=idx)
    assert ES.veto_h2(s, idx[-1]) is True                  # la más alta de sus 90 días → veto
    s2 = s.copy()
    s2.iloc[-1] = 0.40
    assert ES.veto_h2(s2, idx[-1]) is False
    assert ES.veto_h2(s.iloc[:30], idx[29]) is None        # sin 90 días previos: no se veta
    assert ES.veto_h2(pd.Series(dtype=float), idx[-1]) is None


def test_veto_estela_en_ronda(reg, tmp_path):
    r = _reg_papel(reg, tmp_path)
    r.datos["estrategias"]["M3"]["veto_activo"] = True
    k = _buscar_dia_con_compra(r)
    dd, _ = _datos_dia(r, k)
    idx = pd.date_range(dd.dia - pd.Timedelta(days=119), dd.dia, freq="D")
    dd.serie_masa = lambda s: pd.Series(np.linspace(0.5, 0.6, 120), index=idx)
    a = P.ronda_cartera(r, "A", dd, [], [])
    assert not [x for x in a["boletos"] if x["accion"] == "COMPRAR"]
    assert any("ESTELA" in m for m in a["mensajes"])
