# VALIDACIÓN V2 — "MAREA"

Generado el 10/11/2026 08:28 · reglamento 2.0.1 · datos del 01/01/2022 al 31/10/2026.

## Resumen en una frase

**Ningún motor nuevo pasó todas las compuertas ni le ganó a la referencia R1 (BTC con filtro de marea).** Por la regla de la v2, **R1 pasa a ser la candidata (M0) y es la que corre en PAPEL** como línea base. Todo lo demás queda APAGADO. Nunca se promete ganancia.

| Motor | ¿Pasa? | Operaciones fuera de muestra | Expectativa (R) | Factor de ganancia | Calmar fuera de muestra | Le gana al azar (calendario) | Caída p95 (bloques) | Prueba final (ya abierta) |
|---|---|---|---|---|---|---|---|---|
| M1 MAREA (tendencia de cada moneda) | ❌ | 81 | +0.063 | 1.12 | -0.02 | 26 % | 24.9 % | 9 op., +0.370R |
| M2 RANKING (las más fuertes) | ❌ | 112 | -0.083 | 0.81 | -0.17 | 8 % | 29.8 % | 9 op., +0.599R |
| M0 Marea BTC (= R1) | ❌ (como cartera) | 32 cambios | — | — | 1.17 | 66 % | 59.8 % | +11.4 % |

**Cómo leer esta tabla:**
- *Expectativa (R)*: lo que deja en promedio cada operación, en unidades de riesgo, ya con costos. +0.10R = si arriesgas 1 peso, te quedan 10 centavos.
- *Factor de ganancia*: lo ganado entre lo perdido. Se pide 1.3 o más.
- *Calmar*: rendimiento por año ÷ la peor caída. Más alto = más ganancia por cada susto. **R1 hizo 1.17 fuera de muestra: hay que ganarle.**
- *Le gana al azar (calendario)*: a cuántos de 1,000 calendarios al azar (mismas monedas, mismo número de entradas, mismo tiempo invertido, otras fechas) supera. Se pide 90 %.
- *Caída p95 (bloques)*: en el peor 5 % de 10,000 simulaciones que respetan que las pérdidas llegan juntas, cuánto caería el capital. Máximo 25 %.
- *Prueba final*: mayo–octubre 2026. **Ya se abrió en la v1**, así que se reporta pero no decide: la prueba limpia es el papel desde hoy.

## Auditoría A1–A9 (lo que le faltaba a la v1)

Se midió sobre **E1** (la tendencia de la v1) con sus parámetros finales `{'donchian_n': 55, 'stop_atr': 3.0, 'chandelier_atr': 3.0}`, del 01/01/2023 al 01/05/2026 (el periodo fuera de muestra de la v1). No se optimizó nada nuevo.

**A1 — Monte Carlo suelto contra en bloques por fecha.**

| | Suelto (v1) | En bloques de 20 días (v2) | Qué significa |
|---|---|---|---|
| Caída típica | 39.3 % | 41.3 % | la mitad de las simulaciones cae más que esto |
| Caída en el peor 5 % | 56.2 % | 59.3 % | lo que se usa para la compuerta |
| Racha perdedora (peor 5 %) | 18 | 24 | pérdidas seguidas |
| Probabilidad de tocar el freno de 15 % | 99.5 % | 99.8 % | |

**A2 — Caída con operaciones cerradas contra curva diaria a valor de mercado.**

| | Solo cerradas (v1) | A valor de mercado (v2) |
|---|---|---|
| Caída máxima | 41.7 % | 41.8 % |
| Días que tocaron el tope diario | 0 | 2 |
| Semanas que tocaron el tope semanal | 0 | 0 |
| Veces que se habría activado el freno total | 3 | 4 |
| Rendimiento | -26.7 % | -26.3 % |

Con valor a mercado, los topes y el tamaño de cada operación usan el capital real del momento (las posiciones abiertas que van perdiendo cuentan). Por eso el número de operaciones y el rendimiento cambian un poco.

**A3 — ¿Qué tanto pesan las reglas de salida?** Misma entrada de E1 y misma muestra de entradas al azar; solo cambia la salida.

| Salida | E1: operaciones | E1: expectativa | E1: % ganadoras | E1: ganancia promedio | Azar: expectativa | Azar: % ganadoras |
|---|---|---|---|---|---|---|
| (a) actual: stop dinámico 3 ATR + "+1R → entrada" | 2914 | -0.124R | 33.6 % | +0.88R | -0.104R | 32.7 % |
| (b) sin "+1R → entrada" | 2914 | -0.119R | 29.1 % | +1.05R | -0.103R | 30.6 % |
| (c) sin "+1R" y stop dinámico de 5 ATR | 2914 | -0.115R | 27.6 % | +1.78R | -0.105R | 27.8 % |
| (d) salida por canal como M1 (mínimo de 27 velas) | 2914 | -0.103R | 27.2 % | +1.80R | -0.111R | 19.1 % |

