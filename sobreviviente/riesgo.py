"""Motor de riesgo: el Guardián hecho código.

Todas las decisiones de dinero pasan por aquí, tanto en el backtest como en vivo
(es exactamente el mismo código). Cada "sí" y cada "no" sale con su razón.

Reglas clave:
- El riesgo se mide en % del capital. Nunca se infla para alcanzar el mínimo de Binance.
- Si una operación no cabe, se salta y se anota cuánto capital habría hecho falta.
- Los bots pueden decir NO (vetos), nunca "más".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from . import descartes as DS
from .exchange import Filtros, redondear_abajo
from .reglamento import Reglamento

LARGO = "LARGO"
CORTO = "CORTO"


# ---------------------------------------------------------------------------
# Estructuras
# ---------------------------------------------------------------------------

@dataclass
class Posicion:
    """Una posición abierta."""

    simbolo: str
    mercado: str           # SPOT o FUTUROS
    lado: str              # LARGO o CORTO
    estrategia: str        # E1..E5
    cubeta: str            # normales, memes o futuros
    entrada: float
    stop: float
    cantidad: float
    apalancamiento: float = 1.0
    abierta_en: datetime | None = None

    @property
    def valor(self) -> float:
        """Valor de la posición en USDT al precio de entrada."""
        return self.cantidad * self.entrada

    @property
    def riesgo_usdt(self) -> float:
        """Lo que se perdería hoy si toca el stop (0 si el stop ya protege la entrada)."""
        if self.lado == LARGO:
            return max(0.0, (self.entrada - self.stop) * self.cantidad)
        return max(0.0, (self.stop - self.entrada) * self.cantidad)

    @property
    def margen(self) -> float:
        """Margen usado (solo Futuros)."""
        if self.mercado != "FUTUROS":
            return 0.0
        return self.valor / max(self.apalancamiento, 1.0)


@dataclass
class Candidato:
    """Una señal que propone una estrategia, antes de pasar por el riesgo."""

    simbolo: str
    mercado: str
    lado: str
    estrategia: str
    cubeta: str
    precio_entrada: float
    stop: float
    meta: float | None = None             # None = la estrategia sale con stop dinámico
    precio_limite_stop: float | None = None
    comision_pct: float = 0.1             # por lado
    deslizamiento_pct: float = 0.05       # por lado
    apalancamiento: float = 1.0
    razon: str = ""

    @property
    def distancia(self) -> float:
        """Distancia de la entrada al stop, en precio (siempre positiva si el stop es válido)."""
        return (self.precio_entrada - self.stop) if self.lado == LARGO else (self.stop - self.precio_entrada)


@dataclass
class EstadoCartera:
    """Foto de la cartera en este momento (se recalcula cada ronda con el saldo conciliado)."""

    capital: float                      # Capital total (Spot + Futuros), en USDT
    pico: float                         # Capital más alto alcanzado
    capital_inicio_dia: float           # Capital de la ronda anterior (referencia del tope diario; día UTC)
    capital_inicio_semana: float        # Capital al inicio de la semana (lunes, CDMX)
    posiciones: list[Posicion] = field(default_factory=list)
    efectivo_spot: float | None = None      # USDT libre en Spot (None = no limitar)
    efectivo_futuros: float | None = None   # USDT libre en Futuros (None = no limitar)
    pausa_hasta: datetime | None = None
    pausa_motivo: str = ""
    detenido: bool = False              # Caída máxima: se necesita el OK de Ángelo
    rachas: dict[str, int] = field(default_factory=dict)          # pérdidas seguidas por estrategia
    saltar_rondas: dict[str, int] = field(default_factory=dict)   # rondas que le faltan por saltar
    pausa_estrategia_hasta: dict[str, datetime] = field(default_factory=dict)
    conciliacion_ok: bool = True
    datos_ok: bool = True

    @property
    def calor_usdt(self) -> float:
        """El "calor": cuánto dinero (USDT) se perdería si TODAS las posiciones abiertas tocaran su stop a la vez."""
        return sum(p.riesgo_usdt for p in self.posiciones)

    def exposicion_cubeta(self, cubeta: str) -> float:
        """Cuánto dinero (USDT) está metido en posiciones de esa cubeta (por ejemplo "memes" o "normales")."""
        return sum(p.valor for p in self.posiciones if p.cubeta == cubeta)

    def margen_futuros(self) -> float:
        """Margen (garantía en USDT) que ocupan las posiciones de Futuros abiertas."""
        return sum(p.margen for p in self.posiciones)

    def contar(self, cubeta: str) -> int:
        """Cuántas posiciones abiertas hay en esa cubeta (para respetar el máximo de posiciones)."""
        return sum(1 for p in self.posiciones if p.cubeta == cubeta)


@dataclass
class ResultadoTamano:
    """Resultado del cálculo de tamaño."""

    ok: bool
    cantidad: float = 0.0
    valor_usdt: float = 0.0
    riesgo_usdt: float = 0.0
    riesgo_pct: float = 0.0
    recortada: bool = False
    saltada_por_capital: bool = False
    capital_necesario: float | None = None
    razon: str = ""


@dataclass
class Decision:
    """Decisión final del motor de riesgo sobre un candidato."""

    aprobada: bool
    candidato: Candidato
    cantidad: float = 0.0
    valor_usdt: float = 0.0
    riesgo_usdt: float = 0.0
    riesgo_pct: float = 0.0
    factor: float = 1.0
    verificaciones: list[str] = field(default_factory=list)
    razones: list[str] = field(default_factory=list)
    saltada_por_capital: bool = False
    capital_necesario: float | None = None
    solo_papel: bool = False
    codigo: str = ""                    # código estable del motivo (ver descartes.py); solo para registrar

    @property
    def razon(self) -> str:
        return "; ".join(self.razones) if self.razones else "aprobada"


# ---------------------------------------------------------------------------
# Régimen y volatilidad → factor de riesgo
# ---------------------------------------------------------------------------

def clasificar_volatilidad(reg: Reglamento, percentil: float | None) -> str:
    """Convierte el percentil del ATR% en BAJA, NORMAL, ALTA o EXTREMA."""
    if percentil is None:
        return "NORMAL"
    a = reg.riesgo["ajustes"]
    if percentil > a["vol_extrema_percentil"]:
        return "EXTREMA"
    if percentil > a["vol_alta_percentil"]:
        return "ALTA"
    if percentil < a["vol_baja_percentil"]:
        return "BAJA"
    return "NORMAL"


def factor_regimen(
    reg: Reglamento,
    lado: str,
    cubeta: str,
    regimen_btc: str,
    vol_moneda: str = "NORMAL",
    vol_btc: str = "NORMAL",
) -> tuple[float, str | None]:
    """Regresa (factor de riesgo, razón de bloqueo). Si hay bloqueo, el factor es 0."""
    if vol_btc == "EXTREMA" or vol_moneda == "EXTREMA":
        return 0.0, "volatilidad EXTREMA: sin entradas nuevas"
    if lado == LARGO and cubeta == "normales" and regimen_btc == "BAJISTA":
        return 0.0, "BTC BAJISTA: no se abren largos en monedas normales"
    a = reg.riesgo["ajustes"]
    factor = 1.0
    if cubeta == "memes" and regimen_btc == "BAJISTA":
        factor *= float(a["btc_bajista_factor_memes"])
    if vol_moneda == "ALTA" or vol_btc == "ALTA":
        factor *= float(a["vol_alta_factor"])
    return factor, None


# ---------------------------------------------------------------------------
# Costos
# ---------------------------------------------------------------------------

def costo_ida_vuelta_pct(cand: Candidato) -> float:
    """Costo de entrar y salir, en % del precio (comisión + deslizamiento, dos veces)."""
    return 2.0 * (cand.comision_pct + cand.deslizamiento_pct)


def revisar_costos(reg: Reglamento, cand: Candidato) -> tuple[bool, str]:
    """La ganancia hasta la meta debe ser ≥ múltiplo × costo de ida y vuelta."""
    mult = float(reg.riesgo["costos"]["multiplo_minimo"])
    if cand.meta is not None:
        ganancia = abs(cand.meta - cand.precio_entrada)
    else:
        ganancia = float(reg.riesgo["costos"]["meta_nominal_r"]) * cand.distancia
    ganancia_pct = ganancia / cand.precio_entrada * 100.0
    costo = costo_ida_vuelta_pct(cand)
    if ganancia_pct + 1e-12 < mult * costo:
        return False, (
            f"la meta deja {ganancia_pct:.2f} % y entrar y salir cuesta {costo:.2f} %; "
            f"se pide al menos {mult:g} veces el costo"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Tamaño de la posición
# ---------------------------------------------------------------------------

def cantidad_neta(cantidad: float, comision_pct: float, paso: float) -> float:
    """Lo que queda después de la compra si la comisión se cobra en la moneda comprada:
    cantidad × (1 − comisión/100), redondeada hacia ABAJO al paso de Binance. Con comisión 0 es la misma cantidad."""
    if not comision_pct:
        return float(cantidad)
    from decimal import Decimal
    return redondear_abajo(float(Decimal(str(cantidad)) * (1 - Decimal(str(comision_pct)) / 100)), paso)


def calcular_tamano(
    capital: float,
    riesgo_pct: float,
    factor: float,
    cand: Candidato,
    filtros: Filtros,
    tope_valor_usdt: float,
    modo: str = "riesgo",
    comision_en_moneda_pct: float = 0.0,
) -> ResultadoTamano:
    """Calcula cuánto comprar (o vender en corto).

    Modo "riesgo" (A, B y todo lo de la v1):
    1. riesgo_usdt = capital × riesgo_% × factor
    2. cantidad = riesgo_usdt / distancia al stop, redondeada hacia ABAJO al paso de Binance
    3. Si vale más que `tope_valor_usdt` (exposición máxima disponible), se recorta.
    Modo "exposicion" (solo la Cartera C de papel): la compra más grande que permite el tope de
    exposición (× factor de régimen/volatilidad). El riesgo resultante (valor × distancia al stop)
    debe caber en el riesgo por operación de esa cartera.
    En los dos: la compra Y la venta en el stop deben cumplir el mínimo de Binance. Si no: se salta,
    se anota como "saltada por capital" y se calcula el capital que habría hecho falta.
    Nunca se infla el riesgo.
    """
    if capital <= 0:
        return ResultadoTamano(ok=False, razon="capital en cero")
    dist = cand.distancia
    if dist <= 0:
        return ResultadoTamano(ok=False, razon="el stop está del lado equivocado de la entrada")
    if factor <= 0 or riesgo_pct <= 0:
        return ResultadoTamano(ok=False, razon="riesgo en cero")

    riesgo_obj = capital * riesgo_pct / 100.0 * factor
    tope = max(0.0, tope_valor_usdt)
    if modo == "exposicion":
        cantidad = redondear_abajo(tope * factor / cand.precio_entrada, filtros.paso)
        if cantidad * dist > capital * riesgo_pct / 100.0 + 1e-9:
            cantidad = redondear_abajo(capital * riesgo_pct / 100.0 / dist, filtros.paso)
    else:
        cantidad = redondear_abajo(riesgo_obj / dist, filtros.paso)
    recortada = False
    if cantidad * cand.precio_entrada > tope:
        cantidad = redondear_abajo(tope / cand.precio_entrada, filtros.paso)
        recortada = True

    precio_salida_stop = cand.precio_limite_stop if cand.precio_limite_stop else cand.stop
    valor = cantidad * cand.precio_entrada
    # El stop vende lo que queda DESPUÉS de la comisión (si se cobra en la moneda comprada): el mínimo se revisa con eso
    cantidad_stop = cantidad_neta(cantidad, comision_en_moneda_pct, filtros.paso)
    valor_en_stop = cantidad_stop * precio_salida_stop

    fallas = []
    if cantidad <= 0 or cantidad_stop <= 0 or cantidad_stop < filtros.cantidad_min:
        fallas.append("la cantidad no llega al mínimo de Binance")
    if valor < filtros.minimo_usdt:
        fallas.append(f"la compra ({valor:.2f} USDT) no llega al mínimo de {filtros.minimo_usdt:g} USDT")
    if valor_en_stop < filtros.minimo_usdt:
        fallas.append(
            f"la venta en el stop ({valor_en_stop:.2f} USDT) no llega al mínimo de {filtros.minimo_usdt:g} USDT"
        )
    if fallas:
        if modo == "exposicion":
            # con tamaño por exposición, el capital necesario solo depende del tope de exposición
            precio_salida = cand.precio_limite_stop if cand.precio_limite_stop else cand.stop
            cant_min = max(filtros.cantidad_min, filtros.minimo_usdt / max(precio_salida, 1e-12), filtros.paso)
            prop = (tope * factor / capital) if capital > 0 and tope > 0 else None
            necesario = round(cant_min * cand.precio_entrada / prop, 2) if prop else None
        else:
            necesario = capital_necesario(riesgo_pct * factor, cand, filtros, capital, tope)
        return ResultadoTamano(
            ok=False,
            saltada_por_capital=True,
            capital_necesario=necesario,
            razon="saltada por capital: " + "; ".join(fallas),
        )

    riesgo_real = cantidad * dist
    return ResultadoTamano(
        ok=True,
        cantidad=cantidad,
        valor_usdt=valor,
        riesgo_usdt=riesgo_real,
        riesgo_pct=riesgo_real / capital * 100.0,
        recortada=recortada,
        razon="recortada por exposición máxima" if recortada else "",
    )


def capital_necesario(
    riesgo_pct_efectivo: float, cand: Candidato, filtros: Filtros, capital: float, tope_actual: float
) -> float:
    """Capital mínimo con el que esta operación sí habría cabido, sin inflar el riesgo."""
    precio_salida = cand.precio_limite_stop if cand.precio_limite_stop else cand.stop
    cant_min = max(filtros.cantidad_min, filtros.minimo_usdt / max(precio_salida, 1e-12), filtros.paso)
    # por riesgo: cant_min × distancia = capital × riesgo%
    por_riesgo = cant_min * cand.distancia / (riesgo_pct_efectivo / 100.0)
    # por exposición: el tope crece proporcional al capital
    proporcion_tope = (tope_actual / capital) if capital > 0 and tope_actual > 0 else None
    por_expo = cant_min * cand.precio_entrada / proporcion_tope if proporcion_tope else 0.0
    return round(max(por_riesgo, por_expo), 2)


# ---------------------------------------------------------------------------
# Futuros: liquidación
# ---------------------------------------------------------------------------

def precio_liquidacion(entrada: float, lado: str, apalancamiento: float, mantenimiento_pct: float) -> float:
    """Estimación del precio de liquidación en margen aislado (aproximada y conservadora)."""
    m = mantenimiento_pct / 100.0
    if lado == CORTO:
        return entrada * (1 + 1 / apalancamiento - m)
    return entrada * (1 - 1 / apalancamiento + m)


def revisar_liquidacion(reg: Reglamento, cand: Candidato) -> tuple[bool, str]:
    """El precio de liquidación debe estar al menos `colchon_liquidacion` veces más lejos que el stop."""
    fut = reg.riesgo["futuros"]
    liq = precio_liquidacion(cand.precio_entrada, cand.lado, cand.apalancamiento, float(fut["tasa_mantenimiento_pct"]))
    dist_liq = abs(liq - cand.precio_entrada)
    if cand.distancia * float(fut["colchon_liquidacion"]) > dist_liq:
        return False, (
            f"el stop está demasiado cerca de la liquidación estimada ({liq:.6g}); "
            f"baja el apalancamiento o acerca el stop"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Topes diario / semanal / caída máxima
# ---------------------------------------------------------------------------

def _tz(reg: Reglamento) -> ZoneInfo:
    return ZoneInfo(reg.get("zona_horaria", "America/Mexico_City"))


def inicio_dia(reg: Reglamento, ahora: datetime) -> datetime:
    """Medianoche (CDMX) del día de `ahora`."""
    local = ahora.astimezone(_tz(reg))
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def siguiente_dia(reg: Reglamento, ahora: datetime) -> datetime:
    return inicio_dia(reg, ahora) + timedelta(days=1)


def inicio_dia_utc(ahora: datetime) -> datetime:
    """00:00 UTC del día UTC de `ahora`. Es el "día" del tope diario: la ronda oficial corre a las 00:10 UTC."""
    return ahora.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def siguiente_dia_utc(ahora: datetime) -> datetime:
    """00:00 UTC del día UTC siguiente: ahí termina la pausa del tope diario."""
    return inicio_dia_utc(ahora) + timedelta(days=1)


def inicio_semana(reg: Reglamento, ahora: datetime) -> datetime:
    """Lunes 00:00 (CDMX) de la semana de `ahora`."""
    d = inicio_dia(reg, ahora)
    return d - timedelta(days=d.weekday())


def siguiente_lunes(reg: Reglamento, ahora: datetime) -> datetime:
    return inicio_semana(reg, ahora) + timedelta(days=7)


def aplicar_topes(reg: Reglamento, estado: EstadoCartera, ahora: datetime) -> list[str]:
    """Revisa los topes con el capital actual y activa las pausas que toquen.

    Regresa la lista de mensajes de pausa que se activaron (vacía si nada cambió).
    """
    r = reg.riesgo
    mensajes = []
    estado.pico = max(estado.pico, estado.capital)
    caida_pico = (estado.pico - estado.capital) / estado.pico * 100.0 if estado.pico > 0 else 0.0
    if caida_pico >= float(r["caida_max_desde_pico_pct"]) - 1e-9 and not estado.detenido:
        estado.detenido = True
        mensajes.append(
            f"CAÍDA MÁXIMA: el capital bajó {caida_pico:.1f} % desde su pico. Todo se detiene hasta que Ángelo dé el OK."
        )
    perdida_semana = (estado.capital_inicio_semana - estado.capital) / estado.capital_inicio_semana * 100.0 \
        if estado.capital_inicio_semana > 0 else 0.0
    perdida_dia = (estado.capital_inicio_dia - estado.capital) / estado.capital_inicio_dia * 100.0 \
        if estado.capital_inicio_dia > 0 else 0.0
    if perdida_semana >= float(r["tope_semanal_pct"]) - 1e-9:
        hasta = siguiente_lunes(reg, ahora)
        if estado.pausa_hasta is None or estado.pausa_hasta < hasta:
            estado.pausa_hasta = hasta
            estado.pausa_motivo = f"tope semanal: se perdió {perdida_semana:.1f} % en la semana"
            mensajes.append(f"PAUSA hasta el lunes: {estado.pausa_motivo}.")
    elif perdida_dia >= float(r["tope_diario_pct"]) - 1e-9:
        # Tope diario: no se abren compras nuevas hasta las 00:00 UTC del día UTC siguiente (lo abierto sigue con
        # su stop). Así los reintentos del mismo día UTC siguen sin comprar y la ronda siguiente (00:10 UTC) mide
        # otra vez contra el capital de esta ronda.
        hasta = siguiente_dia_utc(ahora)
        if estado.pausa_hasta is None or estado.pausa_hasta < hasta:
            estado.pausa_hasta = hasta
            estado.pausa_motivo = (f"tope diario: se perdió {perdida_dia:.1f} % hoy "
                                   f"(tope {float(r['tope_diario_pct']):.1f} %)")
            mensajes.append(f"PAUSA hasta mañana: {estado.pausa_motivo}.")
    return mensajes


def registrar_resultado(
    reg: Reglamento, estado: EstadoCartera, estrategia: str, ganancia_usdt: float, ahora: datetime
) -> list[str]:
    """Actualiza rachas y pausas de una estrategia al cerrar una operación."""
    r = reg.riesgo["rachas"]
    mensajes = []
    if ganancia_usdt < 0:
        estado.rachas[estrategia] = estado.rachas.get(estrategia, 0) + 1
    else:
        estado.rachas[estrategia] = 0
    n = estado.rachas[estrategia]
    if estrategia == "E4":
        if n >= int(r["surfista_perdidas"]):
            hasta = ahora + timedelta(hours=float(r["surfista_pausa_horas"]))
            estado.pausa_estrategia_hasta[estrategia] = hasta
            estado.rachas[estrategia] = 0
            mensajes.append(f"E4 perdió {n} seguidas: pausa de {r['surfista_pausa_horas']} horas.")
    elif n >= int(r["perdidas_para_saltar"]):
        estado.saltar_rondas[estrategia] = int(r["rondas_a_saltar"])
        estado.rachas[estrategia] = 0
        mensajes.append(f"{estrategia} perdió {n} seguidas: se salta {r['rondas_a_saltar']} ronda.")
    return mensajes


def consumir_ronda(estado: EstadoCartera) -> None:
    """Al terminar una ronda, descuenta las rondas que cada estrategia tenía que saltarse."""
    for k in list(estado.saltar_rondas):
        estado.saltar_rondas[k] -= 1
        if estado.saltar_rondas[k] <= 0:
            del estado.saltar_rondas[k]


# ---------------------------------------------------------------------------
# Eventos y vetos
# ---------------------------------------------------------------------------

_IMPORTANCIA = {"BAJA": 1, "MEDIA": 2, "ALTA": 3}


def evento_activo(reg: Reglamento, eventos: Iterable[dict[str, Any]], ahora: datetime) -> dict[str, Any] | None:
    """Regresa el evento fuerte que bloquea entradas en este momento, o None."""
    cfg = reg.riesgo["eventos"]
    antes = timedelta(minutes=float(cfg["minutos_antes"]))
    despues = timedelta(minutes=float(cfg["minutos_despues"]))
    minimo = _IMPORTANCIA.get(str(cfg["importancia_minima"]).upper(), 3)
    for ev in eventos:
        if _IMPORTANCIA.get(str(ev.get("importancia", "")).upper(), 0) < minimo:
            continue
        cuando = ev.get("fecha_hora")
        if isinstance(cuando, str):
            cuando = datetime.fromisoformat(cuando)
        if cuando is None:
            continue
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=_tz(reg))
        if cuando - antes <= ahora <= cuando + despues:
            return ev
    return None


def veto_activo(vetos: Iterable[dict[str, Any]], simbolo: str, ahora: datetime) -> dict[str, Any] | None:
    """Regresa el veto que aplica a este símbolo (o un veto GLOBAL), o None."""
    for v in vetos:
        vence = v.get("vence")
        if isinstance(vence, str):
            vence = datetime.fromisoformat(vence)
        if vence is not None:
            if vence.tzinfo is None:
                vence = vence.replace(tzinfo=ZoneInfo("America/Mexico_City"))
            if vence < ahora:
                continue
        objetivo = str(v.get("simbolo", "")).upper()
        if objetivo in ("GLOBAL", "*") or objetivo == simbolo.upper():
            return v
    return None


# ---------------------------------------------------------------------------
# Decisión completa
# ---------------------------------------------------------------------------

def evaluar_candidato(
    reg: Reglamento,
    estado: EstadoCartera,
    cand: Candidato,
    filtros: Filtros,
    ahora: datetime,
    regimen_btc: str = "LATERAL",
    vol_moneda: str = "NORMAL",
    vol_btc: str = "NORMAL",
    vetos: Iterable[dict[str, Any]] = (),
    eventos: Iterable[dict[str, Any]] = (),
    apagar_en_banco: Iterable[str] = (),
) -> Decision:
    """Pasa un candidato por TODAS las reglas. Es la misma función en backtest y en vivo.

    `apagar_en_banco` es SOLO para el banco de pruebas de filtros (banco_filtros.py, backtest de experimento):
    códigos de reglas (descartes.py) que se saltan para medir qué pasaría sin ellas. Vacío por defecto. La ronda
    de papel y la ronda viva NUNCA lo pasan. Solo se aceptan los códigos de `descartes.APAGABLES_RIESGO`: los
    límites de verdad (stop inválido, mínimo de Binance, sin dinero libre) no se apagan nunca. Una decisión
    tomada con alguna regla apagada queda marcada `solo_papel` y con la verificación "EXPERIMENTO_BANCO"."""
    d = Decision(aprobada=False, candidato=cand)
    cfg_e = reg.estrategias.get(cand.estrategia, {})
    r = reg.riesgo
    apagadas = frozenset(apagar_en_banco) & DS.APAGABLES_RIESGO

    def activa(codigo: str) -> bool:
        return codigo not in apagadas

    def no(codigo: str, razon: str) -> Decision:
        d.codigo = codigo   # solo para el registro de descartes: no cambia la decisión
        d.razones.append(razon)
        return d

    # --- Frenos globales ---
    if apagadas:
        d.verificaciones.append("EXPERIMENTO_BANCO")
    if activa(DS.FRENO_TOTAL) and estado.detenido:
        return no(DS.FRENO_TOTAL, "sistema DETENIDO por caída máxima: se necesita el OK de Ángelo")
    if activa(DS.PAUSA_TOPE) and estado.pausa_hasta is not None and ahora < estado.pausa_hasta:
        return no(DS.PAUSA_TOPE, f"PAUSA activa ({estado.pausa_motivo})")
    d.verificaciones.append("tope_diario_ok")
    if activa(DS.CONCILIACION) and not estado.conciliacion_ok:
        return no(DS.CONCILIACION, "la conciliación no cuadra: PAUSA hasta revisar")
    if activa(DS.DATOS_NO_CONFIABLES) and not estado.datos_ok:
        return no(DS.DATOS_NO_CONFIABLES, "los datos no son confiables")
    d.verificaciones.append("datos_ok")

    # --- Estado de la estrategia ---
    est = cfg_e.get("estado", "APAGADA")
    if activa(DS.ESTRATEGIA_APAGADA) and est == "APAGADA":
        return no(DS.ESTRATEGIA_APAGADA, f"{cand.estrategia} está APAGADA")
    d.solo_papel = est == "PAPEL"
    if cfg_e.get("cubeta") == "memes" and not cfg_e.get("permitir_vivo", False):
        d.solo_papel = True
    if apagadas:
        d.solo_papel = True   # un experimento del banco nunca es una orden de verdad
    hasta = estado.pausa_estrategia_hasta.get(cand.estrategia)
    if activa(DS.RACHA_PERDIDAS) and hasta is not None and ahora < hasta:
        return no(DS.RACHA_PERDIDAS, f"{cand.estrategia} en pausa por racha de pérdidas")
    if activa(DS.RACHA_PERDIDAS) and estado.saltar_rondas.get(cand.estrategia, 0) > 0:
        return no(DS.RACHA_PERDIDAS, f"{cand.estrategia} se salta esta ronda por racha de pérdidas")
    d.verificaciones.append("racha_ok")

    # --- Vetos y eventos (los bots solo pueden decir NO) ---
    v = veto_activo(vetos, cand.simbolo, ahora)
    if activa(DS.VETO_NOTICIAS) and v is not None:
        razon = " ".join(str(v.get("razon", "sin razón")).split())[: int(reg.get("vetos.razon_max_caracteres", 200))]
        return no(DS.VETO_NOTICIAS, f"vetada por Noticias: {razon}")
    d.verificaciones.append("sin_veto")
    ev = evento_activo(reg, eventos, ahora)
    if activa(DS.EVENTO_FUERTE) and ev is not None:
        return no(DS.EVENTO_FUERTE, f"evento fuerte cerca: {ev.get('nombre', 'evento')}")
    d.verificaciones.append("sin_evento")

    # --- Régimen y volatilidad ---
    rg, vm, vb = regimen_btc, vol_moneda, vol_btc
    factor, bloqueo = factor_regimen(reg, cand.lado, cand.cubeta, rg, vm, vb)
    while bloqueo:
        # factor_regimen revisa primero la volatilidad EXTREMA y después BTC BAJISTA: el código sigue ese orden
        cod = DS.VOL_EXTREMA if "EXTREMA" in (vm, vb) else DS.BTC_BAJISTA
        if activa(cod):
            return no(cod, bloqueo)
        # Solo en un experimento del banco (esa regla está apagada): la volatilidad EXTREMA se trata como ALTA
        # (tamaño reducido, no normal) y BTC BAJISTA como LATERAL. Si queda el OTRO bloqueo, ese sigue mandando.
        if cod == DS.VOL_EXTREMA:
            vm, vb = ("ALTA" if x == "EXTREMA" else x for x in (vm, vb))
        else:
            rg = "LATERAL"
        factor, bloqueo = factor_regimen(reg, cand.lado, cand.cubeta, rg, vm, vb)
    d.factor = factor
    d.verificaciones.append("regimen_ok")

    # --- Una por moneda, nunca largo y corto a la vez ---
    for p in (estado.posiciones if activa(DS.YA_HAY_POSICION) else ()):
        if p.simbolo == cand.simbolo:
            if p.lado != cand.lado:
                return no(DS.YA_HAY_POSICION, "ya hay una posición contraria en esta moneda (nunca largo y corto a la vez)")
            return no(DS.YA_HAY_POSICION, "ya hay una posición abierta en esta moneda (nunca promediar)")
    d.verificaciones.append("una_por_moneda_ok")

    # --- Número de posiciones por cubeta ---
    maximo = int(r["posiciones_max"].get(cand.cubeta, 0))
    if activa(DS.MAX_POSICIONES) and estado.contar(cand.cubeta) >= maximo:
        return no(DS.MAX_POSICIONES, f"ya hay {maximo} posiciones de {cand.cubeta} abiertas (máximo)")
    d.verificaciones.append("posiciones_ok")

    # --- Validez del stop ---
    if cand.distancia <= 0:
        return no(DS.STOP_INVALIDO, "el stop está del lado equivocado de la entrada")
    if cand.mercado == "SPOT" and cand.lado == CORTO:
        return no(DS.STOP_INVALIDO, "no se puede ir en corto en Spot")

    # --- Topes de valor (exposición) ---
    capital = estado.capital
    if cand.mercado == "SPOT":
        tope = capital * float(r["exposicion_max_posicion_spot_pct"]) / 100.0
        if cand.cubeta == "memes":
            libre_memes = capital * float(r["cubeta_memes_max_pct"]) / 100.0 - estado.exposicion_cubeta("memes")
            if libre_memes <= 0:
                return no(DS.EXPOSICION_O_MARGEN, "la cubeta de memes está llena")
            tope = min(tope, libre_memes)
        if estado.efectivo_spot is not None:
            if estado.efectivo_spot <= 0:
                return no(DS.EXPOSICION_O_MARGEN, "no hay USDT libre en Spot")
            tope = min(tope, estado.efectivo_spot)
    else:
        fut = r["futuros"]
        apal_max = float(fut["apalancamiento_max"])
        if cand.apalancamiento > apal_max:
            return no(DS.EXPOSICION_O_MARGEN, f"pide {cand.apalancamiento:g}x y el máximo es {apal_max:g}x")
        margen_libre = capital * float(fut["margen_total_max_pct"]) / 100.0 - estado.margen_futuros()
        if estado.efectivo_futuros is not None:
            margen_libre = min(margen_libre, estado.efectivo_futuros)
        if margen_libre <= 0:
            return no(DS.EXPOSICION_O_MARGEN, "no queda margen libre para Futuros")
        tope = margen_libre * cand.apalancamiento
        ok_liq, msg = revisar_liquidacion(reg, cand)
        if not ok_liq:
            return no(DS.EXPOSICION_O_MARGEN, msg)
        d.verificaciones.append("liquidacion_ok")

    # --- Tamaño ---
    riesgo_pct = reg.riesgo_pct_estrategia(cand.estrategia)
    com_moneda = (cand.comision_pct if cand.mercado == "SPOT" and reg.get("costos.comision_en_moneda_comprada", True)
                  else 0.0)
    t = calcular_tamano(capital, riesgo_pct, factor, cand, filtros, tope, str(r.get("tamano", "riesgo")), com_moneda)
    if not t.ok:
        d.saltada_por_capital = t.saltada_por_capital
        d.capital_necesario = t.capital_necesario
        return no(DS.TAMANO_O_CAPITAL, t.razon)
    d.verificaciones.append("minimo_binance_ok")

    # --- Calor total ---
    calor_max = capital * float(r["calor_total_max_pct"]) / 100.0
    if activa(DS.CALOR_LLENO) and estado.calor_usdt + t.riesgo_usdt > calor_max + 1e-9:
        return no(
            DS.CALOR_LLENO,
            f"calor lleno: ya hay {estado.calor_usdt:.2f} USDT en riesgo y el máximo es {calor_max:.2f} USDT"
        )
    d.verificaciones.append("calor_ok")

    # --- Costos ---
    ok_c, msg_c = revisar_costos(reg, cand)
    if activa(DS.COSTOS) and not ok_c:
        return no(DS.COSTOS, msg_c)
    d.verificaciones.append("costos_ok")

    d.aprobada = True
    d.codigo = DS.APROBADA
    d.cantidad = t.cantidad
    d.valor_usdt = t.valor_usdt
    d.riesgo_usdt = t.riesgo_usdt
    d.riesgo_pct = t.riesgo_pct
    if t.recortada:
        d.razones.append(t.razon)
    return d


# ---------------------------------------------------------------------------
# Gestión de la posición
# ---------------------------------------------------------------------------

def mover_stop(lado: str, stop_actual: float, propuesto: float) -> float:
    """Los stops solo se mueven a favor: hacia arriba en largos, hacia abajo en cortos."""
    if lado == LARGO:
        return max(stop_actual, propuesto)
    return min(stop_actual, propuesto)


def stop_a_entrada(
    reg: Reglamento,
    lado: str,
    entrada: float,
    stop_inicial: float,
    precio_extremo: float,
    stop_actual: float,
    costo_pct: float,
) -> float:
    """En +1R (configurable), el stop sube a la entrada más costos. `precio_extremo` = máximo (largo) o mínimo (corto)."""
    en_r = float(reg.riesgo["gestion"]["mover_a_entrada_en_r"])
    r_unidad = abs(entrada - stop_inicial)
    if lado == LARGO:
        if precio_extremo >= entrada + en_r * r_unidad:
            return mover_stop(lado, stop_actual, entrada * (1 + costo_pct / 100.0))
    else:
        if precio_extremo <= entrada - en_r * r_unidad:
            return mover_stop(lado, stop_actual, entrada * (1 - costo_pct / 100.0))
    return stop_actual


def evaluar_apagado(
    reg: Reglamento, caida_vivo_pct: float, caida_p95_mc_pct: float | None, ultimos_r: list[float]
) -> tuple[bool, str]:
    """Apagado automático: si la caída en vivo rebasa el p95 de Monte Carlo, o la expectativa
    de las últimas N operaciones es negativa, la estrategia regresa sola a PAPEL."""
    n = int(reg.get("validacion.compuertas.apagado_ultimas_n", 30))
    if caida_p95_mc_pct is not None and caida_vivo_pct > caida_p95_mc_pct:
        return True, (
            f"la caída en vivo ({caida_vivo_pct:.1f} %) rebasó la peor esperada por Monte Carlo "
            f"({caida_p95_mc_pct:.1f} %)"
        )
    if len(ultimos_r) >= n:
        recientes = ultimos_r[-n:]
        exp = sum(recientes) / len(recientes)
        if exp < 0:
            return True, f"la expectativa de las últimas {n} operaciones es negativa ({exp:+.2f}R)"
    return False, ""
