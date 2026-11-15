"""Dinero REAL: Spot, reglas de la Cartera A, motor M0 (solo BTC), solo largo (arreglos 129 a 140).

El programa NUNCA tiene llaves de Binance ni firma órdenes: solo lee datos públicos, emite boletos y lee los archivos
que EJECUTOR escribe con lo que contestó Binance (por el conector). Todo lo real vive en datos/real/ y en
salida/boletos_real_*.json, nunca mezclado con datos/papel/.

Falla cerrada: si falta o está viejo un dato del real, NO se compra. Lo que protege (poner el stop, vender a mercado,
reponer un stop) nunca se bloquea por MODO SEGURO, pausa, tope, conciliación o falta de datos.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import archivos as AR
from .reglamento import Reglamento

CARTERA = "REAL"
ESTADOS_STOP = ("ACTIVO", "SIN_STOP", "DISPARADO_SIN_LLENAR")
FOTO_MAX_MIN = 120   # minutos: una foto de saldo más vieja no sirve (un solo valor; real.foto_max_minutos lo puede fijar)
CAMPOS_ESTADO = ("cartera", "capital_inicial", "pico", "capital_inicio_dia", "capital_inicio_semana", "pausa_hasta",
                 "rachas", "posiciones", "cerradas")
CAMPOS_POSICION = ("id", "simbolo", "estrategia", "cantidad_comprada", "cantidad_neta", "precio_llenado", "comision",
                   "moneda_comision", "stop", "limite_stop", "id_stop", "orden_id_stop", "estado_stop", "t_entrada")


class EstadoRealDanado(Exception):
    """El estado real no se puede leer o tiene un formato raro. La ronda real no compra hasta que se revise."""


def ruta_real(reg: Reglamento) -> Path:
    return AR.carpeta_datos(reg) / "real"


def archivo_estado(reg: Reglamento) -> Path:
    return ruta_real(reg) / "cartera_REAL.json"


def foto_max_minutos(reg: Reglamento) -> float:
    return float(reg.get("real.foto_max_minutos", FOTO_MAX_MIN))


def estado_nuevo(capital: float, inicio: str) -> dict[str, Any]:
    """La cartera real recién creada: la misma forma que una de papel, sin posiciones. Solo cambia con llenados
    confirmados por EJECUTOR (registrar-llenado --real), nunca por simulación."""
    return {"cartera": CARTERA, "reglas_de": "A", "inicio": inicio, "capital_inicial": capital, "pico": capital,
            "capital_inicio_dia": capital, "capital_inicio_semana": capital, "dia_ref": None, "semana_ref": None,
            "pausa_hasta": None, "pausa_motivo": "", "detenido": False, "rachas": {}, "saltar_rondas": {},
            "posiciones": [], "cerradas": [], "ajustes": [], "bloqueo_compras": None}


def _revisar_forma(est: Any) -> list[str]:
    if not isinstance(est, dict):
        return ["no es un objeto"]
    errores = [f"falta '{k}'" for k in CAMPOS_ESTADO if k not in est]
    if errores:
        return errores
    if est.get("cartera") != CARTERA:
        errores.append(f"dice cartera {est.get('cartera')!r} y debe ser {CARTERA}")
    if not isinstance(est["posiciones"], list) or not isinstance(est["cerradas"], list):
        return errores + ["posiciones y cerradas deben ser listas"]
    for i, p in enumerate(est["posiciones"]):
        if not isinstance(p, dict):
            errores.append(f"la posición #{i + 1} no es un objeto")
            continue
        faltan = [k for k in CAMPOS_POSICION if k not in p]
        if faltan:
            errores.append(f"a la posición #{i + 1} le falta {', '.join(faltan)}")
        elif p["estado_stop"] not in ESTADOS_STOP:
            errores.append(f"la posición #{i + 1} tiene estado_stop {p['estado_stop']!r}")
    for k in ("capital_inicial", "pico", "capital_inicio_dia", "capital_inicio_semana"):
        if isinstance(est.get(k), bool) or not isinstance(est.get(k), (int, float)):
            errores.append(f"'{k}' no es un número")
    return errores


def cargar_estado(reg: Reglamento, inicio: str = "") -> dict[str, Any]:
    """Lee datos/real/cartera_REAL.json. Si no existe (ni su copia), regresa una cartera nueva con
    `carteras.capital_inicial`. Si está dañado, NO usa la copia .bak (podría no traer la última compra y la ronda
    compraría dos veces): lanza EstadoRealDanado con qué hacer."""
    arch = archivo_estado(reg)
    bak = arch.with_name(arch.name + ".bak")
    if not arch.exists():
        if bak.exists():
            raise EstadoRealDanado(f"Falta {arch.name} pero existe su copia {bak.name}. No uso la copia (podría no traer "
                                   f"la última compra): Ángelo debe revisar y restaurar el archivo a mano.")
        return estado_nuevo(reg.cifra("carteras.capital_inicial"), inicio)
    try:
        est = json.loads(arch.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as e:
        raise EstadoRealDanado(f"El estado real ({arch.name}) está dañado o no se puede leer ({type(e).__name__}). "
                               f"La ronda real NO compra. No uso la copia .bak: Ángelo debe revisarlo.")
    errores = _revisar_forma(est)
    if errores:
        raise EstadoRealDanado(f"El estado real ({arch.name}) tiene un formato raro: {'; '.join(errores)[:200]}. "
                               f"La ronda real NO compra hasta que Ángelo lo revise.")
    return est


def guardar_estado(reg: Reglamento, est: dict[str, Any]) -> None:
    """Escritura segura (temporal + copia .bak)."""
    AR.escribir_json_seguro(archivo_estado(reg), est)


def universo_real(reg: Reglamento) -> list[str]:
    """Monedas que el real puede comprar: las de M0 (estrategias.M0.universo; hoy solo BTC)."""
    u = str(reg.estrategias.get("M0", {}).get("universo", "BTC")).upper()
    return [u] if u else ["BTC"]


# ---------------------------------------------------------------------------
# Foto de saldo (arreglo 130): la respuesta del conector, tal cual, convertida en datos/real/saldo_binance.json
# ---------------------------------------------------------------------------

def archivo_saldo(reg: Reglamento) -> Path:
    return ruta_real(reg) / "saldo_binance.json"


def _desenvolver(x: Any, clave: str | None) -> Any:
    """La respuesta del conector puede venir sola o envuelta ({"data": …} o {"result": …})."""
    if isinstance(x, dict) and (clave is None or clave not in x):
        for k in ("data", "result", "response"):
            if k in x and isinstance(x[k], (dict, list)):
                return x[k]
    return x


def _num(x: Any) -> float | None:
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def leer_respuesta(ruta: str | Path) -> tuple[Any, str]:
    """(contenido, error). Error si no existe o no es JSON."""
    ruta = Path(ruta)
    try:
        return json.loads(ruta.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, f"no existe {ruta}"
    except (OSError, ValueError, RecursionError) as e:
        return None, f"{ruta.name} está roto o no es JSON ({type(e).__name__})"


def armar_foto(cuenta: Any, ordenes: Any, ahora: datetime) -> tuple[dict[str, Any] | None, list[str]]:
    """Valida el formato de getAccount y getOpenOrders y arma la foto (sin decidir nada todavía)."""
    errores = []
    cuenta = _desenvolver(cuenta, "balances")
    ordenes = _desenvolver(ordenes, None)
    if not isinstance(cuenta, dict) or not isinstance(cuenta.get("balances"), list):
        return None, ["la respuesta de la cuenta (spot.getAccount) no trae 'balances'"]
    if not isinstance(cuenta.get("updateTime"), int) or isinstance(cuenta.get("updateTime"), bool):
        errores.append("la respuesta de la cuenta no trae la hora ('updateTime')")
    if cuenta.get("canTrade") is not True:
        errores.append("la cuenta NO tiene permiso de operar (canTrade): revisa la llave del conector en Binance")
    if cuenta.get("accountType") not in (None, "SPOT"):
        errores.append(f"la cuenta es {cuenta.get('accountType')}, no SPOT")
    activos = {}
    for b in cuenta["balances"]:
        libre, bloq = (_num(b.get("free")), _num(b.get("locked"))) if isinstance(b, dict) else (None, None)
        if libre is None or bloq is None or not isinstance(b.get("asset"), str):
            errores.append(f"un saldo viene con formato raro: {str(b)[:60]}")
            continue
        if libre > 0 or bloq > 0:
            activos[b["asset"].upper()] = {"libre": libre, "bloqueado": bloq}
    if not isinstance(ordenes, list):
        errores.append("la respuesta de órdenes abiertas (spot.getOpenOrders) no es una lista")
        ordenes = []
    abiertas = []
    for o in ordenes:
        if not isinstance(o, dict) or not all(k in o for k in ("symbol", "orderId", "side", "type", "status")):
            errores.append(f"una orden abierta viene con formato raro: {str(o)[:60]}")
            continue
        abiertas.append({"simbolo": o["symbol"], "id": o["orderId"], "clientOrderId": o.get("clientOrderId"),
                         "lado": o["side"], "tipo": o["type"], "estado": o["status"],
                         "cantidad": _num(o.get("origQty")), "stopPrice": _num(o.get("stopPrice")),
                         "precio": _num(o.get("price"))})
    usdt = activos.get("USDT", {"libre": 0.0, "bloqueado": 0.0})
    foto = {"hora_utc": ahora.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "update_time_cuenta": cuenta.get("updateTime"), "usdt_libre": usdt["libre"],
            "usdt_bloqueado": usdt["bloqueado"], "activos": activos, "ordenes_abiertas": abiertas}
    return foto, errores


def registrar_saldo(reg: Reglamento, ruta_cuenta: str | Path, ruta_ordenes: str | Path,
                    precio: Callable[[str], float | None], ahora: datetime | None = None) -> tuple[bool, list[str]]:
    """Arreglo 130: lee los dos archivos que guardó EJECUTOR, valida y escribe datos/real/saldo_binance.json más la
    foto numerada del día en datos/real/saldos/. Con cualquier ❌ la foto queda con ok:false (la ronda real no compra
    con ella; una foto vieja buena no se reutiliza). Regresa (ok, mensajes)."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errores, avisos = [], []
    crudos = []
    for ruta in (ruta_cuenta, ruta_ordenes):
        x, err = leer_respuesta(ruta)
        if err:
            errores.append(err)
        else:
            edad = (ahora.timestamp() - Path(ruta).stat().st_mtime) / 60
            if edad > foto_max_minutos(reg):
                errores.append(f"{Path(ruta).name} se guardó hace {edad:.0f} min (máximo {foto_max_minutos(reg):.0f}): "
                               f"vuelve a pedirlo a Binance")
        crudos.append(x)
    foto = None
    if not errores:
        foto, errores = armar_foto(crudos[0], crudos[1], ahora)
    if foto is not None:
        try:
            est = cargar_estado(reg)
        except EstadoRealDanado as e:
            est = None
            errores.append(str(e))
        en_posicion = {p["simbolo"].upper().removesuffix("USDT") for p in (est or {}).get("posiciones", [])}
        foto["otros"] = sorted(a for a in foto["activos"] if a != "USDT" and a not in en_posicion)
        for a in universo_real(reg):
            if a not in foto["activos"] or a in en_posicion or est is None:
                continue
            total = foto["activos"][a]["libre"] + foto["activos"][a]["bloqueado"]
            px = precio(a + "USDT")
            if px is None:
                errores.append(f"hay {total:g} {a} en la cuenta y no pude leer su precio para saber si vale más de 1 USDT")
            elif total * px > 1.0:
                errores.append(f"hay {total:g} {a} (unos {total * px:.2f} USDT) en la cuenta que el estado real no conoce: "
                               f"la ronda real no compra hasta que Ángelo lo revise")
            else:
                avisos.append(f"ℹ️ quedan {total:g} {a} (menos de 1 USDT; polvo de comisiones): no se usan")
    salida = {**(foto or {"hora_utc": ahora.isoformat(timespec="seconds")}), "ok": not errores, "errores": errores}
    AR.escribir_json_seguro(archivo_saldo(reg), salida)
    carpeta = ruta_real(reg) / "saldos"
    carpeta.mkdir(parents=True, exist_ok=True)
    n = 1 + sum(1 for _ in carpeta.glob(f"{ahora:%Y-%m-%d}_*.json"))
    while (carpeta / f"{ahora:%Y-%m-%d}_{n:03d}.json").exists():
        n += 1
    AR.escribir_json_seguro(carpeta / f"{ahora:%Y-%m-%d}_{n:03d}.json", salida)
    return not errores, errores + avisos


