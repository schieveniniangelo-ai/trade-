"""Arreglo 34: `ronda --verificar` revisa cada tipo de boleto contra las reglas de Binance (sin tocar el motor)."""
import json
from datetime import datetime, timezone

import pytest

from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D
from sobreviviente import papel as P

FILTROS = [{"filterType": "PRICE_FILTER", "tickSize": "0.01"},
           {"filterType": "LOT_SIZE", "stepSize": "0.0001", "minQty": "0.0002"},
           {"filterType": "NOTIONAL", "minNotional": "1"}]
AHORA = datetime(2026, 11, 10, 0, 15, tzinfo=timezone.utc)


def _base(accion, version="", tipo="MARKET"):
    b = {"boleto_id": f"20261109-C-{accion}-ETHUSDT-M0", "accion": accion, "simbolo": "ETHUSDT", "estrategia": "M0",
         "cantidad": 0.0045, "cantidad_stop": 0.0044, "paso_cantidad": 0.0001, "tick_precio": 0.01}
    if accion == "COMPRAR":
        b.update({"version_reglamento": version, "cartera": "C", "precio_entrada": 3000.0, "stop": 2550.0,
                  "precio_limite_stop": 2537.25, "riesgo_pct": 2.0, "id_stop": "x-s0"})
    elif accion == "MODIFICAR_STOP":
        b.update({"stop": 2600.0, "stop_anterior": 2550.0, "precio_limite_stop": 2587.0, "precio_limite_stop_anterior": 2537.25,
                  "id_stop": "x-s1", "id_stop_anterior": "x-s0"})
    else:
        b.update({"tipo_orden": tipo, "razon": "stop tocado" if tipo != "MARKET" else "salida de la estrategia"})
    b["texto"] = P.texto_boleto(b)
    return b


def _verificar(reg, tmp_path, monkeypatch, capsys, boleto, estado="TRADING", precio="3000", reglas_caidas=False):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    if boleto.get("accion") == "COMPRAR" and boleto.get("version_reglamento") == "":
        boleto["version_reglamento"] = r.version
    (tmp_path / "salida").mkdir(exist_ok=True)
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text(json.dumps([boleto]), encoding="utf-8")
    info = {"symbols": [{"symbol": "ETHUSDT", "status": estado, "filters": FILTROS}]}

    def exchange_info(self, mercado="SPOT", forzar=False):
        if reglas_caidas:
            raise D.ErrorDatos("No pude obtener datos de Spot: sin conexión")
        return info

    def spot(self, ruta, params=None):
        if precio is None:
            raise D.ErrorDatos("No pude obtener datos de Spot: sin conexión")
        assert ruta == "/api/v3/avgPrice" and params == {"symbol": "ETHUSDT"}
        return {"mins": 5, "price": precio}

    monkeypatch.setattr(D.ClienteBinance, "exchange_info", exchange_info)
    monkeypatch.setattr(D.ClienteBinance, "spot", spot)
    codigo = CR.verificar_boletos(r, "2026-11-09", ahora=AHORA)
    return codigo, capsys.readouterr().out


@pytest.mark.parametrize("accion,tipo", [("COMPRAR", ""), ("MODIFICAR_STOP", ""), ("CERRAR", "MARKET"),
                                         ("CERRAR", "YA_EJECUTADO_POR_STOP")])
def test_boletos_buenos_pasan(reg, tmp_path, monkeypatch, capsys, accion, tipo):
    codigo, salida = _verificar(reg, tmp_path, monkeypatch, capsys, _base(accion, tipo=tipo or "MARKET"))
    assert codigo == 0 and "✅" in salida and "❌" not in salida, salida


def test_compra_que_llega_al_minimo_con_el_limite_pasa(reg, tmp_path, monkeypatch, capsys):
    b = _base("COMPRAR")
    b.update({"cantidad": 0.0005, "cantidad_stop": 0.0004})      # 0.0004 × 2537.25 = 1.01 ≥ 1
    codigo, salida = _verificar(reg, tmp_path, monkeypatch, capsys, b)
    assert codigo == 0, salida


