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
