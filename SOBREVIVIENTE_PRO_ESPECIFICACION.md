# SOBREVIVIENTE PRO — Especificación para Claude Code

Versión 1.0 · 9 de noviembre de 2026 · Dueño del proyecto: Ángelo (Celaya, México, zona horaria America/Mexico_City)

> Copia de la especificación original entregada por Ángelo. Las decisiones que tomó Ángelo
> en los puntos [DECIDE ÁNGELO] están en `AVANCE.md` y `CAMBIOS.md`.

---

## 0. Cómo usar este documento

Eres el ingeniero principal de este proyecto. Vas a construir un **motor de trading en Python** que va a correr en la computadora en la nube de **Grok Bot** (xAI), donde Ángelo ya tiene un equipo de bots operando en Binance.

Reglas de trabajo:

1. **Trabaja por fases** (sección 17). Al terminar cada fase, escribe un resumen corto en `AVANCE.md` y sigue con la siguiente. Solo detente a preguntarle a Ángelo en los puntos marcados **[DECIDE ÁNGELO]**, y al terminar la Fase 4 (resultados de validación).
2. **Ángelo no es programador.** Todo lo que él lea (README, reportes, mensajes, instrucciones de bots) va en **español mexicano sencillo**, sin tecnicismos o explicándolos. Los nombres de variables y funciones pueden ir en inglés o español, pero los comentarios y docstrings van en español.
3. **Honestidad total.** Nunca inventes resultados, nunca redondees a favor y nunca digas que algo funciona sin haberlo corrido. Si una estrategia no pasa la validación, se dice claro y se queda apagada. Si ninguna pasa, eso también es un resultado válido y valioso.
4. **Verifica, no supongas.** Las reglas de Binance (mínimos, decimales, comisiones) cambian: léelas de la API oficial en cada ejecución, no las escribas fijas en el código.
5. Si no tienes acceso a internet para descargar datos de Binance, dile a Ángelo de inmediato.

---

## 1. Contexto: lo que ya existe

**El equipo actual en Grok Bot** (cada uno es un bot de IA con instrucciones en texto):

| Bot | Qué hace hoy |
|---|---|
| The Boss | Coordina, audita a los demás y le pide decisiones a Ángelo. |
| Explorador | Busca monedas cada ronda con filtros (par USDT, volumen > 10 M USDT en 24 h, sin etiqueta de Monitoreo, sin aviso de deslistado, sin stablecoins, ≥ 30 días listada). Normales al Analista, memes al Surfista. |
| Noticias Crypto | Revisa noticias y X. Pone cada moneda en VERDE, AMARILLO o ROJO. Lleva el calendario de eventos (Fed, inflación, empleo de EE.UU., Casa Blanca). |
| Analista | Califica las monedas normales y propone operaciones (EMA 50/200, RSI, etc.). |
| Guardián de Riesgo | Aprueba o rechaza cada orden. |
| Ejecutor | Pone las órdenes de Spot en Binance (hoy: órdenes de 6 USDT, máximo 3 abiertas). |
| Francotirador | Futuros USDⓈ-M, largo o corto, margen aislado, máximo 2x, una posición, pérdida máxima 1 USDT por operación. |
| Surfista | Solo meme coins en Spot, por moda con volumen real. Órdenes de máximo 2.5 USDT, stop −15 %, vende a las 24 h si no se movió, pausa de 24 h tras 2 pérdidas seguidas. |
| Contador | Lleva las cuentas, métricas, PAUSAS, el "Plan Grok" y consejos para Ángelo. |

**Dinero** (todo en la subcuenta "Agentic" de Binance): 46.18 USDT en total.
- Spot: 36.18 USDT (Ejecutor 31.18 + Surfista 5).
- Futuros USDⓈ-M: 10 USDT (Francotirador).

**Cómo opera hoy:** rondas cada 90 minutos, en cadena (Explorador → Noticias → Analista → Francotirador/Ejecutor/Surfista proponen → Guardián aprueba → Contador anota → Boss audita). Tope de pérdida diario de 3.5 USD para todo el equipo. Grok Bot tiene un **conector personalizado de Binance** con el que los bots consultan saldos y ponen órdenes. **Todos los bots comparten la misma computadora y los mismos archivos.**

