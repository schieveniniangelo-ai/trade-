"""v2: corre la validación completa y guarda los resultados (comando `validar --v2`).

Pasos (se pueden correr por separado con --pasos):
  auditoria   A1–A9 sobre E1 de la v1 (necesita las velas de 1 h; es lo más pesado)
  referencias R0, R1, R2
  motores     M1 y M2 con validación completa; M0 como cartera
  estela      verificación de datos de top traders y estudio de eventos (Fase C)
Los resultados se guardan en `salida/v2/<paso>.json` y el informe se arma con `informe_v2`.
JSON y no pickle: leer un pickle puede correr código; leer JSON no. Los tipos que no tiene JSON (Series, DataFrame,
fechas, tuplas, llaves que no son texto, NaN, pd.NA, Period) se guardan con una marca `__tipo__` y regresan iguales al
leerlos. La escritura es la segura de `archivos.py` (temporal + fsync + copia .bak).
"""
from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import archivos as AR
from . import datos as D
from . import python_actual
from .reglamento import Reglamento

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "salida" / "v2"
_TIPO = "__tipo__"
# Qué paso de `validar --v2 --pasos` escribe cada resultado (para decir qué volver a correr).
PASO_DE = {"referencias": "referencias", "M0": "motores", "M1": "motores", "M2": "motores",
           "M1_veto": "veto", "M2_veto": "veto", "auditoria": "auditoria", "estela": "estela"}


class FaltaResultado(RuntimeError):
    """Un resultado guardado no se puede usar (solo está el .pkl viejo, o falta). El mensaje dice qué correr."""


def _comando_paso(paso: str) -> str:
    return f"{python_actual()} -m sobreviviente validar --v2 --pasos {paso}"


def _indice_a_json(ix: pd.Index, perdidos: list[str] | None) -> dict:
    return {_TIPO: "Index", "nombre": _a_json(ix.name, perdidos), "dtype": str(ix.dtype),
            "valores": _a_json(ix.tolist(), perdidos)}


def _a_json(x: Any, perdidos: list[str] | None = None) -> Any:
    """Convierte `x` a algo que JSON sí guarda, con marcas para lo que JSON no tiene.

    Un tipo desconocido es error (TypeError). Con la lista `perdidos`, en cambio, ese valor queda como marca
    `sin_guardar` (se lee como None) y su tipo se anota en la lista."""
    if x is None or isinstance(x, (bool, str)):
        return x
    if x is pd.NA:
        return {_TIPO: "NA"}
    if isinstance(x, (np.datetime64, np.timedelta64)):          # antes que np.integer: timedelta64 es entero
        return {_TIPO: "numpy_tiempo", "dtype": str(x.dtype), "valor": int(x.astype("int64"))}
    if isinstance(x, (np.bool_, np.integer, np.floating)):
        return {_TIPO: "numpy", "dtype": str(x.dtype), "valor": _a_json(x.item(), perdidos)}
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        x = float(x)
        return x if math.isfinite(x) else {_TIPO: "float", "valor": repr(x)}
    if x is pd.NaT:
        return {_TIPO: "NaT"}
    if isinstance(x, pd.Timestamp):
        return {_TIPO: "Timestamp", "valor": x.isoformat(), "tz": None if x.tz is None else str(x.tz)}
    if isinstance(x, pd.Timedelta):
        return {_TIPO: "Timedelta", "ns": int(x.value)}
    if isinstance(x, timedelta):
        return {_TIPO: "timedelta", "dias": x.days, "segundos": x.seconds, "micro": x.microseconds}
    if isinstance(x, pd.Period):
        return {_TIPO: "Period", "valor": str(x), "freq": x.freqstr}
    if isinstance(x, datetime):
        return {_TIPO: "datetime", "valor": x.isoformat()}
    if isinstance(x, date):
        return {_TIPO: "date", "valor": x.isoformat()}
    if isinstance(x, pd.Index):
        return _indice_a_json(x, perdidos)
    if isinstance(x, pd.Series):
        return {_TIPO: "Series", "nombre": _a_json(x.name, perdidos), "dtype": str(x.dtype),
                "indice": _indice_a_json(x.index, perdidos), "valores": _a_json(x.tolist(), perdidos)}
    if isinstance(x, pd.DataFrame):
        return {_TIPO: "DataFrame", "columnas": _indice_a_json(x.columns, perdidos),
                "indice": _indice_a_json(x.index, perdidos),
                "datos": [{"dtype": str(x.iloc[:, i].dtype), "valores": _a_json(x.iloc[:, i].tolist(), perdidos)}
                          for i in range(x.shape[1])]}
    if isinstance(x, np.ndarray):
        return {_TIPO: "ndarray", "dtype": str(x.dtype), "valores": _a_json(x.tolist(), perdidos)}
    if isinstance(x, list):
        return [_a_json(v, perdidos) for v in x]
    if isinstance(x, tuple):
        return {_TIPO: "tuple", "valores": [_a_json(v, perdidos) for v in x]}
    if isinstance(x, (set, frozenset)):
        return {_TIPO: type(x).__name__, "valores": [_a_json(v, perdidos) for v in x]}
    if isinstance(x, dict):
        if all(isinstance(k, str) for k in x) and _TIPO not in x:
            return {k: _a_json(v, perdidos) for k, v in x.items()}
        return {_TIPO: "dict", "pares": [[_a_json(k, perdidos), _a_json(v, perdidos)] for k, v in x.items()]}
    if perdidos is None:
        raise TypeError(f"No sé guardar en JSON un {type(x).__name__}")
    perdidos.append(type(x).__name__)
    return {_TIPO: "sin_guardar", "tipo": type(x).__name__, "texto": repr(x)[:200]}


