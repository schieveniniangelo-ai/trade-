"""Arreglo 9: las compras vencen a las 00:00 UTC del día siguiente a la ronda; vencido = no se pone."""
import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

FILTROS = [{"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
           {"filterType": "LOT_SIZE", "stepSize": "0.0001", "minQty": "0.0001"},
           {"filterType": "NOTIONAL", "minNotional": "5"}]


def _ronda_con_compra(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    out = P.ronda(r, dd)
    info = {"symbols": [{"symbol": s, "status": "TRADING", "filters": FILTROS} for s in dd.md.velas]}
    monkeypatch.setattr(D.ClienteBinance, "exchange_info", lambda self, mercado="SPOT", forzar=False: info)
    compras = [b for c in out["carteras"].values() for b in c["boletos"] if b["accion"] == "COMPRAR"]
    assert compras
    return r, dd, compras[0]


def test_vence_a_las_0000_utc_del_dia_siguiente_a_la_ronda(reg, tmp_path, monkeypatch):
    r, dd, b = _ronda_con_compra(reg, tmp_path, monkeypatch)
    # La ronda corre el día dd.dia + 1 (00:10 UTC) → vence a las 00:00 UTC de dd.dia + 2
    assert b["vence"] == f"{dd.dia + pd.Timedelta(days=2):%Y-%m-%d}T00:00:00Z"
    assert "CANCÉLALA y avisa a THE BOSS; no la dejes abierta" in b["texto"]
    # 00:00 UTC = 6:00 p. m. en CDMX hoy (7:00 p. m. con el horario de verano que había hasta 2022)
    assert f"Si no se llena antes de {P.hora_cdmx(b['vence'])}" in b["texto"] and "(hora CDMX)" in b["texto"]
    assert P.hora_cdmx("2026-11-11T00:00:00Z") == "6:00 p. m. del 10/11/2026 (hora CDMX)"


def test_boleto_vigente_pasa(reg, tmp_path, monkeypatch, capsys):
    r, dd, b = _ronda_con_compra(reg, tmp_path, monkeypatch)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=15)).to_pydatetime()
    assert CR.verificar_boletos(r, f"{dd.dia:%Y-%m-%d}", ahora=ahora) == 0
    salida = capsys.readouterr().out
    assert f"✅ {b['boleto_id']}" in salida and "vencido" not in salida


def test_boleto_vencido_no_se_pone(reg, tmp_path, monkeypatch, capsys):
    r, dd, b = _ronda_con_compra(reg, tmp_path, monkeypatch)
    ahora = (dd.dia + pd.Timedelta(days=2, minutes=1)).to_pydatetime()
    assert CR.verificar_boletos(r, f"{dd.dia:%Y-%m-%d}", ahora=ahora) == 1
    salida = capsys.readouterr().out
    assert f"❌ {b['boleto_id']}" in salida and "boleto vencido: no lo pongas" in salida


def test_vigencia_sale_del_reglamento(reg):
    r = reg.copia_con({"ronda.vigencia_boleto_horas": 12})
    assert P.vence_compra(r, pd.Timestamp("2026-11-09", tz="UTC")) == "2026-11-10T12:00:00Z"
    assert P.vence_compra(reg, pd.Timestamp("2026-11-09", tz="UTC")) == "2026-11-11T00:00:00Z"
