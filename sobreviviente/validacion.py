"""Validación completa de cada estrategia (comando `validar`).

Pruebas (sección 10 de la especificación):
1. Walk-forward: 12 meses para elegir parámetros, 3 meses para probar; solo se reportan los resultados de prueba.
2. Robustez: parámetros ±20 % (mapa de calor).
3. Monte Carlo: 10,000 remuestreos de las operaciones fuera de muestra.
4. Contra el azar: 1,000 simulaciones con entradas al azar (mismas salidas, mismo número de operaciones).
5. Contra comprar y aguantar BTC.
6. Por régimen de BTC.
7. Prueba final intocable (últimos 6 meses), que solo se abre al final.
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import riesgo as R
from .backtest import Mercado, cartera, contexto, generar_candidatos, simbolos_estrategia
from .estrategias import ESTRATEGIAS
from .metricas import caida_maxima_pct, racha_max, resumen_cartera, resumen_r
from .reglamento import Reglamento

log = logging.getLogger("sobreviviente.validacion")


# ---------------------------------------------------------------------------
# Periodos
# ---------------------------------------------------------------------------

def fechas(reg: Reglamento, sin_holdout: bool = False) -> dict[str, pd.Timestamp]:
    """Periodos. Con `sin_holdout` (ronda 2) el walk-forward llega hasta el final de los datos, porque la
    prueba final de la ronda 1 ya se abrió; se marca `ya_abierto` (mayo–octubre 2026) para reportarlo aparte."""
    inicio = pd.Timestamp(reg.get("backtest.inicio"), tz="UTC")
    fin = pd.Timestamp(reg.get("backtest.fin"), tz="UTC") + pd.Timedelta(hours=23, minutes=59)
    holdout = (pd.Timestamp(reg.get("backtest.fin")) + pd.Timedelta(days=1)
               - pd.DateOffset(months=int(reg.get("validacion.holdout_meses")))).tz_localize("UTC")
    if sin_holdout:
        return {"inicio": inicio, "fin": fin, "holdout": fin + pd.Timedelta(minutes=1), "ya_abierto": holdout}
    return {"inicio": inicio, "fin": fin, "holdout": holdout}


def ventanas_wf(reg: Reglamento, sin_holdout: bool = False) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Ventanas (entrenamiento_inicio, entrenamiento_fin, prueba_inicio, prueba_fin), sin tocar el holdout."""
    f = fechas(reg, sin_holdout)
    ent = int(reg.get("validacion.wf_entrenamiento_meses"))
    pru = int(reg.get("validacion.wf_prueba_meses"))
    out = []
    a = f["inicio"]
    while True:
        p0 = a + pd.DateOffset(months=ent)
        if p0 >= f["holdout"]:
            break
        p1 = min(p0 + pd.DateOffset(months=pru), f["holdout"])
        out.append((a, p0, p0, p1))
        a = a + pd.DateOffset(months=pru)
    return out


def combinaciones(rejilla: dict[str, list[Any]]) -> list[dict[str, Any]]:
    claves = list(rejilla)
    return [dict(zip(claves, vals)) for vals in itertools.product(*(rejilla[k] for k in claves))]


def clave_params(p: dict[str, Any]) -> str:
    return ",".join(f"{k}={p[k]}" for k in sorted(p))


# ---------------------------------------------------------------------------
# Monte Carlo y azar
# ---------------------------------------------------------------------------

def montecarlo(r: np.ndarray, riesgo_pct: float, n: int, semilla: int, caida_alerta_pct: float) -> dict[str, Any]:
    """Remuestrea las operaciones (con reemplazo) n veces y mide rendimiento, caída y rachas."""
    r = np.asarray(r, dtype=float)
    if len(r) == 0:
        return {}
    rng = np.random.default_rng(semilla)
    muestras = rng.choice(r, size=(n, len(r)), replace=True)
    curvas = np.cumprod(1 + muestras * riesgo_pct / 100.0, axis=1)
    curvas = np.concatenate([np.ones((n, 1)), curvas], axis=1)
    picos = np.maximum.accumulate(curvas, axis=1)
    caidas = ((picos - curvas) / picos).max(axis=1) * 100
    finales = (curvas[:, -1] - 1) * 100
    rachas = np.array([racha_max(x) for x in muestras[: min(n, 2000)]])
    return {
        "rend_p5": float(np.percentile(finales, 5)), "rend_p50": float(np.percentile(finales, 50)),
        "rend_p95": float(np.percentile(finales, 95)),
        "caida_p50": float(np.percentile(caidas, 50)), "caida_p95": float(np.percentile(caidas, 95)),
        "racha_p50": float(np.percentile(rachas, 50)), "racha_p95": float(np.percentile(rachas, 95)),
        "prob_caida_alerta": float((caidas >= caida_alerta_pct).mean() * 100),
        "_caidas": caidas, "_finales": finales,
    }


