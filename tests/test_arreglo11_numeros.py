"""Arreglo 11: los números de los boletos van en notación normal (nunca "5e-05")."""
import json
import re

from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def test_numero_txt():
    assert P.numero_txt(5e-05) == "0.00005"
    assert P.numero_txt(9.2e-06) == "0.0000092"
    assert P.numero_txt(0.1 + 0.2, 0.01) == "0.3"           # sin ruido de punto flotante
    assert P.numero_txt(100.0) == "100" and P.numero_txt(2.50) == "2.5" and P.numero_txt(1200) == "1200"
    assert P.numero_txt(75368.41, 0.01) == "75368.41"


def test_los_cuatro_tipos_de_boleto_sin_notacion_cientifica():
    base = {"simbolo": "PEPEUSDT", "cantidad": 5e-05, "paso_cantidad": 1e-05, "tick_precio": 1e-08}
    boletos = [
        {**base, "boleto_id": "x-COM", "accion": "COMPRAR", "precio_entrada": 9.2e-06, "stop": 8.1e-06,
         "precio_limite_stop": 8.05e-06, "vence": "2026-11-11T00:00:00Z"},
        {**base, "boleto_id": "x-MOD", "accion": "MODIFICAR_STOP", "stop": 8.6e-06, "precio_limite_stop": 8.55e-06,
         "stop_anterior": 8.1e-06, "precio_limite_stop_anterior": 8.05e-06},
        {**base, "boleto_id": "x-CER", "accion": "CERRAR", "tipo_orden": "MARKET", "razon": "cerró bajo el piso del canal"},
        {**base, "boleto_id": "x-CES", "accion": "CERRAR", "tipo_orden": "YA_EJECUTADO_POR_STOP", "razon": "stop"},
    ]
    for b in boletos:
        t = P.texto_boleto(b)
        assert not re.search(r"\d[eE][-+]?\d", t), t
    t_compra = P.texto_boleto(boletos[0])
    assert "COMPRAR 0.00005 PEPEUSDT" in t_compra and "LIMIT a 0.0000092" in t_compra
    assert "stop 0.0000081" in t_compra and "límite 0.00000805" in t_compra
    assert "stop 0.0000086" in P.texto_boleto(boletos[1]) and "VENDER 0.00005 PEPEUSDT" in P.texto_boleto(boletos[2])


def test_el_json_de_boletos_guarda_numeros_como_numeros(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    P.ronda(r, dd)
    boletos = json.loads((tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json").read_text(encoding="utf-8"))
    compras = [b for b in boletos if b["accion"] == "COMPRAR"]
    assert compras
    for b in compras:
        for campo in ("cantidad", "precio_entrada", "stop", "precio_limite_stop"):
            assert isinstance(b[campo], (int, float)) and not isinstance(b[campo], bool), campo
        assert P.numero_txt(b["cantidad"], b["paso_cantidad"]) in b["texto"]
