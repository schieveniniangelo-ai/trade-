"""Gestión de una posición abierta, vela por vela.

Es EXACTAMENTE el mismo código en el backtest y en vivo:
- En el backtest se llama una vez por cada vela después de la entrada.
- En vivo, cada ronda se llama con las velas que cerraron desde la última ronda, y si el stop
  cambia se genera un boleto MODIFICAR_STOP; si toca salir, un boleto CERRAR.

Modos de salida:
- "chandelier": stop dinámico = extremo desde la entrada − m × ATR (E1, E5).
- "meta_luego_chandelier": al tocar la meta (2R) el stop sube a +1R y luego sigue dinámico (E2).
- "media": sale en la apertura siguiente cuando el cierre cruza la media (E3).
- "tiempo": sale cuando se cumplen N velas (E4).
- "senal_salida": sale en la apertura siguiente cuando la estrategia lo indica (E6, E7, M2).
- "canal" (v2, M1): sale en la apertura siguiente si el cierre cae bajo el mínimo de las `canal_velas`
  velas previas; el stop real sube cada vela al nuevo mínimo del canal (solo a favor).
- "ranking" (v2, M2): igual que "senal_salida"; la señal la da la tabla semanal o la media de 100 días.
En todos: stop inicial y stops que solo se mueven a favor. El paso "+1R → stop a la entrada"
aplica salvo que la estrategia lo desactive en el reglamento (en_r = None).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LARGO = "LARGO"


@dataclass
class EstadoGestion:
    """Estado de una posición abierta (se puede guardar en la bitácora y reconstruir)."""

    lado: str
    entrada: float            # precio real de entrada
    entrada_plan: float       # precio con el que se calculó el riesgo (cierre de la vela de señal)
    stop_inicial: float
    stop: float
    meta: float | None
    modo: str
    params: dict[str, Any] = field(default_factory=dict)
    costo_pct: float = 0.0    # costo de ida y vuelta en % (para mover el stop a entrada + costos)
    extremo: float = 0.0      # máximo (largo) o mínimo (corto) desde la entrada
    velas: int = 0
    meta_tocada: bool = False
    salir_en_apertura: bool = False
    en_r: float | None = 1.0  # en cuántas R se mueve el stop a la entrada (None = nunca)
    # Llenado realista del STOP_LOSS_LIMIT (papel): límite a `limite_stop_pct` % del stop. None = la regla de siempre
    # (si hay hueco se llena a la apertura). Si el precio abre más allá del límite, el stop NO se llena y queda una
    # orden de venta límite pendiente (`stop_pendiente`) que se llena cuando el precio regrese a ese nivel.
    limite_stop_pct: float | None = None
    stop_pendiente: float | None = None

    def __post_init__(self) -> None:
        if not self.extremo:
            self.extremo = self.entrada

    @property
    def r_unidad(self) -> float:
        return abs(self.entrada_plan - self.stop_inicial)


@dataclass
class Evento:
    """Lo que pasó en una vela."""

    salio: bool = False
    precio: float = 0.0       # precio de salida ANTES de deslizamiento
    motivo: str = ""
    stop_nuevo: float | None = None
    stop_sin_llenar: bool = False  # el stop se activó, pero el precio pasó su límite: la posición sigue abierta


def _a_favor(lado: str, actual: float, nuevo: float) -> float:
    return max(actual, nuevo) if lado == LARGO else min(actual, nuevo)


def vela(est: EstadoGestion, o: float, h: float, l: float, c: float, atr: float,
         media: float | None = None, salida_externa: bool = False, canal: float | None = None) -> Evento:
    """Procesa una vela cerrada. Primero revisa salidas con el stop vigente; luego, al cierre,
    actualiza el stop para la siguiente vela.

    `canal` (modo "canal"): mínimo de las últimas `canal_velas` velas, CONTANDO esta (se conoce al cierre)."""
    largo = est.lado == LARGO
    # 0) Salida programada para la apertura de esta vela
    if est.salir_en_apertura:
        return Evento(salio=True, precio=o, motivo=est.params.get("_motivo_salida", "salida programada"))

    # 0b) Stop ya activado que no se llenó: queda una orden de venta límite en `stop_pendiente`.
    if est.stop_pendiente is not None:
        L = est.stop_pendiente
        if largo:
            if o >= L:
                return Evento(True, o, "stop (llenado tarde)")
            if h >= L:
                return Evento(True, L, "stop (llenado tarde)")
        else:
            if o <= L:
                return Evento(True, o, "stop (llenado tarde)")
            if l <= L:
                return Evento(True, L, "stop (llenado tarde)")
        est.velas += 1
        return Evento(motivo="stop sin llenar", stop_sin_llenar=True)

    # 1) ¿Tocó el stop? Si abrió más allá del stop (hueco), se llena a la apertura… salvo que el hueco pase
    #    el límite del STOP_LOSS_LIMIT (llenado realista): entonces NO se llena.
    if largo:
        if o <= est.stop:
            if est.limite_stop_pct is None:
                return Evento(True, o, "stop (hueco)")
            L = est.stop * (1 - est.limite_stop_pct / 100.0)
            if o >= L:
                return Evento(True, o, "stop (hueco)")
            if h >= L:
                return Evento(True, L, "stop (hueco, al límite)")
            est.stop_pendiente = L
            est.velas += 1
            return Evento(motivo="stop sin llenar", stop_sin_llenar=True)
        if l <= est.stop:
            return Evento(True, est.stop, "stop")
    else:
        if o >= est.stop:
            if est.limite_stop_pct is None:
                return Evento(True, o, "stop (hueco)")
            L = est.stop * (1 + est.limite_stop_pct / 100.0)
            if o <= L:
                return Evento(True, o, "stop (hueco)")
            if l <= L:
                return Evento(True, L, "stop (hueco, al límite)")
            est.stop_pendiente = L
            est.velas += 1
            return Evento(motivo="stop sin llenar", stop_sin_llenar=True)
        if h >= est.stop:
            return Evento(True, est.stop, "stop")

    # 2) Al cierre: actualizar extremos y stop
    est.velas += 1
    est.extremo = max(est.extremo, h) if largo else min(est.extremo, l)
    stop_antes = est.stop
    r = est.r_unidad
    signo = 1 if largo else -1

    # +1R → stop a la entrada más costos
    if est.en_r is not None and (est.extremo - est.entrada_plan) * signo >= est.en_r * r:
        be = est.entrada * (1 + signo * est.costo_pct / 100.0)
        est.stop = _a_favor(est.lado, est.stop, be)

    m = float(est.params.get("chandelier_atr", 3.0))
    if est.modo == "chandelier":
        est.stop = _a_favor(est.lado, est.stop, est.extremo - signo * m * atr)
    elif est.modo == "meta_luego_chandelier":
        if not est.meta_tocada and est.meta is not None and (est.extremo - est.meta) * signo >= 0:
            est.meta_tocada = True
        if est.meta_tocada:
            est.stop = _a_favor(est.lado, est.stop, est.entrada_plan + signo * r)
            est.stop = _a_favor(est.lado, est.stop, est.extremo - signo * m * atr)
    elif est.modo == "media":
        if media is not None and (c - media) * signo >= 0:
            est.salir_en_apertura = True
            est.params["_motivo_salida"] = "regresó al promedio"
    elif est.modo == "tiempo":
        pass
    elif est.modo == "canal":
        previo = est.params.get("_canal_prev")
        if previo is not None and c < previo:
            est.salir_en_apertura = True
            est.params["_motivo_salida"] = "cerró bajo el piso del canal"
        if canal is not None and canal == canal:  # canal == canal descarta NaN
            est.stop = _a_favor(est.lado, est.stop, canal)
            est.params["_canal_prev"] = canal
    elif est.modo in ("senal_salida", "ranking"):
        if salida_externa:
            est.salir_en_apertura = True
            est.params["_motivo_salida"] = "la estrategia ya no quiere estar dentro"

    max_velas = est.params.get("max_velas")
    if max_velas and est.velas >= int(max_velas) and not est.salir_en_apertura:
        est.salir_en_apertura = True
        est.params["_motivo_salida"] = "salida por tiempo"

    ev = Evento()
    if est.stop != stop_antes:
        ev.stop_nuevo = est.stop
    return ev
