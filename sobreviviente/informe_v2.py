"""Escribe VALIDACION_V2.md con los resultados guardados en salida/v2/*.pkl (mismo estilo que VALIDACION.md)."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

from .ejecutar_v2 import cargar_resultado
from .reglamento import Reglamento


def _p(x: Any, d: int = 1, signo: bool = False) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(x):
        return "∞" if x > 0 else "—"
    return f"{x:+.{d}f}" if signo else f"{x:.{d}f}"


def _ok(b: bool) -> str:
    return "✅" if b else "❌"


def _compuertas(c: dict) -> list[str]:
    return [f"- {_ok(ok)} {txt}" for ok, txt in c.values()]


def escribir(reg: Reglamento, destino: Path) -> None:
    refs = cargar_resultado("referencias") or {}
    m0 = cargar_resultado("M0") or {}
    m1 = cargar_resultado("M1") or {}
    m2 = cargar_resultado("M2") or {}
    au = cargar_resultado("auditoria") or {}
    es = cargar_resultado("estela") or {}
    vetos = {k: cargar_resultado(f"{k}_veto") for k in ("M1", "M2")}
    vetos = {k: v for k, v in vetos.items() if v}
    L: list[str] = []
    w = L.append
    w("# VALIDACIÓN V2 — \"MAREA\"")
    w("")
    w(f"Generado el {datetime.now():%d/%m/%Y %H:%M} · reglamento {reg.version} · datos del 01/01/2022 al 31/10/2026.")
    w("")
    motores = {"M1": m1, "M2": m2}
    pasa_alguno = any(x.get("pasa") for x in motores.values())
    r1 = refs.get("R1", {}).get("metricas", {})
    cal_r1 = r1.get("fuera_de_muestra", {}).get("calmar", float("nan"))
    w("## Resumen en una frase")
    w("")
    if pasa_alguno:
        nombres = ", ".join(k for k, x in motores.items() if x.get("pasa"))
        w(f"**{nombres} pasa(n) todas las compuertas históricas** y va(n) a PAPEL. Para dinero real faltan 6 semanas y 10 operaciones de papel, "
          "cero errores de conciliación y el OK de Ángelo.")
    else:
        w("**Ningún motor nuevo pasó todas las compuertas ni le ganó a la referencia R1 (BTC con filtro de marea).** "
          "Por la regla de la v2, **R1 pasa a ser la candidata (M0) y es la que corre en PAPEL** como línea base. "
          "Todo lo demás queda APAGADO. Nunca se promete ganancia.")
    w("")
    w("| Motor | ¿Pasa? | Operaciones fuera de muestra | Expectativa (R) | Factor de ganancia | Calmar fuera de muestra | Le gana al azar (calendario) | Caída p95 (bloques) | Prueba final (ya abierta) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for k, x in motores.items():
        if not x:
            w(f"| {k} | — | sin resultado | | | | | | |")
            continue
        o = x["oos_r"]
        pf = x.get("prueba_final", {})
        w(f"| {k} {x['nombre']} | {_ok(x['pasa'])} | {o.get('operaciones', 0)} | {_p(o.get('expectativa_r'), 3, True)} | "
          f"{_p(o.get('factor_ganancia'), 2)} | {_p(x['oos_curva'].get('calmar'), 2)} | {_p(x['azar'].get('percentil'), 0)} % | "
          f"{_p(x['mc_bloques'].get('caida_p95'))} % | {pf.get('operaciones', 0)} op., {_p(pf.get('expectativa_r'), 3, True)}R |")
    if m0:
        mm = m0["metricas"]["fuera_de_muestra"]
        w(f"| M0 Marea BTC (= R1) | {'✅' if m0.get('pasa') else '❌'} (como cartera) | {mm.get('operaciones')} cambios | — | — | "
          f"{_p(mm.get('calmar'), 2)} | {_p(m0['azar'].get('percentil'), 0)} % | {_p(m0['bootstrap'].get('caida_p95'))} % | "
          f"{_p(m0['metricas']['prueba_final'].get('rend_total_pct'), 1, True)} % |")
    w("")
    w("**Cómo leer esta tabla:**")
    w("- *Expectativa (R)*: lo que deja en promedio cada operación, en unidades de riesgo, ya con costos. +0.10R = si arriesgas 1 peso, te quedan 10 centavos.")
    w("- *Factor de ganancia*: lo ganado entre lo perdido. Se pide 1.3 o más.")
    w(f"- *Calmar*: rendimiento por año ÷ la peor caída. Más alto = más ganancia por cada susto. **R1 hizo {_p(cal_r1, 2)} fuera de muestra: hay que ganarle.**")
    w("- *Le gana al azar (calendario)*: a cuántos de 1,000 calendarios al azar (mismas monedas, mismo número de entradas, mismo tiempo invertido, otras fechas) supera. Se pide 90 %.")
    w("- *Caída p95 (bloques)*: en el peor 5 % de 10,000 simulaciones que respetan que las pérdidas llegan juntas, cuánto caería el capital. Máximo 25 %.")
    w("- *Prueba final*: mayo–octubre 2026. **Ya se abrió en la v1**, así que se reporta pero no decide: la prueba limpia es el papel desde hoy.")
    w("")

    # ---------------- Auditoría -----------------
    w("## Auditoría A1–A9 (lo que le faltaba a la v1)")
    w("")
    if au:
        a, b = au["periodo"]
        w(f"Se midió sobre **E1** (la tendencia de la v1) con sus parámetros finales `{au['params']}`, del {a:%d/%m/%Y} al {b:%d/%m/%Y} "
          "(el periodo fuera de muestra de la v1). No se optimizó nada nuevo.")
        w("")
        s, bl = au["A1"]["suelto"], au["A1"]["bloques"]
        w("**A1 — Monte Carlo suelto contra en bloques por fecha.**")
        w("")
        w("| | Suelto (v1) | En bloques de 20 días (v2) | Qué significa |")
        w("|---|---|---|---|")
        w(f"| Caída típica | {_p(s.get('caida_p50'))} % | {_p(bl.get('caida_p50'))} % | la mitad de las simulaciones cae más que esto |")
        w(f"| Caída en el peor 5 % | {_p(s.get('caida_p95'))} % | {_p(bl.get('caida_p95'))} % | lo que se usa para la compuerta |")
        w(f"| Racha perdedora (peor 5 %) | {_p(s.get('racha_p95'), 0)} | {_p(bl.get('racha_p95'), 0)} | pérdidas seguidas |")
        w(f"| Probabilidad de tocar el freno de 15 % | {_p(s.get('prob_caida_alerta'))} % | {_p(bl.get('prob_caida_alerta'))} % | |")
        w("")
        a2 = au["A2"]
        w("**A2 — Caída con operaciones cerradas contra curva diaria a valor de mercado.**")
        w("")
        w("| | Solo cerradas (v1) | A valor de mercado (v2) |")
        w("|---|---|---|")
        w(f"| Caída máxima | {_p(a2['caida_cerradas_pct'])} % | {_p(a2['caida_mercado_pct'])} % |")
        w(f"| Días que tocaron el tope diario | {a2['topes_cerradas']['dias_tope_diario']} | {a2['topes_mercado']['dias_tope_diario']} |")
        w(f"| Semanas que tocaron el tope semanal | {a2['topes_cerradas']['semanas_tope_semanal']} | {a2['topes_mercado']['semanas_tope_semanal']} |")
        w(f"| Veces que se habría activado el freno total | {a2['topes_cerradas']['veces_freno']} | {a2['topes_mercado']['veces_freno']} |")
        w(f"| Rendimiento | {_p(a2['rend_cerradas_pct'], 1, True)} % | {_p(a2['rend_mercado_pct'], 1, True)} % |")
        w("")
        w("Con valor a mercado, los topes y el tamaño de cada operación usan el capital real del momento (las posiciones abiertas que van perdiendo cuentan). "
          "Por eso el número de operaciones y el rendimiento cambian un poco.")
        w("")
        w("**A3 — ¿Qué tanto pesan las reglas de salida?** Misma entrada de E1 y misma muestra de entradas al azar; solo cambia la salida.")
        w("")
        w("| Salida | E1: operaciones | E1: expectativa | E1: % ganadoras | E1: ganancia promedio | Azar: expectativa | Azar: % ganadoras |")
        w("|---|---|---|---|---|---|---|")
        for k, x in au["A3"].items():
            e, z = x["e1"], x["azar"]
            w(f"| ({k}) {x['nombre']} | {e['operaciones']} | {_p(e['expectativa_r'], 3, True)}R | {_p(e['pct_ganadoras'])} % | "
              f"{_p(e['ganancia_prom_r'], 2, True)}R | {_p(z['expectativa_r'], 3, True)}R | {_p(z['pct_ganadoras'])} % |")
        w("")
        a4 = au["A4"]
        w("**A4 — ¿Las monedas chicas arrastraban a E1?**")
        w("")
        w("| Universo | Operaciones | Expectativa | Factor de ganancia | Rendimiento de cartera |")
        w("|---|---|---|---|---|")
        for k, nombre in (("todas", "Todas (456 monedas)"), ("grandes", "Solo las 15 grandes del día"), ("chicas", "Solo las que NO son grandes")):
            x = a4[k]
            w(f"| {nombre} | {x['operaciones']} | {_p(x['expectativa_r'], 3, True)}R | {_p(x['factor_ganancia'], 2)} | "
              f"{_p(x.get('rend_cartera_pct'), 1, True) + ' %' if 'rend_cartera_pct' in x else '—'} |")
        w("")
        w("**A5 — E3 (comprar lo que se desploma) queda archivada.** Le ganó al 0 % del azar en la v1: comprar caídas fue peor que comprar a ciegas. "
          "No se prueban más ideas de \"comprar la caída\"; es evidencia a favor de seguir la tendencia.")
        w("")
        w("**A6 — Memes fuera de la v2.** En la v1, E4 quedó casi en empate con BTC alcista (+0.032R en 45 operaciones) y fatal con BTC bajista (−0.767R).")
        w("")
        conc = au["A7"]["concentracion_top5_pct"]
        if math.isfinite(conc) if isinstance(conc, float) else False:
            txt = f"las 5 mejores operaciones equivalen al {_p(conc, 0)} % de la suma de resultados"
        else:
            txt = "la suma de resultados es negativa, así que la concentración no aplica"
        w(f"**A7 — Concentración.** En E1 (periodo de la auditoría), {txt} (suma total {_p(au['A7']['suma_r'], 1, True)}R). "
          "En la v1, 2 de 14 ventanas dieron casi todo lo positivo: por eso en los motores lentos la compuerta de ventanas positivas baja de 60 % "
          "a 40 % y en cada motor se reporta qué parte del resultado viene de sus 5 mejores operaciones (más de 100 % = sin esas 5, pierde).")
        w("")
        a8 = au.get("A8", {})
        if a8:
            w(f"**A8 — Cupo.** De {a8['senales']} señales de E1, {a8['fuera_por_cupo']} se quedaron fuera por falta de lugar (posiciones o calor lleno). "
              f"Elegir por \"fuerza\" dio {_p(a8['rend_por_fuerza_pct'], 1, True)} %; elegir al azar entre las señales del mismo momento dio "
              f"{_p(a8['rend_azar_p50_pct'], 1, True)} % típico ({a8['n']} repeticiones). La \"fuerza\" le ganó al {_p(a8['percentil_fuerza'], 0)} % de esas elecciones al azar.")
            w("")
        w("**A9 — Sensibilidad a la comisión (por lado).**")
        w("")
        w("| Comisión | Operaciones | Expectativa | Rendimiento de cartera |")
        w("|---|---|---|---|")
        for com, x in au.get("A9", {}).items():
            w(f"| {com:.3f} % | {x['operaciones']} | {_p(x['expectativa_r'], 3, True)}R | {_p(x['rend_cartera_pct'], 1, True)} % |")
        w("")
    else:
        w("_La auditoría no se corrió._")
        w("")

    # ---------------- Referencias -----------------
    w("## Referencias obligatorias (lo simple contra lo que todo compite)")
    w("")
    w("Señal al cierre diario (00:00 UTC), ejecución en la apertura siguiente, comisión 0.10 % + deslizamiento 0.05 % por lado.")
    w("")
    w("| Referencia | Periodo | Rendimiento | Por año | Caída máxima | Calmar | Tiempo invertido | Operaciones |")
    w("|---|---|---|---|---|---|---|---|")
    nombres_per = {"todo": "2022-01 a 2026-10", "fuera_de_muestra": "fuera de muestra (2023-01 a 2026-04)", "prueba_final": "prueba final (2026-05 a 2026-10)"}
    for k, r in refs.items():
        for per, txt in nombres_per.items():
            m = r["metricas"][per]
            w(f"| {k} {r['nombre']} | {txt} | {_p(m['rend_total_pct'], 1, True)} % | {_p(m['rend_anual_pct'], 1, True)} % | "
              f"{_p(m['caida_max_pct'])} % | {_p(m['calmar'], 2)} | {_p(m['tiempo_invertido_pct'], 0)} % | {m['operaciones']} |")
    w("")
    if refs:
        w("**Por año:**")
        w("")
        anios = sorted({a for r in refs.values() for a in r["por_anio"]})
        w("| Referencia | " + " | ".join(str(a) for a in anios) + " |")
        w("|---|" + "---|" * len(anios))
        for k, r in refs.items():
            w(f"| {k} | " + " | ".join(_p(r['por_anio'].get(a), 0, True) + " %" for a in anios) + " |")
        w("")
        w("*Qué significa:* aguantar BTC (R0) gana mucho en los años buenos pero cae hasta 67 %. El filtro de marea (R1) se sale cuando BTC "
          "pierde su media de 200 días: deja ir parte de la subida, pero corta la caída a la mitad. La canasta de grandes (R2) sufrió porque "
          "las altcoins grandes cayeron mucho en 2024–2025 aunque BTC estuviera arriba de su media.")
        w("")

    # ---------------- M0 -----------------
    if m0:
        w("## M0 — R1 como candidata (se evalúa como cartera)")
        w("")
        w("**Compuertas que le aplican:**")
        w("")
        L.extend(_compuertas(m0["compuertas"]))
        w("")
        az = m0["azar"]
        w(f"- Calendario al azar: R1 hizo {_p(az['real'] * 100, 1, True)} % fuera de muestra; un calendario al azar con las mismas {az['entradas']} entradas "
          f"y el mismo {_p(az['tiempo_invertido_pct'], 0)} % de tiempo invertido hizo {_p(az['azar_p50'] * 100, 1, True)} % típico "
          f"(el 10 % mejor, {_p(az['azar_p90'] * 100, 1, True)} %).")
        b = m0["bootstrap"]
        w(f"- Remuestreo en bloques de 20 días: Calmar entre {_p(b.get('calmar_p5'), 2)} y {_p(b.get('calmar_p95'), 2)} (90 % de los casos); "
          f"caída máxima típica {_p(b.get('caida_p50'))} %, en el peor 5 % {_p(b.get('caida_p95'))} %.")
        w("- Robustez de la media (fuera de muestra):")
        w("")
        w("| Media | Rendimiento | Caída máxima | Calmar |")
        w("|---|---|---|---|")
        for d, x in m0["robustez"].items():
            w(f"| {x['sma']} días | {_p(x['rend_total_pct'], 1, True)} % | {_p(x['caida_max_pct'])} % | {_p(x['calmar'], 2)} |")
        w("")
        w("- Sensibilidad a la comisión: " + " · ".join(f"{c:.3f} % → Calmar {_p(x['calmar'], 2)}" for c, x in m0["comisiones"].items()))
        w("")
        w("- Topes con la curva a valor de mercado (todo el dinero en BTC cuando la marea está alta): " +
          " · ".join(f"Cartera {n}: {t['dias_tope_diario']} días de tope diario, {t['veces_freno']} veces el freno total" for n, t in m0["topes"].items()))
        w("")
        if m0.get("carteras"):
            w("**M0 dentro de las carteras** (como correría en papel: motor de riesgo, stop de catástrofe de 15 %, máximo 30 % en BTC), fuera de muestra:")
            w("")
            w("| Cartera | Rendimiento | Caída máxima | Calmar | Caída p95 (bloques) | Operaciones | Con 46.18 USDT: ejecutadas / saltadas por capital |")
            w("|---|---|---|---|---|---|---|")
            for n, cc in m0["carteras"].items():
                w(f"| {n} | {_p(cc['rend_total_pct'], 1, True)} % | {_p(cc['caida_max_pct'])} % | {_p(cc['calmar'], 2)} | "
                  f"{_p(cc.get('bootstrap_caida_p95'))} % | {cc['operaciones']} | {cc['real_ejecutadas']} / {cc['real_saltadas_capital']} |")
            w("")
            w("**Ojo con la Cartera A:** con 1 % de riesgo y un stop de 15 %, la compra sale de unos 3 USDT, menos que el mínimo de 5 USDT de Binance. "
              "Con 46.18 USDT la Cartera A **no puede comprar BTC nunca** con M0 (haría falta capital de unos 88 USDT, como decía la tabla de la especificación). "
              "La Cartera B (2 %) sí cabe.")
            w("")
        w("*Qué significa:* M0 no le gana a nada: ES la referencia. Si va a papel es como línea base honesta. En las carteras A y B corre a través del "
          "motor de riesgo (riesgo por operación ÷ stop de catástrofe de 15 %, máximo 30 % del capital en BTC), así que tiene una parte de BTC, "
          "no todo el dinero; la versión \"todo adentro\" se sigue aparte como referencia R1.")
        w("")

    # ---------------- M1 y M2 -----------------
    for k, x in motores.items():
        if not x:
            continue
        w(f"## {k} — {x['nombre']}: {'✅ PASA' if x['pasa'] else '❌ NO PASA'}")
        w("")
        w(f"Rondas de ajuste usadas: 0 de 1 (se corrió la configuración pre-registrada tal cual) · {x['combos']} combinaciones probadas "
          f"({', '.join(x['combinaciones'])}) · parámetros finales: `{x['params_finales']}`")
        w("")
        w("**Compuertas:**")
        w("")
        L.extend(_compuertas(x["compuertas"]))
        w("")
        o, c = x["oos_r"], x["oos_curva"]
        w("**Fuera de muestra (Cartera A, capital de prueba de 10,000 USDT):**")
        w("")
        w("| Número | Valor | Qué significa |")
        w("|---|---|---|")
        w(f"| Operaciones | {o.get('operaciones', 0)} | cuántas veces entró |")
        w(f"| % ganadoras | {_p(o.get('pct_ganadoras'))} % | de cada 100, cuántas ganaron |")
        w(f"| Ganancia promedio | {_p(o.get('ganancia_prom_r'), 2, True)}R | lo que deja una ganadora |")
        w(f"| Pérdida promedio | {_p(o.get('perdida_prom_r'), 2, True)}R | lo que quita una perdedora |")
        w(f"| Expectativa | {_p(o.get('expectativa_r'), 3, True)}R | promedio por operación, ya con costos |")
        w(f"| Factor de ganancia | {_p(o.get('factor_ganancia'), 2)} | ganado ÷ perdido |")
        w(f"| Peor racha | {o.get('racha_perdedora_max', 0)} pérdidas seguidas | prepárate para esto |")
        w(f"| Ventanas positivas | {_p(o.get('ventanas_positivas_pct'), 0)} % | en cuántos trimestres ganó (se pide 40 %) |")
        w(f"| Concentración | {_p(x.get('concentracion_top5'), 0)} % | qué parte del resultado viene de las 5 mejores operaciones |")
        w(f"| Rendimiento (valor a mercado) | {_p(c.get('rend_total_pct'), 1, True)} % | con 1 % de riesgo por operación |")
        w(f"| Caída máxima (valor a mercado) | {_p(c.get('caida_max_pct'))} % | lo más que bajó desde un máximo |")
        w(f"| Calmar | {_p(c.get('calmar'), 2)} | contra {_p(x.get('calmar_r1_oos'), 2)} de R1 |")
        w(f"| Tiempo con alguna posición | {_p(c.get('tiempo_invertido_pct'), 0)} % | |")
        w("")
        mc, mb = x["mc"], x["mc_bloques"]
        w(f"**Monte Carlo (10,000):** suelto → caída p95 {_p(mc.get('caida_p95'))} %; en bloques de 20 días → caída p95 {_p(mb.get('caida_p95'))} %, "
          f"racha perdedora p95 {_p(mb.get('racha_p95'), 0)}. Rendimiento en bloques entre {_p(mb.get('rend_p5'), 1, True)} % y {_p(mb.get('rend_p95'), 1, True)} %.")
        w("")
        az = x["azar"]
        if az:
            w(f"**Contra el azar (calendario):** la suma de (peso × rendimiento) real fue {_p(az['real'] * 100, 2, True)} %; la típica de 1,000 calendarios al azar "
              f"{_p(az['azar_p50'] * 100, 2, True)} % y el 10 % mejor {_p(az['azar_p90'] * 100, 2, True)} %. Le gana al {_p(az['percentil'], 0)} %.")
            w("")
        b = x["bootstrap"]
        if b:
            w(f"**Remuestreo en bloques de 20 días (curva diaria):** Calmar entre {_p(b.get('calmar_p5'), 2)} y {_p(b.get('calmar_p95'), 2)}; "
              f"caída máxima entre {_p(b.get('caida_p5'))} % y {_p(b.get('caida_p95'))} %.")
            w("")
        rb = x["robustez"]
        if rb:
            w("**Robustez ±20 %** (" + rb["eje"] + "): " + " · ".join(
                f"{v['valor']} → {_p(v['expectativa_r'], 3, True)}R ({v['operaciones']} op.)" for v in rb["tabla"].values()))
            w("")
        pf = x["prueba_final"]
        w(f"**Prueba final (mayo–octubre 2026, ya abierta, solo se reporta):** {pf.get('operaciones', 0)} operaciones, expectativa "
          f"{_p(pf.get('expectativa_r'), 3, True)}R, rendimiento {_p(pf.get('rend_total_pct'), 1, True)} %.")
        w("")
        w("**Cartera A contra Cartera B (mismas señales, capital de prueba):**")
        w("")
        w("| Cartera | Rendimiento | Caída máxima | Calmar | Días de tope diario | Veces el freno total |")
        w("|---|---|---|---|---|---|")
        for n, cc in x["carteras"].items():
            w(f"| {n} | {_p(cc['rend_total_pct'], 1, True)} % | {_p(cc['caida_max_pct'])} % | {_p(cc['calmar'], 2)} | {cc['dias_tope_diario']} | {cc['veces_freno']} |")
        w("")
        w("*Qué significa:* A y B ven las mismas señales, pero B tiene 2 lugares en vez de 3 y arriesga el doble, así que entran operaciones "
          "distintas. Cuando el resultado cambia tanto según qué señales caben, es señal de que depende de la suerte de cuáles entraron (ver Cupo).")
        w("")
        for n, rr in x["real"].items():
            w(f"**Con 46.18 USDT (Cartera {n}):** de {rr['candidatos']} señales se habrían ejecutado {rr['ejecutadas']} y **{rr['saltadas_capital']} se habrían "
              f"saltado por falta de capital**" + (f"; para no saltarse la mitad harían falta unos **{_p(rr['capital_necesario_mediana'], 0)} USDT**" if rr.get('capital_necesario_mediana') else "") + ".")
        w("")
        cu = x.get("cupo") or {}
        if cu:
            w(f"**Cupo (A8):** {cu['fuera_por_cupo']} de {cu['senales']} señales se quedaron fuera por falta de lugar. Elegir por fuerza: "
              f"{_p(cu['rend_por_fuerza_pct'], 1, True)} %; al azar: {_p(cu['rend_azar_p50_pct'], 1, True)} % típico; la fuerza le ganó al {_p(cu['percentil_fuerza'], 0)} %.")
            w("")
        if x.get("comisiones"):
            w("**Comisión (A9):** " + " · ".join(f"{c:.3f} % → {_p(v['expectativa_r'], 3, True)}R, {_p(v['rend_total_pct'], 1, True)} %"
                                                 for c, v in x["comisiones"].items()))
            w("")
        w("**Ventanas de walk-forward (12 meses para elegir, 3 para probar):**")
        w("")
        w("| Prueba | Parámetro elegido | Operaciones | Suma de R |")
        w("|---|---|---|---|")
        for v in x["ventanas"]:
            w(f"| {v['prueba']} | `{v['params']}` | {v.get('n_prueba', 0)} | {_p(v.get('r_prueba'), 2, True)} |")
        w("")
        if x.get("por_anio"):
            w("**Por año:** " + " · ".join(f"{a}: {v['operaciones']} op., {_p(v['expectativa_r'], 2, True)}R" for a, v in x["por_anio"].items()))
            w("")

    # ---------------- ESTELA -----------------
    w("## M3 — ESTELA (copy trade medido)")
    w("")
    if es:
        w(f"- Ruta `data/futures/um/daily/metrics/<SÍMBOLO>/`: {'existe ✅' if es.get('ruta_existe') else 'NO existe ❌'}. BTC tiene datos desde {es.get('btc_desde')}.")
        va = es.get("verificacion_api", {})
        if va.get("ok"):
            w(f"- Significado de las columnas **verificado** contra la API pública de Binance Futuros ({va.get('fecha')}), fila por fila:")
            w("")
            w("| Columna | Ruta de la API | Error mediano |")
            w("|---|---|---|")
            for col, v in va["columnas"].items():
                w(f"| `{col}` | `/futures/data/{v['api']}` | {_p(v['error_mediano'] * 100, 3)} % |")
            w("")
            w("  Así que `top_largo` usa la razón de POSICIONES de los top traders (`sum_toptrader_long_short_ratio`) y `masa_largo` la razón de "
              "CUENTAS de todos (`count_long_short_ratio`), igual que las rutas en vivo de la especificación.")
        else:
            w(f"- Verificación contra la API: {va.get('motivo', 'no se pudo')}")
        desde = es.get("desde_por_simbolo", {})
        if desde:
            w(f"- Monedas \"grandes\" con perpetuo: {len(desde)}. Fecha desde la que hay datos: " +
              ", ".join(f"{s.replace('USDT', '')} {d}" for s, d in sorted(desde.items(), key=lambda z: z[1])) + ".")
        if es.get("sin_perpetuo"):
            w(f"- Sin datos de top traders (no tienen perpetuo o no hay archivo): {', '.join(es['sin_perpetuo'])}.")
        w("")
        est = es.get("estudio", {})
        if est.get("pruebas"):
            w(f"**Estudio de eventos** ({est['panel_filas']} días-moneda, solo días en que la moneda era \"grande\"; {est['n_pruebas']} pruebas en total, todas reportadas):")
            w("")
            w("| Prueba | Días | Eventos | Signo esperado | Efecto (puntos %) | Intervalo 95 % | Años con el signo esperado | ¿Pasa? |")
            w("|---|---|---|---|---|---|---|---|")
            for p in est["pruebas"]:
                lo, hi = p["ic95"]
                w(f"| {p['prueba']} | {p['h']} | {p['eventos']} | {p['signo_esperado']} | {_p(p['efecto_pct'], 2, True)} | "
                  f"[{_p(lo, 2, True)}, {_p(hi, 2, True)}] | {_p(p['anios_mismo_signo_pct'], 0)} % de {p['anios_con_datos']} | {_ok(p['pasa'])} |")
            w("")
            w("*Cómo leerlo:* \"Efecto\" = cuántos puntos porcentuales más (o menos) sube la moneda en los siguientes 3 o 7 días después del evento, comparado con un "
              "día cualquiera. Para pasar, el efecto debe ir en la dirección de la hipótesis en al menos 70 % de los años y su intervalo no debe tocar el cero.")
            w("")
            if es.get("hay_efecto"):
                pasan = [f"{p['prueba']} a {p['h']} días" for p in est["pruebas"] if p["pasa"]]
                w(f"**Resultado: pasa {', '.join(pasan)}** ({len(pasan)} de {est['n_pruebas']} pruebas). Cuando la gente está muy cargada "
                  "en largo, la moneda rinde menos los días siguientes. H1 (seguir a los top traders) NO pasa en ninguna versión; de hecho "
                  "su efecto salió al revés de lo esperado.")
                w("")
                w(f"*Con cuidado:* se hicieron {est['n_pruebas']} pruebas; con tantas, una puede pasar por suerte (al 95 % se esperaría "
                  "media prueba falsa). A favor: H2 tiene el signo esperado en los dos horizontes y a 7 días su intervalo casi no toca el cero.")
                w("")
                w("Por la regla de la v2, el uso principal es el **VETO** de entradas de M1 y M2. Se midieron con y sin veto:")
            else:
                w("**Resultado: el posicionamiento de los top traders NO predijo nada de forma consistente.** M3 se queda APAGADO y no hay veto. "
                  "El bot ESTELA sigue guardando la foto diaria para poder volver a medirlo con datos nuevos.")
            w("")
    else:
        w("_El estudio de ESTELA no se corrió._")
        w("")
    if vetos:
        w("### Paso 2 — M1 y M2 con y sin el veto de ESTELA")
        w("")
        w("Misma validación completa (walk-forward, azar calendario, remuestreo, robustez); la única diferencia es que no se abre una "
          "compra el día en que la masa de cuentas está en el 10 % más cargado en largo de sus 90 días previos (H2). Las monedas sin datos "
          "de ESTELA no se vetan nunca.")
        w("")
        w("| Motor | Versión | Señales fuera de muestra | Operaciones | Expectativa | Factor | Calmar | Azar calendario | Ventanas + | Robustez (peor) | ¿Pasa? |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for k, xv in vetos.items():
            for etiqueta, x in (("sin veto", motores[k]), ("con veto", xv)):
                o = x["oos_r"]
                senales = xv.get("candidatos_sin_veto") if etiqueta == "sin veto" else xv.get("candidatos_con_veto")
                w(f"| {k} | {etiqueta} | {senales} | {o.get('operaciones', 0)} | {_p(o.get('expectativa_r'), 3, True)}R | "
                  f"{_p(o.get('factor_ganancia'), 2)} | {_p(x['oos_curva'].get('calmar'), 2)} | {_p(x['azar'].get('percentil'), 0)} % | "
                  f"{_p(o.get('ventanas_positivas_pct'), 0)} % | {_p(x['robustez'].get('minimo'), 3, True)}R | {_ok(x['pasa'])} |")
        w("")
        for k, xv in vetos.items():
            fallan = [t for ok, t in xv["compuertas"].values() if not ok]
            w(f"- **{k} con veto:** " + ("pasa todas las compuertas." if xv["pasa"] else
                                       f"no pasa {len(fallan)} de {len(xv['compuertas'])} compuertas: " + "; ".join(fallan) + "."))
        w("")
        mejora = {k: xv["oos_r"].get("expectativa_r", 0) - motores[k]["oos_r"].get("expectativa_r", 0) for k, xv in vetos.items()}
        alguno = any(xv["pasa"] for xv in vetos.values())
        w("*Qué significa:* " + " · ".join(f"en {k} el veto cambia la expectativa {_p(d, 3, True)}R por operación" for k, d in mejora.items())
          + (". **Con veto, al menos un motor pasa todas las compuertas.**" if alguno else
             ". **Ni con veto pasan M1 ni M2**, así que siguen APAGADOS y el veto no tiene a quién aplicarse: queda apagado "
             "(`veto_activo: false`). ESTELA sigue guardando la foto diaria para volver a medir con datos nuevos."))
        w("")

    w("## Cuántas cosas se probaron (para que no haya trampa)")
    w("")
    n_m = sum(x.get("combos", 0) for x in motores.values())
    n_e = len(es.get("estudio", {}).get("pruebas", [])) if es else 0
    w(f"- Motores: M1 {m1.get('combos', 0)} combinaciones, M2 {m2.get('combos', 0)} combinaciones (rejillas pre-registradas, 1 ronda de ajustes): {n_m} en total.")
    w("- Referencias: 3 (R0, R1, R2). M0 = R1, sin parámetros que ajustar.")
    w(f"- ESTELA: {n_e} pruebas (2 hipótesis × rejilla × 2 horizontes)" + (f" y {len(vetos)} validaciones con veto (M1 y M2)." if vetos else "."))
    w("- Auditoría: 4 variantes de salida y 3 comisiones sobre E1 (solo para entender la v1; nada de eso se usa para elegir).")
    w("- Todas aparecen en este informe, no solo la mejor.")
    w("")
    w("## Lo que estas pruebas NO pueden garantizar")
    w("")
    w("- El pasado no garantiza el futuro. La prueba realmente limpia es el **papel desde hoy**.")
    w("- Mayo–octubre 2026 ya se había visto en la v1: sus números se reportan, pero ya no son una prueba a ciegas.")
    w("- Con 46.18 USDT muchas señales se saltan por los mínimos de Binance; los resultados con capital de prueba son para medir la idea, no la cuenta.")
    w("- El universo \"grandes\" usa la lista de memes de hoy para excluirlas (algo de sesgo). Las monedas que Binance borró por completo de su API no se pudieron incluir.")
    w("- Desde junio–julio 2026 Binance lista **acciones tokenizadas** con mucho volumen (por ejemplo SNDKB, SOXLB —un fondo apalancado 3x— y SPCXB). "
      "El filtro de universo no las reconoce, así que pudieron entrar a \"grandes\" en los últimos meses del periodo. El 9 nov 2026 tres de las 15 grandes eran de este tipo.")
    w("- Las reglas de Binance (mínimos y decimales) usadas son las actuales; en el pasado algunas eran distintas.")
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")
