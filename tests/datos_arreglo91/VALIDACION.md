# VALIDACIÓN DE SOBREVIVIENTE PRO

Generado el 11/11/2026 18:30 · reglamento 2.0.1 · datos del 01/01/2022 al 31/10/2026.

## Resumen en una frase

**Pasaron las pruebas del backtest: E1.** Eso NO significa que vayan a ganar: solo que mostraron una ventaja con los datos del pasado. Antes de tocar dinero real necesitan 30 días y 30 operaciones en papel dentro de lo esperado.

| Estrategia | ¿Pasa? | Operaciones fuera de muestra | Expectativa (R) | Factor de ganancia | Caída p95 Monte Carlo | Le gana al azar | Prueba final |
|---|---|---|---|---|---|---|---|
| E1 Estrategia E1 | ✅ Sí | 140 | +0.123 | 1.45 | 14.9 % | 96 % | +0.080R en 21 op. |
| E2 Estrategia E2 | ❌ No | 140 | -0.050 | 1.45 | 14.9 % | 96 % | +0.080R en 21 op. |
| E3 Estrategia E3 | ❌ No | 140 | -0.050 | 1.45 | 14.9 % | 96 % | +0.080R en 21 op. |
| E4 Estrategia E4 | ❌ No | 140 | -0.050 | 1.45 | — % | — % | +0.080R en 21 op. |

**Cómo leer esta tabla:**
- *Expectativa (R)*: lo que deja en promedio cada operación, en unidades de riesgo. +0.10R significa que, si arriesgas 1 peso por operación, en promedio te quedan 10 centavos ya con comisiones.
- *Factor de ganancia*: lo ganado entre lo perdido. 1.0 = empate; se pide 1.3 o más.
- *Caída p95*: en el peor 5 % de 10,000 simulaciones, cuánto llegaría a caer el capital.
- *Le gana al azar*: a qué porcentaje de 1,000 carteras con entradas al azar (mismas salidas) supera. Se pide 90 %.
- *Prueba final*: los últimos 6 meses, que nadie tocó hasta el final.

## Cómo se hizo (para que confíes en los números)

- **Periodo:** enero de 2022 a octubre de 2026. Incluye el mercado bajista de 2022, el lateral de 2023 y los alcistas posteriores.
- **Walk-forward:** 14 ventanas. En cada una se eligen los parámetros con 12 meses y se prueban en los 3 meses siguientes, que la estrategia no vio. **Solo se reportan esos 3 meses de prueba.**
- **Prueba final intocable:** 01/05/2026 a 31/10/2026. Se abrió una sola vez, al final.
- **Costos reales:** comisión de Spot 0.10 % por lado; Futuros 0.05 % por lado; deslizamiento de 0.05 % (grandes), 0.10 % (medianas) y 0.30 % (memes); funding real en Futuros.
- **Sin ver el futuro:** cada señal usa solo velas cerradas y se ejecuta en la apertura de la vela siguiente. Hay pruebas automáticas que lo garantizan.
- **El mismo motor de riesgo que en vivo:** cada operación pasó por las mismas reglas (calor, posiciones, topes, régimen de BTC, volatilidad, costos, mínimos de Binance).
- **Capital de prueba:** 10,000 USDT para medir la ventaja sin que estorben los mínimos de Binance; además se repite con tus 46.18 USDT reales.
- nota de datos uno
- nota de datos dos

## E1 — Estrategia E1: ✅ PASA

Ronda de ajustes 2 de 3 · 12 combinaciones de parámetros probadas · parámetros finales: `{'n': 20, 'stop_atr': 2.0}`

**Compuertas:**

- ✅ Al menos 100 operaciones fuera de muestra
- ✅ Expectativa mayor que +0.05R

**Fuera de muestra (los 3 meses de prueba de cada ventana, unidos):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 140 | cuántas veces entró |
| % ganadoras | 41.5 % | de cada 100 operaciones, cuántas ganaron |
| Ganancia promedio | +2.10R | lo que deja una ganadora en promedio |
| Pérdida promedio | -1.00R | lo que quita una perdedora en promedio |
| Expectativa | +0.123R | promedio por operación, ya con costos |
| Factor de ganancia | 1.45 | ganado ÷ perdido |
| Peor racha | 9 pérdidas seguidas | prepárate mentalmente para esto |
| Ventanas positivas | 64 % | en cuántos trimestres ganó |
| Rendimiento (capital de prueba) | +18.4 % | con 1 % de riesgo por operación |
| Caída máxima (capital de prueba) | 9.7 % | lo más que bajó desde un máximo |
| Comisiones | 22 % de la ganancia bruta | lo que se llevó Binance |

**Monte Carlo (10,000 simulaciones):** rendimiento entre -3.2 % y +41.0 % (90 % de los casos; mediana +17.5 %). Caída máxima típica 8.1 %, en el peor 5 % 14.9 %. Probabilidad de tocar −15 % (el freno total): 4.2 %. Racha perdedora típica 7, en el peor 5 % 12.