**Costo fijo:** Ángelo paga 300 pesos al mes por Grok Bot.

**Además existe** una estrategia previa de Freqtrade llamada "Sobreviviente" (filtro de régimen de BTC, entradas por retroceso y ruptura, stop dinámico con ATR, frenos automáticos). Puedes usar sus ideas como referencia.

---

## 2. El problema y el objetivo: cada debilidad se vuelve ventaja

| Debilidad de hoy | Cómo se vuelve ventaja en Sobreviviente Pro |
|---|---|
| **Los bots de IA deciden las operaciones** y a veces responden distinto ante los mismos datos. | **Todas las decisiones de dinero las toma código determinista**: mismo dato, misma decisión, siempre. Cada decisión queda registrada con su razón. La IA se usa solo para lo que hace bien: contexto, noticias, auditoría y explicar. |
| **No se puede probar con datos del pasado.** | **Backtesting serio**: años de datos, comisiones reales, validación fuera de muestra, Monte Carlo y comparación contra entradas al azar. Ninguna estrategia toca dinero real sin evidencia. |
| **La estrategia no tiene nada único** (todos usan medias y RSI). | **La ventaja está en el proceso, no en un indicador secreto**: estrategias simples y robustas, validadas por separado, activadas según el régimen del mercado, con tamaño ajustado por volatilidad y apagado automático cuando dejan de funcionar. Lo simple se sobreajusta menos. |
| **Muchos bots, muchas reglas y muchos choques** (en un solo día hubo ~5 conflictos de reglas). | **Una sola fuente de verdad: `reglamento.yaml`.** El código valida al arrancar que las reglas no se contradigan; si chocan, no opera y explica por qué. Las instrucciones de los bots se generan del mismo reglamento. Los cambios tienen versión y bitácora. |
| **Montos fijos al aire** (6 USDT, 2.5 USDT, 1 USDT). | **Riesgo en porcentaje del capital**: el tamaño de cada operación sale de cuánto se arriesga y de qué tan lejos está el stop. Las mismas reglas sirven con 46 USDT o con 50,000. |
| **Capital chico.** | **El capital chico es colegiatura barata y además da datos**: el sistema registra cuántas oportunidades se saltaron por falta de capital y cuánto capital habría hecho falta. Los aumentos de capital van por escalones ligados a resultados. |
| **Las comisiones se comen las cuentas chicas.** | **Costos reales en todo**: cada operación debe dejar al menos 3 veces lo que cuesta. El backtest incluye comisiones, deslizamiento y funding. |
| **Ángelo sabe poco de estadística y riesgo.** | **El sistema enseña**: cada reporte explica en una línea qué significa cada número, y hay un glosario sencillo. |
| **Cambios de reglas a cada rato.** | **Control de cambios**: las reglas solo se cambian en una ventana semanal y con datos del Contador. A mitad de semana solo se permiten cambios que reduzcan el riesgo. |
| **Los bots podrían inventar datos o equivocarse al ejecutar.** | **Boletos de ejecución exactos y conciliación**: el Ejecutor pone exactamente lo que dice el boleto, y cada ronda se compara el saldo real de Binance contra la bitácora. Si no cuadra, el sistema se pausa solo. |

---

## 3. Principios no negociables

1. **La IA puede decir NO, nunca "más".** Los bots pueden vetar operaciones, bajar el riesgo o pausar. Nunca pueden agregar operaciones, subir tamaños ni saltarse una regla.
2. **Sin evidencia no hay dinero real.** Toda estrategia empieza APAGADA o en PAPEL y solo sube de nivel si pasa las compuertas de la sección 10.4.
3. **Riesgo en porcentaje, siempre.** Nunca se infla el riesgo para alcanzar el mínimo de Binance: si no cabe, no se opera.
4. **Una sola fuente de verdad.** Todo valor configurable vive en `reglamento.yaml`.
5. **Determinismo y trazabilidad.** El mismo dato produce la misma decisión. Cada decisión, incluido cada "no opero", queda registrada con su razón y con la versión del reglamento.
6. **Costos reales.** Comisiones, deslizamiento, funding, mínimos y decimales de Binance en el backtest y en vivo.
7. **El backtest y el modo en vivo usan exactamente el mismo código** de señales y de riesgo.
8. **Seguridad.** El motor no necesita llaves de Binance: los datos de mercado son públicos y las órdenes las pone el Ejecutor con el conector de Grok Bot.
9. **Sin humo.** Ningún archivo, reporte ni mensaje promete ganancias. Los resultados se presentan con su incertidumbre.

