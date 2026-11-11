# SESIÓN LARGA — 10 de noviembre de 2026

Rama `codex/marea-v2`. Empecé en el commit `220500d` y terminé en el que agrega este archivo. Todo está en PAPEL: no
hay llaves de Binance, ni órdenes reales, ni nada que firme peticiones.

## Resumen en cuatro líneas
- **Tanda 11 completa:** T11-1, T11-2 y T11-3 (Arreglos 42, 43 y 44).
- **Pruebas:** de 305 a 434 que pasan (más 1 que se salta en Windows).
- **Cobertura:** de 55 % a 63 % en total; lo que corre a diario quedó entre 84 % y 100 %.
- **No cambié ninguna regla de riesgo ni de dinero.** Lo que creo que debería revisarse está en `PROPUESTAS.md`.

## Commits (del más viejo al más nuevo)

### Tanda 11
| Commit | Qué hace |
|---|---|
| `1da2763` | **Arreglo 42 (T11-1):** la ronda avisa con ℹ️ si CENTINELA o RADAR llevan más de 48 horas sin poner la fecha en "actualizado". El comando diario de RADAR queda anotado en el registro. |
| `53a41a6` | **Arreglo 43 (T11-2):** comando `respaldo` (copia de seguridad en un `.tar.gz` fuera del proyecto) y aviso ℹ️ si no hay respaldo de las últimas 48 horas. |
| `1d867e5` | **Arreglo 44 (T11-3):** cada boleto de compra y de venta a mercado guarda el precio al momento de correr la ronda y cuánto se alejó de la apertura. La boleta semanal lo resume. Solo mide. |

### Más pruebas (el código no cambia)
| Commit | Qué hace |
|---|---|
| `a9d7acf` | **Arreglo 45:** pruebas del reporte diario y de la boleta semanal. |
| `dff8be1` | **Arreglo 46:** pruebas de la foto diaria de ESTELA. |
| `e4d91e0` | **Arreglo 47:** pruebas de conciliar, del ensayo del EJECUTOR y de la calificación de los bots. |
| `0cea58f` | **Arreglo 48:** pruebas del comando `doctor`. |
| `624eaee` | **Arreglo 61:** pruebas de la capa que habla con Binance (reintentos, ruta de respaldo, velas cerradas). |

### Manejo de errores (que nada falle en silencio)
| Commit | Qué hace |
|---|---|
| `152f6fb` | **Arreglo 49:** si un comando truena por algo imprevisto, dice "❌ El comando … falló y NO terminó", lo anota y guarda el detalle en `datos/bots/errores.log`. |
| `518e824` | **Arreglo 50:** un `referencias.json` dañado ya no hace que la ronda diga "NO corrió" después de haber escrito los boletos. Avisa con ⚠️ y termina. |
| `71b4d59` | **Arreglo 51:** la compra o la venta que no se hizo por falta de precio de apertura ahora sale con ⚠️ en el resumen. |
| `fd3a4bc` | **Arreglo 52:** una respuesta rara de Binance ya no tumba la foto de ESTELA ni las consultas de datos. |
| `b3d3d7e` | **Arreglo 53:** un boleto mal formado o de un tipo desconocido sale con ❌ y no tumba la verificación de los demás. |
| `f7c85dd` | **Arreglo 54:** la fecha del reporte diario es la de CDMX aunque la computadora esté en otra zona horaria. |
| `c347491` | **Arreglo 55:** un archivo de bot ilegible cuenta como "viene mal" (MODO SEGURO), no como error técnico. |
| `fecec9f` | **Arreglo 59:** la ronda y la verificación usan las reglas de Binance de hoy, no la copia guardada ayer. |
| `c34f4f1` | **Arreglo 60:** una fecha del futuro en "actualizado" ya no apaga el aviso de bot dormido. |

### Código más simple y mejor explicado (no cambia lo que hace)
| Commit | Qué hace |
|---|---|
| `959ed37` | **Arreglo 56:** una sola función para "existe el archivo o su copia", que estaba repetida en seis lugares. |
| `89956ff` | **Arreglo 57:** tres pedazos de código repetido o difícil de leer, más simples. |
| `eb90a6d` | **Arreglo 58:** explicaciones sencillas en español en las funciones que tocan dinero o stops (solo comentarios). |

