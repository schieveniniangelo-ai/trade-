"""Archivos que escriben los bots, con ESQUEMA VALIDADO.

Regla de oro (MAREA 6.1): cada tarea de bot = un comando + un archivo. Si un archivo viene mal, se ignora,
se explica el error en español y la ronda sigue en MODO SEGURO (sin entradas nuevas si el archivo es
de los que pueden vetar). Los stops ya puestos nunca se tocan por una falla.

| Archivo                     | Lo escribe | Para qué |
|---|---|---|
| datos/exclusiones.json      | RADAR      | monedas que no se operan (deslistado, Monitoreo, hackeo…) |
| datos/vetos.json            | CENTINELA  | vetos temporales por noticias graves (solo puede vetar) |
| datos/eventos.json          | CENTINELA  | calendario de eventos fuertes (Fed, inflación…) |
| datos/estela/AAAA-MM-DD.json| ESTELA     | foto diaria del posicionamiento (la genera el comando `estela --foto`) |
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .reglamento import Reglamento

RAZONES_EXCLUSION = ("MONITOREO", "DESLISTADO", "HACKEO", "SEMILLA_RECHAZADA", "MANTENIMIENTO", "OTRA")
IMPORTANCIAS = ("BAJA", "MEDIA", "ALTA")


def carpeta_datos(reg: Reglamento) -> Path:
    c = Path(reg.get("datos.carpeta", "datos"))
    if not c.is_absolute() and reg.ruta is not None:
        c = reg.ruta.parent / c
    return c


def _fecha_ok(x: Any) -> bool:
    if not isinstance(x, str):
        return False
    try:
        datetime.fromisoformat(x.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _simbolo_ok(s: Any, permitir_global: bool = False) -> bool:
    if not isinstance(s, str) or not s:
        return False
    if permitir_global and s.upper() in ("GLOBAL", "*"):
        return True
    return s.isupper() and s.isalnum() and s.endswith("USDT") and len(s) > 4


def validar_exclusiones(d: Any) -> list[str]:
    e = []
    if not isinstance(d, dict):
        return ["no es un objeto JSON {…}"]
    if not isinstance(d.get("exclusiones"), list):
        return ["falta la lista 'exclusiones'"]
    for i, x in enumerate(d["exclusiones"]):
        if not isinstance(x, dict):
            e.append(f"exclusión #{i + 1} no es un objeto")
            continue
        if not _simbolo_ok(x.get("simbolo")):
            e.append(f"exclusión #{i + 1}: el símbolo '{x.get('simbolo')}' no es válido (ejemplo: SOLUSDT)")
        if str(x.get("razon", "")).upper() not in RAZONES_EXCLUSION:
            e.append(f"exclusión #{i + 1}: la razón '{x.get('razon')}' no existe (usa {', '.join(RAZONES_EXCLUSION)})")
    return e


def validar_vetos(d: Any) -> list[str]:
    e = []
    if not isinstance(d, dict):
        return ["no es un objeto JSON {…}"]
    if not isinstance(d.get("vetos"), list):
        return ["falta la lista 'vetos'"]
    for i, x in enumerate(d["vetos"]):
        if not isinstance(x, dict):
            e.append(f"veto #{i + 1} no es un objeto")
            continue
        if not _simbolo_ok(x.get("simbolo"), permitir_global=True):
            e.append(f"veto #{i + 1}: el símbolo '{x.get('simbolo')}' no es válido (ejemplo: SOLUSDT o GLOBAL)")
        if not str(x.get("razon", "")).strip():
            e.append(f"veto #{i + 1}: falta la razón")
        if not _fecha_ok(x.get("vence")):
            e.append(f"veto #{i + 1}: 'vence' debe ser fecha y hora (ejemplo: 2026-11-12T18:00:00-06:00)")
        if any(k in x for k in ("comprar", "entrar", "agregar", "cantidad", "tamano", "riesgo")):
            e.append(f"veto #{i + 1}: un veto solo puede decir NO; no puede pedir comprar ni cambiar tamaños")
    return e


def validar_eventos(d: Any) -> list[str]:
    e = []
    if not isinstance(d, dict):
        return ["no es un objeto JSON {…}"]
    if not isinstance(d.get("eventos"), list):
        return ["falta la lista 'eventos'"]
    for i, x in enumerate(d["eventos"]):
        if not isinstance(x, dict):
            e.append(f"evento #{i + 1} no es un objeto")
            continue
        if not str(x.get("nombre", "")).strip():
            e.append(f"evento #{i + 1}: falta el nombre")
        if not _fecha_ok(x.get("fecha_hora")):
            e.append(f"evento #{i + 1}: 'fecha_hora' debe ser fecha y hora (ejemplo: 2026-12-10T13:00:00-06:00)")
        if str(x.get("importancia", "")).upper() not in IMPORTANCIAS:
            e.append(f"evento #{i + 1}: la importancia debe ser BAJA, MEDIA o ALTA")
    return e


def validar_estela(d: Any) -> list[str]:
    e = []
    if not isinstance(d, dict):
        return ["no es un objeto JSON {…}"]
    if not _fecha_ok(d.get("fecha")):
        e.append("falta 'fecha' (AAAA-MM-DD)")
    sim = d.get("simbolos")
    if not isinstance(sim, dict) or not sim:
        return e + ["falta 'simbolos' con al menos una moneda"]
    for s, v in sim.items():
        if not _simbolo_ok(s):
            e.append(f"'{s}' no es un símbolo válido")
            continue
        for campo in ("top_posiciones", "masa_cuentas"):
            x = v.get(campo) if isinstance(v, dict) else None
            if not isinstance(x, (int, float)) or not (0 < x < 100):
                e.append(f"{s}: '{campo}' debe ser una razón largo/corto positiva")
    return e


ESQUEMAS = {"exclusiones.json": validar_exclusiones, "vetos.json": validar_vetos, "eventos.json": validar_eventos}
VACIOS = {"exclusiones.json": {"exclusiones": []}, "vetos.json": {"vetos": []}, "eventos.json": {"eventos": []}}


def leer(reg: Reglamento, nombre: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Lee y valida un archivo de bot. Regresa (datos, errores). Si hay errores, datos = None."""
    arch = carpeta_datos(reg) / nombre
    if not arch.exists():
        return None, [f"no existe {arch.name}"]
    try:
        d = json.loads(arch.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        return None, [f"{arch.name} no es JSON válido ({ex.msg if hasattr(ex, 'msg') else ex})"]
    errores = ESQUEMAS[nombre](d) if nombre in ESQUEMAS else []
    return (None, errores) if errores else (d, [])


def leer_todos(reg: Reglamento) -> dict[str, tuple[dict[str, Any] | None, list[str]]]:
    return {n: leer(reg, n) for n in ESQUEMAS}


def leer_estela(reg: Reglamento, fecha: str) -> tuple[dict[str, Any] | None, list[str]]:
    arch = carpeta_datos(reg) / "estela" / f"{fecha}.json"
    if not arch.exists():
        return None, [f"no hay foto de ESTELA del {fecha}"]
    try:
        d = json.loads(arch.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        return None, [f"la foto de ESTELA del {fecha} no es JSON válido ({ex.msg})"]
    err = validar_estela(d)
    return (None, err) if err else (d, [])


# ---------------------------------------------------------------------------
# Registro de tareas de los bots (para la calificación `estado --bots`)
# ---------------------------------------------------------------------------

def registrar_tarea(reg: Reglamento, bot: str, tarea: str, ok: bool, detalle: str = "", a_tiempo: bool = True,
                    diferencias: int = 0, ahora: datetime | None = None) -> None:
    arch = carpeta_datos(reg) / "bots" / "registro.jsonl"
    arch.parent.mkdir(parents=True, exist_ok=True)
    fila = {"cuando": (ahora or datetime.now().astimezone()).isoformat(timespec="seconds"), "bot": bot, "tarea": tarea,
            "ok": bool(ok), "a_tiempo": bool(a_tiempo), "diferencias": int(diferencias), "detalle": detalle}
    with open(arch, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def leer_registro(reg: Reglamento) -> list[dict[str, Any]]:
    arch = carpeta_datos(reg) / "bots" / "registro.jsonl"
    if not arch.exists():
        return []
    filas = []
    for linea in arch.read_text(encoding="utf-8").splitlines():
        try:
            filas.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return filas


def calificacion_bots(reg: Reglamento, dias: int = 7) -> dict[str, dict[str, Any]]:
    """Por bot: tareas cumplidas a tiempo, archivos rechazados y diferencias entre boleto y llenado."""
    from datetime import timedelta
    limite = datetime.now().astimezone() - timedelta(days=dias)
    out: dict[str, dict[str, Any]] = {}
    for f in leer_registro(reg):
        try:
            cuando = datetime.fromisoformat(f["cuando"])
        except (KeyError, ValueError):
            continue
        if cuando < limite:
            continue
        if f.get("detalle") == "ya existía":  # ronda repetida el mismo día: no cuenta como tarea nueva
            continue
        b = out.setdefault(f.get("bot", "?"), {"tareas": 0, "a_tiempo": 0, "rechazos": 0, "diferencias": 0})
        b["tareas"] += 1
        b["a_tiempo"] += int(f.get("a_tiempo", False) and f.get("ok", False))
        b["rechazos"] += int(not f.get("ok", True))
        b["diferencias"] += int(f.get("diferencias", 0))
    return out
