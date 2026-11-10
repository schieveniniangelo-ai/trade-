"""Ronda 2 de estrategias (pedida por Ángelo el 10/11/2026) → VALIDACION_RONDA2.md."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import informe
from . import referencias as RF
from . import regimen as RG
from .backtest import Mercado, preparar_rotacion
from .estrategias import e7 as E7
from .validacion import evaluar, fechas

CLAVES = ["E1D", "E6", "E7"]


def _f(x, d=1, signo=False):
    return informe._f(x, d, signo)


def referencias(m: Mercado) -> dict:
    """Curvas de comparación en tres periodos."""
    reg = m.reg
    f = fechas(reg, True)
    largo = m.largo1d
    c_grande = float(reg.costos["comision_spot_pct"]) + float(reg.costos["deslizamiento_pct"]["grande"])
    c_mediana = float(reg.costos["comision_spot_pct"]) + float(reg.costos["deslizamiento_pct"]["mediana"])
    periodos = {
        "2022-01 a 2026-10 (principal)": (f["inicio"], f["fin"]),
        "2018-01 a 2021-12 (antes, solo BTC/ETH)": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2021-12-31", tz="UTC")),
        "2026-05 a 2026-10 (ya abierto)": (f["ya_abierto"], f["fin"]),
    }
    preparar_rotacion(m, [30, 60, 90])
    btc_diario = RG.a_intervalo(m.btc_reg4h, m.spot1d["BTCUSDT"].index, pd.Timedelta(hours=4), pd.Timedelta(days=1))
    out = {}
    for nombre, (a, b) in periodos.items():
        curvas, inv, ops = {}, {}, {}
        curvas["Comprar y aguantar BTC"] = RF.comprar_aguantar(largo, {"BTCUSDT": 1.0}, a, b, c_grande)
        curvas["Comprar y aguantar 50 % BTC + 50 % ETH"] = RF.comprar_aguantar(largo, {"BTCUSDT": .5, "ETHUSDT": .5}, a, b, c_grande)
        curvas["DCA: comprar BTC cada lunes"] = RF.dca_semanal(largo["BTCUSDT"], a, b, c_grande)
        c, i = RF.tendencia_pura(largo, ["BTCUSDT"], 200, a, b, c_grande)
        curvas["Tendencia pura: solo BTC (media 200 días)"], inv["Tendencia pura: solo BTC (media 200 días)"] = c, i
        c, i = RF.tendencia_pura(largo, ["BTCUSDT", "ETHUSDT"], 200, a, b, c_grande)
        curvas["Tendencia pura: BTC + ETH (media 200 días)"], inv["Tendencia pura: BTC + ETH (media 200 días)"] = c, i
        if a >= f["inicio"]:
            for top in (3, 5):
                for v in (30, 60, 90):
                    nom = f"Rotación pura: top {top}, fuerza de {v} días"
                    c, i, n = RF.rotacion_pura(m.spot1d, m.lugar_rotacion[v], btc_diario, top, a, b, c_mediana, E7.DIA_REBALANCEO)
                    curvas[nom], inv[nom], ops[nom] = c, i, n
        out[nombre] = {"curvas": curvas, "metricas": {k: RF.metricas_curva(v, inv.get(k)) for k, v in curvas.items()},
                       "operaciones": ops}
    return out


def grafica_referencias(refs: dict, carpeta: Path) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    carpeta.mkdir(parents=True, exist_ok=True)
    curvas = refs["2022-01 a 2026-10 (principal)"]["curvas"]
    elegir = ["Comprar y aguantar BTC", "DCA: comprar BTC cada lunes", "Tendencia pura: BTC + ETH (media 200 días)",
              "Tendencia pura: solo BTC (media 200 días)", "Rotación pura: top 3, fuerza de 60 días"]
    fig, ax = plt.subplots(figsize=(9.5, 5))
    for k in elegir:
        c = curvas[k]
        ax.plot(c.index, c.values / c.iloc[0], lw=1.3, label=k)
    ax.set_yscale("log")
    ax.axhline(1, color="#888", lw=0.8, ls="--")
    ax.set_title("Cuánto valdría 1 dólar (escala logarítmica), 2022–2026")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = carpeta / "ronda2_referencias.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p.name


def escribir(resultados, refs, reg, ruta: Path) -> None:
    r2 = reg.datos["validacion"]["ronda2"]
    n_ideas = int(r2["ideas_probadas"])
    azar_min = 100 - float(r2["azar_base_pct"]) / n_ideas
    conf = 100 * (1 - float(r2["confianza_base"]) / n_ideas)
    L = ["# VALIDACIÓN — RONDA 2", "",
         f"Generado el {datetime.now():%d/%m/%Y %H:%M} · reglamento {reg.version} · datos de enero 2022 a octubre 2026.", ""]
    pasan = [r for r in resultados if r.pasa]
    L += ["## Resumen en una frase", ""]
    if pasan:
        L.append(f"**Pasaron todas las compuertas: {', '.join(r.clave for r in pasan)}.** Siguiente paso: 30 días y 30 "
                 "operaciones en papel (desde noviembre de 2026) dentro de lo esperado, antes de cualquier dinero real.")
    else:
        L.append("**Ninguna estrategia de la ronda 2 pasó todas las compuertas con el motor de riesgo.** "
                 "Abajo está qué tan cerca quedó cada una y cómo se comparan las ideas \"puras\" contra comprar y aguantar.")
    L.append("")
    L += ["## Las reglas de esta ronda (escritas ANTES de ver resultados)", "",
          "- Mismas compuertas y mismo motor de riesgo que la ronda 1.",
          "- La prueba final de mayo–octubre 2026 ya se abrió en la ronda 1: ahora es una ventana más del walk-forward "
          "y además una compuerta extra (debe salir positiva). **Noviembre 2026 en adelante es la prueba en papel.**",
          f"- **Más estricto por probar muchas ideas** ({n_ideas} en total con los mismos datos): debe ganarle al "
          f"**{azar_min:.2f} %** de las entradas al azar (antes 90 %) y el **piso del intervalo de confianza del {conf:.1f} %** "
          "de su expectativa debe ser mayor que cero. Esto baja la probabilidad de que un resultado bonito sea pura suerte.",
          "- E6 y E7 se miden de dos formas: **pura** (todo el dinero adentro o afuera, como la idea original) y "
          "**con tu reglamento** (1 % de riesgo por operación, máximo 30 % por posición y 3 posiciones). "
          "Las compuertas se aplican a la versión con reglamento, porque es la que operaría.",
          "- **Robustez** (cambio de método, avisado): se mide con las operaciones que el motor realmente toma. "
          "E6 y E7 repiten la señal cada día que siguen dentro; contar todas las señales mediría la misma posición muchas veces.",
          "- **Corrección de datos** (afecta también a la ronda 1): 9 cambios de denominación de monedas (por ejemplo BNX 1:100 "
          "en febrero de 2023) aparecían como caídas falsas de hasta 99 %. Se ajustaron como un \"split\". La ronda 1 se volvió a correr.",
          "- E1D cambia una regla del reglamento: no se sube el stop a la entrada en +1R (pedido por Ángelo; queda anotado en el reglamento 1.1.0).", ""]
    L += ["## Veredicto con tu reglamento (compuertas)", "",
          "| Estrategia | ¿Pasa? | Operaciones | Expectativa | Factor | Piso de confianza | Le gana al azar | Mayo–oct 2026 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in resultados:
        o = r.oos_r
        L.append(f"| {r.clave} {r.nombre} | {'✅ Sí' if r.pasa else '❌ No'} | {o.get('operaciones', 0)} | "
                 f"{_f(o.get('expectativa_r'), 3, True)}R | {_f(o.get('factor_ganancia'), 2)} | "
                 f"{_f(r.ic_inferior, 3, True)}R | {_f(r.azar.get('percentil_estrategia'), 1)} % | "
                 f"{_f(r.ya_abierto.get('expectativa_r'), 3, True)}R en {r.ya_abierto.get('operaciones', 0)} |")
    L.append("")
    # Referencias
    for nombre, bloque in refs.items():
        L += [f"## Comparación de ideas puras: {nombre}", "",
              "| Idea | Rendimiento total | Por año | Caída máxima | Volatilidad | Rend./volatilidad | Tiempo invertido |",
              "|---|---|---|---|---|---|---|"]
        for k, mt in bloque["metricas"].items():
            if not mt:
                continue
            L.append(f"| {k} | {_f(mt['rend_total_pct'], 0, True)} % | {_f(mt['rend_anual_pct'], 1, True)} % | "
                     f"{_f(mt['caida_max_pct'], 0)} % | {_f(mt['volatilidad_pct'], 0)} % | {_f(mt['sharpe'], 2)} | "
                     f"{_f(mt.get('tiempo_invertido_pct'), 0) + ' %' if 'tiempo_invertido_pct' in mt else '100 %' if 'aguantar' in k else '—'} |")
        L.append("")
    L += ["**Cómo leer estas tablas:** *caída máxima* es lo más que bajó tu dinero desde su punto más alto (lo que más "
          "duele). *Rend./volatilidad* compara la ganancia contra los sustos: más alto = más ganancia por cada susto. "
          "Las rotaciones se muestran TODAS (6 variantes) para que no se elija a la que le fue mejor por suerte.", ""]
    principal = refs["2022-01 a 2026-10 (principal)"]["curvas"]
    L += ["## Rendimiento por año (versiones puras y referencias)", "",
          "| Idea | " + " | ".join(str(a) for a in range(2022, 2027)) + " |", "|---|" + "---|" * 5]
    for k in ["Comprar y aguantar BTC", "DCA: comprar BTC cada lunes", "Tendencia pura: solo BTC (media 200 días)",
              "Tendencia pura: BTC + ETH (media 200 días)", "Rotación pura: top 3, fuerza de 60 días",
              "Rotación pura: top 5, fuerza de 60 días"]:
        pa = RF.por_anio(principal[k])
        L.append(f"| {k} | " + " | ".join(f"{_f(pa.get(a), 0, True)} %" for a in range(2022, 2027)) + " |")
    L.append("")
    img = grafica_referencias(refs, ruta.parent / "docs" / "img")
    if img:
        L += [f"![referencias](docs/img/{img})", ""]
    carpeta_img = ruta.parent / "docs" / "img"
    for r in resultados:
        L += informe._seccion(r, informe.graficas(r, carpeta_img))
        if r.por_anio:
            L += ["**Por año (con tu reglamento):** " + " · ".join(
                f"{a}: {v['operaciones']} op., {_f(v['expectativa_r'], 2, True)}R" for a, v in r.por_anio.items()), ""]
    ruta.write_text("\n".join(L) + "\n", encoding="utf-8")


def ejecutar(m: Mercado, ruta: Path, avisar=print):
    resultados = []
    for k in CLAVES:
        avisar(f"Validando {k} ({m.reg.estrategias[k]['nombre']})…")
        r = evaluar(m, k, avisar=avisar, ronda_ajuste=2 if k == "E1D" else 1, ronda2=True)
        avisar(f"  {k}: {'PASA' if r.pasa else 'NO PASA'}")
        resultados.append(r)
    avisar("Calculando referencias…")
    refs = referencias(m)
    escribir(resultados, refs, m.reg, ruta)
    return resultados, refs
