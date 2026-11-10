"""Arreglo 59: la ronda y la verificación piden las reglas de Binance FRESCAS (no la copia de ayer); si Binance no
contesta, usan la copia guardada y lo dicen."""
import json
import os
import time

import pandas as pd

import test_arreglo34_verificar_completo as T34
from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas


class _ClienteQueAnota(ClienteFalso):
    pedidos = []

    def exchange_info(self, mercado="SPOT", forzar=False):
        type(self).pedidos.append(forzar)
        return super().exchange_info(mercado, forzar)


def test_la_ronda_pide_reglas_frescas(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    _ClienteQueAnota.pedidos = []
    cli = _ClienteQueAnota(tmp_path, _velas_completas(), k)
    P.preparar_datos(r, cli, [], ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime())
    assert _ClienteQueAnota.pedidos == [True]


def _cliente_con_copia_de_ayer(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    cli = D.ClienteBinance(r)
    cli.cache.mkdir(parents=True, exist_ok=True)
    copia = cli.cache / "exchangeinfo_spot.json"
    copia.write_text(json.dumps({"symbols": [{"symbol": "VIEJOUSDT"}]}), encoding="utf-8")
    hace_23h = time.time() - 23 * 3600                       # la copia de la ronda de ayer: todavía "vigente" (< 24 h)
    os.utime(copia, (hace_23h, hace_23h))
    return r, cli


def test_cliente_real_con_copia_de_23h_baja_reglas_nuevas_si_se_le_pide(reg, tmp_path, monkeypatch):
    _, cli = _cliente_con_copia_de_ayer(reg, tmp_path)
    monkeypatch.setattr(cli, "spot", lambda ruta, params=None: {"symbols": [{"symbol": "NUEVOUSDT"}]})
    assert cli.exchange_info("SPOT")["symbols"][0]["symbol"] == "VIEJOUSDT"                 # sin forzar: la copia
    assert cli.exchange_info("SPOT", forzar=True)["symbols"][0]["symbol"] == "NUEVOUSDT"    # forzando: lo de hoy
    assert cli.avisos_copias == []


def test_si_binance_no_contesta_se_usa_la_copia_y_se_avisa(reg, tmp_path, monkeypatch):
    _, cli = _cliente_con_copia_de_ayer(reg, tmp_path)

    def caido(ruta, params=None):
        raise D.ErrorDatos("No pude obtener datos de Spot: sin conexión")

    monkeypatch.setattr(cli, "spot", caido)
    assert cli.exchange_info("SPOT", forzar=True)["symbols"][0]["symbol"] == "VIEJOUSDT"
    assert len(cli.avisos_copias) == 1 and "reglas de Binance" in cli.avisos_copias[0]
    assert 22 < cli.edad_copia_max_h < 24                    # 23 h: aviso, pero todavía sin MODO SEGURO (eso es a las 48 h)


def test_verificar_pide_reglas_frescas_y_dice_si_uso_la_copia(reg, tmp_path, monkeypatch, capsys):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    boleto = T34._base("COMPRAR")
    boleto["version_reglamento"] = r.version
    (tmp_path / "salida").mkdir()
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text(json.dumps([boleto]), encoding="utf-8")
    info = {"symbols": [{"symbol": "ETHUSDT", "status": "TRADING", "filters": T34.FILTROS}]}
    pedidos = []

    def exchange_info(self, mercado="SPOT", forzar=False):
        pedidos.append(forzar)
        self.avisos_copias.append("se usó una copia de 2026-11-09 00:10 UTC de las reglas de Binance de SPOT (exchangeInfo); no está al día")
        return info

    monkeypatch.setattr(D.ClienteBinance, "exchange_info", exchange_info)
    assert CR.verificar_boletos(r, "2026-11-09", ahora=T34.AHORA) == 0
    salida = capsys.readouterr().out
    assert pedidos == [True]
    assert "⚠️ Se usó una copia de 2026-11-09 00:10 UTC de las reglas de Binance" in salida and "✅" in salida
