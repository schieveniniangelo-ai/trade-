# VALIDACIÓN V2 — "MAREA"

Generado el 11/11/2026 18:30 · reglamento 2.0.1 · datos del 01/01/2022 al 31/10/2026.

## Resumen en una frase

**M1 pasa(n) todas las compuertas históricas** y va(n) a PAPEL. Para dinero real faltan 6 semanas y 10 operaciones de papel, cero errores de conciliación y el OK de Ángelo.

| Motor | ¿Pasa? | Operaciones fuera de muestra | Expectativa (R) | Factor de ganancia | Calmar fuera de muestra | Le gana al azar (calendario) | Caída p95 (bloques) | Prueba final (ya abierta) |
|---|---|---|---|---|---|---|---|---|
| M1 Tendencia lenta | ✅ | 80 | +0.091 | 1.35 | 0.90 | 93 % | 19.0 % | 9 op., +0.020R |
| M2 Rotación lenta | ❌ | 80 | -0.030 | 1.35 | 0.90 | — % | 19.0 % | 9 op., +0.020R |
| M0 Marea BTC (= R1) | ❌ (como cartera) | 14 cambios | — | — | 0.80 | 70 % | 45.0 % | -2.0 % |

**Cómo leer esta tabla:**
- *Expectativa (R)*: lo que deja en promedio cada operación, en unidades de riesgo, ya con costos. +0.10R = si arriesgas 1 peso, te quedan 10 centavos.
- *Factor de ganancia*: lo ganado entre lo perdido. Se pide 1.3 o más.
- *Calmar*: rendimiento por año ÷ la peor caída. Más alto = más ganancia por cada susto. **R1 hizo 0.80 fuera de muestra: hay que ganarle.**
- *Le gana al azar (calendario)*: a cuántos de 1,000 calendarios al azar (mismas monedas, mismo número de entradas, mismo tiempo invertido, otras fechas) supera. Se pide 90 %.
- *Caída p95 (bloques)*: en el peor 5 % de 10,000 simulaciones que respetan que las pérdidas llegan juntas, cuánto caería el capital. Máximo 25 %.
- *Prueba final*: mayo–octubre 2026. **Ya se abrió en la v1**, así que se reporta pero no decide: la prueba limpia es el papel desde hoy.

## Auditoría A1–A9 (lo que le faltaba a la v1)

Se midió sobre **E1** (la tendencia de la v1) con sus parámetros finales `{'n': 20}`, del 01/01/2023 al 30/04/2026 (el periodo fuera de muestra de la v1). No se optimizó nada nuevo.

**A1 — Monte Carlo suelto contra en bloques por fecha.**

| | Suelto (v1) | En bloques de 20 días (v2) | Qué significa |
|---|---|---|---|
| Caída típica | 10.0 % | 13.0 % | la mitad de las simulaciones cae más que esto |
| Caída en el peor 5 % | 18.0 % | 25.0 % | lo que se usa para la compuerta |
| Racha perdedora (peor 5 %) | 12 | 15 | pérdidas seguidas |
| Probabilidad de tocar el freno de 15 % | 9.0 % | 20.0 % | |

**A2 — Caída con operaciones cerradas contra curva diaria a valor de mercado.**

| | Solo cerradas (v1) | A valor de mercado (v2) |
|---|---|---|
| Caída máxima | 12.0 % | 16.0 % |
| Días que tocaron el tope diario | 1 | 4 |
| Semanas que tocaron el tope semanal | 0 | 1 |
| Veces que se habría activado el freno total | 0 | 1 |
| Rendimiento | +20.0 % | +17.0 % |

Con valor a mercado, los topes y el tamaño de cada operación usan el capital real del momento (las posiciones abiertas que van perdiendo cuentan). Por eso el número de operaciones y el rendimiento cambian un poco.

**A3 — ¿Qué tanto pesan las reglas de salida?** Misma entrada de E1 y misma muestra de entradas al azar; solo cambia la salida.

