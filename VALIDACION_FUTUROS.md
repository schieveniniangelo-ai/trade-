# VALIDACIÓN DE FUTUROS F1 (variante de F1 v2) — SOLO PAPEL

**Veredicto: F1 NO PASA.** Se queda con `activo: false`: activar cualquier variante es DECISIÓN DE ÁNGELO y exige escalones verificados y el Arreglo 152.

Fecha: 2026-11-17. Commit: 3b36f23. Hipótesis 004 (HIPOTESIS.md), registrada antes de medir: lados «ambos», salida por tiempo apagada; todo lo demás igual a F1 v2. Barras por 4 pruebas en la familia F1 (12 ideas): azar ≥ 99.17 % y t ≥ 2.2414. Mismas ventanas walk-forward (12/3) y mismas monedas que F1, datos de data.binance.vision desde 2021-01-01. Nada de esto promete ganancias.

## Compuertas (si falla una, NO PASA)

| Compuerta | ¿Pasa? | Detalle |
|---|---|---|
| operaciones | ✅ | 126 operaciones fuera de muestra, sumando las 4 monedas (mínimo 100) |
| factor_ganancia | ❌ | factor de ganancia 0.93 (mínimo 1.3) |
| expectativa | ❌ | expectativa -0.034R después de costos (mínimo +0.10R) |
| ventanas | ❌ | 31 % de ventanas positivas (mínimo 60 %) |
| caida_p95 | ❌ | caída p95 34.0 % con 1 % de riesgo, la peor entre Monte Carlo suelto y por bloques (máximo 25 %) |
| azar | ❌ | le gana al 52.4 % de las entradas al azar (mínimo 99.2 %) |
| robustez | ❌ | robustez ±20 %: peor expectativa -0.070R (todas deben ser > 0) |
| liquidaciones | ✅ | 0 liquidaciones (deben ser CERO) |
| estres | ❌ | con estrés de costos (comisión 0.075 %, deslizamiento ×2, funding ×2): -0.071R (mínimo +0.05R) |
| largo_y_corto | ❌ | largo solo +0.114R (86 ops) y corto solo -0.353R (40 ops); los dos > 0R |
| concentracion | ❌ | la moneda que más aporta da nan % de la R total (máximo 50 %; sin R total positiva no se puede repartir) |
| sin_una_moneda | ❌ | quitando cualquier moneda, la peor expectativa es -0.163R (mínimo +0.05R) |
| no_caben | ✅ | con 42.54 USDT, 9 de 123 señales «no caben» (7.3 %; máximo 20 %) |
| significancia | ❌ | t de la expectativa -0.27 (mínimo 2.24; Bonferroni α = 0.05/4) |
| escalones | ❌ | escalones sin verificar: SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT (TAREA DE ÁNGELO: copiarlos de Leverage & Margin) |

## Fuera de muestra (sumando las 4 monedas)

- Operaciones: 126; ganadoras 34 %; expectativa -0.034R; factor de ganancia 0.93; peor racha 11 pérdidas.
- Monte Carlo suelto: caída p95 28.8 %; por bloques: 34.0 % (1 % de riesgo).
- Azar: le gana al 52.4 % (pool de 3000 entradas al azar).
- Estrés de costos: expectativa -0.071R.
- t de la expectativa: -0.27.

| Lado | Ops | Expectativa | Factor |
|---|---|---|---|
| LARGO | 86 | +0.114R | 1.27 |
| CORTO | 40 | -0.353R | 0.39 |

| Moneda | Ops | Expectativa | R total | Parte | Sin ella |
|---|---|---|---|---|---|
| SOLUSDT | 37 | +0.129R | +4.76 | — % | -0.163R |
| XRPUSDT | 26 | -0.113R | -2.93 | — % | -0.006R |
| BNBUSDT | 34 | -0.020R | -0.67 | — % | -0.060R |
| DOGEUSDT | 29 | -0.190R | -5.50 | — % | +0.006R |

## Ventanas de prueba

