"""Arreglo 44 (T11-3, R22): se MIDE cuánto se mueve el precio entre la apertura que usa el papel y la hora real de
la ronda. No cambia cómo llena el papel, ni el tamaño, ni el límite, ni el stop, ni el vencimiento."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P
from sobreviviente import reportes

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas
from test_arreglo9_vencimiento import FILTROS
from test_papel import _datos_dia

CAMPOS = ("precio_al_correr", "hora_real_utc", "dif_apertura_pct")


def _compra(reg, carpeta, precio_ahora="sin"):
    """Ronda de la Cartera C en un día de marea alta (compra BTC). `precio_ahora`: función, o "sin" para no ponerla."""
    carpeta.mkdir(parents=True, exist_ok=True)
    r = _reg_m0(reg, carpeta, capital=1000.0)
    k = _dia_marea_alta(r)
    dd = _datos_dia(r, k)[0]
    if precio_ahora != "sin":
        dd.precio_ahora = precio_ahora(dd) if precio_ahora is not None else None
    res = P.ronda_cartera(r, "C", dd, [], [])
    return r, k, dd, next(b for b in res["boletos"] if b["accion"] == "COMPRAR")


def _venta_a_mercado(reg, carpeta, monkeypatch, precio_ahora="sin"):
    """Día siguiente a la compra, con la estrategia pidiendo salir: CERRAR a mercado en la apertura de hoy."""
    r, k, _, _ = _compra(reg, carpeta)
    original = P._senales

    def pide_salir(dd, clave, simbolo, params):
        sen = original(dd, clave, simbolo, params)
        if sen is not None:
            sen = sen.copy()
            sen["salir"], sen["entrada"] = True, False
        return sen

    monkeypatch.setattr(P, "_senales", pide_salir)
    dd = _datos_dia(r, k + 1)[0]
    if precio_ahora != "sin":
        dd.precio_ahora = precio_ahora(dd)
    res = P.ronda_cartera(r, "C", dd, [], [])
    cierres = [b for b in res["boletos"] if b["accion"] == "CERRAR"]
    assert cierres and cierres[0]["tipo_orden"] == "MARKET", res["boletos"]
    return dd, cierres[0]


def _mas_04(dd):
    return lambda s: dd.apertura_hoy(s) * 1.004


def test_medir_apertura_100_contra_100_4():
    dd = P.DatosDia(dia=pd.Timestamp("2026-11-10", tz="UTC"), md=None, apertura_hoy=lambda s: 100.0,
                    precio_ahora=lambda s: 100.4)
    m = P.medir_apertura(dd, "BTCUSDT", 100.0)
    assert m["precio_al_correr"] == 100.4 and m["dif_apertura_pct"] == 0.4
    assert datetime.fromisoformat(m["hora_real_utc"]).tzinfo is not None
    dd.precio_ahora = lambda s: 99.5
    assert P.medir_apertura(dd, "BTCUSDT", 100.0)["dif_apertura_pct"] == -0.5


def test_compra_trae_los_tres_campos(reg, tmp_path):
    _, _, dd, b = _compra(reg, tmp_path, _mas_04)
    apertura = dd.apertura_hoy("BTCUSDT")
    assert b["precio_al_correr"] == pytest.approx(apertura * 1.004) and b["dif_apertura_pct"] == 0.4
    assert b["hora_real_utc"].endswith("+00:00")
    assert not any(c in b["texto"] for c in CAMPOS) and "al correr" not in b["texto"]      # el EJECUTOR no los ve


def test_cerrar_a_mercado_trae_los_tres_campos(reg, tmp_path, monkeypatch):
    dd, b = _venta_a_mercado(reg, tmp_path, monkeypatch, _mas_04)
    assert b["precio_al_correr"] == pytest.approx(dd.apertura_hoy("BTCUSDT") * 1.004) and b["dif_apertura_pct"] == 0.4
    assert b["hora_real_utc"] and not any(c in b["texto"] for c in CAMPOS)


def _truena(dd):
    def f(s):
        raise RuntimeError("ticker caído")
    return f


@pytest.mark.parametrize("ticker", [_truena, lambda dd: (lambda s: 0), lambda dd: (lambda s: "x"),
                                    lambda dd: (lambda s: None), lambda dd: (lambda s: float("nan")), None])
def test_ticker_que_falla_deja_null_y_el_boleto_igual(reg, tmp_path, ticker):
    _, _, _, sin = _compra(reg, tmp_path / "sin")
    _, _, _, con = _compra(reg, tmp_path / "con", ticker)
    assert all(con[c] is None for c in CAMPOS)
    assert con == sin                                                    # idéntico, campo por campo


def test_cerrar_sin_ticker_deja_null(reg, tmp_path, monkeypatch):
    _, b = _venta_a_mercado(reg, tmp_path, monkeypatch)
    assert all(b[c] is None for c in CAMPOS)


def test_la_medicion_no_cambia_nada_del_boleto(reg, tmp_path):
    _, _, _, sin = _compra(reg, tmp_path / "sin")
    _, _, _, con = _compra(reg, tmp_path / "con", _mas_04)
    assert con["dif_apertura_pct"] == 0.4 and sin["dif_apertura_pct"] is None
    for campo in ("boleto_id", "id_stop", "cantidad", "cantidad_stop", "precio_entrada", "stop", "precio_limite_stop",
                  "vence", "riesgo_pct", "riesgo_usdt", "valor_usdt", "llenado_papel", "texto"):
        assert con[campo] == sin[campo], campo
    assert {k: v for k, v in con.items() if k not in CAMPOS} == {k: v for k, v in sin.items() if k not in CAMPOS}


def test_verificar_da_lo_mismo_con_y_sin_los_campos(reg, tmp_path, monkeypatch, capsys):
    r, k, dd, con = _compra(reg, tmp_path, _mas_04)
    info = {"symbols": [{"symbol": s, "status": "TRADING", "filters": FILTROS} for s in dd.md.velas]}
    monkeypatch.setattr(D.ClienteBinance, "exchange_info", lambda self, mercado="SPOT", forzar=False: info)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=15)).to_pydatetime()
    arch = tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json"
    arch.parent.mkdir(exist_ok=True)
    salidas = []
    for boleto in (con, {k_: v for k_, v in con.items() if k_ not in CAMPOS}):
        arch.write_text(json.dumps([boleto]), encoding="utf-8")
        codigo = CR.verificar_boletos(r, f"{dd.dia:%Y-%m-%d}", ahora=ahora)
        salidas.append((codigo, capsys.readouterr().out))
    assert salidas[0] == salidas[1] and salidas[0][0] == 0


# ---------------- Boleta semanal ----------------

AHORA = datetime(2026, 11, 15, 2, 30, tzinfo=timezone.utc)


def _reg_reporte(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "salida").mkdir()
    return r


def _boletos(tmp_path, dia, difs):
    (tmp_path / "salida" / f"boletos_{dia}.json").write_text(
        json.dumps([{"boleto_id": f"b{i}", "accion": "COMPRAR", "dif_apertura_pct": d} for i, d in enumerate(difs)]),
        encoding="utf-8")


def test_boleta_semanal_con_tres_boletos(reg, tmp_path):
    r = _reg_reporte(reg, tmp_path)
    assert r.get("reportes.dif_apertura_aviso_pct") == 0.3
    _boletos(tmp_path, "2026-11-10", [0.1, -0.5])
    _boletos(tmp_path, "2026-11-12", [0.4, None])                         # el que no trae dato no cuenta
    _boletos(tmp_path, "2026-11-01", [9.0])                               # de hace más de 7 días: fuera
    texto = reportes.semanal(r, AHORA)
    linea = "Apertura vs precio al correr (últimos 7 días): promedio 0.0 %, peor 0.5 %, 2 de 3 boletos con más de 0.3 %."
    assert linea in texto.splitlines()
    lineas = texto.splitlines()
    assert lineas.index(linea) < next(i for i, x in enumerate(lineas) if x.startswith("Recuerda"))


def test_boleta_semanal_sin_boletos(reg, tmp_path):
    r = _reg_reporte(reg, tmp_path)
    assert "Apertura vs precio al correr: sin datos todavía." in reportes.semanal(r, AHORA).splitlines()
    _boletos(tmp_path, "2026-11-12", [None, "x", True])                   # boletos viejos o raros: tampoco hay dato
    assert "Apertura vs precio al correr: sin datos todavía." in reportes.semanal(r, AHORA).splitlines()


def test_boletos_danados_no_tumban_la_boleta(reg, tmp_path):
    r = _reg_reporte(reg, tmp_path)
    _boletos(tmp_path, "2026-11-10", [0.2])
    (tmp_path / "salida" / "boletos_2026-11-11.json").write_text("{dañado", encoding="utf-8")
    (tmp_path / "salida" / "boletos_2026-11-12.json").write_text('{"no": "es lista"}', encoding="utf-8")
    texto = reportes.semanal(r, AHORA)
    assert "promedio 0.2 %, peor 0.2 %, 0 de 1 boletos con más de 0.3 %." in texto
    assert "⚠️ boletos_2026-11-11.json está dañado" in texto and "👍" in texto


# ---------------- La ronda repetida no vuelve a preguntar precios ----------------

class _ClienteConTicker(ClienteFalso):
    llamadas = 0

    def spot(self, ruta, params=None):
        if ruta == "/api/v3/ticker/price":
            type(self).llamadas += 1
            return {"symbol": params["symbol"], "price": str(self.apertura[params["symbol"]] * 1.004)}
        return super().spot(ruta, params)


def test_ronda_repetida_no_llama_al_ticker(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    _ClienteConTicker.llamadas = 0
    cli = _ClienteConTicker(tmp_path, _velas_completas(), k)
    ahora = (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0
    boletos = json.loads((tmp_path / "salida" / f"boletos_{cli.hoy - timedelta(days=1):%Y-%m-%d}.json").read_text(encoding="utf-8"))
    compras = [b for b in boletos if b["accion"] == "COMPRAR"]
    assert compras and all(b["dif_apertura_pct"] == 0.4 and b["hora_real_utc"] for b in compras)
    primera = _ClienteConTicker.llamadas
    assert primera == 1                                                   # una sola consulta por moneda (BTC), con caché
    capsys.readouterr()
    assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0
    assert "ya corrió" in capsys.readouterr().out
    assert _ClienteConTicker.llamadas == primera
