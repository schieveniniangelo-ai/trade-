# HIPÓTESIS — ideas registradas antes de probarlas

## Reglas (no se negocian)
1. **Se registra antes de probar.** Una idea entra aquí, con sus campos llenos, ANTES de correr cualquier prueba. Lo
   que se pruebe sin registro no cuenta.
2. **Una variable a la vez.** Cada hipótesis cambia UNA sola cosa. Si hacen falta dos cambios, son dos hipótesis.
3. **Nunca se cambia `reglamento.yaml` por una hipótesis sin decisión de Ángelo en la ventana del domingo.** Un buen
   resultado no aplica nada por sí solo.
4. **Con menos de 30 operaciones el resultado es preliminar.** Se anota, pero no alcanza para decidir.

THE BOSS puede proponer hipótesis nuevas en su reporte semanal con este mismo formato, pero nunca las aplica ni edita
este archivo. Nada de lo que se anote aquí promete ganancias.

## Plantilla (copiar una por idea)

```
### Hipótesis NNN — <título corto>
- **Número:** NNN (el que sigue; lo pone quien la registra en este archivo)
- **Fecha de registro:** AAAA-MM-DD (antes de probar)
- **Qué se cambia (UNA sola cosa):**
- **Por qué:**
- **Qué se espera (con número):** por ejemplo, «la expectativa fuera de muestra pasa de A R a B R o más»
- **Cómo y con qué datos nuevos se prueba:** datos que NO se usaron para tener la idea (por ejemplo, el papel desde la fecha de registro)
- **Mínimo de operaciones o días:** (con menos de 30 operaciones, el resultado es preliminar)
- **Resultado:** (se llena al terminar, con cifras)
- **Decisión de Ángelo:** (solo Ángelo, en la ventana del domingo: aplicar, descartar o seguir midiendo)
```

## Registradas

Las dos primeras pasaron tal cual desde `PROPUESTAS.md` (sección H4, 11 de noviembre de 2026). Eran las mejoras de
señal pendientes. Están en **borrador**: les faltan campos que nadie ha definido todavía (no se inventaron), así que
no se pueden probar hasta llenarlos. E5 sigue APAGADA por decisión de Ángelo (`PROPUESTAS.md` H3.1); registrarlas no
la enciende.

### Hipótesis 001 — E5: el filtro de funding no toma en cuenta cada cuánto se cobra
- **Número:** 001
- **Fecha de registro:** 2026-11-12 (viene de `PROPUESTAS.md` H4.1, escrita el 11/11/2026). Estado: borrador.
- **Qué se cambia (UNA sola cosa):** el filtro de funding de E5. El cambio exacto falta definirlo antes de probar.
- **Por qué (texto original de H4.1, sin cambios):** **El filtro de funding de E5 compara la tasa de cada cobro sin importar cada cuánto se cobra** (1, 4 u 8 h):
   −0.05 % cada hora pesa ocho veces más que cada 8 h. Cambiarlo cambia la señal y obliga a validar otra vez.
- **Qué se espera (con número):** falta.
- **Cómo y con qué datos nuevos se prueba:** falta.
- **Mínimo de operaciones o días:** falta.
- **Resultado:** —
- **Decisión de Ángelo:** —

### Hipótesis 002 — E5: el «rebote» no es espejo exacto de E2
- **Número:** 002
- **Fecha de registro:** 2026-11-12 (viene de `PROPUESTAS.md` H4.3, escrita el 11/11/2026). Estado: borrador.
- **Qué se cambia (UNA sola cosa):** falta elegirla. El texto original trae dos diferencias (3 velas contra 5, y el
  cierre abajo de la EMA 20); por la regla 2, si se quieren probar las dos, son dos hipótesis.
- **Por qué (texto original de H4.3, sin cambios):** **El "rebote" de E5 no es espejo exacto de E2:** mira el máximo de 3 velas en vez de 5 y no pide cierre abajo de la
   EMA 20. Coincide con lo que dice su descripción, así que es diseño y no bug. Cambiarlo sería otra ronda de ajustes.
- **Qué se espera (con número):** falta.
- **Cómo y con qué datos nuevos se prueba:** falta.
- **Mínimo de operaciones o días:** falta.
- **Resultado:** —
- **Decisión de Ángelo:** —

### Hipótesis 003 — F1 v2 Futuros de dos lados en 4 h
- **Número:** 003
- **Fecha de registro:** 2026-11-17, desde el commit 299181b (rama codex/marea-v2), ANTES de cualquier resultado.
  Decisiones del 2026-11-16 (Ángelo y MECÁNICO por delegación de Ángelo). Con esta idea van **9 ideas probadas**
  (8 + 1): la exigencia contra el azar pasa a 100 − 10/9 = 98.9 %. Se sube solo en este texto; `reglamento.yaml`
  (`validacion.ronda2.ideas_probadas: 8`) NO se toca en esta tanda.
