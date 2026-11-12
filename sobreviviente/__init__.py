"""Sobreviviente Pro: motor de trading determinista para el equipo de bots de Ángelo."""
import sys
from pathlib import Path

__version__ = "0.1.0"
_RAIZ = Path(__file__).resolve().parent.parent


def python_actual() -> str:
    """El Python que está corriendo el programa, listo para copiar en un aviso «corre …» (Arreglo 96).

    Dentro del proyecto, la ruta relativa (`.venv\\Scripts\\python.exe` en Windows, `.venv/bin/python` en Linux o Mac);
    fuera, la ruta completa, entre comillas si tiene espacios. No resuelve enlaces: en Linux el `python` del `.venv` es
    un enlace al del sistema y resolverlo se saltaría el `.venv` (el del sistema no tiene los paquetes)."""
    if not sys.executable:
        return "python"
    exe = Path(sys.executable).absolute()
    try:
        texto = str(exe.relative_to(_RAIZ))
    except ValueError:
        texto = str(exe)
    return f'"{texto}"' if " " in texto else texto
