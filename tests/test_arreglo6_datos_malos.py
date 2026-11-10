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


def test_una_moneda_rara_falla_no_frena_las_compras(reg, tmp_path):
    """(a) Falla una moneda que no es BTC ni está abierta: NO hay modo seguro, se excluye hoy y C compra BTC."""
    r = _reg_m0(reg, tmp_path)
    dd, _ = _preparar(r, tmp_path, fallan={"AUSDT"})
    assert dd.datos_ok
    aviso = [a for a in dd.avisos if "AUSDT" in a]
    assert aviso and "se excluyen hoy" in aviso[0] and "No afecta a BTC ni a lo abierto" in aviso[0]
    assert not any("MODO SEGURO" in a for a in dd.avisos)
    assert "AUSDT" not in dd.md.velas and dd.excluidas_hoy == ["AUSDT"]   # nunca se opera con velas viejas
    out = P.ronda(r, dd)
    assert not out["modo_seguro"]
    assert any(b["simbolo"] == "BTCUSDT" and b["cartera"] == "C" for b in _compras(out))
    assert any("AUSDT" in a for a in out["avisos"])


def test_falla_btc_modo_seguro_sin_compras(reg, tmp_path):
    """(b) Falla BTC (queda la copia de ayer): MODO SEGURO, sin compras."""
    r = _reg_m0(reg, tmp_path)
    velas = _velas_completas()
    k = _dia_marea_alta(r)
    ayer = ClienteFalso(tmp_path, velas, k - 1)
    P.preparar_datos(r, ayer, [], ahora=(ayer.hoy + pd.Timedelta(minutes=10)).to_pydatetime())   # llena la caché
    cli = ClienteFalso(tmp_path, velas, k, fallan={"BTCUSDT"})
    dd = P.preparar_datos(r, cli, [], ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime())
    assert not dd.datos_ok
    assert any("BTCUSDT" in a and "MODO SEGURO" in a for a in dd.avisos)
    assert any("Se usó una copia" in a and "BTCUSDT" in a for a in dd.avisos)
    assert not _compras(P.ronda(r, dd))


def _reg_m0_m1(reg, carpeta):
    r = _reg_m0(reg, carpeta, capital=1000.0)
    r.datos["estrategias"]["M1"]["estado"] = "PAPEL"
    r.datos["estrategias"]["M1"]["parametros"] = {"n": 20}
    return r


def _ahora(cli):
    return (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()


def _dia_con_compra_m1(reg, base):
    """Busca un día en que M1 compra una moneda que no es BTC (comprobado con una ronda sana)."""
    from test_papel import _datos_dia
    velas = _velas_completas()
    r0 = _reg_m0_m1(reg, base / "busqueda")
    for k in range(260, 650, 3):
        dd, _ = _datos_dia(r0, k)
        dia_dec = dd.dia + pd.Timedelta(days=1)
        if dd.md.marea.get(dd.dia) != "ALCISTA" or dia_dec not in dd.md.grandes.index:
            continue
        for s in ("AUSDT", "BUSDT", "CUSDT"):
            if not bool(dd.md.grandes.at[dia_dec, s]):
                continue
            sen = P._senales(dd, "M1", s, {"n": 20})
            if sen is None or not bool(sen.at[dd.dia, "entrada"]):
                continue
            carpeta = base / f"control_{k}_{s}"
            r2 = _reg_m0_m1(reg, carpeta)
            cli = ClienteFalso(carpeta, velas, k)
            if any(b["simbolo"] == s for b in _compras(P.ronda(r2, P.preparar_datos(r2, cli, [], ahora=_ahora(cli))))):
                return k, s, velas
    pytest.skip("los datos sintéticos no dieron una compra de M1")


def test_moneda_abierta_falla_modo_seguro_y_se_revisa_lo_demas(reg, tmp_path):
    """(c) Falla una moneda con posición abierta: MODO SEGURO sin compras; lo que sí se bajó (BTC) se revisa,
    y la posición de la moneda que falló sigue abierta tal cual (no se mueve con velas viejas)."""
    k, x, velas = _dia_con_compra_m1(reg, tmp_path)
    r = _reg_m0_m1(reg, tmp_path / "c")
    cli = ClienteFalso(tmp_path / "c", velas, k)
    P.ronda(r, P.preparar_datos(r, cli, [], ahora=_ahora(cli)))                 # día k: entra M1 en x
    con_x = [n for n in P.CARTERAS if any(p["simbolo"] == x for p in P.cargar_estado(r, n, "")["posiciones"])]
    assert con_x
    cli2 = ClienteFalso(tmp_path / "c", velas, k + 1, fallan={x})
    dd2 = P.preparar_datos(r, cli2, [], ahora=_ahora(cli2))
    assert not dd2.datos_ok and any(x in a and "MODO SEGURO" in a for a in dd2.avisos)
    out = P.ronda(r, dd2)
    assert not _compras(out)
    dia_k = f"{velas['BTCUSDT'].index[k]:%Y-%m-%d}"
    for n in P.CARTERAS:
        est = P.cargar_estado(r, n, "")
        assert est["ultimo_dia"] == out["dia"]                                  # la ronda sí corrió para todas
        for p in est["posiciones"]:
            if p["simbolo"] == x:
                assert p["ultimo_dia"] == dia_k and p["gestion"]["stop"] == p["stop_inicial"]   # sin vela nueva: intacta
            else:
                assert p["ultimo_dia"] == out["dia"]                            # lo que sí se bajó, se revisó


def test_con_m1_la_moneda_que_falla_no_genera_senal(reg, tmp_path):
    """(d) M1 encendido: la moneda que falla no genera señal ese día (en una ronda sana sí la compraba)."""
    k, x, velas = _dia_con_compra_m1(reg, tmp_path)
    r = _reg_m0_m1(reg, tmp_path / "d")
    cli = ClienteFalso(tmp_path / "d", velas, k, fallan={x})
    dd = P.preparar_datos(r, cli, [], ahora=_ahora(cli))
    assert dd.datos_ok and x not in dd.md.velas
    out = P.ronda(r, dd)
    assert not any(b["simbolo"] == x for b in _compras(out))
    assert not out["modo_seguro"]


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