| Salida | E1: operaciones | E1: expectativa | E1: % ganadoras | E1: ganancia promedio | Azar: expectativa | Azar: % ganadoras |
|---|---|---|---|---|---|---|
| (a) la de la v1 | 100 | +0.050R | 40.0 % | +2.00R | -0.010R | 35.0 % |

**A4 — ¿Las monedas chicas arrastraban a E1?**

| Universo | Operaciones | Expectativa | Factor de ganancia | Rendimiento de cartera |
|---|---|---|---|---|
| Todas (456 monedas) | 100 | +0.050R | 1.20 | +15.0 % |
| Solo las 15 grandes del día | 30 | +0.150R | 1.60 | — |
| Solo las que NO son grandes | 70 | -0.010R | 0.98 | — |

**A5 — E3 (comprar lo que se desploma) queda archivada.** Le ganó al 0 % del azar en la v1: comprar caídas fue peor que comprar a ciegas. No se prueban más ideas de "comprar la caída"; es evidencia a favor de seguir la tendencia.

**A6 — Memes fuera de la v2.** En la v1, E4 quedó casi en empate con BTC alcista (+0.032R en 45 operaciones) y fatal con BTC bajista (−0.767R).

**A7 — Concentración.** En E1 (periodo de la auditoría), las 5 mejores operaciones equivalen al 140 % de la suma de resultados (suma total +12.5R). En la v1, 2 de 14 ventanas dieron casi todo lo positivo: por eso en los motores lentos la compuerta de ventanas positivas baja de 60 % a 40 % y en cada motor se reporta qué parte del resultado viene de sus 5 mejores operaciones (más de 100 % = sin esas 5, pierde).

**A8 — Cupo.** De 300 señales de E1, 40 se quedaron fuera por falta de lugar (posiciones o calor lleno). Elegir por "fuerza" dio +15.0 %; elegir al azar entre las señales del mismo momento dio +14.0 % típico (200 repeticiones). La "fuerza" le ganó al 60 % de esas elecciones al azar.

**A9 — Sensibilidad a la comisión (por lado).**

| Comisión | Operaciones | Expectativa | Rendimiento de cartera |
|---|---|---|---|
| 0.100 % | 100 | +0.050R | +15.0 % |

## Referencias obligatorias (lo simple contra lo que todo compite)

Señal al cierre diario (00:00 UTC), ejecución en la apertura siguiente, comisión 0.10 % + deslizamiento 0.05 % por lado.

| Referencia | Periodo | Rendimiento | Por año | Caída máxima | Calmar | Tiempo invertido | Operaciones |
|---|---|---|---|---|---|---|---|
| R0 Referencia R0 | 2022-01 a 2026-10 | +150.0 % | +37.5 % | 40.0 % | 0.50 | 60 % | 12 |
| R0 Referencia R0 | fuera de muestra (2023-01 a 2026-04) | +150.0 % | +37.5 % | 40.0 % | 0.50 | 60 % | 12 |
| R0 Referencia R0 | prueba final (2026-05 a 2026-10) | +150.0 % | +37.5 % | 40.0 % | 0.50 | 60 % | 12 |
| R1 Referencia R1 | 2022-01 a 2026-10 | +90.0 % | +22.5 % | 40.0 % | 0.50 | 60 % | 12 |
| R1 Referencia R1 | fuera de muestra (2023-01 a 2026-04) | +90.0 % | +22.5 % | 40.0 % | 0.80 | 60 % | 12 |
| R1 Referencia R1 | prueba final (2026-05 a 2026-10) | +90.0 % | +22.5 % | 40.0 % | 0.50 | 60 % | 12 |
| R2 Referencia R2 | 2022-01 a 2026-10 | -20.0 % | -5.0 % | 40.0 % | 0.50 | 60 % | 12 |
| R2 Referencia R2 | fuera de muestra (2023-01 a 2026-04) | -20.0 % | -5.0 % | 40.0 % | 0.50 | 60 % | 12 |
| R2 Referencia R2 | prueba final (2026-05 a 2026-10) | -20.0 % | -5.0 % | 40.0 % | 0.50 | 60 % | 12 |

