"""Arreglo 46: pruebas de la foto diaria de ESTELA (estela_vivo.guardar_foto) con un cliente de Binance falso."""
import json
from argparse import Namespace
from datetime import datetime, timezone

import pandas as pd

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import estela_vivo as EV

AHORA = datetime(2026, 11, 11, 0, 20, tzinfo=timezone.utc)          # la foto es del día 2026-11-10
FIN_MS = int(pd.Timestamp("2026-11-11", tz="UTC").timestamp() * 1000) - 1


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    return r


class FuturosFalso:
    """Imita las rutas públicas de Futuros que usa ESTELA."""

    def __init__(self, perps=("BTCUSDT", "ETHUSDT", "SOLUSDT"), vacios=(), bloqueado=False, bloqueado_en_datos=False):
        self.perps, self.vacios = perps, set(vacios)
        self.bloqueado, self.bloqueado_en_datos = bloqueado, bloqueado_en_datos
        self.pedidos = []

    def futuros(self, ruta, params=None):
        self.pedidos.append((ruta, params))
        if self.bloqueado:
            raise D.ErrorDatos("La API de Futuros respondió 451 (bloqueo por región).")
        if ruta == "/fapi/v1/exchangeInfo":
            return {"symbols": [{"symbol": s, "contractType": "PERPETUAL", "status": "TRADING"} for s in self.perps]
                    + [{"symbol": "XRPUSDT", "contractType": "PERPETUAL", "status": "SETTLING"},
                       {"symbol": "BNBUSDT", "contractType": "CURRENT_QUARTER", "status": "TRADING"}]}
        if self.bloqueado_en_datos:
            raise D.ErrorDatos("Futuros respondió 403")
        if params["symbol"] in self.vacios:
            return []
        valor = "1.9000" if "topLongShortPositionRatio" in ruta else "3.0000"
        return [{"symbol": params["symbol"], "longShortRatio": valor, "timestamp": FIN_MS - 299_999}]


def _foto(tmp_path, fecha="2026-11-10"):
    return json.loads((tmp_path / "datos" / "estela" / f"{fecha}.json").read_text(encoding="utf-8"))


def test_guarda_la_foto_del_dia_que_cerro(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    cli = FuturosFalso()
    ok, msg = EV.guardar_foto(r, cli, ahora=AHORA)
    assert ok and msg == "Foto de ESTELA del 2026-11-10 guardada: 3 monedas."
    foto = _foto(tmp_path)
    assert foto["fecha"] == "2026-11-10" and foto["por"] == "ESTELA"
    # Sin datos/papel/grandes.json usa la lista de respaldo, y solo los perpetuos que están operando
    assert sorted(foto["simbolos"]) == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert foto["simbolos"]["BTCUSDT"]["top_posiciones"] == 1.9 and foto["simbolos"]["BTCUSDT"]["masa_cuentas"] == 3.0
    assert AR.validar_estela(foto) == []
    # Se pide la última foto de 5 minutos ANTES de las 00:00 UTC (igual que en el estudio histórico)
    pedidos = [p for ruta, p in cli.pedidos if "futures/data" in ruta]
    assert pedidos and all(p["endTime"] == FIN_MS and p["period"] == "5m" and p["limit"] == 1 for p in pedidos)


def test_usa_las_grandes_de_la_ultima_ronda(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    AR.escribir_json_seguro(tmp_path / "datos" / "papel" / "grandes.json", ["ETHUSDT", "DOGEUSDT", "SOLUSDT"])
    ok, _ = EV.guardar_foto(r, FuturosFalso(), ahora=AHORA)
    assert ok and sorted(_foto(tmp_path)["simbolos"]) == ["ETHUSDT", "SOLUSDT"]      # DOGE no tiene perpetuo operando


def test_futuros_bloqueado_no_guarda_nada(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    for cli in (FuturosFalso(bloqueado=True), FuturosFalso(bloqueado_en_datos=True)):
        ok, msg = EV.guardar_foto(r, cli, ahora=AHORA)
        assert not ok and "bloqueadas desde esta computadora" in msg and "M3 se queda apagado" in msg
    assert not (tmp_path / "datos" / "estela").exists()


def test_una_moneda_sin_datos_se_reporta_y_las_demas_se_guardan(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    ok, msg = EV.guardar_foto(r, FuturosFalso(vacios=["SOLUSDT"]), ahora=AHORA)
    assert ok and msg == "Foto de ESTELA del 2026-11-10 guardada: 2 monedas (sin datos: SOLUSDT)."
    assert sorted(_foto(tmp_path)["simbolos"]) == ["BTCUSDT", "ETHUSDT"]


def test_foto_vacia_no_se_guarda(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    ok, msg = EV.guardar_foto(r, FuturosFalso(vacios=["BTCUSDT", "ETHUSDT", "SOLUSDT"]), ahora=AHORA)
    assert not ok and msg.startswith("La foto salió incompleta")
    assert not (tmp_path / "datos" / "estela" / "2026-11-10.json").exists()


def test_grandes_danado_da_error_claro(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    (tmp_path / "datos" / "papel" / "grandes.json").write_text("{dañado", encoding="utf-8")
    ok, msg = EV.guardar_foto(r, FuturosFalso(), ahora=AHORA)
    assert not ok and "grandes.json está dañado" in msg


def test_no_pisa_la_foto_de_otro_dia(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    assert EV.guardar_foto(r, FuturosFalso(), ahora=AHORA)[0]
    assert EV.guardar_foto(r, FuturosFalso(perps=("BTCUSDT",)), ahora=datetime(2026, 11, 12, 0, 20, tzinfo=timezone.utc))[0]
    assert len(_foto(tmp_path, "2026-11-10")["simbolos"]) == 3 and list(_foto(tmp_path, "2026-11-11")["simbolos"]) == ["BTCUSDT"]


def test_cmd_estela_registra_la_tarea(reg, tmp_path, monkeypatch, capsys):
    r = _reg_tmp(reg, tmp_path)
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    monkeypatch.setattr(D, "ClienteBinance", lambda reg_: FuturosFalso())
    assert CR.cmd_estela(Namespace(foto=False, reglamento=None)) == 2
    assert "estela --foto" in capsys.readouterr().out
    assert CR.cmd_estela(Namespace(foto=True, reglamento=None)) == 0
    assert capsys.readouterr().out.startswith("👍 Foto de ESTELA del ")
    monkeypatch.setattr(D, "ClienteBinance", lambda reg_: FuturosFalso(bloqueado=True))
    assert CR.cmd_estela(Namespace(foto=True, reglamento=None)) == 1
    assert capsys.readouterr().out.startswith("❌ Las rutas de Binance Futuros están bloqueadas")
    filas = [json.loads(x) for x in (tmp_path / "datos" / "bots" / "registro.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(f["bot"], f["tarea"], f["ok"]) for f in filas] == [("ESTELA", "estela --foto", True), ("ESTELA", "estela --foto", False)]
