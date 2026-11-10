# Avance de Sobreviviente Pro

## Decisiones de Ángelo (10 nov 2026)
- Riesgo: **1 % por operación**, topes **3 % diario / 6 % semanal / 15 % desde el pico**.
- Memes (E4): pueden ir a dinero real **solo si pasan todas las compuertas**.
- Bots: **fusionar a 6** (Boss, Noticias+Explorador, Guardián, Ejecutor, Contador y Supervisor de mercados).
- Conector de Binance: soporta **LIMIT, STOP y OCO** en Spot y **STOP_MARKET** en Futuros.

## Internet
- Funciona: datos de Spot por el respaldo oficial (`data-api.binance.vision`) e históricos (`data.binance.vision`), incluidas monedas deslistadas.
- Bloqueado desde esta nube: `api.binance.com` y `fapi.binance.com` (Binance responde "ubicación restringida"). El motor cambia solo al respaldo. Para Futuros en el backtest se usan los históricos oficiales.

## Fase 1 — terminada
- Estructura del repo, `reglamento.yaml` comentado línea por línea.
- Validador del reglamento: si las reglas chocan, el motor no corre y explica qué ajustar.
- Motor de riesgo (`sobreviviente/riesgo.py`): tamaño por % de riesgo, mínimos de Binance (compra y venta en el stop), "saltada por capital" con el capital que habría hecho falta, calor, exposición, cubeta de memes, margen y liquidación en Futuros, topes diario/semanal/caída, rachas, eventos, vetos, costos, stops solo a favor, +1R a entrada, apagado automático.
- 73 pruebas pasando; riesgo, reglamento y reglas del exchange con 100 % de cobertura.

## Fase 2 — terminada
- Descarga oficial de Binance con respaldo automático; caché local; revisión de calidad (huecos, datos viejos, precios absurdos).
- 700 pares USDT revisados; 456 estuvieron en el universo alguna vez desde 2022 (111 ya deslistados, incluidos para reducir el sesgo de supervivencia). 176 perpetuos de Futuros con funding.
- Universo día por día sin ver el futuro; régimen de BTC (EMA 200 + pendiente) y volatilidad (percentil del ATR, 90 días).

## Fase 3 — terminada
- Estrategias E1 a E5 como funciones puras (máximo 4 parámetros cada una).
- Gestión de posición idéntica en backtest y vivo (stop, +1R a entrada, stop dinámico, salida por media o por tiempo).
- Backtester en dos pasos: simulación de cada operación con costos reales y luego el motor de riesgo real decidiendo.
- Pruebas: no adelanto de información (5 estrategias), determinismo, casos calculados a mano (stop, hueco, deslizamiento, corto con funding).

## Fase 4 — terminada (ALTO: esperando a Ángelo)
- Validación completa: walk-forward (14 ventanas), robustez ±20 %, Monte Carlo 10,000, azar 1,000, contra BTC, por régimen y prueba final intocable (mayo–octubre 2026).
- **Resultado: ninguna estrategia pasó.** Todas quedan APAGADAS. Detalle en `VALIDACION.md`.
- Ronda de ajustes usada: 1 de 3 por estrategia.

## Ronda 2 de estrategias (pedida por Ángelo) — terminada
- Nuevas: **E1D** (E1 diaria, sin stop a la entrada en +1R, stop dinámico amplio), **E6** (tendencia larga BTC/ETH con media de 200 días), **E7** (rotación semanal por momentum, top 3 de las 20 más líquidas, filtro de BTC). Referencias: comprar y aguantar, 50/50 BTC-ETH y DCA semanal en BTC.
- Reglas más estrictas por probar 8 ideas: ganarle al 98.75 % del azar y piso del intervalo de confianza del 99.4 % > 0. Mayo–octubre 2026 pasó a ser una ventana más (ya se había abierto). Noviembre 2026 en adelante = papel.
- Corrección de datos: 9 cambios de denominación (p. ej. BNX 1:100) aparecían como caídas falsas; se ajustaron. La ronda 1 se volvió a correr: mismos resultados (ninguna pasa).
- Resultado: **ninguna pasa todas las compuertas.** E6 es la más cercana: pasa ventaja, azar (100 %), confianza, robustez y Monte Carlo, pero solo tiene 21 operaciones (mínimo 100) y 38 % de ventanas positivas (67 % contando solo las ventanas en que operó). Detalle en `VALIDACION_RONDA2.md`.
- Rondas de ajuste usadas: E1 → 2 de 3 (E1D); E6 → 1 de 3; E7 → 1 de 3.

