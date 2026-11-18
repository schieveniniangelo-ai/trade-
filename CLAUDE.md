# Sobreviviente Pro

Motor de trading en PAPEL (paquete sobreviviente/, Python 3.12+). Zona horaria: America/Mexico_City. Pruebas en tests/.

## Comandos

Todos con el Python del entorno .venv, que tiene los paquetes (el del sistema no los tiene). En Linux o Mac va .venv/bin/python en lugar de .venv\Scripts\python.exe.

* Instalar: .venv\Scripts\python.exe -m pip install -r requirements.lock (para cobertura, también requirements-extra.txt)
* Pruebas: .venv\Scripts\python.exe -m pytest. Una sola prueba: .venv\Scripts\python.exe -m pytest tests/test_arregloXX_nombre.py
* Cobertura del paquete (es el piso, no el TOTAL): .venv\Scripts\python.exe -m pytest --cov=sobreviviente
* Ronda de papel: .venv\Scripts\python.exe -m sobreviviente ronda --modo papel
* Otros (con .venv\Scripts\python.exe -m sobreviviente): doctor, verificar, conciliar, reporte diario|semanal, estado, registrar-llenado, banco-filtros, estela, respaldo

## Reglas que no se negocian

* Papel en paralelo y real en Spot solo con las reglas de la Cartera A (solo largo, solo BTCUSDT con M0; DECISIÓN DE ÁNGELO del 15 nov 2026). El programa nunca tiene llaves ni firma órdenes: EJECUTOR las pone por el conector de Binance. No uses ni pidas llaves de Binance. No leas ni crees .env, *.key ni secretos.
* No cambies reglamento.yaml ni reglas de riesgo (riesgo por operación, topes, caída, exposición, stops, tamaño, universo). Si hay un problema ahí, anótalo en PROPUESTAS.md como DECISIÓN DE ÁNGELO.
* No borres ni aflojes pruebas. En 0c003ba pasan 1000 pruebas en Linux (GitHub, 0 saltadas) y 999 en Windows con 1 saltada: la de enlaces simbólicos de tests/test_arreglo43_respaldo.py; no la aflojes. El arreglo 141 suma 11: al terminar la tanda pasan 1011 en Linux y 1010 en Windows con 1 saltada. La tanda F1 (143–153) suma 107: al terminar pasan 1118 en Linux y 1117 en Windows con 1 saltada (el 152 va el domingo 22 nov y suma las suyas). Después entraron el 154 y el 155: en 5619f84 pasan 1127 en Linux y 1126 en Windows con 1 saltada. La tanda F1 variantes (156–163) suma 58: al terminar pasan 1185 en Linux y 1184 en Windows con 1 saltada (el 152 sigue para el domingo 22 nov). Después entró el 159 (DECISIÓN DE ÁNGELO del 17 nov 2026: escalones sin verificar bloquean la activación) y suma 11 (1196). Luego el 164 (escalones reales de Binance) suma 9: pasan 1205 en Linux y 1204 en Windows con 1 saltada. La tanda de seguridad (165–168) arranca en 26ccdfb: el 165 (stop pegado a la compra) suma 17 (1222); el 166 (saltar la ronda si Binance tiene problemas) suma 21 (1243); el 167 (el papel falla cerrado sin conciliación) suma 8 (1251); el 168 (aviso de capital viejo en papel) suma 5: al terminar la tanda pasan 1256 en Linux y 1255 en Windows con 1 saltada. La tanda chiquita (169–171) arranca en 3c0a2af: el 169 (la conciliación del papel tiene que ser de hoy o de ayer y decir ok) suma 23 (1279); el 170 (anotar la compra real ANTES de mandarla) suma 16 (1295); el 171 (revisar justo después de cada compra real) suma 12: al terminar la tanda pasan 1307 en Linux y 1306 en Windows con 1 saltada. La tanda 172–174 arranca en cc22b80: el 172 (venta urgente del BTC sin anotar) suma 30 (1337); el 173 (no se manda una segunda compra con una sin anotar) suma 8 (1345); el 174 (un archivo de boletos de papel por cartera) suma 13: al terminar la tanda pasan 1358 en Linux y 1357 en Windows con 1 saltada. La tanda 175–184 arranca en 94a17e0: el 175 (llenado real idempotente) suma 9 (1367); el 176 (un renglón ilegible de llenados.jsonl bloquea las compras) suma 10 (1377); el 177 (el candado de la ronda real también para registrar-llenado, conciliar y registrar-saldo) suma 6: pasan 1383 en Linux y 1382 en Windows con 1 saltada.
* La cobertura del paquete no puede bajar del 69 % ni de la cifra de arranque. En la tanda F1 el piso es 89.7 % y ningún commit baja la cifra del anterior: arrancó en 90.82 % (299181b) y quedó en 92.12 % (Linux). En la tanda F1 variantes (156–163) arrancó en 92.12 % (5619f84) y quedó en 92.26 % (Linux). En la tanda de seguridad (165–168) arrancó en 92.26 % (26ccdfb) y quedó en 92.36 % (Linux). En la tanda chiquita (169–171) arrancó en 92.36 % (3c0a2af) y quedó en 92.44 % (Linux). En la tanda 172–174 arrancó en 92.44 % (cc22b80) y quedó en 92.56 % (Linux).
* Un arreglo = un commit, con pytest completo pasando, y luego push a codex/marea-v2. Pruebas nuevas: tests/test_arregloN_....py.
* No prometas ganancias. No ajustes parámetros al pasado.

