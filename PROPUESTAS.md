# PROPUESTAS — cosas que encontré y NO cambié

Sesión larga del 10 de noviembre de 2026, rama `codex/marea-v2`. Aquí está todo lo que vi al leer el código y que no
me tocaba decidir a mí. Nada de esta lista se cambió. Los números de línea son del commit `624eaee`.

Cada punto dice: dónde está, qué pasa hoy y qué sugiero.

## A. Tocan reglas de riesgo o de dinero (decide Ángelo)

### A1. El tope diario de pérdida no hace nada con una ronda al día — ✅ RESUELTO (Arreglo 64)
- **Resuelto el 10 de noviembre de 2026, por decisión de Ángelo (commit `24de1dc`):** la pérdida del día es el capital
  de esta ronda contra el de la ronda anterior; el "día" es el día UTC de la ronda (00:10 UTC); al tocar o pasar el
  tope no se abren compras nuevas hasta las 00:00 UTC del día siguiente y lo abierto sigue con su stop; el resumen
  avisa con ⚠️ y sin 👍. Los números del tope no cambiaron. Lo de abajo describe cómo estaba ANTES del arreglo.
- **Dónde:** `sobreviviente/papel.py:504-508` y `sobreviviente/riesgo.py:412-425`.
- **Qué pasaba:** el "capital con que empezó el día" se vuelve a poner igual al capital de hoy en cada ronda, justo
  antes de revisar los topes. Como solo hay una ronda al día, la pérdida "del día" siempre sale 0 % y el tope diario
  (3 %, 4 % o 4.5 % según la cartera) nunca se activa. Además, si se activara, la pausa dura "hasta mañana" (medianoche
  de CDMX) y la siguiente ronda es a las 6:10 p. m. del día siguiente, cuando la pausa ya venció.
- **Qué sí funciona:** el tope semanal y la caída máxima desde el pico.
- **Qué sugiero:** que Ángelo decida qué quiere que signifique el tope diario con una ronda al día. Una opción: comparar
  el capital de hoy contra el de la ronda de ayer y, si cayó más que el tope, no abrir compras en la ronda de hoy.

### A2. Los eventos fuertes se comparan con la hora "oficial" de la ronda, no con la hora en que se pone la orden
- **Dónde:** `sobreviviente/papel.py:504` (la hora que se usa es siempre 00:10 UTC) y `sobreviviente/riesgo.py:563`.
- **Qué pasa hoy:** un evento de importancia ALTA bloquea compras 30 minutos antes y después. La revisión se hace con las
  6:10 p. m. exactas. Si el evento es a las 6:45 p. m., la ventana empieza 6:15 p. m.: la ronda no lo ve, pero el
  EJECUTOR pone la orden a las 6:15 p. m. o después, ya dentro de la ventana.
- **Qué sugiero:** revisar el evento contra la hora en que el EJECUTOR va a actuar (por ejemplo, hasta el vencimiento
  del boleto o al menos 6:10–7:00 p. m.).

### A3. Una venta que no se pudo hacer por falta de precio conserva el 👍
- **Dónde:** `sobreviviente/papel.py:440`.
- **Qué pasa hoy:** si toca vender en la apertura y Binance no contesta el precio, la venta se intenta mañana. Desde el
  Arreglo 51 sale con ⚠️ en el resumen, pero el resumen sigue terminando con "👍 No necesito nada de ti".
- **Qué sugiero:** que Ángelo decida si ese caso debe terminar con "Necesito tu respuesta", igual que "sin velas hoy,
  revisar a mano" (Arreglo 41).

### A4. Después de un día sin precio de apertura, el papel vende al precio de AYER
- **Dónde:** `sobreviviente/gestion.py:87-88` y el ciclo de velas pendientes de `sobreviviente/papel.py` (~línea 405).
- **Qué pasa hoy:** si ayer tocaba vender y no hubo precio, hoy el papel da por hecha la venta al precio de apertura de
  la vela de ayer (un precio de hace 24 horas), mientras que el boleto de venta se ejecuta al precio de hoy. El papel y
  la realidad quedan distintos en ese caso. Lo vi en la prueba del Arreglo 51.
- **Qué sugiero:** que en ese caso el papel use la apertura de hoy.

### A5. El aviso de "una estrategia se salta una ronda por racha de pérdidas" se pierde
- **Dónde:** `sobreviviente/papel.py:463` y `sobreviviente/riesgo.py:429-450`.
- **Qué pasa hoy:** cuando una estrategia pierde varias seguidas, el motor de riesgo arma el mensaje "perdió N seguidas:
  se salta 1 ronda", pero la ronda no lo guarda en ningún lado. Ángelo solo ve después que la señal "no entra". Además,
  esa función recibe la hora real de la computadora y no la hora de la ronda (solo afecta a una estrategia vieja, E4).
- **Qué sugiero:** guardar ese mensaje en los mensajes de la cartera y pasarle la hora de la ronda.