### Documentos
| Commit | Qué hace |
|---|---|
| `7a7666c` | **Arreglo 62:** `PROPUESTAS.md`, con los huecos que encontré y no cambié. |
| (este) | **Arreglo 63:** este archivo. |

## Pruebas
| | Pasan | Se saltan | Fallan |
|---|---|---|---|
| Antes (`220500d`) | 305 | 0 | 0 |
| Después | 434 | 1 | 0 |

La prueba que se salta es la de enlaces simbólicos del respaldo: Windows no deja crearlos sin un permiso especial. En
Linux sí corre. Agregué otra prueba que cubre la misma regla sin crear enlaces.

Corrí `pytest` completo antes de cada commit de código. No borré ni debilité ninguna prueba que ya existía. Todas las
pruebas nuevas usan carpetas temporales y no tocan `datos/` ni `salida/`.

## Cobertura
Medida con `coverage run --source=sobreviviente -m pytest`.

| Archivo | Antes | Después |
|---|---|---|
| **Total** | **55 %** | **63 %** |
| `reportes.py` | 28 % | 100 % |
| `estela_vivo.py` | 0 % | 100 % |
| `doctor.py` | 0 % | 96 % |
| `cli_ronda.py` (ronda, verificar, conciliar) | 77 % | 92 % |
| `papel.py` | 90 % | 96 % |
| `respaldo.py` (nuevo) | — | 92 % |
| `archivos.py` | 80 % | 84 % |
| `datos.py` | 42 % | 71 % |
| `__main__.py` | 0 % | 56 % |
| `riesgo.py` | 99 % | 99 % |

El total sube poco porque casi la mitad del código es de estudio histórico (backtest, validación, informes) y no lo
toqué: sigue entre 0 % y 50 %.

## Problemas reales que encontré y arreglé
1. **La ronda podía decir "NO corrió, hoy no hay boletos" con los boletos ya escritos** (Arreglo 50). Pasaba si
   `referencias.json` estaba dañado.
2. **La ronda podía decidir con las reglas de Binance de ayer** sin avisar (Arreglo 59).
3. **Un boleto de tipo desconocido pasaba la verificación con ✅** sin ninguna revisión (Arreglo 53).
4. **El reporte diario podía salir con la fecha de mañana** si la computadora está en UTC (Arreglo 54).
5. **Una venta que no se hizo por falta de precio no llegaba al resumen de Ángelo** (Arreglo 51).

## Lo que no terminé o no hice
- **No arreglé nada de la sección A de `PROPUESTAS.md`**, porque toca riesgo o dinero. El punto más importante es el
  A1: con una ronda al día, el tope diario de pérdida no hace nada. Lo comprobé con una corrida corta: el capital de
  inicio del día se reinicia en cada ronda.
- **No subí la cobertura del código de estudio histórico** (punto B10 de `PROPUESTAS.md`).
- **No probé nada contra Binance real en esta sesión**, salvo lo que ya estaba probado antes. Las pruebas nuevas usan
  clientes falsos. El comando `respaldo` no lo corrí sobre los datos reales: la primera copia real la hará el CONTADOR.
- **No actualicé `AVANCE.md` ni `CAMBIOS.md`** con los Arreglos 42 a 63.

## Cosas que cambian lo que ven Ángelo o los bots
1. **Avisos ℹ️ nuevos en el resumen de la ronda** (no quitan el 👍 ni activan MODO SEGURO): bot dormido y sin
   respaldo. Ahora van al final del resumen, antes de la última línea, para que no empujen fuera a las carteras.
2. **Mañana saldrá "ℹ️ Sin respaldo de datos todavía"** hasta que el CONTADOR corra `python -m sobreviviente respaldo`.
3. **CENTINELA debe poner la fecha de hoy en "actualizado"** en `vetos.json` y `eventos.json` todos los días. Si no,
   a las 48 horas sale el aviso ℹ️. Ya está en `bots/2_CENTINELA.md`.
4. **El CONTADOR tiene un paso nuevo** a las 6:25 p. m.: el respaldo. Ya está en `bots/5_CONTADOR.md` y
   `bots/MIGRACION.md`.
5. **Llaves nuevas en `reglamento.yaml`** (las pedía la tanda 11): `bots.max_horas_sin_actualizar`, `respaldo.*` y
   `reportes.dif_apertura_aviso_pct`. Ningún valor que ya existía cambió.
6. **Instalé la herramienta `coverage`** en el entorno de Python de esta computadora para medir la cobertura.
