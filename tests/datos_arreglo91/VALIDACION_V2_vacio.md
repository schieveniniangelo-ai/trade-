# VALIDACIÓN V2 — "MAREA"

Generado el 11/11/2026 18:30 · reglamento 2.0.1 · datos del 01/01/2022 al 31/10/2026.

## Resumen en una frase

**Ningún motor nuevo pasó todas las compuertas ni le ganó a la referencia R1 (BTC con filtro de marea).** Por la regla de la v2, **R1 pasa a ser la candidata (M0) y es la que corre en PAPEL** como línea base. Todo lo demás queda APAGADO. Nunca se promete ganancia.

| Motor | ¿Pasa? | Operaciones fuera de muestra | Expectativa (R) | Factor de ganancia | Calmar fuera de muestra | Le gana al azar (calendario) | Caída p95 (bloques) | Prueba final (ya abierta) |
|---|---|---|---|---|---|---|---|---|
| M1 | — | sin resultado | | | | | | |
| M2 | — | sin resultado | | | | | | |

**Cómo leer esta tabla:**
- *Expectativa (R)*: lo que deja en promedio cada operación, en unidades de riesgo, ya con costos. +0.10R = si arriesgas 1 peso, te quedan 10 centavos.
- *Factor de ganancia*: lo ganado entre lo perdido. Se pide 1.3 o más.
- *Calmar*: rendimiento por año ÷ la peor caída. Más alto = más ganancia por cada susto. **R1 hizo — fuera de muestra: hay que ganarle.**
- *Le gana al azar (calendario)*: a cuántos de 1,000 calendarios al azar (mismas monedas, mismo número de entradas, mismo tiempo invertido, otras fechas) supera. Se pide 90 %.
- *Caída p95 (bloques)*: en el peor 5 % de 10,000 simulaciones que respetan que las pérdidas llegan juntas, cuánto caería el capital. Máximo 25 %.
- *Prueba final*: mayo–octubre 2026. **Ya se abrió en la v1**, así que se reporta pero no decide: la prueba limpia es el papel desde hoy.

## Auditoría A1–A9 (lo que le faltaba a la v1)

_La auditoría no se corrió._

## Referencias obligatorias (lo simple contra lo que todo compite)

Señal al cierre diario (00:00 UTC), ejecución en la apertura siguiente, comisión 0.10 % + deslizamiento 0.05 % por lado.

| Referencia | Periodo | Rendimiento | Por año | Caída máxima | Calmar | Tiempo invertido | Operaciones |
|---|---|---|---|---|---|---|---|

## M3 — ESTELA (copy trade medido)

_El estudio de ESTELA no se corrió._

## Cuántas cosas se probaron (para que no haya trampa)

- Motores: M1 0 combinaciones, M2 0 combinaciones (rejillas pre-registradas, 1 ronda de ajustes): 0 en total.
- Referencias: 3 (R0, R1, R2). M0 = R1, sin parámetros que ajustar.
- ESTELA: 0 pruebas (2 hipótesis × rejilla × 2 horizontes).
- Auditoría: 4 variantes de salida y 3 comisiones sobre E1 (solo para entender la v1; nada de eso se usa para elegir).
- Todas aparecen en este informe, no solo la mejor.

## Lo que estas pruebas NO pueden garantizar

- El pasado no garantiza el futuro. La prueba realmente limpia es el **papel desde hoy**.
- Mayo–octubre 2026 ya se había visto en la v1: sus números se reportan, pero ya no son una prueba a ciegas.
- Con 46.18 USDT muchas señales se saltan por los mínimos de Binance; los resultados con capital de prueba son para medir la idea, no la cuenta.
- El universo "grandes" usa la lista de memes de hoy para excluirlas (algo de sesgo). Las monedas que Binance borró por completo de su API no se pudieron incluir.
- Desde junio–julio 2026 Binance lista **acciones tokenizadas** con mucho volumen (por ejemplo SNDKB, SOXLB —un fondo apalancado 3x— y SPCXB). El filtro de universo no las reconoce, así que pudieron entrar a "grandes" en los últimos meses del periodo. El 9 nov 2026 tres de las 15 grandes eran de este tipo.
- Las reglas de Binance (mínimos y decimales) usadas son las actuales; en el pasado algunas eran distintas.
