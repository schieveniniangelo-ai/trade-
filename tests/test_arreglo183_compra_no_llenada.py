"""Arreglo 183 (I7): COMPRA_NO_LLENADA con motivo, también para cuando Binance RECHAZA la compra.

Antes, bots/4_EJECUTOR_REAL.md solo decía qué anotar si la compra FOK no se llenaba (EXPIRED). Si Binance la rechazaba
(contestaba con un error, por ejemplo -2010, y no creaba la orden), no había instrucción: el COMPRA_ENVIADA quedaba sin
resultado, `conciliar --real` lo contaba SIN STOP y ponía `bloqueo_compras`, que solo Ángelo quitaba, aunque nunca hubo
BTC (una falsa alarma).

Ahora:
* COMPRA_NO_LLENADA pide `--motivo` (EXPIRED, o el código y mensaje de Binance);
* al anotarla, ya no hay SIN STOP por esa compra; y si el bloqueo de compras lo había puesto ESA compra enviada sin
  anotar, se quita (queda en `falsas_alarmas`). Cualquier otro bloqueo se queda;
* bots/4_EJECUTOR_REAL.md (paso 4e) dice qué hacer si Binance rechaza la compra o si no se sabe cómo terminó.
"""
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
RECHAZO = "-2010 Account has insufficient balance for requested action."


def _enviar(r, b):
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]


def _no_llenada(r, b, motivo=RECHAZO, minutos=3):
    return RE.registrar_llenado(r, b["boleto_id"], "COMPRA_NO_LLENADA", motivo=motivo,
                                ahora=AHORA + timedelta(minutes=minutos))


@pytest.mark.parametrize("motivo", ["", "   "])
def test_sin_motivo_no_se_anota(compra, motivo):
    r, b, _ = compra
    _enviar(r, b)
    ok, msgs = _no_llenada(r, b, motivo)
    assert not ok and msgs == ["falta --motivo: EXPIRED si la compra FOK no se llenó, o el código y el mensaje de Binance "
                               "si la rechazó (por ejemplo \"-2010 Account has insufficient balance\")"]
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["COMPRA_ENVIADA"]


def test_rechazada_por_binance_quita_la_falsa_alarma_y_el_bloqueo(compra):
    r, b, foto = compra
    _enviar(r, b)
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=2))               # sin BTC: la compra nunca existió
    res = RE.conciliar(r, AHORA + timedelta(minutes=2))
    assert res["sin_stop"] == ["BTC"]                                    # la falsa alarma
    motivo = f"SIN STOP: BTC (compra enviada sin anotar, boleto {b['boleto_id']})"
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == motivo == RE.motivo_compra_sin_anotar("BTC", b["boleto_id"])
    ok, msgs = _no_llenada(r, b)
    assert ok and msgs[0] == f"👍 Anotado: la compra no se llenó ({RECHAZO}); no hay posición (no se reintenta)."
    assert msgs[1].startswith(f"✅ Se quitó el bloqueo de compras que había puesto esta compra enviada sin anotar "
                              f"({b['boleto_id']}): Binance no la llenó")
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"] is None and est["posiciones"] == []
    (fa,) = est["falsas_alarmas"]
    assert fa["boleto"] == b["boleto_id"] and fa["motivo"] == RECHAZO and fa["bloqueo"]["motivo"] == motivo
    assert RE.leer_llenados(r)[-1]["motivo"] == RECHAZO
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=4))
    res = RE.conciliar(r, AHORA + timedelta(minutes=5))
    assert res["ok"] and res["sin_stop"] == [] and RE.cargar_estado(r)["bloqueo_compras"] is None


def test_otro_bloqueo_no_se_quita(compra):
    r, b, _ = compra
    _enviar(r, b)
    RE.guardar_estado(r, {**RE.cargar_estado(r), "bloqueo_compras": {"desde": "x", "motivo": "SIN STOP: BTC"}})
    ok, msgs = _no_llenada(r, b, "EXPIRED")
    assert ok and len(msgs) == 1 and "(EXPIRED)" in msgs[0]
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == "SIN STOP: BTC"
    assert "falsas_alarmas" not in RE.cargar_estado(r)


def test_si_de_verdad_hay_btc_la_conciliacion_vuelve_a_bloquear(compra):
    """Si el EJECUTOR se equivoca (anota NO_LLENADA y sí se compró), la foto de saldo lo encuentra otra vez."""
    r, b, foto = compra
    _enviar(r, b)
    RE.conciliar(r, AHORA + timedelta(minutes=2))
    assert _no_llenada(r, b)[0] and RE.cargar_estado(r)["bloqueo_compras"] is None
    foto(cuenta(usdt=142.54 - 9.10, btc=0.00013), [], ahora=AHORA + timedelta(minutes=4))
    res = RE.conciliar(r, AHORA + timedelta(minutes=5))
    assert res["sin_stop"] == ["BTC"]
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"] == "SIN STOP: BTC en la cuenta que el estado real no conoce"


def test_por_la_linea_de_comandos(compra, monkeypatch, capsys):
    r, b, _ = compra
    _enviar(r, b)
    RE.conciliar(r, AHORA + timedelta(minutes=2))
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(RE, "ahora_utc", lambda: AHORA + timedelta(minutes=3))    # arreglo 188: con la foto aún fresca
    args = ["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA"]
    capsys.readouterr()
    assert MAIN.main(args) == 1
    assert capsys.readouterr().out.startswith("❌ falta --motivo")
    assert MAIN.main(args + ["--motivo", RECHAZO]) == 0
    salida = capsys.readouterr().out.splitlines()
    assert salida[0].startswith("👍 Anotado: la compra no se llenó (-2010") and salida[1].startswith("✅ Se quitó")


def test_textos(compra):
    r, b, _ = compra
    ok, msgs = RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                    precio_actual=70000.0)
    assert "si no se llena o Binance la rechaza, registra COMPRA_NO_LLENADA con --motivo (EXPIRED o el error de " \
        "Binance)" in msgs[0]
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso4 = ej[ej.index("4. Boleto de COMPRA"):ej.index("5. Boleto de CIERRE")]
    assert "--evento COMPRA_NO_LLENADA --motivo EXPIRED" in paso4
    assert "Si Binance RECHAZÓ la compra" in paso4 and "--motivo \"<código y mensaje de Binance, tal cual>\"" in paso4
    assert "el bloqueo se quita solo (era una falsa alarma)" in paso4
    assert "Si no sabes cómo terminó (se cortó la conexión): primero revisa con `spot.getOrder`" in paso4