def leer_foto(reg: Reglamento, ahora: datetime | None = None) -> tuple[dict[str, Any] | None, str]:
    """(foto, "") si existe, está ok y tiene menos de `foto_max_minutos`; si no, (foto o None, por qué no sirve)."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    arch = archivo_saldo(reg)
    if not arch.exists():
        return None, "no hay foto de saldo (EJECUTOR debe correr registrar-saldo)"
    try:
        foto = json.loads(arch.read_text(encoding="utf-8"))
        hora = datetime.fromisoformat(str(foto["hora_utc"]))
    except (OSError, ValueError, RecursionError, KeyError, TypeError):
        return None, "la foto de saldo está dañada (EJECUTOR debe repetir registrar-saldo)"
    if not isinstance(foto, dict) or foto.get("ok") is not True:
        return foto if isinstance(foto, dict) else None, "la última foto de saldo salió con ❌: " + \
            "; ".join(foto.get("errores", []) if isinstance(foto, dict) else [])[:200]
    edad = (ahora - hora.astimezone(timezone.utc)).total_seconds() / 60
    if edad > foto_max_minutos(reg) or edad < -5:
        return foto, f"la foto de saldo tiene {edad:.0f} min (máximo {foto_max_minutos(reg):.0f}): EJECUTOR debe repetirla"
    return foto, ""


# ---------------------------------------------------------------------------
# Conciliación real (arreglo 131) y ajuste del capital (solo Ángelo)
# ---------------------------------------------------------------------------

def moneda(simbolo: str) -> str:
    return simbolo.upper().removesuffix("USDT")


def costo_usdt(p: dict[str, Any]) -> float:
    """Lo que salió de USDT al comprar: cantidad comprada × precio de llenado (+ la comisión si se cobró en USDT)."""
    if "costo_usdt" in p:
        return float(p["costo_usdt"])
    com = float(p["comision"]) if str(p.get("moneda_comision", "")).upper() == "USDT" else 0.0
    return float(p["cantidad_comprada"]) * float(p["precio_llenado"]) + com


def usdt_esperado(est: dict[str, Any]) -> float:
    """capital inicial + ajustes de Ángelo + ganancias cerradas − costo de lo abierto."""
    return (float(est["capital_inicial"]) + sum(float(a.get("delta", 0)) for a in est.get("ajustes", []))
            + sum(float(c["ganancia_usdt"]) for c in est["cerradas"]) - sum(costo_usdt(p) for p in est["posiciones"]))


def archivo_conciliacion(reg: Reglamento) -> Path:
    return ruta_real(reg) / "conciliacion_real.json"


def conciliar(reg: Reglamento, ahora: datetime | None = None, escribir: bool = True) -> dict[str, Any]:
    """Compara la última foto de saldo contra cartera_REAL.json. Falla cerrada: sin foto, con foto vieja o con ❌, o
    con el estado dañado, NO cuadra. Una posición sin su stop vivo queda marcada SIN_STOP (con `escribir`).
    Regresa {"ok", "lineas": [(ok, texto)], "diferencias", "errores", "sin_stop", "foto_hora"}."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tol = float(reg.get("conciliacion.tolerancia_usdt", 0.10))
    res: dict[str, Any] = {"fecha": ahora.isoformat(timespec="seconds"), "ok": False, "foto_hora": None,
                           "diferencias": {}, "errores": [], "sin_stop": [], "lineas": []}
    foto, por_que = leer_foto(reg, ahora)
    if por_que:
        res["errores"].append(por_que)
    try:
        est = cargar_estado(reg)
    except EstadoRealDanado as e:
        est = None
        res["errores"].append(str(e))
    lineas = res["lineas"]
    if foto is not None and not por_que and est is not None:
        res["foto_hora"] = foto["hora_utc"]
        dif = res["diferencias"]
        usdt = float(foto["usdt_libre"]) + float(foto["usdt_bloqueado"])
        esperado = usdt_esperado(est)
        d = usdt - esperado
        if abs(d) > tol:
            dif["usdt"] = round(d, 6)
        lineas.append((abs(d) <= tol, f"USDT: {usdt:.4f} en Binance y {esperado:.4f} anotado (diferencia {d:+.4f}, "
                                      f"tolerancia {tol:g})" + ("" if abs(d) <= tol else ": un cambio que no viene de "
                                      "llenados (¿depósito, retiro, comisión rara?). Solo Ángelo lo resuelve con "
                                      "ajustar-capital-real.")))
        ids_stop = set()
        cambio = False
        for p in est["posiciones"]:
            m = moneda(p["simbolo"])
            act = foto["activos"].get(m, {"libre": 0.0, "bloqueado": 0.0})
            hay = float(act["libre"]) + float(act["bloqueado"])
            paso = float(p.get("paso_cantidad") or 0.0)
            ok_c = abs(hay - float(p["cantidad_neta"])) <= paso + 1e-12
            if not ok_c:
                dif.setdefault("activos", {})[m] = round(hay - float(p["cantidad_neta"]), 12)
            lineas.append((ok_c, f"{m}: {hay:g} en Binance y {float(p['cantidad_neta']):g} anotado"))
            ids_stop.add(p["id_stop"])
            st = next((o for o in foto["ordenes_abiertas"] if o.get("clientOrderId") == p["id_stop"]), None)
            if st is None or st.get("lado") != "SELL" or st.get("estado") != "NEW":
                res["sin_stop"].append(m)
                dif.setdefault("sin_stop", []).append(m)
                lineas.append((False, f"SIN STOP: {m}"))
                if p["estado_stop"] != "SIN_STOP":
                    p["estado_stop"] = "SIN_STOP"
                    cambio = True
            elif (abs(float(st.get("cantidad") or 0) - float(p["cantidad_neta"])) > 1e-12
                  or abs(float(st.get("stopPrice") or 0) - float(p["stop"])) > 1e-9):
                dif.setdefault("stop_distinto", []).append(m)
                lineas.append((False, f"el stop de {m} no es el anotado: {st.get('cantidad')} a {st.get('stopPrice')} y "
                                      f"debe ser {p['cantidad_neta']} a {p['stop']}"))
            else:
                lineas.append((True, f"stop de {m} vivo ({p['cantidad_neta']} a {p['stop']})"))
        for o in foto["ordenes_abiertas"]:
            if o.get("clientOrderId") not in ids_stop:
                dif.setdefault("ordenes_desconocidas", []).append(o.get("clientOrderId") or o.get("id"))
                lineas.append((False, f"orden abierta que el estado real no conoce: {o.get('lado')} {o.get('tipo')} "
                                      f"{o.get('simbolo')} (id {o.get('id')}). Avisa a THE BOSS con prioridad"))
        if cambio and escribir:
            guardar_estado(reg, est)
    for e in res["errores"]:
        lineas.append((False, e))
    res["ok"] = not res["errores"] and not res["diferencias"]
    if escribir:
        AR.escribir_json_seguro(archivo_conciliacion(reg), {k: v for k, v in res.items() if k != "lineas"})
    return res


