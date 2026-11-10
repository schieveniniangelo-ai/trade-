# Bitácora de cambios

## Reglamento 1.0.0 — 10 nov 2026
- Primera versión. Valores por defecto de la especificación, confirmados por Ángelo (1 % / 3 % / 6 % / 15 %).
- Todas las estrategias empiezan **APAGADAS** (suben a PAPEL solo después de correr su backtest).
- Validador: la regla "riesgo por operación × posiciones máximas ≤ tope diario" se aplica como
  "lo máximo que puede perderse de golpe ≤ tope diario", donde lo máximo es el menor entre el calor total (3 %)
  y riesgo × posiciones (1 % × 6 = 6 %). Así, con los valores por defecto, el peor caso es 3 % = tope diario.
  Sin esta aclaración, los valores por defecto de la especificación chocarían entre sí.
