"""Arreglo 57: pruebas que confirman que el código simplificado hace lo mismo que antes."""
from sobreviviente import papel as P
from sobreviviente.exchange import Filtros


def test_vence_del_veto_en_hora_de_cdmx_o_tal_cual():
    assert P._vence_en_cdmx("2026-11-11T00:00:00Z") == "6:00 p. m. del 10/11/2026, hora CDMX"
    assert P._vence_en_cdmx("no es fecha") == "no es fecha"
    cartera = {"capital": 46.18, "boletos": [], "mensajes": [], "opera": True}
    out = {"dia": "2026-11-09", "carteras": {"C": cartera}, "referencias": {}, "avisos": [],
           "veto": {"razon": "hackeo", "vence": "no es fecha"}}
    assert "⚠️ Veto activo de Noticias: hoy no se compra (hackeo, hasta no es fecha)." in P.resumen_corto(out)
    out = {**out, "veto": None, "veto_info": {"razon": "hackeo", "vence": "2026-11-11T00:00:00Z"}}
    assert "ℹ️ Veto activo de Noticias hasta 6:00 p. m. del 10/11/2026, hora CDMX (hackeo); hoy no cambió nada." in P.resumen_corto(out)


def test_cantidad_del_stop_guardada_o_calculada():
    f = Filtros("ETHUSDT", 0.01, 0.0001, 0.0001, 5.0)
    assert P._cantidad_stop({"cantidad": 0.0531, "cantidad_stop": 0.053}, 0.1, f) == 0.053     # la guardada manda
    assert P._cantidad_stop({"cantidad": 0.0531}, 0.1, f) == 0.053                              # posición vieja: se calcula
    assert P._cantidad_stop({"cantidad": 0.0531}, 0.0, f) == 0.0531                             # sin comisión en la moneda
    assert P._cantidad_stop({"cantidad": 0.0531}, 0.0, None) == 0.0531                          # sin reglas de Binance
