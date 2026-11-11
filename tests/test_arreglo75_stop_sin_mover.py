"""Arreglo 75: si el motor sube el stop menos que el tick de Binance, no sale un boleto MODIFICAR_STOP.

Ya redondeado hacia abajo, ese stop queda igual al de la orden vigente y `ronda --verificar` lo rechazaría
("el stop nuevo no está arriba del anterior"). Sin red ni llaves: velas sintéticas, filtros falsos y un motor de
gestión falso que deja el stop justo donde la prueba lo pide."""
import json
from datetime import timedelta

import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P
from sobreviviente.exchange import Filtros, redondear_abajo
from sobreviviente.gestion import Evento

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

STOP_ANTERIOR = 10.00


def _ronda_con_stop(reg, tmp_path, monkeypatch, stop_motor):
    """Abre BTC en la Cartera C, deja su stop en 10.00 y corre el día siguiente con tick 0.01 y un motor que
    sube el stop a `stop_motor` (sin redondear). Regresa (resultado, posición antes, posición después, r, dd)."""
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    assert P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])["posiciones"] == ["BTCUSDT"]
    est = P.cargar_estado(r, "C", "")
    est["posiciones"][0]["gestion"]["stop"] = STOP_ANTERIOR
    P.guardar_estado(r, est)
    antes = json.loads(json.dumps(est["posiciones"][0]))

    def vela_falsa(g, *a, **kw):
        g.stop = max(g.stop, stop_motor)     # el motor solo sube el stop (como el de verdad)
        return Evento()

    monkeypatch.setattr(P, "vela", vela_falsa)
    dd = _datos_dia(r, k + 1)[0]
    dd.md.filtros["BTCUSDT"] = Filtros("BTCUSDT", 0.01, 0.0001, 0.0001, 5.0)
    res = P.ronda_cartera(r, "C", dd, [], [])
    despues = next(p for p in P.cargar_estado(r, "C", "")["posiciones"] if p["simbolo"] == "BTCUSDT")
    return res, antes, despues, r, dd


def _mover(res):
    return [b for b in res["boletos"] if b["accion"] == "MODIFICAR_STOP"]


def test_stop_que_sube_menos_de_un_tick_no_da_boleto(reg, tmp_path, monkeypatch):
    res, antes, despues, _, _ = _ronda_con_stop(reg, tmp_path, monkeypatch, 10.004)
    assert _mover(res) == []
    assert despues["gestion"]["stop"] == STOP_ANTERIOR            # el stop de la orden vigente
    assert despues.get("stop_n", 0) == antes.get("stop_n", 0)      # no se "gastó" un id de stop


def test_stop_que_sube_un_tick_o_mas_si_da_boleto_y_pasa_verificar(reg, tmp_path, monkeypatch, capsys):
    res, antes, despues, r, dd = _ronda_con_stop(reg, tmp_path, monkeypatch, 10.02)
    mover = _mover(res)
    assert len(mover) == 1
    b = mover[0]
    _, lim_stop = P.limites_ejecucion(r)
    assert b["stop"] == 10.02 and b["stop_anterior"] == STOP_ANTERIOR
    assert b["precio_limite_stop"] == redondear_abajo(10.02 * (1 - lim_stop / 100), 0.01)   # como hoy
    assert despues["gestion"]["stop"] == 10.02
    assert despues["stop_n"] == antes.get("stop_n", 0) + 1
    assert b["id_stop_anterior"] == P.id_stop(antes["id"], antes.get("stop_n", 0))

    # `ronda --verificar` lo acepta (reglas de Binance falsas, sin red)
    fecha = dd.dia.strftime("%Y-%m-%d")
    salida = AR.carpeta_datos(r).parent / "salida"
    salida.mkdir(parents=True, exist_ok=True)
    (salida / f"boletos_{fecha}.json").write_text(json.dumps([b], ensure_ascii=False), encoding="utf-8")
    filtros = [{"filterType": "PRICE_FILTER", "tickSize": "0.01"},
               {"filterType": "LOT_SIZE", "stepSize": "0.0001", "minQty": "0.0001"},
               {"filterType": "NOTIONAL", "minNotional": "0.0001"}]
    info = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "filters": filtros}]}
    monkeypatch.setattr(D.ClienteBinance, "exchange_info", lambda self, mercado="SPOT", forzar=False: info)
    monkeypatch.setattr(D.ClienteBinance, "spot", lambda self, ruta, params=None: {"mins": 5, "price": "100"})
    ahora = (dd.dia + timedelta(days=1, minutes=15)).to_pydatetime()
    codigo = CR.verificar_boletos(r, fecha, ahora=ahora)
    out = capsys.readouterr().out
    assert codigo == 0 and "❌" not in out and "✅" in out, out


@pytest.mark.parametrize("stop_motor", [STOP_ANTERIOR, 9.5])
def test_stop_que_no_se_mueve_no_da_boleto(reg, tmp_path, monkeypatch, stop_motor):
    res, antes, despues, _, _ = _ronda_con_stop(reg, tmp_path, monkeypatch, stop_motor)
    assert _mover(res) == []
    assert despues["gestion"]["stop"] == STOP_ANTERIOR
    assert despues.get("stop_n", 0) == antes.get("stop_n", 0)
