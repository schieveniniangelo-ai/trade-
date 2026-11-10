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
