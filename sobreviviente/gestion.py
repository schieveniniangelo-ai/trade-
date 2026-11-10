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
En todos: stop inicial, +1R → stop a la entrada más costos, y los stops solo se mueven a favor.
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
    en_r: float = 1.0         # en cuántas R se mueve el stop a la entrada

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


def _a_favor(lado: str, actual: float, nuevo: float) -> float:
    return max(actual, nuevo) if lado == LARGO else min(actual, nuevo)


def vela(est: EstadoGestion, o: float, h: float, l: float, c: float, atr: float,
         media: float | None = None) -> Evento:
    """Procesa una vela cerrada. Primero revisa salidas con el stop vigente; luego, al cierre,
    actualiza el stop para la siguiente vela."""
    largo = est.lado == LARGO
    # 0) Salida programada para la apertura de esta vela
    if est.salir_en_apertura:
        return Evento(salio=True, precio=o, motivo=est.params.get("_motivo_salida", "salida programada"))

    # 1) ¿Tocó el stop? Si abrió más allá del stop (hueco), se llena a la apertura.
    if largo:
        if o <= est.stop:
            return Evento(True, o, "stop (hueco)")
        if l <= est.stop:
            return Evento(True, est.stop, "stop")
    else:
        if o >= est.stop:
            return Evento(True, o, "stop (hueco)")
        if h >= est.stop:
            return Evento(True, est.stop, "stop")

    # 2) Al cierre: actualizar extremos y stop
    est.velas += 1
    est.extremo = max(est.extremo, h) if largo else min(est.extremo, l)
    stop_antes = est.stop
    r = est.r_unidad
    signo = 1 if largo else -1

    # +1R → stop a la entrada más costos
    if (est.extremo - est.entrada_plan) * signo >= est.en_r * r:
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

    max_velas = est.params.get("max_velas")
    if max_velas and est.velas >= int(max_velas) and not est.salir_en_apertura:
        est.salir_en_apertura = True
        est.params["_motivo_salida"] = "salida por tiempo"

    ev = Evento()
    if est.stop != stop_antes:
        ev.stop_nuevo = est.stop
    return ev
