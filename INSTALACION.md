# Instalación en la computadora de Grok Bot

Hace falta **Python 3.11 o más nuevo** y **git**. No hace falta ninguna llave de Binance: el sistema solo lee datos públicos; las órdenes las pone el Ejecutor con su conector.

## 4 comandos
```
git clone --branch codex/marea-v2 https://github.com/schieveniniangelo-ai/trade-.git sobreviviente && cd sobreviviente
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m sobreviviente doctor
```

Todos los comandos usan `.venv\Scripts\python.exe`: es el Python del entorno `.venv`, que tiene los paquetes. El
`python` del sistema no los tiene (daría `ModuleNotFoundError`). Se corren dentro de la carpeta del proyecto. En Linux
o Mac va `.venv/bin/python` en lugar de `.venv\Scripts\python.exe`.

`doctor` revisa la versión de Python, los paquetes, que se pueda escribir en `datos/` y la conexión desde ESA computadora a cada sitio de Binance que usa el sistema. Imprime ✅ o ❌ por renglón y qué hacer con cada ❌. Un ⚠️ no es grave (por ejemplo, "Binance Spot principal" suele estar bloqueado en nubes de EE. UU.; el sistema usa el respaldo oficial solo).

## Arranque en papel (un comando)
```
.venv\Scripts\python.exe -m sobreviviente ronda --modo papel
```
La primera vez descarga solo lo que necesita (velas diarias de los últimos ~14 meses de los pares USDT, no los años de históricos) y crea `datos/papel/cartera_A.json`, `cartera_B.json` y `cartera_C.json` con 46.18 USDT de papel cada una.

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