**A4 — ¿Las monedas chicas arrastraban a E1?**

| Universo | Operaciones | Expectativa | Factor de ganancia | Rendimiento de cartera |
|---|---|---|---|---|
| Todas (456 monedas) | 2914 | -0.124R | 0.70 | -26.3 % |
| Solo las 15 grandes del día | 847 | -0.027R | 0.93 | -8.2 % |
| Solo las que NO son grandes | 2067 | -0.164R | 0.62 | — |

**A5 — E3 (comprar lo que se desploma) queda archivada.** Le ganó al 0 % del azar en la v1: comprar caídas fue peor que comprar a ciegas. No se prueban más ideas de "comprar la caída"; es evidencia a favor de seguir la tendencia.

**A6 — Memes fuera de la v2.** En la v1, E4 quedó casi en empate con BTC alcista (+0.032R en 45 operaciones) y fatal con BTC bajista (−0.767R).

**A7 — Concentración.** En E1 (periodo de la auditoría), la suma de resultados es negativa, así que la concentración no aplica (suma total -34.5R). En la v1, 2 de 14 ventanas dieron casi todo lo positivo: por eso en los motores lentos la compuerta de ventanas positivas baja de 60 % a 40 % y en cada motor se reporta qué parte del resultado viene de sus 5 mejores operaciones (más de 100 % = sin esas 5, pierde).

**A8 — Cupo.** De 3494 señales de E1, 1942 se quedaron fuera por falta de lugar (posiciones o calor lleno). Elegir por "fuerza" dio -26.3 %; elegir al azar entre las señales del mismo momento dio -25.4 % típico (200 repeticiones). La "fuerza" le ganó al 42 % de esas elecciones al azar.

**A9 — Sensibilidad a la comisión (por lado).**

| Comisión | Operaciones | Expectativa | Rendimiento de cartera |
|---|---|---|---|
| 0.075 % | 2914 | -0.118R | -24.7 % |
| 0.100 % | 2914 | -0.124R | -26.3 % |
| 0.150 % | 2914 | -0.135R | -29.5 % |

## Referencias obligatorias (lo simple contra lo que todo compite)

Señal al cierre diario (00:00 UTC), ejecución en la apertura siguiente, comisión 0.10 % + deslizamiento 0.05 % por lado.

| Referencia | Periodo | Rendimiento | Por año | Caída máxima | Calmar | Tiempo invertido | Operaciones |
|---|---|---|---|---|---|---|---|
| R0 Aguantar BTC | 2022-01 a 2026-10 | +67.4 % | +11.3 % | 66.9 % | 0.17 | 100 % | 1 |
| R0 Aguantar BTC | fuera de muestra (2023-01 a 2026-04) | +358.1 % | +58.0 % | 49.5 % | 1.17 | 100 % | 1 |
| R0 Aguantar BTC | prueba final (2026-05 a 2026-10) | +1.3 % | +2.7 % | 28.7 % | 0.09 | 100 % | 1 |
| R1 BTC con filtro de marea (media 200 días) | 2022-01 a 2026-10 | +221.1 % | +27.3 % | 32.0 % | 0.85 | 53 % | 33 |
| R1 BTC con filtro de marea (media 200 días) | fuera de muestra (2023-01 a 2026-04) | +188.2 % | +37.5 % | 32.0 % | 1.17 | 70 % | 32 |
| R1 BTC con filtro de marea (media 200 días) | prueba final (2026-05 a 2026-10) | +11.4 % | +24.1 % | 10.7 % | 2.26 | 40 % | 1 |
| R2 Canasta de las 10 grandes con filtro de marea | 2022-01 a 2026-10 | +13.6 % | +2.7 % | 60.2 % | 0.04 | 53 % | 688 |
| R2 Canasta de las 10 grandes con filtro de marea | fuera de muestra (2023-01 a 2026-04) | +4.5 % | +1.3 % | 60.2 % | 0.02 | 70 % | 653 |
| R2 Canasta de las 10 grandes con filtro de marea | prueba final (2026-05 a 2026-10) | +8.7 % | +18.1 % | 23.1 % | 0.78 | 40 % | 35 |

**Por año:**

| Referencia | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| R0 | -64 % | +154 % | +120 % | -5 % | -13 % |
| R1 | +0 % | +94 % | +81 % | -18 % | +11 % |
| R2 | +0 % | +56 % | -9 % | -26 % | +9 % |