def filtro_reglas_baratas(reg: Reglamento, cands: pd.DataFrame) -> pd.DataFrame:
    """Aplica a un grupo de candidatos las reglas de régimen, volatilidad y costos (sin cartera).
    Se usa para que las entradas al azar pasen por los mismos filtros que la estrategia."""
    if cands.empty:
        return cands
    keep = []
    for f in cands.itertuples(index=False):
        vm = R.clasificar_volatilidad(reg, None if pd.isna(f.vol_moneda) else float(f.vol_moneda))
        vb = R.clasificar_volatilidad(reg, None if pd.isna(f.vol_btc) else float(f.vol_btc))
        factor, bloqueo = R.factor_regimen(reg, f.lado, f.cubeta, f.regimen_btc or "LATERAL", vm, vb)
        if bloqueo:
            keep.append(False)
            continue
        c = R.Candidato(f.simbolo, f.mercado, f.lado, f.estrategia, f.cubeta, f.precio_plan, f.stop,
                        None if pd.isna(f.meta) else f.meta, None, f.comision_pct, f.desliz_pct)
        keep.append(c.distancia > 0 and R.revisar_costos(reg, c)[0])
    return cands[np.array(keep, dtype=bool)]


def pool_azar(m: Mercado, clave: str, params: dict[str, Any], inicio: pd.Timestamp, fin: pd.Timestamp,
              tamano: int, semilla: int) -> pd.DataFrame:
    """Entradas al azar (en velas donde la moneda estaba en el universo) con las MISMAS salidas y stops."""
    rng = np.random.default_rng(semilla)
    mod = ESTRATEGIAS[clave]
    elegibles = []
    for s in simbolos_estrategia(m, clave):
        ctx = contexto(m, clave, s)
        from .backtest import DURACION, MIN_VELAS
        if ctx is None or len(ctx.velas) < MIN_VELAS[mod.TEMPORALIDAD]:
            continue
        idx = ctx.velas.index
        sen = mod.senales(ctx, params)
        dia = (idx + DURACION[mod.TEMPORALIDAD]).floor("D")
        try:
            per = m.pertenece[s].reindex(dia).fillna(False).to_numpy(bool)
        except KeyError:
            continue
        ok = per & (idx >= inicio) & (idx < fin) & np.isfinite(sen["stop"].to_numpy(float))
        if clave == "E5":
            liq = m.fut_liquido[s].reindex(dia).fillna(False).to_numpy(bool) if s in m.fut_liquido else np.zeros(len(idx), bool)
            ok &= liq
        filas = np.flatnonzero(ok[:-1])
        elegibles.extend((s, int(i)) for i in filas)
    if not elegibles:
        return pd.DataFrame()
    elegidos = rng.choice(len(elegibles), size=min(tamano, len(elegibles)), replace=False)
    por_simbolo: dict[str, list[int]] = {}
    for k in sorted(elegidos):
        s, i = elegibles[k]
        por_simbolo.setdefault(s, []).append(i)
    return generar_candidatos(m, clave, params, inicio, fin, filas_azar=por_simbolo)


# ---------------------------------------------------------------------------
# Evaluación de una estrategia
# ---------------------------------------------------------------------------

