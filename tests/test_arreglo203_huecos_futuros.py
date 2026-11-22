"""Arreglo 203: avisar los huecos de datos de Futuros (SOLO AVISOS: nunca bloquean nada).

Antes `datos_publicos.cargar` solo medía el atraso de la última vela, y la descarga histórica se saltaba en silencio los
meses que daban 404. Ahora:
* `cargar` cuenta por moneda las velas de 4 h esperadas contra las recibidas (de la primera a la última), lo mismo para
  las velas de marca, y los cobros de funding esperados según el intervalo de cada moneda (el más común de su serie);
  si falta algo, agrega un aviso con qué falta, cuántas piezas y entre qué fechas. No cambia `entradas_ok`.
* La descarga histórica anota los meses que no llegaron (`cliente.meses_sin_archivo`).
* validar-futuros agrega la sección «Huecos de datos» con los conteos por moneda, y los avisos.
No se usa `datos.max_huecos_pct` para frenar nada (eso lo decide Ángelo).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from apoyo_futuros import MS, ClienteFalso, Respuesta
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import config
from sobreviviente.futuros import datos_publicos as DP
from sobreviviente.futuros import validar as VF

AHORA = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
H4 = MS["4h"]


@pytest.fixture
def reg(tmp_path):
    return RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})


class ConHuecos(ClienteFalso):
    """El ClienteFalso, pero sin las piezas de `quitar`: {(ruta, símbolo): {tiempos en ms}}."""

    def __init__(self, reg, quitar, **kw):
        super().__init__(reg, fin=AHORA, **kw)
        self.quitar = quitar

    def _get(self, url, params=None, intentos=3):
        r = super()._get(url, params, intentos)
        params = params or {}
        fuera = self.quitar.get((url.rsplit("/fapi", 1)[-1], params.get("symbol")))
        if fuera and isinstance(r._cuerpo, list):
            def tiempo(x):
                return int(x["fundingTime"]) if isinstance(x, dict) else int(x[0])
            r = Respuesta(200, [x for x in r._cuerpo if tiempo(x) not in fuera])
        return r


def _fin_ms():
    return int(AHORA.timestamp() * 1000) // H4 * H4


def _txt(ms):
    return pd.Timestamp(ms, unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M")


def test_sin_huecos_no_hay_avisos_nuevos(reg):
    d = DP.cargar(ClienteFalso(reg, fin=AHORA), config.leer(reg), AHORA)
    assert d.avisos == [] and d.entradas_ok
    assert all(x["velas"]["faltan"] == 0 and x["marca"]["faltan"] == 0 and x["funding"]["faltan"] == 0
               for x in d.huecos.values())


def test_diez_velas_de_4h_de_en_medio_de_sol_dan_un_aviso(reg):
    t0 = _fin_ms() - 60 * 86_400_000
    fuera = {t0 + k * H4 for k in range(10)}
    d = DP.cargar(ConHuecos(reg, {("/v1/klines", "SOLUSDT"): fuera}), config.leer(reg), AHORA)
    (aviso,) = d.avisos                                            # antes: avisos vacío
    assert aviso.startswith("⚠️ Huecos de datos de SOLUSDT: faltan 10 velas de 4 h")
    assert f"entre {_txt(t0)} y {_txt(t0 + 9 * H4)} UTC" in aviso and "solo aviso" in aviso
    assert d.entradas_ok                                           # solo aviso: no bloquea
    assert d.huecos["SOLUSDT"]["velas"]["faltan"] == 10
    assert d.huecos["SOLUSDT"]["velas"]["esperadas"] == d.huecos["SOLUSDT"]["velas"]["recibidas"] + 10


def test_hueco_de_marca(reg):
    t0 = _fin_ms() - 3 * 86_400_000
    fuera = {t0, t0 + H4, t0 + 2 * H4}
    d = DP.cargar(ConHuecos(reg, {("/v1/markPriceKlines", "XRPUSDT"): fuera}), config.leer(reg), AHORA)
    (aviso,) = d.avisos
    assert aviso.startswith("⚠️ Huecos de datos de XRPUSDT: faltan 3 velas de marca de 4 h")
    assert f"entre {_txt(t0)} y {_txt(t0 + 2 * H4)} UTC" in aviso
    assert d.entradas_ok and d.huecos["XRPUSDT"]["marca"]["faltan"] == 3


def test_cobro_de_funding_faltante(reg):
    t = (_fin_ms() - 4 * 86_400_000) // (8 * MS["1h"]) * (8 * MS["1h"])
    d = DP.cargar(ConHuecos(reg, {("/v1/fundingRate", "BNBUSDT"): {t}}), config.leer(reg), AHORA)
    (aviso,) = d.avisos
    assert aviso.startswith("⚠️ Huecos de datos de BNBUSDT: falta 1 cobro de funding (cada 8 h)")
    assert f"entre {_txt(t)} y {_txt(t)} UTC" in aviso
    assert d.entradas_ok and d.huecos["BNBUSDT"]["funding"]["faltan"] == 1


def test_huecos_funding_con_el_intervalo_de_la_moneda():
    idx = pd.date_range("2026-11-01", periods=20, freq="4h", tz="UTC")
    s = pd.Series(0.0001, index=idx.delete([5, 6, 12]))
    h = DP.huecos_funding(s)
    assert h["intervalo_h"] == 4 and h["faltan"] == 3 and h["recibidos"] == 17 and h["esperados"] == 20
    assert h["desde"] == idx[5] and h["hasta"] == idx[12]
    assert DP.huecos_funding(pd.Series(dtype=float))["faltan"] == 0


# ---------------------------------------------------------------------------- descarga histórica
class Historico(ClienteFalso):
    """data.binance.vision falso: contesta los zips mensuales salvo los meses de `faltan` (404 → None)."""

    def __init__(self, reg, faltan):
        super().__init__(reg, fin=datetime(2024, 5, 1, tzinfo=timezone.utc))
        self.faltan = faltan

    def zip_historico(self, ruta):
        self.urls.append(f"{self.url_hist}/{ruta}")
        partes = ruta.split("/")
        s, mes = partes[5], ruta.rsplit("-", 2)[-2] + "-" + ruta.rsplit("-", 1)[-1][:2]
        if (s, mes) in self.faltan:
            return None
        ini = pd.Timestamp(mes + "-01", tz="UTC")
        a, b = int(ini.timestamp() * 1000), int((ini + pd.offsets.MonthBegin(1)).timestamp() * 1000)
        if "fundingRate" in ruta:
            filas = [[t, 8, 0.0001] for t in range(a, b, 8 * MS["1h"])]
            return pd.DataFrame(filas)
        iv = "1h" if "markPriceKlines" in ruta else partes[6]
        return pd.DataFrame([f for f in self._velas(s, iv, a, 10**6) if f[0] < b])


def test_la_descarga_historica_anota_los_meses_que_no_llegaron(reg):
    cli = Historico(reg, {("SOLUSDT", "2024-02")})
    meses = ["2024-01", "2024-02", "2024-03"]
    v = cli.velas_futuros_historicas("SOLUSDT", "4h", meses)
    m = cli.precio_marca_historico("SOLUSDT", meses)
    f = cli.funding_historico("SOLUSDT", meses)
    assert not v.empty and not m.empty and not f.empty            # los otros meses sí se usan, como antes
    assert cli.meses_sin_archivo == [("SOLUSDT", "velas 4h", "2024-02"), ("SOLUSDT", "marca 1h", "2024-02"),
                                     ("SOLUSDT", "funding", "2024-02")]


def test_validar_avisa_el_mes_que_falto_y_el_informe_trae_huecos_de_datos(reg, tmp_path):
    reg = reg.copia_con({"backtest.fin": "2024-04-30"})
    cfg = config.leer(reg)
    cli = Historico(reg, {("SOLUSDT", "2024-02")})
    m = VF.cargar_mercado(reg, cli, cfg, inicio="2024-01-01", fin="2024-04-30")
    sol = m.huecos["SOLUSDT"]
    assert sol["meses"] == {"velas 4h": ["2024-02"], "marca 1h": ["2024-02"], "funding": ["2024-02"]}
    assert sol["velas"]["faltan"] == 29 * 6 and sol["marca"]["faltan"] == 29 * 24 and sol["funding"]["faltan"] == 29 * 3
    assert any(a.startswith("⚠️ SOLUSDT: no llegaron los archivos mensuales de velas 4h de 2024-02") for a in m.avisos)
    assert any(a.startswith("⚠️ Huecos de datos de SOLUSDT: faltan 174 velas de 4 h") for a in m.avisos)
    assert not any("XRPUSDT" in a for a in m.avisos)              # las demás monedas llegaron completas
    res = VF.ResultadoF1(avisos=list(m.avisos))
    texto = VF.informe(res, m, tmp_path / "V.md")
    sec = texto[texto.index("## Huecos de datos"):]
    assert "| Moneda | Velas 4 h | Marca 1 h | Funding | Meses sin archivo |" in sec
    assert "| SOLUSDT | faltan 174 de" in sec and "2024-02" in sec
    assert "| XRPUSDT | faltan 0 de" in sec


def test_validar_sin_huecos_dice_ninguno(reg, tmp_path):
    from test_arreglo151_validar_futuros import _mercado
    m = _mercado(reg)                                             # armado a mano: sin conteos guardados
    texto = VF.informe(VF.ResultadoF1(), m, tmp_path / "V.md")
    assert "## Huecos de datos" in texto and "- Sin conteos (el mercado no se bajó de Binance)." in texto
