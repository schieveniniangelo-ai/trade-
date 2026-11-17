"""Arreglo 166: si Binance tiene problemas, la ronda se salta COMPLETA (papel y real, igual).

Antes de operar se revisa en exchangeInfo que BTCUSDT esté en TRADING. Si no lo está, si exchangeInfo falla, si regresa
algo raro o si Binance no contestó y solo hay una copia guardada (no dice cómo está HOY), la ronda no compra, no toca
ninguna cartera ni el estado real, no escribe boletos y sale con ❌ y un mensaje claro para THE BOSS. Como no queda archivo
de boletos, se puede repetir cuando Binance responda. En real, además, se dicen como URGENTE las posiciones sin stop
confirmado (con el estado local, sin red). Sin red y sin llaves: clientes falsos.
"""
import json
from datetime import timedelta

import pandas as pd
import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo131_conciliar_real import POS, USDT_CON_POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas

PREPARAR = P.preparar_datos          # el de verdad (el fixture `mundo` lo cambia por uno falso)


class ClienteBinance(ClienteFalso):
    """Como ClienteFalso, pero con exchangeInfo caído, raro o con BTCUSDT en otro estado."""

    def __init__(self, *a, falla=False, raro=None, estado_btc="TRADING", **kw):
        super().__init__(*a, **kw)
        self.falla, self.raro, self.estado_btc = falla, raro, estado_btc
        self.pedidas = 0

    def exchange_info(self, mercado="SPOT", forzar=False):
        self.pedidas += 1
        if self.falla:
            raise D.ErrorDatos("No pude obtener datos de Spot: sin conexión")
        info = super().exchange_info(mercado, forzar)
        if self.raro is not None:
            return self.raro
        for s in info["symbols"]:
            if s["symbol"] == "BTCUSDT":
                s["status"] = self.estado_btc
        return info


CASOS = {
    "btc_en_halt": (dict(estado_btc="HALT"), "BTCUSDT en estado HALT (no TRADING)"),
    "btc_en_break": (dict(estado_btc="BREAK"), "BTCUSDT en estado BREAK (no TRADING)"),
    "exchangeinfo_cae": (dict(falla=True), "exchangeInfo de Binance falló (No pude obtener datos de Spot: sin conexión)"),
    "lista_vacia": (dict(raro=[]), "regresó algo raro"),
    "objeto_vacio": (dict(raro={}), "regresó algo raro"),
    "symbols_no_es_lista": (dict(raro={"symbols": "BTCUSDT"}), "regresó algo raro"),
    "sin_btcusdt": (dict(raro={"symbols": [{"symbol": "ETHUSDT", "status": "TRADING", "quoteAsset": "USDT"}]}),
                    "no trae BTCUSDT"),
    "solo_copia_guardada": (dict(copia_h=10), "Binance no contestó exchangeInfo (se usó una copia"),
}


def _huella(tmp_path):
    out = {}
    for base in (tmp_path / "datos" / "papel", tmp_path / "datos" / "real", tmp_path / "salida"):
        if base.is_dir():
            out.update({str(p): p.read_bytes() for p in base.rglob("*") if p.is_file() and p.name != "ronda.lock"})
    return out


# ---------------------------------------------------------------- revisar_binance (sin red)

def test_revisar_binance():
    bien = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING"}]}
    assert P.revisar_binance(bien) == ""
    assert "PRE_TRADING" in P.revisar_binance({"symbols": [{"symbol": "BTCUSDT", "status": "PRE_TRADING"}]})
    assert "None" in P.revisar_binance({"symbols": [{"symbol": "BTCUSDT"}]})              # sin estado: no se opera
    assert "algo raro" in P.revisar_binance(None) and "algo raro" in P.revisar_binance("hola")
    assert "no trae BTCUSDT" in P.revisar_binance({"symbols": ["BTCUSDT", 3]})
    # Con la copia guardada no importa lo que diga la copia: no es de hoy
    assert P.revisar_binance(bien, "se usó una copia de ayer").startswith("Binance no contestó exchangeInfo")


# ---------------------------------------------------------------- papel