@dataclass
class ResultadoValidacion:
    clave: str
    nombre: str
    ronda_ajuste: int = 1
    combos: int = 0
    ventanas: list[dict[str, Any]] = field(default_factory=list)
    oos_r: dict[str, Any] = field(default_factory=dict)            # métricas en R de las operaciones fuera de muestra
    oos_cartera: dict[str, Any] = field(default_factory=dict)      # métricas en dinero (capital de prueba)
    real: dict[str, Any] = field(default_factory=dict)             # con el capital real de Ángelo
    mc: dict[str, Any] = field(default_factory=dict)
    azar: dict[str, Any] = field(default_factory=dict)
    btc: dict[str, Any] = field(default_factory=dict)
    por_regimen: dict[str, dict[str, Any]] = field(default_factory=dict)
    holdout: dict[str, Any] = field(default_factory=dict)
    robustez: dict[str, Any] = field(default_factory=dict)
    params_finales: dict[str, Any] = field(default_factory=dict)
    compuertas: dict[str, tuple[bool, str]] = field(default_factory=dict)
    pasa: bool = False
    curva_oos: pd.Series | None = None
    notas: list[str] = field(default_factory=list)
    ronda2: bool = False
    ic_inferior: float | None = None      # piso del intervalo de confianza de la expectativa (R)
    ya_abierto: dict[str, Any] = field(default_factory=dict)  # mayo–octubre 2026 (ronda 2)
    por_anio: dict[str, dict[str, Any]] = field(default_factory=dict)


def _btc_periodo(m: Mercado, a: pd.Timestamp, b: pd.Timestamp) -> dict[str, float]:
    c = m.spot1h["BTCUSDT"]["close"]
    tramo = c[(c.index >= a) & (c.index < b)]
    if tramo.empty:
        return {"rend_pct": float("nan"), "caida_pct": float("nan")}
    return {"rend_pct": float((tramo.iloc[-1] / tramo.iloc[0] - 1) * 100), "caida_pct": caida_maxima_pct(tramo.values)}


