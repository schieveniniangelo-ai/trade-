"""Arreglo 41: una posición abierta sin velas de hoy pide revisión a mano: el resumen no da 👍 (tampoco repetido)."""
from sobreviviente import papel as P

from test_arreglo35_posicion_sin_velas import _con_btc_abierto
from test_papel import _datos_dia


def test_sin_velas_de_hoy_no_hay_pulgar(reg, tmp_path):
    r, k, _ = _con_btc_abierto(reg, tmp_path)
    dd = _datos_dia(r, k + 1)[0]
    dd.md.velas.pop("BTCUSDT")
    for vez in ("primera", "repetida"):                       # la repetida regresa lo guardado de ese día
        hoy = P.ronda_cartera(r, "C", dd, [], [])
        texto = P.resumen_corto({"dia": hoy["dia"], "carteras": {"C": hoy}, "referencias": {}, "avisos": []})
        assert "revisar a mano" in texto and "👍" not in texto, vez
        assert texto.splitlines()[-1] == "Necesito tu respuesta (ver arriba).", vez