| Prueba | Ops entrenamiento | Ops prueba | R total | Expectativa |
|---|---|---|---|---|
| 2023-01→2023-04 | 36 | 7 | -3.26 | -0.466 |
| 2023-04→2023-07 | 35 | 3 | -1.26 | -0.420 |
| 2023-07→2023-10 | 25 | 4 | -1.80 | -0.451 |
| 2023-10→2024-01 | 23 | 8 | +13.33 | +1.666 |
| 2024-01→2024-04 | 22 | 8 | +2.67 | +0.333 |
| 2024-04→2024-07 | 23 | 3 | -0.34 | -0.113 |
| 2024-07→2024-10 | 23 | 13 | -8.12 | -0.625 |
| 2024-10→2025-01 | 32 | 9 | -1.91 | -0.212 |
| 2025-01→2025-04 | 33 | 6 | +0.89 | +0.149 |
| 2025-04→2025-07 | 31 | 9 | -4.01 | -0.446 |
| 2025-07→2025-10 | 37 | 14 | +8.55 | +0.611 |
| 2025-10→2026-01 | 38 | 15 | -4.36 | -0.291 |
| 2026-01→2026-04 | 44 | 10 | -5.18 | -0.518 |
| 2026-04→2026-07 | 48 | 5 | +2.82 | +0.564 |
| 2026-07→2026-10 | 44 | 11 | -1.73 | -0.157 |
| 2026-10→2026-11 | 41 | 1 | -0.60 | -0.599 |

## Robustez ±20 % (donchian_n × stop_atr)

| donchian \ stop | -20 % | -10 % | +0 % | +10 % | +20 % |
|---|---|---|---|---|---|
| -20 % | -0.045 | -0.010 | -0.054 | -0.070 | -0.044 |
| -10 % | -0.030 | +0.005 | -0.040 | -0.064 | -0.033 |
| +0 % | -0.006 | +0.018 | -0.034 | -0.059 | -0.021 |
| +10 % | -0.016 | +0.011 | -0.021 | -0.042 | -0.002 |
| +20 % | -0.015 | +0.012 | -0.019 | -0.048 | -0.009 |

## Cartera F con 42.54 USDT (mínimos y pasos reales)

- Operaciones tomadas: 114; capital final 41.02 USDT; caída máxima 13.0 %; veces que se habría detenido todo (−15 %): 0; liquidaciones: 0.
- Señales que «no caben»: 9 de 123 (7.3 %).

## Cifras usadas (y quién las decidió)

- activo: False — DECISIÓN DE ÁNGELO 2026-11-16
- capital_papel: 42.54 — DECISIÓN DE ÁNGELO 2026-11-16
- apalancamiento_tope: 2 — DECISIÓN DE ÁNGELO 2026-11-16
- margen: AISLADO — DECISIÓN DE ÁNGELO 2026-11-16
- modo_posicion: ONE_WAY — MECÁNICO por delegación de Ángelo 2026-11-16
- monedas: ['SOLUSDT', 'XRPUSDT', 'BNBUSDT', 'DOGEUSDT'] — MECÁNICO por delegación de Ángelo 2026-11-16
- regimen_btc: BTCUSDT — MECÁNICO por delegación de Ángelo 2026-11-16
- temporalidad: 4h — MECÁNICO por delegación de Ángelo 2026-11-16
- riesgo_por_operacion_pct: 1.0 — MECÁNICO por delegación de Ángelo 2026-11-16
- calor_total_max_pct: 2.0 — MECÁNICO por delegación de Ángelo 2026-11-16
- posiciones_max: 2 — MECÁNICO por delegación de Ángelo 2026-11-16
- margen_posicion_max_pct: 30.0 — MECÁNICO por delegación de Ángelo 2026-11-16
- margen_total_max_pct: 60.0 — MECÁNICO por delegación de Ángelo 2026-11-16
- stop_min_pct: 1.5 — MECÁNICO por delegación de Ángelo 2026-11-16
- stop_max_pct: 8.0 — MECÁNICO por delegación de Ángelo 2026-11-16
- volumen_mediano_min_usdt: 100000000 — MECÁNICO por delegación de Ángelo 2026-11-16
- tope_diario_pct: 3.0 — DECISIÓN DE ÁNGELO 2026-11-16
- tope_semanal_pct: 6.0 — DECISIÓN DE ÁNGELO 2026-11-16
- caida_max_desde_pico_pct: 15.0 — DECISIÓN DE ÁNGELO 2026-11-16
- perdidas_seguidas_pausa: 4 — MECÁNICO por delegación de Ángelo 2026-11-16
- pausa_horas: 24 — MECÁNICO por delegación de Ángelo 2026-11-16
- funding_extremo_pct_8h: 0.05 — MECÁNICO por delegación de Ángelo 2026-11-16
- Parámetros de F1: {'donchian_n': 55, 'stop_atr': 2.5, 'chandelier_atr': 3.0, 'funding_extremo_pct': 0.05} — MECÁNICO por delegación de Ángelo 2026-11-16 (fijos, sin rejilla).

## Avisos

- exchangeInfo de Futuros no disponible (ErrorDatos): se usan los pasos y mínimos consultados el 2026-11-16 y la tarifa de liquidación de esa fecha.
- Tablas de escalones de liquidación: SUPUESTO CONSERVADOR (MMR 1 %) en las monedas sin verificar; ver escalones.json y PROPUESTAS.md N.