def _indice_de_json(d: dict) -> pd.Index:
    return pd.Index(_de_json(d["valores"]), dtype=d["dtype"], name=_de_json(d["nombre"]))


def _de_json(x: Any) -> Any:
    """Lo contrario de `_a_json`."""
    if isinstance(x, list):
        return [_de_json(v) for v in x]
    if not isinstance(x, dict):
        return x
    tipo = x.get(_TIPO)
    if tipo is None:
        return {k: _de_json(v) for k, v in x.items()}
    if tipo == "float":
        return float(x["valor"])
    if tipo == "numpy":
        return np.dtype(x["dtype"]).type(_de_json(x["valor"]))
    if tipo == "numpy_tiempo":
        return np.array(x["valor"], dtype="int64").view(x["dtype"])[()]
    if tipo == "NA":
        return pd.NA
    if tipo == "NaT":
        return pd.NaT
    if tipo == "Timestamp":
        t = pd.Timestamp(x["valor"])
        return t if x["tz"] is None else t.tz_convert(x["tz"])
    if tipo == "Timedelta":
        return pd.Timedelta(x["ns"], unit="ns")
    if tipo == "timedelta":
        return timedelta(days=x["dias"], seconds=x["segundos"], microseconds=x["micro"])
    if tipo == "Period":
        return pd.Period(x["valor"], freq=x["freq"])
    if tipo == "datetime":
        return datetime.fromisoformat(x["valor"])
    if tipo == "date":
        return date.fromisoformat(x["valor"])
    if tipo == "Index":
        return _indice_de_json(x)
    if tipo == "Series":
        return pd.Series(_de_json(x["valores"]), index=_indice_de_json(x["indice"]), dtype=x["dtype"],
                         name=_de_json(x["nombre"]))
    if tipo == "DataFrame":
        indice = _indice_de_json(x["indice"])
        cols = [pd.Series(_de_json(c["valores"]), index=indice, dtype=c["dtype"]) for c in x["datos"]]
        df = pd.DataFrame(dict(enumerate(cols)), index=indice) if cols else pd.DataFrame(index=indice)
        df.columns = _indice_de_json(x["columnas"])
        return df
    if tipo == "ndarray":
        return np.array(_de_json(x["valores"]), dtype=x["dtype"])
    if tipo == "tuple":
        return tuple(_de_json(v) for v in x["valores"])
    if tipo in ("set", "frozenset"):
        return (set if tipo == "set" else frozenset)(_de_json(v) for v in x["valores"])
    if tipo == "dict":
        return {_de_json(k): _de_json(v) for k, v in x["pares"]}
    if tipo == "sin_guardar":
        return None
    raise ValueError(f"Marca {_TIPO} desconocida: {tipo!r}")


