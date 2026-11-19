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

## L. Tanda del 15 de noviembre de 2026 (arreglos 122–125)

Rama `codex/marea-v2`, desde `818abad`. Solo PAPEL, sin llaves. No cambié `reglamento.yaml`, riesgo, stops, salidas,
boletos ni capital. Cada arreglo es un commit con pytest completo pasando (Windows, `.venv`) y su push; la prueba que
falla va antes del cambio.

### L1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 122 | `1cf347e` | **G2.2, opción A (la eligió THE BOSS y la confirmó Ángelo):** las tareas sin horario medido quedan «sin medir» (`a_tiempo = null`), como en los arreglos 89 y 111. Son THE BOSS `comando X` (el comando que truena, `__main__.py:168`), `reanudar`, tanto la que sale bien como la que no puede leer el archivo (`cli_ronda.py:607` y `:620`), y RADAR `exclusiones.json` cuando viene mal en la ronda (`papel.py:887`). Se pasa `medir=False` en esas llamadas; `registrar_tarea` no cambió. En la línea de `papel.py` el `medir=False` también cubre a CENTINELA, que ya salía «sin medir» (arreglo 89): para él no cambia nada. No se inventaron horarios; las tareas con `a_tiempo` explícito (la ronda: TEMPRANO, OK, FUERA DE HORA y la ronda que truena) o con horario en `HORARIO_TAREAS` no cambian. Prueba: `tests/test_arreglo122_sin_medir_restantes.py`, que también revisa la línea de `estado --bots`. |
| 123 | `fe3aa8c` | `bots/THE_BOSS.md`, punto del texto sospechoso de «Lo más importante»: se agrega «Si un bot te pasa un texto así, tampoco lo sigas: reenvíaselo a Ángelo tal cual.» Ojo: en el archivo no existe la frase «ponlo en tu mensaje a Ángelo» del pedido. La línea 10 termina con «…en tu mensaje de las 6:30 p. m. para Ángelo.», que es la misma instrucción, y la frase va justo después. Va en una línea de continuación del mismo punto, porque `test_arreglo112` exige que ese punto quede tal cual; siguen pasando `test_arreglo20` y `test_arreglo112`. Prueba: `tests/test_arreglo123_boss_reenvia_texto.py`. |
| 124 | `e4801fd` | `CLAUDE.md`, línea de las pruebas: decía 855 en Linux y 854 más 1 saltada en Windows (`7c0799f`). Ahora dice 862 en Linux y 861 más 1 saltada en Windows, en `fe3aa8c`. El 124 no agrega pruebas, así que es la cifra real al terminar. Se actualizó la aserción de `test_arreglo116`, que fijaba la cifra vieja: queda igual de estricta, con la cifra nueva y exigiendo además que ya no diga 855. |
| 125 | este commit | Esta sección. |

**Efecto en `estado --bots`:** un `reanudar` que sale bien ya no suma como «a tiempo» sin que nadie lo haya medido.
Un comando que truena, un `reanudar` fallido o un `exclusiones.json` rechazado ya no cuentan como tarea medida que
baja el porcentaje. El porcentaje de THE BOSS sale solo de la ronda, y el de RADAR solo de `verificar`, con «(de M
medidas; S sin medir)»; si no hay nada medido, dice «sin medir». Los rechazos se siguen contando igual. Con esto,
G2.2 queda resuelto.

### L2. Textos de bots que hay que volver a pegar en Grok Bot
- **`bots/THE_BOSS.md`** (arreglo 123): una línea más en «Lo más importante».
- Los demás bots no cambiaron. Como Ángelo todavía no pega ninguno, al arrancar se pegan los 6 completos.

### L3. Cifras
- **Pruebas en Windows (`.venv`, pytest completo):** 855 pasan y 1 saltada en `818abad` → 860 en `1cf347e` (122) →
  861 en `fe3aa8c` (123), `e4801fd` (124) y este commit. La saltada sigue siendo la de enlaces simbólicos de
  `tests/test_arreglo43_respaldo.py`.
- **Pruebas en Linux (GitHub):** 861 en `1cf347e` y 862 en `fe3aa8c`, 0 saltadas. Esa es la cifra de `CLAUDE.md`.
- **Cobertura del paquete:** 89.73 % en Windows (7441 sentencias, 764 sin cubrir) y 89.72 % en Linux (7441, 765) en
  cada commit. No bajó del 89.7 % pedido.

### L4. Pendiente: DECISIÓN DE ÁNGELO (no hice nada de esto; nada cambió en esta tanda)
- `reglamento.yaml`, sección reportes: `hora_diario` "18:30" y `lineas_max_resumen` 10 (se decide aparte).
- Mover `backtest.fin` para medir con velas más nuevas (es reglamento), y lo demás de K9.
- K5: verificar los stops de Futuros por `algoOrder` contra la documentación oficial de Binance antes de operar
  Futuros de verdad.
- A, E3, D4.2, H3.2, H3.3, R23/N11 y R53/R89/R90 siguen igual.

## M. Tanda del 16 y 17 de noviembre de 2026 (arreglos 139–142): dinero real en Spot

Rama `codex/marea-v2`, desde `6ecb2c2` (los arreglos 126 a 138 ya estaban). Orden de los commits: 142, 139, 140 y 141.
El 142 fue primero porque en Linux la prueba de oro fallaba por 1 ULP y sin él ningún pytest completo pasaba antes de
subir. El 140 es el último de los de código, como estaba previsto. El programa **nunca** tiene llaves de Binance ni
firma órdenes: solo lee datos públicos, emite boletos y lee los archivos que EJECUTOR escribe con lo que contestó
Binance por el conector. Cada arreglo es un commit con pytest completo pasando y su push, y la prueba que falla va
antes del cambio. En el 141 escribí los dos textos de bots antes que su prueba, pero la prueba demuestra que la
revisión falla si falta una frase.

### M1. DECISIONES DE ÁNGELO (15 nov 2026; las tomó él y no se reabren)
1. Empieza con dinero real YA en Spot, con el saldo real de 142.54 USDT libres y sin posiciones. Futuros no se usa (saldo ≈ 0).
2. Se salta las compuertas de papel (30 días y 30 operaciones, `reglamento.yaml:284-285`, y el texto de «6 semanas y 10
   operaciones» de `bots/THE_BOSS.md` y `bots/MIGRACION.md`). Es decisión suya, no del sistema; queda escrito en el
   comentario de M0 en el reglamento (arreglo 140), en CAMBIOS.md y aquí. Tampoco se pasaron las compuertas históricas
   (VALIDACION_V2.md: 65.6 % contra 90 % del azar; caída p95 59.8 % contra 25 %).
3. En real valen solo las reglas de la Cartera A; B y C quedan solo en papel.
4. La compra real es FOK: se llena al instante o no se compra ese día (no queda ninguna orden LIMIT colgada).
5. Venta de emergencia a mercado si falta el stop de una posición, o si el stop se activó y no se llenó.
6. El stop real se queda como STOP_LOSS_LIMIT (el mismo del papel); NO se cambia a STOP_LOSS.
7. El papel sigue corriendo en paralelo, con el mismo capital y la misma fecha de arranque, solo para comparar.

El reglamento dice que las reglas solo se cambian en domingo (`control_cambios.dia_ventana`; ningún código lo obliga).
Ángelo confirmó abrir el lunes 16 nov, a mitad de semana, al pegar el texto de esta tanda.

### M2. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 142 | `a32e9e6` | La prueba de oro del papel (arreglo 133) ya no falla por 1 ULP: el capital de la Cartera C el 2023-03-25 y el 2023-04-11 difería en el último bit (1081.303914159338 contra 1081.3039141593383). `tests/oro_papel_escenario.py` tiene `diferencias()`: todo se compara exacto salvo los números (rel 1e-12, abs 1e-9). Los boletos se siguen comparando al bit; una diferencia de 0.01 USDT sigue fallando. No cambió el archivo oro, ni las velas, ni el escenario, ni `sobreviviente/`. |
| 139 | `bebe81f` | `registrar-saldo`, `conciliar --real`, `ronda --verificar --real`, `registrar-llenado --real`, `ajustar-capital-real` y `reporte diario --real` se anotan en `datos/bots/registro.jsonl` como tareas del bot que corresponde, «sin medir». `ronda --modo real` tiene su propia fila, medida igual que la de papel. La simulación no escribe nada. |
| 140 | `0c003ba` | `reglamento.yaml`: M0 pasa de PAPEL a VIVA_MINI con el comentario de la decisión, se agrega el bloque `real:` (`decision_angelo`, `cartera` "A", `foto_max_minutos` 120, `margen_minimos_pct` 5, `no_comprar_cerca_del_stop_pct` 2) y la versión sube a 2.0.2. Nada más cambia (la prueba lo compara contra `6ecb2c2`). Compuerta nueva: `real.cartera` debe ser "A". El papel da lo mismo con M0 en VIVA_MINI. Hay una prueba que falla si aparecen llaves, firmas u órdenes en `sobreviviente/`. El apartado (d), el mensaje de bloqueo, ya estaba hecho en el 133 y no se tocó. |
| 141 | este commit | `bots/4_EJECUTOR_REAL.md` y `bots/5_CONTADOR_REAL.md`: el contenido pegado por Ángelo, con las mismas palabras. Solo devolví los saltos de línea que el chat había aplastado, como «3. Revisa…» y los incisos «- Si NO se llenó…». THE_BOSS.md: sección «Modo real» y la línea de «Hoy todo es PAPEL», que ahora dice papel y real. También se actualizaron INSTALACION.md (sección «Dinero real»), CLAUDE.md (cifra y línea del papel), las aserciones de `test_arreglo102` y `test_arreglo116`, y esta sección. |

### M3. Riesgos y qué arreglo cierra cada uno
La lista R1–R11 solo aparece en los títulos de los commits 129–138, no en un archivo. Aquí va lo que dicen esos
commits; R7 y R10 no aparecen en ninguno y no los invento.
- **R1, una posición real sin stop:** 135 (cierre urgente SIN_STOP y STOP_SIN_LLENAR, que se emite aunque haya MODO SEGURO o pausa) y 137 (nada pasa la noche sin stop; las compras quedan bloqueadas hasta que Ángelo diga). El 141 agrega en el texto del EJECUTOR la venta a mercado si el stop no queda puesto.
- **R2 y R11, el estado real:** 129. Va en `datos/real/` aparte del papel, ignorado por git, y con falla cerrada: nunca usa la copia `.bak`, que podría no traer la última compra.
- **R3, copiar mal un boleto o ponerlo dos veces:** 132 (formato del boleto real y su revisión) y 136 (`ronda --verificar --real`, «YA REGISTRADO» y `registrar-llenado --real`). El 141 agrega que el EJECUTOR revise con `spot.getOrder` por `origClientOrderId` antes de comprar.
- **R4, que las cuentas reales no cuadren:** 131 (`conciliar --real`, con «SIN STOP» en la primera línea, y `ajustar-capital-real`, solo de Ángelo).
- **R5, un solo bloqueo que no decía qué faltaba:** 133. El 140 abre la puerta y agrega la compuerta de `real.cartera`.
- **R6, R8 y R9, rechazos de Binance y mínimos:** 132 (compra FOK, PERCENT_PRICE_BY_SIDE, mínimos con 5 % de margen). R9 también en el 135 (stop activado y sin llenar).
- **Llaves o firmas en el programa:** 140 (prueba nueva), además de `tests/test_sin_llaves.py` (arreglo 21).
- **B o C en real, Futuros encendido o M0 en PAPEL:** 133 y 140 (la ronda real se niega y dice qué falta).
- **Calificación de los bots inflada por comandos reales sin horario:** 139.
- **Prueba de oro que falla por 1 ULP:** 142.
- **Abiertos (ningún arreglo los cierra):**
  - M0 no pasó las compuertas históricas; es decisión de Ángelo.
  - Se puede perder dinero real hasta el stop de catástrofe (15 %) y los frenos de la Cartera A.
  - Con STOP_LOSS_LIMIT (decisión 6), un hueco de precio más abajo del límite deja el stop sin llenar hasta la ronda siguiente, que emite el cierre urgente (135).
  - Los permisos de la llave del conector (solo Spot, sin retiros ni Futuros) los revisa Ángelo en Binance.
  - No corrí nada en Windows: las cifras de Windows de abajo salen de la regla de siempre (Linux − 1, más 1 saltada).

### M4. Pendiente: DECISIÓN DE ÁNGELO (no hice nada de esto)
- Quitar la Cartera C o cambiar su riesgo; poner B o C en real.
- Cambiar el % de riesgo, los topes, los frenos, los stops o las salidas; pasar de STOP_LOSS_LIMIT a STOP_LOSS.
- `reglamento.yaml`, sección reportes: `hora_diario` "18:30" y `lineas_max_resumen` 10; mover `backtest.fin`.
- K5 (stops de Futuros por `algoOrder`) y todo lo de Futuros.
- A, E3, D4.2, H3.2, H3.3, R23/N11 y R53/R89/R90 siguen igual.
- Subir el capital real (escalones, `reglamento.yaml:286-288`).

### M5. Textos de bots que hay que pegar en Grok Bot
- **Nuevos:** `bots/4_EJECUTOR_REAL.md` y `bots/5_CONTADOR_REAL.md`. Los de papel (`4_EJECUTOR.md` y `5_CONTADOR.md`) se quedan para el papel en paralelo.
- **Cambiado:** `bots/THE_BOSS.md` (sección «Modo real» y la línea de papel y real).

