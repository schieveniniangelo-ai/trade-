"""Cartera F de PAPEL de Futuros F1: estado propio, frenos, calor, rachas, vetos y gestión de posiciones.

- Estado en datos/papel_futuros/F.json (`archivos.escribir_json_seguro`). No comparte nada con A, B, C ni con el real.
- Frenos con `riesgo.aplicar_topes` sobre una COPIA del reglamento (`Reglamento.copia_con`) con las cifras de F1:
  diario 3 % (pausa hasta las 00:00 UTC), semanal 6 % (hasta el lunes), 15 % desde el pico (todo se detiene hasta el
  OK de Ángelo). Así los frenos de F1 no cambian los de A, B y C.
- Vetos (`riesgo.veto_activo`) y eventos fuertes (`riesgo.evento_activo`) bloquean los dos lados; si vetos.json o
  eventos.json vienen dañados, no hay entradas.
- 2 posiciones como máximo, 1 por moneda, calor ≤ 2 %; 4 pérdidas seguidas = pausa de 24 h.
- Cada vela de 4 h: liquidación con el precio de MARCA, stop con el máximo y el mínimo del último precio (la misma
  `gestion.vela` del backtest, con el chandelier y la salida por régimen) y funding en cada hora de cobro.
Todo es papel: nada de esto genera boletos ni órdenes.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .. import archivos as AR
from .. import riesgo as R
from ..exchange import Filtros
from ..gestion import EstadoGestion, vela
from ..reglamento import Reglamento
from . import tamano as T

CARPETA = "papel_futuros"
ARCHIVO = "F.json"


# ---------------------------------------------------------------------------- estado
def ruta_estado(reg: Reglamento) -> Path:
    return AR.carpeta_datos(reg) / CARPETA / ARCHIVO


def estado_nuevo(cfg: dict[str, Any], ahora: datetime | None = None) -> dict[str, Any]:
    cap = float(cfg["capital_papel"])
    return {"cartera": "F", "solo_papel": True, "capital_inicial": cap, "capital": cap, "pico": cap,
            "capital_inicio_dia": cap, "dia_utc": None, "capital_inicio_semana": cap, "semana": None,
            "pausa_hasta": None, "pausa_motivo": "", "detenido": False, "perdidas_seguidas": 0,
            "pausa_racha_hasta": None, "posiciones": [], "cerradas": [], "ultima_vela": None,
            "creado": (ahora or datetime.now(timezone.utc)).isoformat(timespec="seconds")}


def cargar_estado(reg: Reglamento, cfg: dict[str, Any]) -> dict[str, Any]:
    """Estado guardado o uno nuevo. Si F.json está dañado lanza ArchivoDanado (no se inventa otro encima)."""
    arch = ruta_estado(reg)
    if not arch.exists():
        return estado_nuevo(cfg)
    return AR.leer_json_seguro(arch)


def guardar_estado(reg: Reglamento, est: dict[str, Any]) -> Path:
    arch = ruta_estado(reg)
    AR.escribir_json_seguro(arch, est)
    return arch


def _fecha(x: Any) -> datetime | None:
    if x is None or x == "":
        return None
    d = x if isinstance(x, datetime) else datetime.fromisoformat(str(x))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------- frenos
def reglamento_f1(reg: Reglamento, cfg: dict[str, Any]) -> Reglamento:
    """Copia del reglamento con los frenos de F1 (el original no cambia)."""
    return reg.copia_con({"riesgo.tope_diario_pct": float(cfg["tope_diario_pct"]),
                          "riesgo.tope_semanal_pct": float(cfg["tope_semanal_pct"]),
                          "riesgo.caida_max_desde_pico_pct": float(cfg["caida_max_desde_pico_pct"])})


def aplicar_frenos(reg_f1: Reglamento, est: dict[str, Any], ahora: datetime) -> list[str]:
    """Mide los topes contra la referencia del día UTC y de la semana (CDMX), como el papel y el backtest."""
    semana = R.inicio_semana(reg_f1, ahora).isoformat()
    if est.get("semana") != semana:
        est["semana"] = semana
        est["capital_inicio_semana"] = est["capital"]
    ec = R.EstadoCartera(capital=float(est["capital"]), pico=float(est["pico"]),
                         capital_inicio_dia=float(est["capital_inicio_dia"]),
                         capital_inicio_semana=float(est["capital_inicio_semana"]),
                         pausa_hasta=_fecha(est.get("pausa_hasta")), pausa_motivo=est.get("pausa_motivo", ""),
                         detenido=bool(est.get("detenido")))
    mensajes = R.aplicar_topes(reg_f1, ec, ahora)
    est["pico"], est["detenido"] = ec.pico, ec.detenido
    est["pausa_hasta"] = ec.pausa_hasta.isoformat() if ec.pausa_hasta else None
    est["pausa_motivo"] = ec.pausa_motivo
    dia = R.inicio_dia_utc(ahora).isoformat()
    if est.get("dia_utc") != dia:
        est["dia_utc"] = dia
        est["capital_inicio_dia"] = est["capital"]
    return mensajes


def leer_vetos_eventos(reg: Reglamento) -> tuple[list[dict], list[dict], bool, list[str]]:
    """(vetos, eventos, dañado, avisos) de los archivos de CENTINELA, igual que la ronda de papel (sin importarla)."""
    vetos, eventos, danado, avisos = [], [], False, []
    for nombre, (d, err) in AR.leer_todos(reg).items():
        if err and not (len(err) == 1 and err[0].startswith("no existe")):
            danado = True
            avisos.append(f"{nombre} viene mal ({'; '.join(err)}): F1 no tiene entradas hoy.")
        elif d is not None:
            vetos = d.get("vetos", vetos) if nombre == "vetos.json" else vetos
            eventos = d.get("eventos", eventos) if nombre == "eventos.json" else eventos
    return vetos, eventos, danado, avisos


def bloqueos_entrada(reg_f1: Reglamento, est: dict[str, Any], simbolo: str, ahora: datetime,
                     vetos: list[dict] | None = None, eventos: list[dict] | None = None,
                     archivos_danados: bool = False) -> list[str]:
    """Razones por las que NO se puede abrir nada en esta moneda ahora (vacío = se puede). Vale para los dos lados."""
    out = []
    if est.get("detenido"):
        out.append("F1 DETENIDO por caída desde el pico: solo Ángelo lo reanuda.")
    p = _fecha(est.get("pausa_hasta"))
    if p and ahora < p:
        out.append(f"F1 en pausa ({est.get('pausa_motivo', '')}) hasta {p.isoformat()}.")
    pr = _fecha(est.get("pausa_racha_hasta"))
    if pr and ahora < pr:
        out.append(f"F1 en pausa por pérdidas seguidas hasta {pr.isoformat()}.")
    if archivos_danados:
        out.append("un archivo de CENTINELA viene dañado: sin entradas.")
    v = R.veto_activo(vetos or [], simbolo, ahora)
    if v is not None:
        out.append(f"veto de CENTINELA ({v.get('simbolo')}): {str(v.get('razon', ''))[:80]}")
    e = R.evento_activo(reg_f1, eventos or [], ahora)
    if e is not None:
        out.append(f"evento fuerte: {str(e.get('nombre', e.get('evento', '')))[:80]}")
    return out


# ---------------------------------------------------------------------------- tamaño y entrada
def margen_abierto(est: dict[str, Any]) -> float:
    return float(sum(p["margen"] for p in est["posiciones"]))


def calor_usdt(est: dict[str, Any]) -> float:
    """Lo que se perdería si todas las abiertas tocaran su stop vigente."""
    total = 0.0
    for p in est["posiciones"]:
        d = (p["entrada"] - p["stop"]) if p["lado"] == "LARGO" else (p["stop"] - p["entrada"])
        total += max(0.0, d * p["cantidad"])
    return total


def cabe(cfg: dict[str, Any], est: dict[str, Any], simbolo: str, lado: str, precio: float, stop: float,
         filtros: Filtros) -> T.Tamano:
    """¿Cabe una posición nueva? Posiciones máximas, 1 por moneda, calor y tamaño por riesgo (con margen)."""
    if len(est["posiciones"]) >= int(cfg["posiciones_max"]):
        return T.Tamano(False, f"no cabe: ya hay {len(est['posiciones'])} posiciones (máximo {cfg['posiciones_max']})")
    if any(p["simbolo"] == simbolo for p in est["posiciones"]):
        return T.Tamano(False, f"no cabe: ya hay una posición en {simbolo} (1 por moneda)")
    cap = float(est["capital"])
    t = T.calcular(cap, float(cfg["riesgo_por_operacion_pct"]), precio, stop, lado, filtros, cfg,
                   margen_abierto=margen_abierto(est))
    if not t.cabe:
        return t
    tope = cap * float(cfg["calor_total_max_pct"]) / 100.0
    if calor_usdt(est) + t.riesgo_usdt > tope + 1e-9:
        return T.Tamano(False, f"no cabe por calor: lo abierto arriesga {calor_usdt(est):.3f} USDT y esta "
                               f"{t.riesgo_usdt:.3f}; el tope es {tope:.3f} ({cfg['calor_total_max_pct']:g} %)")
    return t


def abrir(est: dict[str, Any], simbolo: str, lado: str, entrada: float, precio_plan: float, stop: float,
          t: T.Tamano, ahora: datetime, gest: dict[str, Any], comision_pct: float) -> dict[str, Any]:
    """Abre la posición de papel (la comisión de entrada se descuenta del capital)."""
    params = {k: v for k, v in gest.items() if k not in ("modo", "sin_breakeven")}
    g = EstadoGestion(lado=lado, entrada=entrada, entrada_plan=precio_plan, stop_inicial=stop, stop=stop, meta=None,
                      modo=gest["modo"], params=params, en_r=None)
    comision = entrada * t.cantidad * comision_pct / 100.0
    pos = {"simbolo": simbolo, "lado": lado, "entrada": entrada, "cantidad": t.cantidad, "stop": stop,
           "stop_inicial": stop, "apalancamiento": t.apalancamiento, "margen": t.margen, "liquidacion": t.liquidacion,
           "abierta_en": ahora.isoformat(timespec="seconds"), "comisiones": comision, "funding": 0.0,
           "gestion": asdict(g)}
    est["capital"] = float(est["capital"]) - comision
    est["posiciones"].append(pos)
    return pos


# ---------------------------------------------------------------------------- velas, funding y cierre
def cobrar_funding(pos: dict[str, Any], cobros: pd.Series, precio_marca: float) -> float:
    """Funding de los cobros dados (fracción por cobro) sobre el valor a precio de marca. Positivo = cobra."""
    signo = -1.0 if pos["lado"] == "LARGO" else 1.0     # funding positivo: el largo paga, el corto cobra
    monto = float(cobros.sum()) * pos["cantidad"] * precio_marca * signo
    pos["funding"] = float(pos.get("funding", 0.0)) + monto
    return monto


def procesar_vela(pos: dict[str, Any], o: float, h: float, l: float, c: float, atr: float,
                  marca_h: float | None, marca_l: float | None, salir: bool) -> tuple[bool, float, str]:
    """Una vela de 4 h cerrada: (salió, precio, motivo). Primero la liquidación con la marca; luego el stop."""
    g = EstadoGestion(**pos["gestion"])
    ev = vela(g, o, h, l, c, atr, salida_externa=salir)
    liq = pos.get("liquidacion")
    largo = pos["lado"] == "LARGO"
    if liq is not None and marca_h is not None and marca_l is not None:
        toca = (marca_l <= liq) if largo else (marca_h >= liq)
        if toca and not (ev.salio and ((ev.precio > liq) if largo else (ev.precio < liq))):
            pos["gestion"] = asdict(g)
            return True, float(liq), "liquidación"
    pos["gestion"] = asdict(g)
    pos["stop"] = g.stop
    if ev.salio:
        return True, float(ev.precio), ev.motivo
    return False, 0.0, ""


def cerrar(est: dict[str, Any], pos: dict[str, Any], precio: float, motivo: str, ahora: datetime,
           cfg: dict[str, Any], comision_pct: float, desliz_pct: float, tarifa_liq_pct: float = 0.0) -> float:
    """Cierra en papel. Liquidación (Arreglo 157) = min(margen, pérdida hasta la liquidación + tarifa sobre el nocional):
    en AISLADO nunca se pierde más que el margen. Regresa la ganancia neta de la operación."""
    largo = pos["lado"] == "LARGO"
    q = pos["cantidad"]
    if motivo == "liquidación":
        tarifa = precio * q * tarifa_liq_pct / 100.0
        bruto = -min(float(pos["margen"]), abs(pos["entrada"] - precio) * q + tarifa)
        comision = 0.0
        salida = precio
    else:
        salida = precio * (1 - desliz_pct / 100.0 if largo else 1 + desliz_pct / 100.0)
        bruto = (salida - pos["entrada"]) * q if largo else (pos["entrada"] - salida) * q
        comision = salida * q * comision_pct / 100.0
    neto_capital = bruto - comision + float(pos.get("funding", 0.0))
    est["capital"] = float(est["capital"]) + neto_capital
    neta = neto_capital - float(pos.get("comisiones", 0.0))       # la comisión de entrada ya salió del capital
    est["posiciones"] = [p for p in est["posiciones"] if p is not pos]
    est["cerradas"].append({**{k: v for k, v in pos.items() if k != "gestion"}, "salida": salida, "motivo": motivo,
                            "cerrada_en": ahora.isoformat(timespec="seconds"), "ganancia_usdt": neta,
                            "capital_despues": est["capital"]})
    registrar_racha(est, neta, ahora, cfg)
    return neta


def registrar_racha(est: dict[str, Any], ganancia: float, ahora: datetime, cfg: dict[str, Any]) -> bool:
    """4 pérdidas seguidas → pausa de 24 h (y la cuenta vuelve a 0). Regresa True si empezó una pausa."""
    if ganancia < 0:
        est["perdidas_seguidas"] = int(est.get("perdidas_seguidas", 0)) + 1
    else:
        est["perdidas_seguidas"] = 0
    if est["perdidas_seguidas"] >= int(cfg["perdidas_seguidas_pausa"]):
        est["pausa_racha_hasta"] = (ahora + timedelta(hours=float(cfg["pausa_horas"]))).isoformat(timespec="seconds")
        est["perdidas_seguidas"] = 0
        return True
    return False
