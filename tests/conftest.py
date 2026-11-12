"""Piezas comunes para las pruebas."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from sobreviviente import reglamento
from sobreviviente.exchange import Filtros
from sobreviviente.riesgo import Candidato, EstadoCartera

CDMX = ZoneInfo("America/Mexico_City")
RAIZ = Path(__file__).resolve().parent.parent


def huella_datos_reales(raiz: Path = RAIZ) -> dict[str, tuple[int, int]]:
    """Tamaño y hora de cada archivo de `datos/` (sin `datos/cache/`, las copias de Binance) y de `salida/`."""
    out = {}
    for base in (raiz / "datos", raiz / "salida"):
        if not base.is_dir():
            continue
        for hijo in base.iterdir():
            if base.name == "datos" and hijo.name == "cache":
                continue
            for p in ([hijo] if hijo.is_file() else hijo.rglob("*")):
                if p.is_file():
                    st = p.stat()
                    out[str(p.relative_to(raiz))] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(autouse=True)
def _sin_tocar_datos_reales():
    """Arreglo 95: ninguna prueba puede modificar los datos reales del papel (`datos/` y `salida/` del proyecto).

    Si falla justo mientras corría la ronda real (6:10 p. m. CDMX), vuelve a correr pytest."""
    antes = huella_datos_reales()
    yield
    despues = huella_datos_reales()
    cambiados = sorted(k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k))
    assert not cambiados, f"Esta prueba modificó datos reales del papel: {cambiados}"


@pytest.fixture(autouse=True)
def _casa_temporal(monkeypatch, tmp_path):
    """Arreglo 85: '~' apunta a una carpeta temporal, para que ninguna prueba lea ~/respaldos-sobreviviente real."""
    casa = str(tmp_path / "casa")
    monkeypatch.setenv("HOME", casa)
    monkeypatch.setenv("USERPROFILE", casa)


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