*Qué significa:* aguantar BTC (R0) gana mucho en los años buenos pero cae hasta 67 %. El filtro de marea (R1) se sale cuando BTC pierde su media de 200 días: deja ir parte de la subida, pero corta la caída a la mitad. La canasta de grandes (R2) sufrió porque las altcoins grandes cayeron mucho en 2024–2025 aunque BTC estuviera arriba de su media.

## M0 — R1 como candidata (se evalúa como cartera)

**Compuertas que le aplican:**

- ❌ le gana al 65.6 % de los calendarios al azar (mínimo 90 %)
- ✅ 50 % de trimestres positivos (mínimo 40 %)
- ✅ media de 160 a 240 días: positiva en todos los casos
- ❌ caída p95 del remuestreo en bloques 59.8 % (máximo 25 %)

- Calendario al azar: R1 hizo +188.2 % fuera de muestra; un calendario al azar con las mismas 16 entradas y el mismo 70 % de tiempo invertido hizo +143.9 % típico (el 10 % mejor, +382.8 %).
- Remuestreo en bloques de 20 días: Calmar entre -0.07 y 3.43 (90 % de los casos); caída máxima típica 38.5 %, en el peor 5 % 59.8 %.
- Robustez de la media (fuera de muestra):

| Media | Rendimiento | Caída máxima | Calmar |
|---|---|---|---|
| 160 días | +168.9 % | 33.4 % | 1.04 |
| 180 días | +216.1 % | 33.6 % | 1.23 |
| 200 días | +188.2 % | 32.0 % | 1.17 |
| 220 días | +133.4 % | 42.2 % | 0.69 |
| 240 días | +141.4 % | 33.0 % | 0.92 |

- Sensibilidad a la comisión: 0.075 % → Calmar 1.19 · 0.100 % → Calmar 1.17 · 0.150 % → Calmar 1.14

- Topes con la curva a valor de mercado (todo el dinero en BTC cuando la marea está alta): Cartera A: 69 días de tope diario, 11 veces el freno total · Cartera B: 31 días de tope diario, 1 veces el freno total

**M0 dentro de las carteras** (como correría en papel: motor de riesgo, stop de catástrofe de 15 %, máximo 30 % en BTC), fuera de muestra:

| Cartera | Rendimiento | Caída máxima | Calmar | Caída p95 (bloques) | Operaciones | Con 46.18 USDT: ejecutadas / saltadas por capital |
|---|---|---|---|---|---|---|
| A | +10.3 % | 3.8 % | 0.79 | 8.2 % | 15 | 0 / 758 |
| B | +21.2 % | 7.0 % | 0.85 | 15.0 % | 15 | 11 / 13 |

**Ojo con la Cartera A:** con 1 % de riesgo y un stop de 15 %, la compra sale de unos 3 USDT, menos que el mínimo de 5 USDT de Binance. Con 46.18 USDT la Cartera A **no puede comprar BTC nunca** con M0 (haría falta capital de unos 88 USDT, como decía la tabla de la especificación). La Cartera B (2 %) sí cabe.

*Qué significa:* M0 no le gana a nada: ES la referencia. Si va a papel es como línea base honesta. En las carteras A y B corre a través del motor de riesgo (riesgo por operación ÷ stop de catástrofe de 15 %, máximo 30 % del capital en BTC), así que tiene una parte de BTC, no todo el dinero; la versión "todo adentro" se sigue aparte como referencia R1.

## M1 — MAREA (tendencia de cada moneda): ❌ NO PASA

Rondas de ajuste usadas: 0 de 1 (se corrió la configuración pre-registrada tal cual) · 3 combinaciones probadas (n=20, n=50, n=100) · parámetros finales: `{'n': 20}`

**Compuertas:**

- ✅ 81 operaciones fuera de muestra (mínimo 60)
- ❌ factor de ganancia 1.12 (mínimo 1.3)
- ❌ expectativa +0.063R (mínimo +0.1R)
- ❌ 36 % de ventanas positivas (mínimo 40 % para motores lentos; contando solo las 12 ventanas con operaciones: 42 %)
- ✅ caída p95 de Monte Carlo 24.9 % (la peor entre suelto y en bloques; máximo 25 %)
- ❌ le gana al 26.2 % de los calendarios al azar (mínimo 90 %)
- ❌ Calmar fuera de muestra -0.02 contra 1.17 de R1 (debe ser mayor)
- ❌ robustez ±20 %: peor expectativa -0.047R