---

## 4. Arquitectura

```
 Datos públicos de Binance ──► Universo ──► Régimen de mercado ──► Estrategias
                                                                      │
                                                         señales candidatas
                                                                      ▼
   vetos.json (Noticias) ──────────────────────────────►  Motor de riesgo
   eventos.json (calendario)                                  │
   exclusiones.json (etiquetas, deslistados)          boletos de ejecución (JSON)
                                                              │
                         Guardián (bot) verifica ◄────────────┤
                                                              ▼
                              Ejecutor (bot) pone las órdenes con el conector de Binance
                                                              │
                                                   reporte de llenados y saldos
                                                              ▼
                       Bitácora (SQLite) ──► Conciliación ──► Reportes ──► Contador / Boss / Ángelo
```

- **El motor** es un paquete de Python llamado `sobreviviente/` que se maneja desde la línea de comandos (sección 13).
- **Los bots de Grok Bot** pasan de "tomar decisiones" a **operar y supervisar el motor**, coordinándose con archivos JSON en `datos/`.
- Nueva función de cada bot (propuesta; se puede proponer fusionar bots **[DECIDE ÁNGELO]**):

| Bot | Nueva función |
|---|---|
| The Boss | Corre `ronda` cada 90 minutos, revisa el resumen, audita a los demás y le escala decisiones a Ángelo. |
| Explorador | Mantiene `exclusiones.json` y `memes.json`. Revisa que el universo tenga sentido. |
| Noticias Crypto | Mantiene `eventos.json` y `vetos.json`. Revisa cada boleto antes de ejecutar y puede vetarlo. |
| Analista | Explica en lenguaje sencillo por qué el motor propone cada operación y vigila anomalías. |
| Guardián | Corre `ronda --verificar` y confirma que cada boleto cumple el reglamento. Puede vetar; nunca puede aprobar algo que el motor rechazó. |
| Ejecutor | Único bot que toca Binance para Spot y Futuros. Pone exactamente lo que dice cada boleto y reporta llenados y saldos. |
| Francotirador | Supervisa el módulo de cortos y futuros (E5). |
| Surfista | Supervisa el módulo de memes (E4). |
| Contador | Corre `registrar-llenado`, `conciliar` y `reporte`. Lleva el Plan Grok. |

---

## 5. Datos

- Principal: `https://api.binance.com`. Respaldo solo para datos de mercado: `https://data-api.binance.vision`. Maneja errores 451 y 403 cambiando al respaldo.
- Futuros: endpoints públicos `fapi` para velas, funding y `exchangeInfo`.
- Históricos masivos: `https://data.binance.vision`. Incluye pares deslistados: úsalos para reducir el sesgo de supervivencia y documenta lo que no se pudo cubrir.
- Reglas del exchange: `exchangeInfo` (`PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE`, `NOTIONAL` / `MIN_NOTIONAL`), en caché por un día. Nunca mínimos fijos en el código.
- Calidad de datos: velas faltantes, datos viejos (más de 2 velas de atraso) y precios absurdos. Si los datos no son confiables, no se opera y se avisa.
- Archivos que mantienen los bots (esquema validado; si está mal formado, se ignora y se avisa): `exclusiones.json`, `memes.json`, `eventos.json`, `vetos.json`, `tipo_cambio.json`, `saldos.json`.

## 6. Universo

- Pares Spot contra USDT con estado TRADING; volumen mediano diario de 30 días ≥ 10 M USDT; listada hace ≥ 30 días.
- Fuera: stablecoins, tokens apalancados, pares fiat y todo lo de `exclusiones.json`.
- Sin moneda favorita. BTC entra como cualquier otra y además es el termómetro.
- Monedas nuevas entran en cuanto cumplen los filtros.
- Memes (según `memes.json`): cubeta y estrategia propia (E4). La etiqueta Semilla no las excluye; si Binance rechaza por el cuestionario de Semilla, se registra, se excluye y se avisa.
- Futuros: solo perpetuos USDⓈ-M con alto volumen que también estén en el universo de Spot.

