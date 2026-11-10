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
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from .reglamento import Reglamento

log = logging.getLogger("sobreviviente.archivos")


# ---------------------------------------------------------------------------
# Escritura y lectura seguras de archivos de estado (JSON)
# ---------------------------------------------------------------------------

class ArchivoDanado(Exception):
    """Un archivo de estado está dañado y su copia anterior (.bak) tampoco sirve. El mensaje explica qué hacer."""


_AVISOS: list[str] = []


def tomar_avisos() -> list[str]:
    """Avisos pendientes de lecturas que usaron la copia anterior (se vacía al tomarlos)."""
    out = list(_AVISOS)
    _AVISOS.clear()
    return out


def _bak(ruta: Path) -> Path:
    return ruta.with_name(ruta.name + ".bak")


def _es_json_valido(ruta: Path) -> bool:
    try:
        json.loads(ruta.read_text(encoding="utf-8"))
        return True
    except (OSError, ValueError):
        return False


def escribir_json_seguro(ruta: str | Path, objeto: Any, indent: int | None = 1) -> None:
    """Escribe un JSON sin riesgo de dejarlo a medias: temporal en la misma carpeta → flush + fsync →
    la versión anterior (si está sana) se guarda como <nombre>.bak → el temporal reemplaza al archivo."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(objeto, ensure_ascii=False, indent=indent, default=str)
    fd, tmp = tempfile.mkstemp(prefix=ruta.name + ".", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        if ruta.exists() and _es_json_valido(ruta):  # nunca se pisa una copia buena con una dañada
            fd_b, tmp_b = tempfile.mkstemp(prefix=ruta.name + ".", suffix=".baktmp", dir=ruta.parent)
            os.close(fd_b)
            shutil.copy2(ruta, tmp_b)
            os.replace(tmp_b, _bak(ruta))
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def leer_json_seguro(ruta: str | Path) -> Any:
    """Lee un JSON. Si está dañado (o falta pero quedó su .bak), usa la copia anterior y avisa en español.
    Si tampoco sirve, lanza ArchivoDanado con un mensaje claro (la ronda lo reporta como "NO corrió")."""
    ruta = Path(ruta)
    bak = _bak(ruta)
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    elif not bak.exists():
        raise FileNotFoundError(f"No existe {ruta}")
    if bak.exists():
        try:
            objeto = json.loads(bak.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            objeto = None
        if objeto is not None:
            aviso = f"se usó la copia anterior de {ruta.name} (el archivo estaba dañado o faltaba)"
            log.warning(aviso)
            _AVISOS.append(aviso)
            return objeto
    raise ArchivoDanado(f"El archivo {ruta.name} está dañado y no hay una copia anterior que sirva. "
                        f"Revisa {ruta} (o restáuralo) antes de volver a correr la ronda.")

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


def validar_vetos(d: Any, reg: Reglamento | None = None, ahora: datetime | None = None) -> list[str]:
    """Un veto solo puede decir NO, por poco tiempo y con una razón corta (límites en `reglamento.yaml → vetos`)."""
    max_h = float(reg.get("vetos.max_horas", 72)) if reg is not None else 72.0
    max_c = int(reg.get("vetos.razon_max_caracteres", 200)) if reg is not None else 200
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    e = []
    if not isinstance(d, dict):
        return ["no es un objeto JSON {…}"]
    if not isinstance(d.get("vetos"), list):
        return ["falta la lista 'vetos'"]
    for i, x in enumerate(d["vetos"]):
        if not isinstance(x, dict):
            e.append(f"veto #{i + 1} no es un objeto — pide a CENTINELA que lo corrija")
            continue
        # Cada error dice de qué veto se trata (moneda y vence) y qué hacer
        et = f"veto #{i + 1} ({str(x.get('simbolo', '?'))[:20]}, vence {str(x.get('vence', '?'))[:30]})"
        ev: list[str] = []
        if not _simbolo_ok(x.get("simbolo"), permitir_global=True):
            ev.append(f"{et}: el símbolo '{x.get('simbolo')}' no es válido (ejemplo: SOLUSDT o GLOBAL)")
        if not str(x.get("razon", "")).strip():
            ev.append(f"{et}: falta la razón")
        if not _fecha_ok(x.get("vence")):
            ev.append(f"{et}: 'vence' debe ser fecha y hora (ejemplo: 2026-11-12T18:00:00-06:00)")
        else:
            vence = datetime.fromisoformat(str(x["vence"]).replace("Z", "+00:00"))
            if vence.tzinfo is None:
                vence = vence.replace(tzinfo=ZoneInfo("America/Mexico_City"))
            if vence - ahora > timedelta(hours=max_h):
                ev.append(f"{et}: vence en más de {max_h:.0f} horas (máximo del reglamento); "
                         f"pon una fecha más cercana y renuévalo si hace falta")
        for campo in ("razon", "nota"):
            if x.get(campo) is None:
                continue
            t = str(x[campo])
            if len(t) > max_c:
                ev.append(f"{et}: la {campo} tiene {len(t)} caracteres (máximo {max_c})")
            if any(c in t for c in (chr(10), chr(13))):  # saltos de línea
                ev.append(f"{et}: la {campo} no puede tener saltos de línea")
            if "http" in t.lower():
                ev.append(f"{et}: la {campo} no puede tener enlaces (http)")
        if any(k in x for k in ("comprar", "entrar", "agregar", "cantidad", "tamano", "riesgo")):
            ev.append(f"{et}: un veto solo puede decir NO; no puede pedir comprar ni cambiar tamaños")
        e.extend(f"{m} — pide a CENTINELA que lo corrija" for m in ev)
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
    if nombre == "vetos.json":
        errores = validar_vetos(d, reg)
    else:
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
    """Anota una tarea de un bot en datos/bots/registro.jsonl (para `estado --bots`).

    Anotar nunca tumba el comando que la llama: si el archivo no se puede escribir, se avisa con ⚠️ y se sigue."""
    arch = carpeta_datos(reg) / "bots" / "registro.jsonl"
    fila = {"cuando": (ahora or datetime.now().astimezone()).isoformat(timespec="seconds"), "bot": bot, "tarea": tarea,
            "ok": bool(ok), "a_tiempo": bool(a_tiempo), "diferencias": int(diferencias), "detalle": detalle}
    try:
        arch.parent.mkdir(parents=True, exist_ok=True)
        with open(arch, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"⚠️ No pude anotar la tarea '{tarea}' de {bot} en registro.jsonl ({type(e).__name__}); "
              f"la calificación de los bots no la contará.")


def leer_registro(reg: Reglamento) -> list[dict[str, Any]]:
    arch = carpeta_datos(reg) / "bots" / "registro.jsonl"
    if not arch.exists():
        return []
    filas = []
    try:
        crudo = arch.read_bytes()
    except OSError:
        return []
    for renglon in crudo.split(b"\n"):   # tolerante: un renglón roto, con bytes raros o que no es un objeto se salta
        try:
            fila = json.loads(renglon.decode("utf-8", errors="replace"))
        except (ValueError, RecursionError):
            continue
        if isinstance(fila, dict):
            filas.append(fila)
    return filas


def calificacion_bots(reg: Reglamento, dias: int = 7) -> dict[str, dict[str, Any]]:
    """Por bot: tareas cumplidas a tiempo, archivos rechazados y diferencias entre boleto y llenado."""
    from datetime import timedelta
    limite = datetime.now().astimezone() - timedelta(days=dias)
    out: dict[str, dict[str, Any]] = {}
    for f in leer_registro(reg):
        try:
            cuando = datetime.fromisoformat(f["cuando"])
        except (KeyError, ValueError, TypeError):
            continue
        if cuando.tzinfo is None:   # fecha sin zona (escrita a mano): se toma como hora de esta computadora
            cuando = cuando.astimezone()
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