**Fuera de muestra (Cartera A, capital de prueba de 10,000 USDT):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 81 | cuántas veces entró |
| % ganadoras | 35.8 % | de cada 100, cuántas ganaron |
| Ganancia promedio | +1.63R | lo que deja una ganadora |
| Pérdida promedio | -0.81R | lo que quita una perdedora |
| Expectativa | +0.063R | promedio por operación, ya con costos |
| Factor de ganancia | 1.12 | ganado ÷ perdido |
| Peor racha | 10 pérdidas seguidas | prepárate para esto |
| Ventanas positivas | 36 % | en cuántos trimestres ganó (se pide 40 %) |
| Concentración | 512 % | qué parte del resultado viene de las 5 mejores operaciones |
| Rendimiento (valor a mercado) | -0.9 % | con 1 % de riesgo por operación |
| Caída máxima (valor a mercado) | 15.8 % | lo más que bajó desde un máximo |
| Calmar | -0.02 | contra 1.17 de R1 |
| Tiempo con alguna posición | 51 % | |

**Monte Carlo (10,000):** suelto → caída p95 21.9 %; en bloques de 20 días → caída p95 24.9 %, racha perdedora p95 13. Rendimiento en bloques entre -20.5 % y +42.0 %.

**Contra el azar (calendario):** la suma de (peso × rendimiento) real fue +0.42 %; la típica de 1,000 calendarios al azar +7.20 % y el 10 % mejor +24.68 %. Le gana al 26 %.

**Remuestreo en bloques de 20 días (curva diaria):** Calmar entre -0.30 y 0.76; caída máxima entre 10.6 % y 32.7 %.

**Robustez ±20 %** (n): 16 → +0.050R (105 op.) · 18 → -0.047R (98 op.) · 20 → +0.020R (90 op.) · 22 → +0.266R (79 op.) · 24 → +0.247R (74 op.)

**Prueba final (mayo–octubre 2026, ya abierta, solo se reporta):** 9 operaciones, expectativa +0.370R, rendimiento +3.5 %.

**Cartera A contra Cartera B (mismas señales, capital de prueba):**

| Cartera | Rendimiento | Caída máxima | Calmar | Días de tope diario | Veces el freno total |
|---|---|---|---|---|---|
| A | -0.9 % | 15.8 % | -0.02 | 0 | 1 |
| B | +38.9 % | 21.3 % | 0.49 | 3 | 0 |

*Qué significa:* A y B ven las mismas señales, pero B tiene 2 lugares en vez de 3 y arriesga el doble, así que entran operaciones distintas. Cuando el resultado cambia tanto según qué señales caben, es señal de que depende de la suerte de cuáles entraron (ver Cupo).

**Con 46.18 USDT (Cartera A):** de 472 señales se habrían ejecutado 13 y **368 se habrían saltado por falta de capital**; para no saltarse la mitad harían falta unos **88 USDT**.
**Con 46.18 USDT (Cartera B):** de 472 señales se habrían ejecutado 47 y **40 se habrían saltado por falta de capital**; para no saltarse la mitad harían falta unos **88 USDT**.

**Cupo (A8):** 247 de 472 señales se quedaron fuera por falta de lugar. Elegir por fuerza: -0.9 %; al azar: +9.5 % típico; la fuerza le ganó al 18 %.

**Comisión (A9):** 0.075 % → +0.067R, -0.6 % · 0.100 % → +0.063R, -0.9 % · 0.150 % → +0.056R, -1.4 %

**Ventanas de walk-forward (12 meses para elegir, 3 para probar):**

| Prueba | Parámetro elegido | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01-01 a 2023-04-01 | `{'n': 20}` | 9 | -1.40 |
| 2023-04-01 a 2023-07-01 | `{'n': 20}` | 6 | -4.36 |
| 2023-07-01 a 2023-10-01 | `{'n': 20}` | 6 | -2.03 |
| 2023-10-01 a 2024-01-01 | `{'n': 20}` | 7 | +13.97 |
| 2024-01-01 a 2024-04-01 | `{'n': 20}` | 9 | +8.89 |
| 2024-04-01 a 2024-07-01 | `{'n': 20}` | 5 | -2.82 |
| 2024-07-01 a 2024-10-01 | `{'n': 20}` | 9 | -5.41 |
| 2024-10-01 a 2025-01-01 | `{'n': 100}` | 4 | +3.08 |
| 2025-01-01 a 2025-04-01 | `{'n': 20}` | 6 | -4.74 |
| 2025-04-01 a 2025-07-01 | `{'n': 50}` | 6 | -3.72 |
| 2025-07-01 a 2025-10-01 | `{'n': 20}` | 10 | +3.62 |
| 2025-10-01 a 2026-01-01 | `{'n': 20}` | 4 | +0.03 |
| 2026-01-01 a 2026-04-01 | `{'n': 20}` | 0 | +0.00 |
| 2026-04-01 a 2026-05-01 | `{'n': 20}` | 0 | +0.00 |

