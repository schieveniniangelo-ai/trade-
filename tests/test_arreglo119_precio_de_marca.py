"""Arreglo 119 (F3): velas de 1 h del precio de MARCA de Futuros en la caché (solo datos, sin red en la prueba).

Binance liquida con el precio de marca, y con workingType=MARK_PRICE también dispara los stops con él. Se bajan
de los archivos mensuales oficiales (data/futures/um/monthly/markPriceKlines/<SÍMBOLO>/1h/) y se guardan en
cache/futuros/marca_1h/, igual que las velas de Futuros: si ya están guardadas no se vuelven a bajar.
"""
import io
import zipfile
from types import SimpleNamespace

import pandas as pd

from sobreviviente import datos as D
from sobreviviente import descarga as DG

RUTA = "data/futures/um/monthly/markPriceKlines"


def _zip(filas, encabezado=True):
    cols = "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"
    lineas = ([cols] if encabezado else []) + [",".join(str(x) for x in f) for f in filas]
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", "\n".join(lineas) + "\n")
    return b.getvalue()


def _filas(mes_inicio, n, base):
    t0 = int(pd.Timestamp(mes_inicio, tz="UTC").value // 10**6)
    return [[t0 + i * 3_600_000, base + i, base + i + 0.5, base + i - 0.5, base + i + 0.2, 0,
             t0 + (i + 1) * 3_600_000 - 1, 0, 0, 0, 0, 0] for i in range(n)]


def _cliente(tmp_path, archivos):
    c = object.__new__(D.ClienteBinance)
    c.url_hist = "https://falso"
    c.cache = tmp_path / "cache"
    c.pedidos = []

    def _get(url, params=None):
        c.pedidos.append(url)
        ruta = url.removeprefix("https://falso/")
        if ruta in archivos:
            return SimpleNamespace(status_code=200, content=archivos[ruta])
        return SimpleNamespace(status_code=404, content=b"")
    c._get = _get
    return c


def test_baja_los_meses_y_los_guarda_en_cache(tmp_path):
    archivos = {f"{RUTA}/BTCUSDT/1h/BTCUSDT-1h-2025-01.zip": _zip(_filas("2025-01-01", 3, 100.0)),
                f"{RUTA}/BTCUSDT/1h/BTCUSDT-1h-2025-02.zip": _zip(_filas("2025-02-01", 2, 200.0), encabezado=False)}
    c = _cliente(tmp_path, archivos)
    df = D.actualizar_precio_marca(c, "BTCUSDT", "2025-01-01", "2025-03-31")
    assert len(df) == 5 and list(df["close"]) == [100.2, 101.2, 102.2, 200.2, 201.2]
    assert df.index[0] == pd.Timestamp("2025-01-01", tz="UTC") and str(df.index.tz) == "UTC"
    assert len(c.pedidos) == 3                                       # marzo no existe (404) y no truena
    archivo = tmp_path / "cache" / "futuros" / "marca_1h" / "BTCUSDT.csv.gz"
    assert archivo.exists() and D.ruta_marca(c, "BTCUSDT") == archivo
    otra = D.actualizar_precio_marca(c, "BTCUSDT", "2025-01-01", "2025-03-31")
    assert len(c.pedidos) == 3 and otra.equals(D.leer(archivo))     # ya en caché: no vuelve a bajar


def test_sin_archivos_regresa_vacio_y_no_guarda(tmp_path):
    c = _cliente(tmp_path, {})
    assert D.actualizar_precio_marca(c, "XUSDT", "2025-01-01", "2025-01-31").empty
    assert not (tmp_path / "cache" / "futuros" / "marca_1h" / "XUSDT.csv.gz").exists()


def test_la_descarga_masiva_tambien_baja_el_precio_de_marca(tmp_path, monkeypatch):
    llamadas = []
    monkeypatch.setattr(D, "actualizar_futuros", lambda cli, s, i, ini, fin: None)
    monkeypatch.setattr(D, "actualizar_precio_marca", lambda cli, s, ini, fin: llamadas.append((s, ini, fin)))
    monkeypatch.setattr(D, "actualizar_spot", lambda *a, **k: None)
    monkeypatch.setattr(DG, "descargar_largo", lambda *a, **k: None)
    idx = pd.date_range("2023-01-01", periods=80, freq="D", tz="UTC")
    diario = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
                           "quote_volume": 1e12}, index=idx)
    monkeypatch.setattr(D, "leer", lambda arch: diario)
    monkeypatch.setattr(DG.U, "simbolos_candidatos", lambda reg, info, incluir_deslistados: ["AAAUSDT"])
    monkeypatch.setattr(DG.U, "pertenencia", lambda reg, vol: pd.DataFrame({"AAAUSDT": True}, index=idx))
    cli = SimpleNamespace(cache=tmp_path, exchange_info=lambda m, forzar=False: {"symbols": []})
    reg = SimpleNamespace(get=lambda k: {"datos.inicio_historicos": "2023-01-01", "backtest.fin": "2023-03-20",
                                         "backtest.inicio": "2023-02-01",
                                         "universo.futuros_volumen_min_usdt": 1.0}[k])
    DG.descargar_todo(reg, cli, avisar=lambda *_: None)
    assert llamadas == [("AAAUSDT", "2023-01-01", "2023-03-20")]
