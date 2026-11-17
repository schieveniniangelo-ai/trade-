# VALIDACIÓN DE FUTUROS F1-LC (variante de F1 v2) — SOLO PAPEL

**Veredicto: F1-LC NO PASA.** Se queda con `activo: false`: activar cualquier variante es DECISIÓN DE ÁNGELO y exige escalones verificados y el Arreglo 152.

Fecha: 2026-11-17. Commit: 3b36f23. Hipótesis 004 (HIPOTESIS.md), registrada antes de medir: lados «largo+corto_fuerte», salida por tiempo apagada; todo lo demás igual a F1 v2. Barras por 4 pruebas en la familia F1 (12 ideas): azar ≥ 99.17 % y t ≥ 2.2414. Mismas ventanas walk-forward (12/3) y mismas monedas que F1, datos de data.binance.vision desde 2021-01-01. Nada de esto promete ganancias.

## Compuertas (si falla una, NO PASA)

| Compuerta | ¿Pasa? | Detalle |
|---|---|---|
| operaciones | ✅ | 110 operaciones fuera de muestra, sumando las 4 monedas (mínimo 100) |
| factor_ganancia | ❌ | factor de ganancia 1.02 (mínimo 1.3) |
| expectativa | ❌ | expectativa +0.008R después de costos (mínimo +0.10R) |
| ventanas | ❌ | 31 % de ventanas positivas (mínimo 60 %) |
| caida_p95 | ❌ | caída p95 30.1 % con 1 % de riesgo, la peor entre Monte Carlo suelto y por bloques (máximo 25 %) |
| azar | ❌ | le gana al 73.9 % de las entradas al azar (mínimo 99.2 %) |
| robustez | ❌ | robustez ±20 %: peor expectativa -0.020R (todas deben ser > 0) |
| liquidaciones | ✅ | 0 liquidaciones (deben ser CERO) |
| estres | ❌ | con estrés de costos (comisión 0.075 %, deslizamiento ×2, funding ×2): -0.030R (mínimo +0.05R) |
| largo_y_corto | ❌ | largo solo +0.114R (86 ops) y corto solo -0.370R (24 ops); los dos > 0R |
| concentracion | ❌ | la moneda que más aporta da 665 % de la R total (máximo 50 %; sin R total positiva no se puede repartir) |
| sin_una_moneda | ❌ | quitando cualquier moneda, la peor expectativa es -0.142R (mínimo +0.05R) |
| no_caben | ✅ | con 42.54 USDT, 5 de 107 señales «no caben» (4.7 %; máximo 20 %) |
| significancia | ❌ | t de la expectativa 0.06 (mínimo 2.24; Bonferroni α = 0.05/4) |
| escalones | ❌ | escalones sin verificar: SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT (TAREA DE ÁNGELO: copiarlos de Leverage & Margin) |

## Fuera de muestra (sumando las 4 monedas)

- Operaciones: 110; ganadoras 35 %; expectativa +0.008R; factor de ganancia 1.02; peor racha 10 pérdidas.
- Monte Carlo suelto: caída p95 25.1 %; por bloques: 30.1 % (1 % de riesgo).
- Azar: le gana al 73.9 % (pool de 3000 entradas al azar).
- Estrés de costos: expectativa -0.030R.
- t de la expectativa: 0.06.

| Lado | Ops | Expectativa | Factor |
|---|---|---|---|
| LARGO | 86 | +0.114R | 1.27 |
| CORTO | 24 | -0.370R | 0.43 |

| Moneda | Ops | Expectativa | R total | Parte | Sin ella |
|---|---|---|---|---|---|
| SOLUSDT | 35 | +0.169R | +5.92 | 665 % | -0.142R |
| XRPUSDT | 22 | -0.120R | -2.65 | -298 % | +0.043R |
| BNBUSDT | 29 | +0.035R | +1.03 | 116 % | -0.019R |
| DOGEUSDT | 24 | -0.142R | -3.41 | -383 % | +0.051R |

## Ventanas de prueba

| Prueba | Ops entrenamiento | Ops prueba | R total | Expectativa |
|---|---|---|---|---|
| 2023-01→2023-04 | 30 | 7 | -3.26 | -0.466 |
| 2023-04→2023-07 | 35 | 3 | -1.26 | -0.420 |
| 2023-07→2023-10 | 25 | 1 | -1.03 | -1.027 |
| 2023-10→2024-01 | 20 | 8 | +13.33 | +1.666 |
| 2024-01→2024-04 | 19 (pocas) | 8 | +2.67 | +0.333 |
| 2024-04→2024-07 | 20 | 3 | -0.34 | -0.113 |
| 2024-07→2024-10 | 20 | 7 | -4.46 | -0.637 |
| 2024-10→2025-01 | 26 | 9 | -1.91 | -0.212 |
| 2025-01→2025-04 | 27 | 5 | +1.29 | +0.258 |
| 2025-04→2025-07 | 24 | 8 | -4.40 | -0.551 |
| 2025-07→2025-10 | 29 | 14 | +8.55 | +0.611 |
| 2025-10→2026-01 | 36 | 10 | -3.59 | -0.359 |
| 2026-01→2026-04 | 37 | 10 | -5.18 | -0.518 |
| 2026-04→2026-07 | 42 | 5 | +2.82 | +0.564 |
| 2026-07→2026-10 | 39 | 11 | -1.73 | -0.157 |
| 2026-10→2026-11 | 36 | 1 | -0.60 | -0.599 |

## Robustez ±20 % (donchian_n × stop_atr)

| donchian \ stop | -20 % | -10 % | +0 % | +10 % | +20 % |
|---|---|---|---|---|---|
| -20 % | +0.022 | +0.046 | +0.000 | -0.019 | -0.003 |
| -10 % | +0.036 | +0.059 | +0.013 | -0.017 | +0.005 |
| +0 % | +0.035 | +0.057 | +0.008 | -0.020 | +0.002 |
| +10 % | +0.024 | +0.049 | +0.024 | +0.000 | +0.022 |
| +20 % | +0.024 | +0.051 | +0.027 | -0.007 | +0.015 |

## Cartera F con 42.54 USDT (mínimos y pasos reales)

- Operaciones tomadas: 102; capital final 42.38 USDT; caída máxima 10.4 %; veces que se habría detenido todo (−15 %): 0; liquidaciones: 0.
- Señales que «no caben»: 5 de 107 (4.7 %).

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