**Por año:** 2023: 28 op., +0.22R · 2024: 27 op., +0.14R · 2025: 26 op., -0.18R

## M2 — RANKING (las más fuertes): ❌ NO PASA

Rondas de ajuste usadas: 0 de 1 (se corrió la configuración pre-registrada tal cual) · 3 combinaciones probadas (L=21, L=30, L=60) · parámetros finales: `{'L': 21}`

**Compuertas:**

- ✅ 112 operaciones fuera de muestra (mínimo 40)
- ❌ factor de ganancia 0.81 (mínimo 1.3)
- ❌ expectativa -0.083R (mínimo +0.1R)
- ❌ 21 % de ventanas positivas (mínimo 40 % para motores lentos; contando solo las 12 ventanas con operaciones: 25 %)
- ❌ caída p95 de Monte Carlo 29.8 % (la peor entre suelto y en bloques; máximo 25 %)
- ❌ le gana al 8.0 % de los calendarios al azar (mínimo 90 %)
- ❌ Calmar fuera de muestra -0.17 contra 1.17 de R1 (debe ser mayor)
- ❌ robustez ±20 %: peor expectativa -0.134R

**Fuera de muestra (Cartera A, capital de prueba de 10,000 USDT):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 112 | cuántas veces entró |
| % ganadoras | 35.7 % | de cada 100, cuántas ganaron |
| Ganancia promedio | +0.97R | lo que deja una ganadora |
| Pérdida promedio | -0.67R | lo que quita una perdedora |
| Expectativa | -0.083R | promedio por operación, ya con costos |
| Factor de ganancia | 0.81 | ganado ÷ perdido |
| Peor racha | 8 pérdidas seguidas | prepárate para esto |
| Ventanas positivas | 21 % | en cuántos trimestres ganó (se pide 40 %) |
| Concentración | — % | qué parte del resultado viene de las 5 mejores operaciones |
| Rendimiento (valor a mercado) | -9.2 % | con 1 % de riesgo por operación |
| Caída máxima (valor a mercado) | 17.2 % | lo más que bajó desde un máximo |
| Calmar | -0.17 | contra 1.17 de R1 |
| Tiempo con alguna posición | 62 % | |

**Monte Carlo (10,000):** suelto → caída p95 28.7 %; en bloques de 20 días → caída p95 29.8 %, racha perdedora p95 18. Rendimiento en bloques entre -27.3 % y +16.6 %.

**Contra el azar (calendario):** la suma de (peso × rendimiento) real fue -8.69 %; la típica de 1,000 calendarios al azar +2.70 % y el 10 % mejor +14.86 %. Le gana al 8 %.

**Remuestreo en bloques de 20 días (curva diaria):** Calmar entre -0.32 y 0.38; caída máxima entre 8.8 % y 29.4 %.

**Robustez ±20 %** (L): 17 → -0.133R (117 op.) · 19 → -0.134R (119 op.) · 21 → +0.027R (107 op.) · 23 → -0.053R (116 op.) · 25 → -0.050R (113 op.)

**Prueba final (mayo–octubre 2026, ya abierta, solo se reporta):** 9 operaciones, expectativa +0.599R, rendimiento +5.1 %.

**Cartera A contra Cartera B (mismas señales, capital de prueba):**

| Cartera | Rendimiento | Caída máxima | Calmar | Días de tope diario | Veces el freno total |
|---|---|---|---|---|---|
| A | -9.2 % | 17.2 % | -0.17 | 0 | 1 |
| B | -23.0 % | 30.7 % | -0.25 | 0 | 1 |

*Qué significa:* A y B ven las mismas señales, pero B tiene 2 lugares en vez de 3 y arriesga el doble, así que entran operaciones distintas. Cuando el resultado cambia tanto según qué señales caben, es señal de que depende de la suerte de cuáles entraron (ver Cupo).

**Con 46.18 USDT (Cartera A):** de 359 señales se habrían ejecutado 0 y **308 se habrían saltado por falta de capital**; para no saltarse la mitad harían falta unos **125 USDT**.
**Con 46.18 USDT (Cartera B):** de 359 señales se habrían ejecutado 0 y **308 se habrían saltado por falta de capital**; para no saltarse la mitad harían falta unos **62 USDT**.

**Cupo (A8):** 80 de 359 señales se quedaron fuera por falta de lugar. Elegir por fuerza: -9.2 %; al azar: -9.0 % típico; la fuerza le ganó al 45 %.

**Comisión (A9):** 0.075 % → -0.081R, -9.0 % · 0.100 % → -0.083R, -9.2 % · 0.150 % → -0.088R, -9.6 %

