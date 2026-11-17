# Instalación en la computadora de Grok Bot

Hace falta **Python 3.12 o más nuevo** y **git**. No hace falta ninguna llave de Binance: el sistema solo lee datos públicos; las órdenes las pone el Ejecutor con su conector.

## 4 comandos
```
git clone --branch codex/marea-v2 https://github.com/schieveniniangelo-ai/trade-.git sobreviviente && cd sobreviviente
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\python.exe -m sobreviviente doctor
```

`requirements.lock` trae las versiones exactas de los paquetes con las que pasan todas las pruebas (se probó con
Python 3.12). No instales desde `requirements.txt` en esta
computadora: ese archivo solo dice los mínimos y podría bajar otras versiones.

Todos los comandos usan `.venv\Scripts\python.exe`: es el Python del entorno `.venv`, que tiene los paquetes. El
`python` del sistema no los tiene (daría `ModuleNotFoundError`). Se corren dentro de la carpeta del proyecto. En Linux
o Mac va `.venv/bin/python` en lugar de `.venv\Scripts\python.exe`.

`doctor` revisa la versión de Python, los paquetes, que se pueda escribir en `datos/` y la conexión desde ESA computadora a cada sitio de Binance que usa el sistema. Imprime ✅ o ❌ por renglón y qué hacer con cada ❌. Un ⚠️ no es grave (por ejemplo, "Binance Spot principal" suele estar bloqueado en nubes de EE. UU.; el sistema usa el respaldo oficial solo).

## Arranque en papel (un comando)
```
.venv\Scripts\python.exe -m sobreviviente ronda --modo papel
```
La primera vez descarga solo lo que necesita (velas diarias de los últimos ~14 meses de los pares USDT, no los años de históricos) y crea `datos/papel/cartera_A.json`, `cartera_B.json` y `cartera_C.json` con el capital de `carteras.capital_inicial` del reglamento (142.54 USDT desde el 15 nov 2026) de papel cada una.

## Comandos del día a día
| Comando | Qué hace |
|---|---|
| `.venv\Scripts\python.exe -m sobreviviente ronda --modo papel` | la ronda del día (6:10 p. m. CDMX) |
| `.venv\Scripts\python.exe -m sobreviviente ronda --verificar` | revisa los boletos del día contra el reglamento |
| `.venv\Scripts\python.exe -m sobreviviente registrar-llenado --ensayo --boleto …` | el Ejecutor practica copiando un boleto |
| `.venv\Scripts\python.exe -m sobreviviente conciliar` | revisa que las cuentas de papel cuadren |
| `.venv\Scripts\python.exe -m sobreviviente reporte diario` / `semanal` | reportes para Ángelo |
| `.venv\Scripts\python.exe -m sobreviviente estado` / `estado --bots` | cómo van las carteras / calificación de los bots |
| `.venv\Scripts\python.exe -m sobreviviente estela --foto` | ESTELA: foto diaria de los top traders |
| `.venv\Scripts\python.exe -m sobreviviente verificar` | reglamento, conexión y archivos de los bots |
| `.venv\Scripts\python.exe -m sobreviviente respaldo` | copia de seguridad del estado de papel, los boletos y los archivos de los bots |

## Dinero real (Spot, solo M0/BTC con las reglas de la Cartera A; DECISIÓN DE ÁNGELO del 15 nov 2026)
El programa **nunca** tiene llaves de Binance ni pone órdenes: solo emite boletos REALES y lee los archivos que el
EJECUTOR guarda con lo que contestó Binance (por el conector). El papel sigue corriendo igual, en paralelo, para comparar.
Todo se corre en Windows desde la carpeta del proyecto, con el Python del `.venv`:

| Comando | Quién y cuándo | Qué hace |
|---|---|---|
| `.venv\Scripts\python.exe -m sobreviviente registrar-saldo --cuenta datos/real/entrada/cuenta.json --ordenes datos/real/entrada/ordenes.json` | EJECUTOR, 6:00 p. m. y después de poner o vender | guarda la foto de saldo (las respuestas tal cual de `spot.getAccount` y `spot.getOpenOrders`) |
| `.venv\Scripts\python.exe -m sobreviviente ronda --modo real --simular` | THE BOSS, el día de prueba | corre toda la ronda real y solo imprime: no escribe nada y no hay nada que poner |
| `.venv\Scripts\python.exe -m sobreviviente ronda --modo real` | THE BOSS, 6:10 p. m., después de `ronda --modo papel` | la ronda real: escribe `salida/boletos_real_<día>.json` |
| `.venv\Scripts\python.exe -m sobreviviente ronda --verificar --real` | EJECUTOR, 6:15 p. m. | revisa los boletos REALES del día; solo se ponen los que salen ✅ |
| `.venv\Scripts\python.exe -m sobreviviente registrar-llenado --real --boleto <ID> --evento <EVENTO> …` | EJECUTOR, después de poner las órdenes (en una compra, ya con el stop puesto) | anota lo que contestó Binance (COMPRA_LLENADA, STOP_PUESTO, VENTA_LLENADA, …) |
| `.venv\Scripts\python.exe -m sobreviviente conciliar --real` | CONTADOR, 6:25 p. m. | la foto de saldo contra `datos/real/cartera_REAL.json`; «SIN STOP» sale primero |
| `.venv\Scripts\python.exe -m sobreviviente reporte diario --real` | CONTADOR, 6:25 p. m. | reporte con lo REAL y el PAPEL en secciones separadas |
| `.venv\Scripts\python.exe -m sobreviviente estado --real` | cuando THE BOSS lo pida | capital real, posiciones con su stop y compras bloqueadas |
| `.venv\Scripts\python.exe -m sobreviviente ajustar-capital-real --usdt <total> --ok-angelo "<OK de Ángelo>"` | SOLO con el OK de Ángelo | registra un depósito, retiro o comisión rara |
| `.venv\Scripts\python.exe -m sobreviviente reanudar --cartera REAL --ok-angelo "<OK de Ángelo>"` | SOLO con el OK de Ángelo | quita el freno o el bloqueo de compras de la cartera real |

Los textos de los bots para el real son `bots/4_EJECUTOR_REAL.md` y `bots/5_CONTADOR_REAL.md` (los de papel se quedan),
más la sección «Modo real» de `bots/THE_BOSS.md`. `respaldo` también copia `datos/real/`.

## Empezar el papel de cero (reiniciar-papel)
- `.venv\Scripts\python.exe -m sobreviviente reiniciar-papel` solo explica qué haría; no cambia nada.
- `.venv\Scripts\python.exe -m sobreviviente reiniciar-papel --si` mueve TODO `datos/papel/` (carteras A, B y C, referencias, rondas viejas, bitácora, conciliación, descartes) a `datos/papel/archivo_<fecha y hora UTC>Z/`. No borra nada y no toca `datos/bots/` (registro de los bots), `datos/real/` ni `datos/cache/`.
- Córrelo una sola vez y FUERA de la hora de la ronda: si la ronda está corriendo, se niega (❌) y no mueve nada. La siguiente ronda de papel crea A, B y C con `carteras.capital_inicial` y ese día como día 1 (`estado` dice `Papel: día 1`).
- Correrlo otra vez no pierde nada: si `datos/papel/` ya está vacío, solo lo dice.

## Respaldo (copia de seguridad)
- `.venv\Scripts\python.exe -m sobreviviente respaldo` guarda un archivo `respaldo-AAAA-MM-DD-HHMM.tar.gz` (hora UTC) en la carpeta `respaldo.carpeta` del reglamento (por defecto `~/respaldos-sobreviviente`, fuera del proyecto). Lleva `datos/papel/`, `datos/estela/`, `datos/bots/`, `salida/`, los archivos de los bots (`vetos.json`, `eventos.json`, `exclusiones.json`, `memes.json`) y `reglamento.yaml`. Solo copia: no cambia ni borra nada del proyecto. Conserva los últimos 14.
- **Conviene que esa carpeta esté en otro disco o en una carpeta sincronizada** (por ejemplo, una memoria USB o una carpeta de nube). Si el respaldo vive en el mismo disco y el disco se daña, se pierden los dos.
- Lo corre el CONTADOR a diario (6:25 p. m.). Si pasan más de 48 horas sin respaldo, la ronda lo avisa con ℹ️.
- **Cómo restaurar a mano** (no hay comando de restaurar, a propósito):
  1. Apaga la ronda: que ningún bot corra `ronda` mientras restauras.
  2. Guarda aparte lo que haya ahora en `datos/papel/` y `salida/` (por si acaso).
  3. Descomprime el respaldo que quieras dentro de la carpeta del proyecto: `tar -xzf ~/respaldos-sobreviviente/respaldo-AAAA-MM-DD-HHMM.tar.gz -C <carpeta del proyecto>`. Los archivos caen en su lugar (`datos/papel/…`, `salida/…`).
  4. Corre `.venv\Scripts\python.exe -m sobreviviente conciliar` y `.venv\Scripts\python.exe -m sobreviviente estado` y confirma que todo cuadra antes de volver a prender la ronda.

## Solo para quien quiera repetir la validación (no hace falta en Grok Bot)
```
.venv\Scripts\python.exe -m sobreviviente descargar            # ~40 minutos y ~1 GB: años de históricos
.venv\Scripts\python.exe -m sobreviviente validar --v2 --informe
```
