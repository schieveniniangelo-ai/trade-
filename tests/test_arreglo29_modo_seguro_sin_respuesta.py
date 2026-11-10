"""Arreglo 29: en MODO SEGURO el resumen no repite el aviso y no pide respuesta (tampoco da 👍)."""
from sobreviviente import papel as P

AVISO = "vetos.json viene mal (veto #1: vence en más de 72 horas): se ignora y hoy no hay entradas nuevas (modo seguro)."


def _out(**kw):
    cartera = {"capital": 46.18, "boletos": [], "mensajes": [], "opera": True}
    base = {"dia": "2026-11-09", "carteras": {"C": {**cartera, **kw.pop("cartera", {})}}, "referencias": {},
            "avisos": [AVISO], "modo_seguro": True}
    base.update(kw)
    return base


def test_modo_seguro_sin_repetir_y_sin_pedir_respuesta():
    texto = P.resumen_corto(_out())
    lineas = texto.splitlines()
    assert lineas[1].startswith("⚠️ MODO SEGURO: hoy no se compra (vetos.json viene mal")
    assert texto.count("vetos.json viene mal") == 1                     # no se repite más abajo
    assert lineas[-1] == "Solo para que sepas; no tienes que contestar."
    assert "Necesito tu respuesta" not in texto and "👍" not in texto


def test_otro_aviso_distinto_si_aparece():
    texto = P.resumen_corto(_out(avisos=[AVISO, "Las velas de XRPUSDT llegaron tarde."]))
    assert "⚠️ Las velas de XRPUSDT llegaron tarde." in texto


def test_modo_seguro_y_algo_que_si_necesita_respuesta():
    texto = P.resumen_corto(_out(cartera={"detenido": True}))
    assert texto.splitlines()[-1] == "Necesito tu respuesta (ver arriba)."


def test_sin_modo_seguro_sigue_el_pulgar():
    texto = P.resumen_corto(_out(modo_seguro=False, avisos=[]))
    assert texto.splitlines()[-1] == "👍 No necesito nada de ti."
