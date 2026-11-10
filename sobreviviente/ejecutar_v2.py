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
        _guardar("M0", V2.evaluar_m0(md, refs))
        return
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
    if "veto" in pasos:
        # Fase C, Paso 2: M1 y M2 con el veto de ESTELA (H2), misma validación completa que sin veto.
        from . import estela as ES
        from . import validacion_v2 as V2
        if md is None:
            md = mercado_diario(reg)
        refs = V2.referencias(md)
        calmar_r1 = refs["R1"].metricas["fuera_de_muestra"]["calmar"]
        simbolos = sorted(c for c in md.grandes.columns if md.grandes[c].any())
        md.veto = ES.dias_veto_h2(reg, cli, simbolos)
        avisar(f"Veto de ESTELA: datos para {len(md.veto)} monedas")
        for clave in ("M1", "M2"):
            sin = cargar_resultado(clave)
            sin_cands = sum(len(DI_generar_conteo(md, clave, w["params"], w["inicio"], w["fin"], False)) for w in sin["ventanas"])
            con_cands = sum(len(DI_generar_conteo(md, clave, w["params"], w["inicio"], w["fin"], True)) for w in sin["ventanas"])
            md._ctx.clear()
            t = time.time()
            res = V2.evaluar_lento(md, clave, calmar_r1, avisar=avisar)
            g = res.__dict__.copy()
            for k in ("mc", "mc_bloques"):
                g[k] = {a: b for a, b in g[k].items() if not a.startswith("_")}
            g["candidatos_sin_veto"], g["candidatos_con_veto"] = sin_cands, con_cands
            _guardar(f"{clave}_veto", g)
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
        _guardar("auditoria", res)
    if "estela" in pasos:
        from . import estela as ES
        res = ES.ejecutar(reg, cli, avisar=avisar)
        _guardar("estela", res)
