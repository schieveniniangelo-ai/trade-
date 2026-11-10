"""Respaldo del estado de papel, los boletos y los archivos de los bots (comando `respaldo`).

Crea respaldo-AAAA-MM-DD-HHMM.tar.gz (hora UTC) en la carpeta `respaldo.carpeta` del reglamento (por defecto
~/respaldos-sobreviviente, FUERA del proyecto). Solo LEE los archivos de origen: no borra ni cambia nada de ellos,
no usa red ni llaves y no sigue enlaces simbólicos. Restaurar se hace a mano (ver INSTALACION.md)."""
from __future__ import annotations

import io
import json
import os
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from . import archivos as AR
from .reglamento import Reglamento

PATRON = re.compile(r"^respaldo-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})\.tar\.gz$")
CARPETAS = (("datos", "papel"), ("datos", "estela"), ("datos", "bots"), ("salida",))
SUELTOS = ("vetos.json", "eventos.json", "exclusiones.json", "memes.json")
NO_SE_RESPALDA = (".lock", ".tmp")     # candados y archivos a medias: no son datos


def carpeta_respaldos(reg: Reglamento) -> Path:
    c = Path(str(reg.get("respaldo.carpeta", "~/respaldos-sobreviviente"))).expanduser()
    if not c.is_absolute() and reg.ruta is not None:
        c = reg.ruta.parent / c
    return c


def fecha_de_respaldo(nombre: str) -> datetime | None:
    """La fecha y hora (UTC) que dice el nombre de un respaldo, o None si el nombre no es de un respaldo."""
    m = PATRON.match(nombre)
    if not m:
        return None
    try:
        return datetime(*(int(x) for x in m.groups()), tzinfo=timezone.utc)
    except ValueError:
        return None


def respaldos_existentes(reg: Reglamento) -> list[tuple[datetime, Path]]:
    """Respaldos que hay en la carpeta (solo archivos normales con el nombre de respaldo), del más viejo al más nuevo."""
    carpeta = carpeta_respaldos(reg)
    out = []
    try:
        for p in carpeta.iterdir():
            t = fecha_de_respaldo(p.name)
            if t is not None and p.is_file() and not p.is_symlink():
                out.append((t, p))
    except OSError:
        return []
    return sorted(out)


def _origenes(reg: Reglamento) -> list[tuple[str, Path]]:
    """(nombre dentro del respaldo, archivo de origen). Nunca sigue enlaces simbólicos."""
    datos = AR.carpeta_datos(reg)
    raiz = datos.parent
    bases = {"datos": datos, "salida": raiz / "salida"}
    out: list[tuple[str, Path]] = []
    for partes in CARPETAS:
        base = bases[partes[0]].joinpath(*partes[1:])
        if base.is_symlink() or not base.is_dir():
            continue
        for carpeta, subcarpetas, archivos in os.walk(base, followlinks=False):
            subcarpetas[:] = sorted(d for d in subcarpetas if not (Path(carpeta) / d).is_symlink())
            for a in sorted(archivos):
                p = Path(carpeta) / a
                if p.is_symlink() or not p.is_file() or p.name.endswith(NO_SE_RESPALDA):
                    continue
                out.append(("/".join(partes) + "/" + p.relative_to(base).as_posix(), p))
    for a in SUELTOS:
        p = datos / a
        if p.is_file() and not p.is_symlink():
            out.append((f"datos/{a}", p))
    if reg.ruta is not None and Path(reg.ruta).is_file() and not Path(reg.ruta).is_symlink():
        out.append(("reglamento.yaml", Path(reg.ruta)))
    return out


def _json_valido(crudo: bytes) -> bool:
    try:
        json.loads(crudo.decode("utf-8"))
        return True
    except (ValueError, RecursionError):
        return False


