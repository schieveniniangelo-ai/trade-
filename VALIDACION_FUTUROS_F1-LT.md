# VALIDACIÓN DE FUTUROS F1-LT (variante de F1 v2) — SOLO PAPEL

**Veredicto: F1-LT NO PASA.** Se queda con `activo: false`: activar cualquier variante es DECISIÓN DE ÁNGELO y exige escalones verificados y el Arreglo 152.

Fecha: 2026-11-17. Commit: 3b36f23. Hipótesis 004 (HIPOTESIS.md), registrada antes de medir: lados «largo», salida por tiempo 30 velas sin +1R; todo lo demás igual a F1 v2. Barras por 4 pruebas en la familia F1 (12 ideas): azar ≥ 99.17 % y t ≥ 2.2414. Mismas ventanas walk-forward (12/3) y mismas monedas que F1, datos de data.binance.vision desde 2021-01-01. Nada de esto promete ganancias.

## Compuertas (si falla una, NO PASA)

| Compuerta | ¿Pasa? | Detalle |
|---|---|---|
| operaciones | ❌ | 86 operaciones fuera de muestra, sumando las 4 monedas (mínimo 100) |
| factor_ganancia | ❌ | factor de ganancia 1.29 (mínimo 1.3) |
| expectativa | ✅ | expectativa +0.123R después de costos (mínimo +0.10R) |
| ventanas | ❌ | 31 % de ventanas positivas (mínimo 60 %) |
| caida_p95 | ✅ | caída p95 18.9 % con 1 % de riesgo, la peor entre Monte Carlo suelto y por bloques (máximo 25 %) |
| azar | ❌ | le gana al 96.1 % de las entradas al azar (mínimo 99.2 %) |
| robustez | ✅ | robustez ±20 %: peor expectativa +0.085R (todas deben ser > 0) |
| liquidaciones | ✅ | 0 liquidaciones (deben ser CERO) |
| estres | ✅ | con estrés de costos (comisión 0.075 %, deslizamiento ×2, funding ×2): +0.085R (mínimo +0.05R) |
| largo | ✅ | largo +0.123R (86 ops), debe ser > 0R; sin cortos |
| concentracion | ❌ | la moneda que más aporta da 56 % de la R total (máximo 50 %; sin R total positiva no se puede repartir) |
| sin_una_moneda | ❌ | quitando cualquier moneda, la peor expectativa es +0.006R (mínimo +0.05R) |
| no_caben | ✅ | con 42.54 USDT, 5 de 85 señales «no caben» (5.9 %; máximo 20 %) |
| significancia | ❌ | t de la expectativa 0.69 (mínimo 2.24; Bonferroni α = 0.05/4) |
| escalones | ❌ | escalones sin verificar: SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT (TAREA DE ÁNGELO: copiarlos de Leverage & Margin) |

## Fuera de muestra (sumando las 4 monedas)

- Operaciones: 86; ganadoras 40 %; expectativa +0.123R; factor de ganancia 1.29; peor racha 7 pérdidas.
- Monte Carlo suelto: caída p95 17.4 %; por bloques: 18.9 % (1 % de riesgo).
- Azar: le gana al 96.1 % (pool de 3000 entradas al azar).
- Estrés de costos: expectativa +0.085R.
- t de la expectativa: 0.69.

| Lado | Ops | Expectativa | Factor |
|---|---|---|---|
| LARGO | 86 | +0.123R | 1.29 |
| CORTO | 0 | +0.000R | 0.00 |

| Moneda | Ops | Expectativa | R total | Parte | Sin ella |
|---|---|---|---|---|---|
| SOLUSDT | 31 | +0.192R | +5.95 | 56 % | +0.006R |
| XRPUSDT | 13 | +0.207R | +2.69 | 26 % | +0.096R |
| BNBUSDT | 27 | +0.108R | +2.92 | 28 % | +0.100R |
| DOGEUSDT | 15 | -0.068R | -1.02 | -10 % | +0.128R |

## Ventanas de prueba

| Prueba | Ops entrenamiento | Ops prueba | R total | Expectativa |
|---|---|---|---|---|
| 2023-01→2023-04 | 0 (pocas) | 6 | -2.21 | -0.368 |
| 2023-04→2023-07 | 6 (pocas) | 3 | -0.49 | -0.165 |
| 2023-07→2023-10 | 9 (pocas) | 1 | -1.03 | -1.027 |
| 2023-10→2024-01 | 10 (pocas) | 8 | +13.33 | +1.666 |
| 2024-01→2024-04 | 18 (pocas) | 8 | +2.67 | +0.333 |
| 2024-04→2024-07 | 20 | 3 | -0.34 | -0.113 |
| 2024-07→2024-10 | 20 | 7 | -4.46 | -0.637 |
| 2024-10→2025-01 | 26 | 9 | -1.91 | -0.212 |
| 2025-01→2025-04 | 27 | 5 | +1.29 | +0.258 |
| 2025-04→2025-07 | 24 | 8 | -4.40 | -0.551 |
| 2025-07→2025-10 | 29 | 14 | +8.55 | +0.611 |
| 2025-10→2026-01 | 36 | 3 | +1.40 | +0.468 |
| 2026-01→2026-04 | 30 | 0 | +0.00 | +0.000 |
| 2026-04→2026-07 | 25 | 0 | +0.00 | +0.000 |
| 2026-07→2026-10 | 17 (pocas) | 10 | -1.26 | -0.126 |
| 2026-10→2026-11 | 13 (pocas) | 1 | -0.60 | -0.599 |

## Robustez ±20 % (donchian_n × stop_atr)

| donchian \ stop | -20 % | -10 % | +0 % | +10 % | +20 % |
|---|---|---|---|---|---|
| -20 % | +0.136 | +0.171 | +0.115 | +0.097 | +0.106 |
| -10 % | +0.140 | +0.175 | +0.122 | +0.090 | +0.106 |
| +0 % | +0.145 | +0.179 | +0.123 | +0.093 | +0.109 |
| +10 % | +0.109 | +0.159 | +0.119 | +0.095 | +0.111 |
| +20 % | +0.111 | +0.162 | +0.123 | +0.085 | +0.102 |

## Cartera F con 42.54 USDT (mínimos y pasos reales)

- Operaciones tomadas: 80; capital final 45.90 USDT; caída máxima 9.1 %; veces que se habría detenido todo (−15 %): 0; liquidaciones: 0.
- Señales que «no caben»: 5 de 85 (5.9 %).

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