## 7. Régimen de mercado

- Termómetro BTC (4 h): EMA 200 y su pendiente → ALCISTA, BAJISTA o LATERAL.
- Volatilidad: percentil del ATR% de 90 días → BAJA, NORMAL, ALTA o EXTREMA.
- BTC BAJISTA: ningún largo nuevo en monedas normales; cortos E5 sí; memes con riesgo a la mitad. Volatilidad ALTA (> p80): riesgo a la mitad. EXTREMA (> p95): sin entradas nuevas.
- Régimen por moneda para que tendencia opere con tendencia y rango en rango.

## 8. Estrategias

Funciones puras con velas cerradas hasta *t*. Máximo 4 parámetros. Estados: APAGADA → PAPEL → VIVA_MINI → VIVA.

| Clave | Estrategia | Idea | Dónde |
|---|---|---|---|
| E1 | Ruptura de tendencia | Donchian N en 4 h con tendencia confirmada (EMA 200 con pendiente positiva). Stop 2–3 ATR, salida Chandelier. | Spot, largos |
| E2 | Retroceso en tendencia | 4 h alcista; entrada 1 h en zona EMA 20/50 con RSI que se "resetea" y retoma. Stop bajo mínimo o ATR. Meta 2R y luego stop dinámico. | Spot, largos |
| E3 | Reversión en rango | Solo LATERAL: sobreventa extrema (RSI 2 o bajo Bollinger). Salida rápida al promedio. Riesgo reducido. | Spot, largos |
| E4 | Surfista (memes) | Volumen ≥ 3× promedio, fuerza relativa top 10 % de memes. No entra si subió > 40 % en 24 h; espera respiro. Stop −15 % o ATR (el más cercano). Salida a las 24 h. | Spot, memes |
| E5 | Francotirador (cortos) | Espejo de E1 y E2 para cortos en Futuros con BTC y moneda BAJISTA. Filtro de funding. | Futuros, aislado, ≤ 2x |

Si E4 no pasa la validación, se queda en PAPEL.

## 9. Motor de riesgo

| Regla | Valor por defecto |
|---|---|
| Riesgo por operación | 1 % (E3 y E4: 0.5 %) |
| Calor total | ≤ 3 % |
| Exposición máxima por posición Spot | 30 % |
| Cubeta de memes | ≤ 10 % |
| Futuros | Aislado, ≤ 2x, margen total ≤ 25 % |
| Posiciones | 3 normales + 2 memes + 1 futuros; una por moneda; nunca largo y corto en la misma |
| Tope diario | −3 % → PAUSA hasta el día siguiente (CDMX) |
| Tope semanal | −6 % → PAUSA hasta el lunes |
| Caída máxima desde el pico | −15 % → todo se detiene hasta OK de Ángelo |
| Rachas | 3 pérdidas seguidas → se salta una ronda. Surfista: 2 → 24 h |
| Eventos fuertes | Sin entradas ±30 min |
| Costos | Ganancia hasta la meta ≥ 3× costo ida y vuelta |
| Gestión | Nunca promediar a la baja; stops solo a favor; en +1R stop a entrada + costos |

Tamaño: `riesgo_usdt = capital × riesgo_%`; `tamaño = riesgo_usdt / distancia_al_stop` redondeado hacia abajo al `stepSize`; compra y venta en el stop deben cumplir el mínimo; si no, se salta ("saltada por capital") con el capital que habría hecho falta; si rebasa la exposición, se recorta. Capital recalculado cada ronda con saldo conciliado.

Validador del reglamento obligatorio al arrancar (riesgo × posiciones ≤ tope diario; calor ≥ riesgo por operación; mínimo de Binance alcanzable). Si algo choca, no corre y explica qué ajustar.

## 10. Validación

10.1 Ejecución en la vela siguiente; cero adelanto de información; comisiones (Spot 0.1 %, Futuros 0.02 % maker / 0.05 % taker); deslizamiento (0.05 / 0.10 / 0.30 %); stops al precio o peor, con hueco al de apertura; funding; mínimos y decimales; mismas funciones que en vivo.