**Ventanas de walk-forward (12 meses para elegir, 3 para probar):**

| Prueba | Parámetro elegido | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01-01 a 2023-04-01 | `{'L': 21}` | 11 | -2.85 |
| 2023-04-01 a 2023-07-01 | `{'L': 21}` | 11 | -2.09 |
| 2023-07-01 a 2023-10-01 | `{'L': 21}` | 7 | -3.75 |
| 2023-10-01 a 2024-01-01 | `{'L': 21}` | 5 | +14.83 |
| 2024-01-01 a 2024-04-01 | `{'L': 30}` | 13 | -6.62 |
| 2024-04-01 a 2024-07-01 | `{'L': 30}` | 10 | -5.77 |
| 2024-07-01 a 2024-10-01 | `{'L': 30}` | 7 | -1.86 |
| 2024-10-01 a 2025-01-01 | `{'L': 30}` | 13 | +1.10 |
| 2025-01-01 a 2025-04-01 | `{'L': 21}` | 9 | -3.66 |
| 2025-04-01 a 2025-07-01 | `{'L': 21}` | 9 | -0.09 |
| 2025-07-01 a 2025-10-01 | `{'L': 30}` | 11 | +1.83 |
| 2025-10-01 a 2026-01-01 | `{'L': 21}` | 6 | -0.39 |
| 2026-01-01 a 2026-04-01 | `{'L': 21}` | 0 | +0.00 |
| 2026-04-01 a 2026-05-01 | `{'L': 21}` | 0 | +0.00 |

**Por año:** 2023: 34 op., +0.18R · 2024: 43 op., -0.31R · 2025: 35 op., -0.07R

## M3 — ESTELA (copy trade medido)

- Ruta `data/futures/um/daily/metrics/<SÍMBOLO>/`: existe ✅. BTC tiene datos desde 2020-09-01.
- Significado de las columnas **verificado** contra la API pública de Binance Futuros (2026-11-07), fila por fila:

| Columna | Ruta de la API | Error mediano |
|---|---|---|
| `count_toptrader_long_short_ratio` | `/futures/data/topLongShortAccountRatio` | 0.042 % |
| `sum_toptrader_long_short_ratio` | `/futures/data/topLongShortPositionRatio` | 0.031 % |
| `count_long_short_ratio` | `/futures/data/globalLongShortAccountRatio` | 0.056 % |
| `sum_taker_long_short_vol_ratio` | `/futures/data/takerlongshortRatio` | 0.005 % |
| `sum_open_interest` | `/futures/data/openInterestHist` | 0.008 % |

  Así que `top_largo` usa la razón de POSICIONES de los top traders (`sum_toptrader_long_short_ratio`) y `masa_largo` la razón de CUENTAS de todos (`count_long_short_ratio`), igual que las rutas en vivo de la especificación.