## Dónde está cada cosa

* riesgo.py: motor compartido (evaluar_candidato); no cambies el comportamiento de las reglas.
* papel.py y cli_ronda.py: ronda diaria de papel y boletos. Sin conciliación el papel no compra, salvo el primer día después de reiniciar-papel (167); la conciliación tiene que decir ok y ser de hoy o de ayer en hora de CDMX (169); la ronda y doctor avisan si una cartera tiene capital viejo (168). Cada cartera tiene su archivo de boletos (salida/boletos_<día>_A.json, _B.json y _C.json) y boletos_<día>.json, con los de todas, sigue siendo lo último que escribe la ronda (la marca de que terminó); ronda --verificar revisa el de cada cartera y que coincidan con el de todas, y el ensayo busca el boleto en el de su cartera (174).
* real.py y ronda_real.py: dinero real (boletos, llenados y ronda real). El boleto de compra trae el stop listo para ponerlo en el acto (165). La ronda real y la de papel se saltan completas si BTCUSDT no está en TRADING o exchangeInfo falla (166). El EJECUTOR anota COMPRA_ENVIADA antes de mandar la compra; conciliar --real marca SIN STOP, bloquea compras y avisa a THE BOSS si una compra enviada no tiene resultado o hay BTC que el estado no conoce; el código no vende solo (170). Después de STOP_PUESTO el EJECUTOR toma la foto y corre conciliar --real en el acto; si no cuadra, compras bloqueadas, y COMPRA_ENVIADA sale ❌ con compras bloqueadas, revisión pendiente o una posición sin stop (171). La ronda real arma un boleto de VENTA URGENTE (CERRAR, motivo SIN_ANOTAR) para el BTC libre que el estado no conoce en una foto fresca: vende solo lo libre, a mercado, con la misma revisión (LOT_SIZE, MARKET_LOT_SIZE, MIN_NOTIONAL); sin foto fresca o abajo del mínimo no hay venta y sale ❌ URGENTE; el EJECUTOR la anota con VENTA_LLENADA, que no toca cerradas ni el bloqueo (172). COMPRA_ENVIADA también sale ❌ «NO mandes la compra» si hay otra compra enviada sin anotar, aunque nadie haya conciliado (173). registrar-llenado --real escribe primero el renglón de llenados.jsonl (fsync) y después el estado; un reintento no duplica nada (175). Un renglón ilegible de llenados.jsonl bloquea las compras (176). registrar-llenado --real, conciliar --real y registrar-saldo corren con el candado de la ronda real (datos/real/ronda.lock): el segundo espera o sale con aviso sin hacer nada (177).
* backtest.py y diario.py: simulación histórica y motores diarios.
* banco_filtros.py, metricas.py y validacion.py: medición fuera de muestra.
* estrategias/: E1 a E7 y M0 a M2. bots/: textos de los bots.

## Flujo de un arreglo

1. Plan primero: archivo, qué cambia y qué debe quedar idéntico.
2. La prueba que falla y luego el cambio mínimo.
3. .venv\Scripts\python.exe -m pytest y .venv\Scripts\python.exe -m pytest --cov=sobreviviente antes de cada commit; si el diff trae cambios de más, se deshacen.
4. Actualizar PROPUESTAS.md.