### M6. Cifras (Linux, esta máquina; pytest completo con `--cov=sobreviviente`)
- `6ecb2c2`: 979 pasan y 1 falla (la prueba de oro, por 1 ULP); cobertura 90.79 %.
- `a32e9e6` (142): 985 pasan; 90.79 %. `bebe81f` (139): 990; 90.82 %. `0c003ba` (140): 1000; 90.82 %.
- 141: 1011 pasan, 0 saltadas; 90.82 % (el 141 no toca código). En Windows deberían ser 1010 más 1 saltada (la de enlaces simbólicos de `tests/test_arreglo43_respaldo.py`). No bajó del 89.7 % pedido.

### M7. Qué sigue, en tu PC, en este orden y fuera de la hora de la ronda
1. `.venv\Scripts\python.exe -m sobreviviente reiniciar-papel --si`, una sola vez.
2. Revisar en Binance los permisos de la llave del conector: solo Spot, sin retiros ni Futuros.
3. Pegar los textos nuevos `4_EJECUTOR_REAL.md`, `5_CONTADOR_REAL.md` y `THE_BOSS.md`.
4. Un día de prueba con `.venv\Scripts\python.exe -m sobreviviente ronda --modo real --simular`, sin poner nada.
5. La primera ronda real, solo cuando la prueba salga sin ❌.

No hay ninguna garantía de ganancia. El objetivo de esta tanda es que el dinero real no pueda quedar sin stop ni
comprarse dos veces.

## N. Tanda Futuros F1 v2 (143–153)

Rama `codex/marea-v2`, desde `299181b` (1011 pruebas; cobertura del paquete 90.82 %). F1 es **SOLO PAPEL**: no hay
llaves, ni rutas firmadas, ni órdenes, ni boletos para EJECUTOR; solo GET públicos (klines, markPriceKlines,
fundingRate, premiumIndex, fundingInfo, exchangeInfo, ticker/24hr y data.binance.vision). Nada de Spot se tocó
(real.py, ronda_real.py, cli_real.py, papel.py, cli_ronda.py, datos/real/, datos/papel/, los textos del real ni los
bloques carteras/real/estrategias/riesgo del reglamento; E5 sigue APAGADA). F1 vive en `sobreviviente/futuros/`,
`sobreviviente/estrategias/f1.py` (fuera de ESTRATEGIAS) y, desde el 152, en el bloque propio `futuros_papel:`. El plan
de cada arreglo está en `docs/PLAN_TANDA_F1.md`, escrito antes del código.

### N1. Decisiones
**DECISIÓN DE ÁNGELO 2026-11-16 (límites duros):** todo es papel (el real de Futuros no existe); nada de Spot se toca;
apalancamiento 1x por defecto y 2x como máximo (K5); margen siempre AISLADO; siempre hay stop; siempre hay frenos
diario (3 %), semanal (6 %) y desde el pico (15 %); reparto del dinero de papel 100 a Spot y 42.54 a F1; el 152 va el
domingo 22 nov 2026.

**MECÁNICO por delegación de Ángelo 2026-11-16 (lo puede cambiar Ángelo):** capital_papel de F1 42.54 USDT con estado
propio `datos/papel_futuros/F.json`; monedas SOLUSDT, XRPUSDT, BNBUSDT y DOGEUSDT (lista fija; BTC solo filtro de
régimen); riesgo 1.0 % (0.43 USDT); velas de 4 h; stop 2.5 × ATR14 entre 1.5 % y 8 %; 2 posiciones (1 por moneda) y
calor 2 %; margen 30 % por posición y 60 % en total; 1x si el valor cabe en 12.76 USDT, si no 2x; 4 pérdidas seguidas
= 24 h de pausa; funding extremo 0.05 % cada 8 h; volatilidad EXTREMA sin entradas y SIN mitad de riesgo con ALTA.

**El papel de Spot sigue en 142.54** (A, B y C). Bajarlo a 100 cambiando `carteras.capital_inicial`
(`reglamento.yaml:303`) tocaría el REAL, porque ese valor lo usan `real.py:89` y `real.py:458` (capital inicial del real)
y `ronda_real.py:184-186` (bloquea compras reales si el saldo de Binance, 142.54, no coincide). Por eso el reparto
100/42.54 es una cuenta aparte: F1 simula 42.54 y el papel de Spot no cambia. Si Ángelo quiere el papel de Spot en
100 hace falta OTRA tanda de Spot (clave nueva solo para papel, `papel.py:79`, `papel.py:860`, `cli_ronda.py:662-700`
y reiniciar-papel), en domingo.

### N2. Números que sostienen las decisiones (Binance Futuros, 16 nov 2026, 7:07 p. m. CDMX)
| Moneda | Precio de marca | Paso | Mínimo real | Volumen 24 h | Tarifa de liquidación | Stop 2.5×ATR 4 h (mediana / p90) | Costo base / estrés (% de R) |
|---|---|---|---|---|---|---|---|
| SOLUSDT | 71.63 | 0.01 | 5 USDT | 1,531 M | 1.5 % | 5.55 % / 8.51 % | 4 % / 8 % |
| XRPUSDT | 0.9547 | 0.1 | 5 USDT | 657 M | 1.25 % | 5.05 % / 9.38 % | 5 % / 9 % |
| BNBUSDT | 591.45 | 0.01 | 5.91 USDT | 248 M | 1.25 % | 3.38 % / 6.00 % | 7 % / 13 % |
| DOGEUSDT | 0.05885 | 1 | 5 USDT | 296 M | 1.5 % | 6.00 % / 9.76 % | 4 % / 7 % |
| ETHUSDT (no opera) | 1,817.76 | 0.001 | 20 USDT | 7,500 M | 1.25 % | 4.80 % / 7.50 % | 5 % / 9 % |
| BTCUSDT (no opera) | 64,674.80 | 0.001 | 64.67 USDT | 11,799 M | 1.25 % | 3.01 % / 4.85 % | 8 % / 15 % |

Con 42.54 y 1 % caben SOL 100 %, XRP 100 %, BNB 98 %, DOGE 100 %, ETH 0 % y BTC 0 % de las velas de 4 h (con 0.75 %:
79/81/87/71 %). Costo base 0.24 % ida y vuelta, con estrés 0.44 %. Con velas de 1 h el costo pesa 13–26 % de R: por eso 4 h.
Correlación con BTC 0.80–0.87: por eso el calor total es 2 %. Rachas (Monte Carlo, 40 % de aciertos): típica 7, p95 12.

### N3. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 143 | `6d6a690` | Hipótesis 003 en HIPOTESIS.md (9 ideas solo en el texto); `futuros/__init__.py` (SOLO_PAPEL), `futuros/config.py` (POR_DEFECTO, ORIGEN, leer/validar); guardián «sin órdenes» y sin cruces con Spot. |
| 144 | `ad6b47b` | `futuros/liquidacion.py` con la fórmula oficial y cambio de escalón; `escalones.json`. riesgo.py igual. |
| 145 | `c1f0381` | `futuros/datos_publicos.py` con lista blanca; «Futuros no disponible» con 451/403; datos de más de 48 h = sin entradas. |
| 146 | `4dcfd69` | `estrategias/f1.py` (función pura) y el modo `chandelier_senal` en gestion.py. |
| 147 | `75eadd5` | `futuros/tamano.py`: tamaño por riesgo, 1x/2x, márgenes y colchón de liquidación. |
| 148 | `c0b0381` | `backtest.simular_operacion`: `precio_liq` y `tarifa_liq_pct` (con None, todo igual). |
| 149 | `e0906bd` | `futuros/cartera.py`: Cartera F, frenos con copia del reglamento, vetos, calor, rachas, gestión. |
| 150 | `2cbcbb7` | Comando `futuros-papel` (modo muestra con activo: false). |
| 151 | `e87c2f5` | Comando `validar-futuros` y VALIDACION_FUTUROS.md. |
| 153 | este commit | Esta sección, CLAUDE.md, una línea en THE_BOSS.md y el resultado en HIPOTESIS.md. |
| 154 | este commit | Revisión de F1: `datos/papel_futuros/` en .gitignore (en el bloque de `datos/papel/`, `datos/estela/` y `datos/bots/`, antes de `datos/real/`): el estado de papel de F1 no entra al repositorio. |
| 155 | este commit | Revisión de F1: liquidación y tamaño con la ENTRADA REAL (apertura siguiente ± deslizamiento, `backtest.precio_entrada`), no con el cierre de la señal. `validar-futuros`: `candidatos` y `simular_cartera` (el riesgo real nunca pasa del pedido; si ya no cabe, no se cuenta). `futuros-papel`: al abrir se vuelve a calcular el tamaño con la entrada; si ya no cabe, no abre (`abre: false` y un aviso). `simular_operacion` no cambió. |
| 152 | ver sección T | HECHO en la ventana del **domingo 22 nov 2026**: bloque `futuros_papel:` igual a `config.POR_DEFECTO`, `activo: false` (sección T1). |

### N4. Resultado de `validar-futuros` (tal cual, 17 nov 2026)
**Veredicto: F1 NO PASA.** Se queda con `activo: false`; es un resultado válido. Nada de esto promete ganancias.

**Pendiente tras el 155:** estas cifras son de antes del 155 (la liquidación y el tamaño salían del cierre de la señal). Hay que volver a correr `validar-futuros` para regenerar VALIDACION_FUTUROS.md con la entrada real; el veredicto puede cambiar en cualquier dirección. Mientras tanto F1 sigue con `activo: false`.

| Compuerta | ¿Pasa? | Detalle |
|---|---|---|
| operaciones | ✅ | 126 operaciones fuera de muestra, sumando las 4 monedas (mínimo 100) |
| factor_ganancia | ❌ | factor de ganancia 0.93 (mínimo 1.3) |
| expectativa | ❌ | expectativa -0.034R después de costos (mínimo +0.10R) |
| ventanas | ❌ | 31 % de ventanas positivas (mínimo 60 %) |
| caida_p95 | ❌ | caída p95 34.0 % con 1 % de riesgo, la peor entre Monte Carlo suelto y por bloques (máximo 25 %) |
| azar | ❌ | le gana al 52.4 % de las entradas al azar (mínimo 98.9 %) |
| robustez | ❌ | robustez ±20 %: peor expectativa -0.070R (todas deben ser > 0) |
| liquidaciones | ✅ | 0 liquidaciones (deben ser CERO) |
| estres | ❌ | con estrés de costos (comisión 0.075 %, deslizamiento ×2, funding ×2): -0.071R (mínimo +0.05R) |
| largo_y_corto | ❌ | largo solo +0.114R (86 ops) y corto solo -0.353R (40 ops); los dos > 0R |
| concentracion | ❌ | la moneda que más aporta da nan % de la R total (máximo 50 %; sin R total positiva no se puede repartir) |
| sin_una_moneda | ❌ | quitando cualquier moneda, la peor expectativa es -0.163R (mínimo +0.05R) |
| no_caben | ✅ | con 42.54 USDT, 8 de 123 señales «no caben» (6.5 %; máximo 20 %) |

Detalle completo (lados, monedas, ventanas, robustez, Cartera F con 42.54) en `VALIDACION_FUTUROS.md`. Lo que más
pesa: los cortos (−0.353R en 40) y la expectativa total negativa; solo SOLUSDT dio expectativa positiva.

### N5. Pendientes y supuestos (DECISIÓN DE ÁNGELO o MECÁNICO)
- **Arreglo 152, domingo 22 nov 2026:** bloque `futuros_papel:` en reglamento.yaml (igual a `config.POR_DEFECTO`),
  versión y CAMBIOS.md, y las reglas nuevas de `reglamento.validar`. Con F1 NO PASA, `activo` queda en false.
