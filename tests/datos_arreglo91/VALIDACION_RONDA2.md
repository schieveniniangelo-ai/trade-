# VALIDACIÓN — RONDA 2

Generado el 11/11/2026 18:30 · reglamento 2.0.1 · datos de enero 2022 a octubre 2026.

## Resumen en una frase

**Pasaron todas las compuertas: E6.** Siguiente paso: 30 días y 30 operaciones en papel (desde noviembre de 2026) dentro de lo esperado, antes de cualquier dinero real.

## Las reglas de esta ronda (escritas ANTES de ver resultados)

- Mismas compuertas y mismo motor de riesgo que la ronda 1.
- La prueba final de mayo–octubre 2026 ya se abrió en la ronda 1: ahora es una ventana más del walk-forward y además una compuerta extra (debe salir positiva). **Noviembre 2026 en adelante es la prueba en papel.**
- **Más estricto por probar muchas ideas** (8 en total con los mismos datos): debe ganarle al **98.75 %** de las entradas al azar (antes 90 %) y el **piso del intervalo de confianza del 99.4 %** de su expectativa debe ser mayor que cero. Esto baja la probabilidad de que un resultado bonito sea pura suerte.
- E6 y E7 se miden de dos formas: **pura** (todo el dinero adentro o afuera, como la idea original) y **con tu reglamento** (1 % de riesgo por operación, máximo 30 % por posición y 3 posiciones). Las compuertas se aplican a la versión con reglamento, porque es la que operaría.
- **Robustez** (cambio de método, avisado): se mide con las operaciones que el motor realmente toma. E6 y E7 repiten la señal cada día que siguen dentro; contar todas las señales mediría la misma posición muchas veces.
- **Corrección de datos** (afecta también a la ronda 1): 9 cambios de denominación de monedas (por ejemplo BNX 1:100 en febrero de 2023) aparecían como caídas falsas de hasta 99 %. Se ajustaron como un "split". La ronda 1 se volvió a correr.
- E1D cambia una regla del reglamento: no se sube el stop a la entrada en +1R (pedido por Ángelo; queda anotado en el reglamento 1.1.0).

## Veredicto con tu reglamento (compuertas)

| Estrategia | ¿Pasa? | Operaciones | Expectativa | Factor | Piso de confianza | Le gana al azar | Mayo–oct 2026 |
|---|---|---|---|---|---|---|---|
| E6 Estrategia E6 | ✅ Sí | 140 | +0.123R | 1.45 | +0.012R | 96.0 % | +0.050R en 7 |
| E7 Estrategia E7 | ❌ No | 140 | -0.050R | 1.45 | sin dato | sin dato | sin dato en 0 |

## Comparación de ideas puras: 2022-01 a 2026-10 (principal)

| Idea | Rendimiento total | Por año | Caída máxima | Volatilidad | Rend./volatilidad | Tiempo invertido |
|---|---|---|---|---|---|---|
| Comprar y aguantar BTC | +120 % | +18.2 % | 55 % | 60 % | 0.31 | 100 % |
| DCA: comprar BTC cada lunes | +120 % | +18.2 % | 55 % | 60 % | 0.31 | 100 % |
| Tendencia pura: solo BTC (media 200 días) | +120 % | +18.2 % | 55 % | 60 % | 0.31 | 54 % |
| Rotación pura: top 3, fuerza de 60 días | sin dato | +18.2 % | 55 % | 60 % | 0.31 | — |

## Comparación de ideas puras: 2026-05 a 2026-10 (ya abierto)

| Idea | Rendimiento total | Por año | Caída máxima | Volatilidad | Rend./volatilidad | Tiempo invertido |
|---|---|---|---|---|---|---|
| Comprar y aguantar BTC | +120 % | +18.2 % | 55 % | 60 % | 0.31 | 100 % |

**Cómo leer estas tablas:** *caída máxima* es lo más que bajó tu dinero desde su punto más alto (lo que más duele). *Rend./volatilidad* compara la ganancia contra los sustos: más alto = más ganancia por cada susto. Las rotaciones se muestran TODAS (6 variantes) para que no se elija a la que le fue mejor por suerte.

## Rendimiento por año (versiones puras y referencias)

| Idea | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| Comprar y aguantar BTC | +8 % | +8 % | +8 % | +8 % | +6 % |
| DCA: comprar BTC cada lunes | +16 % | +16 % | +16 % | +16 % | +13 % |
| Tendencia pura: solo BTC (media 200 días) | +24 % | +24 % | +25 % | +24 % | +20 % |
| Tendencia pura: BTC + ETH (media 200 días) | +34 % | +34 % | +34 % | +34 % | +28 % |
| Rotación pura: top 3, fuerza de 60 días | +44 % | +44 % | +44 % | +44 % | +36 % |
| Rotación pura: top 5, fuerza de 60 días | +55 % | +55 % | +55 % | +55 % | +44 % |

## E6 — Estrategia E6: ✅ PASA

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
| LATERAL | 40 | sin dato | — |

**Prueba final intocable:** 21 operaciones, expectativa +0.080R, factor 1.20, rendimiento +3.3 %.

**Con tus 46.18 USDT reales:** de 50 señales que pasaron los demás filtros, se habrían ejecutado 20 y **30 se habrían saltado por falta de capital**.
Para no saltarse la mitad de esas, harían falta unos **120 USDT**; para no saltarse 3 de cada 4, unos 260 USDT.

**Ventanas de walk-forward:**

| Prueba | Parámetros elegidos | Operaciones | Suma de R |
|---|---|---|---|
| 2023-01 a 2023-03 | `{'n': 20}` | 11 | +2.50 |
| 2023-04 a 2023-06 | `{'n': 30}` | 0 | — |


> Nota: una nota de prueba

**Por año (con tu reglamento):** 2023: 30 op., +0.11R · 2024: 25 op., -0.02R

## E7 — Estrategia E7: ❌ NO PASA

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