**Contra el azar:** con entradas al azar (mismas salidas, mismos filtros) la expectativa típica fue -0.020R; el 10 % mejor llegó a +0.040R. La estrategia le gana al 96 % de ellas.

**Contra comprar y aguantar BTC:** en el mismo periodo fuera de muestra BTC hizo +55.0 % con una caída de 30.2 %; la estrategia +18.4 % con caída de 9.7 %. En la prueba final BTC hizo -4.0 %.

**Por régimen de BTC al entrar:**

| Régimen | Operaciones | Expectativa | Factor de ganancia |
|---|---|---|---|
| ALCISTA | 100 | +0.200R | 1.70 |
| LATERAL | 40 | —R | — |

**Prueba final intocable:** 21 operaciones, expectativa +0.080R, factor 1.20, rendimiento +3.3 %.

**Con tus 46.18 USDT reales:** de 50 señales que pasaron los demás filtros, se habrían ejecutado 20 y **30 se habrían saltado por falta de capital**.
Para no saltarse la mitad de esas, harían falta unos **120 USDT**; para no saltarse 3 de cada 4, unos 260 USDT.

**Robustez:** al mover n, stop_atr ±20 %, la peor expectativa fue +0.100R (sigue positiva en todos los casos).

**Ventanas de walk-forward:**

| Prueba | Parámetros elegidos | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01 a 2023-03 | `{'n': 20}` | 11 | +2.50 |
| 2023-04 a 2023-06 | `{'n': 30}` | 0 | — |


> Nota: una nota de prueba

## E2 — Estrategia E2: ❌ NO PASA

Ronda de ajustes 2 de 3 · 12 combinaciones de parámetros probadas · parámetros finales: `{'n': 20, 'stop_atr': 2.0}`

**Compuertas:**

- ✅ Al menos 100 operaciones fuera de muestra
- ❌ Expectativa mayor que +0.05R

**Fuera de muestra (los 3 meses de prueba de cada ventana, unidos):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 140 | cuántas veces entró |
| % ganadoras | 41.5 % | de cada 100 operaciones, cuántas ganaron |
| Ganancia promedio | +2.10R | lo que deja una ganadora en promedio |
| Pérdida promedio | -1.00R | lo que quita una perdedora en promedio |
| Expectativa | -0.050R | promedio por operación, ya con costos |
| Factor de ganancia | 1.45 | ganado ÷ perdido |
| Peor racha | 9 pérdidas seguidas | prepárate mentalmente para esto |
| Ventanas positivas | 64 % | en cuántos trimestres ganó |
| Rendimiento (capital de prueba) | +18.4 % | con 1 % de riesgo por operación |
| Caída máxima (capital de prueba) | 9.7 % | lo más que bajó desde un máximo |
| Comisiones | 22 % de la ganancia bruta | lo que se llevó Binance |

**Monte Carlo (10,000 simulaciones):** rendimiento entre -3.2 % y +41.0 % (90 % de los casos; mediana +17.5 %). Caída máxima típica 8.1 %, en el peor 5 % 14.9 %. Probabilidad de tocar −15 % (el freno total): 4.2 %. Racha perdedora típica 7, en el peor 5 % 12.

**Contra el azar:** con entradas al azar (mismas salidas, mismos filtros) la expectativa típica fue -0.020R; el 10 % mejor llegó a +0.040R. La estrategia le gana al 96 % de ellas.

**Contra comprar y aguantar BTC:** en el mismo periodo fuera de muestra BTC hizo +55.0 % con una caída de 30.2 %; la estrategia +18.4 % con caída de 9.7 %. En la prueba final BTC hizo -4.0 %.

**Por régimen de BTC al entrar:**

| Régimen | Operaciones | Expectativa | Factor de ganancia |
|---|---|---|---|
| ALCISTA | 100 | +0.200R | 1.70 |
| LATERAL | 40 | —R | — |

**Prueba final intocable:** 21 operaciones, expectativa +0.080R, factor 1.20, rendimiento +3.3 %.

**Con tus 46.18 USDT reales:** de 5 señales que pasaron los demás filtros, se habrían ejecutado 5 y **0 se habrían saltado por falta de capital**.

**Robustez:** al mover n, stop_atr ±20 %, la peor expectativa fue -0.100R (negativa en todos los casos: no hay una zona de parámetros que funcione).

**Ventanas de walk-forward:**

| Prueba | Parámetros elegidos | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01 a 2023-03 | `{'n': 20}` | 11 | +2.50 |
| 2023-04 a 2023-06 | `{'n': 30}` | 0 | — |


> Nota: una nota de prueba

## E3 — Estrategia E3: ❌ NO PASA

Ronda de ajustes 2 de 3 · 12 combinaciones de parámetros probadas · parámetros finales: `{'n': 20, 'stop_atr': 2.0}`

**Compuertas:**

- ✅ Al menos 100 operaciones fuera de muestra
- ❌ Expectativa mayor que +0.05R