MALOS = [
    # COMPRAR
    ("COMPRAR", {"cantidad": 0.0005, "cantidad_stop": 0.0004, "precio_limite_stop": 2400.0}, {},
     "la venta en el stop no llega al mínimo"),       # con el stop (2550) sí llegaría; con el límite (2400) no
    ("COMPRAR", {"precio_entrada": 3000.005}, {}, "el precio de entrada no es múltiplo del tick"),
    ("COMPRAR", {"stop": 2550.005}, {}, "el stop no es múltiplo del tick"),
    ("COMPRAR", {"precio_limite_stop": 2537.255}, {}, "el límite del stop no es múltiplo del tick"),
    ("COMPRAR", {"cantidad": 0.0002, "cantidad_stop": 0.0001}, {}, "minQty"),
    ("COMPRAR", {}, {"estado": "BREAK"}, "estado BREAK (no TRADING)"),
    ("COMPRAR", {"precio_limite_stop": 2560.0}, {}, "el límite del stop no está en o abajo del stop"),
    # MODIFICAR_STOP
    ("MODIFICAR_STOP", {"stop": 2550.0, "precio_limite_stop": 2537.25}, {}, "no está arriba del anterior"),
    ("MODIFICAR_STOP", {"stop": 2600.005}, {}, "el stop no es múltiplo del tick"),
    ("MODIFICAR_STOP", {"precio_limite_stop": 2587.005}, {}, "el límite del stop no es múltiplo del tick"),
    ("MODIFICAR_STOP", {"precio_limite_stop": 2610.0}, {}, "el límite del stop no está en o abajo del stop"),
    ("MODIFICAR_STOP", {"cantidad_stop": 0.00445}, {}, "no está redondeada al paso"),
    ("MODIFICAR_STOP", {"cantidad_stop": 0.0001}, {}, "minQty"),
    ("MODIFICAR_STOP", {"cantidad_stop": 0.0003}, {}, "la venta en el stop no llega al mínimo"),   # 0.0003 × 2587 = 0.78
    ("MODIFICAR_STOP", {"id_stop": None}, {}, "faltan los id del stop"),
    ("MODIFICAR_STOP", {"id_stop_anterior": ""}, {}, "faltan los id del stop"),
    ("MODIFICAR_STOP", {}, {"estado": "HALT"}, "estado HALT (no TRADING)"),
    # CERRAR a mercado
    ("CERRAR", {"cantidad": 0.0, "cantidad_stop": 0.0}, {}, "la cantidad a vender es 0"),
    ("CERRAR", {"cantidad_stop": 0.00445}, {}, "no está redondeada al paso"),
    ("CERRAR", {"cantidad_stop": 0.0001}, {}, "minQty"),
    ("CERRAR", {"cantidad_stop": 0.0003}, {}, "no llega al mínimo de Binance"),                     # 0.0003 × 3000 = 0.9
    # (precio promedio caído en un CERRAR: desde el Arreglo 38 ya no bloquea; ver test_arreglo38)
]


@pytest.mark.parametrize("accion,cambios,extra,mensaje", MALOS)
def test_boleto_malo_por_cada_regla(reg, tmp_path, monkeypatch, capsys, accion, cambios, extra, mensaje):
    b = _base(accion)
    b.update(cambios)
    codigo, salida = _verificar(reg, tmp_path, monkeypatch, capsys, b, **extra)
    assert codigo == 1 and "❌" in salida and mensaje in salida, salida


def test_ya_ejecutado_por_stop_no_debe_pedir_vender(reg, tmp_path, monkeypatch, capsys):
    b = _base("CERRAR", tipo="YA_EJECUTADO_POR_STOP")
    b["texto"] = "[x] VENDER 0.0044 ETHUSDT a MERCADO"
    codigo, salida = _verificar(reg, tmp_path, monkeypatch, capsys, b)
    assert codigo == 1 and "no debe pedir vender" in salida


def test_reglas_de_binance_caidas_dan_codigo_1_sin_traceback(reg, tmp_path, monkeypatch, capsys):
    codigo, salida = _verificar(reg, tmp_path, monkeypatch, capsys, _base("COMPRAR"), reglas_caidas=True)
    assert codigo == 1
    assert "❌ No pude leer las reglas de Binance: no pongas nada" in salida and "Traceback" not in salida