def _archivo(nombre: str) -> Path:
    return SALIDA / f"{nombre}.json"


def _guardar(nombre: str, obj) -> None:
    """Guarda `obj` en salida/v2/<nombre>.json. Un tipo desconocido es error y no deja archivo."""
    AR.escribir_json_seguro(_archivo(nombre), _a_json(obj), indent=None)


def _guardar_rescatando(nombre: str, obj, avisar=print) -> None:
    """Como `_guardar`, para los pasos que tardan: un tipo desconocido no tira el resultado de horas de cálculo.
    Ese valor queda vacío (se lee como None), el resto se guarda y se avisa con ⚠️ qué tipos se perdieron."""
    try:
        _guardar(nombre, obj)
    except TypeError:
        perdidos: list[str] = []
        AR.escribir_json_seguro(_archivo(nombre), _a_json(obj, perdidos), indent=None)
        avisar(f"⚠️ {nombre}: {len(perdidos)} valor(es) de tipo {', '.join(sorted(set(perdidos)))} no se pudieron "
               f"guardar en JSON y quedaron vacíos; el resto sí se guardó.")


def cargar_resultado(nombre: str):
    """Lee salida/v2/<nombre>.json (si está dañado, su copia .bak). None si ese paso nunca se corrió.

    Si solo está el .pkl del formato viejo, no se lee (leer un pickle puede correr código): FaltaResultado dice
    qué paso volver a correr, en lugar de seguir como si no hubiera resultado."""
    arch = _archivo(nombre)
    if not AR.hay_archivo(arch):
        if (SALIDA / f"{nombre}.pkl").exists():
            raise FaltaResultado(f"salida/v2/{nombre}.pkl está en el formato viejo (pickle) y ya no se lee, porque "
                                 f"leerlo puede correr código. Vuelve a correr ese paso: "
                                 f"{_comando_paso(PASO_DE.get(nombre, nombre))}")
        return None
    return _de_json(AR.leer_json_seguro(arch))

def _memes() -> list[str]:
    return json.loads((RAIZ / "datos" / "memes.json").read_text(encoding="utf-8"))["memes"]


def mercado_diario(reg: Reglamento):
    from . import diario as DI
    return DI.cargar(reg, D.ClienteBinance(reg), _memes())


def DI_generar_conteo(md, clave, params, a, b, con_veto: bool):
    """Señales fuera de muestra de una ventana, con o sin veto (para contar cuántas quita)."""
    from . import diario as DI
    guardado = md.veto
    if not con_veto:
        md.veto = None
    try:
        c = DI.generar(md, clave, params, a - DI.DIA, b)
        return c[(c["t_decision"] >= a) & (c["t_decision"] < b)] if not c.empty else c
    finally:
        md.veto = guardado


