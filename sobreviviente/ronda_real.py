"""La ronda REAL (arreglos 133 a 137): Spot, reglas de la Cartera A, motor M0 (solo BTC), solo largo.

Usa los mismos datos y la misma decisión que la Cartera A de papel, pero con el capital y el efectivo REALES de la foto
de saldo y las posiciones del estado real. Nunca simula llenados ni cambia el efectivo: solo emite boletos que EJECUTOR
pone por el conector. Lo que protege (cierres, ventas de emergencia) nunca se bloquea por MODO SEGURO, pausa, tope,
conciliación o falta de datos; las compras sí (falla cerrada).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import archivos as AR
from . import real as RE
from .reglamento import Reglamento

ESTADOS_VIVOS = ("VIVA_MINI", "VIVA")
DECISION_ANGELO = "2026-11-15"


def archivo_boletos(reg: Reglamento, fecha: str) -> Path:
    return AR.carpeta_datos(reg).parent / "salida" / f"boletos_real_{fecha}.json"


def compuertas_puerta(reg: Reglamento) -> list[str]:
    """Lo que tiene que estar en orden para que la ronda real corra (si falla algo, no corre nada). Cada renglón dice
    qué falta y qué hacer."""
    malos = []
    m0 = reg.estrategias.get("M0", {})
    if m0.get("estado") not in ESTADOS_VIVOS:
        malos.append(f"M0 está en {m0.get('estado')}: el real solo corre con M0 en VIVA_MINI o VIVA "
                     f"→ lo decide Ángelo en reglamento.yaml (arreglo 140).")
    for k, e in reg.estrategias.items():
        if k != "M0" and e.get("estado") != "APAGADA":
            que = "un motor de Futuros" if e.get("mercado") == "FUTUROS" else "un motor"
            malos.append(f"{k} está en {e.get('estado')} ({que}): en real solo corre M0 → déjalo APAGADA.")
    pm = (reg.get("carteras.A.posiciones_max") or {})
    if int(pm.get("futuros", 1)) != 0 or int(pm.get("memes", 1)) != 0:
        malos.append("la Cartera A permite Futuros o memes (posiciones_max): en real están prohibidos → déjalos en 0.")
    if str(reg.get("real.decision_angelo", "")) != DECISION_ANGELO:
        malos.append(f"falta la decisión escrita de Ángelo (real.decision_angelo: \"{DECISION_ANGELO}\" en el reglamento) "
                     f"→ sin ella no hay dinero real.")
    ok, msg = RE.estado_ok(reg)
    if not ok:
        malos.append(msg + " → Ángelo revisa datos/real/cartera_REAL.json.")
    return malos


def compuertas_compra(reg: Reglamento, ahora: datetime, hora: dict[str, Any], conc: dict[str, Any],
                      est: dict[str, Any] | None) -> list[str]:
    """Lo que bloquea SOLO las compras nuevas (los cierres que protegen se emiten igual)."""
    malos = []
    if hora["estado"] != "OK":
        malos.append(f"ronda FUERA DE HORA ({hora['retraso_min']:.0f} min tarde): hoy no hay compras reales.")
    if not conc["ok"]:
        motivo = "; ".join(conc["errores"]) or json.dumps(conc["diferencias"], ensure_ascii=False)
        malos.append(f"la conciliación real no cuadra o no hay foto de saldo fresca ({motivo[:200]}) → EJECUTOR repite "
                     f"registrar-saldo y CONTADOR corre conciliar --real.")
    if est is not None:
        if est.get("detenido"):
            malos.append("la cartera REAL está DETENIDA por caída máxima → solo Ángelo la reanuda.")
        elif est.get("pausa_hasta") and ahora < datetime.fromisoformat(est["pausa_hasta"]):
            malos.append(f"la cartera REAL está en pausa ({est.get('pausa_motivo', '')}) hasta {est['pausa_hasta']}.")
    return malos


def compuertas_real(reg: Reglamento, ahora: datetime | None = None, hora: dict[str, Any] | None = None) -> list[str]:
    """TODAS las causas por las que hoy no habría compras reales (vacío = todo en orden)."""
    from .cli_ronda import revisar_hora
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    malos = compuertas_puerta(reg)
    if malos:
        return malos
    hora = hora or revisar_hora(reg, ahora)
    return compuertas_compra(reg, ahora, hora, RE.conciliar(reg, ahora, escribir=False), RE.cargar_estado(reg))


def _guardar_bitacora(reg: Reglamento, fila: dict[str, Any]) -> None:
    arch = RE.ruta_real(reg) / "bitacora_real.jsonl"
    arch.parent.mkdir(parents=True, exist_ok=True)
    with open(arch, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


ENCABEZADO = "████ REAL ████"


def _mostrar_guardada(reg: Reglamento, fecha: str) -> int:
    try:
        boletos = AR.leer_json_seguro(archivo_boletos(reg, fecha))
    except AR.ArchivoDanado as e:
        print(f"❌ {e}")
        return 1
    print(f"{ENCABEZADO} La ronda real de {fecha} ya corrió: no se repite y no se crea nada nuevo.")
    if boletos:
        print("Boletos REALES de esa ronda (ya entregados; NO se vuelven a poner):")
        for b in boletos:
            print("  " + str(b.get("texto", b.get("boleto_id"))))
    else:
        print("Esa ronda no tuvo boletos reales.")
    return 0


def decidir(reg: Reglamento, dd, est: dict[str, Any], foto: dict[str, Any] | None, conc: dict[str, Any],
            sin_compras: list[str], ahora: datetime) -> dict[str, Any]:
    """Qué boletos reales salen hoy (los cierres y la compra se agregan en los arreglos 134 y 135)."""
    return {"boletos": [], "mensajes": [], "descartes": []}


def correr(reg: Reglamento, ahora: datetime | None = None, cliente=None, memes: list[str] | None = None,
           simular: bool = False) -> int:
    """`ronda --modo real` (con `simular`, corre todo y solo imprime: no escribe estado, boletos ni bitácora)."""
    from . import cli_ronda as CR
    from . import datos as D
    from . import papel as P
    t0 = time.monotonic()
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    puerta = compuertas_puerta(reg)
    if puerta:
        print(f"{ENCABEZADO} La ronda real NO corre. Falta:")
        for m in puerta:
            print(f"❌ {m}")
        return 2
    hora = CR.revisar_hora(reg, ahora)
    if hora["estado"] == "TEMPRANO":
        print(f"⏳ Es muy temprano ({hora['hora_real_utc']}): la ronda real es a las {hora['hora_programada_utc']} UTC. "
              f"No corrí nada.")
        return 1
    fecha = CR.fecha_ronda(ahora)
    if archivo_boletos(reg, fecha).exists() or AR.hay_archivo(archivo_boletos(reg, fecha)):
        return _mostrar_guardada(reg, fecha)
    try:
        candado = CR.candado_ronda(reg, carpeta=RE.ruta_real(reg)) if not simular else _sin_candado()
        with candado:
            if not simular and AR.hay_archivo(archivo_boletos(reg, fecha)):
                return _mostrar_guardada(reg, fecha)
            cli = cliente or D.ClienteBinance(reg)
            dd = P.preparar_datos(reg, cli, memes if memes is not None else CR._memes(), ahora=ahora)
            conc = RE.conciliar(reg, ahora, escribir=not simular)
            est = RE.cargar_estado(reg, fecha)
            foto, _ = RE.leer_foto(reg, ahora)
            sin_compras = compuertas_compra(reg, ahora, hora, conc, est)
            out = decidir(reg, dd, est, foto, conc, sin_compras, ahora)
            if not simular:
                AR.escribir_json_seguro(archivo_boletos(reg, fecha), out["boletos"])
    except Exception as e:  # noqa: BLE001 - una ronda real caída nunca pasa desapercibida
        motivo = (str(e).strip() or type(e).__name__).splitlines()[0][:160]
        print(f"{ENCABEZADO}\n❌ La ronda real NO corrió: {motivo}\nHoy no hay boletos reales. Los stops ya puestos siguen "
              f"igual. Avisa a THE BOSS de inmediato.")
        return 1
    if not simular:
        try:
            _guardar_bitacora(reg, {"hora_real_utc": hora["hora_real_utc"], "dia_procesado": fecha,
                                    "duracion_s": round(time.monotonic() - t0, 1), "fuera_de_hora": hora["estado"] != "OK",
                                    "sin_compras": sin_compras, "boletos": len(out["boletos"]),
                                    "conciliacion_ok": conc["ok"], "modo_seguro": not dd.datos_ok})
        except OSError as e:
            print(f"⚠️ No pude escribir la bitácora real ({type(e).__name__}). La ronda sí corrió.")
    imprimir(fecha, out, sin_compras, conc, simular)
    return 0


class _sin_candado:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def imprimir(fecha: str, out: dict[str, Any], sin_compras: list[str], conc: dict[str, Any], simular: bool) -> None:
    urgentes = [b for b in out["boletos"] if b.get("urgente")]
    for b in urgentes:                                   # lo urgente va en la primera línea
        print(f"❌ URGENTE: {b['motivo']} en {b['simbolo']} — EJECUTOR debe cerrar ya. Avisa a Ángelo con prioridad.")
    print(f"{ENCABEZADO} Ronda REAL del {fecha} — dinero de verdad (Spot, reglas de la Cartera A, solo M0/BTC)."
          + (" SIMULACIÓN: no se escribió nada." if simular else ""))
    for m in sin_compras:
        print(f"❌ Sin compras: {m}")
    for m in out["mensajes"]:
        print(m)
    if out["boletos"]:
        print("Boletos REALES para el EJECUTOR (copiar tal cual):" if not simular else
              "Boletos REALES que saldrían (simulación: NO se ponen):")
        for b in out["boletos"]:
            print("  " + b["texto"])
    else:
        print("Sin boletos reales hoy." + ("" if sin_compras or not conc["ok"] else " 👍"))