**Por año:**

| Referencia | 2022 | 2023 |
|---|---|---|
| R0 | +90 % | +150 % |
| R1 | +30 % | +90 % |
| R2 | -80 % | -20 % |

*Qué significa:* aguantar BTC (R0) gana mucho en los años buenos pero cae hasta 67 %. El filtro de marea (R1) se sale cuando BTC pierde su media de 200 días: deja ir parte de la subida, pero corta la caída a la mitad. La canasta de grandes (R2) sufrió porque las altcoins grandes cayeron mucho en 2024–2025 aunque BTC estuviera arriba de su media.

## M0 — R1 como candidata (se evalúa como cartera)

**Compuertas que le aplican:**

- ❌ Le gana al 90 % de los calendarios al azar

- Calendario al azar: R1 hizo +90.0 % fuera de muestra; un calendario al azar con las mismas 14 entradas y el mismo 60 % de tiempo invertido hizo +50.0 % típico (el 10 % mejor, +110.0 %).
- Remuestreo en bloques de 20 días: Calmar entre 0.10 y 1.40 (90 % de los casos); caída máxima típica 30.0 %, en el peor 5 % 45.0 %.
- Robustez de la media (fuera de muestra):

| Media | Rendimiento | Caída máxima | Calmar |
|---|---|---|---|
| 160 días | +80.0 % | 35.0 % | 0.70 |

- Sensibilidad a la comisión: 0.100 % → Calmar 0.80 · 0.200 % → Calmar 0.70

- Topes con la curva a valor de mercado (todo el dinero en BTC cuando la marea está alta): Cartera A: 3 días de tope diario, 1 veces el freno total

**M0 dentro de las carteras** (como correría en papel: motor de riesgo, stop de catástrofe de 15 %, máximo 30 % en BTC), fuera de muestra:

| Cartera | Rendimiento | Caída máxima | Calmar | Caída p95 (bloques) | Operaciones | Con 46.18 USDT: ejecutadas / saltadas por capital |
|---|---|---|---|---|---|---|
| A | +0.0 % | 0.0 % | — | — % | 0 | 0 / 14 |

**Ojo con la Cartera A:** con 1 % de riesgo y un stop de 15 %, la compra sale de unos 3 USDT, menos que el mínimo de 5 USDT de Binance. Con 46.18 USDT la Cartera A **no puede comprar BTC nunca** con M0 (haría falta capital de unos 88 USDT, como decía la tabla de la especificación). La Cartera B (2 %) sí cabe.

*Qué significa:* M0 no le gana a nada: ES la referencia. Si va a papel es como línea base honesta. En las carteras A y B corre a través del motor de riesgo (riesgo por operación ÷ stop de catástrofe de 15 %, máximo 30 % del capital en BTC), así que tiene una parte de BTC, no todo el dinero; la versión "todo adentro" se sigue aparte como referencia R1.

## M1 — Tendencia lenta: ✅ PASA

Rondas de ajuste usadas: 0 de 1 (se corrió la configuración pre-registrada tal cual) · 4 combinaciones probadas (sma 100, sma 200) · parámetros finales: `{'sma': 200}`

**Compuertas:**

- ✅ Al menos 60 operaciones
- ✅ Calmar mayor que el de R1

