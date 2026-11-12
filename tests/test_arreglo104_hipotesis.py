"""Arreglo 104: registro de hipótesis (HIPOTESIS.md) y THE BOSS solo puede proponerlas."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMPOS = ["Número", "Fecha de registro", "Qué se cambia (UNA sola cosa)", "Por qué", "Qué se espera (con número)",
          "Cómo y con qué datos nuevos se prueba", "Mínimo de operaciones o días", "Resultado", "Decisión de Ángelo"]


def _hipotesis() -> str:
    return (RAIZ / "HIPOTESIS.md").read_text(encoding="utf-8")


def _plano(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def test_las_cuatro_reglas_van_al_inicio():
    texto = _hipotesis()
    reglas = texto[:texto.index("## Plantilla")]
    assert texto.index("## Reglas") < texto.index("## Plantilla") < texto.index("## Registradas")
    for frase in ("Se registra antes de probar", "Una variable a la vez",
                  "Nunca se cambia `reglamento.yaml` por una hipótesis sin decisión de Ángelo en la ventana del domingo",
                  "Con menos de 30 operaciones el resultado es preliminar"):
        assert frase in _plano(reglas), frase


def test_la_plantilla_y_cada_hipotesis_traen_todos_los_campos_en_orden():
    texto = _hipotesis()
    plantilla = texto[texto.index("## Plantilla"):texto.index("## Registradas")]
    bloques = [plantilla] + re.split(r"\n(?=### Hipótesis \d{3} )", texto[texto.index("## Registradas"):])[1:]
    assert len(bloques) >= 3                                     # la plantilla y las dos que pasaron de PROPUESTAS
    for bloque in bloques:
        posiciones = [bloque.index(f"- **{c}") for c in CAMPOS]
        assert posiciones == sorted(posiciones), bloque[:60]


def test_los_numeros_siguen_sin_huecos():
    numeros = re.findall(r"^### Hipótesis (\d{3}) ", _hipotesis(), flags=re.M)
    assert numeros == [f"{i:03d}" for i in range(1, len(numeros) + 1)]


def test_las_mejoras_de_senal_pendientes_pasaron_sin_cambios():
    propuestas = _plano((RAIZ / "PROPUESTAS.md").read_text(encoding="utf-8"))
    hipotesis = _plano(_hipotesis())
    originales = [
        "**El filtro de funding de E5 compara la tasa de cada cobro sin importar cada cuánto se cobra** (1, 4 u 8 h): "
        "−0.05 % cada hora pesa ocho veces más que cada 8 h. Cambiarlo cambia la señal y obliga a validar otra vez.",
        "**El \"rebote\" de E5 no es espejo exacto de E2:** mira el máximo de 3 velas en vez de 5 y no pide cierre abajo "
        "de la EMA 20. Coincide con lo que dice su descripción, así que es diseño y no bug. Cambiarlo sería otra ronda de "
        "ajustes.",
    ]
    for texto in originales:
        assert texto in propuestas and texto in hipotesis, texto[:50]


def test_the_boss_propone_hipotesis_pero_nunca_las_aplica():
    boss = (RAIZ / "bots" / "THE_BOSS.md").read_text(encoding="utf-8")
    inicio = boss.index("## Hipótesis nuevas")
    fin = boss.find("\n## ", inicio + 1)
    seccion = _plano(boss[inicio:] if fin == -1 else boss[inicio:fin])
    assert "reporte semanal" in seccion and "HIPOTESIS.md" in seccion
    assert "Nunca aplicas una hipótesis" in seccion and "ni editas `HIPOTESIS.md`" in seccion
    for c in CAMPOS[:7]:                                         # el formato de la plantilla, sin resultado ni decisión
        assert c.lower() in seccion.lower(), c
