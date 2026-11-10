"""v2: corre la validación completa y guarda los resultados (comando `validar --v2`).

Pasos (se pueden correr por separado con --pasos):
  auditoria   A1–A9 sobre E1 de la v1 (necesita las velas de 1 h; es lo más pesado)
  referencias R0, R1, R2
  motores     M1 y M2 con validación completa; M0 como cartera
  estela      verificación de datos de top traders y estudio de eventos (Fase C)
Los resultados se guardan en `salida/v2/<paso>.pkl` y el informe se arma con `informe_v2`.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

from . import datos as D
from .reglamento import Reglamento

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "salida" / "v2"


def _guardar(nombre: str, obj) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    with open(SALIDA / f"{nombre}.pkl", "wb") as f:
        pickle.dump(obj, f)


def cargar_resultado(nombre: str):
    arch = SALIDA / f"{nombre}.pkl"
    if not arch.exists():
        return None
    with open(arch, "rb") as f:
        return pickle.load(f)


def _memes() -> list[str]:
    return json.loads((RAIZ / "datos" / "memes.json").read_text(encoding="utf-8"))["memes"]


def mercado_diario(reg: Reglamento):
    from . import diario as DI
    return DI.cargar(reg, D.ClienteBinance(reg), _memes())


def ejecutar(reg: Reglamento, pasos: list[str], avisar=print) -> None:
    cli = D.ClienteBinance(reg)
    md = None
    if any(p in pasos for p in ("referencias", "motores")):
        t = time.time()
        avisar("Cargando velas diarias…")
        md = mercado_diario(reg)
        avisar(f"  {len(md.velas)} monedas en {time.time() - t:.0f} s")
    if "referencias" in pasos or "motores" in pasos:
        from . import validacion_v2 as V2
        avisar("Referencias R0, R1, R2…")
        refs = V2.referencias(md)
        _guardar("referencias", {k: {"nombre": r.nombre, "metricas": r.metricas, "por_anio": r.por_anio,
                                     "curvas": r.curvas, "invertido": r.invertido} for k, r in refs.items()})
        for k, r in refs.items():
            m = r.metricas["fuera_de_muestra"]
            avisar(f"  {k}: fuera de muestra {m['rend_total_pct']:+.1f} %, caída {m['caida_max_pct']:.1f} %, Calmar {m['calmar']:.2f}")
    if "motores" in pasos:
        from . import validacion_v2 as V2
        calmar_r1 = refs["R1"].metricas["fuera_de_muestra"]["calmar"]
        avisar("M0 (R1 como candidata)…")
        m0 = V2.evaluar_m0(md, refs)
        _guardar("M0", m0)
        for clave in ("M1", "M2"):
            t = time.time()
            avisar(f"Validando {clave}…")
            res = V2.evaluar_lento(md, clave, calmar_r1, avisar=avisar)
            res_guardar = res.__dict__.copy()
            for k in ("mc", "mc_bloques"):
                res_guardar[k] = {a: b for a, b in res_guardar[k].items() if not a.startswith("_")}
            _guardar(clave, res_guardar)
            avisar(f"  {clave}: {'PASA' if res.pasa else 'NO PASA'} en {time.time() - t:.0f} s")
    if "auditoria" in pasos:
        from . import auditoria as A
        from . import backtest as B
        t = time.time()
        avisar("Cargando velas de 1 h para la auditoría de la v1 (tarda)…")
        m = B.cargar_mercado(reg, cli, _memes())
        avisar(f"  listo en {time.time() - t:.0f} s")
        res = A.ejecutar(m, avisar=avisar)
        _guardar("auditoria", res)
    if "estela" in pasos:
        from . import estela as ES
        res = ES.ejecutar(reg, cli, avisar=avisar)
        _guardar("estela", res)