**Fuera de muestra (Cartera A, capital de prueba de 10,000 USDT):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 80 | cuántas veces entró |
| % ganadoras | 38.0 % | de cada 100, cuántas ganaron |
| Ganancia promedio | +2.40R | lo que deja una ganadora |
| Pérdida promedio | -1.00R | lo que quita una perdedora |
| Expectativa | +0.091R | promedio por operación, ya con costos |
| Factor de ganancia | 1.35 | ganado ÷ perdido |
| Peor racha | 8 pérdidas seguidas | prepárate para esto |
| Ventanas positivas | 50 % | en cuántos trimestres ganó (se pide 40 %) |
| Concentración | 85 % | qué parte del resultado viene de las 5 mejores operaciones |
| Rendimiento (valor a mercado) | +30.0 % | con 1 % de riesgo por operación |
| Caída máxima (valor a mercado) | 12.0 % | lo más que bajó desde un máximo |
| Calmar | 0.90 | contra 0.80 de R1 |
| Tiempo con alguna posición | 61 % | |

**Monte Carlo (10,000):** suelto → caída p95 15.0 %; en bloques de 20 días → caída p95 19.0 %, racha perdedora p95 11. Rendimiento en bloques entre -5.0 % y +60.0 %.

**Contra el azar (calendario):** la suma de (peso × rendimiento) real fue +1.20 %; la típica de 1,000 calendarios al azar +0.30 % y el 10 % mejor +0.90 %. Le gana al 93 %.

**Remuestreo en bloques de 20 días (curva diaria):** Calmar entre 0.20 y 1.60; caída máxima entre 6.0 % y 21.0 %.

**Robustez ±20 %** (sma): 160 → +0.040R (90 op.) · 240 → +0.100R (70 op.)

**Prueba final (mayo–octubre 2026, ya abierta, solo se reporta):** 9 operaciones, expectativa +0.020R, rendimiento +1.5 %.

**Cartera A contra Cartera B (mismas señales, capital de prueba):**

| Cartera | Rendimiento | Caída máxima | Calmar | Días de tope diario | Veces el freno total |
|---|---|---|---|---|---|
| A | +30.0 % | 12.0 % | 0.90 | 2 | 0 |

*Qué significa:* A y B ven las mismas señales, pero B tiene 2 lugares en vez de 3 y arriesga el doble, así que entran operaciones distintas. Cuando el resultado cambia tanto según qué señales caben, es señal de que depende de la suerte de cuáles entraron (ver Cupo).

**Con 46.18 USDT (Cartera A):** de 80 señales se habrían ejecutado 10 y **70 se habrían saltado por falta de capital**; para no saltarse la mitad harían falta unos **150 USDT**.
**Con 46.18 USDT (Cartera B):** de 80 señales se habrían ejecutado 40 y **40 se habrían saltado por falta de capital**.

**Cupo (A8):** 12 de 92 señales se quedaron fuera por falta de lugar. Elegir por fuerza: +30.0 %; al azar: +22.0 % típico; la fuerza le ganó al 80 %.

**Comisión (A9):** 0.100 % → +0.090R, +30.0 % · 0.200 % → +0.050R, +18.0 %

**Ventanas de walk-forward (12 meses para elegir, 3 para probar):**

| Prueba | Parámetro elegido | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01 a 2023-03 | `{'sma': 200}` | 6 | +1.50 |
| 2023-04 a 2023-06 | `{'sma': 100}` | 0 | — |

**Por año:** 2023: 30 op., +0.12R

## M2 — Rotación lenta: ❌ NO PASA

Rondas de ajuste usadas: 0 de 1 (se corrió la configuración pre-registrada tal cual) · 4 combinaciones probadas (sma 100, sma 200) · parámetros finales: `{'sma': 200}`

**Compuertas:**

- ✅ Al menos 60 operaciones
- ❌ Calmar mayor que el de R1

**Fuera de muestra (Cartera A, capital de prueba de 10,000 USDT):**

