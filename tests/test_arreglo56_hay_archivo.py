"""Arreglo 56: una sola función para "existe el archivo o su copia anterior" (antes repetida en seis lugares)."""
from sobreviviente import archivos as AR


def test_hay_archivo_cuenta_el_original_o_su_copia(tmp_path):
    ruta = tmp_path / "cartera_A.json"
    assert AR.hay_archivo(ruta) is False
    AR.escribir_json_seguro(ruta, {"v": 1})
    assert AR.hay_archivo(ruta) is True and AR.hay_archivo(str(ruta)) is True
    AR.escribir_json_seguro(ruta, {"v": 2})                 # la segunda escritura deja cartera_A.json.bak
    ruta.unlink()
    assert AR.hay_archivo(ruta) is True                     # queda la copia anterior…
    assert AR.leer_json_seguro(ruta) == {"v": 1}            # …y es la que se lee
