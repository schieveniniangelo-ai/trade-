"""Arreglo 208: toda llamada de futuros/datos_publicos.py pasa por un envoltorio que revisa `ruta_permitida`.

Antes RUTAS_PERMITIDAS solo se revisaba en las pruebas: nada impedía que el código llamara otra ruta. Ahora `_pedir`
arma la URL completa, la revisa contra la lista blanca y, si no está, lanza RutaNoPermitida (con un error claro) ANTES
de llamar a la red. ESTELA (estela_vivo.py) no cambia. Sin red.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sobreviviente import datos as D
from sobreviviente.futuros import datos_publicos as DP

AHORA = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
FUENTE = Path(DP.__file__)
ORDEN = "/fapi/v1/" + "order"            # partido: el código de prueba tampoco nombra la ruta de órdenes entera


class Espia:
    """Cliente que anota cada llamada y no tiene red."""

    url_futuros = "https://fapi.binance.com"
    url_hist = "https://data.binance.vision"
    futuros_disponible = True

    def __init__(self):
        self.llamadas = []

    def _anotar(self, nombre, respuesta):
        def f(*a, **k):
            self.llamadas.append(nombre)
            return respuesta
        return f

    def __getattr__(self, nombre):
        raise AttributeError(nombre)

    @property
    def futuros(self):
        return self._anotar("futuros", [])

    @property
    def velas_api(self):
        return self._anotar("velas_api", None)

    @property
    def funding_api(self):
        return self._anotar("funding_api", None)

    @property
    def exchange_info(self):
        return self._anotar("exchange_info", {"symbols": []})


@pytest.mark.parametrize("ruta", [ORDEN, "/fapi/v2/account", "/fapi/v1/" + "leverage", "/fapi/v1/listenKey",
                                  "https://api.binance.com/api/v3/klines",
                                  "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/x.zip",
                                  "/data/spot/monthly/klines/BTCUSDT/1d/"])
def test_una_ruta_fuera_de_la_lista_truena_antes_de_llamar_a_la_red(ruta):
    esp = Espia()
    with pytest.raises(DP.RutaNoPermitida, match="no está en RUTAS_PERMITIDAS de F1.*no se llamó a la red"):
        DP._pedir(esp, ruta, esp.futuros, ruta)
    assert esp.llamadas == []


def test_un_host_cambiado_tambien_truena():
    esp = Espia()
    esp.url_futuros = "https://otro.ejemplo.com"
    with pytest.raises(DP.RutaNoPermitida, match="otro.ejemplo.com/fapi/v1/klines"):
        DP.velas_4h(esp, "SOLUSDT", AHORA)
    assert esp.llamadas == []


def test_no_es_un_error_de_datos():
    assert not issubclass(DP.RutaNoPermitida, D.ErrorDatos)          # cargar no la convierte en «falló un dato»


@pytest.mark.parametrize("ruta,llamar,nombre", [
    ("/fapi/v1/klines", lambda c: DP.velas_4h(c, "SOLUSDT", AHORA), "velas_api"),
    ("/fapi/v1/klines", lambda c: DP.velas_1d(c, "BTCUSDT", AHORA, 30), "velas_api"),
    ("/fapi/v1/markPriceKlines", lambda c: DP.marca_4h(c, "SOLUSDT", AHORA), "futuros"),
    ("/fapi/v1/fundingRate", lambda c: DP.funding(c, "SOLUSDT", AHORA), "funding_api"),
    ("/fapi/v1/premiumIndex", lambda c: DP.marca_y_funding(c, "SOLUSDT"), "futuros"),
    ("/fapi/v1/fundingInfo", lambda c: DP.info_funding(c), "futuros"),
])
def test_cada_funcion_pasa_por_el_envoltorio(monkeypatch, ruta, llamar, nombre):
    esp = Espia()
    monkeypatch.setattr(DP, "RUTAS_PERMITIDAS", tuple(r for r in DP.RUTAS_PERMITIDAS if r != ruta))
    with pytest.raises(DP.RutaNoPermitida, match=ruta):
        llamar(esp)
    assert esp.llamadas == []
    monkeypatch.undo()
    try:
        llamar(esp)
    except (TypeError, KeyError, AttributeError):
        pass                                                         # el espía no trae datos: basta con que llamó
    assert esp.llamadas == [nombre]


def test_exchange_info_de_cargar_pasa_por_el_envoltorio(monkeypatch):
    esp = Espia()
    monkeypatch.setattr(DP, "RUTAS_PERMITIDAS", tuple(r for r in DP.RUTAS_PERMITIDAS if r != "/fapi/v1/exchangeInfo"))
    with pytest.raises(DP.RutaNoPermitida, match="exchangeInfo"):
        DP.cargar(esp, {"monedas": ["SOLUSDT"], "regimen_btc": "BTCUSDT"}, AHORA)
    assert esp.llamadas == []


def test_marca_historica_pasa_por_el_envoltorio(monkeypatch):
    llamadas = []
    monkeypatch.setattr(D, "actualizar_precio_marca", lambda *a: llamadas.append(a))
    monkeypatch.setattr(DP, "PREFIJO_HISTORICOS", "/data/futures/cm/")
    esp = Espia()
    with pytest.raises(DP.RutaNoPermitida, match="data.binance.vision/data/futures/um/monthly/markPriceKlines/SOLUSDT"):
        DP.marca_4h_historica(esp, "SOLUSDT", "2026-01", "2026-01")
    assert llamadas == []


def test_en_el_codigo_no_queda_ninguna_llamada_directa():
    """Ninguna llamada `cliente.algo(...)` ni `D.actualizar_*(...)`/`D.ClienteBinance(...)` fuera de `_pedir`."""
    arbol = ast.parse(FUENTE.read_text(encoding="utf-8"))
    directas = []
    for fn in [n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name != "_pedir"]:
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
                if n.func.value.id == "cliente" or (n.func.value.id == "D" and (
                        n.func.attr.startswith("actualizar_") or n.func.attr == "ClienteBinance")):
                    directas.append(f"{fn.name}: {n.func.value.id}.{n.func.attr}")
    assert directas == []


def test_estela_no_cambia():
    texto = (FUENTE.parent.parent / "estela_vivo.py").read_text(encoding="utf-8")
    assert "_pedir" not in texto and "RutaNoPermitida" not in texto
