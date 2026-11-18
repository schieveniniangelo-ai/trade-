"""Arreglo 182 (I6): COMPRA_ENVIADA pide --precio-actual y revisa EN CÓDIGO el vencimiento y `no_comprar_si`.

Antes, que el boleto no estuviera vencido y que el precio de spot.tickerPrice no pegara con `no_comprar_si` (arriba del
límite de compra, a 2 % o menos del stop, o fuera de PERCENT_PRICE_BY_SIDE) solo lo revisaba el EJECUTOR a mano (paso 4b).
Ahora `registrar-llenado --real --evento COMPRA_ENVIADA` exige `--precio-actual` y lo revisa: si algo falla, sale
«❌ NO mandes la compra: … No se anotó nada. Avisa a THE BOSS …» y no se escribe ningún renglón.
Con el boleto de 70,000 / stop 59,500 de las pruebas: límite de compra 70,210; cerca del stop ≤ 60,690; PERCENT_PRICE
hasta 74,003.125; vence a las 02:10 UTC del 16 nov (8:10 p. m. CDMX del 15).
"""
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE

from apoyo_real import AHORA
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
ENVIADA = "COMPRA_ENVIADA"


def _enviar(r, b, precio, cuando=AHORA + timedelta(minutes=1)):
    return RE.registrar_llenado(r, b["boleto_id"], ENVIADA, ahora=cuando, precio_actual=precio)


def test_las_reglas_salen_del_boleto(compra):
    _, b, _ = compra
    reglas = b["no_comprar_si"]
    assert (reglas["precio_actual_mayor_que"], reglas["precio_actual_menor_o_igual_que"],
            reglas["precio_actual_mayor_que_por_percent_price"]) == (70210.0, 60690.0, 74003.125)
    assert b["vence_utc"] == "2026-11-16T02:10:00Z"


@pytest.mark.parametrize("precio, pedazo", [
    (None, "falta --precio-actual (el último precio de spot.tickerPrice): sin él no se revisan las reglas no_comprar_si"),
    (0.0, "el precio actual 0.0 no es válido"),
    (float("nan"), "el precio actual nan no es válido"),
    (70210.5, "el precio actual 70210.5 es mayor que el límite de compra 70210 (no_comprar_si)"),
    (60690.0, "el precio actual 60690 está muy cerca del stop: menor o igual a 60690 (no_comprar_si)"),
    (60000.0, "el precio actual 60000 está muy cerca del stop"),
])
def test_si_el_precio_pega_con_no_comprar_si_no_se_anota(compra, precio, pedazo):
    r, b, _ = compra
    ok, msgs = _enviar(r, b, precio)
    assert not ok and msgs[0].startswith(f"NO mandes la compra: {pedazo}")
    assert msgs[0].endswith("No se anotó nada. Avisa a THE BOSS con este mensaje.")
    assert RE.leer_llenados(r) == []


def test_percent_price(compra):
    r, b, _ = compra
    b2 = {**b, "no_comprar_si": {**b["no_comprar_si"], "precio_actual_mayor_que": 80000.0}}    # para llegar a la regla
    assert RE._por_que_no_mandar(b2, 74003.2, AHORA) == (
        "con el precio actual 74003.2, Binance rechazaría el stop por PERCENT_PRICE_BY_SIDE (el precio no puede pasar de "
        "74003.125; no_comprar_si)")
    assert RE._por_que_no_mandar(b2, 74003.0, AHORA) == ""


def test_boleto_vencido_no_se_anota(compra):
    r, b, _ = compra
    ok, msgs = _enviar(r, b, 70000.0, cuando=AHORA + timedelta(hours=3))
    assert not ok and msgs[0] == ("NO mandes la compra: el boleto venció a las 8:10 p. m. del 15/11/2026 (hora CDMX). No "
                                  "se anotó nada. Avisa a THE BOSS con este mensaje.")
    assert RE.leer_llenados(r) == []
    assert _enviar(r, b, 70000.0, cuando=AHORA + timedelta(minutes=118))[0]       # 2:10 UTC justo: todavía vale


@pytest.mark.parametrize("cambio, pedazo", [
    ({"vence_utc": None}, "el boleto no dice cuándo vence"),
    ({"no_comprar_si": None}, "el boleto no trae sus reglas no_comprar_si completas"),
    ({"no_comprar_si": {"precio_actual_mayor_que": 70210.0}}, "el boleto no trae sus reglas no_comprar_si completas"),
])
def test_un_boleto_sin_sus_datos_no_se_aprueba(compra, cambio, pedazo):
    _, b, _ = compra
    assert RE._por_que_no_mandar({**b, **cambio}, 70000.0, AHORA) == pedazo


def test_con_el_precio_bueno_se_anota_y_lo_guarda(compra):
    r, b, _ = compra
    ok, msgs = _enviar(r, b, 70000.0)
    assert ok and msgs[0].startswith(f"👍 Compra ENVIADA anotada ({b['boleto_id']})")
    assert msgs[0].endswith("Revisé el precio actual 70000 contra no_comprar_si y el vencimiento: ✅.")
    (fila,) = RE.leer_llenados(r)
    assert fila["evento"] == ENVIADA and fila["precio_actual"] == 70000.0


def test_las_puertas_de_siempre_van_primero(compra):
    r, b, _ = compra
    RE.guardar_estado(r, {**RE.cargar_estado(r), "bloqueo_compras": {"desde": "x", "motivo": "SIN STOP: BTC"}})
    ok, msgs = _enviar(r, b, None)
    assert not ok and "compras reales bloqueadas por SIN STOP: BTC" in msgs[0]


def test_por_la_linea_de_comandos(compra, monkeypatch, capsys):
    r, b, _ = compra
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(RE, "ahora_utc", lambda: AHORA + timedelta(minutes=1))
    capsys.readouterr()
    args = ["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", ENVIADA]
    assert MAIN.main(args) == 1
    assert capsys.readouterr().out.startswith("❌ NO mandes la compra: falta --precio-actual")
    assert MAIN.main(args + ["--precio-actual", "70300"]) == 1
    assert "es mayor que el límite de compra 70210" in capsys.readouterr().out and RE.leer_llenados(r) == []
    assert MAIN.main(args + ["--precio-actual", "70100.5"]) == 0
    assert capsys.readouterr().out.startswith("👍 Compra ENVIADA anotada")
    assert RE.leer_llenados(r)[0]["precio_actual"] == 70100.5


def test_textos_del_boleto_y_del_ejecutor(compra):
    _, b, _ = compra
    assert "--evento COMPRA_ENVIADA --precio-actual <el precio de spot.tickerPrice>" in b["antes_de_comprar"]
    assert "con --precio-actual = el precio de spot.tickerPrice" in b["texto"]
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso4 = ej[ej.index("4. Boleto de COMPRA"):ej.index("5. Boleto de CIERRE")]
    assert "--evento COMPRA_ENVIADA --precio-actual <price de spot.tickerPrice>" in paso4
    assert "que el boleto no esté vencido y que ese precio no pegue con ninguna regla de `no_comprar_si`" in paso4
