"""Arreglo 16: qué hace de verdad ONLY_NEW (error -2011 si el stop ya se ejecutó en parte) y qué usar si el
identificador del stop viejo no existe."""
from pathlib import Path

from sobreviviente import papel as P

RAIZ = Path(__file__).resolve().parent.parent
FRASE_ONLY_NEW = ("con ONLY_NEW, si el stop viejo ya se ejecutó en parte (PARTIALLY_FILLED), Binance no lo cancela "
                  "(error -2011) y no pone el nuevo: no hagas nada más y avisa a THE BOSS")
FRASE_CANCEL_ID = ("si el cancelOrigClientOrderId no existe (el boleto anterior no se aplicó), usa cancelOrderId del "
                   "STOP_LOSS_LIMIT de venta abierto de ese par")


def test_boleto_mover_stop_dice_lo_correcto_de_only_new():
    b = {"boleto_id": "x", "accion": "MODIFICAR_STOP", "simbolo": "SOLUSDT", "cantidad": 0.12, "stop": 150.5,
         "precio_limite_stop": 149.74, "stop_anterior": 140.0, "precio_limite_stop_anterior": 139.3,
         "id_stop_anterior": "spaaaa", "id_stop": "spbbbb"}
    t = P.texto_boleto(b)
    assert FRASE_ONLY_NEW in t
    assert "ya se activó Binance no lo cancela" not in t


def test_ejecutor_tiene_las_dos_frases():
    texto = (RAIZ / "bots" / "4_EJECUTOR.md").read_text(encoding="utf-8")
    assert FRASE_ONLY_NEW.replace("con ONLY_NEW", "Con `ONLY_NEW`") in texto
    assert FRASE_CANCEL_ID[0].upper() + FRASE_CANCEL_ID[1:] in texto
