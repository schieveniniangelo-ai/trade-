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

# El Python más viejo que aceptan todos los paquetes de requirements.lock (numpy 2.5.4 pide 3.12).
PYTHON_MINIMO = (3, 12)

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


ESCALONES_MAX_DIAS = 30   # arreglo 195 (R96): las tablas de escalones se revisan una vez al mes (PROPUESTAS.md, N5)


def aviso_escalones(reg: Reglamento, ahora=None, archivo: Path | None = None) -> str:
    """Arreglo 195 (R96): el renglón de doctor sobre escalones.json (tablas de escalones de Futuros F1, copiadas a mano
    de la página pública de Binance). ⚠️ si su `fecha` tiene más de ESCALONES_MAX_DIAS días (Binance las cambia) o no se
    puede leer; si no, ℹ️ con cuántos días tiene. Solo avisa: no cuenta como ❌ ni cambia nada."""
    import json
    from datetime import date, datetime, timezone
    from zoneinfo import ZoneInfo

    from .futuros import liquidacion as LQ
    archivo = archivo or LQ.ARCHIVO_ESCALONES
    ahora = ahora or datetime.now(timezone.utc)
    hoy = ahora.astimezone(ZoneInfo(str(reg.get("zona_horaria", "America/Mexico_City")))).date()
    try:
        fecha = date.fromisoformat(str(json.loads(archivo.read_text(encoding="utf-8"))["fecha"]))
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return (f"⚠️ No pude leer la fecha de {archivo.name} (tablas de escalones de Futuros F1)\n     → Revisa el "
                f"archivo: sin su fecha no se sabe si las tablas siguen al día.")
    dias = (hoy - fecha).days
    if dias > ESCALONES_MAX_DIAS:
        return (f"⚠️ {archivo.name} (tablas de escalones de Futuros F1) tiene {dias} días sin actualizarse (fecha "
                f"{fecha.isoformat()}; máximo {ESCALONES_MAX_DIAS})\n     → Vuelve a copiar las tablas de la página pública "
                f"Leverage & Margin de Binance, revisa cada cum y pon la fecha nueva (PROPUESTAS.md, sección N5). Binance "
                f"las cambia.")
    return f"ℹ️ {archivo.name} (tablas de escalones de Futuros F1): actualizado hace {dias} días ({fecha.isoformat()})"


# Arreglo 201: control de cambios del reglamento. La ronda de papel guarda la versión y las cifras del reglamento con que
# corrió; doctor las compara con el reglamento de hoy.
DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
# Cifras donde un número MÁS BAJO es MENOS riesgo (riesgo por operación, calor, exposición, topes, caída, posiciones,
# apalancamiento y margen de Futuros, cubeta de memes). Se buscan bajo riesgo.* y carteras.*.
CLAVES_RIESGO = ("riesgo_por", "calor_total", "exposicion_max", "cubeta_memes", "apalancamiento_max", "margen_total_max",
                 "posiciones_max", "tope_", "caida_max")


def archivo_reglamento_ronda(reg: Reglamento) -> Path:
    return AR.carpeta_datos(reg) / "papel" / "reglamento_ultima_ronda.json"


def _plano(d, prefijo: str = "") -> dict:
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_plano(v, f"{prefijo}{k}."))
    else:
        out[prefijo[:-1]] = d
    return out


def guardar_reglamento_de_la_ronda(reg: Reglamento, ahora=None) -> None:
    """Arreglo 201: lo llama la ronda de papel al terminar. Guarda la versión y todas las cifras del reglamento con que
    corrió (datos/papel/reglamento_ultima_ronda.json). No decide nada."""
    from datetime import datetime, timezone
    ahora = ahora or datetime.now(timezone.utc)
    AR.escribir_json_seguro(archivo_reglamento_ronda(reg), {"version": reg.version, "hora_utc": ahora.isoformat(
        timespec="seconds"), "cifras": _plano(reg.datos)})


def _solo_baja_el_riesgo(antes: dict, hoy: dict) -> bool:
    """¿Todo lo que cambió (sin contar `version`) es una cifra de riesgo que bajó o quedó igual?"""
    claves = (set(antes) | set(hoy)) - {"version"}
    for k in claves:
        a, h = antes.get(k), hoy.get(k)
        if a == h:
            continue
        es_riesgo = k.split(".")[0] in ("riesgo", "carteras") and any(t in k for t in CLAVES_RIESGO)
        numeros = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (a, h))
        if not (es_riesgo and numeros and h <= a):
            return False
    return True