- Monedas "grandes" con perpetuo: 135. Fecha desde la que hay datos: BTC 2020-09-01, AAVE 2021-12-01, ADA 2021-12-01, ALGO 2021-12-01, ATOM 2021-12-01, AVAX 2021-12-01, AXS 2021-12-01, BCH 2021-12-01, BLZ 2021-12-01, BNB 2021-12-01, CHZ 2021-12-01, COMP 2021-12-01, CRV 2021-12-01, DASH 2021-12-01, DOT 2021-12-01, DYDX 2021-12-01, ENS 2021-12-01, EOS 2021-12-01, ETC 2021-12-01, ETH 2021-12-01, FIL 2021-12-01, FTM 2021-12-01, GALA 2021-12-01, HBAR 2021-12-01, LINA 2021-12-01, LINK 2021-12-01, LTC 2021-12-01, LUNA 2021-12-01, MANA 2021-12-01, MASK 2021-12-01, MATIC 2021-12-01, MKR 2021-12-01, NEAR 2021-12-01, RAY 2021-12-01, RUNE 2021-12-01, SAND 2021-12-01, SOL 2021-12-01, STMX 2021-12-01, SUSHI 2021-12-01, TRB 2021-12-01, TRX 2021-12-01, UNFI 2021-12-01, UNI 2021-12-01, WAVES 2021-12-01, XLM 2021-12-01, XRP 2021-12-01, ZEC 2021-12-01, ZEN 2021-12-01, ZIL 2021-12-01, ICP 2021-12-23, ROSE 2021-12-30, GMT 2022-03-15, APE 2022-03-17, FTT 2022-04-15, JASMY 2022-04-20, GAL 2022-05-05, OP 2022-06-01, INJ 2022-08-17, STG 2022-08-25, LDO 2022-09-22, APT 2022-10-19, QNT 2022-10-20, FET 2023-01-17, HOOK 2023-01-23, MAGIC 2023-01-25, RNDR 2023-02-03, AGIX 2023-02-16, CFX 2023-02-20, STX 2023-02-21, ARB 2023-03-23, ID 2023-03-23, EDU 2023-04-30, SUI 2023-05-03, WLD 2023-07-24, PENDLE 2023-07-28, YGG 2023-08-05, SEI 2023-08-17, CYBER 2023-08-21, HIFI 2023-09-16, ARK 2023-09-19, LOOM 2023-10-11, GAS 2023-10-25, SLP 2023-10-31, TIA 2023-10-31, CAKE 2023-11-02, TWT 2023-11-03, JTO 2023-12-08, AUCTION 2023-12-15, AI 2024-01-08, XAI 2024-01-09, MANTA 2024-01-18, ONDO 2024-01-20, ALT 2024-01-25, JUP 2024-01-31, OM 2024-02-13, STRK 2024-02-20, TON 2024-03-01, ETHFI 2024-03-18, ENA 2024-04-02, W 2024-04-03, SAGA 2024-04-09, TAO 2024-04-11, BB 2024-05-13, IO 2024-06-11, ZK 2024-06-17, ZRO 2024-06-20, SYN 2024-08-16, SUN 2024-08-22, EIGEN 2024-10-01, TROY 2024-10-31, VIRTUAL 2024-12-10, USUAL 2024-12-18, DEXE 2024-12-24, BIO 2025-01-03, S 2025-01-16, BERA 2025-02-06, TST 2025-02-09, INIT 2025-04-16, BANK 2025-04-18, HYPE 2025-05-30, NEWT 2025-06-19, XPL 2025-08-22, SOMI 2025-08-25, LINEA 2025-09-01, AVNT 2025-09-09, ASTER 2025-09-19, GIGGLE 2025-10-09, 币安人生 2025-10-20, AT 2025-10-29, KITE 2025-10-29, SENT 2025-11-14, NIGHT 2025-12-10, ZAMA 2026-01-09, CHIP 2026-04-16, RE 2026-06-18.
- Sin datos de top traders (no tienen perpetuo o no hay archivo): FTTUSDT, SLPUSDT, SNDKBUSDT, SOXLBUSDT, SPCXBUSDT, TWTUSDT.

**Estudio de eventos** (26255 días-moneda, solo días en que la moneda era "grande"; 10 pruebas en total, todas reportadas):

| Prueba | Días | Eventos | Signo esperado | Efecto (puntos %) | Intervalo 95 % | Años con el signo esperado | ¿Pasa? |
|---|---|---|---|---|---|---|---|
| H1_D3_z1.0 | 3 | 856 | + | -0.16 | [-0.93, +0.68] | 25 % de 4 | ❌ |
| H1_D3_z1.0 | 7 | 850 | + | -0.82 | [-1.87, +0.33] | 0 % de 4 | ❌ |
| H1_D3_z1.5 | 3 | 385 | + | -0.12 | [-1.24, +1.00] | 25 % de 4 | ❌ |
| H1_D3_z1.5 | 7 | 380 | + | -0.62 | [-2.19, +0.95] | 0 % de 4 | ❌ |
| H1_D7_z1.0 | 3 | 1476 | + | -0.23 | [-0.78, +0.33] | 0 % de 4 | ❌ |
| H1_D7_z1.0 | 7 | 1462 | + | -0.63 | [-1.88, +0.63] | 0 % de 4 | ❌ |
| H1_D7_z1.5 | 3 | 777 | + | -0.25 | [-0.94, +0.49] | 25 % de 4 | ❌ |
| H1_D7_z1.5 | 7 | 770 | + | -0.72 | [-2.30, +0.91] | 25 % de 4 | ❌ |
| H2 | 3 | 3405 | − | -0.63 | [-1.18, -0.12] | 100 % de 5 | ✅ |
| H2 | 7 | 3365 | − | -1.08 | [-2.23, +0.01] | 80 % de 5 | ❌ |

*Cómo leerlo:* "Efecto" = cuántos puntos porcentuales más (o menos) sube la moneda en los siguientes 3 o 7 días después del evento, comparado con un día cualquiera. Para pasar, el efecto debe ir en la dirección de la hipótesis en al menos 70 % de los años y su intervalo no debe tocar el cero.

**Resultado: pasa H2 a 3 días** (1 de 10 pruebas). Cuando la gente está muy cargada en largo, la moneda rinde menos los días siguientes. H1 (seguir a los top traders) NO pasa en ninguna versión; de hecho su efecto salió al revés de lo esperado.