def respaldar(reg: Reglamento, ahora: datetime | None = None, avisar=print) -> int:
    """Hace el respaldo. Regresa 0 si quedó guardado y verificado; 1 si no (y no deja archivos a medias)."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    carpeta = carpeta_respaldos(reg)
    final = carpeta / f"respaldo-{ahora:%Y-%m-%d-%H%M}.tar.gz"
    tmp = final.with_name(final.name + ".tmp")
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        contenido: dict[str, bytes] = {}
        danados = []
        for nombre, origen in _origenes(reg):
            crudo = origen.read_bytes()                     # se lee una sola vez: lo que se guarda es lo que se verificó
            contenido[nombre] = crudo
            if nombre.endswith(".json") and not _json_valido(crudo):
                danados.append(nombre)
        with tarfile.open(tmp, "w:gz") as tar:
            for nombre, crudo in contenido.items():
                info = tarfile.TarInfo(nombre)
                info.size = len(crudo)
                info.mtime = int(ahora.timestamp())
                tar.addfile(info, io.BytesIO(crudo))
        # Verificación: se vuelve a abrir y se compara archivo por archivo antes de darle su nombre definitivo
        with tarfile.open(tmp, "r:gz") as tar:
            adentro = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
        if set(adentro) != set(contenido):
            raise OSError("al verificar faltan archivos dentro del respaldo")
        for nombre, crudo in contenido.items():
            if adentro[nombre] != crudo:
                raise OSError(f"al verificar, {nombre} no quedó igual que el original")
            if nombre.endswith(".json") and nombre not in danados and not _json_valido(adentro[nombre]):
                raise OSError(f"al verificar, {nombre} no se puede leer")
        os.replace(tmp, final)
    except (OSError, tarfile.TarError) as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        motivo = f"{type(e).__name__}: {e}"[:160]
        avisar(f"❌ No pude guardar el respaldo en {carpeta}: {motivo}. Los respaldos anteriores no se tocaron.")
        AR.registrar_tarea(reg, "CONTADOR", "respaldo", False, motivo)
        return 1
    for nombre in danados:
        avisar(f"⚠️ {nombre} estaba dañado; se respaldó tal cual")
    # Limpieza: solo respaldos viejos con el nombre de respaldo, en esta carpeta
    guardar = max(1, int(reg.get("respaldo.guardar_ultimos", 14)))
    borrados = 0
    for _, viejo in respaldos_existentes(reg)[:-guardar]:
        try:
            viejo.unlink()
            borrados += 1
        except OSError:
            avisar(f"⚠️ No pude borrar el respaldo viejo {viejo.name}; bórralo a mano si estorba.")
    kb = final.stat().st_size / 1024
    avisar(f"👍 Respaldo guardado: {final} ({len(contenido)} archivos, {kb:.0f} KB). "
           f"Se conservan los últimos {guardar}" + (f"; borré {borrados} viejo(s)." if borrados else "."))
    AR.registrar_tarea(reg, "CONTADOR", "respaldo", True,
                       f"{final.name}; {len(contenido)} archivos" + (f"; {len(danados)} dañado(s)" if danados else ""))
    return 0


def aviso_sin_respaldo(reg: Reglamento, ahora: datetime | None = None) -> list[str]:
    """Aviso ℹ️ si no hay ningún respaldo o el más nuevo tiene más de `respaldo.max_horas_sin_respaldo` horas.
    Solo informa: no activa MODO SEGURO ni quita el 👍."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    max_h = float(reg.get("respaldo.max_horas_sin_respaldo", 48))
    hay = respaldos_existentes(reg)
    if not hay:
        return ["ℹ️ Sin respaldo de datos todavía: corre 'python -m sobreviviente respaldo'"]
    ultimo = hay[-1][0]
    if (ahora - ultimo).total_seconds() / 3600 > max_h:
        return [f"ℹ️ Sin respaldo de datos desde {ultimo:%Y-%m-%d}: corre 'python -m sobreviviente respaldo'"]
    return []