**Fuera de muestra (los 3 meses de prueba de cada ventana, unidos):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 140 | cuántas veces entró |
| % ganadoras | 41.5 % | de cada 100 operaciones, cuántas ganaron |
| Ganancia promedio | +2.10R | lo que deja una ganadora en promedio |
| Pérdida promedio | -1.00R | lo que quita una perdedora en promedio |
| Expectativa | -0.050R | promedio por operación, ya con costos |
| Factor de ganancia | 1.45 | ganado ÷ perdido |
| Peor racha | 9 pérdidas seguidas | prepárate mentalmente para esto |
| Ventanas positivas | 64 % | en cuántos trimestres ganó |
| Rendimiento (capital de prueba) | +18.4 % | con 1 % de riesgo por operación |
| Caída máxima (capital de prueba) | 9.7 % | lo más que bajó desde un máximo |
| Comisiones | 22 % de la ganancia bruta | lo que se llevó Binance |

**Monte Carlo (10,000 simulaciones):** rendimiento entre -3.2 % y +41.0 % (90 % de los casos; mediana +17.5 %). Caída máxima típica 8.1 %, en el peor 5 % 14.9 %. Probabilidad de tocar −15 % (el freno total): 4.2 %. Racha perdedora típica 7, en el peor 5 % 12.

**Contra el azar:** con entradas al azar (mismas salidas, mismos filtros) la expectativa típica fue -0.020R; el 10 % mejor llegó a +0.040R. La estrategia le gana al 96 % de ellas.

**Contra comprar y aguantar BTC:** en el mismo periodo fuera de muestra BTC hizo +55.0 % con una caída de 30.2 %; la estrategia +18.4 % con caída de 9.7 %. En la prueba final BTC hizo -4.0 %.

**Por régimen de BTC al entrar:**

| Régimen | Operaciones | Expectativa | Factor de ganancia |
|---|---|---|---|
| ALCISTA | 100 | +0.200R | 1.70 |
| LATERAL | 40 | —R | — |

**Prueba final intocable:** 21 operaciones, expectativa +0.080R, factor 1.20, rendimiento +3.3 %.

**Con tus 46.18 USDT reales:** de 50 señales que pasaron los demás filtros, se habrían ejecutado 20 y **30 se habrían saltado por falta de capital**.
Para no saltarse la mitad de esas, harían falta unos **120 USDT**; para no saltarse 3 de cada 4, unos 260 USDT.

**Robustez:** al mover n, stop_atr ±20 %, la peor expectativa fue -0.100R (en algunos casos se vuelve negativa).

**Ventanas de walk-forward:**

| Prueba | Parámetros elegidos | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01 a 2023-03 | `{'n': 20}` | 11 | +2.50 |
| 2023-04 a 2023-06 | `{'n': 30}` | 0 | — |


> Nota: una nota de prueba

## E4 — Estrategia E4: ❌ NO PASA

Ronda de ajustes 2 de 3 · 12 combinaciones de parámetros probadas · parámetros finales: `{'n': 20, 'stop_atr': 2.0}`

**Compuertas:**

- ✅ Al menos 100 operaciones fuera de muestra
- ❌ Expectativa mayor que +0.05R

**Fuera de muestra (los 3 meses de prueba de cada ventana, unidos):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 140 | cuántas veces entró |
| % ganadoras | 41.5 % | de cada 100 operaciones, cuántas ganaron |
| Ganancia promedio | +2.10R | lo que deja una ganadora en promedio |
| Pérdida promedio | -1.00R | lo que quita una perdedora en promedio |
| Expectativa | -0.050R | promedio por operación, ya con costos |
| Factor de ganancia | 1.45 | ganado ÷ perdido |
| Peor racha | 9 pérdidas seguidas | prepárate mentalmente para esto |
| Ventanas positivas | 64 % | en cuántos trimestres ganó |
| Rendimiento (capital de prueba) | +18.4 % | con 1 % de riesgo por operación |
| Caída máxima (capital de prueba) | 9.7 % | lo más que bajó desde un máximo |
| Comisiones | 22 % de la ganancia bruta | lo que se llevó Binance |

**Prueba final intocable:** 21 operaciones, expectativa +0.080R, factor 1.20, rendimiento +3.3 %.

**Ventanas de walk-forward:**

| Prueba | Parámetros elegidos | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01 a 2023-03 | `{'n': 20}` | 11 | +2.50 |
| 2023-04 a 2023-06 | `{'n': 30}` | 0 | — |



## Lo que estas pruebas NO pueden garantizar

- El pasado no garantiza el futuro. Los mercados cambian.
- Los resultados con 46 USDT pueden ser muy distintos a los del capital de prueba por los mínimos de Binance.
- El calendario de eventos (Fed, inflación) y los vetos de Noticias no existen en los datos del pasado: en vivo se saltarán algunas operaciones que el backtest sí tomó.
- Las reglas de Binance (mínimos y decimales) usadas son las actuales; en el pasado algunas eran distintas.