def aviso_reglamento_cambiado(reg: Reglamento, ahora=None) -> str:
    """Arreglo 201: compara la versión del reglamento de hoy con la de la última ronda de papel. Si cambió y hoy no es
    `control_cambios.dia_ventana` (hora de CDMX), ⚠️ «reglamento cambiado fuera de la ventana», salvo que el cambio solo
    baje el riesgo. "" si no hay nada que decir. Solo avisa: no bloquea nada ni cuenta como ❌."""
    import json
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    arch = archivo_reglamento_ronda(reg)
    if not arch.exists():
        return ""
    try:
        ultima = json.loads(arch.read_text(encoding="utf-8"))
        version, cifras = str(ultima["version"]), ultima["cifras"]
        if not isinstance(cifras, dict):
            raise TypeError("cifras")
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return (f"⚠️ No pude leer {arch.name} (el reglamento de la última ronda)\n     → No se sabe si el reglamento "
                f"cambió desde la última ronda; la próxima ronda lo vuelve a escribir.")
    if version == reg.version:
        return ""
    ahora = ahora or datetime.now(timezone.utc)
    hoy = DIAS_SEMANA[ahora.astimezone(ZoneInfo(str(reg.get("zona_horaria", "America/Mexico_City")))).weekday()]
    ventana = str(reg.get("control_cambios.dia_ventana", "domingo")).strip().lower()
    if hoy == ventana:
        return f"ℹ️ Reglamento {version} → {reg.version} desde la última ronda (hoy es {ventana}: día de la ventana)"
    if _solo_baja_el_riesgo(cifras, _plano(reg.datos)):
        return (f"ℹ️ Reglamento {version} → {reg.version} desde la última ronda, fuera de la ventana ({ventana}), pero "
                f"el cambio solo baja el riesgo")
    return (f"⚠️ reglamento cambiado fuera de la ventana: {version} → {reg.version} desde la última ronda y hoy es {hoy} "
            f"(la ventana es el {ventana})\n     → Revisa CAMBIOS.md: entre semana solo se aceptan cambios que bajen el "
            f"riesgo. Avisa a Ángelo (no bloquea nada).")


def _renglones_real(reg: Reglamento, imprimir) -> None:
    """Arreglo 133: renglones SOLO informativos del dinero real (no cuentan como ❌ ni bloquean nada)."""
    from datetime import datetime, timezone

    from . import real as RE
    from . import ronda_real as RR
    if RE.real_activo(reg):                       # arreglo 186: el interruptor del real
        imprimir("ℹ️ Real: interruptor real.activo: true (el dinero real está encendido)")
    else:
        imprimir("ℹ️ Real: interruptor real.activo: false → el dinero real está APAGADO: ninguna compra real se aprueba "
                 "ni se anota; lo que protege una posición que ya existe (stops, cierres y ventas urgentes) sigue "
                 "(arreglo 196). Encenderlo lo decide Ángelo.")
    estado_m0 = reg.estrategias.get("M0", {}).get("estado")
    if estado_m0 in RR.ESTADOS_VIVOS:
        imprimir(f"ℹ️ Real: M0 está en {estado_m0} (el real necesita VIVA_MINI o VIVA)")
    else:                                         # arreglo 185: DECISIÓN DE ÁNGELO del 22 nov 2026
        imprimir(f"ℹ️ Real: M0 está en {estado_m0}: la ronda real NO corre (el real necesita VIVA_MINI o VIVA). M0 "
                 f"regresó a PAPEL el 22 nov 2026 porque no pasó sus compuertas (DECISIÓN DE ÁNGELO); el papel sigue "
                 f"igual. Volver a real lo decide Ángelo en reglamento.yaml.")
    foto, por_que = RE.leer_foto(reg)
    if foto is not None and not por_que:
        edad = (datetime.now(timezone.utc) - datetime.fromisoformat(foto["hora_utc"])).total_seconds() / 60
        imprimir(f"ℹ️ Real: foto de saldo de hace {edad:.0f} min")
    else:
        imprimir(f"ℹ️ Real: {por_que}")
    ok, msg = RE.conciliacion_ok(reg)
    imprimir("ℹ️ Real: conciliación real " + ("ok" if ok else f"NO ok ({msg})"))
    for r in renglones_posiciones_y_pendientes(reg):   # arreglo 200: solo informa (no cuenta como ❌)
        imprimir(r)


