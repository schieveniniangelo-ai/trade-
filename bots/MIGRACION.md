# Cambio del equipo de Grok Bot a la v2 "MAREA" (The Boss + 5)

Orden recomendado. Cada paso se puede deshacer; nada de esto toca dinero real (la v2 corre en PAPEL).

## Antes de empezar
1. Instala el sistema en la computadora de Grok Bot siguiendo `INSTALACION.md` (4 comandos) y confirma que `.venv\Scripts\python.exe -m sobreviviente doctor` termina con 👍.
   Todos los comandos se corren dentro de la carpeta del proyecto con `.venv\Scripts\python.exe` (el Python
   del entorno, que tiene los paquetes); el `python` del sistema no los tiene. En Linux o Mac: `.venv/bin/python`.
2. **Apaga las rondas cada 90 minutos** del equipo viejo. En la v2 hay UNA sola ronda al día (6:10 p. m. CDMX).
3. Si hoy hay órdenes reales abiertas del equipo viejo, NO se tocan con este cambio: que el Ejecutor viejo las deje con su stop y las cierre según sus reglas. La v2 empieza con las carteras de papel vacías.

## Paso 1 — Bots que se quedan (cambiar sus instrucciones)
| Bot viejo | Bot nuevo | Texto para pegar |
|---|---|---|
| The Boss | **THE BOSS** | `bots/THE_BOSS.md` |
| Explorador + Analista | **1. RADAR** | `bots/1_RADAR.md` |
| Noticias Crypto | **2. CENTINELA** | `bots/2_CENTINELA.md` |
| Ejecutor | **4. EJECUTOR** | `bots/4_EJECUTOR.md` |
| Contador | **5. CONTADOR** | `bots/5_CONTADOR.md` |

Pega cada texto COMPLETO, reemplazando las instrucciones anteriores.

## Paso 2 — Bot nuevo
| **3. ESTELA** | `bots/3_ESTELA.md` | Guarda la foto diaria de los top traders. |

## Paso 3 — Bots que salen (pausar, no borrar)
- **Guardián de Riesgo**: su trabajo ya lo hace el código (`ronda --verificar` y el motor de riesgo).
- **Francotirador** (Futuros) y **Surfista** (memes): fuera mientras E4 y E5 sigan APAGADAS.
- **Analista**: sus funciones pasaron a RADAR (datos) y al código (señales).

## Paso 4 — Horario diario (hora de CDMX)
| Hora | Bot | Comando |
|---|---|---|
| 6:00 p. m. | RADAR | `.venv\Scripts\python.exe -m sobreviviente verificar` |
| antes de 6:05 | CENTINELA | revisa noticias; actualiza `eventos.json` / `vetos.json` si hace falta |
| 6:05 p. m. | ESTELA | `.venv\Scripts\python.exe -m sobreviviente estela --foto` |
| 6:10 p. m. | THE BOSS | `.venv\Scripts\python.exe -m sobreviviente ronda --modo papel` |
| 6:15 p. m. | EJECUTOR | `.venv\Scripts\python.exe -m sobreviviente ronda --verificar` y `registrar-llenado --ensayo …` por boleto |
| 6:25 p. m. | CONTADOR | `.venv\Scripts\python.exe -m sobreviviente conciliar`, `.venv\Scripts\python.exe -m sobreviviente reporte diario` y `.venv\Scripts\python.exe -m sobreviviente respaldo` (copia de seguridad) |
| 6:30 p. m. | THE BOSS | un solo mensaje a Ángelo |
| Domingo | CONTADOR | además `.venv\Scripts\python.exe -m sobreviviente reporte semanal` |

(6:10 p. m. CDMX = 00:10 UTC. México ya no cambia de horario, así que la hora es fija todo el año.)

## Paso 5 — Primera semana
- Día 1: la primera ronda descarga solo las velas diarias recientes (unos minutos). Las siguientes tardan segundos.
- Revisa al final de la semana `.venv\Scripts\python.exe -m sobreviviente estado --bots`: tareas a tiempo, archivos rechazados y diferencias entre boleto y ensayo. La meta es 0 rechazos y 0 diferencias.

## Para pasar a dinero real (VIVA_MINI) hacen falta TODAS
Compuertas históricas pasadas (ver `VALIDACION_V2.md`), 6 semanas o más en papel, 10 operaciones o más en papel, resultados de papel dentro del rango esperado, cero errores de conciliación y el OK de Ángelo.
