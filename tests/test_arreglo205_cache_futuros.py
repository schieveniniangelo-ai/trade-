"""Arreglo 205: la caché de Futuros se completa mes por mes y cada zip se verifica con su .CHECKSUM.

Antes `actualizar_futuros` y `actualizar_precio_marca` solo bajaban datos si la caché estaba vacía: con meses viejos en
caché y un `fin` más nuevo, los meses nuevos nunca llegaban. Ahora:
* bajan solo los meses que faltan hasta `fin` (los que ya están no se vuelven a bajar) y los juntan con la caché;
* cada zip de data.binance.vision se compara (SHA256) con su .CHECKSUM: si no cuadra o no llega, no se usa y se avisa;
* el cliente dice qué meses se usaron (`meses_usados`) y validar-futuros lo pone en el informe.
Sin red: data.binance.vision falso con zips armados en memoria.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from types import SimpleNamespace

import pandas as pd
import pytest

from sobreviviente import datos as D

H = 3_600_000
VELAS = "data/futures/um/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-{m}.zip"
MARCA = "data/futures/um/monthly/markPriceKlines/BTCUSDT/1h/BTCUSDT-1h-{m}.zip"
FUND = "data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-{m}.zip"


def _zip(lineas: list[str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", "\n".join(lineas) + "\n")
    return b.getvalue()


def _velas_mes(mes: str, paso_h: int) -> bytes:
    ini = pd.Timestamp(mes + "-01", tz="UTC")
    fin = ini + pd.offsets.MonthBegin(1)
    a, b = int(ini.value // 10**6), int(fin.value // 10**6)
    return _zip([f"{t},1,2,0.5,1.5,10,{t + paso_h * H - 1},15,3,0,0,0" for t in range(a, b, paso_h * H)])


def _funding_mes(mes: str) -> bytes:
    ini = pd.Timestamp(mes + "-01", tz="UTC")
    a, b = int(ini.value // 10**6), int((ini + pd.offsets.MonthBegin(1)).value // 10**6)
    return _zip(["calc_time,funding_interval_hours,last_funding_rate"]
                + [f"{t},8,0.0001" for t in range(a, b, 8 * H)])


def _sha(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _servidor(meses: list[str], malos: set[str] = frozenset(), sin_checksum: set[str] = frozenset()) -> dict[str, bytes]:
    """{ruta: bytes} con los zips de velas 4 h, marca 1 h y funding de `meses` y sus .CHECKSUM."""
    archivos = {}
    for m in meses:
        for plantilla, contenido in ((VELAS, _velas_mes(m, 4)), (MARCA, _velas_mes(m, 1)), (FUND, _funding_mes(m))):
            ruta = plantilla.format(m=m)
            archivos[ruta] = contenido
            if m in sin_checksum:
                continue
            sha = "0" * 64 if m in malos else _sha(contenido)
            archivos[ruta + ".CHECKSUM"] = f"{sha}  {ruta.rsplit('/', 1)[-1]}\n".encode()
    return archivos


def _cliente(tmp_path, archivos: dict[str, bytes]):
    c = object.__new__(D.ClienteBinance)
    c.url_hist = "https://falso"
    c.cache = tmp_path / "cache"
    c.pedidos = []

    def _get(url, params=None):
        c.pedidos.append(url.removeprefix("https://falso/"))
        ruta = url.removeprefix("https://falso/")
        if ruta in archivos:
            return SimpleNamespace(status_code=200, content=archivos[ruta], text=archivos[ruta].decode("latin-1"))
        return SimpleNamespace(status_code=404, content=b"", text="")
    c._get = _get
    return c


def _zips_pedidos(c, tipo: str) -> list[str]:
    return sorted(p.rsplit("-", 2)[-2] + "-" + p.rsplit("-", 1)[-1][:2]
                  for p in c.pedidos if p.endswith(".zip") and f"/{tipo}/" in p)


# ---------------------------------------------------------------------------- (a) completar los meses que faltan
def test_cache_con_meses_viejos_y_fin_nuevo_baja_solo_los_que_faltan(tmp_path):
    archivos = _servidor(["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"])
    c = _cliente(tmp_path, archivos)
    v, f = D.actualizar_futuros(c, "BTCUSDT", "4h", "2024-01-01", "2024-03-31")
    assert sorted({str(x)[:7] for x in v.index}) == ["2024-01", "2024-02", "2024-03"]
    c.pedidos.clear()
    v, f = D.actualizar_futuros(c, "BTCUSDT", "4h", "2024-01-01", "2024-05-31")
    assert _zips_pedidos(c, "klines") == ["2024-04", "2024-05"]           # solo los nuevos
    assert _zips_pedidos(c, "fundingRate") == ["2024-04", "2024-05"]
    assert sorted({x.strftime("%Y-%m") for x in v.index}) == ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]
    assert len(v) == (31 + 29 + 31 + 30 + 31) * 6 and v.index.is_monotonic_increasing and v.index.is_unique
    assert len(f) == (31 + 29 + 31 + 30 + 31) * 3
    assert c.meses_usados[("BTCUSDT", "velas 4h")] == ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]
    assert c.meses_usados[("BTCUSDT", "funding")] == ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]
    c.pedidos.clear()
    v2, _ = D.actualizar_futuros(c, "BTCUSDT", "4h", "2024-01-01", "2024-05-31")
    assert _zips_pedidos(c, "klines") == [] and len(v2) == len(v)           # todo en caché: nada que bajar


def test_marca_tambien_completa_los_meses_que_faltan(tmp_path):
    c = _cliente(tmp_path, _servidor(["2024-01", "2024-02", "2024-03"]))
    m = D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-01-31")
    assert len(m) == 31 * 24
    c.pedidos.clear()
    m = D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-03-31")
    assert _zips_pedidos(c, "markPriceKlines") == ["2024-02", "2024-03"]
    assert len(m) == (31 + 29 + 31) * 24
    assert c.meses_usados[("BTCUSDT", "marca 1h")] == ["2024-01", "2024-02", "2024-03"]


def test_cache_vieja_sin_manifiesto_deduce_los_meses_del_indice(tmp_path):
    c = _cliente(tmp_path, _servidor(["2024-01", "2024-02", "2024-03"]))
    D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-02-29")
    manifiesto = D.ruta_manifiesto(D.ruta_marca(c, "BTCUSDT"))
    assert manifiesto.exists()
    manifiesto.unlink()                                                     # como las cachés de antes del 205
    c.pedidos.clear()
    D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-03-31")
    assert _zips_pedidos(c, "markPriceKlines") == ["2024-03"]


def test_un_mes_viejo_que_dio_404_no_se_vuelve_a_pedir(tmp_path):
    c = _cliente(tmp_path, _servidor(["2024-02", "2024-03"]))              # 2024-01: antes del listado (404)
    D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-03-31")
    c.pedidos.clear()
    D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-03-31")
    assert c.pedidos == []


# ---------------------------------------------------------------------------- (b) checksum
def test_zip_con_checksum_malo_se_rechaza_con_aviso(tmp_path, caplog):
    c = _cliente(tmp_path, _servidor(["2024-01", "2024-02"], malos={"2024-02"}))
    with caplog.at_level("WARNING", logger="sobreviviente.datos"):
        m = D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-02-29")
    assert len(m) == 31 * 24 and m.index.max() < pd.Timestamp("2024-02-01", tz="UTC")   # febrero no entró
    assert c.meses_usados[("BTCUSDT", "marca 1h")] == ["2024-01"]
    assert any("BTCUSDT-1h-2024-02.zip" in a and "SHA256 no cuadra" in a and "no se usó" in a for a in c.avisos_checksum)
    assert "SHA256 no cuadra" in caplog.text
    assert ("BTCUSDT", "marca 1h", "2024-02") not in getattr(c, "meses_sin_archivo", [])  # no es un 404
    c.pedidos.clear()
    D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-02-29")
    assert _zips_pedidos(c, "markPriceKlines") == ["2024-02"]               # el rechazado se vuelve a intentar


def test_zip_sin_checksum_tampoco_se_usa(tmp_path):
    c = _cliente(tmp_path, _servidor(["2024-01"], sin_checksum={"2024-01"}))
    assert D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-01-31").empty
    assert any("no llegó su .CHECKSUM" in a for a in c.avisos_checksum)
    assert not D.ruta_marca(c, "BTCUSDT").exists()


def test_checksum_bueno_acepta_mayusculas_y_solo_el_hash(tmp_path):
    archivos = _servidor(["2024-01"])
    ruta = MARCA.format(m="2024-01")
    archivos[ruta + ".CHECKSUM"] = _sha(archivos[ruta]).upper().encode()
    c = _cliente(tmp_path, archivos)
    assert len(D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-01-31")) == 31 * 24


def test_funding_con_checksum_malo_no_entra(tmp_path):
    archivos = _servidor(["2024-01", "2024-02"])
    ruta = FUND.format(m="2024-02")
    archivos[ruta + ".CHECKSUM"] = b"0" * 64
    c = _cliente(tmp_path, archivos)
    v, f = D.actualizar_futuros(c, "BTCUSDT", "4h", "2024-01-01", "2024-02-29")
    assert len(v) == (31 + 29) * 6 and len(f) == 31 * 3
    assert c.meses_usados[("BTCUSDT", "funding")] == ["2024-01"]


# ---------------------------------------------------------------------------- informe
def test_el_informe_dice_que_meses_se_usaron(tmp_path):
    from apoyo_futuros import ClienteFalso  # noqa: F401  (asegura el mismo entorno de las pruebas de F1)
    from sobreviviente import reglamento as RGL
    from sobreviviente.futuros import config
    from sobreviviente.futuros import validar as VF
    from test_arreglo203_huecos_futuros import Historico
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos"), "backtest.fin": "2024-04-30"})
    cli = Historico(reg, {("SOLUSDT", "2024-02")})
    m = VF.cargar_mercado(reg, cli, config.leer(reg), inicio="2024-01-01", fin="2024-04-30")
    assert m.huecos["SOLUSDT"]["meses_usados"]["velas 4h"] == ["2024-01", "2024-03", "2024-04"]
    texto = VF.informe(VF.ResultadoF1(avisos=list(m.avisos)), m, tmp_path / "V.md")
    sec = texto[texto.index("## Meses de datos usados"):]
    assert "| Moneda | Velas 4 h | Marca 1 h | Funding |" in sec
    assert "| SOLUSDT | 2024-01 a 2024-04 (3 meses; falta 2024-02) |" in sec
    assert "| XRPUSDT | 2024-01 a 2024-04 (4 meses) |" in sec


def test_validar_avisa_los_zips_rechazados(tmp_path, monkeypatch):
    from sobreviviente import reglamento as RGL
    from sobreviviente.futuros import config
    from sobreviviente.futuros import validar as VF
    from test_arreglo203_huecos_futuros import Historico
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos"), "backtest.fin": "2024-02-29"})
    cli = Historico(reg, set())
    cli.avisos_checksum = ["⚠️ data/x.zip: el SHA256 no cuadra con su .CHECKSUM; no se usó (data.binance.vision)."]
    m = VF.cargar_mercado(reg, cli, config.leer(reg), inicio="2024-01-01", fin="2024-02-29")
    assert cli.avisos_checksum[0] in m.avisos


@pytest.mark.parametrize("texto", ["", "   \n", "no-es-un-hash"])
def test_checksum_ilegible_se_rechaza(tmp_path, texto):
    archivos = _servidor(["2024-01"])
    archivos[MARCA.format(m="2024-01") + ".CHECKSUM"] = texto.encode()
    c = _cliente(tmp_path, archivos)
    assert D.actualizar_precio_marca(c, "BTCUSDT", "2024-01-01", "2024-01-31").empty
    assert c.avisos_checksum