def evaluar(m: Mercado, clave: str, avisar=print, ronda_ajuste: int = 1, n_azar_pool: int | None = None,
            ronda2: bool = False) -> ResultadoValidacion:
    reg = m.reg
    cfg = reg.estrategias[clave]
    v = reg.datos["validacion"]
    semilla = int(v["semilla"])
    f = fechas(reg, ronda2)
    res = ResultadoValidacion(clave=clave, nombre=cfg["nombre"], ronda_ajuste=ronda_ajuste, ronda2=ronda2)
    riesgo_pct = reg.riesgo_pct_estrategia(clave)
    var = float(v["robustez_variacion_pct"])

    # 1) Candidatos de cada combinación de parámetros (todo el periodo; el holdout se separa después)
    grid = combinaciones(cfg["rejilla"])
    if clave == "E7":
        from .backtest import preparar_rotacion
        vs = set()
        for p in grid:
            for d in (-var, -var / 2, 0.0, var / 2, var):
                vs.add(int(round(p["ventana"] * (1 + d / 100))))
        preparar_rotacion(m, sorted(vs))
    res.combos = len(grid)
    cands: dict[str, pd.DataFrame] = {}
    for p in grid:
        cands[clave_params(p)] = generar_candidatos(m, clave, p, f["inicio"], f["fin"])
    avisar(f"  {clave}: {len(grid)} combinaciones calculadas")

    def tramo(df: pd.DataFrame, a: pd.Timestamp, b: pd.Timestamp) -> pd.DataFrame:
        if df.empty:
            return df
        return df[(df["t_decision"] >= a) & (df["t_decision"] < b)]

    def elegir(a: pd.Timestamp, b: pd.Timestamp) -> tuple[dict[str, Any], float, int]:
        mejor, mejor_exp, mejor_n = grid[0], -1e9, 0
        minimo = int(v["wf_min_operaciones_entrenamiento"])
        for p in grid:
            t = tramo(cands[clave_params(p)], a, b)
            t = filtro_reglas_baratas(reg, t) if not t.empty else t
            n = len(t)
            if n < minimo:
                continue
            e = float(t["r"].mean())
            if e > mejor_exp:
                mejor, mejor_exp, mejor_n = p, e, n
        return mejor, mejor_exp, mejor_n

    # 2) Walk-forward
    partes = []
    for (a, b, c, d) in ventanas_wf(reg, ronda2):
        p, e_ent, n_ent = elegir(a, b)
        t = tramo(cands[clave_params(p)], c, d).copy()
        t["ventana"] = f"{c:%Y-%m}"
        partes.append(t)
        res.ventanas.append({"prueba": f"{c:%Y-%m-%d} a {d:%Y-%m-%d}", "params": p, "exp_entrenamiento": e_ent,
                             "n_entrenamiento": n_ent})
    oos = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if not oos.empty:
        oos = oos.sort_values(["t_decision", "fuerza", "simbolo"], ascending=[True, False, True]).reset_index(drop=True)

    capital = float(reg.get("backtest.capital_ventaja"))
    rc = cartera(reg, oos, capital, m.filtros, [clave])
    ops = rc.operaciones
    r_oos = ops["r"].to_numpy(float) if not ops.empty else np.array([])
    res.oos_r = resumen_r(r_oos)
    res.oos_cartera = resumen_cartera(ops, rc.curva, capital)
    res.curva_oos = rc.curva
    res.oos_cartera["detenciones"] = [f"{x:%Y-%m-%d}" for x in rc.detenciones]
    if rc.detenciones:
        res.notas.append(
            f"Con el capital de prueba, el freno de −15 % se habría activado {len(rc.detenciones)} vez/veces "
            f"({', '.join(res.oos_cartera['detenciones'])}). En el backtest se simuló que Ángelo daba el OK para seguir midiendo.")
    # ventanas positivas
    pos = 0
    for w in res.ventanas:
        etiqueta = w["prueba"][:7]
        sub = ops[ops["ventana"] == etiqueta] if not ops.empty else ops
        w["n_prueba"] = int(len(sub))
        w["r_prueba"] = float(sub["r"].sum()) if len(sub) else 0.0
        w["exp_prueba"] = float(sub["r"].mean()) if len(sub) else 0.0
        pos += int(w["r_prueba"] > 0)
    res.oos_r["ventanas_positivas_pct"] = pos / len(res.ventanas) * 100 if res.ventanas else 0.0
    con_ops = [w for w in res.ventanas if w["n_prueba"] > 0]
    res.oos_r["ventanas_con_operaciones"] = len(con_ops)
    res.oos_r["ventanas_positivas_de_activas_pct"] = (sum(w["r_prueba"] > 0 for w in con_ops) / len(con_ops) * 100) if con_ops else 0.0

    # 3) Capital real de Ángelo
    capital_real = float(reg.get("backtest.capital_real"))
    rr = cartera(reg, oos, capital_real, m.filtros, [clave])
    dec = rr.decisiones
    if not dec.empty:
        saltadas = dec[dec["saltada_por_capital"]]
        res.real = {
            "candidatos": int(len(dec)), "ejecutadas": int(dec["aprobada"].sum()), "saltadas_capital": int(len(saltadas)),
            "capital_necesario_mediana": float(saltadas["capital_necesario"].median()) if len(saltadas) else None,
            "capital_necesario_p75": float(saltadas["capital_necesario"].quantile(0.75)) if len(saltadas) else None,
            **{k: v2 for k, v2 in resumen_cartera(rr.operaciones, rr.curva, capital_real).items()
               if k in ("rendimiento_pct", "caida_max_pct", "comisiones_pct_bruto")},
        }

    # 4) Monte Carlo
    res.mc = montecarlo(r_oos, riesgo_pct, int(v["montecarlo_n"]), semilla,
                        float(reg.riesgo["caida_max_desde_pico_pct"]))

    # 5) Contra el azar
    if len(r_oos) >= 10:
        conteo = pd.Series([clave_params(w["params"]) for w in res.ventanas]).value_counts()
        p_comun = next(w["params"] for w in res.ventanas if clave_params(w["params"]) == conteo.index[0])
        inicio_oos = ventanas_wf(reg, ronda2)[0][2]
        tam = n_azar_pool or int(min(40000, max(5000, 40 * len(r_oos))))
        pool = pool_azar(m, clave, p_comun, inicio_oos, f["holdout"], tam, semilla)
        pool = filtro_reglas_baratas(reg, pool)
        if len(pool) >= len(r_oos):
            rng = np.random.default_rng(semilla + 1)
            pr = pool["r"].to_numpy(float)
            exps = np.array([rng.choice(pr, size=len(r_oos), replace=False).mean() for _ in range(int(v["azar_n"]))])
            res.azar = {"pool": int(len(pool)), "exp_azar_p50": float(np.percentile(exps, 50)),
                        "exp_azar_p90": float(np.percentile(exps, 90)),
                        "percentil_estrategia": float((exps < res.oos_r["expectativa_r"]).mean() * 100),
                        "_exps": exps}
        else:
            res.notas.append("No hubo suficientes entradas al azar para comparar.")

    # 6) BTC comprar y aguantar y 7) por régimen
    if res.ventanas:
        a0 = ventanas_wf(reg, ronda2)[0][2]
        res.btc = {"oos": _btc_periodo(m, a0, f["holdout"]), "holdout": _btc_periodo(m, f["holdout"], f["fin"])}
    if not ops.empty:
        for rg, sub in ops.groupby(ops["regimen_btc"].fillna("SIN DATO")):
            res.por_regimen[rg] = resumen_r(sub["r"].to_numpy(float))

    # Por año (fuera de muestra)
    if not ops.empty:
        for anio, sub in ops.groupby(ops["t_decision"].dt.year):
            res.por_anio[str(anio)] = resumen_r(sub["r"].to_numpy(float))

    # 8) Parámetros finales (elegidos con los 12 meses previos al holdout) y prueba final
    p_fin, _, _ = elegir(f["holdout"] - pd.DateOffset(months=int(v["wf_entrenamiento_meses"])), f["holdout"])
    res.params_finales = p_fin
    if ronda2:
        # La prueba final ya se abrió en la ronda 1: mayo–octubre 2026 se reporta como una ventana más.
        sub = ops[ops["t_decision"] >= f["ya_abierto"]] if not ops.empty else ops
        res.holdout = resumen_r(sub["r"].to_numpy(float) if len(sub) else [])
        res.ya_abierto = res.holdout
        # Piso del intervalo de confianza de la expectativa, corregido por el número de ideas probadas
        r2 = v["ronda2"]
        alfa = float(r2["confianza_base"]) / int(r2["ideas_probadas"])
        if len(r_oos) >= 10:
            rng = np.random.default_rng(semilla + 7)
            medias = rng.choice(r_oos, size=(10000, len(r_oos)), replace=True).mean(axis=1)
            res.ic_inferior = float(np.quantile(medias, alfa))
    else:
        h = tramo(cands[clave_params(p_fin)], f["holdout"], f["fin"])
        rh = cartera(reg, h.reset_index(drop=True), capital, m.filtros, [clave])
        res.holdout = {**resumen_r(rh.operaciones["r"].to_numpy(float) if not rh.operaciones.empty else []),
                       **{k: v2 for k, v2 in resumen_cartera(rh.operaciones, rh.curva, capital).items()
                          if k in ("rendimiento_pct", "caida_max_pct")}}

    # 9) Robustez ±20 % alrededor de los parámetros finales (antes del holdout)
    res.robustez = robustez(m, clave, p_fin, f["inicio"], f["holdout"], var, con_cartera=ronda2)

    # 10) Compuertas
    res.compuertas = compuertas(reg, res)
    res.pasa = all(ok for ok, _ in res.compuertas.values())
    return res