@pytest.fixture
def papel(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    P.guardar_estado(r, {**P.estado_nuevo("A", 46.18, "2026-11-01"), "efectivo": 40.0})   # una cartera que ya existía

    def correr(**kw):
        cli = ClienteBinance(tmp_path, _velas_completas(), k, **kw)
        return CR.correr_ronda(r, ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime(), cliente=cli, memes=[]), cli
    return r, correr


@pytest.mark.parametrize("caso", list(CASOS))
def test_papel_se_salta_completa_y_se_puede_repetir(papel, tmp_path, capsys, caso):
    r, correr = papel
    kw, motivo = CASOS[caso]
    antes = _huella(tmp_path)
    codigo, cli = correr(**kw)
    salida = capsys.readouterr().out
    assert codigo == 1 and cli.pedidas == 1
    assert "❌ La ronda NO corrió: se saltó completa porque" in salida and motivo in salida
    assert "No se compró nada ni se tocó ninguna cartera; no se escribió ningún boleto." in salida
    assert "THE BOSS: vuelve a correr la ronda cuando Binance responda bien (hasta 120 min después de las 00:10 UTC" in salida
    assert _huella(tmp_path) == antes                         # ni carteras, ni boletos, ni grandes.json, ni referencias
    assert not list((tmp_path / "salida").glob("boletos_*.json")) if (tmp_path / "salida").exists() else True
    fila = AR.leer_registro(r)[-1]
    assert (fila["bot"], fila["tarea"], fila["ok"]) == ("THE BOSS", "ronda", False)
    assert fila["detalle"].startswith("saltada: ") and fila["a_tiempo"] is True
    # Binance ya responde bien: la misma ronda se repite y corre normal
    codigo, _ = correr()
    assert codigo == 0 and list((tmp_path / "salida").glob("boletos_*.json"))
    assert "ya corrió" not in capsys.readouterr().out


def test_papel_con_binance_bien_no_cambia_nada(papel, capsys):
    r, correr = papel
    codigo, _ = correr()
    assert codigo == 0 and "se saltó" not in capsys.readouterr().out


def test_preparar_datos_con_copia_sigue_igual_y_avisa_el_motivo(reg, tmp_path):
    """La copia guardada de menos de 48 h no cambia datos_ok (arreglo 59); solo deja el motivo para saltar la ronda."""
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    cli = ClienteBinance(tmp_path, _velas_completas(), k, copia_h=10)
    dd = PREPARAR(r, cli, [], ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime())
    assert dd.datos_ok and dd.no_opera.startswith("Binance no contestó exchangeInfo")
    cli = ClienteBinance(tmp_path / "otra", _velas_completas(), k)
    assert PREPARAR(r, cli, [], ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()).no_opera == ""
    with pytest.raises(P.BinanceNoOpera, match="BTCUSDT en estado HALT"):
        PREPARAR(r, ClienteBinance(tmp_path / "x", _velas_completas(), k, estado_btc="HALT"), [],
                 ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime())


# ---------------------------------------------------------------- real

def _real(mundo, monkeypatch, caso):  # noqa: F811
    """La ronda real con el preparar_datos de verdad y un cliente falso; con copia, el `mundo` deja el motivo."""
    r, cfg, foto, correr = mundo
    kw, motivo = CASOS[caso]
    falso = P.preparar_datos                 # el del `mundo`, para volver a él
    if caso == "solo_copia_guardada":

        def con_copia(reg, cli, memes, ahora=None, **k):
            dd = falso(reg, cli, memes, ahora=ahora, **k)
            dd.no_opera = P.revisar_binance({}, "se usó una copia de 2026-11-15 00:10 UTC de las reglas de Binance de "
                                                "SPOT (exchangeInfo); no está al día")
            return dd
        monkeypatch.setattr(P, "preparar_datos", con_copia)
        cli = object()
    else:
        monkeypatch.setattr(P, "preparar_datos", PREPARAR)
        cli = ClienteBinance(r.ruta.parent, _velas_completas(), 400, **kw)
    return r, foto, cli, motivo, falso


@pytest.mark.parametrize("caso", ["btc_en_halt", "exchangeinfo_cae", "objeto_vacio", "sin_btcusdt", "solo_copia_guardada"])
def test_real_se_salta_completa_y_se_puede_repetir(mundo, monkeypatch, tmp_path, capsys, caso):  # noqa: F811
    r, foto, cli, motivo, falso = _real(mundo, monkeypatch, caso)
    foto()
    antes = _huella(tmp_path)
    assert RR.correr(r, AHORA, cliente=cli, memes=[]) == 1
    salida = capsys.readouterr().out
    assert salida.startswith("████ REAL ████\n❌ La ronda real NO corrió: se saltó completa porque") and motivo in salida
    assert "No se compró nada ni se tocó el estado real; no se escribió ningún boleto." in salida
    assert "URGENTE" not in salida                             # no hay posiciones
    assert _huella(tmp_path) == antes
    assert not RR.archivo_boletos(r, "2026-11-15").exists() and not RE.archivo_conciliacion(r).exists()
    fila = AR.leer_registro(r)[-1]
    assert (fila["tarea"], fila["ok"]) == ("ronda --modo real", False) and fila["detalle"].startswith("saltada: ")
    # Binance ya responde bien: la ronda real se repite y corre normal (con el `mundo` de siempre)
    monkeypatch.setattr(P, "preparar_datos", falso)
    assert mundo[3]() == 0 and RR.archivo_boletos(r, "2026-11-15").exists()


def test_real_saltada_dice_las_posiciones_sin_stop_como_urgentes(mundo, monkeypatch, capsys):  # noqa: F811
    r, foto, cli, *_ = _real(mundo, monkeypatch, "btc_en_halt")
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [{**POS, "estado_stop": "SIN_STOP"}]})
    foto(cuenta(usdt=USDT_CON_POS, btc=0.00012), [])
    antes = RE.archivo_estado(r).read_bytes()
    assert RR.correr(r, AHORA, cliente=cli, memes=[]) == 1
    lineas = capsys.readouterr().out.splitlines()
    assert lineas[0] == "████ REAL ████"
    assert lineas[1].startswith("❌ URGENTE: BTC no tiene stop confirmado (estado SIN_STOP) y hoy no hay boletos")
    assert "vender sin boleto solo lo decide él" in lineas[1] and "se saltó completa" in lineas[2]
    assert RE.archivo_estado(r).read_bytes() == antes          # ni el bloqueo se escribe: no se tocó nada


