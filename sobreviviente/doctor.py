"""`python -m sobreviviente doctor`: revisa que la computadora (la de Grok Bot) tenga todo lo necesario.

Imprime ✅ o ❌ por renglón y, en cada ❌, qué hacer.
"""
from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

import requests

from . import archivos as AR
from . import python_actual
from .reglamento import Reglamento

SITIOS = [
    ("Binance Spot (principal)", "https://api.binance.com/api/v3/ping",
     "Normal en algunas nubes (bloqueo por país). El sistema usa solo el respaldo; no hay que hacer nada si el respaldo sale ✅."),
    ("Binance Spot (respaldo oficial)", "https://data-api.binance.vision/api/v3/ping",
     "Sin esto no hay datos. Pide al soporte de Grok Bot que permita salir a data-api.binance.vision."),
    ("Binance históricos", "https://data.binance.vision/?prefix=data/spot/",
     "Solo hace falta para el backtest. Para el papel diario no es indispensable."),
    ("Binance Futuros (ESTELA)", "https://fapi.binance.com/fapi/v1/ping",
     "Sin esto ESTELA (M3) se queda apagada. Lo demás funciona igual."),
]


def revisar(reg: Reglamento, imprimir=print) -> int:
    malos = 0

    def linea(ok: bool, texto: str, que_hacer: str = "") -> None:
        nonlocal malos
        imprimir(("✅ " if ok else "❌ ") + texto + ("" if ok or not que_hacer else f"\n     → {que_hacer}"))
        malos += 0 if ok else 1

    v = sys.version_info
    linea(v >= (3, 11), f"Python {v.major}.{v.minor}.{v.micro}", "Instala Python 3.11 o más nuevo.")
    for paquete in ("pandas", "numpy", "yaml", "requests"):
        try:
            m = importlib.import_module(paquete)
            linea(True, f"Paquete {paquete} {getattr(m, '__version__', '')}")
        except ImportError:
            linea(False, f"Falta el paquete {paquete}", f"Corre: {python_actual()} -m pip install -r requirements.txt")
    carpeta = AR.carpeta_datos(reg)
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=carpeta, delete=True) as f:
            f.write(b"ok")
        linea(True, f"Se puede escribir en {carpeta}")
    except OSError as e:
        linea(False, f"No se puede escribir en {carpeta} ({e})", "Da permiso de escritura a la carpeta datos/.")
    linea(True, f"Reglamento {reg.version} sin choques")
    for nombre, url, que in SITIOS:
        indispensable = "respaldo" in nombre
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "sobreviviente-pro/2.0"})
            ok, txt = r.status_code == 200, f"{nombre}: {'responde' if r.status_code == 200 else f'responde {r.status_code}'}"
        except requests.RequestException as e:
            ok, txt = False, f"{nombre}: sin conexión ({type(e).__name__})"
        if ok or indispensable:
            linea(ok, txt, que)
        else:
            imprimir(f"⚠️ {txt}\n     → {que}")  # no indispensable: no cuenta como falla
    for n, (_, err) in AR.leer_todos(reg).items():
        if err and err[0].startswith("no existe"):
            linea(True, f"{n}: todavía no existe (se crea vacío; está bien)")
        else:
            linea(not err, f"{n}" + (f": {'; '.join(err)}" if err else " bien escrito"),
                  "El bot que lo escribe debe corregirlo; mientras, la ronda va en modo seguro.")
    sin_llaves = not any(Path(reg.ruta.parent if reg.ruta else ".").glob("*.key"))
    linea(sin_llaves, "Sin llaves de Binance en la carpeta (correcto)", "Borra cualquier llave: el sistema NO las usa.")
    imprimir("👍 Todo listo." if malos == 0 else f"Hay {malos} renglón(es) con ❌. Revisa lo que dice cada uno.")
    return 0 if malos == 0 else 1
