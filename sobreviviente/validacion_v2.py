"""v2: validación de los motores LENTOS (M0, M1, M2) y de las referencias R0–R2.

Compuertas (sección 4 de MAREA, escritas en `reglamento.yaml → validacion.lentos` antes de ver resultados):
1. Operaciones fuera de muestra: ≥ 60 (M1) y ≥ 40 (M2). M0 se evalúa como cartera.
2. Contra el azar "calendario": 1,000 calendarios al azar con el mismo % de tiempo invertido y el mismo
   número de entradas. Debe ganarle al 90 %.
3. Contra R1: Calmar fuera de muestra mayor que el de R1 (no aplica a M0).
4. Remuestreo en bloques de 20 días de los rendimientos diarios → rango de Calmar y de caída máxima.
5. Robustez ±20 % del parámetro y walk-forward 12 + 3 meses. La prueba final (mayo–octubre 2026) se
   reporta, pero ya se abrió en la v1: la prueba limpia es el papel.
Más las de la v1: factor de ganancia ≥ 1.3, expectativa ≥ +0.1R, caída p95 de Monte Carlo ≤ 25 % (se usa
la peor de las dos versiones: suelta y en bloques) y ventanas positivas ≥ 40 % (antes 60 %).

Todo lo de dinero se mide con la curva DIARIA A VALOR DE MERCADO (auditoría A2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import diario as DI
from . import referencias as RF
from .backtest import cartera, curva_diaria
from .metricas import caida_maxima_pct, concentracion, resumen_curva, resumen_r, topes_en_curva
from .reglamento import Reglamento
from .validacion import (bootstrap_diario, clave_params, combinaciones, fechas, filtro_reglas_baratas,
                         montecarlo, montecarlo_bloques, ventanas_wf)

DIA = pd.Timedelta(days=1)


def costo_referencias(reg: Reglamento) -> float:
    """Costo por lado de las referencias: comisión de Spot + deslizamiento de moneda grande."""
    return float(reg.costos["comision_spot_pct"]) + float(reg.costos["deslizamiento_pct"]["grande"])


def periodos(reg: Reglamento) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    f = fechas(reg)
    oos0 = ventanas_wf(reg)[0][2]
    return {"todo": (f["inicio"], f["fin"]), "fuera_de_muestra": (oos0, f["holdout"] - pd.Timedelta(minutes=1)),
            "prueba_final": (f["holdout"], f["fin"])}


# ---------------------------------------------------------------------------
# Referencias
# ---------------------------------------------------------------------------

@dataclass
class Referencia:
    clave: str
    nombre: str
    curvas: dict[str, pd.Series] = field(default_factory=dict)
    invertido: dict[str, pd.Series] = field(default_factory=dict)
    metricas: dict[str, dict[str, Any]] = field(default_factory=dict)
    por_anio: dict[int, float] = field(default_factory=dict)


def referencias(md: DI.MercadoDiario, costo_pct: float | None = None) -> dict[str, Referencia]:
    reg = md.reg
    costo = costo_referencias(reg) if costo_pct is None else costo_pct
    out = {}
    nombres = {"R0": "Aguantar BTC", "R1": "BTC con filtro de marea (media 200 días)",
               "R2": f"Canasta de las {reg.get('universo.canasta_n', 10)} grandes con filtro de marea"}
    for clave, nombre in nombres.items():
        ref = Referencia(clave, nombre)
        for per, (a, b) in periodos(reg).items():
            if clave == "R0":
                c, inv, ops = RF.r0_aguantar(md.btc, a, b, costo)
            elif clave == "R1":
                c, inv, ops = RF.r1_marea(md.btc, md.marea, a, b, costo)
            else:
                c, inv, ops = RF.r2_canasta({s: v for s, v in md.velas.items() if s not in md.memes}, md.grandes,
                                            md.vol_mediano, md.marea, a, b, costo, int(reg.get("universo.canasta_n", 10)))
            ref.curvas[per], ref.invertido[per] = c, inv
            ref.metricas[per] = resumen_curva(c, inv, ops)
        ref.por_anio = RF.por_anio(ref.curvas["todo"])
        out[clave] = ref
    return out


# ---------------------------------------------------------------------------
# Contra el azar "calendario"
# ---------------------------------------------------------------------------

def azar_calendario_operaciones(md: DI.MercadoDiario, ops: pd.DataFrame, inicio, fin, n: int, semilla: int) -> dict[str, Any]:
    """Cada operación real se cambia por otra en la MISMA moneda, con la MISMA duración y el MISMO peso
    (valor ÷ capital al entrar), pero en una fecha al azar en que la moneda estaba en "grandes".
    Así se conservan el número de entradas y el tiempo invertido; solo cambia el CUÁNDO.
    Se compara la suma de (peso × rendimiento neto de costos)."""
    if ops is None or ops.empty:
        return {}
    rng = np.random.default_rng(semilla)
    peso = (ops["valor_usdt"] / ops["capital_entrada"]).to_numpy(float)
    real = float((peso * ops["pnl_unidad"].to_numpy(float) / ops["entrada"].to_numpy(float)).sum())
    sims = np.zeros(n)
    for k, op in enumerate(ops.itertuples(index=False)):
        v = md.velas[op.simbolo]
        o = v["open"].to_numpy(float)
        idx = v.index
        dur = max(1, int(op.velas))
        g = md.grandes[op.simbolo].reindex((idx + DIA).floor("D")).fillna(False).to_numpy(bool)
        ok = g & (idx >= inicio) & (idx < fin)
        ok[len(idx) - dur - 1:] = False
        filas = np.flatnonzero(ok)
        if len(filas) == 0:
            sims += peso[k] * op.pnl_unidad / op.entrada
            continue
        i = rng.choice(filas, size=n, replace=True)
        costo = 2 * (op.comision_pct + op.desliz_pct) / 100
        ret = o[i + 1 + dur] / o[i + 1] - 1 - costo
        sims += peso[k] * np.nan_to_num(ret)
    return {"real": real, "azar_p50": float(np.percentile(sims, 50)), "azar_p90": float(np.percentile(sims, 90)),
            "percentil": float((sims < real).mean() * 100), "n": n}


def azar_calendario_posicion(precios: pd.DataFrame, pos: pd.Series, costo_pct: float, n: int, semilla: int) -> dict[str, Any]:
    """Para M0 (todo adentro o todo afuera de BTC): se revuelven los tramos "adentro" y "afuera" por separado
    y se intercalan → mismo número de entradas y mismo % de tiempo invertido, en otro orden."""
    pos = pos.astype(float)
    r_dia = (precios["open"].shift(-1) / precios["open"] - 1).reindex(pos.index).fillna(0).to_numpy(float)

    def rendimiento(p: np.ndarray) -> float:
        cambio = np.abs(np.diff(np.concatenate([[0.0], p])))
        return float(np.prod(1 + p * r_dia - cambio * costo_pct / 100) - 1)

    p = pos.to_numpy(float)
    real = rendimiento(p)
    tramos = []
    inicio = 0
    for i in range(1, len(p) + 1):
        if i == len(p) or p[i] != p[i - 1]:
            tramos.append((p[inicio], i - inicio))
            inicio = i
    dentro = [L for v, L in tramos if v > 0]
    fuera = [L for v, L in tramos if v == 0]
    rng = np.random.default_rng(semilla)
    sims = np.zeros(n)
    for k in range(n):
        d = list(rng.permutation(dentro)) if dentro else []
        f = list(rng.permutation(fuera)) if fuera else []
        empieza_dentro = rng.random() < 0.5 if d and f else bool(d)
        serie = []
        while d or f:
            if (empieza_dentro and d) or not f:
                serie += [1.0] * int(d.pop())
                empieza_dentro = False
            else:
                serie += [0.0] * int(f.pop())
                empieza_dentro = True
        sims[k] = rendimiento(np.array(serie[: len(p)]))
    return {"real": real, "azar_p50": float(np.percentile(sims, 50)), "azar_p90": float(np.percentile(sims, 90)),
            "percentil": float((sims < real).mean() * 100), "n": n,
            "entradas": len(dentro), "tiempo_invertido_pct": float(p.mean() * 100)}


# ---------------------------------------------------------------------------
# Evaluación de un motor lento (M1 o M2)
# ---------------------------------------------------------------------------

@dataclass
class ResultadoLento:
    clave: str
    nombre: str
    combos: int = 0
    combinaciones: list[str] = field(default_factory=list)
    ventanas: list[dict[str, Any]] = field(default_factory=list)
    oos_r: dict[str, Any] = field(default_factory=dict)
    oos_curva: dict[str, Any] = field(default_factory=dict)
    curva_oos: pd.Series | None = None
    topes: dict[str, Any] = field(default_factory=dict)
    mc: dict[str, Any] = field(default_factory=dict)
    mc_bloques: dict[str, Any] = field(default_factory=dict)
    azar: dict[str, Any] = field(default_factory=dict)
    bootstrap: dict[str, Any] = field(default_factory=dict)
    robustez: dict[str, Any] = field(default_factory=dict)
    params_finales: dict[str, Any] = field(default_factory=dict)
    prueba_final: dict[str, Any] = field(default_factory=dict)
    real: dict[str, dict[str, Any]] = field(default_factory=dict)
    carteras: dict[str, dict[str, Any]] = field(default_factory=dict)
    concentracion_top5: float = float("nan")
    cupo: dict[str, Any] = field(default_factory=dict)
    comisiones: dict[float, dict[str, Any]] = field(default_factory=dict)
    por_anio: dict[str, dict[str, Any]] = field(default_factory=dict)
    calmar_r1_oos: float = float("nan")
    compuertas: dict[str, tuple[bool, str]] = field(default_factory=dict)
    pasa: bool = False
    notas: list[str] = field(default_factory=list)


def _tramo(df: pd.DataFrame, a, b) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["t_decision"] >= a) & (df["t_decision"] < b)]


def _dias_invertido(ops: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.Series:
    """1 si ese día había al menos una posición abierta (para el % del tiempo invertido)."""
    s = pd.Series(0.0, index=idx)
    for op in ops.itertuples(index=False):
        s[(idx > op.t_entrada) & (idx <= op.t_salida)] = 1.0
    return s


def resumen_dinero(ops: pd.DataFrame, capital: float, cierres, a, b) -> tuple[pd.Series, dict[str, Any]]:
    curva = curva_diaria(ops, capital, cierres, a, b)
    inv = _dias_invertido(ops, curva.index) if ops is not None and not ops.empty else pd.Series(0.0, index=curva.index)
    return curva, resumen_curva(curva, inv, 0 if ops is None else len(ops))


def evaluar_lento(md: DI.MercadoDiario, clave: str, calmar_r1_oos: float, avisar=print,
                  hacer_auditoria: bool = True) -> ResultadoLento:
    reg = md.reg
    cfg = reg.estrategias[clave]
    vl = reg.datos["validacion"]["lentos"]
    v = reg.datos["validacion"]
    semilla = int(v["semilla"])
    f = fechas(reg)
    per = periodos(reg)
    oos_a, oos_b = per["fuera_de_muestra"]
    regA = reg.para_cartera("A")
    capital = float(reg.get("backtest.capital_ventaja"))
    cierres = md.cierres()
    res = ResultadoLento(clave=clave, nombre=cfg["nombre"], calmar_r1_oos=calmar_r1_oos)

    grid = combinaciones(cfg["rejilla"])
    res.combos = len(grid)
    res.combinaciones = [clave_params(p) for p in grid]
    cands = {clave_params(p): DI.generar(md, clave, p, f["inicio"], f["fin"]) for p in grid}
    avisar(f"  {clave}: {len(grid)} combinaciones calculadas")

    def elegir(a, b):
        mejor, mejor_e, mejor_n = grid[0], -1e9, 0
        for p in grid:
            t = _tramo(cands[clave_params(p)], a, b)
            t = filtro_reglas_baratas(regA, t) if not t.empty else t
            if len(t) < int(vl["wf_min_operaciones_entrenamiento"]):
                continue
            e = float(t["r"].mean())
            if e > mejor_e:
                mejor, mejor_e, mejor_n = p, e, len(t)
        return mejor, mejor_e, mejor_n

    partes = []
    for (a, b, c, d) in ventanas_wf(reg):
        p, e, nn = elegir(a, b)
        t = _tramo(cands[clave_params(p)], c, d).copy()
        t["ventana"] = f"{c:%Y-%m}"
        partes.append(t)
        res.ventanas.append({"prueba": f"{c:%Y-%m-%d} a {d:%Y-%m-%d}", "params": p, "exp_entrenamiento": e,
                             "n_entrenamiento": nn, "inicio": c, "fin": d})
    oos = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if not oos.empty:
        oos = oos.sort_values(["t_decision", "fuerza", "simbolo"], ascending=[True, False, True]).reset_index(drop=True)

    rc = cartera(regA, oos, capital, md.filtros, [clave], cierres=cierres)
    ops = rc.operaciones
    r = ops["r"].to_numpy(float) if not ops.empty else np.array([])
    res.oos_r = resumen_r(r)
    res.curva_oos, res.oos_curva = resumen_dinero(ops, capital, cierres, oos_a, oos_b)
    res.topes = topes_en_curva(res.curva_oos, float(regA.riesgo["tope_diario_pct"]),
                               float(regA.riesgo["tope_semanal_pct"]), float(regA.riesgo["caida_max_desde_pico_pct"]))
    res.concentracion_top5 = concentracion(r, 5)
    pos = 0
    for w in res.ventanas:
        sub = ops[ops["ventana"] == w["prueba"][:7]] if not ops.empty else ops
        w["n_prueba"] = int(len(sub))
        w["r_prueba"] = float(sub["r"].sum()) if len(sub) else 0.0
        pos += int(w["r_prueba"] > 0)
    res.oos_r["ventanas_positivas_pct"] = pos / len(res.ventanas) * 100 if res.ventanas else 0.0
    con = [w for w in res.ventanas if w["n_prueba"] > 0]
    res.oos_r["ventanas_con_operaciones"] = len(con)
    res.oos_r["ventanas_positivas_de_activas_pct"] = sum(w["r_prueba"] > 0 for w in con) / len(con) * 100 if con else 0.0
    if not ops.empty:
        for anio, sub in ops.groupby(ops["t_decision"].dt.year):
            res.por_anio[str(anio)] = resumen_r(sub["r"].to_numpy(float))

    riesgo = float(regA.riesgo["riesgo_por_operacion_pct"])
    freno = float(regA.riesgo["caida_max_desde_pico_pct"])
    res.mc = montecarlo(r, riesgo, int(v["montecarlo_n"]), semilla, freno)
    res.mc_bloques = montecarlo_bloques(ops, riesgo, int(v["montecarlo_n"]), semilla, freno, int(vl["bloque_dias"]))
    res.azar = azar_calendario_operaciones(md, ops, oos_a, oos_b, int(vl["azar_calendario_n"]), semilla)
    res.bootstrap = bootstrap_diario(res.curva_oos, int(vl["bootstrap_n"]), semilla, int(vl["bloque_dias"]))

    # Parámetros finales (12 meses antes de la prueba final) y prueba final (se reporta)
    p_fin, _, _ = elegir(f["holdout"] - pd.DateOffset(months=int(v["wf_entrenamiento_meses"])), f["holdout"])
    res.params_finales = p_fin
    h = _tramo(cands[clave_params(p_fin)], f["holdout"], f["fin"] + DIA).reset_index(drop=True)
    rh = cartera(regA, h, capital, md.filtros, [clave], cierres=cierres)
    _, dinero_h = resumen_dinero(rh.operaciones, capital, cierres, f["holdout"], f["fin"])
    res.prueba_final = {**resumen_r(rh.operaciones["r"].to_numpy(float) if not rh.operaciones.empty else []),
                        **{k: dinero_h[k] for k in ("rend_total_pct", "caida_max_pct", "calmar")}}

    res.robustez = robustez_lento(md, clave, p_fin, f["inicio"], f["holdout"], float(v["robustez_variacion_pct"]),
                                  regA, capital, cierres)

    # Carteras A y B (capital de prueba) y capital real (46.18) — mismas señales fuera de muestra
    for nombre in ("A", "B"):
        rgc = reg.para_cartera(nombre)
        rk = cartera(rgc, oos, capital, md.filtros, [clave], cierres=cierres)
        curva_k, din = resumen_dinero(rk.operaciones, capital, cierres, oos_a, oos_b)
        res.carteras[nombre] = {**din, **topes_en_curva(curva_k, float(rgc.riesgo["tope_diario_pct"]),
                                                       float(rgc.riesgo["tope_semanal_pct"]),
                                                       float(rgc.riesgo["caida_max_desde_pico_pct"]))}
        cap_real = float(reg.get("carteras.capital_inicial", reg.get("backtest.capital_real")))
        rr = cartera(rgc, oos, cap_real, md.filtros, [clave], cierres=cierres)
        dec = rr.decisiones
        if not dec.empty:
            salt = dec[dec["saltada_por_capital"]]
            _, din_r = resumen_dinero(rr.operaciones, cap_real, cierres, oos_a, oos_b)
            res.real[nombre] = {
                "candidatos": int(len(dec)), "ejecutadas": int(dec["aprobada"].sum()), "saltadas_capital": int(len(salt)),
                "capital_necesario_mediana": float(salt["capital_necesario"].median()) if len(salt) else None,
                "capital_necesario_p75": float(salt["capital_necesario"].quantile(0.75)) if len(salt) else None,
                "rend_total_pct": din_r["rend_total_pct"], "caida_max_pct": din_r["caida_max_pct"],
            }

    if hacer_auditoria:
        res.cupo = auditoria_cupo(regA, oos, capital, md.filtros, clave, cierres, int(vl["orden_azar_n"]), semilla, rc)
        res.comisiones = sensibilidad_comision(md, clave, res.ventanas, [float(x) for x in vl["comisiones_sensibilidad"]],
                                               regA, capital, cierres, oos_a, oos_b)
    res.compuertas = compuertas_lento(reg, res)
    res.pasa = all(ok for ok, _ in res.compuertas.values())
    return res


def robustez_lento(md: DI.MercadoDiario, clave: str, base: dict[str, Any], inicio, fin, variacion: float,
                   reg_cartera: Reglamento, capital: float, cierres) -> dict[str, Any]:
    """Mueve el parámetro −20, −10, 0, +10, +20 % y mide la expectativa de las operaciones que el motor de
    riesgo realmente toma (antes de la prueba final)."""
    eje = list(base)[0]
    pasos = [-variacion, -variacion / 2, 0.0, variacion / 2, variacion]
    tabla = {}
    for d in pasos:
        p = dict(base)
        p[eje] = max(2, int(round(base[eje] * (1 + d / 100))))
        c = DI.generar(md, clave, p, inicio, fin)
        ops = cartera(reg_cartera, c, capital, md.filtros, [clave], cierres=cierres).operaciones if not c.empty else c
        tabla[d] = {"valor": p[eje], "expectativa_r": float(ops["r"].mean()) if len(ops) else float("nan"),
                    "operaciones": int(len(ops))}
    vals = [x["expectativa_r"] for x in tabla.values()]
    return {"eje": eje, "tabla": tabla, "todas_positivas": bool(all(np.isfinite(x) and x > 0 for x in vals)),
            "minimo": float(np.nanmin(vals)) if vals else float("nan")}


def auditoria_cupo(reg_cartera: Reglamento, cands: pd.DataFrame, capital: float, filtros, clave: str, cierres,
                   n: int, semilla: int, base=None) -> dict[str, Any]:
    """Auditoría A8: ¿cuántas señales se quedan fuera por falta de lugar, y elegir por "fuerza" ayuda
    contra elegir al azar entre las señales del mismo día?"""
    if cands is None or cands.empty:
        return {}
    base = base or cartera(reg_cartera, cands, capital, filtros, [clave], cierres=cierres)
    dec = base.decisiones
    fuera = dec[dec["razon"].str.contains("posiciones de normales abiertas|calor lleno", regex=True)]
    rend_fuerza = float(base.curva.iloc[-1] / capital - 1) * 100
    exp_fuerza = float(base.operaciones["r"].mean()) if not base.operaciones.empty else float("nan")
    rends, exps = [], []
    for k in range(n):
        rk = cartera(reg_cartera, cands, capital, filtros, [clave], cierres=cierres, orden_azar=semilla + 100 + k)
        rends.append(float(rk.curva.iloc[-1] / capital - 1) * 100)
        exps.append(float(rk.operaciones["r"].mean()) if not rk.operaciones.empty else float("nan"))
    rends = np.array(rends)
    return {"senales": int(len(dec)), "fuera_por_cupo": int(len(fuera)),
            "rend_por_fuerza_pct": rend_fuerza, "exp_por_fuerza_r": exp_fuerza,
            "rend_azar_p50_pct": float(np.percentile(rends, 50)), "exp_azar_p50_r": float(np.nanmedian(exps)),
            "percentil_fuerza": float((rends < rend_fuerza).mean() * 100), "n": n}


def sensibilidad_comision(md: DI.MercadoDiario, clave: str, ventanas: list[dict[str, Any]], comisiones: list[float],
                          reg_cartera: Reglamento, capital: float, cierres, a, b) -> dict[float, dict[str, Any]]:
    """Auditoría A9: misma selección de parámetros por ventana, con comisión de 0.075 %, 0.10 % y 0.15 % por lado."""
    original = md.reg
    out = {}
    try:
        for com in comisiones:
            md.reg = original.copia_con({"costos.comision_spot_pct": com})
            partes = []
            cache: dict[str, pd.DataFrame] = {}
            a0 = min(w["inicio"] for w in ventanas) - DIA
            b0 = max(w["fin"] for w in ventanas)
            for w in ventanas:
                k = clave_params(w["params"])
                if k not in cache:  # todo el periodo fuera de muestra de una vez (luego se recorta por ventana)
                    cache[k] = DI.generar(md, clave, w["params"], a0, b0)
                partes.append(_tramo(cache[k], w["inicio"], w["fin"]))
            oos = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
            if not oos.empty:
                oos = oos.sort_values(["t_decision", "fuerza", "simbolo"], ascending=[True, False, True]).reset_index(drop=True)
            rg = reg_cartera.copia_con({"costos.comision_spot_pct": com})
            rk = cartera(rg, oos, capital, md.filtros, [clave], cierres=cierres)
            _, din = resumen_dinero(rk.operaciones, capital, cierres, a, b)
            out[com] = {**resumen_r(rk.operaciones["r"].to_numpy(float) if not rk.operaciones.empty else []),
                        "rend_total_pct": din["rend_total_pct"], "calmar": din["calmar"]}
    finally:
        md.reg = original
    return out


def compuertas_lento(reg: Reglamento, res: ResultadoLento) -> dict[str, tuple[bool, str]]:
    c = reg.datos["validacion"]["compuertas"]
    vl = reg.datos["validacion"]["lentos"]
    o = res.oos_r
    out = {}
    minimo = int(vl["min_operaciones_oos"].get(res.clave, c["min_operaciones_oos"]))
    out["operaciones"] = (o.get("operaciones", 0) >= minimo, f"{o.get('operaciones', 0)} operaciones fuera de muestra (mínimo {minimo})")
    fg = o.get("factor_ganancia", 0.0)
    out["factor_ganancia"] = (fg >= c["factor_ganancia_min"], f"factor de ganancia {fg:.2f} (mínimo {c['factor_ganancia_min']})")
    e = o.get("expectativa_r", 0.0)
    out["expectativa"] = (e >= c["expectativa_min_r"], f"expectativa {e:+.3f}R (mínimo +{c['expectativa_min_r']}R)")
    vp = o.get("ventanas_positivas_pct", 0.0)
    vmin = float(vl["ventanas_positivas_min_pct"])
    out["ventanas"] = (vp >= vmin, f"{vp:.0f} % de ventanas positivas (mínimo {vmin:.0f} % para motores lentos; "
                                   f"contando solo las {o.get('ventanas_con_operaciones', 0)} ventanas con operaciones: "
                                   f"{o.get('ventanas_positivas_de_activas_pct', 0):.0f} %)")
    cp = max(res.mc.get("caida_p95", float("inf")), res.mc_bloques.get("caida_p95", float("inf")))
    out["montecarlo"] = (cp <= c["caida_p95_max_pct"], f"caída p95 de Monte Carlo {cp:.1f} % (la peor entre suelto "
                                                       f"y en bloques; máximo {c['caida_p95_max_pct']} %)")
    pz = res.azar.get("percentil", 0.0)
    pmin = float(vl["azar_calendario_percentil_min"])
    out["azar"] = (pz >= pmin, f"le gana al {pz:.1f} % de los calendarios al azar (mínimo {pmin:.0f} %)")
    cal = res.oos_curva.get("calmar", float("nan"))
    out["contra_r1"] = (bool(np.isfinite(cal) and cal > res.calmar_r1_oos),
                        f"Calmar fuera de muestra {cal:.2f} contra {res.calmar_r1_oos:.2f} de R1 (debe ser mayor)")
    rb = res.robustez
    out["robustez"] = (bool(rb.get("todas_positivas")), f"robustez ±20 %: peor expectativa {rb.get('minimo', float('nan')):+.3f}R")
    return out


# ---------------------------------------------------------------------------
# M0 (= R1) como cartera
# ---------------------------------------------------------------------------

def evaluar_m0(md: DI.MercadoDiario, refs: dict[str, Referencia]) -> dict[str, Any]:
    """M0 se evalúa a nivel cartera: azar calendario, remuestreo en bloques, robustez de la media (±20 %),
    ventanas positivas, prueba final (se reporta) y sensibilidad a comisiones."""
    reg = md.reg
    vl = reg.datos["validacion"]["lentos"]
    v = reg.datos["validacion"]
    semilla = int(v["semilla"])
    per = periodos(reg)
    a, b = per["fuera_de_muestra"]
    costo = costo_referencias(reg)
    r1 = refs["R1"]
    out: dict[str, Any] = {"metricas": r1.metricas}
    out["azar"] = azar_calendario_posicion(md.btc, r1.invertido["fuera_de_muestra"], costo, int(vl["azar_calendario_n"]), semilla)
    out["bootstrap"] = bootstrap_diario(r1.curvas["fuera_de_muestra"], int(vl["bootstrap_n"]), semilla, int(vl["bloque_dias"]))
    rob = {}
    for d in (-20, -10, 0, 10, 20):
        n = int(round(200 * (1 + d / 100)))
        marea = RF_marea(md, n)
        c, inv, ops = RF.r1_marea(md.btc, marea, a, b, costo)
        rob[d] = {"sma": n, **resumen_curva(c, inv, ops)}
    out["robustez"] = rob
    out["robustez_todas_positivas"] = all(x["rend_total_pct"] > 0 for x in rob.values())
    # Ventanas trimestrales (mismas fechas que el walk-forward)
    pos, total = 0, 0
    curva = r1.curvas["fuera_de_muestra"]
    for (_, _, c0, c1) in ventanas_wf(reg):
        tramo = curva[(curva.index >= c0) & (curva.index < c1)]
        if len(tramo) > 1:
            total += 1
            base = curva[curva.index < c0]
            ref = base.iloc[-1] if len(base) else tramo.iloc[0]
            pos += int(tramo.iloc[-1] > ref)
    out["ventanas_positivas_pct"] = pos / total * 100 if total else 0.0
    out["comisiones"] = {}
    for com in vl["comisiones_sensibilidad"]:
        cc = float(com) + float(reg.costos["deslizamiento_pct"]["grande"])
        c, inv, ops = RF.r1_marea(md.btc, md.marea, a, b, cc)
        out["comisiones"][float(com)] = resumen_curva(c, inv, ops)
    out["topes"] = {}
    for nombre in ("A", "B"):
        rgc = reg.para_cartera(nombre)
        out["topes"][nombre] = topes_en_curva(curva, float(rgc.riesgo["tope_diario_pct"]), float(rgc.riesgo["tope_semanal_pct"]),
                                              float(rgc.riesgo["caida_max_desde_pico_pct"]))
    # Cómo le iría a M0 DENTRO de las carteras (motor de riesgo, stop de catástrofe de 15 %, máximo 30 % por posición)
    out["carteras"] = {}
    cierres = md.cierres()
    capital = float(reg.get("backtest.capital_ventaja"))
    cands = DI.generar(md, "M0", {"sma": 200}, a - DIA, b)
    cands = _tramo(cands, a, b)
    for nombre in ("A", "B"):
        rgc = reg.para_cartera(nombre)
        rk = cartera(rgc, cands, capital, md.filtros, ["M0"], cierres=cierres)
        curva_k, din = resumen_dinero(rk.operaciones, capital, cierres, a, b)
        out["carteras"][nombre] = {**din, **resumen_r(rk.operaciones["r"].to_numpy(float) if not rk.operaciones.empty else []),
                                   **topes_en_curva(curva_k, float(rgc.riesgo["tope_diario_pct"]), float(rgc.riesgo["tope_semanal_pct"]),
                                                    float(rgc.riesgo["caida_max_desde_pico_pct"]))}
        bk = bootstrap_diario(curva_k, int(vl["bootstrap_n"]), semilla, int(vl["bloque_dias"]))
        out["carteras"][nombre]["bootstrap_caida_p95"] = bk.get("caida_p95", float("nan"))
        out["carteras"][nombre]["bootstrap_calmar_p5"] = bk.get("calmar_p5", float("nan"))
        cap_real = float(reg.get("carteras.capital_inicial", 46.18))
        rr = cartera(rgc, cands, cap_real, md.filtros, ["M0"], cierres=cierres)
        dec = rr.decisiones
        out["carteras"][nombre]["real_ejecutadas"] = int(dec["aprobada"].sum()) if not dec.empty else 0
        out["carteras"][nombre]["real_saltadas_capital"] = int(dec["saltada_por_capital"].sum()) if not dec.empty else 0
    pz = out["azar"].get("percentil", 0.0)
    out["compuertas"] = {
        "azar": (pz >= float(vl["azar_calendario_percentil_min"]),
                 f"le gana al {pz:.1f} % de los calendarios al azar (mínimo {float(vl['azar_calendario_percentil_min']):.0f} %)"),
        "ventanas": (out["ventanas_positivas_pct"] >= float(vl["ventanas_positivas_min_pct"]),
                     f"{out['ventanas_positivas_pct']:.0f} % de trimestres positivos (mínimo {float(vl['ventanas_positivas_min_pct']):.0f} %)"),
        "robustez": (out["robustez_todas_positivas"], "media de 160 a 240 días: " +
                     ("positiva en todos los casos" if out["robustez_todas_positivas"] else "negativa en algún caso")),
        "caida_bootstrap": (out["bootstrap"].get("caida_p95", 100) <= float(v["compuertas"]["caida_p95_max_pct"]),
                            f"caída p95 del remuestreo en bloques {out['bootstrap'].get('caida_p95', float('nan')):.1f} % "
                            f"(máximo {v['compuertas']['caida_p95_max_pct']} %)"),
    }
    out["pasa"] = all(ok for ok, _ in out["compuertas"].values())
    return out


def RF_marea(md: DI.MercadoDiario, n: int) -> pd.Series:
    from . import regimen as RG
    return RG.marea_diaria(md.btc, md.reg.copia_con({"regimen.diario.sma_btc_dias": n}))
