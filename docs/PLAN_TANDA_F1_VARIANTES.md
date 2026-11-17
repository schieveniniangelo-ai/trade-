# Plan de la tanda «F1 — variantes declaradas y arreglos pendientes, SOLO PAPEL» (arreglos 156 a 163)

Escrito el 2026-11-17, ANTES de tocar código, desde 5619f84 (1127 pruebas en Linux; cobertura del paquete 92.12 %).
Cada commit compara su diff contra este plan y explica las diferencias en su mensaje. Orden: 156 → 163. El 152 (bloque
`futuros_papel` en reglamento.yaml) NO es de esta tanda: sigue para el domingo 22 nov 2026.

Reglas de toda la tanda: SOLO PAPEL (sin llaves, sin rutas firmadas, sin órdenes, solo GET públicos; la guardia de
tests/test_arreglo143_futuros_sin_ordenes.py sin cambios). Nada de Spot: real.py, ronda_real.py, cli_real.py, papel.py,
cli_ronda.py, datos/real/, datos/papel/, bots/*_REAL.md, y reglamento.yaml completo (ni carteras/real/estrategias/riesgo
ni nada más). Límites que no cambian: 2x máximo (K5), AISLADO y ONE_WAY, siempre stop, frenos 3/6/15 %, capital de papel
42.54, riesgo 1 %, monedas SOL/XRP/BNB/DOGE. Nada pone `activo: true`. Pruebas viejas sin cambios, salvo las aserciones
de la pérdida por liquidación que el 157 cambia A PROPÓSITO (fuente oficial de Binance).

Huellas de F1 base en 5619f84 (mercado sintético de tests/test_arreglo151_validar_futuros.py, `robustez_on=False`),
para probar que F1 base no cambia: señales por moneda SOL 139 / XRP 100 / BNB 131 / DOGE 150 entradas; fuera de muestra
25 operaciones con R total 13.36894547064314; 0 liquidaciones.

## 156 — Registro de variantes y barra por pruebas múltiples
- `HIPOTESIS.md`: «Hipótesis 004 — variantes F1-L, F1-LC y F1-LT» con la tabla de la tanda tal cual, fecha 2026-11-17 y
  commit 5619f84, antes de medir nada; barras 99.17 % y t ≥ 2.24 con su referencia (Bailey y López de Prado).
- `sobreviviente/futuros/variantes.py` (nuevo): `VARIANTES` (F1, F1-L, F1-LC, F1-LT → `lados`, `tiempo_max_velas`),
  `ErrorVariante`, `variante(nombre)` (copia; desconocida → error), `PRUEBAS_FAMILIA = 4`, `ideas_totales(reg)`
  (= validacion.ronda2.ideas_probadas + 4, sin tocar el reglamento), `azar_min(reg)` (100 − 10/12), `t_min()`
  (normal inversa de 1 − 0.05/4, con `statistics.NormalDist`), y el registro solo-agregar `VARIANTES_FUTUROS.md`:
  `registrar_corrida(ruta, fila)` y `leer_registro(ruta)`. Las variantes no entran a `F1.PARAMETROS` (ni rejilla ni
  robustez).
- `VARIANTES_FUTUROS.md` (nuevo): encabezado y tabla vacía; cada corrida agrega un renglón, nunca se borra.
- Prueba `tests/test_arreglo156_variantes.py`: las 4 existen con sus dicts; desconocida → ErrorVariante; azar_min =
  99.1667 ± 0.0001; t_min = 2.2414 ± 0.0001; ideas_totales = 12; dos corridas → dos renglones y el texto viejo queda
  como prefijo; HIPOTESIS.md trae la 004 con la tabla.
- Queda idéntico: validar.py (azar_min_pct sigue con 9 para la evaluación vieja del 151), f1.py, todo lo demás.

## 157 — La liquidación no se cuenta dos veces
- `backtest.simular_operacion`, rama `precio_liq` (liquidación oficial): pérdida por unidad = min(entrada ÷
  apalancamiento, |entrada − liq| + liq × tarifa ÷ 100). `tarifa_liq_unidad` sigue reportando la tarifa nominal.
  La rama de la liquidación estimada (Arreglo 120, sin `precio_liq`) no cambia.
- `futuros/cartera.cerrar`: pérdida = min(margen, |entrada − precio| × q + precio × q × tarifa ÷ 100).
- Prueba `tests/test_arreglo157_liquidacion_sin_doble_cobro.py`: SOL 2x valor 21 → pierde exactamente 10.5 (simulación
  y cartera); un caso donde la pérdida hasta la liquidación + tarifa es menor que el margen; con precio_liq=None todo
  igual; el mercado sintético da la huella de 5619f84 (0 liquidaciones).
- Pruebas viejas que cambian A PROPÓSITO (solo el número de la pérdida): test_arreglo148 (dos aserciones de
  `pnl_unidad`) y test_arreglo149 (`cerrar` con liquidación).

## 158 — Los costos entran al riesgo en tamano.py
- `futuros/tamano.calcular(..., costos=None)`: con `costos` = {comision_pct, desliz_pct, funding_8h_pct}, distancia
  efectiva = |precio − stop| + precio × (2·comisión + 2·deslizamiento) ÷ 100 + precio × max(0, funding en contra) × 3 ÷
  100; el valor y `riesgo_usdt` usan esa distancia; el colchón de liquidación sigue con la distancia del stop. None = hoy.
- `tamano.costos_f1(reg, lado?, funding_8h_pct)` arma el dict desde reglamento.costos (0.05 y 0.05).
- `cartera.cabe(..., costos=None)` lo pasa; `cli.correr` y `validar.candidatos`/`simular_cartera` pasan siempre los
  costos (funding de la vela de la señal, `ctx.extra["funding_8h"]`).
- Prueba `tests/test_arreglo158_costos_en_el_riesgo.py`: SOL 0.11 (distancia 5.2 %, valor 8.181), XRP 20.2 = 19.285,
  riesgo con costos ≤ 0.4254 con la semilla, funding en contra suma y a favor no, None = comportamiento de hoy, y espías
  que verifican que cartera/cli/validar pasan `costos`.

## 159 — Escalones sin verificar bloquean la activación
- `futuros/liquidacion.py`: `sin_verificar(monedas)` y `todas_verificadas(monedas)`.
- `futuros/config.py`: `ErrorEscalonesSinVerificar(ErrorConfigFuturos)`; `leer(reg, exigir_escalones=True)` lo lanza si
  `activo: true` y falta verificar alguna moneda de `monedas`.
- `futuros/cli.py`: `correr` atrapa ese error, lee sin exigir y se queda en MODO MUESTRA con «escalones sin verificar:
  <monedas>» (antes de la regla de VALIDACION); `comando` no lo trata como error; `comando_validar` lee sin exigir.
- escalones.json NO cambia (verificado sigue en false). TAREA DE ÁNGELO en PROPUESTAS.md (163).
- Prueba `tests/test_arreglo159_escalones_bloquean.py`: con el json actual y activo true → muestra + aviso y leer lanza;
  con un json falso todo verificado → aviso de VALIDACION y sin aviso de escalones.

## 160 — Las variantes en la señal y en la salida
- `estrategias/f1.py`: `senales(ctx, p, variante="F1")`: "largo" apaga cortos; "largo+corto_fuerte" deja los cortos de
  F1 solo si `ctx.extra["btc_bajista_fuerte"]` (BTC cierre < SMA200 Y SMA200 < SMA200 de 20 días antes, alineado como la
  marea con `RG.a_intervalo`; la moneda BAJISTA ya la pide el corto). `armar_contexto` agrega esa serie a `extra`.
  Sin la serie, no hay cortos fuertes. F1 base: mismo código, misma salida.
- `gestion.py`: función nueva `salida_por_tiempo(est, tiempo_max_velas)` (no toca `vela`): si van N velas y el máximo a
  favor no llegó a +1R, sale en la apertura siguiente con motivo «tiempo».
- `backtest.simular_operacion(..., tiempo_max_velas=None)` y `cartera.procesar_vela(..., tiempo_max_velas=None)` la
  llaman (apagada por defecto).
- Prueba `tests/test_arreglo160_variantes_senal_salida.py`: sin cortos en F1-L; F1-LC con SMA200 subiendo no corta y
  bajando sí; cambiar datos posteriores no cambia la señal; F1-LT sale en la vela 31 si no llegó a +1R y no sale si
  llegó (simulación y cartera); F1 base = huella de 5619f84.

## 161 — validar-futuros --variante con las mismas compuertas más dos
- `futuros/validar.py`: `MercadoF1.senales(s, params, variante)`, `candidatos(..., variante)` (señales y
  tiempo_max_velas de la variante), `_oos`, `azar`, `robustez` con la variante; `evaluar(m, ..., variante=None)`:
  None = la evaluación vieja del 151 (13 compuertas, 98.9 %); con variante: azar ≥ 99.17 %, «largo» en vez de
  «largo_y_corto» en F1-L/F1-LT (el corto se sigue reportando), «significancia» (t ≥ 2.2414) y «escalones».
  Veredicto: PASA / PASA SIN ESCALONES VERIFICADOS → no se puede activar / NO PASA. `fila_registro(res)`.
- `informe` con el nombre de la variante; `futuros/cli.py`: `--variante` (por defecto F1), escribe
  VALIDACION_FUTUROS_<variante>.md (F1 también VALIDACION_FUTUROS.md, el que lee futuros-papel) y un renglón en
  VARIANTES_FUTUROS.md. Nada escribe `activo`.
- Prueba `tests/test_arreglo161_validar_variantes.py`: cada variante corre en el mercado sintético; t de 2.0 falla;
  un renglón por corrida; el veredicto nunca escribe activo (reglamento sin cambios); 15 compuertas con sus nombres.

## 162 — Holdout de monedas, sellado
- `futuros/variantes.py`: `MONEDAS_HOLDOUT` = ADAUSDT, LINKUSDT, AVAXUSDT, LTCUSDT con sus respaldos (pasos y mínimos,
  tarifa y escalones conservadores de MMR 1 %, marcados como supuesto) y `puede_holdout(registro, variante)`.
- `futuros/validar.py`: `cargar_mercado(..., monedas=None, respaldo=None)` y `evaluar_holdout(m, variante)`: mismas
  ventanas, mismas reglas y filtro de liquidez; pasa con ≥ 30 operaciones, expectativa ≥ 0R normal y ≥ 0R con estrés;
  con menos de 30 es «sin veredicto».
- `futuros/cli.py`: `--holdout` (se niega sin pase previo de las 15 compuertas sin contar escalones, y la segunda vez);
  escribe VALIDACION_FUTUROS_<variante>_holdout.md y el renglón «holdout».
- Prueba `tests/test_arreglo162_holdout_monedas.py`: se niega sin pase; se niega la segunda vez; < 30 = sin veredicto;
  los 4 nombres no aparecen en el código fuera de variantes.py.

## 163 — Textos y cifras
- `CLAUDE.md`: la regla de pruebas agrega la cifra REAL de pytest en este commit (Linux y Windows con 1 saltada) y la
  suma de la tanda 156–163 (se conservan las frases que piden test_arreglo116 y test_arreglo153).
- `PROPUESTAS.md`: «O. Tanda F1 variantes (156–163)» con commits, resumen de cada VALIDACION_FUTUROS_<variante>.md,
  4 pruebas y las barras (99.17 % y t 2.24), la TAREA DE ÁNGELO de los escalones, el 152 el domingo 22 nov, y que
  ninguna variante se activa sin DECISIÓN DE ÁNGELO.
- Prueba `tests/test_arreglo163_textos_variantes.py`: CLAUDE.md menciona la cifra de `pytest --collect-only -q`
  (contada dentro de la prueba) y la sección O trae sus frases.

## Al final
validar-futuros (F1) y una vez cada una --variante F1-L, F1-LC, F1-LT, sin repetir corridas. --holdout solo con las que
pasen las 15 compuertas sin contar escalones; si ninguna pasa, ningún holdout.
