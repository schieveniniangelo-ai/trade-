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