- **Qué se cambia (UNA sola cosa):** se prueba un motor NUEVO y aparte, F1 (Futuros USDⓈ-M, SOLO PAPEL), con reglas
  propias y su propio capital de papel. No cambia ninguna estrategia ni cartera existente (E5 sigue APAGADA con su
  historial; F1 no va en `estrategias:` ni en `carteras:`).
- **Por qué:** E1 (rupturas de 4 h en Spot) y E5 (cortos de 4 h) NO pasaron sus compuertas (VALIDACION.md). F1 se
  diferencia en que va en los dos lados, usa el régimen doble, opera monedas líquidas fijas y paga comisión de Futuros
  (0.05 % contra 0.10 % de Spot). Aun así puede NO pasar, y ese es un resultado válido. Nada garantiza ganancias.
  Diseño (fijo, sin rejilla):
  - Datos: velas de 4 h de Futuros USDⓈ-M; señal al cierre de cada vela y entrada en la apertura de la siguiente.
  - Régimen doble: largo solo si la marea de BTC (`regimen.marea_diaria`, cierre diario contra la media de 200 días)
    está ALCISTA y la tendencia de 4 h de la moneda (`regimen.tendencia`, EMA 200 con pendiente) está ALCISTA; corto
    solo si las dos están BAJISTA.
  - Entrada: el cierre de 4 h rompe el máximo (largo) o el mínimo (corto) de las 55 velas anteriores; solo la primera
    vela (`base.flanco`).
  - Stop: 2.5 × ATR14 de 4 h; si queda abajo de 1.5 % o arriba de 8 %, la señal se descarta.
  - Salida: chandelier de 3 × ATR que solo se mueve a favor, o la marea o la tendencia se voltean; sin meta fija y sin
    mover el stop a la entrada.
  - Parámetros (4, fijos): donchian_n 55, stop_atr 2.5, chandelier_atr 3.0, funding_extremo_pct 0.05.
  - Funding: no hay largo si los largos pagan más de +0.05 % cada 8 h ni corto si los cortos pagan más de 0.05 %
    (promedio de los últimos 3 cobros llevado a 8 h, `datos.funding_por_8h`).
  - Volatilidad EXTREMA (percentil ≥ 95 del ATR de 4 h): sin entradas. Sin mitad de riesgo con volatilidad ALTA.
  - Vetos de CENTINELA (moneda o GLOBAL) y eventos fuertes bloquean los dos lados; archivo dañado = sin entradas.
  - Liquidez: mediana de volumen de 30 días del perpetuo ≥ 100 M USDT.
  - Límites (DECISIÓN DE ÁNGELO 2026-11-16): todo papel; nada de Spot se toca; 1x por defecto y 2x como máximo; margen
    AISLADO; siempre stop; frenos diario 3 %, semanal 6 % y 15 % desde el pico; capital de papel 42.54 USDT.
  - MECÁNICO por delegación de Ángelo 2026-11-16: monedas SOLUSDT, XRPUSDT, BNBUSDT y DOGEUSDT; riesgo 1.0 %;
    hasta 2 posiciones (1 por moneda), calor máximo 2 %; margen 30 % por posición y 60 % en total; 1x si el valor cabe
    en el 30 %, si no 2x; 4 pérdidas seguidas = pausa de 24 h; estado propio datos/papel_futuros/F.json.
- **Qué se espera (con número):** que F1 pase TODAS las compuertas estrictas de `validar-futuros`: ≥ 100 operaciones
  fuera de muestra, factor de ganancia ≥ 1.3, expectativa ≥ +0.10R después de costos, ventanas positivas ≥ 60 %,
  caída p95 ≤ 25 % con 1 % de riesgo, azar ≥ 98.9 %, robustez ±20 % toda positiva, cero liquidaciones, con estrés de
  costos ≥ +0.05R, largo solo y corto solo > 0R, ninguna moneda > 50 % de la R total, sin cualquier moneda ≥ +0.05R y
  ≤ 20 % de señales que «no caben» con 42.54 USDT.
- **Cómo y con qué datos nuevos se prueba:** walk-forward 12/3 con velas de 4 h, precio de marca y funding de
  data.binance.vision desde 2021-01 (comando `validar-futuros` → `VALIDACION_FUTUROS.md`). Si pasa, el papel de
  Futuros (`futuros-papel`) desde la fecha en que Ángelo lo encienda es la prueba con datos nuevos.
- **Mínimo de operaciones o días:** 100 operaciones fuera de muestra sumando las 4 monedas; en papel, 30 operaciones
  (con menos, preliminar).
- **Resultado:** (se llena con el resultado de `validar-futuros`, tal cual)
- **Decisión de Ángelo:** —