def test_real_saltada_con_stop_activo_no_dice_urgente(mundo, monkeypatch, capsys):  # noqa: F811
    r, foto, cli, *_ = _real(mundo, monkeypatch, "btc_en_break")
    RE.guardar_estado(r, {**RE.estado_nuevo(142.54, "2026-11-14"), "posiciones": [dict(POS)]})
    foto(cuenta(usdt=USDT_CON_POS, btc_bloq=0.00012), [orden_stop()])
    assert RR.correr(r, AHORA, cliente=cli, memes=[]) == 1
    salida = capsys.readouterr().out
    assert "URGENTE" not in salida and "BTCUSDT en estado BREAK" in salida


def test_real_saltada_con_estado_danado_lo_dice(mundo, monkeypatch, capsys):  # noqa: F811
    r, foto, cli, *_ = _real(mundo, monkeypatch, "btc_en_halt")
    RE.archivo_estado(r).parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(RR, "compuertas_puerta", lambda reg: [])        # la puerta ya se revisó; el estado se daña después
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert RR.correr(r, AHORA, cliente=cli, memes=[]) == 1
    assert "❌ URGENTE: no pude leer el estado real" in capsys.readouterr().out


def test_real_simular_saltada_no_registra(mundo, monkeypatch, capsys):  # noqa: F811
    r, foto, cli, *_ = _real(mundo, monkeypatch, "btc_en_halt")
    foto()
    n = len(AR.leer_registro(r))
    assert RR.correr(r, AHORA, cliente=cli, memes=[], simular=True) == 1
    salida = capsys.readouterr().out
    assert "se saltó completa" in salida and "SIMULACIÓN: no se escribió nada." in salida
    assert len(AR.leer_registro(r)) == n


def test_real_fuera_de_hora_saltada_cuenta_tarde(mundo, monkeypatch, capsys):  # noqa: F811
    r, foto, cli, *_ = _real(mundo, monkeypatch, "btc_en_halt")
    tarde = AHORA + timedelta(hours=3)
    foto(ahora=tarde - timedelta(minutes=5))
    assert RR.correr(r, tarde, cliente=cli, memes=[]) == 1
    assert AR.leer_registro(r)[-1]["a_tiempo"] is False
    assert json.dumps(AR.leer_registro(r)[-1], ensure_ascii=False).count("saltada") == 1