## v2 "MAREA" (10 nov 2026) — rama `codex/marea-v2`
Decisiones de Ángelo en esta ronda: contra el azar se pide **90 %** (como dice la especificación); la **Cartera B queda con 2 posiciones** como máximo (si no, el peor día pasaba su tope diario).

### Fase A — terminada
- Auditoría A1–A9 sobre E1 de la v1 (`sobreviviente/auditoria.py`): Monte Carlo en bloques por fecha, curva diaria a valor de mercado (también para los topes y el tamaño), prueba de salidas, solo "grandes", cupo, comisiones.
- Velas diarias, marea diaria de BTC (media de 200 días), gestión por estrategia (`mover_a_entrada`), modos `canal` y `ranking`.
- Referencias R0, R1, R2. Fuera de muestra (2023-01 a 2026-04): R0 +358 % (caída 50 %), **R1 +188 % (caída 32 %, Calmar 1.17)**, R2 +5 % (caída 60 %).
- Reglamento 2.0.0 (ver `CAMBIOS.md`).

### Fase B — terminada
- M1 MAREA y M2 RANKING con validación completa (walk-forward, azar calendario, remuestreo en bloques, robustez, carteras A y B, capital real).
- **Resultado: ninguno pasa.** M1 +0.063R por operación, le gana solo al 26 % de los calendarios al azar, Calmar −0.02. M2 −0.083R, 8 % del azar.
- Por la regla de la v2, **M0 (= R1) pasa a PAPEL** como línea base. M0 tampoco pasa las compuertas históricas para dinero real (azar 66 %).
- Ronda de ajustes usada: **0 de 1** (no se usó: ningún ajuste razonable acercaba a M1 o M2 a la compuerta contra R1).
- Errores míos encontrados y corregidos antes del informe: M2 solo estaba probando L=21 (caché) y la prueba de comisiones mezclaba fechas.

### Fase C — terminada
- Ruta de datos de top traders verificada (desde 2020-09 para BTC) y significado de cada columna comprobado contra la API de Binance.
- Estudio de eventos (135 monedas grandes con perpetuo, 10 pruebas): **H2 (contra la bola) a 3 días pasa** (−0.63 puntos en 3 días, intervalo [−1.18, −0.12], 100 % de los años). H1 (seguir a los top) no pasa en ninguna versión.
- Paso 2, M1 y M2 con y sin veto H2: ninguno pasa. M1 empeora (+0.063R → +0.002R) y M2 mejora poco (−0.083R → −0.070R). **El veto queda apagado** (no hay motor encendido al que aplicarlo). El bot ESTELA sigue guardando la foto diaria.

### Fase D — terminada
- Modo papel (`ronda --modo papel`, `--verificar`, `registrar-llenado --ensayo`, `conciliar`, `reporte diario|semanal`, `estado [--bots]`, `estela --foto`, `doctor`).
- Archivos de bots con esquema validado; si vienen mal, modo seguro. Ronda repetible (mismos boletos el mismo día).
- `bots/` (The Boss + 5), `bots/MIGRACION.md`, `INSTALACION.md`.
- Primera ronda real en papel: 9 nov 2026. Marea alta, pero con 46.18 USDT y volatilidad ALTA (riesgo a la mitad) la compra de BTC no llega al mínimo de Binance en ninguna cartera: se anota como "saltada por capital".

### ALTO — esperando a Ángelo
- Pruebas: todas pasan. Falta subir la rama a GitHub (necesita que Ángelo inicie sesión una vez).
