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

* Todo es PAPEL. No uses ni pidas llaves de Binance. No leas ni crees .env, *.key ni secretos.
* No cambies reglamento.yaml ni reglas de riesgo (riesgo por operación, topes, caída, exposición, stops, tamaño, universo). Si hay un problema ahí, anótalo en PROPUESTAS.md como DECISIÓN DE ÁNGELO.
* No borres ni aflojes pruebas. En f26c219 pasan 746 pruebas en Linux (GitHub, 0 saltadas) y 745 en Windows con 1 saltada: la de enlaces simbólicos de tests/test_arreglo43_respaldo.py; no la aflojes.
* La cobertura del paquete no puede bajar del 69 % ni de la cifra de arranque.
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