### A6. Un boleto de "mover stop" puede salir sin mover nada
- **Dónde:** `sobreviviente/papel.py:469-472`.
- **Qué pasa hoy:** si el stop sube menos que el paso mínimo de precio de Binance, al redondear queda igual que el
  anterior. Se genera un boleto MOVER STOP con el mismo precio, y `ronda --verificar` lo rechaza con ❌ ("el stop nuevo
  no está arriba del anterior"). Es raro, pero puede pasar.
- **Qué sugiero:** no generar el boleto cuando, ya redondeado, el stop no subió.

### A7. "Necesita unos X USDT" queda un poquito corto
- **Dónde:** `sobreviviente/riesgo.py:329`.
- **Qué pasa hoy:** el capital que "haría falta" para que una señal quepa no cuenta la comisión que Binance cobra en la
  moneda comprada (Arreglo 33). El número sale cerca de 0.1 % más bajo de lo real.
- **Qué sugiero:** sumar la comisión al cálculo. Es solo el número que se le muestra a Ángelo; no cambia compras.

### A8. Ronda fuera de hora: las ventas se anotan con la apertura aunque se ejecuten horas después
- **Dónde:** `sobreviviente/papel.py` (venta programada, ~línea 436) y `sobreviviente/cli_ronda.py:40`.
- **Qué pasa hoy:** una ronda FUERA DE HORA no compra, pero sí genera ventas programadas, y el papel las anota al precio
  de las 00:00 UTC aunque la ronda corra muchas horas después. El Arreglo 44 ya mide esa diferencia en cada boleto.
- **Qué sugiero:** revisar esa medición unas semanas y decidir si el papel debe usar otro precio cuando va tarde.

## B. No tocan riesgo, pero no los hice

### B1. La boleta semanal puede contar de más
- **Dónde:** `sobreviviente/reportes.py:110`.
- **Qué pasa hoy:** si una cartera no tuvo ninguna ronda en los últimos 7 días, la línea "en la semana" muestra toda la
  ganancia desde que empezó el papel. Y el primer día de la semana no cuenta, porque la cuenta arranca en el primer
  punto guardado de la semana. La línea de Grok Bot (`reportes.py:125`) sí cuenta 0 en ese caso: las dos líneas no
  usan la misma regla.
- **Por qué no lo cambié:** cambia un número que lee Ángelo; prefiero que lo apruebe.
- **Qué sugiero:** medir siempre contra el último capital guardado antes de la semana.

### B2. El ensayo del EJECUTOR busca los boletos en otra carpeta
- **Dónde:** `sobreviviente/cli_ronda.py:512`.
- **Qué pasa hoy:** `registrar-llenado` busca en la carpeta `salida/` del programa; `ronda` y `ronda --verificar` usan
  la carpeta que dice el reglamento. Hoy son la misma carpeta. Si un día se usa otro reglamento con otra carpeta de
  datos, el ensayo no encontraría los boletos.
- **Qué sugiero:** usar la misma carpeta en los tres.

### B3. Solo la ronda mide si un bot llegó a tiempo — ✅ RESUELTO (Arreglo 87, ver F)
- **Dónde:** `sobreviviente/archivos.py:291`.
- **Qué pasa hoy:** todas las tareas que no son la ronda se anotan como "a tiempo" sin revisar la hora. En
  `estado --bots`, RADAR, CENTINELA, EJECUTOR y CONTADOR siempre salen puntuales.
- **Qué sugiero:** darle a cada tarea su hora límite (la del horario de `bots/MIGRACION.md`) y medirla.

### B4. "actualizado" lo escribe el mismo bot
- **Dónde:** `sobreviviente/papel.py:147-180`.
- **Qué pasa hoy:** el aviso de bot dormido (Arreglo 42) detecta que CENTINELA o RADAR no pusieron la fecha. No puede
  saber si el bot puso la fecha sin haber revisado de verdad.
- **Qué sugiero:** que el bot escriba también qué fuentes revisó, o que THE BOSS lo confirme una vez por semana.

### B5. Los archivos de las carteras crecen sin límite — ✅ EN PARTE (Arreglo 88: las rondas; lo demás en F3)
- **Dónde:** `sobreviviente/papel.py:659` (guarda el resumen completo de cada ronda) y `papel.py:565` (anota cada señal
  saltada por capital; hoy eso pasa a diario en las carteras A y B).
- **Qué pasa hoy:** `cartera_A.json`, `cartera_B.json` y `cartera_C.json` crecen todos los días y se reescriben
  completos en cada ronda. También crecen `registro.jsonl`, `bitacora_rondas.jsonl` y `errores.log`.
- **Por qué no lo cambié:** recortar es mover o borrar datos, y eso no me toca.
- **Qué sugiero:** pasar las rondas de más de 90 días a un archivo aparte (sin borrar nada).

### B6. El respaldo queda, por defecto, en el mismo disco
- **Dónde:** `reglamento.yaml` (`respaldo.carpeta`) y `sobreviviente/respaldo.py:155-160`.
- **Qué pasa hoy:** la carpeta por defecto es `~/respaldos-sobreviviente`, en la misma computadora. Si el disco se daña,
  se pierden el original y el respaldo. Además, la edad del respaldo se lee del nombre del archivo: un respaldo con
  fecha futura (reloj mal puesto) apagaría el aviso.
- **Qué sugiero:** que Ángelo elija una carpeta en otro disco o sincronizada con la nube, y tratar las fechas futuras
  igual que en el Arreglo 60.

### B7. Todo depende de que el reloj de la computadora esté bien
- **Dónde:** `sobreviviente/cli_ronda.py:40` (hora de la ronda) y `sobreviviente/doctor.py:29`.
- **Qué pasa hoy:** la ronda decide qué día procesar y si va temprano o tarde con el reloj de la computadora. Nada
  revisa que ese reloj esté bien.
- **Qué sugiero:** que `doctor` compare el reloj con la hora pública de Binance y avise si difiere más de un minuto.

### B8. La boleta semanal solo compara la Cartera A con el costo de Grok Bot
- **Dónde:** `sobreviviente/reportes.py:123-128`.
- **Qué pasa hoy:** con 46.18 USDT la Cartera A no puede comprar BTC, así que esa línea casi siempre dirá +0.0 pesos.
- **Qué sugiero:** que Ángelo diga contra qué cartera quiere comparar el costo.

### B9. Pruebas que miran la carpeta real de respaldos — ✅ RESUELTO (Arreglo 85)
- **Dónde:** pruebas viejas que corren la ronda completa (por ejemplo `tests/test_arreglo6_datos_malos.py`).
- **Qué pasa hoy:** esas pruebas no cambian `respaldo.carpeta`, así que al correr leen (solo leen) la carpeta
  `~/respaldos-sobreviviente` de la computadora. No fallan por eso, porque el aviso ℹ️ no cambia nada, pero lo ideal es
  que las pruebas no dependan de la computadora.
- **Por qué no lo cambié:** es tocar pruebas que ya existen.

### B10. Cobertura que sigue baja — ✅ EN PARTE (Arreglo 86; lo que falta en F3)
- **Dónde:** `backtest.py` (50 %), `validacion.py` (29 %), `validacion_v2.py` (25 %), `estela.py` (28 %),
  `informe.py`, `informe_v2.py`, `auditoria.py`, `ejecutar_v2.py`, `ronda2.py` y `descarga.py` (0 %).
- **Qué pasa hoy:** es el código de estudio y validación histórica, que no corre en la ronda diaria. Di prioridad a lo
  que sí corre a diario (ronda, verificación, reportes, respaldo, ESTELA en vivo), que quedó entre 84 % y 100 %.
- **Qué sugiero:** probarlo en otra sesión con datos pequeños guardados en el repositorio.

## C. Decisiones mías de esta sesión que conviene que Ángelo o MECÁNICO revisen

1. **Agregué llaves nuevas a `reglamento.yaml`** porque la tanda 11 las pedía: `bots.max_horas_sin_actualizar`,
   `respaldo.carpeta`, `respaldo.guardar_ultimos`, `respaldo.max_horas_sin_respaldo` y
   `reportes.dif_apertura_aviso_pct`. No cambié ningún valor que ya existía.
2. **Los avisos ℹ️ ahora van al final del resumen** (antes de la última línea), no arriba. Con tres avisos nuevos
   posibles, arriba empujaban fuera a las carteras por el corte de 9 líneas. Por eso el resumen puede pasar de 10
   líneas cuando hay avisos ℹ️.
3. **Instalé la herramienta `coverage`** en el entorno de Python para medir la cobertura. No la agregué a
   `requirements.txt`.
4. **Arreglo 59:** la ronda y `ronda --verificar` ahora piden las reglas de Binance frescas cada vez (una petición
   más por corrida). No cambié `datos.cache_exchangeinfo_horas`.
5. **Arreglo 53:** un boleto con una acción o un tipo de orden que el verificador no conoce ahora sale con ❌. Antes
   pasaba con ✅ sin revisión. Si un día se agrega un tipo de boleto nuevo, hay que enseñárselo al verificador.
6. **Arreglo 44:** en la boleta semanal los porcentajes salen con uno o dos decimales (0.0, 0.5, 0.07), para que se
   pueda comparar contra el 0.05 % de deslizamiento del papel.
7. **Arreglo 43:** en Windows la prueba de enlaces simbólicos se salta, porque Windows no deja crearlos sin permiso
   especial. Agregué otra prueba que cubre la misma regla sin crear enlaces; la original sí corre en Linux.

## D. Banco de pruebas de filtros y descartes (11 de noviembre de 2026)

Comando: `python -m sobreviviente banco-filtros`. **Solo mide**, con velas ya guardadas (sin red y sin llaves). No
cambió ninguna regla ni tocó la ronda diaria. El reporte completo queda en `salida/banco_filtros.md` (esa carpeta no
se sube al repositorio). **No promete ganancias:** describe lo que pasó en el pasado, y eso puede no repetirse.

### D1. Qué se midió
- Motores M0, M1 y M2 con los parámetros que ya están en el reglamento (no se buscó ni se eligió ninguno).
- Carteras A, B y C, con 10,000 USDT de capital de prueba (`backtest.capital_ventaja`).
- 14 ventanas de prueba de 3 meses, de enero de 2023 a abril de 2026 (las mismas de la validación: 12 meses de
  entrenamiento + 3 de prueba). Solo se reporta lo de las ventanas de prueba. La prueba final (mayo a octubre de 2026)
  va aparte.
- Línea base = el reglamento sin tocar (hoy solo M0 está encendido). Después, UN filtro cambiado a la vez: 17 filtros.
- Muestra mínima para opinar: 20 operaciones. Con menos, el reporte dice "sin datos suficientes" y no opina.

### D2. Con el reglamento vigente (solo M0) no se puede juzgar NINGÚN filtro
- M0 hizo **15 operaciones** en 3 años y 4 meses de prueba (33 % ganadoras, +0.65 R por operación). Son menos de 20,
  así que esos números pueden ser pura suerte.
- De los 17 filtros, 11 no bloquearon ninguna señal de M0 y los otros 6 quedaron como "sin datos suficientes".
- Caída máxima a valor de mercado en la prueba: Cartera A 3.8 %, B 7.0 %, C 13.1 %.
- **Qué queda como DECISIÓN DE ÁNGELO:** nada que cambiar hoy por estos números. Para poder juzgar los filtros de M0
  hacen falta más operaciones (más meses de papel o de historia); no propongo bajar el mínimo de 20.

### D3. Filtros que este banco no pudo medir
- **Veto de Noticias y evento fuerte:** no hay historial guardado de vetos ni de eventos. Sugerencia (no toca
  riesgo): guardar cada día una copia de `vetos.json` y `eventos.json` para poder medirlos más adelante.
- **Conciliación, datos no confiables y MODO SEGURO:** en un backtest los datos se dan por buenos.
- **Freno total:** en el backtest se simula el OK de Ángelo en cuanto se activa; nunca bloquea señales ahí.
- **BTC bajista, calor lleno y costos:** no bloquearon ninguna señal, porque los motores de la v2 ya piden marea alta
  y no usan meta.
- **Mínimo de Binance, stop inválido y falta de dinero libre:** no se apagan nunca, ni en el banco. Solo se cuentan.
- **Lo que solo pasa en la ronda de papel** (sin señal, fuera de hora, no se llenó, sin precio): desde hoy la ronda
  lo anota cada día en `datos/papel/descartes/`. Todavía no hay historia para medirlo.

### D4. Estudio aparte: M1 y M2 encendidos SOLO dentro del banco
Hoy M1 y M2 están APAGADOS en el reglamento. Este estudio (`--encender M1 M2`) NO es la operación vigente: sirve para
ver cómo se portan los filtros cuando hay más operaciones. Cartera A: 80 operaciones; B: 45; C: 17 (C queda "sin datos
suficientes"). Lo que se vio en A y B:
- **Máximo de posiciones:** las señales que bloqueó, cada una por su cuenta, perdían en promedio (entre −0.46 y −0.23 R
  en A). Sin ese filtro la cartera quedó peor: A −1,926 USDT y B −3,985 USDT contra la línea base, y la caída a valor
  de mercado subió de 12.5 % a 23.0 % en A y de 14.8 % a 33.6 % en B. Peor en 9 de 14 ventanas (A) y en 10 de 14 (B).
- **Universo ("grandes"):** las señales de monedas fuera del universo perdían en promedio (entre −0.59 y −0.48 R; 3,030
  episodios). Sin ese filtro: A −2,183 USDT y B −2,198 USDT, con caída a valor de mercado de 37 % en A y 47 % en B.
- **Veto de ESTELA (encenderlo):** habría bloqueado 44 señales que por su cuenta perdían (entre −0.65 y −0.13 R), pero
  la cartera casi no cambió (A −23 USDT; B igual): casi ninguna de esas señales se estaba tomando.
- **Volatilidad EXTREMA:** no se distingue si lo que bloqueó ganaba o perdía (entre −0.08 y +0.67 R). Sin ese filtro
  la cartera quedó con más dinero (A +1,123 USDT; B +824 USDT), pero mejor en 6 ventanas y peor en 6.
- **Ya hay posición (nunca promediar):** resultado mezclado. Sin ese filtro A quedó +743 USDT y B −2,314 USDT.
- **Pausa por tope y racha de pérdidas:** bloquearon 1 señal cada uno. Sin datos suficientes.
- **Qué queda como DECISIÓN DE ÁNGELO:**
  1. No apliqué ningún cambio. Con estos datos, máximo de posiciones y universo quitaron señales que perdían: no veo
     motivo para tocarlos.
  2. Volatilidad EXTREMA es el único filtro donde apagarlo dejó más dinero, pero el resultado no se sostiene ventana
     por ventana y el rango incluye el cero. Si Ángelo quiere revisarlo, sugiero esperar a tener más operaciones. No
     lo apagué ni lo suavicé.
  3. El veto de ESTELA sigue apagado. Sus señales bloqueadas perdían, pero encenderlo no movió la cartera.
  4. Encender M1 o M2 no se decide con este banco: eso lo decide la validación oficial, que no pasaron.

### D5. Supuestos del banco que conviene que MECÁNICO revise
1. **Sin el bloqueo de volatilidad EXTREMA, la señal se trata como volatilidad ALTA** (tamaño reducido), no como
   normal. Sin el de BTC bajista, como LATERAL.
2. **Las señales repetidas del mismo movimiento cuentan como un solo episodio** (mismo motor, moneda y salida). M0
   repite su señal cada día mientras la marea sigue alta.
3. **La corrida va de corrido por toda la zona de prueba** (las posiciones pasan de una ventana a la otra) y cada
   operación se reporta en la ventana de su decisión.
4. **"Qué habría pasado" con una señal bloqueada es la operación suelta** que ya traía el candidato. No es el efecto
   completo sobre la cartera; ese lo da la corrida con el filtro cambiado.
5. **Apagar un filtro no siempre da más operaciones.** En el estudio, sin "ya hay posición" la Cartera A hizo 46
   operaciones en vez de 80, porque las posiciones repetidas ocuparon los lugares.
6. **Agregué la caída a valor de mercado** junto a la caída sobre la curva de la cartera, porque la segunda no ve lo
   que va perdiendo una posición mientras sigue abierta (en la Cartera A: 0.5 % contra 3.8 %).
7. **La ronda de papel ahora escribe un archivo nuevo por día** (`datos/papel/descartes/descartes_<día>.json`). Solo
   anota; si no se puede escribir, la ronda sigue igual.

## E. Calidad de la señal y de la medición (11 de noviembre de 2026, arreglos 78–83)

Desde `72d9ba8`. Solo limpieza y bugs escondidos: sin funciones nuevas, sin tocar `reglamento.yaml` ni ninguna regla
de riesgo, sin dependencias nuevas. Las pruebas usan velas falsas o casos a mano (sin red y sin llaves). Nada de esto
se midió para que un número del pasado se vea mejor, y nada promete ganancias.

### E1. Qué se hizo
- **Arreglo 78:** los motores diarios suben el stop a la entrada en la R del reglamento
  (`riesgo.gestion.mover_a_entrada_en_r`), igual que el backtest y el papel. Antes `diario.generar` usaba siempre
  1.0 R. Hoy no cambia ningún número (M0, M1 y M2 tienen `mover_a_entrada: false` y el valor es 1.0), pero el banco y
  la validación v2 ya no pueden medir una regla de salida distinta de la del papel.
- **Arreglo 79:** el backtest y los motores diarios arman con las mismas funciones la regla de salida y los arreglos
  de la simulación (`backtest.gestion_simulada` y `backtest.arrays_simulacion`). Antes había dos copias. Resultados
  idénticos.
- **Arreglo 80:** un solo criterio de stop válido (`backtest.stop_valido`) para el backtest y los motores diarios:
  stop y ATR con valor, y el stop del lado correcto del precio. Antes el backtest de la v1 simulaba una señal con el
  stop pegado al precio y reportaba r = 0.0 (inventado). Con las estrategias de hoy no se da (el stop sale del ATR,
  que es mayor que 0 en la vela de señal), así que las operaciones y la curva no cambian.
- **Arreglo 81:** `metricas.resumen_r` da factor de ganancia 0 (no infinito) cuando no hubo ninguna ganancia ni
  pérdida. La compuerta "factor de ganancia ≥ mínimo" ya no pasa con cero ganancia.
- **Arreglo 82:** la ronda de papel calcula el precio límite del STOP_LOSS_LIMIT en un solo lugar
  (`papel._limite_stop`). Boletos idénticos.
- **Arreglo 83:** el funding de Futuros de largos y cortos va en una sola cuenta en `simular_operacion`. Idéntico bit
  a bit; el caso del largo ya tiene prueba.

### E2. Lo que revisé en el código y está bien (no lo toqué)
- **Acierto y empate:** `resumen_r` cuenta como ganadora r > 0, con r ya neto de comisión, deslizamiento y funding.
  Un empate exacto (r = 0) no es ganadora y entra en la pérdida promedio; la racha perdedora solo cuenta r < 0. No
  sesga el acierto: con costos, r = 0 exacto casi no existe (el único caso que lo producía es el del Arreglo 80) y la
  expectativa no depende de cómo se cuente. Quedó escrito en la docstring y fijo en una prueba.
- **Sin ver el futuro:** la gestión vela por vela revisa el stop antes de moverlo y la salida por canal usa el piso de
  las velas anteriores; el universo y "grandes" usan solo días anteriores; el ranking de M2 usa el cierre del día de
  la señal.
- **Walk-forward:** las ventanas de prueba son contiguas y no se cruzan entre sí (el entrenamiento sí se cruza con
  pruebas anteriores, como debe ser). El periodo empieza el día 1 del mes, así que sumar meses no deja huecos.
- **Validación:** `filtro_reglas_baratas` ya quita las señales con stop inválido antes de elegir parámetros y antes
  de armar las entradas al azar.
- **Supuestos D5 del banco:** coinciden con el código (EXTREMA → ALTA y BAJISTA → LATERAL solo dentro del
  experimento; episodios por motor, moneda y salida; corrida de corrido; caída a valor de mercado).

### E3. Pendiente: DECISIÓN DE ÁNGELO (tocan reglas de riesgo; no las cambié)
1. **Un stop con distancia NaN pasa la revisión del stop.** `riesgo.evaluar_candidato` y `riesgo.calcular_tamano`
   rechazan `distancia <= 0`, pero `NaN <= 0` es falso. Hoy no se da: las estrategias quitan la entrada cuando el
   stop no tiene valor (`estrategias/base.salida`), y el backtest y los motores diarios lo revisan antes con
   `stop_valido`. Sugiero `not (distancia > 0)`. Es una regla de stops: decide Ángelo.
2. **Régimen de BTC por defecto distinto cuando falta el dato.** `backtest.cartera` usa `regimen_btc or "LATERAL"` y
   la ronda de papel usa `marea or "BAJISTA"`. En M0, M1 y M2 no pasa (sin marea alta no hay señal), pero en el
   backtest de la v1, al principio de los datos, una señal sin régimen se evalúa como LATERAL y en papel se
   bloquearía. Es una entrada del motor de riesgo: decide Ángelo cuál vale para los dos.

### E4. Pendiente: propuestas de medición (no tocan riesgo)
1. **El banco simula sin el llenado realista del papel.** `banco_filtros.generar_pool` llama a `diario.generar` sin
   `ejecucion_realista`: compra a la apertura sin límite y stop sin límite. El papel usa compra LIMIT (+0.3 %) y
   STOP_LOSS_LIMIT (0.5 % abajo del stop). Por eso el acierto y la expectativa del banco no son 1:1 con los del papel.
   Sugiero correr el banco también con `ejecucion_realista=True`, como estudio aparte, antes de compararlo con el
   papel. No lo cambié porque movería los números del banco ya reportados en D1–D4.
2. **Las operaciones que siguen abiertas al final de los datos cuentan como cerradas** al último cierre
   (`simular_operacion` las marca con `abierta`, pero nadie lee ese campo). Solo afecta la última ventana y la prueba
   final. Sugiero reportar cuántas había, sin quitarlas: quitarlas sesgaría el resultado hacia abajo, porque en un
   sistema de tendencia las que siguen abiertas suelen ser las que van ganando.
3. **El papel redondea el stop al tick antes del motor de riesgo; el backtest y el banco usan el stop sin
   redondear.** El tamaño difiere por menos de un tick. Basta con saberlo al comparar.
4. **Texto del catálogo:** `descartes.CATALOGO[STOP_O_SIMULACION]` dice "stop o ATR sin valor, o la operación no se
   pudo simular", pero ese código también cubre el stop del lado equivocado (ya era así en el diario; desde el
   Arreglo 80 también en el backtest). Cambiar el texto no estaba en el plan de ese arreglo, así que lo dejé.
5. **Funciones largas.** `papel.ronda_cartera` (317 líneas), `cli_ronda.py`, `banco_filtros.texto_reporte` e
   `informe_v2.escribir` siguen largas: solo quité repeticiones que las pruebas cubren (arreglos 79, 82 y 83).
   `informe_v2.escribir` (406 líneas) tiene 0 % de cobertura; antes de partirla hace falta una prueba que fije su
   salida con datos pequeños guardados en el repositorio. `riesgo.evaluar_candidato` no lo toqué.

### E5. Cifras
- Pruebas (Windows): 570 pasan y 1 saltada al empezar → 603 pasan y 1 saltada al terminar. La saltada es
  `tests/test_arreglo43_respaldo.py` (enlaces simbólicos), igual que antes.
- Cobertura del paquete (`pytest --cov=sobreviviente`): 69 % (68.79 %) al empezar → 69 % (69.36 %) al terminar.
- Líneas: el paquete queda con 15 líneas netas más (+60 / −45): son tres funciones compartidas nuevas y una ampliada,
  con su explicación, que reemplazan lógica repetida en dos o tres lugares. Las pruebas suman 307 líneas.

## F. Tanda 13 (11 de noviembre de 2026, arreglos 84–88)

Rama `codex/marea-v2`, desde `c3d9429`. Solo PAPEL, sin llaves. No cambié `reglamento.yaml` ni ninguna regla de riesgo.

### F1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 84 | `ec1a63f` | `CLAUDE.md` en la raíz con las reglas y el flujo, texto de Ángelo tal cual. Comandos y rutas revisados contra el repositorio: todos existen, no hubo que corregir nada. |
| 85 | `72a1693` | B9: `tests/conftest.py` apunta `~` (HOME y USERPROFILE) a una carpeta temporal en cada prueba. Ninguna prueba lee ya `~/respaldos-sobreviviente`. Sin cambios en el paquete ni en aserciones. |
| 86 | `554d2e1` | B10: 54 pruebas nuevas con velas y clientes falsos, sin red. `validacion_v2` 25 → 99 %, `estela` 33 → 75 %, `auditoria` y `descarga` 0 → 100 %, `e1d`/`e6` 100 %, `e7` 96 %. Sin cambios en producción. |
| 87 | `9e67508` | B3: `registrar_tarea` mide las tareas de RADAR, ESTELA, EJECUTOR y CONTADOR contra el horario de `bots/MIGRACION.md`. Cuenta como a tiempo desde su hora hasta el paso que usa su resultado (decisión de Ángelo en este chat): RADAR 6:00–6:10, ESTELA 6:05–6:10, EJECUTOR 6:15–6:25, CONTADOR 6:25–6:30 (reporte semanal solo el domingo). La ronda sigue con su propia regla. |
| 88 | `9def658` | B5: al guardar la ronda, las rondas de más de 90 días pasan de `cartera_X.json` a `datos/papel/rondas_viejas_X.json` (escritura segura). Solo salen de la cartera después de quedar guardadas allá. Nada se borra; si ese archivo falla, se quedan en la cartera y se avisa con ⚠️. El respaldo ya lo incluye. |

### F2. Pendiente: DECISIÓN DE ÁNGELO
1. **B5, lo que falta — ✅ DECIDIDO por Ángelo (tanda 14): se queda como está (ver G2).** `saltadas_capital` (`estado` muestra el total histórico; moverlas cambiaría esa cifra),
   `registro.jsonl` (`estado --bots --dias N` acepta cualquier N; recortarlo cambiaría la calificación con N > 90),
   `bitacora_rondas.jsonl` y `errores.log` (son de solo agregar renglones; recortarlos implica reescribirlos).
   Falta decidir si se recortan, cada cuánto y qué cifra muestra `estado` después.
2. **CENTINELA no tiene hora medida — ✅ se muestra "sin medir" (Arreglo 89, ver G).** no corre ningún comando. Solo aparece en el registro cuando le rechazan un
   archivo (`papel.py:863`). Medir su puntualidad exigiría leer el "actualizado" de `vetos.json`/`eventos.json`
   (relacionado con B4).
3. **`registrar-llenado` sin horario — ✅ se muestra "sin medir" (Arreglo 89, ver G).** en papel es el ensayo de las 6:15, pero en real llega cuando Binance llena.
   Hasta el Arreglo 89 contaba como a tiempo.

### F3. Pendiente: propuestas (no tocan riesgo)
1. **Cobertura que falta — ✅ RESUELTO (Arreglo 91, ver G):** `informe.py`, `informe_v2.py`, `ejecutar_v2.py` y `ronda2.py` siguen en 0 %. Son salida en
   Markdown y gráficas; conviene fijar su salida con datos pequeños guardados en el repositorio antes de partir
   `informe_v2.escribir` (E4.5).
2. **✅ RESUELTO (Arreglo 90). `estrategias/e7.py:34` usaba `DatetimeIndex.dayofweek`,** que pandas marca como obsoleto (aviso `Pandas4Warning`).
   El cambio es `day_of_week`, mismo resultado. No lo hice porque no estaba en el plan del Arreglo 86, que no cambiaba
   producción.
3. **En esta computadora pytest está en `.venv`;** el Python del sistema no lo tiene. `CLAUDE.md` dice `pytest`: se
   corre con `.venv\Scripts\python.exe -m pytest`.

### F4. Cifras (Windows, `.venv`)
- Pruebas: 603 pasan y 1 saltada al empezar → 682 pasan y 1 saltada al terminar. La saltada sigue siendo
  `tests/test_arreglo43_respaldo.py` (enlaces simbólicos).
- Cobertura del paquete (`pytest --cov=sobreviviente`): 69.35 % (7081 sentencias, 2170 sin cubrir) al empezar →
  78.05 % (7106 sentencias, 1560 sin cubrir) al terminar.

## G. Tanda 14 (11 de noviembre de 2026, arreglos 89–91)

Rama `codex/marea-v2`, desde `3b5712e`. Solo PAPEL, sin llaves. No cambié `reglamento.yaml` ni ninguna regla de riesgo.
A y E3 siguen como DECISIÓN DE ÁNGELO (no los toqué).

### G1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 89 | `402d86d` | F2.2/F2.3: CENTINELA y `registrar-llenado` no tienen hora límite medida. `registrar_tarea` los anota con `a_tiempo = null` y `calificacion_bots` los cuenta aparte (`sin_medir`). `estado --bots` saca el porcentaje "bien y a tiempo" solo de las tareas medidas: dice `sin medir` si no hay ninguna medida, o `P % bien y a tiempo (de M medidas; S sin medir)` si hay de las dos. Rechazos y diferencias se cuentan igual. No se les inventó horario; la ronda y las tareas de `HORARIO_TAREAS` no cambian. Se actualizaron dos aserciones viejas que fijaban el comportamiento anterior: el texto de CENTINELA en `test_arreglo47` y la fila de `registrar-llenado` en `test_arreglo87` (`True` → `None`). |
| 90 | `4082b51` | F3.2: `e7.py` usa `day_of_week` (pandas marcaba `dayofweek` como obsoleto). La prueba compara entrada, salir, stop y fuerza contra la fórmula vieja (BTC alcista y bajista) y exige que ya no avise. |
| 91 | `8dac45a` | F3.1: los cuatro módulos se usan (`validar`, `validar --v2 --informe`, `validar --ronda2`, `estela`), así que no se borró nada. 17 pruebas con datos falsos, sin red. Las salidas de referencia están en `tests/datos_arreglo91/`; `informe_v2.escribir` queda fijado antes de partirlo (E4.5). Cobertura: `informe_v2` 0 → 100 %, `informe` 0 → 73 %, `ejecutar_v2` 0 → 69 %, `ronda2` 0 → 61 %. Sin cambios en el paquete. |

### G2. DECISIÓN DE ÁNGELO
1. **B5 / F2.1 — DECIDIDO:** se queda como está por ahora. No se recortan `saltadas_capital`, `registro.jsonl`,
   `bitacora_rondas.jsonl` ni `errores.log`.
2. **Otras tareas sin horario que siguen contando como "a tiempo":** THE BOSS `ronda` cuando falla (`cli_ronda.py`, sin
   `a_tiempo`), THE BOSS `comando X` (`__main__.py`), `reanudar` y RADAR `exclusiones.json` (`papel.py`). Cuando fallan
   no suman a "a tiempo", porque esa cuenta exige `ok`; un `reanudar` que sale bien sí suma sin que nadie lo haya medido.
   El Arreglo 89 solo se encargó de CENTINELA y `registrar-llenado`. Falta decidir si estas también se muestran como
   "sin medir": en la ronda cambiaría el porcentaje de THE BOSS.

### G3. Pendiente: propuestas (no tocan riesgo)
1. **`sobreviviente/referencias.py:51` y `:85`** también usan `DatetimeIndex.dayofweek` (mismo aviso de pandas). Es el
   mismo cambio del Arreglo 90; no lo hice porque no estaba en el plan.
2. **Cobertura que falta en los cuatro módulos:** `informe.graficas` y `ronda2.grafica_referencias` con matplotlib
   (en el `.venv` de Windows no está instalado), `ronda2.referencias(m)` (necesita un `Mercado` completo) y los pasos
   `veto` y `auditoria` de `ejecutar_v2.ejecutar` (velas de 1 h).
3. **Detalles de texto que quedaron fijados tal cual:** en `VALIDACION_RONDA2.md` sale `—R` y `— %` cuando falta el
   dato (piso de confianza, azar). Si se quiere otro texto, hay que actualizar la referencia a propósito.
4. **La cobertura cambia un poco entre corridas** (1555 contra 1560 sentencias sin cubrir con el mismo código).
   Parece que hay ramas que dependen de la hora a la que se corre. No afecta el piso, pero conviene saberlo al comparar cifras.
5. **Las referencias de `tests/datos_arreglo91/` dependen de `reglamento.yaml`:** versión, fechas y capital. Si
   cambia el reglamento, hay que volver a generarlas.

### G4. Cifras (Windows, `.venv`)
- Pruebas: 682 pasan y 1 saltada en `3b5712e` → 705 pasan y 1 saltada al terminar. La saltada sigue siendo
  `tests/test_arreglo43_respaldo.py`.
- Cobertura del paquete (`pytest --cov=sobreviviente`): 78.05 % (7106 sentencias, 1560 sin cubrir; medido en una
  copia limpia de `3b5712e`) → 87.12 % (7110 sentencias, 916 sin cubrir).

## H. Tanda 15 (11 de noviembre de 2026, arreglos 92–93): el bot de Futuros (E5)

Rama `codex/marea-v2`, desde `ed5777a`. Solo PAPEL, sin llaves. No cambié `reglamento.yaml` ni ninguna regla de riesgo.

### H0. Qué es hoy el bot de Futuros
- La única estrategia de Futuros es **E5 «Francotirador (cortos)»** (`estrategias/e5.py`): solo va en corto (apuesta
  a que baja), en velas de 4 h, con margen aislado y 2x. Solo entra con BTC y la moneda BAJISTAS, y no entra si los
  cortos pagan más de 0.05 % de funding. No hay ninguna estrategia de Futuros en largo (que apueste a que sube).
- **No opera, ni en papel:** E5 está `APAGADA`, las carteras A/B/C tienen `futuros: 0` y el papel (`papel.py`) solo
  compra en Spot. E5 vive en el backtest y la validación.
- En la validación no pasó: expectativa −0.204R, le ganó solo al 5 % del azar y la robustez salió negativa en todos
  los casos (`VALIDACION.md`).
- Revisé todo su camino: señal → simulación → gestión del corto → motor de riesgo → cartera. Esto está bien: el signo
  del funding, el stop del corto (hueco, +1R a la entrada menos costos, chandelier que solo baja), el deslizamiento en
  contra al vender y al recomprar, la comisión sobre el valor completo, la unidad R, el margen y el tope de 2x.

### H1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 92 | `f9e8c64` | E5 se dimensionaba con las reglas de Binance **Spot** (mínimo de la orden y paso de cantidad). Ahora `cargar_mercado` también lee las de **Futuros** (`Mercado.filtros_futuros`, con `exchange_info("FUTUROS")` y su copia de 1 día) y `cartera(..., filtros_futuros)` las usa para las señales de Futuros; `validacion.evaluar` las pasa en sus 4 corridas. Sin reglas de Futuros todo queda como antes. Spot, M0–M2 y el resultado en R de cada operación no cambian. |
| 93 | `49c8348` | La ventana del funding en `simular_operacion`. Binance anota 42 % de las horas de funding unos milisegundos tarde (352,155 de 841,402 en los datos guardados), así que el funding del instante de entrada se contaba unas veces sí y otras no. Además, si el stop saltaba dentro de la vela, se contaba el del cierre aunque la posición ya estaba cerrada. Ahora se compara sin milisegundos y solo mientras la posición seguro seguía abierta: después de entrar y hasta la apertura de la vela de salida (hasta el último cierre si sigue abierta). Mismo signo; las pruebas viejas de funding siguen igual. |

### H2. Efecto medido en los datos guardados
E5 con los parámetros finales de `VALIDACION.md` (`donchian_n` 55, `stop_atr` 3.0, `chandelier_atr` 3.0) en todo el
periodo fuera de muestra (enero 2023 a abril 2026): 720 señales. No es la corrida de validación, que cambia de
parámetros por ventana, pero muestra el tamaño del efecto.
- **Arreglo 92, con 46.18 USDT:** con las reglas de Spot salían 21 cortos ejecutados y 183 saltados por capital
  (capital necesario mediano: 93 USDT). Con las de Futuros quedan **15 ejecutados y 242 saltados** (mediano:
  115 USDT). En las reglas de Futuros guardadas el 11/11/2026, BTC pide al menos 50 USDT por orden y ETH 20, con
  paso de 0.001 en los dos.
- **Arreglo 93:** cambian 377 de las 720 operaciones, pero muy poco: +0.00014R en promedio y +0.021R la que más.
  La expectativa de las señales sueltas pasa de −0.1825R a −0.1823R. No cambia ningún veredicto.

### H3. Pendiente: DECISIÓN DE ÁNGELO
1. **Poner un bot de Futuros en papel — ✅ DECIDIDO por Ángelo (11/11/2026): así queda.** E5 sigue `APAGADA`, las
   carteras siguen con `futuros: 0` y no se construye el papel en corto. Lo que habría hecho falta: cambiar
   `posiciones_max.futuros` (regla de riesgo),
   hacer que el papel sepa ir en corto (función nueva) y pasar las compuertas. Con la evidencia actual de E5 no lo
   recomiendo tal cual. Rediseñar E5 sería otra ronda de ajustes con datos ya vistos (riesgo de sobreajuste). Lo
   honesto sería registrar el diseño antes y medirlo solo con datos nuevos (el papel desde hoy).
2. **La liquidación estimada del corto queda un poco optimista:** `riesgo.precio_liquidacion` da 49.5 % arriba de la
   entrada; la fórmula de Binance (margen aislado, 2x, 0.5 % de mantenimiento) da 49.25 %. En el largo la
   aproximación sí es conservadora. Es regla de riesgo: no la toqué. Con el colchón de 2 no cambia nada en la práctica.
3. **El margen de Futuros no se limita por el efectivo de Spot:** Spot + Futuros pueden pasar del 100 % del capital.
   Además, dentro de un mismo momento de decisión, la cartera del backtest no descuenta del efectivo de Spot el margen
   de un corto recién aprobado (entre un momento y el siguiente sí). Hoy no pasa porque ninguna cartera mezcla Spot y
   Futuros, pero toca reglas de exposición.

### H4. Pendiente: propuestas (no tocan riesgo)
1. **→ Pasó a `HIPOTESIS.md` como Hipótesis 001 (Arreglo 104, ver J).** **El filtro de funding de E5 compara la tasa de cada cobro sin importar cada cuánto se cobra** (1, 4 u 8 h):
   −0.05 % cada hora pesa ocho veces más que cada 8 h. Cambiarlo cambia la señal y obliga a validar otra vez.
2. **Los números de E5 en `VALIDACION.md` se quedan viejos** hasta volver a correr `python -m sobreviviente validar`
   con las cinco estrategias (es pesado). Ojo: `validar E5` solo reescribe el archivo con E5 y se pierden E1–E4.
   Con el Arreglo 92, la línea "Con tus 46.18 USDT" de E5 bajaría (ver H2).
3. **→ Pasó a `HIPOTESIS.md` como Hipótesis 002 (Arreglo 104, ver J).** **El "rebote" de E5 no es espejo exacto de E2:** mira el máximo de 3 velas en vez de 5 y no pide cierre abajo de la
   EMA 20. Coincide con lo que dice su descripción, así que es diseño y no bug. Cambiarlo sería otra ronda de ajustes.
4. **G3.1 sigue pendiente:** `referencias.py:51` y `:85` todavía usan `dayofweek`.

### H5. Cifras (Windows, `.venv`)
- Pruebas: 705 pasan y 1 saltada en `ed5777a` → 716 pasan y 1 saltada. La saltada sigue siendo
  `tests/test_arreglo43_respaldo.py`.
- Cobertura del paquete (`pytest --cov=sobreviviente`): 87.12 % (7110 sentencias, 916 sin cubrir) → 87.13 %
  (7123 sentencias, 917 sin cubrir).

## I. ¿Listo para el papel? Revisión del 11 de noviembre de 2026 (punta `43bfdb2`)

**Veredicto: casi.** La rutina diaria completa funciona: la corrí de punta a punta en una copia aislada, con datos de
Binance de hoy, sin tocar `datos/` ni `salida/` reales. Antes de arrancar faltan dos arreglos (I2.1 y I2.2) y un
ajuste en la computadora de los bots (I2.3). El papel real casi no ha corrido: solo hay una ronda, la del
9 de noviembre (A y B saltadas por capital; la Cartera C nunca corrió).

### I1. Lo que se probó y funciona
- Pruebas: 716 pasan y 1 saltada (Windows); cobertura del paquete 87.13 %.
- En una copia aislada (el mismo reglamento, una copia de `datos/` y el respaldo hacia una carpeta temporal) corrí la
  rutina del Paso 4 de `bots/MIGRACION.md`. Resultados:
  - `doctor`: 👍 (Spot, respaldo, históricos y Futuros responden).
  - `verificar`: ✅.
  - `estela --foto`: 👍, 12 monedas.
  - La ronda, como si fueran las 00:12 UTC: **la Cartera C compra 0.00009 BTC a 74,237.24 con stop en 62,912.91**.
    A y B no llegan al mínimo de Binance (necesitan unos 177 y 89 USDT).
  - `ronda --verificar`: ✅. `registrar-llenado --ensayo`: 👍 copiado igualito. `conciliar`: 👍.
  - `reporte diario`, `respaldo` (👍), `estado` y `estado --bots`: corren bien.
- La lista de monedas «grandes» ya sale sin acciones tokenizadas (bStocks).

### I2. Lo que frena el arranque (arreglos propuestos; esperan tu OK y su plan)
1. **Arreglo 94 · En Windows, con la salida capturada, 7 de 9 comandos se caen — ✅ RESUELTO (`7a9efe7`, ver I5).** Pasa cuando la salida no va a una
   ventana de consola sino a otro programa (un bot que la lee, un archivo de log). Python usa entonces la codificación
   cp1252, que no tiene ✅ ❌ 👍 ni →, y el comando truena con `UnicodeEncodeError`. Medido en la copia: se caen
   `doctor`, `verificar`, la ronda, `ronda --verificar`, `conciliar`, `reporte diario` y `--help`; solo `estado` y
   `estado --bots` funcionan. La ronda deja sus boletos guardados, pero truena al imprimir el resumen: el bot ve un
   error y no ve los boletos. **Cambio propuesto:** que el programa siempre escriba en UTF-8 desde el arranque
   (`__main__`). **Mientras tanto:** poner la variable `PYTHONUTF8=1` en la computadora de los bots lo evita.
2. **Arreglo 95 · Una prueba escribe en el registro real de los bots — ✅ RESUELTO (`cedced1`, ver I5).** La segunda llamada de
   `test_ensayo_tolera_un_precio_casi_igual` (`tests/test_arreglo47_conciliar_ensayo_estado.py`) usa el reglamento
   real. **64 de las 65 filas de `datos/bots/registro.jsonl` vienen de correr pytest.** Por eso `estado --bots` dice
   que EJECUTOR tiene 30 archivos rechazados y 34 diferencias, y el reporte diario dice «Bots con errores hoy:
   EJECUTOR». Además, esa llamada ya no prueba la tolerancia de precio: regresa 1 porque no encuentra el boleto.
   **Cambio propuesto:** que la prueba use su carpeta temporal y revise el motivo. Además, una guarda en
   `tests/conftest.py` que haga fallar cualquier prueba que modifique `datos/` o `salida/` reales. Después habría que
   limpiar esas 64 filas, con copia de respaldo, **solo con tu OK** (`datos/bots/` no está en git).
3. **En la computadora de los bots, `python` debe ser el del `.venv` — ✅ RESUELTO en los textos (ver I6).** El `python` del sistema no tiene pandas
   (`ModuleNotFoundError`). Los textos de los bots e `INSTALACION.md` dicen `python -m sobreviviente …`, así que hay
   que activar `.venv` antes o usar `.venv\Scripts\python.exe`.

### I3. Qué va a medir el papel, y qué no
- **Con 46.18 USDT solo opera la Cartera C.** A y B van a salir como «saltada por capital» cada vez que M0 quiera
  entrar. Que operen en papel exigiría cambiar `carteras.capital_inicial` (DECISIÓN DE ÁNGELO).
- **M0 es lento.** En la validación hizo unos 33 cambios en casi 5 años (unas 5 compras al año), así que en 6 semanas
  habrá de 0 a 2 operaciones. Para dinero real las reglas piden compuertas históricas pasadas (M0 no las pasó: es la
  línea base) y al menos 10 operaciones en papel; con M0 eso tomaría un par de años.
- **Para qué sirve el papel estas semanas:**
  - Probar la operación diaria: ronda a tiempo, bots sin rechazos ni diferencias, conciliación siempre bien.
  - Comparar M0 en la Cartera C contra las referencias R0, R1 y R2 con precios reales.
  - Medir cuánto se mueve el precio entre la apertura que usa el papel y la hora real de la ronda
    (`reportes.apertura_vs_precio`).
- **Lo que no va a decir pronto:** si una estrategia tiene ventaja. Con tan pocas operaciones, cambiar reglas por lo
  que salga en papel sería ajustar al ruido. Las mejoras de señal se registran antes y se miden con datos nuevos. Las
  de operación (bots, boletos, horarios, mensajes) sí se corrigen con lo que muestre el papel.

### I4. Qué revisar cada semana
- `estado --bots`: la meta es 0 rechazos y 0 diferencias.
- `conciliar`: siempre 👍.
- `datos/papel/bitacora_rondas.jsonl`: rondas a tiempo y sin MODO SEGURO.
- `reporte semanal`, y las referencias contra la Cartera C.

### I5. Después de los arreglos 94 y 95 (11 de noviembre de 2026)
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 94 | `7a9efe7` | `main()` pasa la salida a UTF-8 si no lo está. Medido otra vez en la copia aislada, con la salida capturada y la codificación por defecto de Windows: los 9 comandos terminan bien (antes se caían 7). En una ventana de consola y en Linux no cambia nada. |
| 95 | `cedced1` | La prueba de la tolerancia de precio usa su reglamento temporal y revisa el motivo real («precio 75100.0 en vez de 75000.0»). `tests/conftest.py` tiene una guarda que hace fallar cualquier prueba que modifique `datos/` (sin `cache/`) o `salida/` reales. Corrida completa: ningún archivo real cambió. |

- **Registro real de los bots, limpio:** se quitaron las 70 filas que había dejado pytest (36 «boleto inexistente» y
  34 «precio 75100.0 en vez de 75000.0»). Antes se guardó una copia en
  `datos/bots/registro.jsonl.antes-de-limpiar-20261111`. Queda la fila real de la ronda del 9 de noviembre;
  `estado --bots` ya no muestra errores del EJECUTOR.
- **Cifras:** 722 pruebas pasan y 1 saltada (Windows); cobertura del paquete 87.13 % (7126 sentencias, 917 sin cubrir).
- **Veredicto ahora:** listo para arrancar el papel (ver I6 para los comandos). Lo de I3 (qué mide el papel y qué
  no) sigue igual.

### I6. Los comandos de los bots usan el Python del `.venv` (pedido por Ángelo, 11 de noviembre de 2026)
- `bots/*.md` (RADAR, CENTINELA, ESTELA, EJECUTOR, CONTADOR, THE BOSS y MIGRACION) e `INSTALACION.md`: cada
  `python -m sobreviviente …` pasó a `.venv\Scripts\python.exe -m sobreviviente …`. **Hay que volver a pegar en
  Grok Bot los textos de los bots que cambiaron.**
- `INSTALACION.md` ahora crea el entorno primero (`python -m venv .venv`) e instala los paquetes ahí, para que esa
  ruta exista en una instalación nueva. En Linux o Mac va `.venv/bin/python`. También se corrigió un dato viejo: la
  primera ronda crea tres carteras (A, B y C), no dos.
- Probado en esta computadora: `.venv\Scripts\python.exe -m sobreviviente estado` funciona igual en PowerShell y en
  `cmd` (código 0). Los comandos se corren dentro de la carpeta del proyecto.
- **✅ RESUELTO con el Arreglo 96 (ver I7). Quedaban con el comando viejo:** los avisos que imprime el
  programa. Son la ayuda de `doctor` («Corre: pip install -r requirements.txt»), el ℹ️ de la ronda («corre
  'python -m sobreviviente respaldo'», cuyo texto fija `test_arreglo43_respaldo.py`), «Usa: python -m sobreviviente
  estela --foto» (`cli_ronda.py`) y el de `banco_filtros.py`. Un bot que los siga al pie de la letra usaría el
  `python` del sistema.
- `CLAUDE.md` también dice `pip install` y `pytest` sin `.venv`. Es texto tuyo, así que no lo toqué.

### I7. Arreglo 96: los avisos del programa dicen el Python del `.venv`
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 96 | `3680daa` | `python_actual()` (`sobreviviente/__init__.py`) da el Python que está corriendo el programa, listo para copiar: dentro del proyecto `.venv\Scripts\python.exe` (en Linux o Mac `.venv/bin/python`); fuera, la ruta completa. Lo usan los 6 avisos que decían `python -m sobreviviente` o `pip install`: el ℹ️ de respaldo de la ronda, la ayuda de `doctor`, el «Usa:» de `estela`, el aviso de `banco-filtros` y la línea de uso de `--help`. Cinco aserciones viejas con el texto exacto pasaron al texto nuevo, igual de exacto. |

- Prueba de humo repetida en una copia aislada nueva, con toda la rutina diaria y datos de Binance de hoy: todo 👍.
  El ℹ️ de la ronda dice «corre '.venv\Scripts\python.exe -m sobreviviente respaldo'». El reporte diario ya no
  muestra errores falsos del EJECUTOR y `estado --bots` da 0 rechazos y 0 diferencias.
- **Cifras:** 728 pruebas pasan y 1 saltada (Windows); cobertura del paquete 87.19 % (7143 sentencias, 915 sin cubrir).
- **Para arrancar el papel solo falta** volver a pegar en Grok Bot los textos de los bots que cambiaron (I6).

## J. Tanda 16 (12 de noviembre de 2026, arreglos 97–104)

Rama `codex/marea-v2`, desde `e93e01c`. Solo PAPEL, sin llaves. No cambié `reglamento.yaml` ni ninguna regla de riesgo.
Cada arreglo es un commit con pytest completo pasando (Windows, `.venv`) y su push; GitHub los volvió a correr en
Linux y todos pasaron (el 97 es anterior al workflow).

### J1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 97 | `01b0dcd` | `requirements.lock` con las 18 versiones exactas del `.venv` que pasa las pruebas (Python 3.12.10, Windows). `INSTALACION.md` instala desde ese archivo; `requirements.txt` queda como la lista de mínimos. Revisé que las 18 versiones tienen paquete para Linux con Python 3.12. |
| 98 | `525c91d` | `.github/workflows/pruebas.yml`: en cada push a `codex/marea-v2` instala desde `requirements.lock` con Python 3.12 y corre pytest completo con cobertura del paquete. Sin secretos y con permisos de solo lectura. |
| 99 | `5e9b297` | Sin pickle: `ejecutar_v2.py` guarda y lee `salida/v2/<paso>.json` (antes `.pkl`). Leer un pickle puede correr código; leer JSON no. Lo que JSON no tiene (Series, DataFrame, fechas, tuplas, llaves numéricas, NaN e infinito, escalares de numpy) va con una marca `__tipo__` y regresa igual y del mismo tipo. Un tipo desconocido es error y no deja archivo a medias. `test_arreglo91` espera `.json` en lugar de `.pkl`, con las mismas comprobaciones. No era demasiado grande (unas 100 líneas en un solo archivo), así que sí se hizo. |
| 100 | `82932cb` | Fuera `.claude/skills`: las 11 skills del paquete Day Trader de acciones de EE. UU. y su licencia (28 archivos). `README.md` hablaba solo de ese paquete; ahora describe Sobreviviente y apunta a `INSTALACION.md`, `CLAUDE.md`, `PROPUESTAS.md` y `bots/`. |
| 101 | `f26c219` | **Extra, no estaba en la lista:** GitHub pide iniciar sesión con permisos de administrador para leer los logs, así que no se podía ver la cifra de Linux. Ahora el workflow publica el resumen de pytest y la cobertura como aviso, que se ve en la página del run sin iniciar sesión. Si pytest falla, el paso sigue fallando. |
| 102 | `7f6862b` | `CLAUDE.md` (autorizado por Ángelo): los comandos usan `.venv\Scripts\python.exe` (en Linux o Mac, `.venv/bin/python`), instalar va desde `requirements.lock` y la cifra de pruebas es la nueva (en `f26c219`: 746 en Linux y 745 más 1 saltada en Windows). También corregí que en Windows se salta una prueba de `test_arreglo43_respaldo.py`, no el archivo completo. |
| 103 | `a11727a` | La rutina diaria la arranca RADAR (6:00 p. m.). Ahora corre primero `.venv\Scripts\python.exe -m sobreviviente doctor`. Si no termina con «👍 Todo listo.», manda a THE BOSS el mensaje completo y sigue. THE BOSS corre la ronda igual (tiene su MODO SEGURO) y pone ese mensaje en el suyo a Ángelo. Cambian `bots/1_RADAR.md`, `bots/THE_BOSS.md` y el horario de `bots/MIGRACION.md`. |
| 104 | `d46e0b1` | `HIPOTESIS.md`: las 4 reglas al inicio, la plantilla por idea y las dos mejoras de señal pendientes (H4.1 y H4.3, con su texto sin cambios) como hipótesis 001 y 002, en borrador. Les faltan campos que nadie ha definido (qué se espera, cómo se prueba, mínimo de operaciones) y no los inventé. `bots/THE_BOSS.md`: en su reporte semanal puede proponer hipótesis con ese formato, pero nunca aplicarlas ni editar el archivo. |

### J2. Textos de bots que hay que volver a pegar en Grok Bot
- **`bots/1_RADAR.md`** (arreglo 103): el paso 1 nuevo con `doctor`. Los demás pasos se recorrieron un número.
- **`bots/THE_BOSS.md`** (arreglos 103 y 104): la ronda se corre aunque `doctor` no salga 👍, la línea de RADAR en
  «Qué espero de cada bot», el domingo y la sección nueva «Hipótesis nuevas».
- `bots/MIGRACION.md` también cambió (la fila de las 6:00 en el Paso 4), pero es la guía del cambio, no un texto para
  pegar.
- CENTINELA, ESTELA, EJECUTOR y CONTADOR no cambiaron en esta tanda. Si todavía no se pegaron los textos de I6
  (comandos con `.venv`), lo más simple es volver a pegar los 6 completos.

### J3. Pendiente: propuestas (no tocan riesgo)
1. **La versión de Python de la computadora de Grok Bot no está escrita en el repositorio.** Usé 3.12, la del `.venv`
   que fija el lock. La primera línea de `doctor` dice la versión de esa computadora: si no es 3.12, hay que cambiar
   `python-version` en el workflow y la cabecera de `requirements.lock` (la prueba del arreglo 98 exige que coincidan).
   ~~Los paquetes del lock piden Python 3.11 o más nuevo (pandas 3.1.1).~~ **Corrección (Arreglo 106, ver J6):**
   numpy 2.5.4 pide Python 3.12 o más nuevo, así que con 3.11 la instalación falla.
2. **✅ RESUELTO (Arreglo 105, `9dc7fa9`, ver J5). `doctor` todavía dice «pip install -r requirements.txt»** cuando falta un paquete (`doctor.py:45`; el texto lo
   fija `test_arreglo96`), pero `INSTALACION.md` ya dice que se instale desde `requirements.lock`. Es un arreglo chico;
   no lo hice porque no estaba en la lista. Ahora que RADAR corre `doctor` a diario, importa más.
3. **✅ RESUELTO (Arreglo 110, ver J7). Avisos de GitHub en cada run:** `actions/checkout@v4` y `actions/setup-python@v5` son de Node 20 (GitHub ya los
   corre con Node 24 y funcionan; las versiones nuevas son `checkout@v5` y `setup-python@v6`). Además, `ubuntu-latest`
   va a pasar a Ubuntu 26: fijar `ubuntu-24.04` va con la idea de dependencias fijas.
4. **✅ AHORA LO AVISA (Arreglo 107, ver J7). Los resultados viejos en `.pkl` ya no se leen.** En esta computadora `salida/v2/` está vacía. Si en otra hay
   `.pkl`, se vuelve a correr `validar --v2` (no hace falta en Grok Bot).
5. **D4.2 (volatilidad EXTREMA) no pasó a `HIPOTESIS.md`:** es un filtro del motor de riesgo y está como DECISIÓN DE
   ÁNGELO, no como mejora de señal. Si Ángelo quiere medirlo, se registra como hipótesis nueva.

### J4. Cifras
- **Pruebas en Windows (`.venv`):** 728 pasan y 1 saltada en `e93e01c` → 759 pasan y 1 saltada en `d46e0b1`
  (97: 731 · 98: 735 · 99: 741 · 100: 741 · 101: 745 · 102: 749 · 103: 754 · 104: 759). La saltada sigue siendo la
  de enlaces simbólicos de `tests/test_arreglo43_respaldo.py`.
- **Pruebas en Linux (GitHub, Python 3.12, desde `requirements.lock`):** 746 pasan y 0 saltadas en `f26c219` → 760
  pasan y 0 saltadas en `d46e0b1`.
- **Cobertura del paquete:** 87.19 % (7143 sentencias, 915 sin cubrir) al empezar → 87.33 % en Windows (7236
  sentencias, 917 sin cubrir) y 87.31 % en Linux (7236, 918) en `d46e0b1`. El piso del 69 % se cumple.

### J5. Arreglo 105: `doctor` manda a instalar desde `requirements.lock` (pedido por Ángelo, J3.2)
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 105 | `9dc7fa9` | Cuando falta un paquete, `doctor` decía «pip install -r requirements.txt». Ahora dice «… -m pip install -r requirements.lock», el mismo archivo que `INSTALACION.md`. La aserción exacta de `test_arreglo96` pasó al texto nuevo, igual de exacta. Prueba nueva: el aviso usa el archivo de instalación de `INSTALACION.md` para los 4 paquetes (pandas, numpy, yaml, requests). |

- No cambia ningún texto de bots: es lo que imprime el programa. No hay que pegar nada nuevo por este arreglo.
- **Cifras:** Windows 763 pasan y 1 saltada; Linux (GitHub) 764 pasan y 0 saltadas. Cobertura del paquete igual:
  87.33 % en Windows y 87.31 % en Linux (7236 sentencias).

### J6. Arreglo 106: Python 3.12 como mínimo, y qué falta para arrancar
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 106 | `37ac3cf` | Lo encontré al revisar si faltaba algo para arrancar: numpy 2.5.4, fijo en `requirements.lock` desde el Arreglo 97, pide Python 3.12 o más nuevo, pero `INSTALACION.md`, `README.md` y `doctor` aceptaban 3.11. Con 3.11 la instalación fallaba y `doctor` decía que bastaba. Ahora `doctor.PYTHON_MINIMO = (3, 12)` y los textos dicen 3.12. La prueba nueva saca el mínimo de los paquetes del lock instalados y exige que coincida con `doctor` y los textos. |

- **Prueba de humo:** `.venv\Scripts\python.exe -m sobreviviente doctor` de verdad en esta computadora: todo ✅,
  termina con «👍 Todo listo.» (lo que espera el texto de RADAR) y código 0. No cambió nada del repositorio.
- **✅ RESUELTO (Arreglo 109, ver J7). `CLAUDE.md` todavía dice «Python 3.11+»** en su primera línea. Es texto de Ángelo y su permiso de esta tanda era
  para la cifra de pruebas y los comandos con `.venv`, así que no lo cambié.
- **Ángelo confirmó (12/11/2026) que todavía no ha pegado ningún texto en Grok Bot** (y aún no tiene uso de Grok).
  Para arrancar el papel falta, en este orden: instalar en la computadora de Grok Bot con `INSTALACION.md` (Python
  3.12 o más nuevo; `doctor` debe terminar con 👍), pegar los 6 textos completos (`THE_BOSS.md` y los 5 bots, Pasos 1
  y 2 de `bots/MIGRACION.md`), pausar los bots viejos (Paso 3) y poner el horario (Paso 4). En el código no queda
  nada que frene el arranque.
- **Cifras:** Windows 768 pasan y 1 saltada; Linux (GitHub) 769 pasan y 0 saltadas. Cobertura del paquete: 87.33 %
  en Windows (7237 sentencias, 917 sin cubrir) y 87.32 % en Linux (7237, 918).

### J7. Revisión de los arreglos 97–106 y sus correcciones (arreglos 107–110, pedido por Ángelo)
Se revisó todo lo de esta tanda (`/code-review`, nivel alto, `e93e01c..37ac3cf`). Salieron 8 hallazgos; ninguno toca
riesgo ni dinero. Los 8 quedaron corregidos:

| Arreglo | Commit | Hallazgos que corrige | Qué cambió |
|---|---|---|---|
| 107 | `b5deee1` | Tipos que faltaban; un tipo desconocido tiraba un paso largo; `.pkl` viejos ignorados sin avisar; escritura propia en vez de la segura | `ejecutar_v2` guarda y lee `pd.NA`, `np.datetime64`, `np.timedelta64`, `datetime.timedelta` y `Period`. Los pasos largos usan `_guardar_rescatando`: un valor de tipo desconocido queda vacío (se lee como None), el resto se guarda y se avisa con ⚠️; `_guardar` sigue estricto. Si solo está el `.pkl` viejo, `FaltaResultado` dice qué paso volver a correr: el informe ya no sale vacío y `veto` lo revisa antes de cargar nada. `validar` lo muestra con ❌ y no lo anota como falla de un bot. Escribe con `archivos.escribir_json_seguro` (fsync y copia `.bak`) y lee con `leer_json_seguro` (usa la `.bak` si el archivo está dañado). `test_arreglo99` espera también el `.bak` al guardar dos veces. |
| 108 | `5c73262` | THE BOSS prometía de más con el MODO SEGURO; dos hipótesis propuestas podían repetir número | THE BOSS, RADAR y la fila de las 6:00 de MIGRACION dicen que el MODO SEGURO cubre conexión, datos y archivos de los bots, y que si falta un paquete, el Python es viejo o no se puede escribir en `datos/`, la ronda truena con ❌. THE BOSS pone «por asignar» en el número de las hipótesis que propone; lo pone Ángelo al registrarlas (la plantilla de `HIPOTESIS.md` lo dice). |
| 109 | `9c2aac2` | `CLAUDE.md` decía Python 3.11+ | Dice 3.12+ (autorizado por Ángelo). |
| 110 | `e094e55` | Máquina y acciones del workflow sin fijar | `runs-on: ubuntu-24.04`, `actions/checkout@v7` y `actions/setup-python@v7` (versiones mayores actuales, Node 24). El run de GitHub ya no trae los avisos de Node 20 ni de Ubuntu. |

- **Textos de bots que cambiaron otra vez:** `bots/THE_BOSS.md`, `bots/1_RADAR.md` y `bots/MIGRACION.md`. Como Ángelo
  todavía no pega ninguno, no cambia nada para él: al arrancar se pegan los 6 completos.
- **Cifras:** Windows 787 pasan y 1 saltada (la de enlaces simbólicos); Linux (GitHub) 788 pasan y 0 saltadas.
  Cobertura del paquete: 87.67 % en Windows (7273 sentencias, 897 sin cubrir) y 87.65 % en Linux (7273, 898).

## K. Tanda del 14 de noviembre de 2026 (arreglos 111–121)

Rama `codex/marea-v2`, desde `82696e8`. Solo PAPEL, sin llaves. No cambié `reglamento.yaml` ni ninguna regla de riesgo
(riesgo por operación, topes, caída, exposición, stops, tamaño, universo), ni la señal de E5. Cada arreglo es un
commit con pytest completo pasando (Windows, `.venv`, en una copia aparte de cada commit) y la cobertura sin bajar.

### K1. Parte A: arreglos de la revisión del mecánico
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 111 | `d31c6cf` | `cli_ronda.py`: la ronda repetida («ya existía») y la repetida que no pudo leer lo guardado quedan «sin medir» (`a_tiempo = null`), como en el arreglo 89. Ojo con las líneas: en las ~199 y ~235 que decía la revisión la hora sí se mide (TEMPRANO y OK/FUERA DE HORA) y no cambiaron; las que caían en el «a tiempo» por defecto eran las de las líneas 172, 176 y 218. La ronda que truena (218) sí tenía su hora medida: queda a tiempo salvo FUERA DE HORA. `registrar_tarea` gana `medir=False`. |
| 112 | `3f177b6` | `bots/THE_BOSS.md`, último punto de «Lo más importante»: el texto que pidió Ángelo (anota el texto sospechoso en su mensaje de las 6:30 p. m.). Ya no dice «avisa a THE BOSS» ni «exclusión o veto». RADAR y CENTINELA no cambian. `bots/MIGRACION.md` no necesitó cambio. |
| 113 | `6fe307a` | `referencias.py`: `day_of_week` en vez de `dayofweek` (DCA semanal y rotación pura), como en el arreglo 90. Misma salida. |
| 114 | `42cde73` | «sin dato» en lugar de «—R» y «— %» (`informe._fu`, usado en todo `informe.py` y `ronda2.py`). `VALIDACION_RONDA2.md` regenerado con `validar --ronda2` (ver K3). |
| 115 | `758540c` | Solo pruebas: `referencias.py` con números a mano (métricas, comprar y aguantar, DCA, tendencia pura, R0, R1, R2, por año), `ronda2.referencias`, `informe` (robustez y sección sin Monte Carlo/azar/BTC) y los pasos `veto` y `auditoria` de `ejecutar_v2`. |
| 116 | `b28fbb1` | `CLAUDE.md`, línea de las pruebas: decía 746 (`f26c219`); ahora 855 en Linux y 854 más 1 saltada en Windows, en `7c0799f` (autorizado en esta tanda). Va en la historia después del 121 porque lleva la cifra de la tanda completa. |

### K2. Punto 7: banco de filtros con velas reales públicas de Binance (solo medir)
- Corrí `banco-filtros` (línea base) y el estudio `--encender M1 M2`, con las velas reales de Binance que ya están en
  la caché (públicas, sin llaves; terminan el 31/10/2026, que es `backtest.fin` del reglamento y no lo moví).
- **Salieron exactamente las mismas cifras que el 11/11 (sección D):** los dos reportes son idénticos renglón por
  renglón, salvo la fecha. Línea base (solo M0): 15 operaciones en las ventanas de prueba, 33.3 % ganadoras, +0.65R;
  caída a valor de mercado A 3.8 %, B 7.0 %, C 13.1 %; ningún filtro con datos suficientes para opinar. Estudio con M1
  y M2: A 80 operaciones (+0.21R, caída 12.5 %), B 45 (+0.48R, 14.8 %), C 17 (sin datos suficientes).
- Lo de D2 y D4 sigue igual, también lo que queda como DECISIÓN DE ÁNGELO. No cambié señales ni reglas.
- Para medir con velas más nuevas (noviembre) habría que mover `backtest.fin` en `reglamento.yaml` y volver a
  descargar. Eso es cambiar el reglamento: lo dejo como DECISIÓN DE ÁNGELO (no hace falta para nada de esta tanda).

### K3. `VALIDACION_RONDA2.md` regenerado (arreglo 114)
- Se corrió `validar --ronda2` con matplotlib (de `requirements-extra.txt`) en un entorno aparte, para conservar las
  gráficas; el `.venv` del proyecto no se tocó. Tardó unos 5 minutos.
- Cambian los 6 «— %» por «sin dato» (en la ronda 2 la prueba final ya es una ventana del walk-forward: no hay
  rendimiento aparte de BTC ni de la estrategia), la fecha y la versión del reglamento (1.1.0 → 2.0.1).
- **Veredictos, compuertas y todas las cifras de E1D, E6 y E7 son iguales.** Lo único que se movió es «Con tus 46.18
  USDT reales»: E1D se habría ejecutado 28 veces y saltado 420 (antes 29 y 418); E6, 0 y 1,523 (antes 1 y 1,401). Es
  por las reglas de Binance de hoy (exchangeInfo se volvió a leer el 14/11) y el reglamento 2.0.1. Las gráficas se
  volvieron a dibujar.
- `VALIDACION_V2.md` tiene un «— %» (la concentración de M0, de `informe_v2.py`). No estaba en la lista y no lo toqué.

### K4. Parte B: Futuros, solo lo que no toca reglas
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 117 (F1) | `1b6581d` | `backtest.simular_operacion`: cada cobro de funding va por el precio de esa hora (`precio_funding`, índice = hora en que se conoce el precio), no por el de entrada. Sin esa serie, o antes de que empiece, se usa la entrada como antes (los motores diarios y la ventana del arreglo 93 no cambian). Caso de la tanda (corto 30 días, baja 30 % en línea recta, +0.01 % cada 8 h, 90 cobros): con entrada 100, antes 0.9 por unidad y ahora 0.7635; sobrestimaba 17.9 %. La tanda calculó 0.8985 contra 0.7672 (17.1 %); la diferencia es la entrada y dónde cae cada cobro en la recta. |
| 118 (F2) | `607378d` | `datos.intervalo_funding(serie)` (1, 2, 4 u 8 h desde el cobro anterior; el primero toma el del siguiente; un hueco de más de 8 h cuenta como 8) y `datos.funding_por_8h(serie)`. Se corrigió la docstring de `funding_historico`. No cambia la señal de E5. En la caché, **89 de 170 perpetuos tuvieron algún cobro de menos de 8 h** (BTC y ETH siempre de 8 h). |
| 119 (F3) | `156be1d` | Velas de 1 h del precio de marca (`markPriceKlines`) de los archivos mensuales oficiales, en `cache/futuros/marca_1h/`, con caché como las de Futuros; `descargar` también las baja. Solo datos; prueba con zips falsos. |
| 120 (F4) | `0b5c15c` | La simulación revisa la liquidación con el precio de marca: si la marca cruza la liquidación estimada antes de que salga el stop, `liquidada=True` y pierde el margen aislado completo (más la comisión de entrada, con el funding que ya llevaba). Con la marca en la caché, el funding del F1 va por el cierre de marca. Sin marca, nada cambia y el resultado no trae `liquidada`. |
| 121 (F5) | `7c0799f` | Comando `futuros-capital` (solo informa). Ver K6. |

**Efecto en E5, medido como en H2.** Mismos parámetros finales de `VALIDACION.md` (`donchian_n` 55, `stop_atr` 3.0,
`chandelier_atr` 3.0, `funding_min_pct` −0.05), de enero de 2023 a abril de 2026, con el precio de marca real bajado
de los archivos públicos de Binance (170 perpetuos, sin llaves): 720 señales, igual que en H2.
- **F1 (funding al precio de cada cobro):** cambian 707 de las 720 operaciones, muy poco: +0.00013R en promedio y
  +0.022R la que más. La suma del funding (÷ entrada) pasa de −0.200 a −0.189: en esas operaciones E5 pagaba funding neto,
  y un poco menos de lo que se calculaba: se cobra sobre el valor de cada momento, que en promedio quedó abajo de la
  entrada. Con el cierre de marca o con el
  de Futuros sale prácticamente lo mismo.
- **F4 (liquidación):** **0 liquidaciones de 720** con 2x y el colchón de 2. No cambia ninguna operación.
- La expectativa de las señales sueltas pasa de −0.1823R a −0.1822R. **No cambia ningún veredicto:** E5 sigue muy
  lejos de las compuertas.

### K5. F6: stops de Futuros, Binance cambió la ruta (solo nota; todavía no hay boletos de Futuros)
Lo que pasó Ángelo en la tanda (no lo verifiqué contra la documentación de Binance desde aquí):
- Desde diciembre de 2025, en USDⓈ-M, `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `STOP`, `TAKE_PROFIT` y
  `TRAILING_STOP_MARKET` van por el Algo Service: `POST /fapi/v1/algoOrder` con `algoType=CONDITIONAL` y
  `triggerPrice` (no `stopPrice`). Si se mandan por `/fapi/v1/order`, Binance contesta −4120.
- **Cualquier boleto de Futuros, cuando exista, debe llevar:**
  1. margen `ISOLATED`;
  2. el apalancamiento puesto **antes** de abrir;
  3. el stop como `STOP_MARKET` por `algoOrder` con `closePosition=true` (sin `quantity` ni `reduceOnly`);
  4. `workingType=MARK_PRICE` (el stop se dispara con el precio de marca, el mismo con el que se liquida; F3 ya lo
     guarda);
  5. `priceProtect=false`: con `true`, Binance deja expirar el stop si el último precio y el de marca se separan mucho,
     justo cuando más se necesita.
- **Antes de cualquier operación real de Futuros hay que comprobar que el conector de Grok Bot pone el stop por
  `algoOrder`.** Si lo manda por `/fapi/v1/order`, el stop no queda puesto (−4120) y la posición queda sin protección.
- Hoy no cambia nada en el código: el papel solo compra en Spot y E5 sigue `APAGADA`.

### K6. F5: `futuros-capital` con los datos guardados
`.venv\Scripts\python.exe -m sobreviviente futuros-capital` (reglas de Futuros leídas el 14/11; precios del último
cierre guardado, 31/10/2026; 144 perpetuos en `TRADING` con velas en la caché):
- **Las referencias de la tanda se reproducen exactas** (corto, 1 % de riesgo; stop de 5 % / 15 %): mínimo 5 USDT →
  24 / 65; 20 → 95 / 261; 50 → 238 / 652; 100 → 476 / 1,304. Quedan fijas en la prueba.
- **BTCUSDT:** exchangeInfo dice mínimo 50 USDT, pero también minQty 0.001 BTC, que al último cierre (77,520) vale
  77.52 USDT. Manda la cantidad mínima: con el stop típico de E5 (2.5 %) hacen falta 195 USDT en A, 98 en B y 43 en C.
- **El stop típico de E5** (mediana de 2.5 × ATR de 4 h ÷ cierre en ~90 días) va de 1.3 % a 13.3 % según el perpetuo
  (mediana 7.1 %); BTC 2.5 % y ETH 3.6 %. Con el mínimo de 5 USDT de casi todas las altcoins y un stop de 7 %, A pide
  unos 33 USDT: por eso caben muchas con 46.18.
- **Con 46.18 USDT caben:** A 129 de 144, B 140, C 144. **Con 10 USDT:** A 1, B 3, C 125. Con el 1 % de A, con 10 USDT
  cabe un solo perpetuo, TRXUSDT, el de stop típico más chico (1.3 %); la tanda decía «nada» con stops de 5 % y 15 %. La cifra de C es
  solo de referencia: C se dimensiona por exposición, no por riesgo.
- Esto no cambia nada: E5 sigue `APAGADA` y las carteras con `futuros: 0`.

### K7. Textos de bots que hay que volver a pegar en Grok Bot
- **`bots/THE_BOSS.md`** (arreglo 112): solo cambió el último punto de «Lo más importante».
- RADAR, CENTINELA, ESTELA, EJECUTOR y CONTADOR no cambiaron. `bots/MIGRACION.md` tampoco.
- Como Ángelo todavía no pega ninguno (12/11), no cambia nada para él: al arrancar se pegan los 6 completos.

### K8. Cifras
- **Pruebas en Windows (`.venv`, pytest completo de cada commit en una copia aparte):** 787 pasan y 1 saltada en
  `82696e8` → 855 pasan y 1 saltada en `b28fbb1` (111: 791 · 112: 793 · 113: 798 · 114: 806 · 115: 821 · 117: 826 ·
  118: 832 · 119: 835 · 120: 842 · 121: 854 · 116: 855). La saltada sigue siendo la de enlaces simbólicos de
  `tests/test_arreglo43_respaldo.py`.
- **Pruebas en Linux (GitHub, Python 3.12, desde `requirements.lock`):** 788 en `82696e8` → 827 en `1b6581d` y 855 en
  `7c0799f`, 0 saltadas. Esa es la cifra que quedó en `CLAUDE.md`.
- **Cobertura del paquete:** 87.67 % (7273 sentencias, 897 sin cubrir) al empezar → 89.73 % en Windows (7441, 764) y
  89.72 % en Linux (7441, 765) en `7c0799f`. Nunca bajó entre un commit y el siguiente; el piso del 69 % se cumple.

### K9. Pendiente: DECISIÓN DE ÁNGELO (no hice nada de esto)
Lo que la tanda dejó para el domingo, sin tocar: el cambio de reportes en `reglamento.yaml`, las referencias R3 y R4,
la Cartera F, los topes propios de Futuros, la liquidación con la fórmula oficial y cualquier cambio a la señal de E5.
Lo que salió de esta tanda y también toca reglas:
1. **La liquidación del F4 usa la fórmula de siempre** (`riesgo.precio_liquidacion`, un poco optimista en el corto;
   ver H3.2). El F4 solo informa; cambiar la fórmula es regla de riesgo.
2. **Con funding cada 1, 2 o 4 h, el filtro de E5 compara la tasa de cada cobro sin llevarla a 8 h** (Hipótesis 001).
   El F2 ya da `funding_por_8h`, pero usarlo en la señal es cambiar E5 y validar otra vez.
3. **Velas más nuevas para el banco** (K2): mover `backtest.fin`.
