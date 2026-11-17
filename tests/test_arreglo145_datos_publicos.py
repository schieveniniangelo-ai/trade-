"""Arreglo 145: datos públicos de 4 h para F1 (solo GET y solo rutas de la lista blanca)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from apoyo_futuros import ClienteFalso
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import config
from sobreviviente.futuros import datos_publicos as DP


@pytest.fixture
def reg(tmp_path):
    return RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})


def test_cada_url_pedida_esta_en_la_lista_blanca(reg):
    cli = ClienteFalso(reg)
    cfg = config.leer(reg)
    d = DP.cargar(cli, cfg)
    assert d.disponible and d.entradas_ok, d.avisos
    DP.marca_y_funding(cli, "SOLUSDT")
    DP.info_funding(cli)
    assert cli.urls
    malas = [u for u in cli.urls if not DP.ruta_permitida(u)]
    assert not malas, malas
    assert set(d.velas) == set(cfg["monedas"]) and all(len(v) > 500 for v in d.velas.values())
    assert d.btc1d is not None and len(d.btc1d) >= 200
    assert all(len(m) > 0 for m in d.marca.values())
    assert all(v == pytest.approx(3e8) for v in d.volumen.values())
    assert set(d.exchange) == set(cfg["monedas"])


def test_lista_blanca():
    assert DP.ruta_permitida("https://fapi.binance.com/fapi/v1/klines")
    assert DP.ruta_permitida("https://data.binance.vision/data/futures/um/monthly/klines/SOLUSDT/4h/x.zip")
    for mala in ("https://fapi.binance.com/fapi/v1/" + "order", "https://fapi.binance.com/fapi/v1/" + "leverage",
                 "https://fapi.binance.com/fapi/v2/account", "https://api.binance.com/api/v3/klines",
                 "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/x.zip", "https://ejemplo.com/"):
        assert not DP.ruta_permitida(mala), mala


def test_datos_de_mas_de_48_horas_no_dan_entradas(reg):
    cli = ClienteFalso(reg, fin=datetime.now(timezone.utc) - timedelta(days=3))
    d = DP.cargar(cli, config.leer(reg))
    assert d.disponible and not d.entradas_ok
    assert any("más de 48 h" in a for a in d.avisos)


@pytest.mark.parametrize("estado", [451, 403])
def test_futuros_bloqueado_dice_no_disponible_y_no_hay_entradas(reg, estado):
    cli = ClienteFalso(reg, estado=estado)
    d = DP.cargar(cli, config.leer(reg))
    assert not d.disponible and not d.entradas_ok
    assert any("Futuros no disponible" in a for a in d.avisos)


def test_otro_error_tambien_apaga_las_entradas(reg):
    cli = ClienteFalso(reg, estado=500)
    d = DP.cargar(cli, config.leer(reg))
    assert d.disponible and not d.entradas_ok
    assert any("Falló un dato de Futuros" in a for a in d.avisos)


def test_premium_index_funding_info_y_funding_8h(reg):
    cli = ClienteFalso(reg)
    mf = DP.marca_y_funding(cli, "SOLUSDT")
    assert mf["marca"] > 0 and mf["funding_pct"] == pytest.approx(0.01)
    info = DP.info_funding(cli)
    assert info["DOGEUSDT"]["intervalo_h"] == 4 and info["DOGEUSDT"]["tope_pct"] == pytest.approx(2.0)
    idx = pd.to_datetime(["2026-11-01 00:00", "2026-11-01 04:00", "2026-11-01 08:00", "2026-11-01 12:00"], utc=True)
    s = pd.Series([0.0001, 0.0002, 0.0002, 0.0002], index=idx)          # cobros cada 4 h → ×2 para llevarlos a 8 h
    assert DP.funding_8h_promedio(s) == pytest.approx(0.04)
    assert DP.funding_8h_promedio(pd.Series(dtype=float)) is None
    assert DP.volumen_mediano_30d(pd.DataFrame()) == 0.0
    assert DP.horas_de_atraso(pd.DataFrame(), datetime.now(timezone.utc)) == float("inf")


def test_marca_historica_usa_la_cache_y_remuestrea(reg, monkeypatch):
    idx = pd.date_range("2026-01-01", periods=8, freq="1h", tz="UTC")
    uno = pd.DataFrame({"open": range(8), "high": range(1, 9), "low": range(8), "close": range(8)}, index=idx,
                       dtype=float)
    monkeypatch.setattr(DP.D, "actualizar_precio_marca", lambda cli, s, a, b: uno)
    m4 = DP.marca_4h_historica(ClienteFalso(reg), "SOLUSDT", "2026-01", "2026-01")
    assert list(m4["high"]) == [4.0, 8.0] and list(m4["low"]) == [0.0, 4.0]


def test_sin_velas_de_marca_regresa_tabla_vacia(reg):
    cli = ClienteFalso(reg, fin=datetime.now(timezone.utc) - timedelta(days=30))
    m = DP.marca_4h(cli, "SOLUSDT", datetime.now(timezone.utc))
    assert m.empty and list(m.columns) == ["open", "high", "low", "close"]