def robustez(m: Mercado, clave: str, base: dict[str, Any], inicio: pd.Timestamp, fin: pd.Timestamp,
             variacion: float, con_cartera: bool = False) -> dict[str, Any]:
    """Mueve los dos parámetros principales en −20, −10, 0, +10 y +20 % y mide la expectativa (en R).

    `con_cartera` (ronda 2): mide con las operaciones que el motor de riesgo realmente toma. Hace falta para
    estrategias que repiten la señal cada día mientras siguen dentro (E6, E7): contar todas las señales
    mediría la misma posición muchas veces."""
    numericos = [k for k, x in base.items() if isinstance(x, (int, float)) and x != 0]
    if len(numericos) < 1:
        return {}
    ejes = numericos[:2]
    pasos = [-variacion, -variacion / 2, 0.0, variacion / 2, variacion]
    tabla = {}
    for d1 in pasos:
        for d2 in (pasos if len(ejes) > 1 else [0.0]):
            p = dict(base)
            for eje, d in zip(ejes, (d1, d2)):
                val = base[eje] * (1 + d / 100.0)
                p[eje] = int(round(val)) if isinstance(base[eje], int) else round(val, 4)
            c = generar_candidatos(m, clave, p, inicio, fin)
            if con_cartera and not c.empty:
                ops = cartera(m.reg, c, float(m.reg.get("backtest.capital_ventaja")), m.filtros, [clave]).operaciones
                c = ops if not ops.empty else ops
            elif not c.empty:
                c = filtro_reglas_baratas(m.reg, c)
            tabla[(d1, d2)] = (float(c["r"].mean()) if len(c) else float("nan"), int(len(c)))
    valores = [x[0] for x in tabla.values()]
    return {"ejes": ejes, "pasos": pasos, "tabla": tabla,
            "todas_positivas": bool(all(np.isfinite(x) and x > 0 for x in valores)),
            "minimo": float(np.nanmin(valores)) if valores else float("nan")}


