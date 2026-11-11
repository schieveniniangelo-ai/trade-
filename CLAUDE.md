# Sobreviviente Pro

Motor de trading en PAPEL (paquete sobreviviente/, Python 3.11+). Zona horaria: America/Mexico_City. Pruebas en tests/.

## Comandos

* Instalar: pip install -r requirements.txt (para cobertura, también requirements-extra.txt)
* Pruebas: pytest. Una sola prueba: pytest tests/test_arregloXX_nombre.py
* Cobertura del paquete (es el piso, no el TOTAL): pytest --cov=sobreviviente
* Ronda de papel: python -m sobreviviente ronda --modo papel
* Otros: doctor, verificar, conciliar, reporte diario|semanal, estado, registrar-llenado, banco-filtros, estela, respaldo

## Reglas que no se negocian

* Todo es PAPEL. No uses ni pidas llaves de Binance. No leas ni crees .env, *.key ni secretos.
* No cambies reglamento.yaml ni reglas de riesgo (riesgo por operación, topes, caída, exposición, stops, tamaño, universo). Si hay un problema ahí, anótalo en PROPUESTAS.md como DECISIÓN DE ÁNGELO.
* No borres ni aflojes pruebas. En Linux, en c3d9429, pasan 604 pruebas (0 saltadas). En Windows se salta tests/test_arreglo43_respaldo.py; no la aflojes.
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
3. pytest y pytest --cov=sobreviviente antes de cada commit; si el diff trae cambios de más, se deshacen.
4. Actualizar PROPUESTAS.md.
