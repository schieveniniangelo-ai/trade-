# Instalación en la computadora de Grok Bot

Hace falta **Python 3.11 o más nuevo** y **git**. No hace falta ninguna llave de Binance: el sistema solo lee datos públicos; las órdenes las pone el Ejecutor con su conector.

## 3 comandos
```
git clone --branch codex/marea-v2 https://github.com/schieveniniangelo-ai/trade-.git sobreviviente && cd sobreviviente
pip install -r requirements.txt
python -m sobreviviente doctor
```

`doctor` revisa la versión de Python, los paquetes, que se pueda escribir en `datos/` y la conexión desde ESA computadora a cada sitio de Binance que usa el sistema. Imprime ✅ o ❌ por renglón y qué hacer con cada ❌. Un ⚠️ no es grave (por ejemplo, "Binance Spot principal" suele estar bloqueado en nubes de EE. UU.; el sistema usa el respaldo oficial solo).

## Arranque en papel (un comando)
```
python -m sobreviviente ronda --modo papel
```
La primera vez descarga solo lo que necesita (velas diarias de los últimos ~14 meses de los pares USDT, no los años de históricos) y crea `datos/papel/cartera_A.json` y `cartera_B.json` con 46.18 USDT de papel cada una.

## Comandos del día a día
| Comando | Qué hace |
|---|---|
| `python -m sobreviviente ronda --modo papel` | la ronda del día (6:10 p. m. CDMX) |
| `python -m sobreviviente ronda --verificar` | revisa los boletos del día contra el reglamento |
| `python -m sobreviviente registrar-llenado --ensayo --boleto …` | el Ejecutor practica copiando un boleto |
| `python -m sobreviviente conciliar` | revisa que las cuentas de papel cuadren |
| `python -m sobreviviente reporte diario` / `semanal` | reportes para Ángelo |
| `python -m sobreviviente estado` / `estado --bots` | cómo van las carteras / calificación de los bots |
| `python -m sobreviviente estela --foto` | ESTELA: foto diaria de los top traders |
| `python -m sobreviviente verificar` | reglamento, conexión y archivos de los bots |

## Solo para quien quiera repetir la validación (no hace falta en Grok Bot)
```
python -m sobreviviente descargar            # ~40 minutos y ~1 GB: años de históricos
python -m sobreviviente validar --v2 --informe
```
