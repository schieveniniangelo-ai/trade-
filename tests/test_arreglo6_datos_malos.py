"""Arreglo 6: la ronda no decide con datos malos o a medias.

Se usa un cliente de Binance FALSO: el flujo real de descarga (`datos.actualizar_spot`), caché y ronda, sin internet."""
import json
import os
import time
from pathlib import Path

import pandas as pd
import pytest

from sobreviviente import datos as D
from sobreviviente import papel as P
from sobreviviente import reglamento as RGL

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_v2 import diarias

SIMBOLOS = ["BTCUSDT", "AUSDT", "BUSDT", "CUSDT"]


def _velas_completas():
    out = {s: diarias(700, semilla=i + 20, tendencia=0.0012 + 0.0004 * i) for i, s in enumerate(SIMBOLOS)}
    for v in out.values():
        v["quote_volume"] = 5e8
    return out


class ClienteFalso:
    """Imita lo que la ronda usa de `datos.ClienteBinance`."""

    def __init__(self, carpeta: Path, velas: dict, k: int, fallan=(), copia_h: float | None = None):
        self.cache = carpeta / "cache"
        self.velas = {s: v.iloc[:k + 1] for s, v in velas.items()}    # velas CERRADAS hasta el día k
        self.apertura = {s: float(v["open"].iloc[k + 1]) for s, v in velas.items()}
        self.hoy = velas["BTCUSDT"].index[k + 1]
        self.fallan = set(fallan)
        self.copia_h = copia_h
        self.avisos_copias: list[str] = []
        self.edad_copia_max_h = 0.0

    def exchange_info(self, mercado="SPOT", forzar=False):
        if self.copia_h is not None:
            self.avisos_copias.append("se usó una copia de 2000-01-01 00:00 UTC de las reglas de Binance de SPOT (exchangeInfo); no está al día")
            self.edad_copia_max_h = self.copia_h
        filtros = [{"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
                   {"filterType": "LOT_SIZE", "stepSize": "0.0001", "minQty": "0.0001"},
                   {"filterType": "NOTIONAL", "minNotional": "5"}]
        return {"symbols": [{"symbol": s, "status": "TRADING", "quoteAsset": "USDT", "baseAsset": s[:-4], "filters": filtros}
                            for s in SIMBOLOS]}

    def velas_api(self, simbolo, intervalo, inicio_ms, fin_ms=None, mercado="SPOT"):
        if simbolo in self.fallan:
            raise D.ErrorDatos(f"No pude conectarme ({simbolo})")
        v = self.velas[simbolo]
        a = pd.Timestamp(inicio_ms, unit="ms", tz="UTC")
        b = pd.Timestamp(fin_ms, unit="ms", tz="UTC") if fin_ms else v.index[-1] + pd.Timedelta(days=1)
        x = v[(v.index >= a) & (v.index < b)].copy()
        x["close_time"] = x.index + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
        x.index.name = "tiempo"
        return x

    def spot(self, ruta, params=None):
        s = params["symbol"]
        return [[int(self.hoy.timestamp() * 1000), str(self.apertura[s])]]


def _preparar(r, tmp_path, **kw):
    velas = _velas_completas()
    k = _dia_marea_alta(r)
    cli = ClienteFalso(tmp_path, velas, k, **kw)
    ahora = (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()
    return P.preparar_datos(r, cli, [], ahora=ahora), cli


def _compras(out):
    return [b for c in out["carteras"].values() for b in c["boletos"] if b["accion"] == "COMPRAR"]


def test_todo_sano_ronda_normal(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    dd, _ = _preparar(r, tmp_path)
    assert dd.datos_ok and not dd.avisos
    out = P.ronda(r, dd)
    assert not out["modo_seguro"] and _compras(out)                # la Cartera C compra BTC


def test_una_moneda_falla_modo_seguro_sin_compras(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    dd, _ = _preparar(r, tmp_path, fallan={"AUSDT"})
    assert not dd.datos_ok
    assert any("AUSDT" in a and "MODO SEGURO" in a for a in dd.avisos)
    out = P.ronda(r, dd)
    assert not _compras(out)
    assert any("AUSDT" in a for a in out["avisos"])


def test_moneda_con_posicion_abierta_falla_pero_se_revisan_sus_stops(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    dd, cli = _preparar(r, tmp_path)
    P.ronda(r, dd)                                                 # día k: C compra BTC
    assert P.cargar_estado(r, "C", "")["posiciones"]
    # Día siguiente: falla otra moneda; lo abierto (BTC) sí se bajó y se procesa
    velas = _velas_completas()
    k = _dia_marea_alta(r) + 1
    cli2 = ClienteFalso(tmp_path, velas, k, fallan={"BUSDT"})
    dd2 = P.preparar_datos(r, cli2, [], ahora=(cli2.hoy + pd.Timedelta(minutes=10)).to_pydatetime())
    assert not dd2.datos_ok
    c = P.ronda_cartera(r, "C", dd2, [], [])
    assert c["dia"] == f"{dd2.dia:%Y-%m-%d}"
    pos = P.cargar_estado(r, "C", "")["posiciones"]
    assert not pos or pos[0]["ultimo_dia"] == c["dia"]            # la posición se revisó con la vela nueva


def test_btc_con_precio_absurdo_modo_seguro(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    velas = _velas_completas()
    k = _dia_marea_alta(r)
    cli = ClienteFalso(tmp_path, velas, k)
    t = cli.velas["BTCUSDT"].index[-3]
    cli.velas["BTCUSDT"] = cli.velas["BTCUSDT"].copy()
    cli.velas["BTCUSDT"].loc[t, "close"] *= 3                     # salto imposible de +200 % en un día
    dd = P.preparar_datos(r, cli, [], ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime())
    assert not dd.datos_ok
    assert any("BTCUSDT no son confiables" in a for a in dd.avisos)


def test_copia_vieja_de_reglas_mas_de_48h_modo_seguro(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    dd, _ = _preparar(r, tmp_path, copia_h=72)
    assert not dd.datos_ok
    assert any("no está al día" in a for a in dd.avisos) and any("48 horas" in a for a in dd.avisos)
    dd2, _ = _preparar(r, tmp_path / "otra", copia_h=10)           # copia de 10 h: aviso, pero sin modo seguro
    assert dd2.datos_ok and any("no está al día" in a for a in dd2.avisos)


def test_cliente_real_avisa_cuando_usa_copia_vieja(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    cli = D.ClienteBinance(r)
    cli.cache.mkdir(parents=True)
    arch = cli.cache / "exchangeinfo_spot.json"
    arch.write_text(json.dumps({"symbols": []}), encoding="utf-8")
    hace = time.time() - 72 * 3600
    os.utime(arch, (hace, hace))

    def sin_red(*a, **k):
        raise D.ErrorDatos("sin conexión")
    cli.spot = sin_red
    assert cli.exchange_info("SPOT") == {"symbols": []}
    assert cli.avisos_copias and "no está al día" in cli.avisos_copias[0]
    assert cli.edad_copia_max_h == pytest.approx(72, abs=0.1)
