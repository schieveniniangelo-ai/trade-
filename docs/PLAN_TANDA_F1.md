# Plan de la tanda «Motor de Futuros F1 v2 — SOLO PAPEL» (arreglos 143 a 153)

Escrito el 2026-11-17, ANTES de tocar código, desde 299181b. Cada commit compara su diff contra este plan y explica
las diferencias. Orden: 143 → 151, luego 153; el 152 espera al domingo 22 nov 2026 (ventana de cambios).

Reglas de toda la tanda: nada de Spot (real.py, ronda_real.py, cli_real.py, papel.py, cli_ronda.py, datos/real/,
datos/papel/, bots/4_EJECUTOR_REAL.md, bots/5_CONTADOR_REAL.md, los bloques carteras/real/estrategias/riesgo del
reglamento, estrategias.E5 y estrategias/e5.py). Solo GET públicos de la lista blanca. F1 no genera boletos.

## 143 — Registro, configuración y guardián «sin órdenes»
- `HIPOTESIS.md`: «Hipótesis 003 — F1 v2 Futuros de dos lados en 4 h» con el diseño y las decisiones tal cual, fecha
  2026-11-17 y commit de partida 299181b; nota de que ideas_probadas pasa a 9 solo en el texto (el reglamento no cambia).
- `sobreviviente/futuros/__init__.py`: `SOLO_PAPEL = True`.
- `sobreviviente/futuros/config.py`: `POR_DEFECTO` (las cifras de «Decisiones», activo=False), `ORIGEN` (quién decidió
  cada cifra, para el reporte), `MONEDAS_PERMITIDAS`, `ErrorConfigFuturos`, `leer(reg)` y `validar(cfg)`.
- Prueba `tests/test_arreglo143_futuros_sin_ordenes.py`: textos prohibidos (sin comentarios), importaciones cruzadas
  con real/ronda_real/cli_real/papel/cli_ronda en los dos sentidos, `SOLO_PAPEL is True`, `leer` = POR_DEFECTO con el
  reglamento actual, cada error de `leer`, y `carteras.capital_inicial` = 142.54.
- Queda idéntico: todo lo demás.

## 144 — Liquidación con la fórmula oficial
- `sobreviviente/futuros/liquidacion.py`: `escalon_de(nocional, escalones)`, `precio_liquidacion_aislado(entrada,
  cantidad, lado, apalancamiento, escalones)` con recálculo si cae en otro escalón; `cargar_escalones()`,
  `tarifa_liquidacion(simbolo, info_simbolo=None)` (exchangeInfo.liquidationFee; si no hay, la cifra del 2026-11-16).
- `sobreviviente/futuros/escalones.json`: tablas por moneda con fecha y estado de verificación.
- Prueba `tests/test_arreglo144_liquidacion_oficial.py`: la tabla BTC 1x/2x largo/corto (±1 USDT), cambio de escalón,
  `riesgo.precio_liquidacion` sin cambios.
- Queda idéntico: riesgo.py.

## 145 — Datos públicos de 4 h
- `sobreviviente/futuros/datos_publicos.py`: `RUTAS_PERMITIDAS`, `ruta_permitida(url)`, `velas_4h`, `marca_4h`,
  `funding`, `funding_8h_promedio`, `marca_y_funding` (premiumIndex), `info_funding` (fundingInfo),
  `volumen_mediano_30d` (klines 1d), `frescura(velas, ahora)` (>48 h = sin entradas), `cargar(cliente, cfg, ahora)` que
  junta todo y dice «Futuros no disponible» si la API responde 451/403.
- Prueba `tests/test_arreglo145_datos_publicos.py` con un cliente falso.
- Queda idéntico: datos.py.

## 146 — Señal F1 (función pura)
- `sobreviviente/estrategias/f1.py`: `TEMPORALIDAD = "4h"`, `PARAMETROS` (4), `POR_DEFECTO`, `senales(ctx, p)` con
  columna `lado`, `salir_largo` y `salir_corto`; `gestion(p)`. NO entra en `estrategias/__init__.ESTRATEGIAS`.
- `gestion.py`: modo nuevo `chandelier_senal` (chandelier que además sale en la apertura siguiente si la señal de salida
  lo pide). Los modos existentes no cambian.
- Prueba `tests/test_arreglo146_senal_f1.py`: sin mirar el futuro, espejo 1/p, flanco, régimen doble, funding en los
  dos lados, stop 1.5–8 %, volatilidad EXTREMA, y que F1 no está en ESTRATEGIAS ni en el reglamento.

## 147 — Tamaño por riesgo
- `sobreviviente/futuros/tamano.py`: `filtros_moneda`, `calcular(capital, riesgo_pct, precio, stop, lado, filtros,
  cfg, margen_abierto=0, escalones=None)` → `Tamano` (cabe, razón, cantidad, valor, apalancamiento, margen, riesgo real,
  liquidación).
- Prueba `tests/test_arreglo147_tamano_futuros.py`: los casos SOL/XRP/BNB/ETH/BTC, margen, tope 2x y riesgo real ≤
  pedido con valores al azar (semilla del reglamento).

## 148 — Simulación con la liquidación oficial
- `backtest.simular_operacion`: parámetros `precio_liq=None`, `tarifa_liq_pct=0.0`. Con None, nada cambia.
- Prueba `tests/test_arreglo148_liquidacion_en_simulacion.py`.

## 149 — Cartera F de papel
- `sobreviviente/futuros/cartera.py`: estado en datos/papel_futuros/F.json, `reglamento_f1` (copia con copia_con),
  `bloqueos_entrada` (frenos, vetos, eventos, archivos dañados), `cabe` (posiciones, moneda, calor, tamaño),
  `abrir`, `procesar_vela` (stop por máx/mín de 4 h, liquidación con marca, funding), `cerrar`, rachas.
- Prueba `tests/test_arreglo149_cartera_futuros.py`.

## 150 — Comando futuros-papel
- `sobreviviente/futuros/cli.py` (`registrar(sub)`, `comando`), registrado en `__main__.py` junto a futuros-capital.
- Prueba `tests/test_arreglo150_futuros_papel.py`: lista blanca, nada en datos/real, datos/papel ni salida/boletos*,
  compuertas_puerta igual antes y después, modo muestra, código 0 si falla un dato.

## 151 — validar-futuros
- `sobreviviente/futuros/validar.py`: datos de data.binance.vision, candidatos con `backtest.simular_operacion`,
  cartera con las reglas de F1, walk-forward 12/3, compuertas estrictas, `VALIDACION_FUTUROS.md`.
- Comando `validar-futuros` en `futuros/cli.py`.
- Prueba `tests/test_arreglo151_validar_futuros.py` con mercado sintético.

## 153 — Textos y cifras (antes del 152)
- PROPUESTAS.md sección «N. Tanda Futuros F1 v2 (143–153)»; CLAUDE.md (cifra nueva sin quitar la vieja, que fija
  test_arreglo116); bots/THE_BOSS.md una línea.
- Prueba `tests/test_arreglo153_textos_futuros.py`.

## 152 — reglamento (DOMINGO 22 nov 2026; no se hace en esta corrida)
