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
