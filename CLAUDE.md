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
* No borres ni aflojes pruebas. En 0c003ba pasan 1000 pruebas en Linux (GitHub, 0 saltadas) y 999 en Windows con 1 saltada: la de enlaces simbólicos de tests/test_arreglo43_respaldo.py; no la aflojes. El arreglo 141 suma 11: al terminar la tanda pasan 1011 en Linux y 1010 en Windows con 1 saltada. La tanda F1 (143–153) suma 107: al terminar pasan 1118 en Linux y 1117 en Windows con 1 saltada (el 152 va el domingo 22 nov y suma las suyas). Después entraron el 154 y el 155: en 5619f84 pasan 1127 en Linux y 1126 en Windows con 1 saltada. La tanda F1 variantes (156–163) suma 58: al terminar pasan 1185 en Linux y 1184 en Windows con 1 saltada (el 152 sigue para el domingo 22 nov). Después entró el 159 (DECISIÓN DE ÁNGELO del 17 nov 2026: escalones sin verificar bloquean la activación) y suma 11 (1196). Luego el 164 (escalones reales de Binance) suma 9: pasan 1205 en Linux y 1204 en Windows con 1 saltada. La tanda de seguridad (165–168) arranca en 26ccdfb: el 165 (stop pegado a la compra) suma 17 (1222); el 166 (saltar la ronda si Binance tiene problemas) suma 21: pasan 1243 en Linux y 1242 en Windows con 1 saltada.
* La cobertura del paquete no puede bajar del 69 % ni de la cifra de arranque. En la tanda F1 el piso es 89.7 % y ningún commit baja la cifra del anterior: arrancó en 90.82 % (299181b) y quedó en 92.12 % (Linux). En la tanda F1 variantes (156–163) arrancó en 92.12 % (5619f84) y quedó en 92.26 % (Linux).
* Un arreglo = un commit, con pytest completo pasando, y luego push a codex/marea-v2. Pruebas nuevas: tests/test_arregloN_....py.
* No prometas ganancias. No ajustes parámetros al pasado.

## Dónde está cada cosa

* riesgo.py: motor compartido (evaluar_candidato); no cambies el comportamiento de las reglas.
* papel.py y cli_ronda.py: ronda diaria de papel y boletos.
* backtest.py y diario.py: simulación histórica y motores diarios.
* banco_filtros.py, metricas.py y validacion.py: medición fuera de muestra.
* estrategias/: E1 a E7 y M0 a M2. bots/: textos de los bots.

## Flujo de un arreglo

1. Plan primero: archivo, qué cambia y qué debe quedar idéntico.
2. La prueba que falla y luego el cambio mínimo.
3. .venv\Scripts\python.exe -m pytest y .venv\Scripts\python.exe -m pytest --cov=sobreviviente antes de cada commit; si el diff trae cambios de más, se deshacen.
4. Actualizar PROPUESTAS.md.