| Número | Valor | Qué significa |
|---|---|---|
| Operaciones | 80 | cuántas veces entró |
| % ganadoras | 38.0 % | de cada 100, cuántas ganaron |
| Ganancia promedio | +2.40R | lo que deja una ganadora |
| Pérdida promedio | -1.00R | lo que quita una perdedora |
| Expectativa | -0.030R | promedio por operación, ya con costos |
| Factor de ganancia | 1.35 | ganado ÷ perdido |
| Peor racha | 8 pérdidas seguidas | prepárate para esto |
| Ventanas positivas | 50 % | en cuántos trimestres ganó (se pide 40 %) |
| Concentración | 85 % | qué parte del resultado viene de las 5 mejores operaciones |
| Rendimiento (valor a mercado) | +30.0 % | con 1 % de riesgo por operación |
| Caída máxima (valor a mercado) | 12.0 % | lo más que bajó desde un máximo |
| Calmar | 0.90 | contra 0.80 de R1 |
| Tiempo con alguna posición | 61 % | |

**Monte Carlo (10,000):** suelto → caída p95 15.0 %; en bloques de 20 días → caída p95 19.0 %, racha perdedora p95 11. Rendimiento en bloques entre -5.0 % y +60.0 %.

**Prueba final (mayo–octubre 2026, ya abierta, solo se reporta):** 9 operaciones, expectativa +0.020R, rendimiento +1.5 %.

**Cartera A contra Cartera B (mismas señales, capital de prueba):**

| Cartera | Rendimiento | Caída máxima | Calmar | Días de tope diario | Veces el freno total |
|---|---|---|---|---|---|
| A | +30.0 % | 12.0 % | 0.90 | 2 | 0 |

*Qué significa:* A y B ven las mismas señales, pero B tiene 2 lugares en vez de 3 y arriesga el doble, así que entran operaciones distintas. Cuando el resultado cambia tanto según qué señales caben, es señal de que depende de la suerte de cuáles entraron (ver Cupo).


**Ventanas de walk-forward (12 meses para elegir, 3 para probar):**

| Prueba | Parámetro elegido | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01 a 2023-03 | `{'sma': 200}` | 6 | +1.50 |
| 2023-04 a 2023-06 | `{'sma': 100}` | 0 | — |

## M3 — ESTELA (copy trade medido)

- Ruta `data/futures/um/daily/metrics/<SÍMBOLO>/`: existe ✅. BTC tiene datos desde 2021-12-01.
- Significado de las columnas **verificado** contra la API pública de Binance Futuros (2026-11-09), fila por fila:

| Columna | Ruta de la API | Error mediano |
|---|---|---|
| `top_largo` | `/futures/data/topLongShortPositionRatio` | 0.010 % |

  Así que `top_largo` usa la razón de POSICIONES de los top traders (`sum_toptrader_long_short_ratio`) y `masa_largo` la razón de CUENTAS de todos (`count_long_short_ratio`), igual que las rutas en vivo de la especificación.
- Monedas "grandes" con perpetuo: 2. Fecha desde la que hay datos: BTC 2021-12-01, ETH 2022-01-01.
- Sin datos de top traders (no tienen perpetuo o no hay archivo): XYZUSDT.

**Estudio de eventos** (9000 días-moneda, solo días en que la moneda era "grande"; 2 pruebas en total, todas reportadas):

| Prueba | Días | Eventos | Signo esperado | Efecto (puntos %) | Intervalo 95 % | Años con el signo esperado | ¿Pasa? |
|---|---|---|---|---|---|---|---|
| H1 top | 3 | 50 | + | -0.40 | [-0.90, +0.10] | 20 % de 5 | ❌ |
| H2 masa | 7 | 60 | − | -1.20 | [-2.00, -0.30] | 80 % de 5 | ✅ |

*Cómo leerlo:* "Efecto" = cuántos puntos porcentuales más (o menos) sube la moneda en los siguientes 3 o 7 días después del evento, comparado con un día cualquiera. Para pasar, el efecto debe ir en la dirección de la hipótesis en al menos 70 % de los años y su intervalo no debe tocar el cero.

