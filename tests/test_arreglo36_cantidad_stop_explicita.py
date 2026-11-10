"""Arreglo 36: el boleto y el EJECUTOR dicen explícito por cuánta cantidad va el stop según la comisión."""
from pathlib import Path

from sobreviviente import papel as P

from test_arreglo33_cantidad_neta import _boleto

RAIZ = Path(__file__).resolve().parent.parent


def test_texto_del_boleto_compra_lo_dice_explicito():
    texto = P.texto_boleto(_boleto("COMPRAR"))
    assert "si commissionAsset es BNB (o cualquier moneda distinta a ETH)" in texto
    assert "executedQty completo, sin restar nada, redondeado hacia abajo al stepSize" in texto
    assert "si es ETH, por executedQty − commission" in texto
    assert "si la respuesta no trae comisión, usa 0.053 (cantidad_stop del boleto)" in texto


def test_ejecutor_lo_dice_explicito():
    doc = (RAIZ / "bots" / "4_EJECUTOR.md").read_text(encoding="utf-8")
    assert "sin restar nada" in doc and "`executedQty` − `commission`" in doc and "usa `cantidad_stop`" in doc
    assert "usa la misma cantidad del stop actual" in doc


def test_mover_stop_y_cerrar_usan_la_cantidad_del_stop_actual():
    assert "misma cantidad del stop actual" in P.texto_boleto(_boleto("MODIFICAR_STOP"))
    assert "misma cantidad del stop actual" in P.texto_boleto(_boleto("CERRAR"))
