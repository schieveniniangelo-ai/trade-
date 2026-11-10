"""Reportes para Ángelo: cortos, sin palabras técnicas y con 👍 cuando no necesita hacer nada."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import archivos as AR
from . import papel as P
from .reglamento import Reglamento


def _ultimo(est: dict) -> float:
    return list(est["curva"].values())[-1] if est["curva"] else float(est["capital_inicial"])


def _refs(reg: Reglamento) -> dict:
    arch = P.ruta_papel(reg) / "referencias.json"
    return AR.leer_json_seguro(arch) if (arch.exists() or arch.with_name(arch.name + ".bak").exists()) else {}


def hoy_local(reg: Reglamento, ahora: datetime | None = None) -> datetime:
    """La fecha y hora de Ángelo (zona horaria del reglamento, CDMX), sin importar en qué zona esté la computadora."""
    from zoneinfo import ZoneInfo
    return (ahora or datetime.now(timezone.utc)).astimezone(ZoneInfo(str(reg.get("zona_horaria", "America/Mexico_City"))))


def diario(reg: Reglamento, ahora: datetime | None = None) -> str:
    """10 líneas o menos."""
    lineas = []
    necesita = False
    for n in P.CARTERAS:
        est = P.cargar_estado(reg, n, "")
        cap0 = float(est["capital_inicial"])
        hoy = _ultimo(est)
        dia = est.get("ultimo_dia") or "—"
        lineas.append(f"Cartera {n}: {hoy:.2f} USDT ({(hoy / cap0 - 1) * 100:+.1f} % desde que empezó el papel) · "
                      f"{len(est['posiciones'])} abiertas")
        if est.get("detenido"):
            necesita = True
            lineas.append(f"⚠️ Cartera {n} detenida por caída máxima: necesito tu OK para seguir.")
        ult = est.get("rondas", {}).get(est.get("ultimo_dia") or "", {})
        if ult and not ult.get("opera", True):
            nec = ult.get("capital_necesario")
            lineas.append(f"   Cartera {n} NO opera con el capital actual: sus señales no llegan al mínimo de Binance"
                          + (f" (necesita unos {nec:.0f} USDT)." if nec else "."))
    refs = _refs(reg)
    if refs:
        d, r = sorted(refs.items())[-1]
        if "R0" in r:
            lineas.append(f"Para comparar ({d}): BTC {r['R0']:.2f} · BTC con marea {r['R1']:.2f} · canasta {r['R2']:.2f}")
    cal = AR.calificacion_bots(reg, 1)
    malos = [b for b, c in cal.items() if c["rechazos"] or c["diferencias"]]
    if malos:
        lineas.append(f"Bots con errores hoy: {', '.join(malos)} (el sistema los ignoró y siguió seguro).")
    lineas = [f"Reporte del día {hoy_local(reg, ahora).strftime('%d/%m/%Y')} — todo en PAPEL, sin dinero real."] + lineas[:8]
    lineas.append("👍 No necesito nada de ti." if not necesita else "Necesito tu respuesta.")
    return "\n".join(lineas)


def _pct(x: float) -> str:
    """Porcentaje con uno o dos decimales (0.0, 0.5, 0.07), sin cero negativo."""
    t = f"{round(x, 2) + 0.0:.2f}"
    return t[:-1] if t.endswith("0") else t


def apertura_vs_precio(reg: Reglamento, hace7: str) -> list[str]:
    """Línea(s) de la boleta: cuánto se movió el precio entre la apertura que usa el papel y la hora real de la ronda.
    Lee salida/boletos_AAAA-MM-DD.json desde `hace7`. Un archivo dañado no tumba el reporte: se salta y se avisa."""
    umbral = float(reg.get("reportes.dif_apertura_aviso_pct", 0.3))
    carpeta = AR.carpeta_datos(reg).parent / "salida"
    difs, avisos = [], []
    for arch in sorted(carpeta.glob("boletos_*.json")) if carpeta.is_dir() else []:
        if arch.stem[len("boletos_"):] < hace7:
            continue
        try:
            boletos = AR.leer_json_seguro(arch)
        except (AR.ArchivoDanado, OSError):
            avisos.append(f"⚠️ {arch.name} está dañado: no entró en la cuenta de apertura vs precio.")
            continue
        for b in boletos if isinstance(boletos, list) else []:
            d = b.get("dif_apertura_pct") if isinstance(b, dict) else None
            if isinstance(d, (int, float)) and not isinstance(d, bool) and d == d and abs(d) != float("inf"):
                difs.append(float(d))
    if not difs:
        return ["Apertura vs precio al correr: sin datos todavía."] + avisos
    lejos = sum(1 for d in difs if abs(d) > umbral)
    return [f"Apertura vs precio al correr (últimos 7 días): promedio {_pct(sum(difs) / len(difs))} %, "
            f"peor {_pct(max(abs(d) for d in difs))} %, {lejos} de {len(difs)} boletos con más de {umbral:g} %."] + avisos


def semanal(reg: Reglamento, ahora: datetime | None = None) -> str:
    """Boleta del domingo: cada cartera contra R0 y R1, saltadas por capital y costo de Grok Bot contra lo ganado."""
    hace7 = ((ahora or datetime.now(timezone.utc)) - timedelta(days=7)).strftime("%Y-%m-%d")
    refs = _refs(reg)
    dias = sorted(refs)
    r_ini = next((refs[d] for d in dias if d >= hace7), None)
    r_fin = refs[dias[-1]] if dias else None
    tc = 18.0
    tca = AR.carpeta_datos(reg) / "tipo_cambio.json"
    if tca.exists() or tca.with_name(tca.name + ".bak").exists():
        datos_tc = AR.leer_json_seguro(tca)   # dañado y sin copia → ArchivoDanado: el reporte dice "❌ …" y regresa 1
        try:
            tc = float(datos_tc["mxn_por_usdt"])
        except (KeyError, ValueError, TypeError):
            pass
    lineas = ["BOLETA SEMANAL (papel, sin dinero real)"]
    for n in P.CARTERAS:
        est = P.cargar_estado(reg, n, "")
        curva = est["curva"]
        ini = next((v for d, v in sorted(curva.items()) if d >= hace7), float(est["capital_inicial"]))
        fin = _ultimo(est)
        ops = [c for c in est["cerradas"] if str(c["t_salida"])[:10] >= hace7]
        salt = [s for s in est["saltadas_capital"] if s["dia"] >= hace7]
        lineas.append(f"Cartera {n}: {fin - ini:+.2f} USDT en la semana ({(fin / ini - 1) * 100 if ini else 0:+.1f} %), "
                      f"{len(ops)} operaciones cerradas, {len(salt)} señales saltadas por capital")
        if salt:
            nec = sorted(x["capital_necesario"] for x in salt if x.get("capital_necesario"))
            if nec:
                lineas.append(f"   Para no saltarlas habrían hecho falta unos {nec[len(nec) // 2]:.0f} USDT.")
    if r_ini and r_fin and "R0" in r_ini and "R0" in r_fin:
        lineas.append(f"Referencias en la semana: BTC {(r_fin['R0'] / r_ini['R0'] - 1) * 100:+.1f} % · "
                      f"BTC con marea {(r_fin['R1'] / r_ini['R1'] - 1) * 100:+.1f} %")
    costo_semana = float(reg.get("plan_grok.costo_mxn_mes", 300)) / 30 * 7
    gan = sum(_ultimo(P.cargar_estado(reg, n, "")) - next((v for d, v in sorted(P.cargar_estado(reg, n, "")["curva"].items())
                                                          if d >= hace7), _ultimo(P.cargar_estado(reg, n, "")))
              for n in ("A",))
    lineas.append(f"Grok Bot cuesta unos {costo_semana:.0f} pesos por semana; la Cartera A ganó en papel unos "
                  f"{gan * tc:+.1f} pesos (tipo de cambio {tc:.2f}).")
    lineas += apertura_vs_precio(reg, hace7)
    lineas.append("Recuerda: esto es papel. Para dinero real faltan las compuertas, 6 semanas y 10 operaciones de papel.")
    lineas.append("👍 No necesito nada de ti.")
    return "\n".join(lineas)