10.2 ≥ 2 años de velas 1 h y 4 h, ideal desde 2022. Últimos 6 meses = prueba final intocable.

10.3 Walk-forward (12/3), robustez ±20 % con mapa de calor, Monte Carlo 10,000, contra el azar 1,000, contra comprar y aguantar BTC, por régimen.

10.4 Compuertas: APAGADA→PAPEL (código probado y backtest); PAPEL→VIVA_MINI (≥ 100 operaciones fuera de muestra, FG ≥ 1.3, expectativa ≥ +0.1R con costos, ≥ 60 % ventanas positivas, caída p95 MC ≤ 25 %, arriba del p90 del azar, pasa la prueba final; además ≥ 30 días y ≥ 30 operaciones en papel dentro de la banda 5–95 %); VIVA_MINI→VIVA (≥ 100 operaciones reales en banda + aprobación de Ángelo; escalones ×2 cada ≥ 30 días); apagado automático (caída > p95 MC o expectativa de las últimas 30 negativa → PAPEL). Máximo 3 rondas de ajustes por estrategia.

## 11. Boletos de ejecución

`salida/boletos_<fecha_hora>.json` con campos: boleto_id, version_reglamento, accion, mercado, simbolo, lado, tipo_orden, precio_entrada, stop, precio_limite_stop, meta, cantidad, valor_usdt, riesgo_usdt, riesgo_pct, apalancamiento, estrategia, razon, vence, verificaciones. El Ejecutor pone exactamente lo del boleto; si Binance rechaza, reporta el código y no improvisa. Idempotentes por boleto_id.

## 12. Bitácora, conciliación y Contador

SQLite `datos/bitacora.db` con exportación CSV; conciliación cada ronda contra `saldos.json` (diferencia > 0.10 USDT → PAUSA); métricas por estrategia, moneda y total contra la banda esperada. Plan Grok: 300 pesos al mes, ciclos de 30 días desde el 9 de noviembre de 2026, metas 10/70/300 pesos, línea diaria fija y veredicto por ciclo.

## 13. Integración con Grok Bot

Python 3.11+, dependencias mínimas (pandas, numpy, pyyaml, requests; pytest). Comandos: `verificar`, `descargar`, `validar`, `ronda` (`--papel`, `--verificar`), `registrar-llenado`, `conciliar`, `reporte diario|semanal`, `estado`. `ronda` < 60 s con ~50 monedas. Carpeta `bots/` con instrucciones por bot y `bots/MIGRACION.md`. Sin llaves de Binance.

## 14. Reportes y "modo escuela"

Resumen de ronda ≤ 8 líneas (👍 si no necesita nada). Reporte diario 8:30 p. m. CDMX y semanal domingo, cada número con "qué significa". `docs/GLOSARIO.md` con ≥ 20 términos. Gráficas PNG.

## 15. Calidad de ingeniería

Pruebas pytest (tamaño, mínimos, límites, validador, no adelanto, determinismo, caso a mano del backtester, esquema de boletos, apagados). Riesgo con cobertura ~100 %. `CAMBIOS.md` con versiones.

## 16. Entregables

README_ANGELO.md, reglamento.yaml comentado, VALIDACION.md, bots/*.md y MIGRACION.md, docs/GLOSARIO.md, AVANCE.md, CAMBIOS.md y un .zip.

## 17. Fases

F1 estructura, reglamento, validador, riesgo y pruebas · F2 datos, universo, régimen · F3 estrategias, backtester, no adelanto · F4 validación completa y VALIDACION.md (**alto para explicar a Ángelo**) · F5 ronda, boletos, coordinación, bitácora, conciliación, Plan Grok, reportes · F6 bots, migración, README, glosario, .zip.

## 18. Decisiones de Ángelo

Riesgo y topes; memes en vivo o papel; fusionar bots; tipos de orden del conector; capital y escalones.

## 19. Lo que NUNCA debe hacer este sistema

Prometer ganancias; martingala, promediar a la baja, grids sin stop, apalancamiento > 2x o margen cruzado; optimizar hasta que "se vea bonito"; pedir/guardar/usar llaves de Binance o conectarse a bancos; usar fuentes no oficiales; operar con datos viejos, incompletos o sin conciliar.
