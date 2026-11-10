"""Carga y validación del reglamento (`reglamento.yaml`).

El reglamento es la única fuente de verdad. Al arrancar, el motor revisa que las
reglas no se contradigan. Si algo choca, NO opera y explica en español qué ajustar.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RUTA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "reglamento.yaml"

ESTADOS_VALIDOS = ("APAGADA", "PAPEL", "VIVA_MINI", "VIVA")
MERCADOS_VALIDOS = ("SPOT", "FUTUROS")
LADOS_VALIDOS = ("LARGO", "CORTO")
CUBETAS_VALIDAS = ("normales", "memes", "futuros")
APALANCAMIENTO_TOPE_ABSOLUTO = 2  # Sección 19: nunca más de 2x, aunque el YAML diga otra cosa.
MAX_PARAMETROS = 4


class ErrorReglamento(Exception):
    """El reglamento tiene choques o valores inválidos. El mensaje explica qué ajustar."""

    def __init__(self, problemas: list[str]):
        self.problemas = problemas
        texto = "El reglamento tiene problemas y el motor NO va a operar:\n" + "\n".join(
            f"  - {p}" for p in problemas
        )
        super().__init__(texto)


@dataclass
class Reglamento:
    """Reglamento ya cargado y validado. `datos` es el diccionario completo del YAML."""

    datos: dict[str, Any]
    ruta: Path | None = None
    avisos: list[str] = field(default_factory=list)

    # ---- atajos de lectura ----
    @property
    def version(self) -> str:
        return str(self.datos["version"])

    @property
    def riesgo(self) -> dict[str, Any]:
        return self.datos["riesgo"]

    @property
    def costos(self) -> dict[str, Any]:
        return self.datos["costos"]

    @property
    def estrategias(self) -> dict[str, dict[str, Any]]:
        return self.datos["estrategias"]

    def riesgo_pct_estrategia(self, clave: str) -> float:
        """Riesgo por operación (en %) para una estrategia, con sus excepciones."""
        excepciones = self.riesgo.get("riesgo_por_estrategia_pct") or {}
        return float(excepciones.get(clave, self.riesgo["riesgo_por_operacion_pct"]))

    def get(self, ruta: str, defecto: Any = None) -> Any:
        """Lee un valor con ruta de puntos, por ejemplo `riesgo.futuros.apalancamiento_max`."""
        nodo: Any = self.datos
        for parte in ruta.split("."):
            if not isinstance(nodo, dict) or parte not in nodo:
                return defecto
            nodo = nodo[parte]
        return nodo

    def para_cartera(self, nombre: str) -> "Reglamento":
        """v2: copia del reglamento con los valores de riesgo de la Cartera A o B (sección `carteras`)."""
        cfg = (self.datos.get("carteras") or {}).get(nombre)
        if not cfg:
            raise ErrorReglamento([f"No existe la cartera '{nombre}' en el reglamento."])
        cambios = {f"riesgo.{k}": v for k, v in cfg.items() if k not in ("nombre", "posiciones_max")}
        nuevo = self.copia_con(cambios)
        if "posiciones_max" in cfg:
            nuevo.datos["riesgo"]["posiciones_max"] = dict(cfg["posiciones_max"])
        nuevo.datos["riesgo"]["riesgo_por_estrategia_pct"] = {}  # en la v2 todas las estrategias usan el riesgo de la cartera
        return nuevo

    def copia_con(self, cambios: dict[str, Any]) -> "Reglamento":
        """Devuelve una copia con algunos valores cambiados (ruta con puntos → valor). Útil en pruebas."""
        nuevo = copy.deepcopy(self.datos)
        for ruta, valor in cambios.items():
            nodo = nuevo
            partes = ruta.split(".")
            for parte in partes[:-1]:
                nodo = nodo.setdefault(parte, {})
            nodo[partes[-1]] = valor
        return Reglamento(datos=nuevo, ruta=self.ruta)


def cargar(ruta: str | Path | None = None, validar_al_cargar: bool = True) -> Reglamento:
    """Lee el YAML y (por defecto) lo valida. Lanza ErrorReglamento si hay choques."""
    ruta = Path(ruta) if ruta else RUTA_POR_DEFECTO
    if not ruta.exists():
        raise ErrorReglamento([f"No encuentro el reglamento en {ruta}."])
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = yaml.safe_load(f)
    except yaml.YAMLError as e:  # pragma: no cover - depende del archivo
        raise ErrorReglamento([f"El archivo {ruta.name} no se puede leer (formato YAML roto): {e}"])
    if not isinstance(datos, dict):
        raise ErrorReglamento(["El reglamento está vacío o no tiene el formato esperado."])
    reg = Reglamento(datos=datos, ruta=ruta)
    if validar_al_cargar:
        reg.avisos = validar(reg)
    return reg


# ---------------------------------------------------------------------------
# Validador
# ---------------------------------------------------------------------------

_CLAVES_OBLIGATORIAS = [
    "version",
    "riesgo.riesgo_por_operacion_pct",
    "riesgo.calor_total_max_pct",
    "riesgo.exposicion_max_posicion_spot_pct",
    "riesgo.cubeta_memes_max_pct",
    "riesgo.futuros.margen",
    "riesgo.futuros.apalancamiento_max",
    "riesgo.futuros.margen_total_max_pct",
    "riesgo.posiciones_max.normales",
    "riesgo.posiciones_max.memes",
    "riesgo.posiciones_max.futuros",
    "riesgo.tope_diario_pct",
    "riesgo.tope_semanal_pct",
    "riesgo.caida_max_desde_pico_pct",
    "riesgo.costos.multiplo_minimo",
    "costos.comision_spot_pct",
    "costos.comision_futuros_taker_pct",
    "costos.deslizamiento_pct.grande",
    "costos.deslizamiento_pct.mediana",
    "costos.deslizamiento_pct.meme",
    "universo.volumen_mediano_min_usdt",
    "estrategias",
    "conciliacion.tolerancia_usdt",
]

_PORCENTAJES = [
    "riesgo.riesgo_por_operacion_pct",
    "riesgo.calor_total_max_pct",
    "riesgo.exposicion_max_posicion_spot_pct",
    "riesgo.cubeta_memes_max_pct",
    "riesgo.futuros.margen_total_max_pct",
    "riesgo.tope_diario_pct",
    "riesgo.tope_semanal_pct",
    "riesgo.caida_max_desde_pico_pct",
]


FRENO_MIN_VECES_RIESGO = 15  # v2: el freno total debe ser ≥ 15 × el riesgo por operación.


def validar(reg: Reglamento, contexto: dict[str, Any] | None = None, _es_cartera: bool = False) -> list[str]:
    """Revisa que el reglamento no se contradiga.

    Regresa una lista de AVISOS (cosas que no impiden operar). Si hay CHOQUES,
    lanza ErrorReglamento con la lista de problemas y qué ajustar.

    `contexto` opcional: {"capital": float, "minimos": [minNotional por moneda del universo]}
    para revisar que el mínimo de Binance sea alcanzable con el capital actual.
    """
    problemas: list[str] = []
    avisos: list[str] = []

    for clave in _CLAVES_OBLIGATORIAS:
        if reg.get(clave) is None:
            problemas.append(f"Falta el valor '{clave}'. Agrégalo al reglamento.")
    if problemas:
        raise ErrorReglamento(problemas)

    for clave in _PORCENTAJES:
        v = reg.get(clave)
        if not isinstance(v, (int, float)) or not (0 < v <= 100):
            problemas.append(f"'{clave}' = {v} no es un porcentaje válido (debe estar entre 0 y 100).")
    if problemas:
        raise ErrorReglamento(problemas)

    r = reg.riesgo
    riesgo_base = float(r["riesgo_por_operacion_pct"])
    excepciones = r.get("riesgo_por_estrategia_pct") or {}
    riesgos = [riesgo_base] + [float(v) for v in excepciones.values()]
    riesgo_max = max(riesgos)
    for k, v in excepciones.items():
        if not (0 < float(v) <= 100):
            problemas.append(f"El riesgo de {k} ({v} %) no es válido.")

    calor = float(r["calor_total_max_pct"])
    pos = r["posiciones_max"]
    total_pos = int(pos["normales"]) + int(pos["memes"]) + int(pos["futuros"])
    if total_pos <= 0:
        problemas.append("Las posiciones máximas suman 0: el sistema nunca podría operar.")

    # 1) Calor total ≥ riesgo por operación
    if calor < riesgo_max:
        problemas.append(
            f"El calor total ({calor} %) es menor que el riesgo de una sola operación ({riesgo_max} %). "
            f"Ninguna operación cabría. Sube el calor total o baja el riesgo por operación."
        )

    # 2) Lo máximo que se puede perder de golpe (si todo toca su stop) ≤ tope diario
    peor_caso = min(calor, riesgo_max * total_pos)
    tope_d = float(r["tope_diario_pct"])
    if peor_caso > tope_d + 1e-9:
        problemas.append(
            f"Si todas las posiciones tocan su stop a la vez se perdería {peor_caso:.2f} %, "
            f"más que el tope diario ({tope_d} %). Baja el calor total a {tope_d} % o menos, "
            f"o sube el tope diario."
        )

    # 3) Orden lógico de los topes
    tope_s = float(r["tope_semanal_pct"])
    caida = float(r["caida_max_desde_pico_pct"])
    if not (tope_d <= tope_s <= caida):
        problemas.append(
            f"Los topes deben ir de menor a mayor: diario ({tope_d} %) ≤ semanal ({tope_s} %) ≤ "
            f"caída máxima ({caida} %)."
        )

    # 4) Futuros
    fut = r["futuros"]
    if str(fut["margen"]).upper() != "AISLADO":
        problemas.append("El margen de Futuros debe ser AISLADO. El margen cruzado está prohibido.")
    apal = fut["apalancamiento_max"]
    if not isinstance(apal, (int, float)) or apal < 1 or apal > APALANCAMIENTO_TOPE_ABSOLUTO:
        problemas.append(
            f"El apalancamiento máximo ({apal}x) no es válido: debe estar entre 1x y "
            f"{APALANCAMIENTO_TOPE_ABSOLUTO}x."
        )

    # 5) El riesgo de una operación no puede ser mayor que su exposición máxima
    expo = float(r["exposicion_max_posicion_spot_pct"])
    if riesgo_max > expo:
        problemas.append(
            f"El riesgo por operación ({riesgo_max} %) es mayor que la exposición máxima por "
            f"posición ({expo} %). Eso no tiene sentido; baja el riesgo."
        )
    memes = float(r["cubeta_memes_max_pct"])
    riesgo_e4 = float(excepciones.get("E4", riesgo_base))
    if int(pos["memes"]) > 0 and riesgo_e4 > memes:
        problemas.append(
            f"El riesgo de memes ({riesgo_e4} %) es mayor que la cubeta de memes ({memes} %)."
        )

    # 6) Costos
    mult = float(r["costos"]["multiplo_minimo"])
    if mult < 1:
        problemas.append(
            f"El múltiplo de costos ({mult}) es menor que 1: aceptaría operaciones que cuestan "
            f"más de lo que pueden ganar."
        )

    # 7) Estrategias
    for clave, e in reg.estrategias.items():
        if e.get("estado") not in ESTADOS_VALIDOS:
            problemas.append(f"{clave}: el estado '{e.get('estado')}' no existe. Usa {ESTADOS_VALIDOS}.")
        if e.get("mercado") not in MERCADOS_VALIDOS:
            problemas.append(f"{clave}: el mercado '{e.get('mercado')}' no existe.")
        if e.get("lado") not in LADOS_VALIDOS:
            problemas.append(f"{clave}: el lado '{e.get('lado')}' no existe.")
        if e.get("cubeta") not in CUBETAS_VALIDAS:
            problemas.append(f"{clave}: la cubeta '{e.get('cubeta')}' no existe.")
        params = e.get("parametros") or {}
        if len(params) > MAX_PARAMETROS:
            problemas.append(
                f"{clave} tiene {len(params)} parámetros; el máximo es {MAX_PARAMETROS} (para evitar sobreajuste)."
            )
        if e.get("mercado") == "SPOT" and e.get("lado") == "CORTO":
            problemas.append(f"{clave}: no se puede ir en corto en Spot.")
        if e.get("mercado") == "FUTUROS":
            ap = e.get("apalancamiento", 1)
            if ap > apal:
                problemas.append(f"{clave} pide {ap}x pero el máximo permitido es {apal}x.")
        if e.get("cubeta") == "memes" and e.get("estado") in ("VIVA_MINI", "VIVA") and not e.get(
            "permitir_vivo", False
        ):
            problemas.append(f"{clave} está en {e.get('estado')} pero Ángelo decidió que las memes solo van en papel.")

    # 7b) v2: freno total suficientemente lejos (con 2 % de riesgo, un freno de 15 % apagaría el sistema
    #     aunque funcionara: Monte Carlo de 20,000 corridas → 82 % de probabilidad de tocarlo).
    if _es_cartera or reg.get("carteras"):
        if caida + 1e-9 < FRENO_MIN_VECES_RIESGO * riesgo_base:
            problemas.append(
                f"El freno total ({caida} %) debe ser al menos {FRENO_MIN_VECES_RIESGO} veces el riesgo por operación "
                f"({riesgo_base} % × {FRENO_MIN_VECES_RIESGO} = {FRENO_MIN_VECES_RIESGO * riesgo_base:g} %). "
                f"Si no, el freno apagaría el sistema por mala suerte normal. Sube el freno o baja el riesgo."
            )

    # 7c) v2: cada cartera de papel (A, B) se valida con TODAS las reglas
    if not _es_cartera and reg.get("carteras"):
        for nombre in [k for k, v in reg.datos["carteras"].items() if isinstance(v, dict)]:
            try:
                validar(reg.para_cartera(nombre), None, _es_cartera=True)
            except ErrorReglamento as e:
                problemas.extend(f"Cartera {nombre}: {p}" for p in e.problemas)

    # 8) Mínimo de Binance alcanzable con el capital actual
    if contexto and contexto.get("capital") and contexto.get("minimos"):
        capital = float(contexto["capital"])
        tope_posicion = capital * expo / 100.0
        alcanzables = [m for m in contexto["minimos"] if m <= tope_posicion]
        if not alcanzables:
            problemas.append(
                f"Con {capital:.2f} USDT, la posición más grande permitida es {tope_posicion:.2f} USDT "
                f"({expo} %), y ninguna moneda del universo tiene un mínimo tan bajo "
                f"(el más bajo es {min(contexto['minimos']):.2f}). Hay que meter más capital o subir la exposición."
            )
        elif len(alcanzables) < len(contexto["minimos"]):
            avisos.append(
                f"Con el capital actual solo {len(alcanzables)} de {len(contexto['minimos'])} monedas "
                f"tienen un mínimo de Binance alcanzable."
            )

    if problemas:
        raise ErrorReglamento(problemas)
    return avisos
