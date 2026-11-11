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

### B3. Solo la ronda mide si un bot llegó a tiempo
- **Dónde:** `sobreviviente/archivos.py:291`.
- **Qué pasa hoy:** todas las tareas que no son la ronda se anotan como "a tiempo" sin revisar la hora. En
  `estado --bots`, RADAR, CENTINELA, EJECUTOR y CONTADOR siempre salen puntuales.
- **Qué sugiero:** darle a cada tarea su hora límite (la del horario de `bots/MIGRACION.md`) y medirla.

### B4. "actualizado" lo escribe el mismo bot
- **Dónde:** `sobreviviente/papel.py:147-180`.
- **Qué pasa hoy:** el aviso de bot dormido (Arreglo 42) detecta que CENTINELA o RADAR no pusieron la fecha. No puede
  saber si el bot puso la fecha sin haber revisado de verdad.
- **Qué sugiero:** que el bot escriba también qué fuentes revisó, o que THE BOSS lo confirme una vez por semana.

### B5. Los archivos de las carteras crecen sin límite
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

### B9. Pruebas que miran la carpeta real de respaldos
- **Dónde:** pruebas viejas que corren la ronda completa (por ejemplo `tests/test_arreglo6_datos_malos.py`).
- **Qué pasa hoy:** esas pruebas no cambian `respaldo.carpeta`, así que al correr leen (solo leen) la carpeta
  `~/respaldos-sobreviviente` de la computadora. No fallan por eso, porque el aviso ℹ️ no cambia nada, pero lo ideal es
  que las pruebas no dependan de la computadora.
- **Por qué no lo cambié:** es tocar pruebas que ya existen.

### B10. Cobertura que sigue baja
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
