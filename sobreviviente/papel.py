"""v2: MODO PAPEL — una ronda al día (00:10 UTC = 6:10 p. m. CDMX).

Usa EXACTAMENTE el mismo código que el backtest:
- señales: `estrategias/` (M0, M1, M2), con velas diarias cerradas;
- gestión de cada posición: `gestion.vela` (stops que solo suben, salida por canal o por señal);
- motor de riesgo: `riesgo.evaluar_candidato` con los valores de la Cartera A o B.

Cómo se llena en papel (igual que el backtest):
- Entradas y salidas por señal: en la APERTURA del día (la de la vela que acaba de empezar a las 00:00 UTC),
  con comisión y deslizamiento del reglamento.
- Stops: con el máximo y el mínimo de cada vela cerrada; si la vela abrió más allá del stop (hueco), a la apertura.
- Mínimos y decimales: los reales de Binance (exchangeInfo).

Seguridad (MAREA 6.1):
- Repetible: si la ronda de un día ya se hizo, correrla otra vez regresa los MISMOS boletos (mismo identificador)
  y no duplica nada.
- Si falta algo (datos viejos, archivo de bot mal escrito), cero entradas nuevas y un mensaje claro.
  Las posiciones abiertas y sus stops siguen igual.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from . import archivos as AR
from . import diario as DI
from . import referencias as RF
from . import riesgo as R
from .estrategias import ESTRATEGIAS
from .exchange import Filtros, redondear_abajo, redondear_arriba
from .gestion import EstadoGestion, vela
from .reglamento import Reglamento

DIA = pd.Timedelta(days=1)
CARTERAS = ("A", "B", "C")  # C: tamaño por exposición (pedida por Ángelo para que el papel con 46.18 USDT sí opere)
MOTORES_V2 = ("M0", "M1", "M2")
CAMPOS_GESTION = ("lado", "entrada", "entrada_plan", "stop_inicial", "stop", "meta", "modo", "params", "costo_pct",
                  "extremo", "velas", "meta_tocada", "salir_en_apertura", "en_r", "limite_stop_pct", "stop_pendiente")


def limites_ejecucion(reg: Reglamento) -> tuple[float, float]:
    """(límite de la compra LIMIT, límite del STOP_LOSS_LIMIT) en %, del reglamento."""
    return float(reg.get("ejecucion.limite_compra_pct", 0.3)), float(reg.get("ejecucion.limite_stop_pct", 0.5))


# ---------------------------------------------------------------------------
# Estado de una cartera de papel (archivo datos/papel/cartera_X.json)
# ---------------------------------------------------------------------------

def ruta_papel(reg: Reglamento) -> Path:
    return AR.carpeta_datos(reg) / "papel"


def estado_nuevo(nombre: str, capital: float, inicio: str) -> dict[str, Any]:
    return {"cartera": nombre, "inicio": inicio, "capital_inicial": capital, "efectivo": capital,
            "posiciones": [], "cerradas": [], "saltadas_capital": [], "ultimo_dia": None,
            "pico": capital, "capital_inicio_dia": capital, "capital_inicio_semana": capital,
            "dia_ref": None, "semana_ref": None, "pausa_hasta": None, "pausa_motivo": "", "detenido": False,
            "rachas": {}, "saltar_rondas": {}, "curva": {}, "rondas": {}}


def cargar_estado(reg: Reglamento, nombre: str, inicio: str) -> dict[str, Any]:
    arch = ruta_papel(reg) / f"cartera_{nombre}.json"
    if arch.exists() or arch.with_name(arch.name + ".bak").exists():
        return AR.leer_json_seguro(arch)
    cap = float(reg.get("carteras.capital_inicial", 46.18))
    return estado_nuevo(nombre, cap, inicio)


def guardar_estado(reg: Reglamento, est: dict[str, Any]) -> None:
    AR.escribir_json_seguro(ruta_papel(reg) / f"cartera_{est['cartera']}.json", est)


def id_stop(posicion_id: str, n: int) -> str:
    """newClientOrderId del stop número `n` de una posición (0 = el que se pone al comprar). Corto y sin acentos,
    como lo pide Binance; con él, cada reemplazo sabe exactamente qué stop cancelar (cancelOrigClientOrderId)."""
    return "sp" + hashlib.sha1(f"{posicion_id}|{n}".encode()).hexdigest()[:16]


def boleto_id(dia: str, cartera: str, accion: str, simbolo: str, estrategia: str) -> str:
    h = hashlib.sha1(f"{dia}|{cartera}|{accion}|{simbolo}|{estrategia}".encode()).hexdigest()[:8]
    return f"{dia.replace('-', '')}-{cartera}-{accion[:3]}-{simbolo.replace('USDT', '')}-{h}"


# ---------------------------------------------------------------------------
# Datos del día
# ---------------------------------------------------------------------------

@dataclass
class DatosDia:
    dia: pd.Timestamp                         # apertura de la última vela diaria CERRADA
    md: DI.MercadoDiario
    apertura_hoy: Callable[[str], float | None]  # apertura de la vela que empezó a las 00:00 UTC
    avisos: list[str] = field(default_factory=list)
    datos_ok: bool = True
    serie_masa: Callable[[str], pd.Series] | None = None   # ESTELA (solo si el veto está activo)
    excluidas_hoy: list[str] = field(default_factory=list)  # monedas que no se pudieron bajar hoy (fuera de las señales)
    informativos: list[str] = field(default_factory=list)   # avisos ℹ️: no activan MODO SEGURO ni quitan el 👍


def avisos_bstocks(reg: Reglamento, exchange_info: dict[str, Any]) -> list[str]:
    """Avisos ℹ️ de pares raros (¿acción tokenizada?) y de bStocks excluidas solas que faltan en la lista."""
    from . import universo as U
    excluidas, raras = U.bstocks_detectadas(reg, exchange_info)
    nuevas = sorted(excluidas - set(reg.get("universo.excluir_bases") or []))
    out = []
    if raras:
        out.append(f"ℹ️ Par raro en Binance (¿acción tokenizada?): {', '.join(raras)}. Si no es cripto, agrégala a "
                   f"universo.excluir_bases; si lo es, a universo.permitir_con_B.")
    if nuevas:
        out.append(f"ℹ️ Nueva bStock excluida automáticamente: {', '.join(nuevas)}; agrégala a excluir_bases.")
    return out


def preparar_datos(reg: Reglamento, cliente, memes: list[str], ahora: datetime | None = None,
                   dias_historia: int = 420, avisar=print) -> DatosDia:
    """Descarga (solo lo que falta) las velas diarias recientes de los pares USDT y arma el mercado."""
    from . import datos as D
    from . import universo as U
    ahora = ahora or datetime.now(timezone.utc)
    dia = pd.Timestamp(ahora).tz_convert("UTC").normalize() - DIA
    info = cliente.exchange_info("SPOT")
    excl, err = AR.leer(reg, "exclusiones.json")
    avisos = []
    if err and not (len(err) == 1 and err[0].startswith("no existe")):
        avisos.append("exclusiones.json viene mal (" + "; ".join(err) + "): MODO SEGURO, sin entradas nuevas.")
    excluidas = {x["simbolo"] for x in (excl or {}).get("exclusiones", [])}
    # Copias viejas de las reglas de Binance (si no se pudieron actualizar)
    for a in getattr(cliente, "avisos_copias", []):
        avisos.append(a[0].upper() + a[1:] + ".")
    if getattr(cliente, "edad_copia_max_h", 0.0) > 48:
        avisos.append("Esa copia tiene más de 48 horas: MODO SEGURO, sin compras nuevas.")
    candidatos = [s for s in U.simbolos_candidatos(reg, info) if s not in excluidas]
    informativos = avisos_bstocks(reg, info)
    if "BTCUSDT" not in candidatos:
        candidatos.append("BTCUSDT")
    # Las monedas con posición abierta se bajan SIEMPRE (aunque ya no estén en la lista), para revisar sus stops
    abiertas = sorted({p["simbolo"] for n in CARTERAS for p in cargar_estado(reg, n, "").get("posiciones", [])})
    candidatos += [s for s in abiertas if s not in candidatos]
    inicio = (dia - pd.Timedelta(days=dias_historia)).strftime("%Y-%m-%d")
    fin = (dia + DIA).strftime("%Y-%m-%d")
    resultados = D.descargar_muchos(lambda s: D.actualizar_spot(cliente, s, "1d", inicio, fin), [(s,) for s in candidatos])
    fallidas = [s for s, r in zip(candidatos, resultados) if r is None]
    # BTC o una moneda con posición abierta: sin ellas no se puede decidir bien → MODO SEGURO.
    criticas = [s for s in fallidas if s == "BTCUSDT" or s in abiertas]
    # Cualquier otra: se excluye HOY (no entra al mercado ni como candidata). Nunca se opera con velas viejas.
    excluidas_hoy = [s for s in fallidas if s not in criticas]
    if criticas:
        avisos.append(f"No se pudieron bajar {', '.join(criticas)} (BTC o con posición abierta): MODO SEGURO, "
                      f"sin compras nuevas. Lo abierto se revisa con lo que sí se bajó.")
        for s in criticas:  # se usa la copia guardada de sus velas: se dice de cuándo es
            viejo = D.leer(D.ruta_cache(cliente, "spot", "1d", s))
            if not viejo.empty:
                cierre = viejo.index[-1] + DIA
                avisos.append(f"Se usó una copia de {cierre:%Y-%m-%d %H:%M} UTC de las velas de {s}; no está al día.")
    if excluidas_hoy:
        lista = ", ".join(excluidas_hoy[:8]) + ("…" if len(excluidas_hoy) > 8 else "")
        avisos.append(f"No se pudieron bajar {len(excluidas_hoy)} moneda(s) ({lista}); se excluyen hoy. "
                      f"No afecta a BTC ni a lo abierto.")
    velas = {}
    for s in candidatos:
        if s in excluidas_hoy:
            continue
        df = D.leer(D.ruta_cache(cliente, "spot", "1d", s))
        if df.empty:
            continue
        df = df[df.index >= pd.Timestamp(inicio, tz="UTC")]
        if len(df):
            velas[s] = df.astype({c: "float64" for c in ["open", "high", "low", "close", "volume", "quote_volume"] if c in df})
    # Calidad (velas faltantes, datos viejos, precios absurdos) de BTC y de lo que está abierto
    from .calidad import revisar_velas
    for s in ["BTCUSDT"] + [x for x in abiertas if x != "BTCUSDT"]:
        rep_c = revisar_velas(reg, velas.get(s), s, "1D", ahora=ahora, ventana=dias_historia)
        if not rep_c.confiable:
            avisos.append(f"Los datos de {s} no son confiables ({'; '.join(rep_c.motivos)}): MODO SEGURO, sin compras nuevas.")
    md = DI.preparar(reg, velas, cliente, memes, exchange_info=info,
                     btc_largo=velas.get("BTCUSDT"))
    datos_ok = "BTCUSDT" in velas and velas["BTCUSDT"].index[-1] == dia
    if not datos_ok:
        avisos.append("Las velas de BTC no están al día: MODO SEGURO, sin entradas nuevas.")
    if avisos and any("MODO SEGURO" in a for a in avisos):
        datos_ok = False
    cache_apertura: dict[str, float | None] = {}

    def apertura_hoy(s: str) -> float | None:
        if s not in cache_apertura:
            try:
                k = cliente.spot("/api/v3/klines", {"symbol": s, "interval": "1d", "limit": 1})
                cache_apertura[s] = float(k[0][1]) if k and int(k[0][0]) == int((dia + DIA).timestamp() * 1000) else None
            except Exception:  # noqa: BLE001
                cache_apertura[s] = None
        return cache_apertura[s]

    serie_masa = None
    if reg.estrategias.get("M3", {}).get("veto_activo"):
        from . import estela as ES
        serie_masa = lambda s: ES.serie_masa(reg, cliente, s)  # noqa: E731
    return DatosDia(dia=dia, md=md, apertura_hoy=apertura_hoy, avisos=avisos, datos_ok=datos_ok, serie_masa=serie_masa,
                    excluidas_hoy=excluidas_hoy, informativos=informativos)


# ---------------------------------------------------------------------------
# La ronda
# ---------------------------------------------------------------------------

def conciliacion_ok(reg: Reglamento | None) -> bool:
    """False si el último `conciliar` no cuadró (datos/papel/conciliacion.json con ok:false)."""
    if reg is None:
        return True
    arch = ruta_papel(reg) / "conciliacion.json"
    if not arch.exists():
        return True
    try:
        return bool(json.loads(arch.read_text(encoding="utf-8")).get("ok", True))
    except (json.JSONDecodeError, OSError):
        return False  # archivo roto: por seguridad, como si no cuadrara


def _estado_riesgo(est: dict[str, Any], capital: float, posiciones: list[R.Posicion],
                   reg: Reglamento | None = None) -> R.EstadoCartera:
    e = R.EstadoCartera(capital=capital, pico=max(float(est["pico"]), capital), capital_inicio_dia=float(est["capital_inicio_dia"]),
                        capital_inicio_semana=float(est["capital_inicio_semana"]), posiciones=posiciones,
                        efectivo_spot=float(est["efectivo"]))
    if est.get("pausa_hasta"):
        e.pausa_hasta = datetime.fromisoformat(est["pausa_hasta"])
        e.pausa_motivo = est.get("pausa_motivo", "")
    e.detenido = bool(est.get("detenido"))
    e.rachas = dict(est.get("rachas", {}))
    e.saltar_rondas = dict(est.get("saltar_rondas", {}))
    e.conciliacion_ok = conciliacion_ok(reg)
    return e


def _senales(dd: DatosDia, clave: str, simbolo: str, params: dict[str, Any]) -> pd.DataFrame | None:
    ctx = DI.contexto(dd.md, clave, simbolo)
    if ctx is None:
        return None
    if clave == "M2":
        DI.preparar_m2(dd.md, [int(params["L"])])
        ctx = DI.contexto(dd.md, clave, simbolo)
    return ESTRATEGIAS[clave].senales(ctx, {**dd.md.reg.estrategias[clave].get("fijos", {}), **params})


def _precio_salida(precio: float, desliz_pct: float) -> float:
    return precio * (1 - desliz_pct / 100)


def valor_posicion(p: dict[str, Any], md, dia: pd.Timestamp) -> float:
    """Valor de una posición abierta al cierre de `dia`: cantidad × último cierre conocido; si no hay velas, al precio
    de entrada. Nunca vale 0 por falta de datos (el capital caería de forma falsa y `reanudar` tomaría ese pico)."""
    v = md.velas.get(p["simbolo"])
    px = float(v["close"].asof(dia)) if v is not None and len(v) else float("nan")
    if not np.isfinite(px):
        px = float(p["entrada"])
    return p["cantidad"] * px


def ronda_cartera(reg: Reglamento, nombre: str, dd: DatosDia, vetos: list, eventos: list,
                  forzar_seguro: bool = False, bloquear_compras: str = "") -> dict[str, Any]:
    """Procesa UN día para una cartera. Repetible: si el día ya se procesó, regresa lo guardado.

    `bloquear_compras` (p. ej. ronda FUERA DE HORA): las posiciones y sus stops se procesan igual, pero no se
    abre nada nuevo; el texto es el motivo que se reporta."""
    dia_txt = dd.dia.strftime("%Y-%m-%d")
    est = cargar_estado(reg, nombre, (dd.dia + DIA).strftime("%Y-%m-%d"))
    if est.get("ultimo_dia") == dia_txt and dia_txt in est.get("rondas", {}):
        return est["rondas"][dia_txt]
    rgc = reg.para_cartera(nombre)
    comision = float(rgc.costos["comision_spot_pct"])
    # Binance Spot cobra la comisión de la compra en la moneda comprada: el stop y la venta van por la cantidad neta
    com_moneda = comision if rgc.get("costos.comision_en_moneda_comprada", True) else 0.0
    boletos, mensajes, cerradas_hoy, stops_sin_llenar, no_llenadas = [], [], [], [], []
    md = dd.md
    lim_compra, lim_stop = limites_ejecucion(reg)
    avisos_capital = dict(est.get("avisos_capital", {}))
    vistos_capital: set[str] = set()

    # 1) Avanzar las posiciones abiertas con las velas cerradas que faltan
    siguen = []
    for p in est["posiciones"]:
        v = md.velas.get(p["simbolo"])
        clave = p["estrategia"]
        params = p["params"]
        ge = p["gestion"]
        g = EstadoGestion(**{k: ge[k] for k in CAMPOS_GESTION if k in ge})
        stop_antes = g.stop
        salida = None
        sin_llenar = False
        if v is not None:
            sen = _senales(dd, clave, p["simbolo"], params)
            canal = v["low"].rolling(int(g.params["canal_velas"])).min() if g.modo == "canal" else None
            pendientes = v[(v.index > pd.Timestamp(p["ultimo_dia"], tz="UTC")) & (v.index <= dd.dia)]
            for t, fila in pendientes.iterrows():
                salir_ext = bool(sen.at[t, "salir"]) if sen is not None and t in sen.index else False
                ev = vela(g, fila["open"], fila["high"], fila["low"], fila["close"], 0.0, None, salir_ext,
                          None if canal is None else float(canal.get(t, np.nan)))
                p["ultimo_dia"] = t.strftime("%Y-%m-%d")
                sin_llenar = ev.stop_sin_llenar
                if ev.salio:
                    # stop tocado durante la vela t (o salida programada en su apertura): se anota al cierre de t
                    salida = (ev.precio, ev.motivo, t + DIA)
                    break
            if salida is None and sin_llenar:
                mensajes.append(f"⚠️ {p['simbolo']}: el stop se activó, pero el precio abrió abajo de su límite "
                                f"({g.stop_pendiente:.8g}): STOP SIN LLENAR. La posición sigue abierta con una orden de venta "
                                f"a ese precio. En dinero real, el Ejecutor avisa a THE BOSS de inmediato.")
                stops_sin_llenar.append(p["simbolo"])
            if salida is None and g.salir_en_apertura:
                px = dd.apertura_hoy(p["simbolo"])
                if px is not None:
                    salida = (px, g.params.get("_motivo_salida", "salida programada"), dd.dia + DIA)
                else:
                    mensajes.append(f"{p['simbolo']}: toca vender en la apertura pero no hay precio; se intenta mañana.")
        if salida is not None:
            precio, motivo, cuando = salida
            real = _precio_salida(precio, p["desliz_pct"])
            bruto = p["cantidad"] * real
            com = bruto * comision / 100
            est["efectivo"] += bruto - com
            ganancia = bruto - com - p["costo_total"]
            r = ganancia / (p["cantidad"] * abs(p["entrada_plan"] - p["stop_inicial"]))
            cerr = {**{k: p[k] for k in ("id", "estrategia", "simbolo", "cantidad", "entrada", "t_entrada")},
                    "salida": real, "t_salida": str(cuando), "motivo": motivo, "ganancia_usdt": ganancia, "r": r}
            est["cerradas"].append(cerr)
            cerradas_hoy.append(cerr)
            f_c = md.filtros.get(p["simbolo"])
            boletos.append({"boleto_id": boleto_id(dia_txt, nombre, "CERRAR", p["simbolo"], clave), "accion": "CERRAR",
                            "simbolo": p["simbolo"], "estrategia": clave, "cantidad": p["cantidad"],
                            "cantidad_stop": p.get("cantidad_stop", R.cantidad_neta(p["cantidad"], com_moneda,
                                                                                    f_c.paso if f_c else 0)),
                            "paso_cantidad": f_c.paso if f_c else None, "tick_precio": f_c.tick if f_c else None,
                            "tipo_orden": "YA_EJECUTADO_POR_STOP" if motivo.startswith("stop") else "MARKET",
                            "razon": motivo})
            er = _estado_riesgo(est, est["efectivo"], [])
            R.registrar_resultado(rgc, er, clave, ganancia, datetime.now(timezone.utc))
            est["rachas"], est["saltar_rondas"] = er.rachas, er.saltar_rondas
            continue
        p["gestion"] = {**ge, **{k: getattr(g, k) for k in ("stop", "extremo", "velas", "meta_tocada", "salir_en_apertura",
                                                            "limite_stop_pct", "stop_pendiente")},
                        "params": g.params}
        if g.stop > stop_antes:
            f = md.filtros.get(p["simbolo"])
            stop_txt = redondear_abajo(g.stop, f.tick) if f else g.stop
            p["gestion"]["stop"] = stop_txt
            n_viejo = int(p.get("stop_n", 0))
            p["stop_n"] = n_viejo + 1
            boletos.append({"boleto_id": boleto_id(dia_txt, nombre, "MODIFICAR_STOP", p["simbolo"], clave),
                            "accion": "MODIFICAR_STOP", "simbolo": p["simbolo"], "estrategia": clave,
                            "id_stop_anterior": id_stop(p["id"], n_viejo), "id_stop": id_stop(p["id"], n_viejo + 1),
                            "cantidad": p["cantidad"], "stop": stop_txt,
                            "cantidad_stop": p.get("cantidad_stop", R.cantidad_neta(p["cantidad"], com_moneda,
                                                                                    f.paso if f else 0)),
                            "paso_cantidad": f.paso if f else None, "tick_precio": f.tick if f else None,
                            "precio_limite_stop": redondear_abajo(stop_txt * (1 - lim_stop / 100), f.tick) if f
                            else stop_txt * (1 - lim_stop / 100),
                            "stop_anterior": stop_antes,
                            "precio_limite_stop_anterior": redondear_abajo(stop_antes * (1 - lim_stop / 100), f.tick) if f
                            else stop_antes * (1 - lim_stop / 100),
                            "tipo_orden": "CANCEL_REPLACE (POST /api/v3/order/cancelReplace, cancelReplaceMode=STOP_ON_FAILURE) "
                                          "→ STOP_LOSS_LIMIT",
                            "regla_precio": REGLA_PRECIO_STOP,
                            "razon": "el stop sube (solo a favor)"})
        siguen.append(p)
    est["posiciones"] = siguen

    # 2) Capital a valor de mercado al cierre del día
    valor_pos = 0.0
    posiciones_r = []
    for p in siguen:
        valor_pos += valor_posicion(p, md, dd.dia)
        v = md.velas.get(p["simbolo"])
        if v is None or dd.dia not in v.index:   # no se cierra nada solo: se avisa
            mensajes.append(f"⚠️ {p['simbolo']}: sin velas hoy, revisar a mano")
        posiciones_r.append(R.Posicion(p["simbolo"], "SPOT", "LARGO", p["estrategia"], "normales", p["entrada"],
                                       float(p["gestion"]["stop"]), p["cantidad"]))
    capital = est["efectivo"] + valor_pos
    ahora = (dd.dia + DIA + pd.Timedelta(minutes=10)).to_pydatetime()
    d0 = R.inicio_dia(rgc, ahora).isoformat()
    w0 = R.inicio_semana(rgc, ahora).isoformat()
    if est.get("dia_ref") != d0:
        est["dia_ref"], est["capital_inicio_dia"] = d0, capital
    if est.get("semana_ref") != w0:
        est["semana_ref"], est["capital_inicio_semana"] = w0, capital
    er = _estado_riesgo(est, capital, posiciones_r, reg)
    if not er.conciliacion_ok:
        mensajes.append("⚠️ La conciliación no cuadró: hoy no se abren posiciones nuevas hasta que un conciliar salga bien.")
    er.datos_ok = dd.datos_ok and not forzar_seguro
    mensajes += R.aplicar_topes(rgc, er, ahora)
    est["pico"] = er.pico
    est["detenido"] = er.detenido
    est["pausa_hasta"] = er.pausa_hasta.isoformat() if er.pausa_hasta else None
    est["pausa_motivo"] = er.pausa_motivo

    # 3) Señales nuevas de los motores en PAPEL
    activas = [k for k in MOTORES_V2 if reg.estrategias.get(k, {}).get("estado") in ("PAPEL", "VIVA_MINI", "VIVA")]
    dia_dec = dd.dia + DIA
    grandes_hoy = [s for s in md.grandes.columns if dia_dec in md.grandes.index and bool(md.grandes.at[dia_dec, s])]
    marea = md.marea.get(dd.dia)
    candidatos = []
    for clave in activas:
        params = reg.estrategias[clave]["parametros"]
        simbolos = ["BTCUSDT"] if clave == "M0" else grandes_hoy
        for s in simbolos:
            sen = _senales(dd, clave, s, params)
            if sen is None or dd.dia not in sen.index or not bool(sen.at[dd.dia, "entrada"]):
                continue
            candidatos.append((float(sen.at[dd.dia, "fuerza"]) if np.isfinite(sen.at[dd.dia, "fuerza"]) else 0.0,
                               clave, s, params, sen))
    candidatos.sort(key=lambda x: (-x[0], x[2]))
    if bloquear_compras:
        if candidatos:
            mensajes.append(f"Hoy no se compra ({bloquear_compras}): {len(candidatos)} señal(es) sin boleto.")
        candidatos = []
    m3 = reg.estrategias.get("M3", {})
    for _, clave, s, params, sen in candidatos:
        if m3.get("veto_activo") and clave in ("M1", "M2") and dd.serie_masa is not None:
            from . import estela as ES
            if ES.veto_h2(dd.serie_masa(s), dd.dia, float(m3.get("fijos", {}).get("percentil_masa", 90))):
                mensajes.append(f"{s} ({clave}): no entra — vetada por ESTELA (la masa está muy cargada en largo).")
                continue
        f = md.filtros.get(s)
        precio = float(sen.at[dd.dia, "precio"])
        stop = float(sen.at[dd.dia, "stop"])
        if f is None:
            continue
        stop = redondear_abajo(stop, f.tick)
        vm = md.vol_mediano.at[dia_dec, s] if dia_dec in md.vol_mediano.index and s in md.vol_mediano.columns else 0.0
        from . import universo as U
        desliz = U.deslizamiento(rgc, U.clasificar_liquidez(rgc, float(vm) if np.isfinite(vm) else 0.0, False))
        cand = R.Candidato(s, "SPOT", "LARGO", clave, "normales", precio, stop, None,
                           redondear_abajo(stop * (1 - lim_stop / 100), f.tick), comision, desliz)
        vol_m = R.clasificar_volatilidad(rgc, _num(md.vol_pct.get(s, pd.Series(dtype=float)).get(dd.dia)))
        vol_b = R.clasificar_volatilidad(rgc, _num(md.btc_vol.get(dd.dia)))
        dec = R.evaluar_candidato(rgc, er, cand, f, ahora, regimen_btc=marea or "BAJISTA", vol_moneda=vol_m,
                                  vol_btc=vol_b, vetos=vetos, eventos=eventos)
        if not dec.aprobada:
            if dec.saltada_por_capital:
                est["saltadas_capital"].append({"dia": dia_txt, "simbolo": s, "estrategia": clave,
                                                "capital_necesario": dec.capital_necesario})
                k_av = f"{clave}:{s}"
                vistos_capital.add(k_av)
                if k_av not in avisos_capital:
                    # Primera vez: se explica. Los días siguientes no se repite mientras siga igual.
                    nec = f"{dec.capital_necesario:.2f}" if dec.capital_necesario else "?"
                    mensajes.append(f"{s} ({clave}): no cabe con {capital:.2f} USDT ({dec.razon.replace('saltada por capital: ', '')}). "
                                    f"Haría falta un capital de unos {nec} USDT. Se vuelve a intentar cada día; "
                                    f"no vuelvo a avisar mientras siga igual.")
                    avisos_capital[k_av] = {"desde": dia_txt, "capital_necesario": dec.capital_necesario, "dias": 1}
                else:
                    avisos_capital[k_av]["dias"] = int(avisos_capital[k_av].get("dias", 1)) + 1
                    avisos_capital[k_av]["capital_necesario"] = dec.capital_necesario
            else:
                mensajes.append(f"{s} ({clave}): no entra — {dec.razon}.")
            continue
        if redondear_abajo(dec.cantidad, f.paso) <= 0:
            # Redondeada al paso de Binance (stepSize) queda en 0: un boleto con cantidad "0" no se genera nunca.
            mensajes.append(f"⚠️ cantidad menor que el mínimo de Binance, no se compra ({s}, {clave}).")
            continue
        px = dd.apertura_hoy(s)
        if px is None:
            mensajes.append(f"{s} ({clave}): no hay precio de apertura; no entra hoy.")
            continue
        limite = redondear_arriba(precio * (1 + lim_compra / 100), f.tick)
        if px > limite:
            # La compra es LIMIT a `limite`: si abrió más arriba, en Binance no se llena. En papel tampoco.
            mensajes.append(f"{s} ({clave}): NO SE LLENÓ — abrió en {px:.8g}, arriba del límite de compra {limite:.8g}. "
                            f"No se abre posición.")
            no_llenadas.append(s)
            continue
        entrada = min(px * (1 + desliz / 100), limite)
        costo = dec.cantidad * entrada * (1 + comision / 100)
        if costo > est["efectivo"] + 1e-9:
            mensajes.append(f"{s} ({clave}): no alcanza el efectivo en papel ({est['efectivo']:.2f} USDT).")
            continue
        est["efectivo"] -= costo
        g = ESTRATEGIAS[clave].gestion(params)
        en_r = None if not reg.estrategias[clave].get("mover_a_entrada", True) else float(rgc.riesgo["gestion"]["mover_a_entrada_en_r"])
        gparams = {k: v for k, v in g.items() if k != "modo"}
        if g["modo"] == "canal":
            cv = md.velas[s]["low"].rolling(int(g["canal_velas"])).min()
            gparams["_canal_prev"] = float(cv.get(dd.dia, np.nan))
        ge = EstadoGestion(lado="LARGO", entrada=entrada, entrada_plan=precio, stop_inicial=stop, stop=stop, meta=None,
                           modo=g["modo"], params=gparams, costo_pct=2 * (comision + desliz), en_r=en_r,
                           limite_stop_pct=lim_stop)
        bid = boleto_id(dia_txt, nombre, "COMPRAR", s, clave)
        cant_stop = R.cantidad_neta(dec.cantidad, com_moneda, f.paso)   # lo que queda después de la comisión
        est["posiciones"].append({
            "id": bid, "estrategia": clave, "simbolo": s, "params": params, "cantidad": dec.cantidad, "stop_n": 0,
            "cantidad_stop": cant_stop,
            "entrada": entrada, "entrada_plan": precio, "stop_inicial": stop, "t_entrada": str(dia_dec),
            "desliz_pct": desliz, "costo_total": costo, "ultimo_dia": dia_txt,
            "gestion": {k: getattr(ge, k) for k in CAMPOS_GESTION},
        })
        er.posiciones.append(R.Posicion(s, "SPOT", "LARGO", clave, "normales", precio, stop, dec.cantidad))
        er.efectivo_spot = est["efectivo"]
        avisos_capital.pop(f"{clave}:{s}", None)
        boletos.append({
            "boleto_id": bid, "version_reglamento": reg.version, "cartera": nombre, "accion": "COMPRAR",
            "mercado": "SPOT", "simbolo": s, "lado": "COMPRA", "tipo_orden": "LIMIT + STOP_LOSS_LIMIT individual",
            "id_stop": id_stop(bid, 0),
            "precio_entrada": limite, "stop": stop, "precio_limite_stop": cand.precio_limite_stop, "meta": None,
            "cantidad": dec.cantidad, "cantidad_stop": cant_stop,
            "valor_usdt": round(dec.cantidad * limite, 4), "riesgo_usdt": round(dec.riesgo_usdt, 4),
            "paso_cantidad": f.paso, "tick_precio": f.tick,
            "riesgo_pct": round(dec.riesgo_pct, 3), "apalancamiento": 1, "estrategia": clave,
            "razon": f"{reg.estrategias[clave]['nombre']}: señal al cierre del {dia_txt}",
            "vence": vence_compra(reg, dd.dia), "verificaciones": dec.verificaciones,
            "llenado_papel": {"precio": round(entrada, 8), "comision_usdt": round(dec.cantidad * entrada * comision / 100, 6)},
        })

    # 4) Cierre de la ronda
    valor_pos = sum(valor_posicion(p, md, dd.dia) for p in est["posiciones"])
    capital_fin = est["efectivo"] + valor_pos
    est["curva"][dia_txt] = capital_fin
    R.consumir_ronda(er)
    est["saltar_rondas"] = er.saltar_rondas
    for b in boletos:
        b["texto"] = texto_boleto(b)
    # Avisos de capital: los que hoy ya no aplican se borran (si regresan, se vuelve a explicar)
    avisos_capital = {k: v for k, v in avisos_capital.items() if k in vistos_capital}
    est["avisos_capital"] = avisos_capital
    no_alcanza = bool(avisos_capital) and not est["posiciones"]
    nec = [v["capital_necesario"] for v in avisos_capital.values() if v.get("capital_necesario")]
    resumen = {"dia": dia_txt, "cartera": nombre, "capital": capital_fin, "efectivo": est["efectivo"],
               "posiciones": [p["simbolo"] for p in est["posiciones"]], "boletos": boletos, "mensajes": mensajes,
               "cerradas_hoy": cerradas_hoy, "pausa": est.get("pausa_motivo") if est.get("pausa_hasta") else "",
               "detenido": est.get("detenido", False), "datos_ok": dd.datos_ok and not forzar_seguro,
               "opera": not no_alcanza, "capital_necesario": max(nec) if (no_alcanza and nec) else None,
               "stops_sin_llenar": stops_sin_llenar, "no_llenadas": no_llenadas,
               "conciliacion_ok": er.conciliacion_ok}
    est["rondas"][dia_txt] = resumen
    est["ultimo_dia"] = dia_txt
    guardar_estado(reg, est)
    return resumen


def _num(x) -> float | None:
    try:
        x = float(x)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def vence_compra(reg: Reglamento, dia: pd.Timestamp) -> str:
    """Hasta cuándo vale una compra: `ronda.vigencia_boleto_horas` (24) desde las 00:00 UTC del día en que corre la
    ronda (= el día siguiente a la vela de señal `dia`). Con 24 h vence a las 00:00 UTC del día siguiente a la ronda."""
    horas = float(reg.get("ronda.vigencia_boleto_horas", 24))
    return (dia + DIA + pd.Timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")


def hora_cdmx(iso_utc: str) -> str:
    """'2026-11-11T00:00:00Z' → '6:00 p. m. del 10/11/2026 (hora CDMX)'."""
    from zoneinfo import ZoneInfo
    t = datetime.fromisoformat(str(iso_utc).replace("Z", "+00:00"))
    t = (t.replace(tzinfo=ZoneInfo("America/Mexico_City")) if t.tzinfo is None else t).astimezone(ZoneInfo("America/Mexico_City"))
    h12 = t.hour % 12 or 12
    return f"{h12}:{t.minute:02d} {'a. m.' if t.hour < 12 else 'p. m.'} del {t:%d/%m/%Y} (hora CDMX)"


REGLA_PRECIO_STOP = "el stop nuevo debe quedar por debajo del precio actual; si no, NO lo pongas, deja el viejo y avisa"


def numero_txt(x: Any, paso: float | None = None) -> str:
    """Número para copiar a Binance: SIEMPRE notación normal (nunca "5e-05"), sin ceros de sobra.
    Con `paso` (paso de cantidad o tick de precio) se ajusta a sus decimales para quitar ruido del punto flotante."""
    from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
    if x is None:
        return "—"
    try:
        d = Decimal(str(x))
        if paso:
            d = d.quantize(Decimal(str(paso)).normalize(), rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError):
        return str(x)
    t = format(d, "f")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t if t not in ("", "-0") else "0"


def texto_boleto(b: dict[str, Any]) -> str:
    """Texto listo para copiar: nada que el Ejecutor tenga que calcular."""
    s = b["simbolo"]
    paso, tick = b.get("paso_cantidad"), b.get("tick_precio")
    cant = numero_txt(b.get("cantidad"), paso)
    cant_stop = numero_txt(b.get("cantidad_stop", b.get("cantidad")), paso)   # neta: lo que queda tras la comisión
    moneda = s[:-len("USDT")] if s.endswith("USDT") else s
    if b["accion"] == "COMPRAR":
        return (f"[{b['boleto_id']}] COMPRAR {cant} {s} con orden LIMIT a {numero_txt(b['precio_entrada'], tick)} y, en cuanto "
                f"se llene, pon un STOP_LOSS_LIMIT individual de VENTA de {cant_stop} {s}: stop {numero_txt(b['stop'], tick)}, "
                f"límite {numero_txt(b['precio_limite_stop'], tick)}"
                + (f", newClientOrderId={b['id_stop']}" if b.get("id_stop") else "")
                + f". Después de la compra tendrás {cant_stop} {moneda} si la comisión se cobra en {moneda}. Cantidad del stop "
                  f"según la respuesta de la compra: si commissionAsset es BNB (o cualquier moneda distinta a {moneda}), el stop "
                  f"va por executedQty completo, sin restar nada, redondeado hacia abajo al stepSize; si es {moneda}, por "
                  f"executedQty − commission, redondeado hacia abajo al stepSize; si la respuesta no trae comisión, usa "
                  f"{cant_stop} (cantidad_stop del boleto)"
                + ". El stop va como STOP_LOSS_LIMIT individual, nunca dentro de una orden de lista "
                  "(cancelar una pata de una lista cancela toda la lista). "
                f"Confirma que el stop quedó ACTIVO."
                + (f" Si no se llena antes de {hora_cdmx(b['vence'])}, CANCÉLALA y avisa a THE BOSS; no la dejes abierta."
                   if b.get("vence") else ""))
    if b["accion"] == "MODIFICAR_STOP":
        viejo = numero_txt(b.get("stop_anterior"), tick)
        lim_viejo = numero_txt(b.get("precio_limite_stop_anterior"), tick)
        return (f"[{b['boleto_id']}] MOVER STOP de {s} con reemplazo en una sola operación de Binance "
                f"(order/cancelReplace, cancelReplaceMode=STOP_ON_FAILURE, cancelRestrictions=ONLY_NEW"
                + (f", cancelOrigClientOrderId={b['id_stop_anterior']}" if b.get("id_stop_anterior") else "")
                + (f", newClientOrderId={b['id_stop']}" if b.get("id_stop") else "")
                + f"): con ONLY_NEW, si el stop viejo ya se ejecutó en parte (PARTIALLY_FILLED), Binance no lo cancela "
                f"(error -2011) y no pone el nuevo: no hagas nada más y avisa a THE BOSS. "
                f"El stop actual se reemplaza por un "
                f"STOP_LOSS_LIMIT de VENTA de {cant_stop} {s} (o la misma cantidad del stop actual, si es distinta): "
                f"stop {numero_txt(b['stop'], tick)}, "
                f"límite {numero_txt(b['precio_limite_stop'], tick)}. "
                f"Antes, revisa: {REGLA_PRECIO_STOP}. "
                f"Si Binance rechaza el stop nuevo, el viejo se queda; avisa a THE BOSS y no improvises. "
                f"ÚNICA EXCEPCIÓN (así lo dice la documentación de Binance): si la respuesta es el error -2021 "
                f"(cancelResult SUCCESS y newOrderResult FAILURE), el stop viejo YA se canceló y la posición quedó SIN stop: "
                f"vuelve a poner de inmediato el stop viejo (STOP_LOSS_LIMIT de VENTA de {cant_stop} {s} o la misma cantidad "
                f"que tenía, si era distinta: stop {viejo}, "
                f"límite {lim_viejo}"
                + (f", newClientOrderId={b['id_stop']}" if b.get("id_stop") else "")
                + ") y avisa a THE BOSS. Si no puedes volver a poner el stop viejo (Binance lo rechaza), VENDE la posición "
                f"a MERCADO de inmediato y avisa a THE BOSS; una posición sin stop no se vale. "
                f"Confirma que quedó un stop ACTIVO.")
    if b["accion"] == "CERRAR":
        if b.get("tipo_orden") == "YA_EJECUTADO_POR_STOP":
            return f"[{b['boleto_id']}] {s}: el stop ya se ejecutó. Solo confirma que ya no tienes {s} ni órdenes abiertas."
        return (f"[{b['boleto_id']}] VENDER {cant_stop} {s} a MERCADO (o la misma cantidad del stop actual, si es distinta; "
                f"primero cancela su stop). "
                f"Motivo: {b['razon']}.")
    return f"[{b['boleto_id']}] {b['accion']} {s}"


def referencias_papel(reg: Reglamento, dd: DatosDia, inicio: str) -> dict[str, float]:
    """R0, R1 y R2 seguidas en papel desde `inicio` con el mismo capital inicial (se recalculan cada día)."""
    md = dd.md
    cap = float(reg.get("carteras.capital_inicial", 46.18))
    a = pd.Timestamp(inicio, tz="UTC")
    b = dd.dia + DIA
    if b <= a:
        return {"R0": cap, "R1": cap, "R2": cap}
    costo = float(reg.costos["comision_spot_pct"]) + float(reg.costos["deslizamiento_pct"]["grande"])
    btc = md.velas["BTCUSDT"].copy()
    hoy = dd.apertura_hoy("BTCUSDT")
    if hoy is not None and b not in btc.index:
        btc.loc[b, "open"] = hoy
    out = {}
    try:
        out["R0"] = cap * float(RF.r0_aguantar(btc, a, b, costo)[0].iloc[-1])
        out["R1"] = cap * float(RF.r1_marea(btc, md.marea, a, b, costo)[0].iloc[-1])
        out["R2"] = cap * float(RF.r2_canasta({s: v for s, v in md.velas.items() if s not in md.memes}, md.grandes,
                                              md.vol_mediano, md.marea, a, dd.dia, costo,
                                              int(reg.get("universo.canasta_n", 10)))[0].iloc[-1])
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


def ronda(reg: Reglamento, dd: DatosDia, avisar=print, bloquear_compras: str = "") -> dict[str, Any]:
    """Ronda completa del día: las dos carteras + referencias + archivo de boletos."""
    archivos_bots = AR.leer_todos(reg)
    seguro = not dd.datos_ok
    vetos, eventos = [], []
    for nombre, (d, err) in archivos_bots.items():
        if err and not (len(err) == 1 and err[0].startswith("no existe")):
            dd.avisos.append(f"{nombre} viene mal ({'; '.join(err)}): se ignora y hoy no hay entradas nuevas (modo seguro).")
            AR.registrar_tarea(reg, "RADAR" if nombre == "exclusiones.json" else "CENTINELA", nombre, False, "; ".join(err))
            seguro = True
        elif d is not None:
            vetos = d.get("vetos", vetos) if nombre == "vetos.json" else vetos
            eventos = d.get("eventos", eventos) if nombre == "eventos.json" else eventos
    out = {"dia": dd.dia.strftime("%Y-%m-%d"), "carteras": {}, "avisos": list(dd.avisos), "modo_seguro": seguro,
           "informativos": list(dd.informativos)}
    inicio = None
    for n in CARTERAS:
        out["carteras"][n] = ronda_cartera(reg, n, dd, vetos, eventos, forzar_seguro=seguro,
                                           bloquear_compras=bloquear_compras)
        inicio = inicio or cargar_estado(reg, n, out["dia"])["inicio"]
    out["referencias"] = referencias_papel(reg, dd, inicio or out["dia"])
    # ¿Un veto GLOBAL o de BTC frenó compras hoy? (para que el resumen no diga 👍)
    v = R.veto_activo(vetos, "BTCUSDT", (dd.dia + DIA + pd.Timedelta(minutes=10)).to_pydatetime())
    if v is not None:
        info = {"razon": " ".join(str(v.get("razon", "")).split())[:80], "vence": str(v.get("vence", ""))}
        if any("vetada por Noticias" in m for c in out["carteras"].values() for m in c.get("mensajes", [])):
            out["veto"] = info            # frenó compras: el resumen no da 👍
        else:
            out["veto_info"] = info       # vigente, pero hoy no cambió nada: solo se informa
    carpeta = AR.carpeta_datos(reg).parent / "salida"
    carpeta.mkdir(parents=True, exist_ok=True)
    todos = [b for c in out["carteras"].values() for b in c["boletos"]]
    AR.escribir_json_seguro(carpeta / f"boletos_{out['dia']}.json", todos)
    dia_dec = dd.dia + DIA
    if dia_dec in dd.md.grandes.index:  # para que ESTELA sepa de qué monedas tomar la foto
        g = [s for s in dd.md.grandes.columns if bool(dd.md.grandes.at[dia_dec, s])]
        AR.escribir_json_seguro(ruta_papel(reg) / "grandes.json", sorted(g), indent=None)
    hist = ruta_papel(reg) / "referencias.json"
    h = AR.leer_json_seguro(hist) if (hist.exists() or hist.with_name(hist.name + ".bak").exists()) else {}
    h[out["dia"]] = out["referencias"]
    AR.escribir_json_seguro(hist, h)
    out["avisos"] += [a[0].upper() + a[1:] + "." for a in AR.tomar_avisos()]  # copias anteriores usadas hoy
    return out


def sin_icono(m: str) -> str:
    return m[len("⚠️"):].strip() if m.startswith("⚠️") else m.strip()


def avisos_carteras(out: dict[str, Any]) -> dict[str, list[str]]:
    """Mensajes "⚠️" de cada cartera, agrupados por texto (la misma advertencia en A, B y C sale una vez).
    Los de conciliación y de stop sin llenar ya tienen su propia línea en el resumen."""
    grupos: dict[str, list[str]] = {}
    for n, c in out.get("carteras", {}).items():
        for m in c.get("mensajes", []):
            if m.startswith("⚠️") and "conciliación no cuadró" not in m and "STOP SIN LLENAR" not in m:
                grupos.setdefault(sin_icono(m), []).append(n)
    return grupos


def fuente_modo_seguro(out: dict[str, Any]) -> str | None:
    """El aviso del que sale la causa del MODO SEGURO (el primero que lo menciona; si ninguno, el primero)."""
    avisos = out.get("avisos", [])
    return next((a for a in avisos if "modo seguro" in a.lower()), avisos[0] if avisos else None)


def causa_modo_seguro(out: dict[str, Any], limite: int = 160) -> str:
    """La causa del MODO SEGURO en pocas palabras (del primer aviso que lo menciona), de `limite` caracteres o menos."""
    aviso = fuente_modo_seguro(out) or "datos no confiables"
    for corte in (": MODO SEGURO", ": se ignora", " (modo seguro)", "MODO SEGURO"):
        if corte in aviso:
            aviso = aviso.split(corte, 1)[0]
            break
    aviso = " ".join(aviso.split()).rstrip(" .:")
    return (aviso[:limite - 3] + "…") if len(aviso) > limite else aviso


def resumen_corto(out: dict[str, Any]) -> str:
    """Resumen para Ángelo: 10 líneas o menos, sin palabras técnicas; 👍 si no necesita nada de él."""
    lineas = [f"Ronda del {out['dia']} (papel)."]
    necesita = False
    solo_aviso = False   # MODO SEGURO: sin 👍, pero Ángelo no tiene que contestar nada
    fuente = None
    if out.get("modo_seguro"):
        # Va hasta arriba: en MODO SEGURO ninguna cartera compra, por la causa que sea
        causa = causa_modo_seguro(out)
        lineas.append(f"⚠️ MODO SEGURO: hoy no se compra ({causa}).")
        fuente = fuente_modo_seguro(out)
        if fuente and causa != causa_modo_seguro(out, limite=len(fuente)):
            lineas.append("⚠️ " + fuente)   # la causa se cortó: el aviso completo va justo abajo (y no se repite al final)
        solo_aviso = True
    if out.get("veto"):
        try:
            hasta = hora_cdmx(out["veto"]["vence"]).replace(" (hora CDMX)", ", hora CDMX")
        except ValueError:
            hasta = out["veto"]["vence"]
        lineas.append(f"⚠️ Veto activo de Noticias: hoy no se compra ({out['veto']['razon']}, hasta {hasta}).")
        necesita = True
    if out.get("veto_info"):
        try:
            hasta = hora_cdmx(out["veto_info"]["vence"]).replace(" (hora CDMX)", ", hora CDMX")
        except ValueError:
            hasta = out["veto_info"]["vence"]
        lineas.append(f"ℹ️ Veto activo de Noticias hasta {hasta} ({out['veto_info']['razon']}); hoy no cambió nada.")
    lineas += out.get("informativos", [])   # ℹ️ (pares raros, bStocks nuevas): solo informan, no piden respuesta
    if any(not c.get("conciliacion_ok", True) for c in out["carteras"].values()):
        # Va arriba para que nunca se corte: la conciliación bloquea TODAS las compras
        lineas.append("⚠️ La conciliación no cuadró: hoy no se compra. Pide a THE BOSS correr conciliar.")
        necesita = True
    for n, c in out["carteras"].items():
        compras = [b["simbolo"] for b in c["boletos"] if b["accion"] == "COMPRAR"]
        ventas = [b["simbolo"] for b in c["boletos"] if b["accion"] == "CERRAR"]
        txt = f"Cartera {n}: {c['capital']:.2f} USDT"
        if compras:
            txt += f" · compra {', '.join(compras)}"
        if ventas:
            txt += f" · vende {', '.join(ventas)}"
        if not compras and not ventas:
            txt += " · sin movimientos"
        lineas.append(txt)
        if c.get("detenido"):
            lineas.append(f"⚠️ Cartera {n} DETENIDA por caída máxima: necesita tu OK.")
            necesita = True
        elif c.get("pausa"):
            lineas.append(f"Cartera {n} en pausa: {c['pausa']}.")
    operan = [n for n, c in out["carteras"].items() if c.get("opera", True)]
    no_op = [f"{n} (necesita unos {c['capital_necesario']:.0f} USDT)" if c.get("capital_necesario") else n
             for n, c in out["carteras"].items() if not c.get("opera", True)]
    if no_op:
        lineas.append(f"Operan con el capital actual: {', '.join(operan) if operan else 'ninguna'}. "
                      f"No llegan al mínimo de Binance: {', '.join(no_op)}.")
    for n, c in out["carteras"].items():
        for s in c.get("stops_sin_llenar", []):
            lineas.append(f"⚠️ Cartera {n}: el stop de {s} no se llenó (el precio pasó su límite). Sigue abierta.")
            necesita = True
    for texto, ns in avisos_carteras(out).items():
        lineas.append(f"⚠️ Cartera{'s' if len(ns) > 1 else ''} {', '.join(ns)}: {texto}")
    r = out.get("referencias", {})
    if "R0" in r:
        lineas.append(f"Referencias: BTC {r['R0']:.2f} · BTC con marea {r['R1']:.2f} · canasta {r['R2']:.2f}")
    for a in [x for x in out.get("avisos", []) if x != fuente][:2]:   # el del MODO SEGURO ya va arriba: no se repite
        lineas.append("⚠️ " + a)
    lineas = lineas[:9]
    if necesita:
        lineas.append("Necesito tu respuesta (ver arriba).")
    elif solo_aviso:
        lineas.append("Solo para que sepas; no tienes que contestar.")
    else:
        lineas.append("👍 No necesito nada de ti.")
    return "\n".join(lineas)