*Con cuidado:* se hicieron 10 pruebas; con tantas, una puede pasar por suerte (al 95 % se esperaría media prueba falsa). A favor: H2 tiene el signo esperado en los dos horizontes y a 7 días su intervalo casi no toca el cero.

Por la regla de la v2, el uso principal es el **VETO** de entradas de M1 y M2. Se midieron con y sin veto:

### Paso 2 — M1 y M2 con y sin el veto de ESTELA

Misma validación completa (walk-forward, azar calendario, remuestreo, robustez); la única diferencia es que no se abre una compra el día en que la masa de cuentas está en el 10 % más cargado en largo de sus 90 días previos (H2). Las monedas sin datos de ESTELA no se vetan nunca.

| Motor | Versión | Señales fuera de muestra | Operaciones | Expectativa | Factor | Calmar | Azar calendario | Ventanas + | Robustez (peor) | ¿Pasa? |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 | sin veto | 472 | 81 | +0.063R | 1.12 | -0.02 | 26 % | 36 % | -0.047R | ❌ |
| M1 | con veto | 456 | 72 | +0.002R | 1.00 | -0.09 | 13 % | 21 % | -0.067R | ❌ |
| M2 | sin veto | 359 | 112 | -0.083R | 0.81 | -0.17 | 8 % | 21 % | -0.134R | ❌ |
| M2 | con veto | 330 | 103 | -0.070R | 0.84 | -0.14 | 9 % | 29 % | -0.106R | ❌ |

- **M1 con veto:** no pasa 7 de 8 compuertas: factor de ganancia 1.00 (mínimo 1.3); expectativa +0.002R (mínimo +0.1R); 21 % de ventanas positivas (mínimo 40 % para motores lentos; contando solo las 12 ventanas con operaciones: 25 %); caída p95 de Monte Carlo 25.1 % (la peor entre suelto y en bloques; máximo 25 %); le gana al 12.9 % de los calendarios al azar (mínimo 90 %); Calmar fuera de muestra -0.09 contra 1.17 de R1 (debe ser mayor); robustez ±20 %: peor expectativa -0.067R.
- **M2 con veto:** no pasa 7 de 8 compuertas: factor de ganancia 0.84 (mínimo 1.3); expectativa -0.070R (mínimo +0.1R); 29 % de ventanas positivas (mínimo 40 % para motores lentos; contando solo las 12 ventanas con operaciones: 33 %); caída p95 de Monte Carlo 29.9 % (la peor entre suelto y en bloques; máximo 25 %); le gana al 9.2 % de los calendarios al azar (mínimo 90 %); Calmar fuera de muestra -0.14 contra 1.17 de R1 (debe ser mayor); robustez ±20 %: peor expectativa -0.106R.

*Qué significa:* en M1 el veto cambia la expectativa -0.061R por operación · en M2 el veto cambia la expectativa +0.013R por operación. **Ni con veto pasan M1 ni M2**, así que siguen APAGADOS y el veto no tiene a quién aplicarse: queda apagado (`veto_activo: false`). ESTELA sigue guardando la foto diaria para volver a medir con datos nuevos.

## Cuántas cosas se probaron (para que no haya trampa)

- Motores: M1 3 combinaciones, M2 3 combinaciones (rejillas pre-registradas, 1 ronda de ajustes): 6 en total.
- Referencias: 3 (R0, R1, R2). M0 = R1, sin parámetros que ajustar.
- ESTELA: 10 pruebas (2 hipótesis × rejilla × 2 horizontes) y 2 validaciones con veto (M1 y M2).
- Auditoría: 4 variantes de salida y 3 comisiones sobre E1 (solo para entender la v1; nada de eso se usa para elegir).
- Todas aparecen en este informe, no solo la mejor.

## Lo que estas pruebas NO pueden garantizar

- El pasado no garantiza el futuro. La prueba realmente limpia es el **papel desde hoy**.
- Mayo–octubre 2026 ya se había visto en la v1: sus números se reportan, pero ya no son una prueba a ciegas.
- Con 46.18 USDT muchas señales se saltan por los mínimos de Binance; los resultados con capital de prueba son para medir la idea, no la cuenta.
- El universo "grandes" usa la lista de memes de hoy para excluirlas (algo de sesgo). Las monedas que Binance borró por completo de su API no se pudieron incluir.
- Desde junio–julio 2026 Binance lista **acciones tokenizadas** con mucho volumen (por ejemplo SNDKB, SOXLB —un fondo apalancado 3x— y SPCXB). El filtro de universo no las reconoce, así que pudieron entrar a "grandes" en los últimos meses del periodo. El 9 nov 2026 tres de las 15 grandes eran de este tipo.
- Las reglas de Binance (mínimos y decimales) usadas son las actuales; en el pasado algunas eran distintas.
