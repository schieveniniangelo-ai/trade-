"""Genera VALIDACION.md (en español sencillo) y las gráficas PNG."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .validacion import ResultadoValidacion, fechas, ventanas_wf


def _f(x: Any, d: int = 2, signo: bool = False) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.{d}f}" if signo else f"{x:.{d}f}"


def graficas(res: ResultadoValidacion, carpeta: Path) -> dict[str, str]:
    """Curva de capital, caídas de Monte Carlo y mapa de calor de robustez. Requiere matplotlib (opcional)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {}
    carpeta.mkdir(parents=True, exist_ok=True)
    out = {}
    if res.curva_oos is not None and len(res.curva_oos) > 1:
        fig, ax = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
        c = res.curva_oos
        ax[0].plot(c.index, c.values, color="#1f6feb", lw=1.4)
        ax[0].axhline(c.iloc[0], color="#888", lw=0.8, ls="--")
        ax[0].set_title(f"{res.clave} {res.nombre}: capital fuera de muestra (capital de prueba)")
        ax[0].set_ylabel("USDT")
        caida = (c / c.cummax() - 1) * 100
        ax[1].fill_between(caida.index, caida.values, 0, color="#d1242f", alpha=0.5)
        ax[1].set_ylabel("caída %")
        fig.tight_layout()
        p = carpeta / f"{res.clave}_curva.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        out["curva"] = p.name
    if "_caidas" in res.mc:
        fig, ax = plt.subplots(figsize=(7, 3.2))
        ax.hist(res.mc["_caidas"], bins=60, color="#8250df", alpha=0.8)
        ax.axvline(res.mc["caida_p95"], color="#d1242f", ls="--", label=f"peor 5 %: {res.mc['caida_p95']:.1f} %")
        ax.set_title(f"{res.clave}: caídas máximas en 10,000 simulaciones de Monte Carlo")
        ax.set_xlabel("caída máxima (%)")
        ax.legend()
        fig.tight_layout()
        p = carpeta / f"{res.clave}_montecarlo.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        out["mc"] = p.name
    rb = res.robustez
    if rb.get("tabla") and len(rb["ejes"]) == 2:
        pasos = rb["pasos"]
        z = np.array([[rb["tabla"][(a, b)][0] for b in pasos] for a in pasos])
        fig, ax = plt.subplots(figsize=(5.6, 4.6))
        lim = np.nanmax(np.abs(z)) if np.isfinite(z).any() else 1
        im = ax.imshow(z, cmap="RdYlGn", vmin=-lim, vmax=lim, origin="lower")
        ax.set_xticks(range(len(pasos)), [f"{p:+.0f}%" for p in pasos])
        ax.set_yticks(range(len(pasos)), [f"{p:+.0f}%" for p in pasos])
        ax.set_xlabel(rb["ejes"][1])
        ax.set_ylabel(rb["ejes"][0])
        for i in range(len(pasos)):
            for j in range(len(pasos)):
                ax.text(j, i, _f(z[i, j], 2, True), ha="center", va="center", fontsize=8)
        ax.set_title(f"{res.clave}: expectativa (R) al mover parámetros")
        fig.colorbar(im, ax=ax, shrink=0.8)
        fig.tight_layout()
        p = carpeta / f"{res.clave}_robustez.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        out["robustez"] = p.name
    return out