**Resultado: pasa H2 masa a 7 días** (1 de 2 pruebas). Cuando la gente está muy cargada en largo, la moneda rinde menos los días siguientes. H1 (seguir a los top traders) NO pasa en ninguna versión; de hecho su efecto salió al revés de lo esperado.

*Con cuidado:* se hicieron 2 pruebas; con tantas, una puede pasar por suerte (al 95 % se esperaría media prueba falsa). A favor: H2 tiene el signo esperado en los dos horizontes y a 7 días su intervalo casi no toca el cero.

Por la regla de la v2, el uso principal es el **VETO** de entradas de M1 y M2. Se midieron con y sin veto:

### Paso 2 — M1 y M2 con y sin el veto de ESTELA

Misma validación completa (walk-forward, azar calendario, remuestreo, robustez); la única diferencia es que no se abre una compra el día en que la masa de cuentas está en el 10 % más cargado en largo de sus 90 días previos (H2). Las monedas sin datos de ESTELA no se vetan nunca.

| Motor | Versión | Señales fuera de muestra | Operaciones | Expectativa | Factor | Calmar | Azar calendario | Ventanas + | Robustez (peor) | ¿Pasa? |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 | sin veto | 92 | 80 | +0.091R | 1.35 | 0.90 | 93 % | 50 % | +0.040R | ✅ |
| M1 | con veto | 80 | 80 | -0.030R | 1.35 | 0.90 | 93 % | 50 % | +0.040R | ❌ |
| M2 | sin veto | 92 | 80 | -0.030R | 1.35 | 0.90 | — % | 50 % | —R | ❌ |
| M2 | con veto | 80 | 80 | -0.030R | 1.35 | 0.90 | — % | 50 % | —R | ❌ |

- **M1 con veto:** no pasa 1 de 2 compuertas: Calmar mayor que el de R1.
- **M2 con veto:** no pasa 1 de 2 compuertas: Calmar mayor que el de R1.

*Qué significa:* en M1 el veto cambia la expectativa -0.121R por operación · en M2 el veto cambia la expectativa +0.000R por operación. **Ni con veto pasan M1 ni M2**, así que siguen APAGADOS y el veto no tiene a quién aplicarse: queda apagado (`veto_activo: false`). ESTELA sigue guardando la foto diaria para volver a medir con datos nuevos.

## Cuántas cosas se probaron (para que no haya trampa)

- Motores: M1 4 combinaciones, M2 4 combinaciones (rejillas pre-registradas, 1 ronda de ajustes): 8 en total.
- Referencias: 3 (R0, R1, R2). M0 = R1, sin parámetros que ajustar.
- ESTELA: 2 pruebas (2 hipótesis × rejilla × 2 horizontes) y 2 validaciones con veto (M1 y M2).
- Auditoría: 4 variantes de salida y 3 comisiones sobre E1 (solo para entender la v1; nada de eso se usa para elegir).
- Todas aparecen en este informe, no solo la mejor.

## Lo que estas pruebas NO pueden garantizar

- El pasado no garantiza el futuro. La prueba realmente limpia es el **papel desde hoy**.
- Mayo–octubre 2026 ya se había visto en la v1: sus números se reportan, pero ya no son una prueba a ciegas.
- Con 46.18 USDT muchas señales se saltan por los mínimos de Binance; los resultados con capital de prueba son para medir la idea, no la cuenta.
- El universo "grandes" usa la lista de memes de hoy para excluirlas (algo de sesgo). Las monedas que Binance borró por completo de su API no se pudieron incluir.
- Desde junio–julio 2026 Binance lista **acciones tokenizadas** con mucho volumen (por ejemplo SNDKB, SOXLB —un fondo apalancado 3x— y SPCXB). El filtro de universo no las reconoce, así que pudieron entrar a "grandes" en los últimos meses del periodo. El 9 nov 2026 tres de las 15 grandes eran de este tipo.
- Las reglas de Binance (mínimos y decimales) usadas son las actuales; en el pasado algunas eran distintas.
