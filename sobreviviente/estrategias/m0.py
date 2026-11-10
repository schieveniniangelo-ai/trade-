"""M0 — Marea BTC (= referencia R1 convertida en motor, v2).

Dentro de BTC mientras su cierre diario esté arriba de la media de 200 días; fuera (en USDT) cuando cierra abajo.
Solo se usa si ningún motor le gana a R1 (regla de la v2).

Para que pase por el motor de riesgo como cualquier otra estrategia necesita un stop real en Binance:
se usa un stop de CATÁSTROFE a `stop_pct` % bajo la entrada (15 % por defecto, el mismo tope de M1). Con el
tamaño por riesgo (1 % o 2 % ÷ 15 %) y el tope de 30 % por posición, la cartera tiene una parte de BTC,
no todo el dinero: la versión "todo adentro" es la referencia R1, que se sigue aparte en papel.
"""
from __future__ import annotations

from .base import Contexto, salida

TEMPORALIDAD = "1d"
PARAMETROS = ("sma",)
STOP_PCT = 15.0


def senales(ctx: Contexto, p: dict):
    v = ctx.velas
    alta = ctx.regimen_btc == "ALCISTA"
    # Por ESTADO (no solo el día que cambia): igual que R1, si la marea está alta y no hay posición, se entra.
    # Así una cartera que empieza a mitad de una marea alta también entra, y tras un stop de catástrofe se
    # vuelve a entrar al día siguiente si la marea sigue alta. Si ya hay posición, el motor de riesgo no duplica.
    entrada = alta if ctx.simbolo == "BTCUSDT" else alta & False
    salir = ~alta
    stop = v["close"] * (1 - float(p.get("stop_pct", STOP_PCT)) / 100.0)
    return salida(ctx, entrada, stop, None, None, salir)


def gestion(p: dict) -> dict:
    return {"modo": "senal_salida"}
