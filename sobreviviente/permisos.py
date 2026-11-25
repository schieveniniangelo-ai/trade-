"""Arreglo 206: permisos de la llave de Binance que usa EJECUTOR (registrar-permisos). SOLO lee un archivo.

EJECUTOR guarda tal cual la respuesta de apiRestrictions de Binance (la consulta él por el conector de Binance; el
programa nunca tiene llaves ni llama a esa ruta) y corre `registrar-permisos --archivo <json>`. Aquí se
revisa que la llave solo pueda operar Spot: sin retiros, Futuros, Margen, transferencias internas o universales ni
opciones. Con `ipRestrict` false solo se avisa (se recomienda limitarla por IP). El resultado se guarda en
datos/real/permisos.json y doctor lo muestra con su fecha. No cambia la ronda real ni las compras (DECISIÓN DE ÁNGELO
si algún día debe exigirse).
"""
# La ruta de Binance es GET /sapi/v1/account/apiRestrictions; documentación oficial:
# https://developers.binance.com/docs/wallet/account/api-key-permission
# (va en comentario: el código del paquete no nombra rutas firmadas; ver tests/test_arreglo140_puerta_real.py)
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import archivos as AR
from .reglamento import Reglamento

ARCHIVO = "permisos.json"
DEBEN_SER_FALSE = ("enableWithdrawals", "enableFutures", "enableMargin", "enableInternalTransfer",
                   "permitsUniversalTransfer", "enableVanillaOptions")
DEBE_SER_TRUE = "enableSpotAndMarginTrading"
RECOMENDADO_TRUE = "ipRestrict"


def ruta(reg: Reglamento) -> Path:
    return AR.carpeta_datos(reg) / "real" / ARCHIVO


def validar(datos: Any) -> tuple[list[str], list[str]]:
    """(problemas, avisos). Un campo que falta o que no es true/false de verdad es un problema."""
    if not isinstance(datos, dict):
        return ["el archivo no es un objeto JSON con los permisos de la llave"], []
    problemas, avisos = [], []
    for campo in DEBEN_SER_FALSE:
        v = datos.get(campo)
        if not isinstance(v, bool):
            problemas.append(f"falta {campo} (o no es true/false)")
        elif v:
            problemas.append(f"{campo} está en true: debe ser false")
    v = datos.get(DEBE_SER_TRUE)
    if not isinstance(v, bool):
        problemas.append(f"falta {DEBE_SER_TRUE} (o no es true/false)")
    elif not v:
        problemas.append(f"{DEBE_SER_TRUE} está en false: debe ser true (la llave tiene que poder operar Spot)")
    if datos.get(RECOMENDADO_TRUE) is not True:
        avisos.append(f"{RECOMENDADO_TRUE} no está en true: se recomienda limitar la llave a la IP de la computadora "
                      f"(solo aviso)")
    return problemas, avisos


def registrar(reg: Reglamento, archivo: str | Path, ahora: datetime | None = None) -> dict[str, Any]:
    """Lee el JSON guardado, lo valida y guarda el resultado en datos/real/permisos.json (también si no pasa)."""
    archivo = Path(archivo)
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        datos, problemas, avisos = None, [f"no pude leer {archivo.name} como JSON ({type(e).__name__})"], []
    else:
        problemas, avisos = validar(datos)
    campos = {k: datos.get(k) for k in (*DEBEN_SER_FALSE, DEBE_SER_TRUE, RECOMENDADO_TRUE)} \
        if isinstance(datos, dict) else {}
    res = {"ok": not problemas, "problemas": problemas, "avisos": avisos, "archivo": archivo.name, "campos": campos,
           "fecha_utc": (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")}
    AR.escribir_json_seguro(ruta(reg), res)
    return res


def renglon_doctor(reg: Reglamento) -> tuple[bool | None, str]:
    """(ok, texto) para doctor. ok None = sin registrar (solo informa, no cuenta como ❌)."""
    arch = ruta(reg)
    if not arch.exists():
        return None, ("ℹ️ Permisos de la llave de Binance: sin registrar (EJECUTOR guarda la respuesta de "
                      "apiRestrictions y corre registrar-permisos --archivo <json>)")
    try:
        d = AR.leer_json_seguro(arch)
        fecha = str(d["fecha_utc"])[:10]
        ok = d["ok"] is True
    except (AR.ArchivoDanado, OSError, KeyError, TypeError):
        return False, "Permisos de la llave de Binance: datos/real/permisos.json no se puede leer"
    if ok:
        extra = f" — ⚠️ {'; '.join(d.get('avisos') or [])}" if d.get("avisos") else ""
        return True, f"Permisos de la llave de Binance: bien (registrados el {fecha}){extra}"
    return False, f"Permisos de la llave de Binance: {'; '.join(d.get('problemas') or [])} (registrados el {fecha})"
