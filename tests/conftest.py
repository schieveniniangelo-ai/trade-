"""Piezas comunes para las pruebas."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from sobreviviente import reglamento
from sobreviviente.exchange import Filtros
from sobreviviente.riesgo import Candidato, EstadoCartera

CDMX = ZoneInfo("America/Mexico_City")


@pytest.fixture
def reg():
    """Reglamento real con las estrategias en PAPEL para poder evaluar candidatos."""
    r = reglamento.cargar()
    for k in r.estrategias:
        r.datos["estrategias"][k]["estado"] = "PAPEL"
    return r


@pytest.fixture
def ahora():
    return datetime(2026, 11, 10, 12, 0, tzinfo=CDMX)


@pytest.fixture
def filtros():
    return Filtros(simbolo="SOLUSDT", tick=0.01, paso=0.001, cantidad_min=0.001, minimo_usdt=5.0)


def hacer_estado(capital=1000.0, **kw):
    base = dict(capital=capital, pico=capital, capital_inicio_dia=capital, capital_inicio_semana=capital)
    base.update(kw)
    return EstadoCartera(**base)


def hacer_cand(**kw):
    base = dict(
        simbolo="SOLUSDT", mercado="SPOT", lado="LARGO", estrategia="E1", cubeta="normales",
        precio_entrada=100.0, stop=95.0, comision_pct=0.1, deslizamiento_pct=0.05,
    )
    base.update(kw)
    return Candidato(**base)