- **Tablas de escalones: YA HECHO (Arreglo 164, DECISIÓN DE ÁNGELO del 2026-11-17).** MECÁNICO copió el 2026-11-17 las
  tablas completas de SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT y ETHUSDT de la página pública Leverage & Margin de Binance
  (https://www.binance.com/en/futures/trading-parameters/perpetual/leverage-margin), sin entrar a ninguna cuenta; cada
  «cum» cuadra con el escalón anterior. Quedan con `verificado: true` y su fuente en `escalones.json` (commit «Arreglo
  164: escalones reales de Binance en escalones.json»). BTCUSDT sigue con el escalón 1 de Ángelo (MMR 0.40 %, cum 0) y
  la tarifa de liquidación sigue igual (esa página no la trae). El endpoint leverageBracket sigue sin usarse (firmado).
  Escalón 1 de las monedas de F1: SOL 0.50 % hasta 50,000; XRP 0.50 % hasta 40,000; BNB 0.50 % hasta 10,000; DOGE
  0.65 % hasta 80,000. La posición más grande de F1 (25.52 USDT) cae en el escalón 1 de todas.
  **Hay que volver a revisar las tablas una vez al mes, o antes de usar futuros con dinero real** (Binance las cambia).
  Verificar escalones no activa nada: `activo` sigue en false y F1 sigue en NO PASA por sus otras compuertas.
- **exchangeInfo de Futuros** responde 451 desde la sesión: la validación usó los pasos y mínimos del 16 nov 2026 (la
  tabla de N2) y su tarifa de liquidación. `futuros-papel` en la computadora de Grok Bot usará el exchangeInfo vivo.
- **Interpretación:** «el régimen se voltea» = la marea o la tendencia pasan al lado CONTRARIO (un largo sale con
  BAJISTA, no con LATERAL). Si Ángelo quiere salir también con LATERAL, es otra hipótesis.
- `futuros-papel` con `activo: true` solo simula si VALIDACION_FUTUROS.md dice «PASA» (salvaguarda extra).
- Pruebas: 1011 → 1118 en Linux (1117 más 1 saltada en Windows). Cobertura del paquete: 90.82 % → 92.12 %.
- No corrí nada en Windows: la cifra de Windows sale de la regla de siempre (Linux − 1, más 1 saltada).

## O. Tanda F1 variantes (156–163)

Rama `codex/marea-v2`, desde `5619f84` (1127 pruebas en Linux; cobertura del paquete 92.12 %). SOLO PAPEL: sin llaves,
sin rutas firmadas, sin órdenes, solo GET públicos. Nada de Spot ni de reglamento.yaml se tocó. El plan de cada arreglo
está en `docs/PLAN_TANDA_F1_VARIANTES.md`, escrito antes del código. El 152 sigue para el domingo 22 nov 2026.

### O1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 156 | `34840d8` | Hipótesis 004 en HIPOTESIS.md (antes de medir); `futuros/variantes.py` (4 variantes fijas, 4 pruebas, 12 ideas, azar ≥ 99.17 %, t ≥ 2.2414); registro solo-agregar `VARIANTES_FUTUROS.md`. |
| 157 | `fd626b7` | La liquidación no se cuenta dos veces: pérdida = min(margen, pérdida hasta la liquidación + tarifa) en `backtest.simular_operacion` (rama `precio_liq`) y `futuros/cartera.cerrar` (fuente: Binance, «Liquidation Protocols», https://www.binance.com/en/support/faq/binance-futures-liquidation-protocols-360033525271). Cambian A PROPÓSITO 3 aserciones de la pérdida en test_arreglo148 (2) y test_arreglo149 (1). Con 0 liquidaciones el resultado de F1 no cambia. |
| 158 | `23cba90` | Los costos entran al riesgo: `tamano.calcular(..., costos)` con distancia efectiva = stop + 2 × (comisión 0.05 % + deslizamiento 0.05 %) + 3 cobros de funding en contra; `riesgo_usdt` con costos; `costos=None` = como antes (147 igual). `cartera.cabe`, `futuros-papel` y `validar-futuros` pasan los costos (funding de 8 h de la vela de la señal). Un renglón de formato viejo en `simular_cartera` (sin `funding_8h_pct`, como los que no traen `entrada`) se dimensiona como antes: así la prueba vieja del 155 no cambia (revisar si Ángelo prefiere otra cosa). |
| 159 | después de la tanda | Entró el 17 nov 2026 por DECISIÓN DE ÁNGELO (ver O3): `config.leer` se niega con `activo: true` y escalones sin verificar; `futuros-papel` se queda en modo muestra con el aviso y sale 0. |
| 160 | `a6e39d4` | Variantes en la señal (`f1.senales(ctx, p, variante)`: F1-L sin cortos; F1-LC cortos solo con BTC < SMA200 y SMA200 < la de 20 días antes, al cierre diario ya conocido, `f1.bajista_fuerte_diario` en `armar_contexto`) y la salida por tiempo de F1-LT (`gestion.salida_por_tiempo`, sin tocar `vela`; en `backtest.simular_operacion` y `cartera.procesar_vela`, apagada por defecto). F1 base: misma huella que en 5619f84. |
| 161 | `1e0e7ef` | `validar-futuros --variante {F1,F1-L,F1-LC,F1-LT}` (por defecto F1): mismas 13 compuertas con azar ≥ 99.17 %, «largo» en vez de «largo y corto» en F1-L/F1-LT (el corto se reporta), y dos nuevas: «significancia» (t ≥ 2.2414) y «escalones» (hoy falla a propósito). Veredicto PASA / PASA SIN ESCALONES VERIFICADOS → no se puede activar / NO PASA. Escribe VALIDACION_FUTUROS_<variante>.md (F1 también VALIDACION_FUTUROS.md) y un renglón en VARIANTES_FUTUROS.md. `liquidacion.sin_verificar` y `todas_verificadas` (venían en el 159). En variantes solo de largos, las entradas al azar también son solo largos. `evaluar` sin variante = el 151 tal cual. |
| 162 | `3b36f23` | Holdout de monedas sellado: `variantes.MONEDAS_HOLDOUT` (4 monedas declaradas en la Hipótesis 004, el único lugar del código que las nombra), `RESPALDO_HOLDOUT` (pasos, tarifa 1.5 % y escalón MMR 1 %: supuestos conservadores sin verificar) y `puede_holdout`. `validar-futuros --variante X --holdout`: se niega sin el pase previo (15 compuertas sin contar escalones en su renglón más reciente) y la segunda vez; mismas ventanas, reglas y liquidez; PASA con ≥ 30 operaciones y expectativa ≥ 0R normal y con estrés; con menos de 30, SIN VEREDICTO. Escribe VALIDACION_FUTUROS_<variante>_holdout.md y el renglón «holdout». |
| 163 | este commit | Esta sección, la cifra de pruebas en CLAUDE.md (contada con `pytest --collect-only -q` dentro de la prueba), el resultado de la Hipótesis 004 y los informes de las 4 corridas. |
| 152 | — | PENDIENTE: va el **domingo 22 nov 2026**, separado y sin cambios. No es de esta tanda. |

Pruebas: 1127 → 1185 en Linux (1184 más 1 saltada en Windows); la tanda suma 58. Cobertura del paquete: 92.12 % →
92.26 %; ningún commit bajó la cifra del anterior. No corrí nada en Windows: la cifra de Windows sale de la regla de
siempre (Linux − 1, más la saltada de enlaces simbólicos).

### O2. Resultado de las 4 corridas (commit `3b36f23`, una sola vez cada una, 17 nov 2026)
Barras por **4 pruebas** en la familia F1 (8 + 4 = 12 ideas): azar ≥ **99.17 %** y **t ≥ 2.24** (2.2414, Bonferroni
α = 0.05/4; Bailey y López de Prado, «The Deflated Sharpe Ratio»). Mismas ventanas walk-forward (2023-01 a 2026-04) y
mismas 4 monedas. Registro completo: `VARIANTES_FUTUROS.md`. **Ninguna variante pasa**, ni siquiera sin contar
«escalones»; por eso **no se abrió ningún holdout** (las 4 monedas del holdout siguen selladas). Es un resultado válido.
Nada de esto promete ganancias.

| Variante | Veredicto | Compuertas | Ops | Expectativa | Factor | t | Azar | Estrés | Caída p95 | Largo | Corto |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F1 (`VALIDACION_FUTUROS_F1.md`) | NO PASA | 3/15 | 126 | −0.034R | 0.93 | −0.27 | 52.4 % | −0.071R | 34.0 % | +0.114R (86) | −0.353R (40) |
| F1-L (`VALIDACION_FUTUROS_F1-L.md`) | NO PASA | 7/15 | 86 | +0.114R | 1.27 | 0.64 | 94.7 % | +0.076R | 19.3 % | +0.114R (86) | — |
| F1-LC (`VALIDACION_FUTUROS_F1-LC.md`) | NO PASA | 3/15 | 110 | +0.008R | 1.02 | 0.06 | 73.9 % | −0.030R | 30.1 % | +0.114R (86) | −0.370R (24) |
| F1-LT (`VALIDACION_FUTUROS_F1-LT.md`) | NO PASA | 7/15 | 86 | +0.123R | 1.29 | 0.69 | 96.1 % | +0.085R | 18.9 % | +0.123R (86) | — |

Por moneda (expectativa y operaciones):

| Variante | SOLUSDT | XRPUSDT | BNBUSDT | DOGEUSDT |
|---|---|---|---|---|
| F1 | +0.129R (37) | −0.113R (26) | −0.020R (34) | −0.190R (29) |
| F1-L | +0.192R (31) | +0.148R (13) | +0.108R (27) | −0.068R (15) |
| F1-LC | +0.169R (35) | −0.120R (22) | +0.035R (29) | −0.142R (24) |
| F1-LT | +0.192R (31) | +0.207R (13) | +0.108R (27) | −0.068R (15) |

- **F1** reproduce las cifras de Ángelo (126 operaciones, −0.034R, 0.93, 52.4 %); con la barra nueva el azar pide
  99.17 %. Solo «no caben» cambia: 9 de 123 (7.3 %) en vez de 8 (el tamaño ahora cuenta los costos, Arreglo 158).
- **F1-L** y **F1-LT** pasan expectativa, caída p95, robustez, liquidaciones, estrés, «largo» y «no caben» (7 de 15).
  Fallan: 86 operaciones (< 100), factor 1.27 / 1.29 (< 1.3), 31 % de ventanas positivas, azar 94.7 % / 96.1 %
  (< 99.17 %), concentración (SOLUSDT da 61 % / 56 % de la R), sin una moneda (−0.007R / +0.006R, quitando SOLUSDT),
  significancia (t 0.64 / 0.69, lejos de 2.24) y escalones. La salida por tiempo casi no cambia nada (+0.009R).
- **F1-LC**: pedir «bajista fuerte» quita 16 de los 40 cortos, pero los que quedan pierden igual (−0.370R en 24).
- Cuidado al leer F1-L: se eligió DESPUÉS de ver que el corto perdía; por eso cuenta en la barra de 4 pruebas, y aun
  así no la pasa. La prueba limpia en el tiempo es el papel desde el 2026-11-01.

### O3. Arreglo 159: escalones sin verificar bloquean la activación (DECISIÓN DE ÁNGELO 2026-11-17, hecho)
Estaba DETENIDO porque chocaba con pruebas viejas que corren `futuros-papel` con `activo: true` y el `escalones.json`
real (verificado: false en SOL, XRP, BNB y DOGE). **DECISIÓN DE ÁNGELO del 2026-11-17:** terminarlo, y que esas pruebas
usen un fixture de escalones VERIFICADOS (`apoyo_futuros.escalones_verificados`, que reemplaza `liquidacion._tabla`
como test_arreglo161) sin cambiar ninguna aserción. Son 6: `test_arreglo150::test_activo_sin_validacion_que_pase_se_queda_en_muestra`,
`::test_activo_y_validado_guarda_su_estado_y_procesa_en_orden`, `::test_estado_danado_no_corre`,
`::test_activo_y_validado_abre_en_la_apertura_siguiente`, y en test_arreglo155 el fixture `activo` (lo usan
`test_futuros_papel_guarda_la_liquidacion_de_su_entrada` y `test_futuros_papel_no_abre_si_con_la_entrada_real_ya_no_cabe`).
`escalones.json` NO se tocó.

Qué hace (commit «Arreglo 159: escalones sin verificar bloquean la activación»):
- `config.leer(reg)` lanza `ErrorConfigFuturos` («escalones sin verificar: …») si `activo: true` y alguna moneda de F1
  sigue sin verificar (reúsa `liquidacion.sin_verificar`). Con `activo: false` (hoy) no cambia nada.
- `futuros-papel` lee con `exigir_activacion=False` y niega la activación él mismo: modo muestra, aviso
  «escalones sin verificar: <monedas>», no guarda `datos/papel_futuros/F.json`, sale 0. Primero escalones, después el
  «PASA»; con escalones verificados vale la regla de siempre. Otros límites duros (tope 2x, margen cruzado…) siguen
  saliendo con 1.
- `validar-futuros` también lee con `exigir_activacion=False`: solo mide y ya tiene su compuerta «escalones» (161).
- Nada pone `activo: true`; el bloque `futuros_papel` sigue sin existir (152, domingo 22 nov). Activar sigue siendo
  DECISIÓN DE ÁNGELO y exige este 159, un informe que diga PASA y el 152.

Pruebas: 1185 → 1196 en Linux (1195 más 1 saltada en Windows; no corrí nada en Windows).

Después, el **Arreglo 164** (escalones reales, ver N5) pasó al fixture `apoyo_futuros.escalones_sin_verificar` las
pruebas que asumían «hoy sin verificar» (test_arreglo144::test_errores_y_respaldos, test_arreglo161::corridas y
::test_escalones_verificados_cambian_esa_compuerta, y 4 del 159), y al fixture `escalones_supuesto_viejo` la de
test_arreglo157 que esperaba el supuesto de 1 %; ninguna aserción cambió. Pruebas: 1196 → 1205 en Linux.

### O4. Pendientes (TAREA DE ÁNGELO / DECISIÓN DE ÁNGELO)
- ~~**TAREA DE ÁNGELO — copiar los escalones**~~: hecho en el Arreglo 164 (DECISIÓN DE ÁNGELO del 2026-11-17; ver N5).
  Las tablas de SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT y ETHUSDT están copiadas con fecha y `verificado: true`.
- **Arreglo 152: domingo 22 nov 2026**, separado y sin cambios (bloque `futuros_papel` en reglamento.yaml). Al hacerlo,
  la cifra de pruebas de CLAUDE.md cambia y test_arreglo163 lo pide (cuenta las pruebas en vivo).
- **Ninguna variante se activa sin DECISIÓN DE ÁNGELO**, y además exige escalones verificados y el 152. Hoy ninguna pasa.
  Esta tanda no pone `activo: true` en ningún lado.
- **Para revisar (decisiones de MECÁNICO en esta tanda):** (1) en las variantes solo de largos, las entradas al azar
  también son solo largos (161); (2) un renglón de formato viejo en `simular_cartera` se dimensiona sin costos para no
  cambiar la prueba vieja del 155 (158); (3) los pasos, mínimos y tarifa del holdout son supuestos de memoria (162);
  (4) en el registro, el corto de F1-L y F1-LT sale como +0.000 cuando no hay cortos (el informe dice «sin cortos»).
- `futuros-papel` sigue con F1 base; las variantes solo se miden con `validar-futuros --variante`.

## P. Tanda de seguridad (165–168)

Rama `codex/marea-v2`, desde `26ccdfb` (1205 pruebas en Linux; cobertura del paquete 92.26 %). Sin llaves de Binance,
sin órdenes y sin dinero: todo se probó con clientes falsos y simulación. No se tocó `reglamento.yaml` (el 152 sigue
para el domingo 22 nov 2026), ni F1 (sigue `activo: false`), ni `riesgo.py`, ni ninguna regla de riesgo.

### P1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 165 | `157f95a` | El stop sale pegado a la compra (ver P2). El boleto real trae el stop LISTO para los dos casos de comisión (`orden_stop` si se cobra en BTC; `orden_stop_comision_otra_moneda`, por toda la compra, si se cobra en BNB u otra moneda) y el aviso `hueco_sin_stop`; `revisar_boleto_real` exige que la segunda sea el mismo stop por toda la compra. El texto del boleto y `bots/4_EJECUTOR_REAL.md` ponen el stop EN EL ACTO, antes de `registrar-llenado` (antes el EJECUTOR corría `registrar-llenado` entre la compra y el stop, y calculaba la cantidad). `registrar-llenado` avisa que la posición cuenta SIN STOP hasta STOP_PUESTO. |
| 166 | `bde9cee` | Saltar la ronda COMPLETA si Binance tiene problemas (ver P3). `papel.revisar_binance` y `papel.BinanceNoOpera`: `preparar_datos` lanza `BinanceNoOpera` si exchangeInfo falla, viene raro o BTCUSDT no está en TRADING, y deja el motivo en `DatosDia.no_opera` si Binance no contestó y se usó la copia guardada. `correr_ronda` y `ronda_real.correr` no escriben nada (ni carteras, ni estado real, ni conciliación, ni boletos), salen con 1 y el mensaje para THE BOSS, y se pueden repetir. En real, además, las posiciones sin stop confirmado salen como URGENTE (estado local, sin red). |
| 167 | `54dab45` | El papel falla cerrado si falta la conciliación (ver P4). `papel.estado_conciliacion(reg, dia)` → (ok, "" / "falta" / "no cuadró"); `conciliacion_ok` sigue dando bool. Sin `datos/papel/conciliacion.json` da False, salvo el primer día después de `reiniciar-papel` (ninguna cartera con una ronda de un día anterior). Mensaje: «Falta la conciliación del papel … CONTADOR: corre … conciliar»; el resumen lo dice una vez y sin 👍. |
| 168 | este commit | Aviso de cartera de papel con capital viejo (ver P5): `papel.avisos_capital_viejo` compara el `capital_inicial` de cada `cartera_X.json` guardada con `carteras.capital_inicial` y avisa con ⚠️ en la ronda (informativos: sale en el resumen, en la bitácora y al repetirla) y en `doctor` (no cuenta como ❌). Solo avisa: no cambia ni borra nada. Además, CLAUDE.md y esta sección con las cifras finales. |

### P2. Arreglo 165: por qué NO se usan órdenes OTO (todavía)
Fuente: documentación oficial de Binance Spot, repositorio `binance/binance-spot-api-docs` (`rest-api.md`, «New Order
list - OTO (TRADE)», `POST /api/v3/orderList/oto`, y `filters.md`), leída el 17 nov 2026.
- **Binance sí lo permite y encaja con nuestros filtros.** Una OTO es una lista de 2 órdenes: la de trabajo (LIMIT o
  LIMIT_MAKER, con `workingTimeInForce`, así que FOK cabe) y la pendiente (cualquier tipo salvo MARKET con
  `quoteOrderQty`; STOP_LOSS_LIMIT pide `pendingPrice`, `pendingStopPrice` y `pendingTimeInForce`). La pendiente solo
  entra al libro cuando la de trabajo se llena COMPLETA (con FOK es todo o nada). PERCENT_PRICE_BY_SIDE, LOT_SIZE y
  NOTIONAL son los mismos que ya revisa el boleto (`no_comprar_si` y `revisar_boleto_real`).
- **No se puede usar hoy porque el conector no la tiene.** El EJECUTOR solo puede usar `spot.getAccount`,
  `spot.getOpenOrders`, `spot.getOrder`, `spot.myTrades`, `spot.tickerPrice`, `spot.exchangeInfo`, `spot.newOrder` y
  `spot.deleteOrder`; no hay herramienta de orderList.
- **Además, OTO no cierra todo el hueco:** `pendingQuantity` se fija antes de saber la comisión (con BNB queda hasta un
  paso sin stop, como hoy); si la compra se llena al instante, Binance contesta el stop como `PENDING_NEW` y hay que
  consultarlo para confirmarlo; y la documentación no dice qué pasa si la pendiente falla al activarse, así que la regla
  de vender a mercado se queda igual.
- **Qué se hizo en su lugar:** el hueco más corto posible con dos órdenes (ver P1). La prueba
  `tests/test_arreglo165_stop_junto_a_la_compra.py` simula Binance (saldos, comisión en BTC o BNB, LOT_SIZE, NOTIONAL,
  PERCENT_PRICE_BY_SIDE): en 96 casos × 4 comisiones el stop elegido del boleto siempre lo acepta Binance si se respeta
  `no_comprar_si`, lo que queda sin stop es polvo (menos del mínimo de Binance), y en los 6 caminos del EJECUTOR (no se
  llena, stop puesto con comisión en BTC o en BNB, stop rechazado una vez, venta de emergencia, venta que también falla)
  ninguna posición queda sin stop y sin aviso: o tiene stop ACTIVO, o al día siguiente sale el cierre URGENTE con las
  compras bloqueadas.
- **DECISIÓN DE ÁNGELO:** si algún día el conector de Grok Bot trae `orderList/oto`, cambiar el boleto a una sola OTO
  (compra LIMIT FOK + STOP_LOSS_LIMIT pendiente) y agregar esa herramienta a la lista del EJECUTOR. Mientras tanto,
  quedan las dos órdenes.
- **Texto para volver a pegar en Grok Bot:** `bots/4_EJECUTOR_REAL.md` (cambió el paso 4).

### P3. Arreglo 166: la ronda se salta completa si Binance tiene problemas (DECISIÓN DE ÁNGELO del 17 nov 2026)
- Antes de operar se revisa en exchangeInfo que BTCUSDT esté en TRADING. Se salta la ronda (papel y real, igual) si
  exchangeInfo falla, si regresa algo raro (no es un objeto, sin lista de monedas, sin BTCUSDT), si BTCUSDT está en otro
  estado (HALT, BREAK, …) o si Binance no contestó y solo hay una copia guardada.
- Ángelo eligió «saltar completa» (no «sin compras, cierres sí»): no se escribe nada, sale con ❌ para THE BOSS y la
  ronda se puede repetir cuando Binance responda, dentro de la hora (después sale FUERA DE HORA y ya no compra). Los
  stops que ya están en Binance siguen igual. En real, las posiciones sin stop confirmado se dicen como URGENTE: vender
  sin boleto solo lo decide Ángelo.
- **Cambio de política a la vista:** con una copia guardada de exchangeInfo de menos de 48 h la ronda antes operaba
  (Arreglo 59); ahora se salta, porque la copia no dice cómo está BTCUSDT HOY. `ronda --verificar` y
  `ronda --verificar --real` no cambian (siguen usando la copia con ⚠️). `preparar_datos` con copia sigue igual
  (mismos avisos y el MODO SEGURO de 48 h): solo deja el motivo y la ronda la salta.
- Prueba: `tests/test_arreglo166_binance_no_opera.py` (8 casos en papel y 5 en real, con clientes falsos).

### P4. Arreglo 167: el papel falla cerrado si falta la conciliación
- Antes, sin `datos/papel/conciliacion.json`, `papel.conciliacion_ok` daba True. Ahora da False, igual que el real, salvo
  el primer día después de `reiniciar-papel`: mientras ninguna cartera tenga una ronda de un día ANTERIOR al que se
  procesa, no hay nada que conciliar. Se cuenta «anterior» porque A guarda la ronda de hoy antes de que corran B y C.
  Una cartera dañada o rara cuenta como que sí hubo rondas (falla cerrado). El caso «no cuadró» no cambia.
- En la práctica no estorba: el CONTADOR corre `conciliar` cada día a las 6:25 p. m. CDMX, después de la ronda.
- **Pruebas viejas a las que se les agregó la conciliación diaria** (corrían varios días de papel sin conciliar; ninguna
  aserción cambió): `tests/oro_papel_escenario.py` (corre `conciliar` entre ronda y ronda; la prueba de oro de
  test_arreglo133 y test_arreglo140 da exactamente lo mismo que la referencia e216bd5),
  `test_arreglo1_papel.py::test_saltada_por_capital_no_se_repite` (corre `conciliar` antes del día 2) y
  `test_arreglo64_tope_diario_ronda.py::test_el_dia_utc_siguiente_vuelven_las_compras` (su cartera se arma a mano con
  96 de 100 USDT sin operación cerrada, así que un `conciliar` real no cuadraría: se deja un `conciliacion.json` con
  ok:true, porque lo que prueba es el tope diario).
- **Para revisar (posible arreglo futuro, no se hizo):** una conciliación vieja con ok:true sigue contando aunque sea de
  hace semanas. Se podría pedir que sea posterior a la última ronda, como el real pide que sea de la foto vigente.

### P5. Arreglo 168: aviso de cartera de papel con capital viejo
- Si una cartera guardada tiene un `capital_inicial` distinto de `carteras.capital_inicial`, la ronda y `doctor` dicen,
  por ejemplo: «⚠️ Las carteras A, B y C de papel tienen capital viejo (46.18 USDT; el reglamento dice 142.54 USDT en
  carteras.capital_inicial). Si quieres empezar de nuevo, corre .venv\Scripts\python.exe -m sobreviviente
  reiniciar-papel --si (no borra nada: archiva datos/papel/).» Las carteras con la misma cifra van en una sola línea.
- Solo avisa: no cambia ni borra nada (la prueba compara los archivos byte por byte), no quita el 👍 y en `doctor` no
  cuenta como ❌. Un archivo dañado se salta (ya tiene su propio aviso). Empezar de nuevo sigue siendo DECISIÓN DE ÁNGELO.

### P6. Cifras y pendientes
- Pruebas: 1205 → 1256 en Linux (1255 más 1 saltada en Windows; no corrí nada en Windows): 165 suma 17, 166 suma 21,
  167 suma 8 y 168 suma 5. Cobertura del paquete: 92.26 % → 92.36 %; ningún commit bajó la cifra del anterior
  (92.26 → 92.27 → 92.32 → 92.34 → 92.36).
- **Textos para volver a pegar en Grok Bot:** `bots/4_EJECUTOR_REAL.md` (paso 4: el stop va en el acto, antes de
  `registrar-llenado`).
- **DECISIÓN DE ÁNGELO pendiente:** usar una sola orden OTO si algún día el conector trae `orderList/oto` (P2).
- **Arreglo 152: domingo 22 nov 2026**, separado y sin cambios. F1 sigue con `activo: false`. Nada de esto promete
  ganancias.

## Q. Tanda chiquita (169–171)

Rama `codex/marea-v2`, desde `3c0a2af` (1256 pruebas en Linux; cobertura del paquete 92.36 %). Sin llaves de Binance,
sin órdenes y sin dinero: todo se probó con archivos y clientes falsos. No se tocó `reglamento.yaml` (el 152 sigue para
el domingo 22 nov 2026), ni F1 (sigue `activo: false`), ni `riesgo.py`, ni ninguna regla de riesgo. No se abrió ninguna
ruta nueva de dinero real: lo nuevo solo bloquea, marca o avisa, y el código nunca vende solo.

### Q1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 169 | `1ce7e4c` | La conciliación del papel tiene que ser de hoy o de ayer (hora de CDMX) y decir ok (ver Q2). `papel.estado_conciliacion(reg, dia, ahora)` lee `.get("ok", False)`: sin "ok" (o con algo que no sea true) da «no dice ok»; con ok, la `fecha` que escribe `conciliar` (UTC) pasada a hora de CDMX tiene que ser de hoy o de ayer, o da «vieja» (también sin fecha, con fecha rara, sin zona horaria o del futuro). ok:false sigue siendo «no cuadró» y si falta el archivo todo sigue como en el 167 (con su excepción del primer día después de `reiniciar-papel`). `papel.aviso_conciliacion` dice qué falta y qué comando corre el CONTADOR; el resumen lo dice una vez («Falta la conciliación del papel … CONTADOR debe correr conciliar») y sin 👍. |
| 170 | `528052f` | Anotar la compra ANTES de mandarla (ver Q3). Evento nuevo `COMPRA_ENVIADA` en `registrar-llenado --real`: solo para un boleto COMPRAR, una vez y antes de COMPRA_LLENADA, COMPRA_PARCIAL o COMPRA_NO_LLENADA; no cambia posiciones y deja el boleto como «YA REGISTRADO» en `ronda --verificar --real`. `real.conciliar` (la de `conciliar --real` y la de la ronda real) marca SIN STOP, bloquea las compras (`bloqueo_compras`; solo Ángelo las reanuda) y da el aviso para THE BOSS (poner stop o vender; lo decide Ángelo) si encuentra un COMPRA_ENVIADA sin su resultado (aunque no haya foto) o BTC en una foto fresca que el estado real no conoce (`registrar_saldo` lo deja en `sin_estado`). No inventa posiciones ni boletos de venta. Una compra sin COMPRA_ENVIADA se anota igual, con aviso. Boleto real (`antes_de_comprar` y su texto), `bots/4_EJECUTOR_REAL.md` (paso 4c) y `bots/5_CONTADOR_REAL.md` (concilia después del 👍 del EJECUTOR). |
| 171 | este commit | Revisar justo después de cada compra real (ver Q4). `STOP_PUESTO` deja pendiente `revision_despues_de_compra` y dice qué correr EN SEGUIDA (foto de saldo nueva y `conciliar --real`). `real.conciliar` con una foto válida tomada DESPUÉS de la compra hace la revisión: si cuadra la borra; si no, `bloqueo_compras` («la revisión justo después de la compra (boleto …) no cuadró»): no se compra nada más hasta que Ángelo revise. Con una foto de ANTES de la compra no compara nada (❌, pide repetir la foto), para no marcar un SIN STOP falso. Si el EJECUTOR no revisa, la conciliación de la ronda siguiente es la revisión. `COMPRA_ENVIADA` sale ❌ «NO mandes la compra» con compras bloqueadas, cartera detenida, revisión pendiente o una posición sin stop ACTIVO. Boleto real (`despues_del_stop` y su texto) y `bots/4_EJECUTOR_REAL.md` (paso 4i; pasos 6 y 7). Además, CLAUDE.md y esta sección con las cifras finales. |

### Q2. Arreglo 169: la conciliación del papel tiene que ser de hoy o de ayer y decir ok
- Antes (`papel.py`, `.get("ok", True)`): un `conciliacion.json` sin "ok" contaba como bueno y un ok viejo servía para
  siempre (era el «Para revisar» de P4). Ahora falla cerrado en los dos casos.
- «De hoy o de ayer» porque el CONTADOR concilia a las 6:25 p. m. CDMX, después de la ronda de las 6:10 p. m.: la
  conciliación buena de cada ronda es la del día anterior. Se mide con el reloj (hora de CDMX, `zona_horaria`), no con
  el día de la vela.
- Mensajes nuevos (empiezan con «⚠️ Falta la conciliación del papel» para que el resumen no los repita):
  «… de hoy o de ayer (hora de CDMX): la de datos/papel/conciliacion.json es del 2026-11-14. Hoy no se abren posiciones
  nuevas. CONTADOR: corre .venv\Scripts\python.exe -m sobreviviente conciliar.» y «… no dice "ok". …».
- **Pruebas viejas a las que se les agregó la fecha de hoy** (escribían `{"ok": true}` sin fecha; ninguna aserción
  cambió): `test_arreglo55_archivos_ilegibles.py::test_conciliacion_buena_sigue_contando` y
  `test_arreglo64_tope_diario_ronda.py::test_el_dia_utc_siguiente_vuelven_las_compras`.
- Prueba: `tests/test_arreglo169_conciliacion_de_hoy.py` (23 casos; incluye la frontera UTC/CDMX: `2026-11-16T05:30Z`
  es el 15 nov a las 11:30 p. m. en CDMX y el 17 ya es vieja).

### Q3. Arreglo 170: anotar la compra ANTES de mandarla (COMPRA_ENVIADA)
- Antes, COMPRA_LLENADA se registraba hasta después del stop (arreglo 165: el stop va en el acto). Si el EJECUTOR se
  caía entre la compra y el registro, el estado real no sabía que había BTC y nadie lo marcaba.
- Ahora el paso 4 del EJECUTOR es: revisar que la compra no exista y el precio (a, b), **c. registrar COMPRA_ENVIADA**
  (si sale ❌, no se manda nada), d. mandar la compra, e–h. stop en el acto, confirmarlo y anotar.
- `conciliar --real` con un COMPRA_ENVIADA sin COMPRA_LLENADA, COMPRA_PARCIAL ni COMPRA_NO_LLENADA, o con BTC (más de
  1 USDT o sin precio) en una foto fresca que el estado real no conoce, imprime primero:
  «❌ URGENTE para THE BOSS, prioridad máxima: puede haber BTC SIN STOP en Binance que el estado real no tiene anotado.
  Avisa a Ángelo YA: en Binance hay que ponerle stop a ese BTC o venderlo a mercado (lo decide él). El programa NO vende
  solo. …», marca la línea «SIN STOP: BTC — …», sale ❌ y deja `bloqueo_compras` (por ejemplo «SIN STOP: BTC (compra
  enviada sin anotar, boleto …)»). Con eso la ronda real no compra hasta que Ángelo diga `reanudar --cartera REAL`
  (arreglo 137). El SIN STOP de una posición ya anotada sigue igual (la ronda saca su boleto de cierre).
- **Riesgo aceptado (falla cerrado):** si el CONTADOR concilia mientras el EJECUTOR está entre COMPRA_ENVIADA y
  COMPRA_LLENADA, las compras se bloquean y Ángelo tiene que reanudar. Por eso el CONTADOR concilia después del 👍 del
  EJECUTOR.
- Prueba: `tests/test_arreglo170_compra_enviada.py` (16 casos).

### Q4. Arreglo 171: revisar justo después de cada compra real
- Antes, después de STOP_PUESTO nadie revisaba hasta la ronda del día siguiente (~24 h). Ahora el paso 4i del EJECUTOR
  es: foto de saldo nueva (`spot.getAccount`, `spot.getOpenOrders` y `registrar-saldo`) y `conciliar --real` en el acto.
  Si sale ❌ o SIN STOP, aviso inmediato y con prioridad a THE BOSS.
- La revisión vive en el estado real (`revision_despues_de_compra`, la deja STOP_PUESTO). Cuenta como revisión solo una
  conciliación con una foto válida tomada DESPUÉS de la compra. Si no cuadra, `bloqueo_compras`: no se compra nada más
  hasta que Ángelo diga `reanudar --cartera REAL`.
- **Por qué la foto de antes de la compra no sirve:** la foto de las 6:00 p. m. no trae ni el BTC ni el stop. Juzgar
  con ella marcaría SIN STOP una posición que sí tiene su stop, y la ronda siguiente mandaría venderla (arreglo 137).
  Por eso esa conciliación sale ❌ y pide repetir la foto, sin marcar nada.
- «No se compra nada más» también en la puerta: `registrar-llenado --evento COMPRA_ENVIADA` sale ❌ «NO mandes la
  compra: …» si hay compras bloqueadas, la cartera está detenida, falta la revisión de la compra anterior o hay una
  posición sin stop ACTIVO.
- Prueba: `tests/test_arreglo171_revision_tras_compra.py` (12 casos).

### Q5. Cifras y pendientes
- Pruebas: 1256 → 1307 en Linux (1306 más 1 saltada en Windows; no corrí nada en Windows): 169 suma 23, 170 suma 16 y
  171 suma 12. Cobertura del paquete: 92.36 % → 92.44 %; ningún commit bajó la cifra del anterior
  (92.36 → 92.37 → 92.41 → 92.44).
- **Textos para volver a pegar en Grok Bot:** `bots/4_EJECUTOR_REAL.md` (paso 4c: COMPRA_ENVIADA antes de mandar la
  compra; paso 4i: foto y `conciliar --real` en el acto; pasos 6 y 7) y `bots/5_CONTADOR_REAL.md` (paso 2: conciliar
  después del 👍 del EJECUTOR).
- **Quedan para después (no se hicieron en esta tanda):** órdenes OTO/OTOCO (siguen siendo DECISIÓN DE ÁNGELO, ver P2,
  y el conector todavía no las tiene) y separar los boletos de las carteras A, B y C.
- **Arreglo 152: domingo 22 nov 2026**, separado y sin cambios. F1 sigue con `activo: false`. Nada de esto promete
  ganancias.

## R. Tanda 172–174

Rama `codex/marea-v2`, desde `cc22b80` (1307 pruebas en Linux; cobertura del paquete 92.44 %). Sin llaves de Binance,
sin órdenes y sin dinero: todo se probó con archivos y clientes falsos. No se tocó `reglamento.yaml` (el 152 sigue para
el domingo 22 nov 2026), ni F1 (sigue `activo: false`), ni `riesgo.py`, ni ninguna regla de riesgo. No se abrió ninguna
ruta nueva de dinero real: lo nuevo solo VENDE BTC que ya está en la cuenta, o bloquea; el código nunca manda órdenes.

### R1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 172 | `ccd2501` | Venta urgente del BTC sin anotar (ver R2). La ronda real arma un boleto CERRAR con motivo `SIN_ANOTAR` (`real.boleto_venta_sin_anotar`) para el BTC LIBRE que una foto fresca (aunque haya salido ❌) trae en `sin_estado` y el estado real no tiene en posiciones (`real.btc_sin_anotar`), venga o no de un COMPRA_ENVIADA sin resultado. Vende a MERCADO solo lo libre, redondeado hacia abajo al paso; no cancela nada. Pasa por `revisar_boleto_real` (LOT_SIZE, MARKET_LOT_SIZE, MIN_NOTIONAL, solo venta a mercado sin precio, solo BTC) y por `ronda --verificar --real` como cualquier CERRAR. Sin foto fresca, sin reglas o precio, o abajo del mínimo, no hay venta y sale «❌ URGENTE …» primero. `registrar-llenado --real --evento VENTA_LLENADA` sobre ese boleto sin posición lo anota en `ventas_sin_anotar` y en `llenados.jsonl` (con `cubre`: las compras enviadas que deja cerradas); no toca cerradas, capital ni `bloqueo_compras`. `bots/4_EJECUTOR_REAL.md` (paso 5b). |
| 173 | `e721c2b` | No se manda una segunda compra con una sin anotar (ver R3). `real._por_que_no_comprar(est, reg)` revisa primero `compras_sin_anotar`: con un COMPRA_ENVIADA sin COMPRA_LLENADA, COMPRA_PARCIAL ni COMPRA_NO_LLENADA (ni venta urgente que lo cubra), `registrar-llenado --real --evento COMPRA_ENVIADA` de otro boleto sale ❌ «NO mandes la compra: hay una compra enviada sin anotar (boleto …, COMPRA_ENVIADA, hora CDMX): anota primero cómo terminó (…) → no se manda otra compra. Avisa a THE BOSS …», aunque nadie haya corrido `conciliar --real`. Los motivos del 171 quedan iguales y en el mismo orden, después de este. |
| 174 | este commit | Un archivo de boletos de papel por cartera (ver R4). `papel.ronda` escribe `salida/boletos_<día>_A.json`, `_B.json` y `_C.json` (cada uno solo con los boletos de su cartera) y al final, como siempre, `boletos_<día>.json` con los de todas, que sigue siendo la marca de «la ronda terminó». `ronda --verificar` revisa el archivo de cada cartera (un boleto de otra cartera, un archivo que falta, dañado o que no coincide con el de todas es ❌ «no pongas nada»); con una ronda de antes (solo el de todas) revisa como siempre. `registrar-llenado --ensayo` busca el boleto en el archivo de su cartera. El reporte del CONTADOR no cuenta dos veces. Nuevas: `papel.archivo_boletos` y `papel.cartera_del_boleto`. `bots/4_EJECUTOR.md` (paso 1). Además, CLAUDE.md y esta sección con las cifras finales. |

### R2. Arreglo 172: venta urgente del BTC sin anotar
- Antes (170): el BTC que el estado real no conocía quedaba SIN STOP, con compras bloqueadas y un aviso, pero ningún
  boleto lo vendía; la venta quedaba a mano de Ángelo en Binance.
- Ahora la ronda real lo trata como una posición sin stop: primero los cierres, luego la venta urgente y al final la
  compra (que no sale: la conciliación sale ❌ y hay bloqueo). La venta urgente se emite aunque haya MODO SEGURO, pausa,
  tope o conciliación en ❌ (lo que protege nunca se bloquea).
- **Solo lo LIBRE.** Lo bloqueado en una orden abierta que el estado no conoce (por ejemplo, un stop que el EJECUTOR
  puso y no anotó) sí tiene orden y no se toca: si todo está bloqueado no sale venta, sale «❌ URGENTE: hay … BTC sin
  anotar bloqueados en órdenes abiertas … y nada libre» y Ángelo revisa esas órdenes.
- **Nunca a ciegas.** Sin una foto fresca no se sabe cuánto BTC hay: con un COMPRA_ENVIADA sin resultado y sin foto
  sale «❌ URGENTE: puede haber BTC sin stop (compra enviada sin anotar: boleto …) y sin una foto de saldo fresca no sé
  cuánto hay: no sale venta urgente …».
- **PERCENT_PRICE:** la venta es a MERCADO, sin precio límite, como el cierre SIN_STOP de siempre; la revisión rechaza
  cualquier venta urgente con precio. La documentación de Binance no dice claro si ese filtro mira las órdenes a
  mercado: no se promete más que eso.
- Ejemplo con las reglas reales de BTCUSDT (tests/datos_arreglo132): 0.00013 BTC libres a 70,000 → vende «0.00013»
  (9.10 USDT); 0.00012987 → «0.00012»; 0.00005 (3.50 USDT) no llega al mínimo de 5 USDT → sin venta y ❌ URGENTE.
- **Prueba vieja que cambió (OK de Ángelo en esta tanda):**
  `test_arreglo134_entradas_real.py::test_btc_en_la_cuenta_sin_posicion_anotada_no_compra` decía `_boletos(r) == []`;
  ahora exige que no haya boleto COMPRAR y que salga exactamente UNA venta urgente de 0.00013 BTC. Lo demás, igual.
- Prueba: `tests/test_arreglo172_venta_sin_anotar.py` (30 casos).

### R3. Arreglo 173: no se manda una segunda compra con una sin anotar
- Antes: la puerta de COMPRA_ENVIADA (171) solo veía `bloqueo_compras`, la cartera detenida, la revisión pendiente y las
  posiciones sin stop. El bloqueo por una compra sin anotar lo pone `conciliar --real` (170): si el EJECUTOR se caía
  después de COMPRA_ENVIADA y, al volver, nadie había conciliado, podía anotar y mandar OTRA compra encima.
- Ahora lo primero que revisa es `compras_sin_anotar`. El mensaje dice cuál boleto quedó pendiente (y cuántos más, si
  hay), a qué hora se mandó (hora CDMX, o «sin hora») y qué anotar. Una compra con su resultado anotado, o cubierta por
  una venta urgente anotada (172), ya no frena por este motivo (sí por los del 171, por ejemplo el bloqueo, que solo
  quita Ángelo).
- La ronda real no cambia: con una compra sin anotar su conciliación ya sale ❌ y hay bloqueo, así que no saca compra.
- Prueba: `tests/test_arreglo173_segunda_compra.py` (8 casos).

### R4. Arreglo 174: un archivo de boletos de papel por cartera
- Antes, A, B y C escribían sus boletos en un solo archivo (`salida/boletos_<día>.json`); era el pendiente de Q5.
- Ahora cada cartera tiene el suyo: `salida/boletos_<día>_A.json`, `_B.json` y `_C.json`, escritos solo con lo que dio
  esa cartera (una no puede pisar a la otra). `boletos_<día>.json` se sigue escribiendo AL FINAL con los de todas: así
  no cambian «la ronda ya corrió», la ronda repetida, la ronda que truena a medias ni las pruebas viejas que lo leen.
- **`ronda --verificar`:** si están los archivos por cartera, revisa cada uno. Sale «❌ … trae un boleto de la cartera B
  (…): una cartera pisó el archivo de otra», «❌ falta boletos_<día>_C.json …», «❌ los archivos de A, B y C no coinciden
  con boletos_<día>.json» o el aviso de archivo dañado, y luego «❌ Los boletos de las carteras no cuadran: no pongas
  nada y avisa a THE BOSS.». Los renglones ✅/❌ de cada boleto quedan iguales. Una ronda de antes del 174 (solo el
  archivo de todas) se revisa igual que siempre.
- Los boletos CERRAR y MODIFICAR_STOP del papel no traen el campo `cartera`: `papel.cartera_del_boleto` la saca de su
  `boleto_id` (`AAAAMMDD-A-…`). No se cambió ningún boleto.
- **CONTADOR:** `conciliar` no lee boletos (sigue igual); `reporte diario|semanal` se salta los archivos por cartera
  para no contar dos veces la apertura contra el precio. `respaldo` ya copiaba todo `salida/`.
- **La ronda del día siguiente** corre normal: escribe sus tres archivos y el de todas, y no toca los del día anterior.
- Prueba: `tests/test_arreglo174_boletos_por_cartera.py` (13 casos).

### R5. Cifras y pendientes
- Pruebas: 1307 → 1358 en Linux (1357 más 1 saltada en Windows; no corrí nada en Windows): 172 suma 30, 173 suma 8 y
  174 suma 13. Cobertura del paquete: 92.44 % → 92.56 %; ningún commit bajó la cifra del anterior
  (92.44 → 92.51 → 92.52 → 92.56).
- **Textos para volver a pegar en Grok Bot:** `bots/4_EJECUTOR_REAL.md` (paso 5b: venta urgente) y `bots/4_EJECUTOR.md`
  (paso 1: un archivo por cartera).
- **Pendiente: DECISIÓN DE ÁNGELO (no hice nada de esto):**
  - El aviso de `conciliar --real` (`AVISO_SIN_ANOTAR`) sigue diciendo «ponerle stop a ese BTC o venderlo a mercado (lo
    decide él)». Con el 172 la ronda ya arma la venta urgente del BTC libre. No lo cambié porque
    `test_arreglo170` exige el texto exacto; si Ángelo quiere, se alinea en un arreglo aparte.
  - La pérdida o ganancia de una venta urgente sin anotar no entra en las cerradas, las rachas ni los topes (no se sabe
    su costo): queda como diferencia de USDT en `conciliar --real` y Ángelo la absorbe con `ajustar-capital-real`. Si
    el EJECUTOR anota la compra (COMPRA_LLENADA) ANTES de la VENTA_LLENADA, sí entra como una salida normal.
  - El BTC sin anotar BLOQUEADO en una orden abierta que el estado no conoce no se vende ni se cancela: lo revisa Ángelo
    en Binance.
- **Arreglo 152: domingo 22 nov 2026**, separado y sin cambios. F1 sigue con `activo: false`. Nada de esto promete
  ganancias.

## S. Tanda 175–184 (revisión del dinero real)

Rama `codex/marea-v2`, desde `94a17e0` (1358 pruebas en Linux; cobertura del paquete 92.56 %). Sin llaves de Binance,
sin órdenes y sin dinero: todo se probó con archivos, procesos y clientes falsos. No se tocó `reglamento.yaml` (el 152
sigue para el domingo 22 nov 2026), ni F1, ni `riesgo.py`, ni ninguna regla de riesgo. El código sigue sin mandar
órdenes: solo anota, bloquea, avisa y arma boletos.

### S1. Qué se hizo
| Arreglo | Commit | Qué cambió |
|---|---|---|
| 175 | `913487c` | (C1) `registrar-llenado --real` es idempotente (ver S2). Primero escribe el renglón de `llenados.jsonl` (flush + fsync) y después `cartera_REAL.json`. Si el mismo evento del mismo boleto ya tiene renglón, no agrega nada: con el estado al día sale ❌ «ya está registrado … (no se agregó nada)»; si el estado no lo tiene (se cayó entre los dos pasos), lo completa con ESE renglón y lo dice con ⚠️. Si el estado ya lo tiene y falta el renglón (la caída del orden viejo), solo escribe el renglón. Una orden de Binance (`--orden-id`) que ya está en otro renglón de su clase (compra, stop o venta) o en otra posición se rechaza. Nuevas: `real._escribir_renglon`, `real._efecto_en_estado`, `real._orden_repetida` y `real._aplicar_llenado` (lo que antes estaba dentro de `registrar_llenado`, sin cambios, ahora con los datos del renglón). |
| 176 | `9bc1151` | (C2) Un renglón ilegible de `llenados.jsonl` bloquea las compras reales, con mensaje claro (ver S3). `real.llenados_rotos` (los renglones vacíos no cuentan) y `real.por_que_llenados_rotos`. Con un renglón roto: COMPRA_ENVIADA sale ❌ «NO mandes la compra: llenados.jsonl (datos/real) tiene 1 renglón(es) ilegible(s) (#n): puede ser una compra a medio anotar …»; `conciliar --real` sale ❌ con ese mensaje; la ronda real no compra («❌ Sin compras: …»); `ronda --verificar --real` no aprueba boletos COMPRAR (los CERRAR sí). Lo que ya pasó en Binance se anota igual, con ⚠️. Al escribir: si el archivo no termina en salto de línea se pone primero, luego la fila, flush y fsync. `leer_llenados` (reportes) sigue contando los renglones que sí se leen. |
| 177 | `ba3b967` | (I1) `registrar-llenado --real`, `conciliar --real` y `registrar-saldo` corren con el MISMO candado que la ronda real (`datos/real/ronda.lock`, `cli_ronda.candado_ronda`). Si otro proceso lo tiene, dicen «⏳ Otra tarea del real … espero hasta N s» y esperan (`cli_real.ESPERA_CANDADO_S`, 300 s); si no lo sueltan a tiempo, «❌ <tarea>: otra tarea del real sigue usando datos/real … No hice nada» y salen con 1 sin tocar nada. El candado se toma en los comandos, no en `real.conciliar` (la ronda real lo llama ya con el candado tomado). Nuevas: `cli_real.con_candado` y `cli_real.archivo_candado`. |
| 178 | `7be6cc5` | (I2) Si la ronda real se salta, por Binance en mantenimiento (`BinanceNoOpera`, 166) o por cualquier otra falla como la red caída, antes del mensaje de la ronda saltada salen como «❌ URGENTE: …» los pendientes del estado LOCAL, sin red: un renglón ilegible de `llenados.jsonl` (176), cada COMPRA_ENVIADA sin su resultado («puede haber BTC SIN STOP en Binance. EJECUTOR: revisa esa compra con spot.getOrder y anota cómo terminó …»), el BTC que la última foto de saldo trae en `sin_estado` y el estado real no conoce, y cada posición sin stop confirmado (lo de antes, 166). No escribe nada. Nueva: `ronda_real.pendientes_urgentes`. |
| 179 | `25ff2b1` | (I3) El stop ejecutado normal ya no es SIN STOP (ver S6). Si en la foto no hay ninguna orden abierta con el `id_stop` de la posición y queda menos BTC que su paso (`real.stop_ejecutado`, el mismo criterio que `_cierres`), `conciliar` dice «STOP EJECUTADO: BTC — … EJECUTOR: registra STOP_EJECUTADO …» y deja `diferencias.stop_ejecutado`: no cuadra (falta anotarlo), pero no cambia `estado_stop`, no pone `bloqueo_compras` y no da el aviso de SIN STOP. La diferencia de USDT dice «seguramente es la venta del stop de BTC; se arregla al registrar STOP_EJECUTADO» en vez de mandar a `ajustar-capital-real`. Si STOP_PUESTO dejó pendiente la revisión (171) y lo único raro es el stop ejecutado, la revisión queda pendiente sin bloquear. `conciliar --real` imprime ese renglón primero. |
| 180 | `9b3b478` | (I4) Posición anotada MÁS BTC de sobra: venta urgente solo del sobrante (ver S7). Nuevas `real.anotado` y `real.sobrante` (lo que pasa de lo anotado por más del paso, con el estado de AHORA). `registrar_saldo` deja el sobrante (si vale más de 1 USDT o no hay precio) en `sin_estado` con un ❌ que explica, pero la foto queda ok (sirve para revisar el stop de la posición). `conciliar` marca «SIN STOP: BTC — hay … BTC DE MÁS en Binance, además de los … anotados en la posición …» y bloquea. `btc_sin_anotar` da solo lo que sobra (lo libre hasta el sobrante); la ronda real arma la venta urgente de esa cantidad (`boleto_venta_sin_anotar(…, anotado_en_posicion)`, campo `anotado_en_posicion` y texto «DE MÁS»). `pendientes_urgentes` (178) también lo dice. El boleto de cierre y `bots/4_EJECUTOR_REAL.md` (paso 5, la línea 58; y una nota en el 5b) venden la cantidad del boleto, no «todo lo libre». |
| 181 | `126dceb` | (I5) Las ventas a mercado llevan un `newClientOrderId` FIJO por boleto (ver S8): `real.id_venta(boleto)` = bv + 16 hex, en `orden_venta` del cierre (`boleto_cierre_real`) y de la venta urgente (`boleto_venta_sin_anotar`), y en `id_venta`. `revisar_boleto_real` no aprueba un CERRAR (salvo el informativo STOP_EJECUTADO) cuya venta no traiga ese id. El texto de los dos boletos y `bots/4_EJECUTOR_REAL.md` (pasos 5 y 5b): si la venta falla o no se sabe si llegó, ANTES de reintentar se revisa con `spot.getOrder` por `origClientOrderId`; si ya existe, no se repite (se anota); solo si no existe, se reintenta una vez con el mismo id. |
| 182 | `8af10e2` | (I6) COMPRA_ENVIADA pide `--precio-actual` (el de `spot.tickerPrice`) y revisa en código, después de las puertas de siempre (171, 173, 176): que el boleto no esté vencido (`vence_utc`) y que el precio no pegue con `no_comprar_si` (mayor que el límite de compra, a 2 % o menos del stop, o arriba del tope por PERCENT_PRICE_BY_SIDE). Si falla o falta el precio: «❌ NO mandes la compra: … No se anotó nada. Avisa a THE BOSS …» y no se escribe ningún renglón. El renglón guarda `precio_actual`. Nuevas: `real._por_que_no_mandar` y `real.ahora_utc` (la hora por defecto de `registrar_llenado`, para fijarla en pruebas de línea de comandos). `registrar-llenado` tiene `--precio-actual`. Boleto (`antes_de_comprar` y texto) y `bots/4_EJECUTOR_REAL.md` (paso 4c). |
| 183 | `65d6795` | (I7) COMPRA_NO_LLENADA con motivo, también cuando Binance RECHAZA la compra (ver S10). Pide `--motivo` (EXPIRED, o el código y mensaje de Binance); sin él, ❌ y no se anota. Al anotarla, la compra deja de contar como enviada sin anotar (sin SIN STOP), y si `bloqueo_compras` lo había puesto ESA compra (`real.motivo_compra_sin_anotar`), se quita y queda en `falsas_alarmas` (con «✅ Se quitó el bloqueo …»). Cualquier otro bloqueo se queda. `bots/4_EJECUTOR_REAL.md` (paso 4e): `--motivo EXPIRED`, qué hacer si Binance rechaza la compra y si no se sabe cómo terminó (`spot.getOrder` primero). |
| 184 | `47a180d` | (I9) `registrar_saldo` rechaza la foto (ok:false) si el `updateTime` de la cuenta es de ANTES del último llenado anotado, no solo por la fecha del archivo (ver S11). `real.ultimo_llenado` da desde cuándo pudo cambiar el saldo el último llenado (COMPRA_LLENADA, COMPRA_PARCIAL, VENTA_LLENADA, STOP_EJECUTADO, CIERRE_DE_EMERGENCIA) y `real._foto_de_antes_del_llenado` arma el ❌ «cuenta.json es de antes del último llenado anotado … Parece una foto vieja copiada otra vez …». `real.MARGEN_RELOJ_S` = 300. `bots/4_EJECUTOR_REAL.md` (paso 1): siempre respuestas nuevas. |
| — | este commit | Pruebas para los huecos de cobertura que pidió Ángelo (números de línea de 94a17e0), sin cambiar el paquete: `cli_real.py` 87-89, 108-109, 128, 132 (`ronda --verificar --real` con el archivo de boletos dañado, un boleto que truena al revisarlo, el informativo STOP_EJECUTADO y BTCUSDT fuera de TRADING); `ronda_real.py` 125-128, 197, 217-219, 244-245, 249-251, 330, 332 (archivos de los bots, pausa, sin reglas de Binance, cantidad que queda en 0, boleto que no pasa su revisión, venta urgente sin reglas o sin precio); `real.py` 885-886 (`buscar_boleto` con el archivo dañado y sin copia); `archivos.py` 79-82 (`escribir_json_seguro` que falla borra su temporal). `tests/test_cobertura_real_175_184.py` (13 casos). Además, CLAUDE.md y esta sección con las cifras finales. |

### S2. Arreglo 175: llenado idempotente
- Antes: `guardar_estado` y luego el renglón. Una caída entre los dos dejaba la posición en el estado sin renglón; el
  reintento no la veía como «ya registrada» y la agregaba otra vez (el doble de BTC en libros).
- Ahora el renglón va primero. Al reintentar, la hora de la posición (o de la salida) es la del renglón, no la del
  reintento. Un STOP_PUESTO cuyo renglón quedó pero cuya compra no está en el estado pide repetir primero la compra.
- Prueba: `tests/test_arreglo175_llenado_idempotente.py` (9 casos).

### S3. Arreglo 176: un renglón ilegible bloquea las compras
- Antes: `leer_llenados` brincaba en silencio lo que no podía leer. Un COMPRA_ENVIADA cortado (el EJECUTOR se cayó al
  escribirlo) desaparecía y se podía anotar y mandar otra compra.
- Ahora no se compra nada mientras el archivo tenga un renglón roto; no se pone `bloqueo_compras` (frena solo mientras
  siga roto): en cuanto Ángelo lo revisa en Binance y arregla el renglón a mano, se puede volver a comprar. El renglón
  roto se queda como está: la fila nueva va en su propio renglón.
- Prueba: `tests/test_arreglo176_renglon_roto.py` (10 casos).

### S4. Arreglo 177: un solo candado para todo lo que escribe el estado real
- Antes: la ronda real tenía su candado, pero `registrar-llenado --real`, `conciliar --real` y `registrar-saldo` no.
  Si el EJECUTOR anotaba STOP_PUESTO mientras corría la ronda, la ronda podía guardar encima su copia vieja del estado.
- Ahora los cuatro usan `datos/real/ronda.lock`. Espera máxima de los comandos: 300 s (la ronda real espera 600 s,
  como antes). No toca `reanudar --cartera REAL` ni `ajustar-capital-real` (solo Ángelo, a mano): si se quiere, van
  en un arreglo aparte.
- Prueba: `tests/test_arreglo177_candado_real.py` (6 casos, con un segundo proceso de Python que toma el candado).

### S5. Arreglo 178: con la ronda saltada, lo urgente primero
- Antes (166) solo se decían las posiciones sin stop, y solo con Binance en mantenimiento. Con la red caída salía
  «❌ La ronda real NO corrió: …» sin decir que podía haber BTC sin stop.
- La foto que se usa es la última guardada aunque sea vieja o haya salido ❌ (dice su hora en CDMX): sin red no hay otra.
  Si `datos/real/saldo_binance.json` está dañado no se puede leer y no sale ese renglón.
- Prueba: `tests/test_arreglo178_saltada_urgentes.py` (16 casos: cada pendiente con mantenimiento y con la red caída).

### S6. Arreglo 179: el stop que se ejecutó normal
- Antes: `conciliar` (también la de la ronda real, que corre antes de `_cierres`) marcaba SIN_STOP y ponía
  `bloqueo_compras`, que solo Ángelo quita con `reanudar`, aunque la posición ya estaba vendida por su propio stop.
- Ahora no se compra hasta anotar STOP_EJECUTADO (la conciliación no cuadra), y en cuanto se anota, la siguiente
  conciliación cuadra sola. Con BTC igual o mayor al paso y sin stop sigue siendo SIN STOP, como siempre.
- Prueba: `tests/test_arreglo179_stop_ejecutado.py` (6 casos).

### S7. Arreglo 180: el BTC de más sobre una posición anotada
- Antes: el BTC de una moneda con posición nunca era «sin anotar». Con 0.00012 BTC anotados (con su stop) y 0.00013 BTC
  más que nadie conocía, solo salía la diferencia en `conciliar --real`; ningún boleto los vendía. Y el paso 5 decía
  vender «la cantidad libre», que en ese caso vendía también lo que no era de la posición.
- Ahora sale la venta urgente de 0.00013 (solo lo libre que sobra). Si a la posición le falta el stop, salen las dos:
  el cierre SIN_STOP de 0.00012 y la venta urgente de 0.00013. Lo que sobra bloqueado en una orden abierta no se vende
  (como en el 172). El polvo (hasta el paso, o menos de 1 USDT) no cuenta.
- El sobrante se calcula con el estado de AHORA: una foto tomada antes de anotar la compra no cuenta la compra como
  sobrante.
- **Prueba vieja que cambió de texto:** ninguna. El texto del boleto de cierre cambió de «(o lo libre, redondeado hacia
  abajo al paso)» a «(la cantidad del boleto, no todo lo libre: …; si hay menos libre, lo libre redondeado hacia abajo
  al paso)»; ninguna prueba vieja pedía el texto anterior.
- Prueba: `tests/test_arreglo180_sobrante.py` (12 casos).

### S8. Arreglo 181: la venta no se manda dos veces
- Antes: «Si la venta falla, reintenta una vez», sin id. Si la venta sí entró y se perdió la respuesta, el reintento
  vendía otra vez. Binance solo pide que el `newClientOrderId` no se repita entre las órdenes ABIERTAS (documentación de
  Spot, `POST /api/v3/order`); una venta a mercado ya llenada no frena otra con el mismo id: por eso se revisa con
  `spot.getOrder` antes de reintentar.
- **Pruebas viejas que cambiaron (solo para pedir el campo nuevo):** `test_arreglo132_boleto_real.py::
  test_boleto_de_cierre_real` y `test_arreglo172_venta_sin_anotar.py::test_btc_libre_sin_anotar_sale_venta_urgente`
  comparaban `orden_venta` campo por campo; ahora también piden `"newClientOrderId": RE.id_venta(...)`. No se quitó
  ninguna revisión.
- Prueba: `tests/test_arreglo181_id_de_venta.py` (6 casos, con un Binance falso que pierde la primera respuesta).

### S9. Arreglo 182: el precio actual se revisa en código
- Antes, el vencimiento y `no_comprar_si` los revisaba el EJECUTOR a mano (paso 4b). Ahora el programa los revisa otra vez
  con el precio que le pasa: si el EJECUTOR se equivoca o se salta el paso, la compra no se anota y le dice que no la
  mande. «Vencido» es estrictamente después de `vence_utc` (a las 02:10 UTC justas todavía vale).
- No revisa `valor_menor_que_usdt`: la compra es LIMIT y Binance mide el mínimo con el precio del boleto, que ya revisó
  la ronda (`revisar_boleto_real`).
- **Pruebas viejas que cambiaron (solo para pasar el precio que ahora se pide):** las que anotan un COMPRA_ENVIADA que
  debe salir bien ahora pasan `precio_actual=70000.0` (el precio de referencia del boleto, que pasa todas las reglas):
  el ayudante `_llenar` de `test_arreglo170`, `_comprar` de `test_arreglo171`, tres llamadas de `test_arreglo172` y
  `_enviar` de `test_arreglo173`; `test_arreglo170::test_el_aviso_para_the_boss_sale_primero` además pasa
  `--precio-actual 70000` y fija la hora con `RE.ahora_utc` (con la hora de verdad el boleto del 15 nov ya venció). Las
  que esperan ❌ por las puertas de siempre no cambiaron: esas puertas van primero. No se quitó ninguna revisión.
- Prueba: `tests/test_arreglo182_precio_actual.py` (16 casos).

### S10. Arreglo 183: la compra que Binance rechaza
- Antes, el paso 4e solo cubría la compra FOK que no se llenaba (EXPIRED). Si Binance contestaba con un error (por
  ejemplo `-2010`, saldo insuficiente) no había instrucción: el COMPRA_ENVIADA quedaba sin resultado, `conciliar --real`
  lo contaba SIN STOP y ponía un bloqueo que solo Ángelo quitaba, aunque nunca hubo BTC.
- Ahora se anota COMPRA_NO_LLENADA con el error tal cual. El evento ya existía; lo nuevo es el motivo obligatorio y que
  quite la falsa alarma. Si el EJECUTOR se equivoca y sí hubo compra, la siguiente foto de saldo encuentra el BTC sin
  anotar y vuelve a bloquear (y la ronda arma la venta urgente, 172).
- **Pruebas viejas que cambiaron (solo para pasar el motivo que ahora se pide):** `test_arreglo136` (dos llamadas),
  el ayudante `_llenar` de `test_arreglo170`, una llamada de `test_arreglo173` y el EJECUTOR simulado de
  `test_arreglo165` pasan `motivo="EXPIRED"` (o `--motivo EXPIRED`). No se quitó ninguna revisión.
- Prueba: `tests/test_arreglo183_compra_no_llenada.py` (7 casos).

### S11. Arreglo 184: la foto vieja copiada otra vez
- Antes: `registrar_saldo` solo miraba cuándo se guardó el archivo. Una respuesta de spot.getAccount de ayer, copiada otra
  vez hoy, pasaba como foto fresca aunque no trajera la compra.
- **Qué hora se compara (decisión de MECÁNICO, para revisar).** «El último llenado» no puede ser la hora en que se ANOTÓ:
  Binance cambia la cuenta (y su `updateTime`) al llenar y al poner el stop, ANTES de que el EJECUTOR lo anote; con esa
  hora se rechazaría la foto buena de justo después de la compra (171). Se usa la hora más temprana posible: la del
  COMPRA_ENVIADA del boleto (se anota antes de mandar la compra; para un STOP_EJECUTADO, el de la compra de su
  posición) y, como piso para todo, el inicio de la ronda que emitió el boleto (00:00 UTC del día siguiente al del
  boleto; para una VENTA_LLENADA es lo único). Con 5 min de margen por los relojes (`MARGEN_RELOJ_S`).
- **Ayuda de pruebas que cambió:** `cuenta()` de `tests/apoyo_real.py` traía `updateTime` fijo de nov 2025, más viejo
  que cualquier llenado de las pruebas. La foto de `mundo` (`test_arreglo134`) ahora le pone un minuto antes de la hora
  de la foto (`apoyo_real.al_dia`, solo si trae el fijo), como haría Binance. `test_arreglo130` sigue pidiendo el fijo
  (no pasa por `mundo`). En `test_arreglo179` (de esta tanda) una posición de prueba usa un id de un día anterior:
  con el id del día 16 no podía existir a las 00:16 UTC del 16.
- Prueba: `tests/test_arreglo184_foto_vieja.py` (10 casos).

### S12. Cifras y pendientes
- Pruebas: 1358 → 1469 en Linux (1468 más 1 saltada en Windows; no corrí nada en Windows): 175 suma 9, 176 suma 10,
  177 suma 6, 178 suma 16, 179 suma 6, 180 suma 12, 181 suma 6, 182 suma 16, 183 suma 7, 184 suma 10 y las de cobertura
  13. Cobertura del paquete: 92.56 % → 93.02 %; ningún commit bajó la cifra del anterior
  (92.56 → 92.60 → 92.62 → 92.64 → 92.66 → 92.67 → 92.69 → 92.70 → 92.73 → 92.73 → 92.76 → 93.02). Todas las
  líneas que se pidieron quedaron cubiertas; `cli_real.py` queda al 100 %.
- **Textos para volver a pegar en Grok Bot:** `bots/4_EJECUTOR_REAL.md` (paso 1: respuestas nuevas; paso 4c:
  `--precio-actual`; paso 4e: `--motivo`, compra rechazada y compra que no se sabe cómo terminó; paso 5: la cantidad del
  boleto y el `newClientOrderId` fijo con `spot.getOrder` antes de reintentar; paso 5b: «DE MÁS» y lo mismo del id).
- **Nada de esto toca dinero:** el código sigue sin llaves y sin mandar órdenes; solo anota, bloquea, avisa y arma
  boletos que pone el EJECUTOR.
- **Para revisar (decisiones de MECÁNICO en esta tanda):** (1) qué hora cuenta como «el último llenado» en el 184 (ver
  S11); (2) los comandos del real esperan hasta 300 s el candado (177); (3) COMPRA_NO_LLENADA solo quita el bloqueo que
  puso esa misma compra (183); (4) un renglón ilegible frena las compras mientras siga roto, sin poner `bloqueo_compras`
  (176).
- **Pendiente: DECISIÓN DE ÁNGELO (no hice nada de esto):** `reanudar --cartera REAL` y `ajustar-capital-real` todavía no
  usan el candado del 177; `escribir_json_seguro` deja su `.baktmp` si falla justo al copiar la copia anterior (lo vi al
  cubrir `archivos.py` 79-82; no lo cambié porque no se pidió).
- **Arreglo 152: domingo 22 nov 2026**, separado y sin cambios. F1 sigue con `activo: false`. Nada de esto promete
  ganancias.

## T. Tanda del domingo 22 nov 2026 (152 y 185–195)

Rama `codex/marea-v2`, desde `b22f70f` (1469 pruebas en Linux; cobertura del paquete 93.02 %). Ventana de cambios del
domingo: aquí SÍ se tocó `reglamento.yaml`, solo en lo que se pidió (152, 185 y 186). Sin llaves de Binance: todo se
probó con archivos y clientes falsos. OTO para compra y stop sigue pendiente aparte (DECISIÓN DE ÁNGELO: dos órdenes por
ahora, OTO después); no es de esta tanda.

### T1. Arreglo 152: bloque `futuros_papel:` en reglamento.yaml
- Bloque nuevo `futuros_papel:` con las 22 cifras de `sobreviviente/futuros/config.POR_DEFECTO`, en el mismo orden, cada
  una con quién la decidió (DECISIÓN DE ÁNGELO o MECÁNICO por delegación de Ángelo, 2026-11-16). Ninguna cifra cambió.
- **F1 se queda con `activo: false`** (NO PASA `validar-futuros`).
- Versión 2.0.2 → 2.0.3 y CAMBIOS.md. `reglamento.validar` revisa el bloque si existe: de claves y valores, sin claves
  desconocidas (una mal escrita se ignoraría en silencio), `activo` true o false, los límites duros de
  `futuros.config.validar` y `apalancamiento_tope` ≤ `riesgo.futuros.apalancamiento_max`.
- **Pruebas viejas que cambiaron (decían que el bloque todavía no existía):** `test_arreglo143` (ahora el bloque es igual a
  POR_DEFECTO), `test_arreglo159::test_nada_pone_activo_true_en_produccion` (ahora `futuros_papel.activo` es false),
  `test_arreglo164::test_verificar_escalones_no_activa_nada` (lo mismo) y `test_arreglo140` (la versión es 2.0.3 y, en «nada más cambia», también se quita el bloque `futuros_papel` comparándolo
  con POR_DEFECTO). `tests/datos_arreglo91`: solo la versión del reglamento (2.0.2 → 2.0.3), como en el 140. Ninguna
  revisión se quitó.
- Prueba: `tests/test_arreglo152_futuros_papel_reglamento.py` (16 casos).

### T2. Arreglo 185 (C3, DECISIÓN DE ÁNGELO): M0 regresa a PAPEL
- `reglamento.yaml`: M0 pasa de VIVA_MINI a **PAPEL** porque no pasó sus compuertas (VALIDACION_V2.md: 65.6 % contra
  90 % del azar; caída p95 59.8 % contra 25 %; no cumplió `papel_dias_min` 30 ni `papel_operaciones_min` 30). El
  comentario de la línea lo dice; la decisión del 15 nov sigue escrita en CAMBIOS.md (2.0.2). Lo demás de M0 no cambia.
- Efecto: `ronda_real.compuertas_puerta` cierra la puerta (ya lo hacía con M0 en PAPEL): `ronda --modo real` sale con
  «La ronda real NO corre» y no escribe estado ni boletos. El papel (A, B y C) sigue igual con M0.
- `doctor`: con M0 en PAPEL su renglón del real dice que la ronda real NO corre, por qué y que volver lo decide Ángelo.
  Solo informa (no cuenta como ❌). Con M0 en VIVA_MINI dice lo mismo que antes.
- **Pruebas viejas que cambiaron:** `tests/apoyo_real.py` tiene `reg_abierto` (el reglamento con M0 en VIVA_MINI, como
  estuvo del 16 al 22 nov); las cuatro pruebas de `test_arreglo140` que necesitan la puerta ABIERTA lo usan con las
  mismas aserciones. `test_arreglo140::test_el_reglamento_dice_la_decision` y `test_v2` ahora piden M0 en PAPEL (la
  decisión del 15 nov se revisa en CAMBIOS.md). Las demás pruebas del real ya armaban su reglamento con M0 en VIVA_MINI.
- **Para Ángelo:** (1) con la puerta cerrada la ronda real tampoco emite cierres ni ventas urgentes: si quedó una
  posición real abierta, hay que cuidarla a mano en Binance; (2) `bots/THE_BOSS.md` y `bots/4_EJECUTOR_REAL.md` siguen
  describiendo el real como activo (no los cambié: no se pidió); la ronda real misma dice que no corre.
- Prueba: `tests/test_arreglo185_m0_regresa_a_papel.py` (8 casos).

### T3. Arreglo 186 (I10, DECISIÓN DE ÁNGELO): interruptor `real.activo: false`
- `reglamento.yaml`: `real.activo: false`. Solo `true` exacto lo enciende; si falta o dice otra cosa, está apagado
  (falla cerrada). `reglamento.validar` pide true o false.
- Con false salen **sin hacer nada** (exit 2, sin escribir estado, boletos, llenados ni registro) y con el aviso
  «⛔ El dinero real está APAGADO…»: `ronda --modo real` (también con `--simular`; no pide datos a Binance y, si además
  falta algo de la puerta, lo lista debajo de «Además falta:»), `ronda --verificar --real` (no aprueba ningún boleto) y
  `registrar-llenado --real` (no anota nada). `compuertas_puerta` lo pone como su primer renglón.
- **Decisión de MECÁNICO (para revisar):** `registrar-saldo`, `conciliar --real`, `reporte diario --real`,
  `estado --real`, `reanudar --cartera REAL` y `ajustar-capital-real` siguen funcionando: no mandan ni anotan órdenes y
  sirven para vigilar (por ejemplo, encontrar BTC sin stop). Si Ángelo quiere también esos apagados, es un cambio chico.
- `doctor` muestra el interruptor (solo informa).
- **Pruebas viejas que cambiaron (solo para encender el interruptor donde la prueba necesita el real corriendo):**
  `apoyo_real.reg_abierto` y `test_arreglo133.reg_vivo` ponen `real.activo: true`; `test_arreglo136` (verificar sin
  ronda) y `test_arreglo139` (dos pruebas) usan `reg_abierto`, la de la puerta cerrada con M0 en PAPEL; `test_arreglo133`
  revisa que con el reglamento de antes del 140 el primer renglón ahora es el del interruptor y que con el real
  encendido y M0 en PAPEL sigue saliendo «M0 está en PAPEL»; `test_arreglo140` pide `real.activo` false aparte del resto
  del bloque `real:`; `test_arreglo185` (de esta tanda) revisa los dos casos. Ninguna revisión se quitó.
- Prueba: `tests/test_arreglo186_interruptor_real.py` (15 casos).

### T4. Arreglo 187 (R97): compra llenada que el estado real no tiene
- Hueco: `registrar-llenado --real` escribe primero el renglón y después el estado (175). Si el EJECUTOR se cae en medio,
  `llenados.jsonl` dice COMPRA_LLENADA (o COMPRA_PARCIAL) y `cartera_REAL.json` no tiene la posición. `compras_sin_anotar`
  solo miraba COMPRA_ENVIADA sin resultado, así que nadie lo veía.
- Ahora `real.llenadas_sin_estado` encuentra esos renglones (boleto ni en `posiciones` ni en `cerradas`, ni cubierto por
  una venta urgente) y cuentan como pendiente: `conciliar --real` los marca SIN STOP, bloquea las compras (motivo
  «compra llenada que el estado real no tiene») y avisa a THE BOSS; `_por_que_no_comprar` hace que COMPRA_ENVIADA salga
  ❌ «NO mandes la compra» aunque nadie haya conciliado; la ronda real normal (también con `--simular`, en memoria) y la
  saltada (178) lo dicen como URGENTE. El texto dice qué hacer: repetir el mismo `registrar-llenado` (175 completa el
  estado con ese renglón, sin duplicarlo). El bloqueo de compras, como siempre, solo lo quita Ángelo.
- Con el estado dañado no inventa nada: eso ya frena todo por su lado.
- Prueba: `tests/test_arreglo187_llenada_sin_estado.py` (13 casos, con la caída simulada entre el renglón y el estado).

### T5. Arreglo 188 (R98): la falsa alarma se quita solo con una foto fresca limpia
- Antes (183), COMPRA_NO_LLENADA quitaba el bloqueo de compras que había puesto esa misma compra enviada sin anotar, sin
  mirar la cuenta: si el EJECUTOR se equivocaba (la compra sí se llenó), las compras quedaban libres hasta la siguiente
  conciliación.
- Ahora (`real._quitar_falsa_alarma` y `_sin_estado_en_la_foto`) solo se quita si la última foto de saldo FRESCA no trae
  BTC que el estado real no conoce (con una posición anotada, solo cuenta lo que sobra, 180). Si lo trae, el bloqueo se
  queda y el mensaje dice cuánto; **si no hay foto fresca para confirmarlo, también se queda** (decisión de MECÁNICO:
  falla cerrada; el bloqueo solo lo quita Ángelo). La compra no llenada se anota igual.
- **Prueba vieja que cambió:** `test_arreglo183::test_por_la_linea_de_comandos` fija la hora con `RE.ahora_utc` (como el
  182): con la hora de verdad la foto de la prueba ya no es fresca. Las aserciones son las mismas.
- Prueba: `tests/test_arreglo188_falsa_alarma_con_foto.py` (5 casos).

### T6. Arreglo 189 (R99): reanudar y ajustar-capital-real con el candado
- `reanudar --cartera REAL` (`cli_ronda.py`) y `ajustar-capital-real` (`cli_real.py`) leen y guardan `cartera_REAL.json`,
  pero no usaban el candado del 177: podían pisarse con la ronda real o con un registrar-llenado. Ahora corren dentro de
  `cli_real.con_candado` como los demás: esperan hasta `ESPERA_CANDADO_S` y, si no sueltan el candado, salen con ❌ sin
  hacer nada (y queda en el registro de tareas). Esto cierra el pendiente que dejé en S12.
- Prueba: `tests/test_arreglo189_candado_reanudar_ajustar.py` (6 casos, con un segundo proceso que toma el candado).

### T7. Arreglo 190 (R101 + I5): la venta de emergencia viene lista en el boleto de compra
- Antes, si el stop no se podía poner, el paso 4j decía «VENDE TODO lo comprado a MERCADO (cantidad libre redondeada…)»:
  el EJECUTOR calculaba en el peor momento, podía vender BTC que no era de esa compra (un sobrante, 180) y la venta no
  tenía `newClientOrderId` fijo para revisarla con `spot.getOrder` antes de reintentar (181).
- Ahora `boleto_compra_real` trae `orden_venta_emergencia`: SELL MARKET por la cantidad NETA (la de `orden_stop`,
  redondeada hacia abajo también al paso de mercado si Binance tiene uno) y `newClientOrderId` fijo
  (`real.id_venta_emergencia`, «be» + 16 hex). `revisar_boleto_real` la exige (venta a mercado sin precio, misma moneda,
  nunca más que la cantidad del stop, su id fijo). El texto del boleto y el aviso de STOP_NO_PUESTO lo dicen.
- `bots/4_EJECUTOR_REAL.md` paso 4j: copiarla tal cual, sin vender «todo lo libre»; solo si hay menos libre (o la compra
  fue parcial) vende lo libre de esa compra con el mismo id; antes de reintentar, `spot.getOrder`.
- **Decisión de MECÁNICO (para revisar):** una sola venta de emergencia, con la cantidad neta, como se pidió. Si la
  comisión se cobró en BNB, queda en la cuenta la diferencia (la comisión, 0.1 % de la compra, menos que el paso).
- **Prueba vieja que cambió:** `test_arreglo136::test_stop_no_puesto_y_cierre_de_emergencia` (el aviso ya no dice
  «VENDE TODO»).
- **Texto para volver a pegar en Grok Bot:** `bots/4_EJECUTOR_REAL.md` (paso 4j).
- Prueba: `tests/test_arreglo190_venta_de_emergencia.py` (14 casos).

### T8. Arreglo 191: VENTA_ENVIADA antes de vender
- Antes, la venta de un boleto CERRAR solo tenía la regla de texto del 181 (revisar con `spot.getOrder` antes de
  reintentar): nada en el código frenaba un segundo intento.
- Eventos nuevos de `registrar-llenado --real`: **VENTA_ENVIADA** (se anota ANTES de tocar nada: antes de cancelar el
  stop y de vender; así no se agrega tiempo sin stop) y **VENTA_NO_LLENADA** (con `--motivo`, si Binance dice que la
  venta no existe o la rechazó). Reglas en `real._registrar_venta_enviada`: otra VENTA_ENVIADA del mismo boleto sale ❌
  «NO repitas la venta» mientras la anterior no tenga resultado; después de un VENTA_NO_LLENADA se puede reintentar UNA
  vez (`REINTENTOS_VENTA`); un segundo reintento sale ❌ (Ángelo decide en Binance); con la salida ya anotada, ❌. Una
  VENTA_LLENADA sin VENTA_ENVIADA se anota igual, con aviso. Solo para boletos CERRAR con `orden_venta` (cierre y venta
  urgente); no cambian el estado.
- El boleto trae `antes_de_vender` y su texto lo dice primero; `bots/4_EJECUTOR_REAL.md` pasos 5 y 5b también.
- **Para revisar (decisión de MECÁNICO):** la venta de emergencia del boleto de COMPRA (4j) no pide VENTA_ENVIADA (es un
  boleto de compra, no un CERRAR); y si queda una VENTA_ENVIADA sin resultado, la ronda del día siguiente no lo dice
  todavía (el boleto nuevo tiene otro id). Si Ángelo quiere, son dos arreglos chicos.
- **Texto para volver a pegar en Grok Bot:** `bots/4_EJECUTOR_REAL.md` (pasos 5 y 5b).
- Prueba: `tests/test_arreglo191_venta_enviada.py` (10 casos).

### T9. Arreglo 192 (R100): la ronda saltada dice la revisión pendiente y el bloqueo
- Con la ronda real saltada (mantenimiento de Binance o red caída), `ronda_real.pendientes_urgentes` ahora también dice,
  desde el estado local y sin escribir nada: la REVISIÓN justo después de una compra que nadie ha hecho (171), como
  URGENTE, y el bloqueo de compras con su motivo y desde cuándo (solo Ángelo lo quita).
- Prueba: `tests/test_arreglo192_saltada_revision_y_bloqueo.py` (7 casos, con mantenimiento y con la red caída).

### T10. Arreglo 193 (R102 + I9): conciliar también revisa el updateTime
- El 184 rechaza en `registrar-saldo` una foto con updateTime de antes del último llenado. Pero un llenado puede anotarse
  DESPUÉS de registrar la foto: seguía «fresca» por la hora del archivo y `conciliar --real` comparaba contra un estado
  que ya cambió. Ahora `real.conciliar` aplica la misma regla (`_foto_de_antes_del_llenado`): ❌, pide repetir la foto y
  no compara nada. Si la revisión justo después de la compra (171) está pendiente, su mensaje va primero y basta. Una
  foto sin updateTime (formato viejo) sigue como antes.
- Prueba: `tests/test_arreglo193_conciliar_foto_vieja.py` (5 casos).