def compuertas(reg: Reglamento, res: ResultadoValidacion) -> dict[str, tuple[bool, str]]:
    """Compuertas PAPEL → VIVA_MINI que se pueden revisar con el backtest (las de papel se revisan después)."""
    c = reg.datos["validacion"]["compuertas"]
    o = res.oos_r
    out = {}
    out["operaciones"] = (o.get("operaciones", 0) >= c["min_operaciones_oos"],
                          f"{o.get('operaciones', 0)} operaciones fuera de muestra (mínimo {c['min_operaciones_oos']})")
    fg = o.get("factor_ganancia", 0.0)
    out["factor_ganancia"] = (fg >= c["factor_ganancia_min"], f"factor de ganancia {fg:.2f} (mínimo {c['factor_ganancia_min']})")
    e = o.get("expectativa_r", 0.0)
    out["expectativa"] = (e >= c["expectativa_min_r"], f"expectativa {e:+.3f}R (mínimo +{c['expectativa_min_r']}R)")
    vp = o.get("ventanas_positivas_pct", 0.0)
    out["ventanas"] = (vp >= c["ventanas_positivas_min_pct"], f"{vp:.0f} % de ventanas positivas (mínimo {c['ventanas_positivas_min_pct']} %; "
                       f"contando solo las {o.get('ventanas_con_operaciones', 0)} ventanas con operaciones: "
                       f"{o.get('ventanas_positivas_de_activas_pct', 0):.0f} %)")
    cp = res.mc.get("caida_p95", float("inf"))
    out["montecarlo"] = (cp <= c["caida_p95_max_pct"], f"caída p95 de Monte Carlo {cp:.1f} % (máximo {c['caida_p95_max_pct']} %)")
    pz = res.azar.get("percentil_estrategia", 0.0)
    minimo_azar = float(c["azar_percentil_min"])
    if res.ronda2:
        r2 = reg.datos["validacion"]["ronda2"]
        minimo_azar = 100.0 - float(r2["azar_base_pct"]) / int(r2["ideas_probadas"])
    out["azar"] = (pz >= minimo_azar, f"le gana al {pz:.1f} % de las entradas al azar (mínimo {minimo_azar:.2f} %)")
    h = res.holdout
    hok = h.get("operaciones", 0) > 0 and h.get("expectativa_r", 0) > 0 and h.get("factor_ganancia", 0) > 1.0
    etiqueta = "mayo–octubre 2026 (ya abierto, como una ventana más)" if res.ronda2 else "prueba final"
    out["prueba_final"] = (hok, f"{etiqueta}: {h.get('operaciones', 0)} operaciones, expectativa "
                                f"{h.get('expectativa_r', 0):+.3f}R, factor {h.get('factor_ganancia', 0):.2f}")
    if res.ronda2:
        r2 = reg.datos["validacion"]["ronda2"]
        conf = 100 * (1 - float(r2["confianza_base"]) / int(r2["ideas_probadas"]))
        ic = res.ic_inferior
        out["confianza"] = (ic is not None and ic > 0,
                            f"piso del intervalo de confianza del {conf:.1f} %: "
                            f"{'—' if ic is None else f'{ic:+.3f}R'} (debe ser mayor que 0R)")
    rb = res.robustez
    out["robustez"] = (bool(rb.get("todas_positivas")), f"robustez ±20 %: peor expectativa {rb.get('minimo', float('nan')):+.3f}R")
    return out