def ejecutar(reg: Reglamento, pasos: list[str], avisar=print) -> None:
    cli = D.ClienteBinance(reg)
    md = None
    if "m0" in pasos and "motores" not in pasos:
        pasos = list(pasos) + ["referencias"]
    if any(p in pasos for p in ("referencias", "motores", "m0")):
        t = time.time()
        avisar("Cargando velas diarias…")
        md = mercado_diario(reg)
        avisar(f"  {len(md.velas)} monedas en {time.time() - t:.0f} s")
    if "m0" in pasos and "motores" not in pasos:
        from . import validacion_v2 as V2
        refs = V2.referencias(md)
        avisar("M0 (R1 como candidata)…")
        _guardar_rescatando("M0", V2.evaluar_m0(md, refs), avisar)
        return
    if "referencias" in pasos or "motores" in pasos:
        from . import validacion_v2 as V2
        avisar("Referencias R0, R1, R2…")
        refs = V2.referencias(md)
        _guardar_rescatando("referencias", {k: {"nombre": r.nombre, "metricas": r.metricas, "por_anio": r.por_anio,
                                                "curvas": r.curvas, "invertido": r.invertido}
                                            for k, r in refs.items()}, avisar)
        for k, r in refs.items():
            m = r.metricas["fuera_de_muestra"]
            avisar(f"  {k}: fuera de muestra {m['rend_total_pct']:+.1f} %, caída {m['caida_max_pct']:.1f} %, Calmar {m['calmar']:.2f}")
    if "motores" in pasos:
        from . import validacion_v2 as V2
        calmar_r1 = refs["R1"].metricas["fuera_de_muestra"]["calmar"]
        avisar("M0 (R1 como candidata)…")
        m0 = V2.evaluar_m0(md, refs)
        _guardar_rescatando("M0", m0, avisar)
        for clave in ("M1", "M2"):
            t = time.time()
            avisar(f"Validando {clave}…")
            res = V2.evaluar_lento(md, clave, calmar_r1, avisar=avisar)
            res_guardar = res.__dict__.copy()
            for k in ("mc", "mc_bloques"):
                res_guardar[k] = {a: b for a, b in res_guardar[k].items() if not a.startswith("_")}
            _guardar_rescatando(clave, res_guardar, avisar)
            avisar(f"  {clave}: {'PASA' if res.pasa else 'NO PASA'} en {time.time() - t:.0f} s")
    if "veto" in pasos:
        # Fase C, Paso 2: M1 y M2 con el veto de ESTELA (H2), misma validación completa que sin veto.
        from . import estela as ES
        from . import validacion_v2 as V2
        sin_veto = {clave: cargar_resultado(clave) for clave in ("M1", "M2")}   # antes de cargar nada pesado
        faltan = [clave for clave, r in sin_veto.items() if r is None]
        if faltan:
            raise FaltaResultado(f"Falta el resultado sin veto de {' y '.join(faltan)} (salida/v2/). Corre antes: "
                                 f"{_comando_paso('motores')}")
        if md is None:
            md = mercado_diario(reg)
        refs = V2.referencias(md)
        calmar_r1 = refs["R1"].metricas["fuera_de_muestra"]["calmar"]
        simbolos = sorted(c for c in md.grandes.columns if md.grandes[c].any())
        md.veto = ES.dias_veto_h2(reg, cli, simbolos)
        avisar(f"Veto de ESTELA: datos para {len(md.veto)} monedas")
        for clave in ("M1", "M2"):
            sin = sin_veto[clave]
            sin_cands = sum(len(DI_generar_conteo(md, clave, w["params"], w["inicio"], w["fin"], False)) for w in sin["ventanas"])
            con_cands = sum(len(DI_generar_conteo(md, clave, w["params"], w["inicio"], w["fin"], True)) for w in sin["ventanas"])
            md._ctx.clear()
            t = time.time()
            res = V2.evaluar_lento(md, clave, calmar_r1, avisar=avisar)
            g = res.__dict__.copy()
            for k in ("mc", "mc_bloques"):
                g[k] = {a: b for a, b in g[k].items() if not a.startswith("_")}
            g["candidatos_sin_veto"], g["candidatos_con_veto"] = sin_cands, con_cands
            _guardar_rescatando(f"{clave}_veto", g, avisar)
            avisar(f"  {clave} con veto: {'PASA' if res.pasa else 'NO PASA'} ({sin_cands} → {con_cands} señales "
                   f"fuera de muestra) en {time.time() - t:.0f} s")
        md.veto = None
    if "auditoria" in pasos:
        from . import auditoria as A
        from . import backtest as B
        t = time.time()
        avisar("Cargando velas de 1 h para la auditoría de la v1 (tarda)…")
        m = B.cargar_mercado(reg, cli, _memes())
        avisar(f"  listo en {time.time() - t:.0f} s")
        res = A.ejecutar(m, avisar=avisar)
        _guardar_rescatando("auditoria", res, avisar)
    if "estela" in pasos:
        from . import estela as ES
        res = ES.ejecutar(reg, cli, avisar=avisar)
        _guardar_rescatando("estela", res, avisar)