def conciliacion_ok(reg: Reglamento, ahora: datetime | None = None) -> tuple[bool, str]:
    """Para el real (NO es papel.conciliacion_ok, que da True si falta el archivo): ok solo si conciliacion_real.json
    existe, salió ok y es de la foto de saldo vigente (fresca)."""
    foto, por_que = leer_foto(reg, ahora)
    if por_que:
        return False, por_que
    try:
        c = json.loads(archivo_conciliacion(reg).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, "no hay conciliación real (corre conciliar --real)"
    except (OSError, ValueError, RecursionError):
        return False, "la conciliación real está dañada (corre conciliar --real)"
    if not isinstance(c, dict) or c.get("foto_hora") != foto["hora_utc"]:
        return False, "la conciliación real no es de la última foto de saldo (corre conciliar --real)"
    if c.get("ok") is not True:
        return False, "la conciliación real no cuadró: " + json.dumps(c.get("diferencias"), ensure_ascii=False)[:160]
    return True, ""


def ajustar_capital(reg: Reglamento, usdt: float, ok_angelo: str, ahora: datetime | None = None) -> tuple[bool, str]:
    """Solo Ángelo: registra un cambio de USDT que no viene de llenados (depósito, retiro, comisión rara). Anota la
    fecha, la cifra y su texto; desde ahí lo esperado es `usdt`, y el pico y los puntos del día y de la semana se rehacen
    con el capital nuevo (USDT + costo de lo abierto). Sin el texto no hace nada."""
    if not ok_angelo or not ok_angelo.strip():
        return False, "Falta el OK de Ángelo (--ok-angelo \"…\"). Sin eso no se ajusta nada."
    if not (usdt >= 0):
        return False, "La cifra de USDT no es válida."
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    est = cargar_estado(reg, ahora.strftime("%Y-%m-%d"))
    antes = usdt_esperado(est)
    capital = usdt + sum(costo_usdt(p) for p in est["posiciones"])
    est.setdefault("ajustes", []).append({"fecha": ahora.isoformat(timespec="seconds"), "usdt": usdt,
                                          "delta": round(usdt - antes, 8), "texto": ok_angelo.strip(),
                                          "pico_anterior": est["pico"], "capital_nuevo": capital})
    est["pico"] = est["capital_inicio_dia"] = est["capital_inicio_semana"] = capital
    guardar_estado(reg, est)
    return True, (f"Capital real ajustado con el OK de Ángelo: USDT esperado {antes:.4f} → {usdt:.4f}; el pico y los puntos "
                  f"del día y de la semana quedan en {capital:.2f} USDT.")


def estado_ok(reg: Reglamento) -> tuple[bool, str]:
    """(True, "") si el estado real se lee bien; si no, (False, el mensaje con qué hacer)."""
    try:
        cargar_estado(reg)
    except EstadoRealDanado as e:
        return False, str(e)
    return True, ""