def renglones_posiciones_y_pendientes(reg: Reglamento) -> list[str]:
    """Arreglo 200: lo que doctor dice del estado real, sin red: las posiciones reales abiertas (símbolo, cantidad y
    estado del stop) y los pendientes urgentes (COMPRA_ENVIADA sin resultado, la revisión justo después de una compra y
    el bloqueo de compras). Solo informa: con el real apagado también, porque una posición que ya existe sigue en
    Binance."""
    from . import real as RE
    try:
        est = RE.cargar_estado(reg)
    except RE.EstadoRealDanado as e:
        return [f"⚠️ Real: no pude leer el estado real para ver posiciones y pendientes ({e})"]
    pos = [f"{p.get('simbolo')} {format(float(p.get('cantidad_neta') or 0.0), 'g')} (stop {p.get('estado_stop')})"
           for p in est["posiciones"]]
    out = ["ℹ️ Real: posiciones abiertas: " + ("; ".join(pos) if pos else "ninguna")]
    pend = []
    try:
        enviadas = [str(x.get("boleto_id")) for x in RE.compras_sin_anotar(reg)]
    except OSError as e:
        enviadas = [f"no pude leer llenados.jsonl ({type(e).__name__})"]
    if enviadas:
        pend.append("COMPRA_ENVIADA sin resultado (boleto " + ", ".join(enviadas) + ")")
    rev = est.get(RE.REVISION)
    if rev:
        pend.append("REVISION después de la compra del boleto "
                    + str(rev.get("boleto", "?") if isinstance(rev, dict) else "?") + " sin hacer")
    bloqueo = est.get("bloqueo_compras")
    if bloqueo:
        pend.append("bloqueo_compras: " + str(bloqueo.get("motivo", "sin motivo") if isinstance(bloqueo, dict) else bloqueo))
    out.append("⚠️ Real: pendientes urgentes: " + "; ".join(pend) + " → avisa a THE BOSS" if pend else
               "ℹ️ Real: pendientes urgentes: ninguno")
    return out


def revisar(reg: Reglamento, imprimir=print) -> int:
    malos = 0

    def linea(ok: bool, texto: str, que_hacer: str = "") -> None:
        nonlocal malos
        imprimir(("✅ " if ok else "❌ ") + texto + ("" if ok or not que_hacer else f"\n     → {que_hacer}"))
        malos += 0 if ok else 1

    v = sys.version_info
    linea(v >= PYTHON_MINIMO, f"Python {v.major}.{v.minor}.{v.micro}",
          f"Instala Python {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} o más nuevo.")
    for paquete in ("pandas", "numpy", "yaml", "requests"):
        try:
            m = importlib.import_module(paquete)
            linea(True, f"Paquete {paquete} {getattr(m, '__version__', '')}")
        except ImportError:
            linea(False, f"Falta el paquete {paquete}", f"Corre: {python_actual()} -m pip install -r requirements.lock")
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
    from . import papel as P
    for aviso in P.avisos_capital_viejo(reg):          # arreglo 168: solo avisa (no cuenta como ❌ ni cambia nada)
        imprimir(aviso)
    _renglones_real(reg, imprimir)
    imprimir(aviso_escalones(reg))                     # arreglo 195: solo avisa (no cuenta como ❌)
    if aviso := aviso_reglamento_cambiado(reg):        # arreglo 201: solo avisa (no cuenta como ❌)
        imprimir(aviso)
    sin_llaves = not any(Path(reg.ruta.parent if reg.ruta else ".").glob("*.key"))
    linea(sin_llaves, "Sin llaves de Binance en la carpeta (correcto)", "Borra cualquier llave: el sistema NO las usa.")
    imprimir("👍 Todo listo." if malos == 0 else f"Hay {malos} renglón(es) con ❌. Revisa lo que dice cada uno.")
    return 0 if malos == 0 else 1