def escribir(resultados: list[ResultadoValidacion], reg, ruta: Path, notas_datos: list[str]) -> None:
    f = fechas(reg)
    vw = ventanas_wf(reg)
    carpeta_img = ruta.parent / "docs" / "img"
    L: list[str] = []
    L.append("# VALIDACIÓN DE SOBREVIVIENTE PRO")
    L.append("")
    L.append(f"Generado el {datetime.now():%d/%m/%Y %H:%M} · reglamento {reg.version} · "
             f"datos del {f['inicio']:%d/%m/%Y} al {f['fin']:%d/%m/%Y}.")
    L.append("")
    pasan = [r for r in resultados if r.pasa]
    L.append("## Resumen en una frase")
    L.append("")
    if pasan:
        L.append(f"**Pasaron las pruebas del backtest: {', '.join(r.clave for r in pasan)}.** "
                 "Eso NO significa que vayan a ganar: solo que mostraron una ventaja con los datos del pasado. "
                 "Antes de tocar dinero real necesitan 30 días y 30 operaciones en papel dentro de lo esperado.")
    else:
        L.append("**Ninguna estrategia pasó todas las pruebas.** Eso es un resultado válido y valioso: "
                 "el sistema evita arriesgar dinero en algo que no demostró ventaja.")
    L.append("")
    L.append("| Estrategia | ¿Pasa? | Operaciones fuera de muestra | Expectativa (R) | Factor de ganancia | Caída p95 Monte Carlo | Le gana al azar | Prueba final |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in resultados:
        o = r.oos_r
        L.append(f"| {r.clave} {r.nombre} | {'✅ Sí' if r.pasa else '❌ No'} | {o.get('operaciones', 0)} | "
                 f"{_f(o.get('expectativa_r'), 3, True)} | {_f(o.get('factor_ganancia'))} | "
                 f"{_f(r.mc.get('caida_p95'), 1)} % | {_f(r.azar.get('percentil_estrategia'), 0)} % | "
                 f"{_f(r.holdout.get('expectativa_r'), 3, True)}R en {r.holdout.get('operaciones', 0)} op. |")
    L.append("")
    L.append("**Cómo leer esta tabla:**")
    L.append("- *Expectativa (R)*: lo que deja en promedio cada operación, en unidades de riesgo. +0.10R significa "
             "que, si arriesgas 1 peso por operación, en promedio te quedan 10 centavos ya con comisiones.")
    L.append("- *Factor de ganancia*: lo ganado entre lo perdido. 1.0 = empate; se pide 1.3 o más.")
    L.append("- *Caída p95*: en el peor 5 % de 10,000 simulaciones, cuánto llegaría a caer el capital.")
    L.append("- *Le gana al azar*: a qué porcentaje de 1,000 carteras con entradas al azar (mismas salidas) supera. Se pide 90 %.")
    L.append("- *Prueba final*: los últimos 6 meses, que nadie tocó hasta el final.")
    L.append("")
    L.append("## Cómo se hizo (para que confíes en los números)")
    L.append("")
    L.append(f"- **Periodo:** {f['inicio']:%B %Y} a {f['fin']:%B %Y}. Incluye el mercado bajista de 2022, el lateral de "
             "2023 y los alcistas posteriores.")
    L.append(f"- **Walk-forward:** {len(vw)} ventanas. En cada una se eligen los parámetros con 12 meses y se prueban "
             "en los 3 meses siguientes, que la estrategia no vio. **Solo se reportan esos 3 meses de prueba.**")
    L.append(f"- **Prueba final intocable:** {f['holdout']:%d/%m/%Y} a {f['fin']:%d/%m/%Y}. Se abrió una sola vez, al final.")
    L.append("- **Costos reales:** comisión de Spot 0.10 % por lado; Futuros 0.05 % por lado; deslizamiento de 0.05 % "
             "(grandes), 0.10 % (medianas) y 0.30 % (memes); funding real en Futuros.")
    L.append("- **Sin ver el futuro:** cada señal usa solo velas cerradas y se ejecuta en la apertura de la vela "
             "siguiente. Hay pruebas automáticas que lo garantizan.")
    L.append("- **El mismo motor de riesgo que en vivo:** cada operación pasó por las mismas reglas (calor, posiciones, "
             "topes, régimen de BTC, volatilidad, costos, mínimos de Binance).")
    L.append(f"- **Capital de prueba:** {reg.get('backtest.capital_ventaja'):,.0f} USDT para medir la ventaja sin que "
             f"estorben los mínimos de Binance; además se repite con tus {reg.get('backtest.capital_real')} USDT reales.")
    for n in notas_datos:
        L.append(f"- {n}")
    L.append("")
    for r in resultados:
        L += _seccion(r, graficas(r, carpeta_img))
    L.append("## Lo que estas pruebas NO pueden garantizar")
    L.append("")
    L.append("- El pasado no garantiza el futuro. Los mercados cambian.")
    L.append("- Los resultados con 46 USDT pueden ser muy distintos a los del capital de prueba por los mínimos de Binance.")
    L.append("- El calendario de eventos (Fed, inflación) y los vetos de Noticias no existen en los datos del pasado: "
             "en vivo se saltarán algunas operaciones que el backtest sí tomó.")
    L.append("- Las reglas de Binance (mínimos y decimales) usadas son las actuales; en el pasado algunas eran distintas.")
    ruta.write_text("\n".join(L) + "\n", encoding="utf-8")


def _seccion(r: ResultadoValidacion, imgs: dict[str, str]) -> list[str]:
    L = [f"## {r.clave} — {r.nombre}: {'✅ PASA' if r.pasa else '❌ NO PASA'}", ""]
    L.append(f"Ronda de ajustes {r.ronda_ajuste} de 3 · {r.combos} combinaciones de parámetros probadas · "
             f"parámetros finales: `{r.params_finales}`")
    L.append("")
    L.append("**Compuertas:**")
    L.append("")
    for k, (ok, txt) in r.compuertas.items():
        L.append(f"- {'✅' if ok else '❌'} {txt}")
    L.append("")
    o, c = r.oos_r, r.oos_cartera
    L.append("**Fuera de muestra (los 3 meses de prueba de cada ventana, unidos):**")
    L.append("")
    L.append("| Número | Valor | Qué significa |")
    L.append("|---|---|---|")
    L.append(f"| Operaciones | {o.get('operaciones', 0)} | cuántas veces entró |")
    L.append(f"| % ganadoras | {_f(o.get('pct_ganadoras'), 1)} % | de cada 100 operaciones, cuántas ganaron |")
    L.append(f"| Ganancia promedio | {_f(o.get('ganancia_prom_r'), 2, True)}R | lo que deja una ganadora en promedio |")
    L.append(f"| Pérdida promedio | {_f(o.get('perdida_prom_r'), 2, True)}R | lo que quita una perdedora en promedio |")
    L.append(f"| Expectativa | {_f(o.get('expectativa_r'), 3, True)}R | promedio por operación, ya con costos |")
    L.append(f"| Factor de ganancia | {_f(o.get('factor_ganancia'))} | ganado ÷ perdido |")
    L.append(f"| Peor racha | {o.get('racha_perdedora_max', 0)} pérdidas seguidas | prepárate mentalmente para esto |")
    L.append(f"| Ventanas positivas | {_f(o.get('ventanas_positivas_pct'), 0)} % | en cuántos trimestres ganó |")
    L.append(f"| Rendimiento (capital de prueba) | {_f(c.get('rendimiento_pct'), 1, True)} % | con 1 % de riesgo por operación |")
    L.append(f"| Caída máxima (capital de prueba) | {_f(c.get('caida_max_pct'), 1)} % | lo más que bajó desde un máximo |")
    L.append(f"| Comisiones | {_f(c.get('comisiones_pct_bruto'), 0)} % de la ganancia bruta | lo que se llevó Binance |")
    L.append("")
    if r.mc:
        L.append(f"**Monte Carlo (10,000 simulaciones):** rendimiento entre {_f(r.mc['rend_p5'], 1, True)} % y "
                 f"{_f(r.mc['rend_p95'], 1, True)} % (90 % de los casos; mediana {_f(r.mc['rend_p50'], 1, True)} %). "
                 f"Caída máxima típica {_f(r.mc['caida_p50'], 1)} %, en el peor 5 % {_f(r.mc['caida_p95'], 1)} %. "
                 f"Probabilidad de tocar −15 % (el freno total): {_f(r.mc['prob_caida_alerta'], 1)} %. "
                 f"Racha perdedora típica {r.mc['racha_p50']:.0f}, en el peor 5 % {r.mc['racha_p95']:.0f}.")
        L.append("")
    if r.azar:
        L.append(f"**Contra el azar:** con entradas al azar (mismas salidas, mismos filtros) la expectativa típica fue "
                 f"{_f(r.azar['exp_azar_p50'], 3, True)}R; el 10 % mejor llegó a {_f(r.azar['exp_azar_p90'], 3, True)}R. "
                 f"La estrategia le gana al {_f(r.azar['percentil_estrategia'], 0)} % de ellas.")
        L.append("")
    if r.btc:
        L.append(f"**Contra comprar y aguantar BTC:** en el mismo periodo fuera de muestra BTC hizo "
                 f"{_f(r.btc['oos']['rend_pct'], 1, True)} % con una caída de {_f(r.btc['oos']['caida_pct'], 1)} %; "
                 f"la estrategia {_f(c.get('rendimiento_pct'), 1, True)} % con caída de {_f(c.get('caida_max_pct'), 1)} %. "
                 f"En la prueba final BTC hizo {_f(r.btc['holdout']['rend_pct'], 1, True)} %.")
        L.append("")
    if r.por_regimen:
        L.append("**Por régimen de BTC al entrar:**")
        L.append("")
        L.append("| Régimen | Operaciones | Expectativa | Factor de ganancia |")
        L.append("|---|---|---|---|")
        for k, v in r.por_regimen.items():
            L.append(f"| {k} | {v['operaciones']} | {_f(v['expectativa_r'], 3, True)}R | {_f(v['factor_ganancia'])} |")
        L.append("")
    h = r.holdout
    L.append(f"**Prueba final intocable:** {h.get('operaciones', 0)} operaciones, expectativa "
             f"{_f(h.get('expectativa_r'), 3, True)}R, factor {_f(h.get('factor_ganancia'))}, rendimiento "
             f"{_f(h.get('rendimiento_pct'), 1, True)} %.")
    L.append("")
    if r.real:
        rr = r.real
        L.append(f"**Con tus {46.18} USDT reales:** de {rr['candidatos']} señales que pasaron los demás filtros, "
                 f"se habrían ejecutado {rr['ejecutadas']} y **{rr['saltadas_capital']} se habrían saltado por falta de capital**.")
        if rr.get("capital_necesario_mediana"):
            L.append(f"Para no saltarse la mitad de esas, harían falta unos **{rr['capital_necesario_mediana']:,.0f} USDT**; "
                     f"para no saltarse 3 de cada 4, unos {rr['capital_necesario_p75']:,.0f} USDT.")
        L.append("")
    if r.robustez.get("tabla"):
        L.append(f"**Robustez:** al mover {', '.join(r.robustez['ejes'])} ±20 %, la peor expectativa fue "
                 f"{_f(r.robustez['minimo'], 3, True)}R ({'sigue positiva en todos los casos' if r.robustez['todas_positivas'] else 'en algunos casos se vuelve negativa'}).")
        L.append("")
    L.append("**Ventanas de walk-forward:**")
    L.append("")
    L.append("| Prueba | Parámetros elegidos | Operaciones | Suma de R |")
    L.append("|---|---|---|---|")
    for w in r.ventanas:
        L.append(f"| {w['prueba']} | `{w['params']}` | {w.get('n_prueba', 0)} | {_f(w.get('r_prueba'), 2, True)} |")
    L.append("")
    for k in ("curva", "mc", "robustez"):
        if k in imgs:
            L.append(f"![{k}](docs/img/{imgs[k]})")
    L.append("")
    for n in r.notas:
        L.append(f"> Nota: {n}")
    L.append("")
    return L
