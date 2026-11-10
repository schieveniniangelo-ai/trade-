"""Arreglo 61: pruebas de la capa que habla con Binance (datos.ClienteBinance), sin red: la sesión es falsa.

Es lo que usa cada ronda para bajar velas: reintentos, límite de peticiones, cambio a la ruta de respaldo cuando la
principal está bloqueada y lectura de velas solo CERRADAS."""
import time

import pandas as pd
import pytest
import requests

from sobreviviente import datos as D


class _Resp:
    def __init__(self, codigo=200, cuerpo=None, cabeceras=None):
        self.status_code, self._cuerpo, self.headers = codigo, cuerpo, cabeceras or {}
        self.text = str(cuerpo)

    def json(self):
        return self._cuerpo


class _Sesion:
    """Contesta lo que diga `guion(url, params)`: una respuesta o una excepción."""

    def __init__(self, guion):
        self.guion, self.visitas = guion, []

    def get(self, url, params=None, timeout=None):
        self.visitas.append((url, params))
        r = self.guion(url, params)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def cli(reg, tmp_path, monkeypatch):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    monkeypatch.setattr(time, "sleep", lambda s: None)            # sin esperas reales en las pruebas
    return D.ClienteBinance(r)


def test_no_manda_llaves_ni_firma(cli):
    cli.sesion = _Sesion(lambda url, p: _Resp(200, {}))
    cli.spot("/api/v3/ping")
    assert "X-MBX-APIKEY" not in D.ClienteBinance(cli.reg).sesion.headers
    url, params = cli.sesion.visitas[0]
    assert url.endswith("/api/v3/ping") and not params


def test_reintenta_si_falla_la_conexion_y_luego_contesta(cli):
    respuestas = iter([requests.ConnectionError("corte"), requests.Timeout("lento"), _Resp(200, {"ok": 1})])
    cli.sesion = _Sesion(lambda url, p: next(respuestas))
    assert cli.spot("/api/v3/ping") == {"ok": 1}
    assert len(cli.sesion.visitas) == 3


def test_sin_conexion_en_las_dos_rutas_es_error_de_datos(cli):
    cli.sesion = _Sesion(lambda url, p: requests.ConnectionError("sin internet"))
    with pytest.raises(D.ErrorDatos, match="No pude obtener datos de Spot"):
        cli.spot("/api/v3/ping")
    usadas = {u.split("/api/")[0] for u, _ in cli.sesion.visitas}
    assert usadas == set(cli.urls_spot)                           # probó la principal y el respaldo


def test_ruta_principal_bloqueada_usa_el_respaldo_y_lo_recuerda(cli):
    principal, respaldo = cli.urls_spot
    cli.sesion = _Sesion(lambda url, p: _Resp(451, "bloqueado") if url.startswith(principal) else _Resp(200, {"ok": 1}))
    assert cli.spot("/api/v3/ping") == {"ok": 1} and cli._spot_bloqueado is True
    cli.sesion.visitas.clear()
    assert cli.spot("/api/v3/time") == {"ok": 1}
    assert [u for u, _ in cli.sesion.visitas] == [respaldo + "/api/v3/time"]      # ya no pierde tiempo en la bloqueada


def test_limite_de_peticiones_espera_y_reintenta(cli, monkeypatch):
    esperas = []
    monkeypatch.setattr(time, "sleep", esperas.append)
    respuestas = iter([_Resp(429, "despacio", {"Retry-After": "7"}), _Resp(200, {"ok": 1})])
    cli.sesion = _Sesion(lambda url, p: next(respuestas))
    assert cli.spot("/api/v3/ping") == {"ok": 1} and esperas == [7]


def test_error_del_servidor_en_las_dos_rutas(cli):
    cli.sesion = _Sesion(lambda url, p: _Resp(500, "error interno"))
    with pytest.raises(D.ErrorDatos, match="500"):
        cli.spot("/api/v3/ping")


def test_futuros_bloqueado_se_recuerda_y_no_se_vuelve_a_intentar(cli):
    cli.sesion = _Sesion(lambda url, p: _Resp(451, "bloqueado"))
    with pytest.raises(D.ErrorDatos, match="bloqueo por región"):
        cli.futuros("/fapi/v1/ping")
    assert cli.futuros_disponible is False
    visitas = len(cli.sesion.visitas)
    with pytest.raises(D.ErrorDatos, match="no está disponible"):
        cli.futuros("/fapi/v1/ping")
    assert len(cli.sesion.visitas) == visitas                      # ni siquiera salió a internet


def _kline(t_ms, precio, cerrada=True):
    return [t_ms, str(precio), str(precio + 2), str(precio - 2), str(precio + 1), "10", t_ms + D.MS_POR_INTERVALO["1d"] - 1,
            "1000", 5, "5", "500", "0"]


def test_velas_api_solo_regresa_velas_cerradas_y_dentro_del_rango(cli):
    dia = D.MS_POR_INTERVALO["1d"]
    hoy = (int(time.time() * 1000) // dia) * dia                  # 00:00 UTC de hoy
    filas = [_kline(hoy - 3 * dia, 100), _kline(hoy - 2 * dia, 101), _kline(hoy - dia, 102), _kline(hoy, 103)]
    pedidos = []

    def guion(url, p):
        pedidos.append(p)
        return _Resp(200, [f for f in filas if f[0] >= p["startTime"]])

    cli.sesion = _Sesion(guion)
    df = cli.velas_api("BTCUSDT", "1d", hoy - 3 * dia)
    assert list(df["close"]) == [101.0, 102.0, 103.0]             # la vela de hoy (todavía abierta) NO viene
    assert df.index[-1] == pd.Timestamp(hoy - dia, unit="ms", tz="UTC") and str(df.index.tz) == "UTC"
    assert pedidos[0]["symbol"] == "BTCUSDT" and pedidos[0]["interval"] == "1d"
    solo_dos = cli.velas_api("BTCUSDT", "1d", hoy - 3 * dia, fin_ms=hoy - dia)
    assert list(solo_dos["close"]) == [101.0, 102.0]              # fin_ms corta el rango


def test_velas_api_sin_datos_regresa_tabla_vacia(cli):
    cli.sesion = _Sesion(lambda url, p: _Resp(200, []))
    assert cli.velas_api("NUEVAUSDT", "1d", 0, fin_ms=10 * D.MS_POR_INTERVALO["1d"]).empty


def test_a_dataframe_quita_duplicados_y_ordena():
    dia = D.MS_POR_INTERVALO["1d"]
    df = D.a_dataframe([_kline(2 * dia, 102), _kline(dia, 100), _kline(dia, 101)])
    assert list(df["open"]) == [101.0, 102.0] and df.index.is_monotonic_increasing


def test_guardar_y_leer_velas_en_la_cache(cli, tmp_path):
    dia = D.MS_POR_INTERVALO["1d"]
    df = D.a_dataframe([_kline(dia, 100), _kline(2 * dia, 101)])
    ruta = D.ruta_cache(cli, "spot", "1d", "BTCUSDT")
    assert D.leer(ruta).empty                                      # todavía no existe: tabla vacía, sin error
    D.guardar(df, ruta)
    de_vuelta = D.leer(ruta)
    assert list(de_vuelta["close"]) == [101.0, 102.0] and de_vuelta.index.equals(df.index)
