"""v2: auditoría de la v1 (puntos A1 a A9 de MAREA) aplicada a E1, la estrategia de tendencia de la v1.

Se usan los parámetros finales que la v1 ya había elegido para E1 (VALIDACION.md) y el periodo fuera de
muestra de la v1 (enero 2023 a abril 2026). No se optimiza nada nuevo: solo se mide.

A1  Monte Carlo suelto contra Monte Carlo en bloques por fecha.
A2  Caída y topes con la curva diaria a valor de mercado contra la de operaciones cerradas.
A3  Prueba de salidas: (a) actual, (b) sin "+1R → entrada", (c) sin "+1R" y stop dinámico de 5 ATR,
    (d) salida por canal como M1. En E1 y en entradas al azar, misma muestra.
A4  E1 solo con las 15 "grandes" contra todo el universo.
A5, A6  Conclusiones (E3 y E4 se archivan): no requieren cálculo nuevo.
A7  Concentración: qué parte de la ganancia viene de las 5 mejores operaciones (se reporta en la v2).
A8  Señales fuera por cupo y "elegir por fuerza" contra "elegir al azar".
A9  Sensibilidad a la comisión: 0.075 %, 0.10 % y 0.15 % por lado.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import universo as U
from .backtest import Mercado, cartera, curva_diaria, generar_candidatos
from .metricas import caida_maxima_pct, concentracion, resumen_r, topes_en_curva
from .validacion import (filtro_reglas_baratas, fechas, montecarlo, montecarlo_bloques, pool_azar, ventanas_wf)
from .validacion_v2 import auditoria_cupo

E1_PARAMS_V1 = {"donchian_n": 55, "stop_atr": 3.0, "chandelier_atr": 3.0}  # finales de la v1 (VALIDACION.md)

VARIANTES_SALIDA = {
    "a": ("actual: stop dinámico 3 ATR + \"+1R → entrada\"", None),
    "b": ("sin \"+1R → entrada\"", {"sin_breakeven": True}),
    "c": ("sin \"+1R\" y stop dinámico de 5 ATR", {"sin_breakeven": True, "chandelier_atr": 5.0}),
    "d": ("salida por canal como M1 (mínimo de 27 velas)", {"sin_breakeven": True, "modo": "canal", "canal_velas": 27}),
}


def cierres_diarios(m: Mercado) -> dict[str, pd.Series]:
    out = {}
    for s, df in m.spot1d.items():
        c = df["close"].copy()
        c.index = c.index + pd.Timedelta(days=1)
        out[s] = c
    return out


def _resumen(c: pd.DataFrame) -> dict[str, Any]:
    r = c["r"].to_numpy(float) if not c.empty else np.array([])
    return resumen_r(r)


def ejecutar(m: Mercado, avisar=print, n_azar: int = 20000) -> dict[str, Any]:
    reg = m.reg
    v = reg.datos["validacion"]
    semilla = int(v["semilla"])
    f = fechas(reg)
    a = ventanas_wf(reg)[0][2]
    b = f["holdout"]
    capital = float(reg.get("backtest.capital_ventaja"))
    cierres = cierres_diarios(m)
    out: dict[str, Any] = {"params": E1_PARAMS_V1, "periodo": (a, b)}

    avisar("  A: señales de E1 (parámetros finales de la v1)…")
    cands = generar_candidatos(m, "E1", E1_PARAMS_V1, a, b)
    cands_f = filtro_reglas_baratas(reg, cands)

    # ---- A1 y A2 -------------------------------------------------------------------------------
    avisar("  A1/A2: Monte Carlo en bloques y curva a valor de mercado…")
    rc_cerradas = cartera(reg, cands, capital, m.filtros, ["E1"])
    rc_mercado = cartera(reg, cands, capital, m.filtros, ["E1"], cierres=cierres)
    ops = rc_mercado.operaciones
    r = ops["r"].to_numpy(float)
    riesgo = reg.riesgo_pct_estrategia("E1")
    freno = float(reg.riesgo["caida_max_desde_pico_pct"])
    mc = montecarlo(r, riesgo, int(v["montecarlo_n"]), semilla, freno)
    mcb = montecarlo_bloques(ops, riesgo, int(v["montecarlo_n"]), semilla, freno, 20)
    curva_d = curva_diaria(ops, capital, cierres, a, b)
    tope_d, tope_s = float(reg.riesgo["tope_diario_pct"]), float(reg.riesgo["tope_semanal_pct"])
    out["A1"] = {"suelto": {k: x for k, x in mc.items() if not k.startswith("_")},
                 "bloques": {k: x for k, x in mcb.items() if not k.startswith("_")}, "operaciones": len(r)}
    cerr = rc_cerradas.curva
    out["A2"] = {
        "caida_cerradas_pct": caida_maxima_pct(cerr.values),
        "caida_mercado_pct": caida_maxima_pct(curva_d.values),
        "topes_cerradas": topes_en_curva(cerr.resample("1D").last().ffill(), tope_d, tope_s, freno),
        "topes_mercado": topes_en_curva(curva_d, tope_d, tope_s, freno),
        "rend_cerradas_pct": float(cerr.iloc[-1] / capital - 1) * 100,
        "rend_mercado_pct": float(curva_d.iloc[-1] / capital - 1) * 100,
        "operaciones_cerradas": len(rc_cerradas.operaciones), "operaciones_mercado": len(ops),
    }

    # ---- A3 -------------------------------------------------------------------------------------
    avisar("  A3: prueba de salidas (E1 y azar)…")
    a3 = {}
    tam = int(min(40000, max(5000, n_azar)))
    for k, (nombre, go) in VARIANTES_SALIDA.items():
        ce = cands if go is None else generar_candidatos(m, "E1", E1_PARAMS_V1, a, b, gest_override=go)
        ce = filtro_reglas_baratas(reg, ce)
        pz = filtro_reglas_baratas(reg, pool_azar(m, "E1", E1_PARAMS_V1, a, b, tam, semilla, gest_override=go))
        rk = cartera(reg, ce, capital, m.filtros, ["E1"], cierres=cierres)
        a3[k] = {"nombre": nombre, "e1": _resumen(ce), "azar": _resumen(pz),
                 "e1_cartera_rend_pct": float(rk.curva.iloc[-1] / capital - 1) * 100 if len(rk.curva) else 0.0}
        avisar(f"    ({k}) {nombre}: E1 {a3[k]['e1']['expectativa_r']:+.3f}R · azar {a3[k]['azar']['expectativa_r']:+.3f}R")
    out["A3"] = a3

    # ---- A4 -------------------------------------------------------------------------------------
    avisar("  A4: E1 solo con las 15 grandes…")
    g = U.grandes(m.vol_mediano, m.pertenece, m.memes, int(reg.get("universo.grandes_n", 15)))
    dias = cands_f["t_decision"].dt.floor("D")
    en_g = np.array([bool(g.at[d, s]) if (d in g.index and s in g.columns) else False
                     for d, s in zip(dias, cands_f["simbolo"])], dtype=bool)
    cg = cands_f[en_g]
    rg = cartera(reg, cands[cands.index.isin(cands_f.index[en_g])], capital, m.filtros, ["E1"], cierres=cierres)
    out["A4"] = {"todas": {**_resumen(cands_f), "rend_cartera_pct": float(rc_mercado.curva.iloc[-1] / capital - 1) * 100},
                 "grandes": {**_resumen(cg), "rend_cartera_pct": float(rg.curva.iloc[-1] / capital - 1) * 100 if len(rg.curva) else 0.0},
                 "chicas": _resumen(cands_f[~en_g])}

    # ---- A7 (concentración de E1) ----------------------------------------------------------------
    out["A7"] = {"concentracion_top5_pct": concentracion(r, 5), "suma_r": float(r.sum())}

    # ---- A8 -------------------------------------------------------------------------------------
    avisar("  A8: cupo y elegir por fuerza contra azar…")
    out["A8"] = auditoria_cupo(reg, cands, capital, m.filtros, "E1", cierres, int(reg.get("validacion.lentos.orden_azar_n", 200)),
                               semilla, rc_mercado)

    # ---- A9 -------------------------------------------------------------------------------------
    avisar("  A9: sensibilidad a la comisión…")
    a9 = {}
    original = m.reg
    try:
        for com in reg.get("validacion.lentos.comisiones_sensibilidad", [0.075, 0.10, 0.15]):
            m.reg = original.copia_con({"costos.comision_spot_pct": float(com)})
            ck = generar_candidatos(m, "E1", E1_PARAMS_V1, a, b)
            rk = cartera(m.reg, ck, capital, m.filtros, ["E1"], cierres=cierres)
            a9[float(com)] = {**_resumen(filtro_reglas_baratas(m.reg, ck)),
                              "rend_cartera_pct": float(rk.curva.iloc[-1] / capital - 1) * 100}
    finally:
        m.reg = original
    out["A9"] = a9
    return out
