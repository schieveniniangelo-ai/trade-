# Bitácora de cambios

## Reglamento 1.0.0 — 10 nov 2026
- Primera versión. Valores por defecto de la especificación, confirmados por Ángelo (1 % / 3 % / 6 % / 15 %).
- Todas las estrategias empiezan **APAGADAS** (suben a PAPEL solo después de correr su backtest).
- Validador: la regla "riesgo por operación × posiciones máximas ≤ tope diario" se aplica como
  "lo máximo que puede perderse de golpe ≤ tope diario", donde lo máximo es el menor entre el calor total (3 %)
  y riesgo × posiciones (1 % × 6 = 6 %). Así, con los valores por defecto, el peor caso es 3 % = tope diario.
  Sin esta aclaración, los valores por defecto de la especificación chocarían entre sí.

## Reglamento 1.1.0 — 10 nov 2026
- Nuevas estrategias de la ronda 2: E1D, E6 y E7 (todas APAGADAS).
- Nueva opción por estrategia `mover_a_entrada: false` (excepción a "en +1R el stop sube a la entrada"), pedida por Ángelo para E1D, E6 y E7.
- Nueva sección `validacion.ronda2`: exigencias más estrictas por haber probado 8 ideas con los mismos datos.
- Datos: ajuste automático de cambios de denominación en el backtest (`calidad.ajustar_redenominaciones`).

## Reglamento 2.0.0 — 10 nov 2026 (v2 "MAREA")
- Temporalidad `1d` y **marea diaria de BTC** (`regimen.diario.sma_btc_dias: 200`), aparte del régimen de 4 h de la v1.
- `mover_a_entrada_en_r` pasa a ser **por estrategia** (`mover_a_entrada: false`); apagado en M0, M1 y M2.
- Modos de gestión nuevos: `canal` (salida y stop por el mínimo de n/2 días) y `ranking` (salida por la tabla o la media).
- **Una sola ronda al día**: 00:10 UTC (6:10 p. m. CDMX). Se quitó la ronda cada 90 minutos.
- Estrategias nuevas (todas empiezan APAGADAS): M0 (R1 como motor), M1 MAREA, M2 RANKING, M3 ESTELA. Rejillas pre-registradas.
- M0 lleva un stop de catástrofe de 15 % (no venía en la especificación; hace falta para que el motor de riesgo calcule el tamaño).
- E1 a E5 se quedan APAGADAS (no se borran).
- Universo "grandes" (`universo.grandes_n: 15`) y canasta de 10 para la referencia R2.
- **Dos carteras de papel** (`carteras.A` y `carteras.B`), 46.18 USDT cada una. Decisión de Ángelo (10 nov 2026):
  la Cartera B queda con **2 posiciones como máximo** para que el peor día (2 × 2 % = 4 %) quepa en su tope diario de 4 %.
- Validador: **freno total ≥ 15 × riesgo por operación**, y cada cartera se valida con todas las reglas.
- `validacion.lentos`: compuertas de motores lentos (60/40 operaciones, ventanas ≥ 40 %, azar "calendario" ≥ 90 % —
  decidido por Ángelo—, remuestreo en bloques de 20 días, prueba final que se reporta pero no decide).
- Auditoría de la v1: la cartera del backtest ahora puede medir el capital **a valor de mercado** (las abiertas cuentan),
  Monte Carlo **en bloques por fecha**, prueba de salidas, sensibilidad a la comisión y elección al azar por cupo.

## Reglamento 2.0.1 — 10 nov 2026 (arreglos del papel)
- **Cartera C de papel** (`carteras.C`, `tamano: exposicion`): M0 compra lo más grande que permite el tope de 30 %
  (≈ 13.85 USDT con 46.18; al paso de 0.00001 BTC queda en ≈ 13.50; a la mitad si la volatilidad está ALTA) y que llegue al
  mínimo de Binance. Riesgo real 4.5 % (30 % × stop de 15 %), calor 4.5 %, 1 posición, topes 4.5 % / 9 %, freno 30 %.
  Decisión de Ángelo: C queda **exenta** de "freno ≥ 15 × riesgo" porque no se dimensiona por riesgo. A y B no cambian.
- El reporte dice qué carteras operan con el capital actual y cuánto capital necesitan las que no.
- "Saltada por capital": se explica UNA vez (con el capital que haría falta) y no se repite a diario mientras siga igual.
- **Llenado realista en papel** (sección `ejecucion`): la compra LIMIT no se llena si la apertura pasa cierre × 1.003;
  si el hueco pasa el límite del STOP_LOSS_LIMIT (stop × 0.995) el stop queda "sin llenar", la posición sigue abierta y se reporta.
- Backtest: la misma regla existe como opción (`diario.generar(..., ejecucion_realista=True)`), apagada por defecto.
  **Cuánto cambia el resultado** (fuera de muestra 2023-01 a 2026-04, Cartera A; M0 también en C): **nada** en M0, M1 ni M2
  (mismas operaciones, misma expectativa, mismo rendimiento, 0 stops sin llenar). Motivo: cripto opera 24/7 y la vela diaria
  abre casi en el cierre anterior; solo 2.6 % de todas las velas diarias desde 2023 abren a más de 0.3 % (0.8 % a más de 0.5 %),
  casi todas de monedas chicas, y ninguna coincidió con una señal. VALIDACION_V2.md sigue válido.
