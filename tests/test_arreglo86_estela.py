"""Arreglo 86 (B10): pruebas de estela.py con series falsas y un cliente que no sale a la red."""
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sobreviviente import estela as ES

from test_v2 import diarias


# ---------------- indicadores ----------------

def test_parte_larga():
    s = ES.parte_larga(pd.Series([1.0, 3.0, 0.0]))
    assert s.tolist() == [0.5, 0.75, 0.0]


def _serie(n=300, semilla=3):
    rng = np.random.default_rng(semilla)
    return pd.Series(rng.normal(0.5, 0.05, n), index=pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC"))


def test_z_movil_y_percentil_no_miran_el_futuro():
    s = _serie()
    z, p = ES.z_movil(s, 90), ES.percentil_previo(s, 90)
    otra = s.copy()
    otra.iloc[200:] = 99.0                                 # cambiar el futuro no cambia el pasado
    assert z.iloc[:200].equals(ES.z_movil(otra, 90).iloc[:200])
    assert p.iloc[:200].equals(ES.percentil_previo(otra, 90).iloc[:200])


def test_z_movil_y_percentil_sin_historia_dan_nan():
    s = _serie()
    assert ES.z_movil(s, 90).iloc[:45].isna().all()
    p = ES.percentil_previo(s, 90)
    assert p.iloc[:90].isna().all() and p.iloc[90:].between(0, 100).all()


def test_percentil_de_un_maximo_es_100():
    s = _serie()
    s.iloc[150] = 10.0
    assert ES.percentil_previo(s, 90).iloc[150] == 100.0


# ---------------- tabla, eventos y efecto ----------------

def _serie_cruda(n=400):
    rng = np.random.default_rng(1)
    dias = pd.date_range("2022-03-01", periods=n, freq="D")
    return pd.DataFrame({"dia": dias.strftime("%Y-%m-%d"), "top_posiciones": rng.uniform(0.6, 1.8, n),
                         "masa_cuentas": rng.uniform(0.6, 1.8, n)})


def test_tabla_simbolo_rendimiento_desde_la_apertura_siguiente():
    velas = diarias(900)
    t = ES.tabla_simbolo(_serie_cruda(), velas, 90)
    assert {"top_largo", "masa_largo", "brecha", "z_top", "z_masa", "pct_masa", "ret_3", "ret_7"} <= set(t.columns)
    d = t.index[100]
    o = velas["open"]
    assert t.at[d, "ret_3"] == pytest.approx(o[d + pd.Timedelta(days=4)] / o[d + pd.Timedelta(days=1)] - 1)
    assert (t["brecha"] - (t["top_largo"] - t["masa_largo"])).abs().max() < 1e-12


def test_eventos_h1_y_h2():
    t = ES.tabla_simbolo(_serie_cruda(), diarias(900), 90)
    h2 = ES.eventos(t, "H2", pct=90.0)
    assert h2.equals(t["pct_masa"] >= 90.0)
    h1 = ES.eventos(t, "H1", 3, 1.0)
    assert h1.dtype == bool and h1.sum() > 0
    assert (t.loc[h1, "z_masa"] - t["z_masa"].shift(3)[h1] <= 0).all()


def _panel(n=400, evento_cada=10, extra=0.0):
    dias = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    rng = np.random.default_rng(5)
    ev = np.arange(n) % evento_cada == 0
    ret = rng.normal(0, 0.01, n) + np.where(ev, extra, 0.0)
    return pd.DataFrame({"dia": dias, "ret_3": ret, "ev": ev})


def test_efecto_mide_la_diferencia_contra_todos_los_dias():
    p = _panel(extra=0.05)
    e = ES.efecto(p, "ev", 3)
    assert e["eventos"] == 40
    assert e["efecto_pct"] == pytest.approx(e["media_evento_pct"] - e["media_todos_pct"])
    assert e["efecto_pct"] > 3


def test_efecto_sin_eventos():
    p = _panel()
    p["ev"] = False
    e = ES.efecto(p, "ev", 3)
    assert e["eventos"] == 0 and np.isnan(e["efecto_pct"])


def test_ic_bloques_reproducible_y_ordenado():
    p = _panel(extra=0.05)
    a = ES.ic_bloques(p, "ev", 3, 200, 9)
    assert a == ES.ic_bloques(p, "ev", 3, 200, 9)
    assert a[0] <= a[1] and a[0] > 0                       # un efecto fuerte no toca el cero


def test_ic_bloques_con_pocos_eventos_es_nan():
    p = _panel(evento_cada=200)                            # solo 2 eventos
    lo, hi = ES.ic_bloques(p, "ev", 3, 50, 1)
    assert np.isnan(lo) and np.isnan(hi)


def test_estudio_con_paneles_falsos(reg):
    velas = diarias(900)
    t = ES.tabla_simbolo(_serie_cruda(), velas, 90)
    grandes = pd.DataFrame(True, index=t.index + pd.Timedelta(days=1), columns=["XUSDT"])
    r = ES.estudio({"XUSDT": t}, grandes, reg, t.index[0], t.index[-1], n_boot=20)
    pruebas = {(p["prueba"], p["h"]) for p in r["pruebas"]}
    assert ("H2", 3) in pruebas and ("H1_D3_z1.0", 7) in pruebas
    assert r["n_pruebas"] == (4 + 1) * 2 and r["monedas"] == ["XUSDT"]
    assert r["hay_efecto"] == any(p["pasa"] for p in r["pruebas"])
    sin = ES.estudio({"XUSDT": t}, grandes.iloc[:0], reg, t.index[0], t.index[-1], n_boot=20)
    assert sin == {"pruebas": [], "panel_filas": 0}


# ---------------- veto H2 en vivo ----------------

def test_veto_h2():
    s = _serie()
    assert ES.veto_h2(pd.Series(dtype=float), s.index[200]) is None
    assert ES.veto_h2(s, s.index[10]) is None                         # sin 90 días previos
    assert ES.veto_h2(s, pd.Timestamp("2030-01-01", tz="UTC")) is None
    s.iloc[200] = 10.0
    assert ES.veto_h2(s, s.index[200]) is True
    s.iloc[201] = -10.0
    assert ES.veto_h2(s, s.index[201]) is False


# ---------------- descarga con un cliente falso ----------------

def _zip_csv(df: pd.DataFrame) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", df.to_csv(index=False))
    return b.getvalue()


def _fotos(fecha: str, cols=ES.COLUMNAS) -> pd.DataFrame:
    t = pd.date_range(fecha, periods=3, freq="8h").tolist() + [pd.Timestamp(fecha) + pd.Timedelta(days=1)]
    df = pd.DataFrame({c: [float(i + 1) for i in range(len(t))] for c in cols})
    df["create_time"] = [x.strftime("%Y-%m-%d %H:%M:%S") for x in t]
    df["symbol"] = "XUSDT"
    return df


class ClienteFalso:
    """Responde el índice de S3 (en dos páginas) y los zip diarios; cuenta las descargas."""
    url_hist = "https://falso"

    def __init__(self, cache: Path, fechas, malas=()):
        self.cache = cache
        self.fechas = list(fechas)
        self.malas = set(malas)
        self.bajados = []

    def _get(self, url, params=None):
        if url == ES.S3:
            mitad = len(self.fechas) // 2
            pagina = self.fechas[mitad:] if params.get("marker") else self.fechas[:mitad]
            llaves = "".join(f"<Contents><Key>{ES.RUTA}/XUSDT/XUSDT-metrics-{f}.zip</Key></Contents>" for f in pagina)
            llaves += f"<Contents><Key>{ES.RUTA}/XUSDT/raro.zip</Key></Contents>"
            trunc = "false" if params.get("marker") else "true"
            xml = (f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                   f"<IsTruncated>{trunc}</IsTruncated>{llaves}</ListBucketResult>")
            return SimpleNamespace(status_code=200, content=xml.encode())
        fecha = url.rsplit("-metrics-", 1)[-1][:10]
        self.bajados.append(fecha)
        if fecha in self.malas:
            return SimpleNamespace(status_code=404, content=b"")
        return SimpleNamespace(status_code=200, content=_zip_csv(_fotos(fecha)))


def test_listar_dias_recorre_las_paginas_e_ignora_nombres_raros(tmp_path):
    cli = ClienteFalso(tmp_path, ["2024-01-03", "2024-01-01", "2024-01-02", "2024-01-04"])
    assert ES.listar_dias(cli, "XUSDT") == ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def test_dia_toma_la_ultima_foto_antes_de_medianoche(tmp_path):
    cli = ClienteFalso(tmp_path, [])
    d = ES._dia(cli, "XUSDT", "2024-01-01")
    assert d["filas"] == 3 and d["hora_ultima"] == "2024-01-01 16:00:00"
    assert d["top_posiciones"] == 3.0                      # la foto de las 00:00 del día siguiente no cuenta


def test_dia_con_columnas_distintas_o_sin_archivo(tmp_path):
    cli = ClienteFalso(tmp_path, [], malas={"2024-01-02"})
    assert ES._dia(cli, "XUSDT", "2024-01-02") is None
    cli._get = lambda url, params=None: SimpleNamespace(status_code=200, content=_zip_csv(_fotos("2024-01-01", ["create_time"])))
    assert "columnas distintas" in ES._dia(cli, "XUSDT", "2024-01-01")["error"]


def test_descargar_simbolo_guarda_en_cache_y_no_repite(tmp_path):
    fechas = [f"2024-01-0{i}" for i in range(1, 7)]
    cli = ClienteFalso(tmp_path, fechas, malas={"2024-01-05"})
    df = ES.descargar_simbolo(cli, "XUSDT", "2024-01-02", "2024-01-06", hilos=2)
    assert df["dia"].tolist() == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-06"]
    assert (tmp_path / "estela" / "XUSDT.csv.gz").exists()
    cli.bajados.clear()
    otra = ES.descargar_simbolo(cli, "XUSDT", "2024-01-01", "2024-01-06", hilos=2)
    assert sorted(cli.bajados) == ["2024-01-01", "2024-01-05"]   # lo ya guardado no se vuelve a bajar
    assert otra["dia"].astype(str).tolist() == ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-06"]
