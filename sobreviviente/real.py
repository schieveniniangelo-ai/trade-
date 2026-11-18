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
        sin_estado, sobrante = {}, {}
        for a in universo_real(reg):
            if a in foto["activos"] and a in en_posicion and est is not None:
                # Arreglo 180: BTC de más sobre lo anotado en la posición (no es error de la foto: la posición sigue
                # revisándose; conciliar --real lo marca y la ronda real vende solo el sobrante)
                total = foto["activos"][a]["libre"] + foto["activos"][a]["bloqueado"]
                sobra, _ = _sobra(est, a, total)
                px = precio(a + "USDT") if sobra > 0 else None
                if sobra > 0 and (px is None or sobra * px > 1.0):
                    sobrante[a] = sobra
                    avisos.append(f"ℹ️ hay {sobra:g} {a} de más sobre lo anotado en la posición: conciliar --real lo "
                                  f"marca SIN STOP y la ronda real arma su VENTA URGENTE (arreglo 180)")
                continue
            if a not in foto["activos"] or a in en_posicion or est is None:
                continue
            total = foto["activos"][a]["libre"] + foto["activos"][a]["bloqueado"]
            px = precio(a + "USDT")
            if px is None:
                errores.append(f"hay {total:g} {a} en la cuenta y no pude leer su precio para saber si vale más de 1 USDT")
                sin_estado[a] = total
            elif total * px > 1.0:
                errores.append(f"hay {total:g} {a} (unos {total * px:.2f} USDT) en la cuenta que el estado real no conoce: "
                               f"la ronda real no compra hasta que Ángelo lo revise")
                sin_estado[a] = total
            else:
                avisos.append(f"ℹ️ quedan {total:g} {a} (menos de 1 USDT; polvo de comisiones): no se usan")
        if sin_estado:     # arreglo 170: conciliar --real lo marca SIN STOP y bloquea las compras
            foto["sin_estado"] = sin_estado
        if sobrante:       # arreglo 180
            foto["sobrante"] = sobrante
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


REVISION = "revision_despues_de_compra"     # arreglo 171: la deja STOP_PUESTO; la borra un conciliar --real que cuadra
REVISION_DESPUES_DEL_STOP = (
    "EN SEGUIDA, sin esperar a la ronda de mañana: foto de saldo nueva (spot.getAccount y spot.getOpenOrders → "
    "registrar-saldo) y conciliar --real. Si sale ❌ o SIN STOP, avisa a THE BOSS con prioridad: no se compra nada más "
    "(arreglo 171).")
AVISO_SIN_ANOTAR = (
    "❌ URGENTE para THE BOSS, prioridad máxima: puede haber {m} SIN STOP en Binance que el estado real no tiene "
    "anotado. Avisa a Ángelo YA: en Binance hay que ponerle stop a ese {m} o venderlo a mercado (lo decide él). El "
    "programa NO vende solo. Después se anota lo que pasó con registrar-llenado --real. Las compras reales quedan "
    "bloqueadas hasta que Ángelo las reanude (reanudar --cartera REAL).")


def compras_sin_anotar(reg: Reglamento) -> list[dict[str, Any]]:
    """Arreglo 170: los renglones COMPRA_ENVIADA de llenados.jsonl sin COMPRA_LLENADA, COMPRA_PARCIAL ni
    COMPRA_NO_LLENADA del mismo boleto: el EJECUTOR pudo caerse entre la compra y el registro (puede haber BTC sin
    stop). Arreglo 172: la VENTA_LLENADA de una venta urgente (boleto SIN_ANOTAR) también cierra las compras que cubre."""
    filas = leer_llenados(reg)
    terminadas = {x.get("boleto_id") for x in filas if x.get("evento") in COMPRAS}
    terminadas |= {c for x in filas if x.get("evento") == "VENTA_LLENADA" and isinstance(x.get("cubre"), list)
                   for c in x["cubre"] if isinstance(c, str)}
    return [x for x in filas if x.get("evento") == ENVIADA and x.get("boleto_id") not in terminadas]


def _moneda_del_boleto(reg: Reglamento, boleto_id: Any) -> str:
    b = buscar_boleto(reg, str(boleto_id))
    if b is not None and isinstance(b.get("simbolo"), str):
        return moneda(b["simbolo"])
    partes = str(boleto_id).split("-")       # 20261115-RA-COM-BTC-1a2b3c4d
    return partes[3] if len(partes) >= 5 else "?"


def _antes_de(hora_foto: Any, desde: Any) -> bool:
    """Arreglo 171: ¿la foto es de antes de `desde` (la hora de STOP_PUESTO)? Si `desde` no se entiende, no."""
    try:
        return datetime.fromisoformat(str(hora_foto)) < datetime.fromisoformat(str(desde))
    except (TypeError, ValueError):
        return False


def _foto_fresca(reg: Reglamento, foto: dict[str, Any], ahora: datetime) -> bool:
    """¿La foto (aunque haya salido con ❌) es de hace menos de `foto_max_minutos`? Viene de `leer_foto`, que ya
    revisó que su hora se entiende."""
    hora = datetime.fromisoformat(str(foto["hora_utc"])).astimezone(timezone.utc)
    edad = (ahora - hora).total_seconds() / 60
    return -5 <= edad <= foto_max_minutos(reg)


def _sobra(est: dict[str, Any], a: str, total: float) -> tuple[float, float]:
    """Arreglo 180: (lo que hay de más sobre lo anotado en las posiciones de esa moneda, lo anotado). 0 si la
    diferencia no pasa del paso de Binance de la posición."""
    pos = [p for p in est["posiciones"] if moneda(p["simbolo"]) == a]
    anotado = sum(float(p["cantidad_neta"]) for p in pos)
    paso = max([float(p.get("paso_cantidad") or 0.0) for p in pos] or [0.0])
    sobra = total - anotado
    return (sobra if sobra > paso + 1e-12 else 0.0), anotado


def sobrante_en_foto(reg: Reglamento, est: dict[str, Any], foto: Any, ahora: datetime) -> dict[str, dict[str, float]]:
    """Arreglo 180: el BTC DE MÁS sobre lo anotado en una posición, según una foto FRESCA que lo marcó (`sobrante`) y
    el estado de AHORA. {moneda: {"sobra", "hay", "anotado", "libre", "bloqueado"}}; {} sin foto fresca."""
    try:
        if not isinstance(foto, dict) or not isinstance(foto.get("sobrante"), dict) or not _foto_fresca(reg, foto, ahora):
            return {}
    except (KeyError, TypeError, ValueError):
        return {}
    activos = foto.get("activos") if isinstance(foto.get("activos"), dict) else {}
    en_posicion = {moneda(p["simbolo"]) for p in est["posiciones"]}
    out = {}
    for a in universo_real(reg):
        if a not in foto["sobrante"] or a not in en_posicion:
            continue
        act = activos.get(a) if isinstance(activos.get(a), dict) else {}
        libre, bloq = _num(act.get("libre")) or 0.0, _num(act.get("bloqueado")) or 0.0
        sobra, anotado = _sobra(est, a, libre + bloq)
        if sobra > 0:
            out[a] = {"sobra": sobra, "hay": libre + bloq, "anotado": anotado, "libre": libre, "bloqueado": bloq}
    return out


def _sin_anotar(reg: Reglamento, res: dict[str, Any], foto: Any, est: dict[str, Any] | None,
                ahora: datetime) -> bool:
    """Arreglo 170: marca SIN STOP lo que puede estar en Binance sin que el estado real lo sepa y bloquea las compras.
    Regresa True si cambió el estado (lo guarda `conciliar`, solo con `escribir`)."""
    from . import papel as P
    casos = []
    for x in compras_sin_anotar(reg):
        m = _moneda_del_boleto(reg, x.get("boleto_id"))
        hora = P.hora_cdmx(x["hora_utc"]) if isinstance(x.get("hora_utc"), str) else "sin hora"
        bid = x.get("boleto_id")
        casos.append((m, f"SIN STOP: {m} — la compra del boleto {bid} se mandó (COMPRA_ENVIADA, {hora}) y no tiene "
                         f"COMPRA_LLENADA, COMPRA_PARCIAL ni COMPRA_NO_LLENADA: puede haber {m} sin stop en Binance",
                      f"SIN STOP: {m} (compra enviada sin anotar, boleto {bid})"))
        res["diferencias"].setdefault("compra_sin_anotar", []).append(bid)
    if isinstance(foto, dict) and isinstance(foto.get("sin_estado"), dict) and est is not None \
            and _foto_fresca(reg, foto, ahora):
        en_posicion = {moneda(p["simbolo"]) for p in est["posiciones"]}
        for a, cant in foto["sin_estado"].items():
            if a in en_posicion:      # ya se anotó: la revisión de posiciones y stops se encarga
                continue
            casos.append((a, f"SIN STOP: {a} — hay {cant:g} {a} en Binance que el estado real no conoce (no tiene stop "
                             f"anotado)", f"SIN STOP: {a} en la cuenta que el estado real no conoce"))
            res["diferencias"].setdefault("sin_estado", {})[a] = cant
    if est is not None:          # arreglo 180: el BTC de más sobre lo anotado en la posición tampoco tiene stop
        for a, x in sobrante_en_foto(reg, est, foto, ahora).items():
            casos.append((a, f"SIN STOP: {x['sobra']:g} {a} de más — hay {x['hay']:g} {a} en Binance y la posición "
                             f"anota {x['anotado']:g}: el sobrante no tiene stop (la ronda real arma su VENTA URGENTE)",
                          f"SIN STOP: {a} de más en la cuenta que el estado real no conoce"))
            res["diferencias"].setdefault("sobrante", {})[a] = x["sobra"]
    cambio = False
    for m, linea, motivo in casos:
        res["lineas"].append((False, linea))
        res["sin_anotar"].append(m)
        if m not in res["sin_stop"]:
            res["sin_stop"].append(m)
        if est is not None and not est.get("bloqueo_compras"):
            est["bloqueo_compras"] = {"desde": ahora.isoformat(timespec="seconds"), "motivo": motivo}
            cambio = True
    res["avisos"] = [AVISO_SIN_ANOTAR.format(m=m) for m in dict.fromkeys(res["sin_anotar"])]
    return cambio


def conciliar(reg: Reglamento, ahora: datetime | None = None, escribir: bool = True) -> dict[str, Any]:
    """Compara la última foto de saldo contra cartera_REAL.json. Falla cerrada: sin foto, con foto vieja o con ❌, o
    con el estado dañado, NO cuadra. Una posición sin su stop vivo queda marcada SIN_STOP (con `escribir`).
    Regresa {"ok", "lineas": [(ok, texto)], "diferencias", "errores", "sin_stop", "sin_anotar", "avisos", "foto_hora"}.

    Arreglo 170: una compra con COMPRA_ENVIADA y sin su resultado anotado (aunque no haya foto), o BTC en una foto
    fresca que el estado real no conoce, también es SIN STOP: bloquea las compras y deja en `avisos` el aviso para THE
    BOSS (poner stop o vender; lo decide Ángelo). No inventa posiciones ni boletos de venta: el código no vende solo
    (arreglo 172: el boleto de VENTA URGENTE de ese BTC lo arma la ronda real; lo pone el EJECUTOR).

    Arreglo 171: si STOP_PUESTO dejó pendiente la revisión justo después de la compra, una foto válida tomada DESPUÉS
    de la compra la hace: si cuadra, se borra; si no, `bloqueo_compras` (no se compra nada más hasta que Ángelo revise).
    Con una foto de ANTES de la compra no se compara nada (❌, pide repetir la foto): así no hay SIN STOP falso."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tol = float(reg.get("conciliacion.tolerancia_usdt", 0.10))
    res: dict[str, Any] = {"fecha": ahora.isoformat(timespec="seconds"), "ok": False, "foto_hora": None,
                           "diferencias": {}, "errores": [], "sin_stop": [], "sin_anotar": [], "avisos": [],
                           "lineas": []}
    foto, por_que = leer_foto(reg, ahora)
    if por_que:
        res["errores"].append(por_que)
    try:
        est = cargar_estado(reg)
    except EstadoRealDanado as e:
        est = None
        res["errores"].append(str(e))
    rotos = llenados_rotos(reg)
    if rotos:                  # arreglo 176: un renglón ilegible puede esconder una compra enviada: falla cerrada
        res["errores"].append(aviso_llenados_rotos(rotos))
        res["diferencias"]["llenados_rotos"] = rotos
    lineas = res["lineas"]
    cambio = _sin_anotar(reg, res, foto, est, ahora)      # arreglo 170
    rev = est.get(REVISION) if isinstance(est, dict) and isinstance(est.get(REVISION), dict) else None
    if rev is not None and foto is not None and not por_que and _antes_de(foto["hora_utc"], rev.get("desde")):
        # Arreglo 171: con una foto de antes de la compra no se juzga (marcaría un SIN STOP falso y la ronda
        # mandaría vender)
        from . import papel as P
        por_que = (f"la foto de saldo ({P.hora_cdmx(foto['hora_utc'])}) es de antes de la compra del boleto "
                   f"{rev.get('boleto')}: no sirve para revisarla. EJECUTOR: foto de saldo nueva (registrar-saldo) y "
                   f"otra vez conciliar --real")
        res["errores"].append(por_que)
    revisada = foto is not None and not por_que and est is not None
    if revisada:
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
            if st is None and hay < max(paso, 1e-12):
                # Arreglo 179: el stop se ejecutó normal (ni stop abierto ni BTC): no es SIN STOP ni bloquea; falta
                # anotarlo
                dif.setdefault("stop_ejecutado", []).append(m)
                lineas.append((False, f"{m}: el stop ya se ejecutó (no hay stop abierto y quedan {hay:g} {m}, menos que "
                                      f"el paso de {paso:g}). No es SIN STOP: EJECUTOR confirma con spot.getOrder y "
                                      f"registra STOP_EJECUTADO (registrar-llenado --real) con la cantidad y el precio "
                                      f"de la venta"))
            elif st is None or st.get("lado") != "SELL" or st.get("estado") != "NEW":
                res["sin_stop"].append(m)
                dif.setdefault("sin_stop", []).append(m)
                lineas.append((False, f"SIN STOP: {m}"))
                if p["estado_stop"] != "SIN_STOP":
                    p["estado_stop"] = "SIN_STOP"
                    cambio = True
                if not est.get("bloqueo_compras"):   # arreglo 137: sin compras hasta que Ángelo diga lo contrario
                    est["bloqueo_compras"] = {"desde": ahora.isoformat(timespec="seconds"), "motivo": f"SIN STOP: {m}"}
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
    for e in res["errores"]:
        lineas.append((False, e))
    res["ok"] = not res["errores"] and not res["diferencias"]
    if rev is not None and revisada:      # arreglo 171: esta conciliación es la revisión justo después de la compra
        if res["ok"]:
            lineas.append((True, f"revisión justo después de la compra (boleto {rev.get('boleto')}): cuadra"))
        else:
            motivo = f"la revisión justo después de la compra (boleto {rev.get('boleto')}) no cuadró"
            lineas.append((False, f"{motivo}: no se compra nada más hasta que Ángelo revise (reanudar --cartera REAL)"))
            if not est.get("bloqueo_compras"):
                est["bloqueo_compras"] = {"desde": ahora.isoformat(timespec="seconds"), "motivo": motivo}
        est.pop(REVISION, None)
        cambio = True
    if cambio and escribir and est is not None:
        guardar_estado(reg, est)
    if escribir:
        AR.escribir_json_seguro(archivo_conciliacion(reg), {k: v for k, v in res.items() if k != "lineas"})
    return res


def conciliacion_ok(reg: Reglamento, ahora: datetime | None = None) -> tuple[bool, str]:
    """Para el real (NO es papel.conciliacion_ok, que desde el arreglo 167 también da False si falta el archivo, salvo el
    primer día después de reiniciar-papel): ok solo si conciliacion_real.json existe, salió ok y es de la foto de saldo
    vigente (fresca)."""
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
    est["bloqueo_compras"] = None     # arreglo 137: Ángelo ya revisó
    guardar_estado(reg, est)
    return True, (f"Capital real ajustado con el OK de Ángelo: USDT esperado {antes:.4f} → {usdt:.4f}; el pico y los puntos "
                  f"del día y de la semana quedan en {capital:.2f} USDT.")


# ---------------------------------------------------------------------------
# Boletos reales (arreglo 132): funciones puras, sin red ni llaves
# ---------------------------------------------------------------------------

ACCIONES_REALES = ("COMPRAR", "CERRAR")   # nunca MODIFICAR_STOP ni cancelReplace (el conector no los tiene; M0 no mueve el stop)
MOTIVOS_CIERRE = ("SALIDA_M0", "STOP_SIN_LLENAR", "SIN_STOP", "STOP_EJECUTADO")
URGENTES = ("STOP_SIN_LLENAR", "SIN_STOP")


def margen_minimos_pct(reg: Reglamento) -> float:
    return float(reg.get("real.margen_minimos_pct", 5))


def cerca_del_stop_pct(reg: Reglamento) -> float:
    return float(reg.get("real.no_comprar_cerca_del_stop_pct", 2))


def boleto_id_real(dia: str, accion: str, simbolo: str, estrategia: str = "M0") -> str:
    """Como el de papel, con el prefijo RA- (Real, reglas de A): 20261115-RA-COM-BTC-1a2b3c4d."""
    import hashlib
    h = hashlib.sha1(f"{dia}|REAL|{accion}|{simbolo}|{estrategia}".encode()).hexdigest()[:8]
    return f"{dia.replace('-', '')}-RA-{accion[:3]}-{moneda(simbolo)}-{h}"


def id_compra(boleto: str) -> str:
    """newClientOrderId de la compra: bp + 16 hex (corto, sin acentos)."""
    import hashlib
    return "bp" + hashlib.sha1(f"{boleto}|compra".encode()).hexdigest()[:16]


def id_venta(boleto: str) -> str:
    """Arreglo 181: newClientOrderId FIJO de la venta a mercado de un boleto (bv + 16 hex). Antes de reintentar una
    venta, el EJECUTOR busca con spot.getOrder ese id: si ya existe, no se vende dos veces."""
    import hashlib
    return "bv" + hashlib.sha1(f"{boleto}|venta".encode()).hexdigest()[:16]


REINTENTO_VENTA = (
    "Si la venta falla o no sabes si entró, ANTES de reintentar búscala con spot.getOrder (origClientOrderId={id}): si "
    "ya existe y se llenó, NO la repitas (anótala); si no existe, reintenta una vez con el mismo newClientOrderId "
    "(arreglo 181).")


def vence_real(reg: Reglamento, dia: str) -> str:
    """Hora de la ronda del día siguiente a la vela de señal + ronda.max_retraso_min (no las 24 h del papel)."""
    import pandas as pd
    hh, mm = (int(x) for x in str(reg.get("ronda.hora_utc", "00:10")).split(":"))
    t = pd.Timestamp(dia, tz="UTC") + pd.Timedelta(days=1, hours=hh, minutes=mm + float(reg.get("ronda.max_retraso_min", 120)))
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


HUECO_SIN_STOP = (
    "⚠️ HUECO SIN STOP: desde que se llena la compra hasta que el stop queda NEW, la posición NO tiene protección. "
    "Pon el stop EN EL ACTO, sin nada en medio (ni registrar-llenado, ni avisos, ni consultas): el stop ya viene listo "
    "en el boleto, solo eliges cuál según commissionAsset. Binance tiene órdenes OTO (compra y stop en una sola "
    "petición), pero el conector no las tiene: por eso son dos órdenes (arreglo 165).")


def boleto_compra_real(reg: Reglamento, dia: str, simbolo: str, precio_ref: float, stop: float, cantidad: float,
                       f, emitido: datetime, estrategia: str = "M0") -> dict[str, Any]:
    """El boleto de COMPRA real (uno por día; en M0 solo BTCUSDT): compra LIMIT FOK y su STOP_LOSS_LIMIT.

    Arreglo 165: el stop viene LISTO para los dos casos de comisión (en la moneda comprada: `orden_stop`; en BNB u otra
    moneda: `orden_stop_comision_otra_moneda`, por toda la compra, que con FOK se llena completa o nada), para que el
    EJECUTOR lo ponga en el acto, sin calcular ni correr nada entre la compra y el stop."""
    from . import papel as P
    from . import riesgo as R
    from .exchange import redondear_abajo, redondear_arriba
    lim_compra, lim_stop = P.limites_ejecucion(reg)
    tick, paso = f.tick, f.paso
    stop = redondear_abajo(stop, tick)
    precio = redondear_arriba(precio_ref * (1 + lim_compra / 100), tick)
    limite_stop = P._limite_stop(stop, f, lim_stop)
    com = float(reg.costos["comision_spot_pct"]) if reg.get("costos.comision_en_moneda_comprada", True) else 0.0
    cant_stop = R.cantidad_neta(cantidad, com, paso)
    bid = boleto_id_real(dia, "COMPRAR", simbolo, estrategia)
    id_st = P.id_stop(bid, 0)
    riesgo = cantidad * (precio_ref - stop)
    capital = reg.cifra("carteras.capital_inicial")
    mult = f.ask_mult_down or 0.8
    margen = 1 + margen_minimos_pct(reg) / 100
    m = moneda(simbolo)
    n = P.numero_txt
    b = {"boleto_id": bid, "modo": "REAL", "cartera": CARTERA, "reglas_de": "A", "version_reglamento": reg.version,
         "accion": "COMPRAR", "simbolo": simbolo, "estrategia": estrategia, "precio_referencia": precio_ref,
         "emitido_utc": emitido.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "vence_utc": vence_real(reg, dia),
         "orden_compra": {"symbol": simbolo, "side": "BUY", "type": "LIMIT", "timeInForce": "FOK",
                          "quantity": n(cantidad, paso), "price": n(precio, tick), "newClientOrderId": id_compra(bid),
                          "newOrderRespType": "FULL"},
         "orden_stop": {"symbol": simbolo, "side": "SELL", "type": "STOP_LOSS_LIMIT", "timeInForce": "GTC",
                        "quantity": n(cant_stop, paso), "stopPrice": n(stop, tick), "price": n(limite_stop, tick),
                        "newClientOrderId": id_st},
         "orden_stop_comision_otra_moneda": {"symbol": simbolo, "side": "SELL", "type": "STOP_LOSS_LIMIT",
                                             "timeInForce": "GTC", "quantity": n(cantidad, paso), "stopPrice": n(stop, tick),
                                             "price": n(limite_stop, tick), "newClientOrderId": id_st},
         "hueco_sin_stop": HUECO_SIN_STOP,
         "despues_del_stop": REVISION_DESPUES_DEL_STOP,
         "antes_de_comprar": (f"registrar-llenado --real --boleto {bid} --evento COMPRA_ENVIADA (ANTES de mandar la "
                              f"compra; si sale ❌, no la mandes)"),
         "id_stop": id_st, "cantidad": cantidad, "cantidad_stop": cant_stop, "stop": stop, "limite_stop": limite_stop,
         "reglas_para_la_cantidad_del_stop": (
             f"Compra llenada completa (FOK, lo normal): si commissionAsset es {m}, pon orden_stop tal cual "
             f"({n(cant_stop, paso)} {m}); si es BNB u otra moneda, pon orden_stop_comision_otra_moneda tal cual "
             f"({n(cantidad, paso)} {m}). No calcules nada antes de poner el stop. Solo con una compra PARCIAL: "
             f"si commissionAsset es {m}: executedQty − commission; si es BNB u otra moneda: executedQty completo; "
             f"siempre redondeado HACIA ABAJO al paso de {n(paso)} {m}. Nunca más que lo que quedó libre en la cuenta. "
             f"Si la respuesta no trae comisión, usa orden_stop ({n(cant_stop, paso)}, cantidad_stop)."),
         "no_comprar_si": {
             "precio_actual_mayor_que": precio,
             "precio_actual_menor_o_igual_que": round(stop * (1 + cerca_del_stop_pct(reg) / 100), 8),
             "precio_actual_mayor_que_por_percent_price": round(limite_stop / mult, 8),
             "multiplicador_percent_price": mult,
             "valor_menor_que_usdt": round(f.minimo_usdt * margen, 8),
             "texto": [f"el precio actual es mayor que {n(precio, tick)} (el límite de compra)",
                       f"el precio actual es menor o igual a {n(stop * (1 + cerca_del_stop_pct(reg) / 100), tick)} "
                       f"(a {cerca_del_stop_pct(reg):g} % o menos del stop)",
                       f"el precio actual × {mult:g} es mayor que el límite del stop {n(limite_stop, tick)} "
                       f"(Binance rechazaría el stop por PERCENT_PRICE_BY_SIDE)",
                       f"la compra o la venta en el stop valen menos de {f.minimo_usdt * margen:.2f} USDT "
                       f"(el mínimo de Binance con {margen_minimos_pct(reg):g} % de margen)"]},
         "valor_compra_usdt": round(cantidad * precio_ref, 4), "valor_venta_stop_usdt": round(cant_stop * limite_stop, 4),
         "riesgo_usdt": round(riesgo, 6), "riesgo_pct": round(riesgo / capital * 100, 4),
         "stop_pct": round((1 - stop / precio_ref) * 100, 4), "paso_cantidad": paso, "tick_precio": tick,
         "minimo_usdt": f.minimo_usdt, "cantidad_minima": f.cantidad_min, "apalancamiento": 1}
    b["texto"] = (f"[REAL] [{bid}] COMPRAR {n(cantidad, paso)} {simbolo} con orden LIMIT FOK a {n(precio, tick)} "
                  f"(se llena al instante o no se compra hoy; no se reintenta). No compres si: "
                  + "; ".join(b["no_comprar_si"]["texto"]) + ". "
                  f"Si no aplica ninguna, ANTES de mandar la compra registra COMPRA_ENVIADA (registrar-llenado "
                  f"--real); si sale ❌, no la mandes. "
                  f"⚠️ HUECO SIN STOP: en cuanto se llene, EN EL ACTO y sin hacer nada antes (ni registrar-llenado, ni "
                  f"avisos), pon el STOP_LOSS_LIMIT de VENTA que ya viene listo: orden_stop ({n(cant_stop, paso)} {m}) si "
                  f"commissionAsset es {m}, u orden_stop_comision_otra_moneda ({n(cantidad, paso)} {m}) si es BNB u otra "
                  f"moneda; stop {n(stop, tick)}, límite {n(limite_stop, tick)}, newClientOrderId={id_st}. Confirma que "
                  f"quedó NEW y solo DESPUÉS registra COMPRA_LLENADA y STOP_PUESTO (registrar-llenado --real). "
                  f"{REVISION_DESPUES_DEL_STOP} "
                  f"Vence a las {P.hora_cdmx(b['vence_utc'])}. Arriesga {riesgo:.2f} USDT si toca el stop. "
                  f"Esto no es una promesa de ganancia.")
    return b


def boleto_cierre_real(reg: Reglamento, dia: str, p: dict[str, Any], motivo: str, f=None) -> dict[str, Any]:
    """El boleto de CIERRE real: cancelar el stop y vender a MERCADO lo libre (redondeado al paso). No depende de
    la apertura de hoy (en papel, sin precio se pospone; en real no). STOP_EJECUTADO es solo informativo."""
    from . import papel as P
    from .exchange import redondear_abajo
    if motivo not in MOTIVOS_CIERRE:
        raise ValueError(f"motivo de cierre desconocido: {motivo}")
    paso = float(p.get("paso_cantidad") or (f.paso if f else 0.0))
    cant = redondear_abajo(float(p["cantidad_neta"]), paso)
    bid = boleto_id_real(dia, "CERRAR", p["simbolo"], p.get("estrategia", "M0"))
    m = moneda(p["simbolo"])
    b = {"boleto_id": bid, "modo": "REAL", "cartera": CARTERA, "reglas_de": "A", "version_reglamento": reg.version,
         "accion": "CERRAR", "simbolo": p["simbolo"], "estrategia": p.get("estrategia", "M0"), "motivo": motivo,
         "posicion_id": p["id"], "urgente": motivo in URGENTES, "vence_utc": None, "apalancamiento": 1,
         "paso_cantidad": paso}
    if motivo == "STOP_EJECUTADO":
        b["solo_informativo"] = True
        b["texto"] = (f"[REAL] [{bid}] {p['simbolo']}: el stop ya se ejecutó. NO vendas nada: confirma con "
                      f"spot.getOpenOrders que ya no quedan órdenes de {m} ni {m} en la cuenta y registra STOP_EJECUTADO.")
        return b
    b["orden_cancelar"] = {"symbol": p["simbolo"], "origClientOrderId": p["id_stop"], "orderId": p.get("orden_id_stop")}
    b["orden_venta"] = {"symbol": p["simbolo"], "side": "SELL", "type": "MARKET", "quantity": P.numero_txt(cant, paso),
                        "newClientOrderId": id_venta(bid), "newOrderRespType": "FULL"}     # arreglo 181: id fijo
    b["cantidad"] = cant
    urg = "URGENTE: " if b["urgente"] else ""
    por = {"SALIDA_M0": "M0 manda salir (BTC cerró abajo de su media)",
           "STOP_SIN_LLENAR": "el stop se activó y no se llenó",
           "SIN_STOP": "la posición no tiene su stop vivo en Binance"}[motivo]
    b["texto"] = (f"[REAL] [{bid}] {urg}CERRAR {p['simbolo']} ({por}): cancela el stop (newClientOrderId={p['id_stop']}) y en "
                  f"el acto VENDE {P.numero_txt(cant, paso)} {m} a MERCADO (o lo libre, redondeado hacia abajo al paso). "
                  + REINTENTO_VENTA.format(id=id_venta(bid)) +
                  " Si el reintento también falla, vuelve a poner el stop igual y avisa con prioridad."
                  + (" No repongas el stop en vez de vender: si su límite queda abajo de 0.8 × el precio promedio, "
                     "Binance lo rechaza (PERCENT_PRICE_BY_SIDE); se vende." if b["urgente"] else ""))
    return b


# ---------------------------------------------------------------------------
# Venta urgente del BTC que el estado real no tiene anotado (arreglo 172)
# ---------------------------------------------------------------------------

MOTIVO_SIN_ANOTAR = "SIN_ANOTAR"   # un CERRAR sin posición: vende a MERCADO el BTC LIBRE que el estado no conoce


def btc_sin_anotar(reg: Reglamento, est: dict[str, Any], foto: Any, ahora: datetime) -> dict[str, dict[str, Any]]:
    """Arreglo 172: lo que una foto FRESCA (aunque haya salido con ❌) trae en `sin_estado` y el estado real no tiene en
    `posiciones`, solo de las monedas del real (M0: BTC). Lo mismo que `_sin_anotar` marca SIN STOP.
    Regresa {moneda: {"libre", "bloqueado", "compras": [boletos con COMPRA_ENVIADA sin anotar de esa moneda]}}.
    Sin foto fresca regresa {}: no se sabe cuánto hay y nunca se vende a ciegas."""
    try:
        if not isinstance(foto, dict) or not isinstance(foto.get("sin_estado"), dict) \
                or not _foto_fresca(reg, foto, ahora):
            return {}
    except (KeyError, TypeError, ValueError):
        return {}
    en_posicion = {moneda(p["simbolo"]) for p in est["posiciones"]}
    pendientes = compras_sin_anotar(reg)
    activos = foto.get("activos") if isinstance(foto.get("activos"), dict) else {}
    out = {}
    for a in universo_real(reg):
        if a not in foto["sin_estado"] or a in en_posicion:
            continue
        act = activos.get(a) if isinstance(activos.get(a), dict) else {}
        out[a] = {"libre": _num(act.get("libre")) or 0.0, "bloqueado": _num(act.get("bloqueado")) or 0.0,
                  "compras": [str(x.get("boleto_id")) for x in pendientes
                              if _moneda_del_boleto(reg, x.get("boleto_id")) == a]}
    return out


def ventas_urgentes(reg: Reglamento, est: dict[str, Any], foto: Any, ahora: datetime) -> dict[str, dict[str, Any]]:
    """Arreglos 172 y 180: lo que la ronda real manda vender de urgencia: el BTC sin anotar (`btc_sin_anotar`) y el
    BTC de más sobre lo anotado en una posición (`sobrante_en_foto`: solo el sobrante, nunca lo de la posición, y
    nunca más que lo libre)."""
    out = btc_sin_anotar(reg, est, foto, ahora)
    for a, x in sobrante_en_foto(reg, est, foto, ahora).items():
        if a not in out:
            out[a] = {"libre": min(x["libre"], x["sobra"]), "bloqueado": max(0.0, x["sobra"] - x["libre"]),
                      "compras": [], "sobrante": x}
    return out


def boleto_venta_sin_anotar(reg: Reglamento, dia: str, simbolo: str, libre: float, precio_ref: float, f,
                            compras: list[str] | tuple = (), sobrante: dict[str, float] | None = None) -> dict[str, Any]:
    """Arreglo 172: el boleto de VENTA URGENTE del BTC libre que el estado real no conoce. Es un CERRAR como el de una
    posición SIN STOP (mismo flujo del EJECUTOR y misma revisión), pero sin stop que cancelar: vende a MERCADO solo lo
    LIBRE de la foto, redondeado hacia abajo al paso (LOT_SIZE y MARKET_LOT_SIZE). Lo bloqueado en órdenes abiertas
    no se toca (lo revisa Ángelo). El código no manda nada: solo arma el boleto."""
    from . import papel as P
    from .exchange import redondear_abajo
    paso = float(f.paso)
    cant = redondear_abajo(float(libre), paso)
    if float(f.paso_mercado or 0) > 0:
        cant = redondear_abajo(cant, float(f.paso_mercado))
    compras = [str(c) for c in compras if c]
    bid = boleto_id_real(dia, "CERRAR", simbolo, MOTIVO_SIN_ANOTAR)
    m = moneda(simbolo)
    n = P.numero_txt
    b = {"boleto_id": bid, "modo": "REAL", "cartera": CARTERA, "reglas_de": "A", "version_reglamento": reg.version,
         "accion": "CERRAR", "simbolo": simbolo, "estrategia": "M0", "motivo": MOTIVO_SIN_ANOTAR, "urgente": True,
         "sin_anotar": True, "posicion_id": compras[0] if len(compras) == 1 else None, "compras_sin_anotar": compras,
         "vence_utc": None, "apalancamiento": 1, "paso_cantidad": paso, "cantidad": cant, "libre_en_la_foto": libre,
         "precio_referencia": precio_ref, "valor_venta_usdt": round(cant * precio_ref, 4),
         "orden_venta": {"symbol": simbolo, "side": "SELL", "type": "MARKET", "quantity": n(cant, paso),
                         "newClientOrderId": id_venta(bid), "newOrderRespType": "FULL"}}     # arreglo 181: id fijo
    de = f" (compra enviada sin anotar: boleto {', '.join(compras)})" if compras else ""
    if sobrante:          # arreglo 180: solo lo de más sobre la posición anotada
        b["sobrante"] = {k: round(float(sobrante[k]), 8) for k in ("sobra", "hay", "anotado")}
        b["libre_en_la_foto"] = sobrante["libre"]
        que = (f"hay {n(sobrante['hay'], 1e-8)} {m} en Binance y la posición anota {n(sobrante['anotado'], 1e-8)}: "
               f"sobran {n(sobrante['sobra'], 1e-8)} {m} que el estado real no tiene anotados")
    else:
        que = f"hay {n(libre)} {m} libres en Binance que el estado real no tiene anotados{de}"
    b["texto"] = (f"[REAL] [{bid}] URGENTE: VENTA URGENTE de {m} SIN ANOTAR: {que}: no tienen stop. No hay stop que "
                  f"cancelar: en el acto VENDE "
                  f"{n(cant, paso)} {m} a MERCADO (orden_venta tal cual; nunca más de lo libre, redondeado hacia abajo "
                  f"al paso). No toques lo bloqueado en órdenes abiertas (lo revisa Ángelo) y no pongas un stop en vez "
                  f"de vender. {REINTENTO_VENTA.format(id=id_venta(bid))} "
                  f"Si el reintento también falla, avisa a THE BOSS con prioridad "
                  f"máxima: Ángelo debe entrar a Binance y proteger o vender a mano. Después registra VENTA_LLENADA "
                  f"(registrar-llenado --real --boleto {bid}). Las compras siguen bloqueadas hasta que Ángelo las "
                  f"reanude.")
    return b


def _revisar_venta_sin_anotar(reg: Reglamento, b: dict[str, Any], f) -> list[str]:
    """Arreglo 172: la venta urgente solo VENDE, a MERCADO, la moneda del real, en los pasos y arriba del mínimo de
    Binance (LOT_SIZE, MARKET_LOT_SIZE y MIN_NOTIONAL con el precio de referencia). A mercado no lleva precio límite,
    como el cierre SIN_STOP: un precio límite es lo que PERCENT_PRICE_BY_SIDE le rechaza al stop."""
    from .cli_ronda import _multiplo
    errores = []
    if b.get("accion") != "CERRAR":
        errores.append("la venta urgente tiene que ser un CERRAR")
    if "orden_compra" in b or "orden_cancelar" in b:
        errores.append("la venta urgente solo vende: no compra ni cancela nada")
    ov = b.get("orden_venta")
    if not isinstance(ov, dict) or (ov.get("side"), ov.get("type")) != ("SELL", "MARKET"):
        return errores + ["la venta urgente no es una VENTA a MERCADO"]
    if "price" in ov or "stopPrice" in ov:
        errores.append("la venta urgente trae precio: va a MERCADO, sin precio límite (PERCENT_PRICE_BY_SIDE)")
    s = str(ov.get("symbol", ""))
    if s != b.get("simbolo") or not s.endswith("USDT") or moneda(s) not in universo_real(reg):
        errores.append("la venta urgente no es de la moneda del real")
    cant = _num(ov.get("quantity")) or 0.0
    if cant <= 0:
        return errores + ["la cantidad a vender es 0"]
    if f is not None:
        if not _multiplo(ov.get("quantity"), f.paso):
            errores.append("la cantidad no está redondeada al paso de Binance (LOT_SIZE)")
        if cant < f.cantidad_min:
            errores.append("la cantidad no llega a la cantidad mínima de Binance (minQty)")
        if f.paso_mercado > 0 and not _multiplo(ov.get("quantity"), f.paso_mercado):
            errores.append("la cantidad no está redondeada al paso de Binance para órdenes a mercado (MARKET_LOT_SIZE)")
        if f.cantidad_min_mercado > 0 and cant < f.cantidad_min_mercado:
            errores.append("la cantidad no llega al mínimo de Binance para órdenes a mercado (MARKET_LOT_SIZE minQty)")
        if f.cantidad_max_mercado > 0 and cant > f.cantidad_max_mercado:
            errores.append("la cantidad pasa el máximo de Binance para órdenes a mercado (MARKET_LOT_SIZE maxQty)")
        px = _num(b.get("precio_referencia"))
        if px is None or px <= 0:
            errores.append("la venta urgente no trae precio de referencia para revisar el mínimo de Binance")
        elif cant * px < f.minimo_usdt:
            errores.append(f"la venta (unos {cant * px:.2f} USDT) no llega al mínimo de Binance (MIN_NOTIONAL "
                           f"{f.minimo_usdt:g} USDT)")
    return errores


def revisar_boleto_real(reg: Reglamento, b: dict[str, Any], f) -> list[str]:
    """Errores de un boleto real (lista vacía = cumple). Lo que no se reconoce no se aprueba."""
    if not isinstance(b, dict):
        return ["no es un boleto (formato raro): no lo pongas"]
    errores = []
    if b.get("modo") != "REAL":
        errores.append("no es un boleto REAL: no lo pongas")
    if b.get("accion") not in ACCIONES_REALES:
        errores.append(f"acción {b.get('accion')} no permitida en real")
    if b.get("apalancamiento") != 1:
        errores.append("el apalancamiento no es 1")
    if b.get("version_reglamento") != reg.version:
        errores.append(f"reglamento {b.get('version_reglamento')} y el vigente es {reg.version}")
    if b.get("motivo") == MOTIVO_SIN_ANOTAR or b.get("sin_anotar"):     # arreglo 172: la venta urgente
        errores += _revisar_venta_sin_anotar(reg, b, f)
    ov = b.get("orden_venta")
    if b.get("accion") == "CERRAR" and isinstance(ov, dict) and ov.get("newClientOrderId") != id_venta(str(b.get("boleto_id"))):
        errores.append("la venta no trae su newClientOrderId fijo (sin él no se puede revisar con spot.getOrder antes "
                       "de reintentar y se podría vender dos veces)")     # arreglo 181
    if b.get("accion") == "COMPRAR":
        oc, os_ = b.get("orden_compra") or {}, b.get("orden_stop") or {}
        if (oc.get("type"), oc.get("timeInForce"), oc.get("side")) != ("LIMIT", "FOK", "BUY"):
            errores.append("la compra no es LIMIT FOK")
        if (os_.get("type"), os_.get("side")) != ("STOP_LOSS_LIMIT", "SELL"):
            errores.append("el stop no es STOP_LOSS_LIMIT de venta")
        # Arreglo 165: el stop listo para comisión en BNB u otra moneda es el MISMO stop, por toda la compra
        oo = b.get("orden_stop_comision_otra_moneda")
        if not isinstance(oo, dict):
            errores.append("falta orden_stop_comision_otra_moneda (el stop listo para comisión en otra moneda)")
        else:
            if any(oo.get(k) != os_.get(k) for k in ("symbol", "side", "type", "timeInForce", "stopPrice", "price",
                                                    "newClientOrderId")):
                errores.append("orden_stop_comision_otra_moneda no es el mismo stop que orden_stop")
            if oo.get("quantity") != oc.get("quantity"):
                errores.append("orden_stop_comision_otra_moneda no es por toda la compra")
        if f is not None:
            margen = f.minimo_usdt * (1 + margen_minimos_pct(reg) / 100)
            cant, cant_stop = float(oc.get("quantity", 0)), float(os_.get("quantity", 0))
            precio, lim = float(oc.get("price", 0)), float(os_.get("price", 0))
            if cant * precio < margen or cant_stop * lim < margen:
                errores.append(f"la compra o la venta en el stop no llegan a {margen:.2f} USDT (mínimo + margen)")
            if cant < f.cantidad_min or cant_stop < f.cantidad_min:
                errores.append("la cantidad no llega a la cantidad mínima de Binance")
            mult = f.ask_mult_down or 0.8
            if lim < mult * precio:
                errores.append(f"el límite del stop queda abajo de {mult:g} × el precio (PERCENT_PRICE_BY_SIDE)")
            if not (0 < lim <= float(os_.get("stopPrice", 0)) < precio):
                errores.append("el stop no queda entre su límite y el precio de compra")
    return errores


# ---------------------------------------------------------------------------
# Llenados confirmados (arreglo 136): lo ÚNICO que cambia las posiciones y las cerradas de cartera_REAL.json
# ---------------------------------------------------------------------------

ENVIADA = "COMPRA_ENVIADA"   # arreglo 170: el EJECUTOR la anota ANTES de mandar la compra
EVENTOS = (ENVIADA, "COMPRA_LLENADA", "COMPRA_NO_LLENADA", "COMPRA_PARCIAL", "STOP_PUESTO", "STOP_NO_PUESTO",
           "VENTA_LLENADA", "STOP_EJECUTADO", "CIERRE_DE_EMERGENCIA")
COMPRAS = ("COMPRA_LLENADA", "COMPRA_NO_LLENADA", "COMPRA_PARCIAL")
SALIDAS = ("VENTA_LLENADA", "STOP_EJECUTADO", "CIERRE_DE_EMERGENCIA")
AVISOS_EVENTO = {
    "STOP_NO_PUESTO": "❌ COMPRA SIN STOP: VENDE TODO a MERCADO ya y registra CIERRE_DE_EMERGENCIA. Avisa a THE BOSS con "
                      "prioridad máxima. Si la venta falla, Ángelo debe entrar a Binance y proteger o vender a mano.",
    "COMPRA_PARCIAL": "❌ COMPRA PARCIAL: pon de inmediato el stop por lo que sí se compró y avisa a THE BOSS con prioridad. "
                      "Si lo comprado vale menos del mínimo de Binance y no se puede proteger ni vender, es una posición "
                      "SIN STOP: avisa ya.",
    "CIERRE_DE_EMERGENCIA": "❌ COMPRA SIN STOP, VENDIDA A MERCADO. Avisa a THE BOSS con prioridad máxima.",
}


def archivo_llenados(reg: Reglamento) -> Path:
    return ruta_real(reg) / "llenados.jsonl"


def _renglones_llenados(reg: Reglamento) -> tuple[list[dict[str, Any]], list[int]]:
    """(filas que se entienden, números de renglón ilegibles). Un renglón vacío no cuenta como roto."""
    arch = archivo_llenados(reg)
    if not arch.exists():
        return [], []
    out, rotos = [], []
    for i, renglon in enumerate(arch.read_bytes().split(b"\n"), start=1):
        if not renglon.strip():
            continue
        try:
            fila = json.loads(renglon.decode("utf-8", errors="replace"))
        except (ValueError, RecursionError):
            fila = None
        if isinstance(fila, dict):
            out.append(fila)
        else:
            rotos.append(i)
    return out, rotos


def leer_llenados(reg: Reglamento) -> list[dict[str, Any]]:
    """Los renglones de llenados.jsonl que se entienden (los ilegibles los dice `llenados_rotos`)."""
    return _renglones_llenados(reg)[0]


def llenados_rotos(reg: Reglamento) -> list[int]:
    """Arreglo 176: los renglones de llenados.jsonl que no se pueden leer (por ejemplo, uno cortado a la mitad)."""
    return _renglones_llenados(reg)[1]


def aviso_llenados_rotos(rotos: list[int]) -> str:
    """Arreglo 176: el mensaje de falla cerrada con renglones ilegibles en llenados.jsonl."""
    cuales = ", ".join(str(n) for n in rotos[:5]) + (" …" if len(rotos) > 5 else "")
    return (f"llenados.jsonl tiene {len(rotos)} renglón(es) ilegible(s) (renglón {cuales}): puede ser una "
            f"COMPRA_ENVIADA cortada (BTC sin stop que no se ve) → no se compra nada hasta que Ángelo revise y arregle "
            f"datos/real/llenados.jsonl")


def buscar_boleto(reg: Reglamento, boleto_id: str) -> dict[str, Any] | None:
    """El boleto real con ese id, en salida/boletos_real_<día>.json (el día sale del id)."""
    d = str(boleto_id)[:8]
    arch = AR.carpeta_datos(reg).parent / "salida" / f"boletos_real_{d[:4]}-{d[4:6]}-{d[6:8]}.json"
    try:
        boletos = AR.leer_json_seguro(arch) if AR.hay_archivo(arch) else []
    except AR.ArchivoDanado:
        return None
    return next((b for b in boletos if isinstance(b, dict) and b.get("boleto_id") == boleto_id), None) \
        if isinstance(boletos, list) else None


def _por_que_no_comprar(est: dict[str, Any], reg: Reglamento | None = None) -> str:
    """Arreglo 171: por qué el EJECUTOR NO debe mandar una compra real ("" = puede).

    Arreglo 173: con `reg`, lo primero es una compra enviada sin anotar (COMPRA_ENVIADA sin COMPRA_LLENADA,
    COMPRA_PARCIAL ni COMPRA_NO_LLENADA, ni venta urgente que la cubra): no se manda otra compra encima, aunque nadie
    haya corrido conciliar --real (que es quien pone `bloqueo_compras`)."""
    rotos = llenados_rotos(reg) if reg is not None else []
    if rotos:                  # arreglo 176: falla cerrada
        return aviso_llenados_rotos(rotos)
    pendientes = compras_sin_anotar(reg) if reg is not None else []
    if pendientes:
        from . import papel as P
        x = pendientes[0]
        try:
            hora = P.hora_cdmx(x["hora_utc"]) if isinstance(x.get("hora_utc"), str) else "sin hora"
        except (TypeError, ValueError):
            hora = "sin hora"
        mas = f" y {len(pendientes) - 1} más" if len(pendientes) > 1 else ""
        return (f"hay una compra enviada sin anotar (boleto {x.get('boleto_id')}{mas}, COMPRA_ENVIADA, {hora}): anota "
                f"primero cómo terminó (COMPRA_LLENADA, COMPRA_PARCIAL o COMPRA_NO_LLENADA) → no se manda otra compra")
    if est.get("bloqueo_compras"):
        return (f"compras reales bloqueadas por {est['bloqueo_compras'].get('motivo')} → solo Ángelo las reanuda "
                f"(reanudar --cartera REAL)")
    if est.get("detenido"):
        return "la cartera REAL está DETENIDA por caída máxima → solo Ángelo la reanuda"
    rev = est.get(REVISION)
    if rev:
        return (f"falta la revisión después de la compra del boleto "
                f"{rev.get('boleto') if isinstance(rev, dict) else '?'} (foto de saldo nueva y conciliar --real)")
    sin = [moneda(p["simbolo"]) for p in est["posiciones"] if p.get("estado_stop") != "ACTIVO"]
    return f"{', '.join(sin)} no tiene su stop ACTIVO" if sin else ""


def _ya_en_estado(est: dict[str, Any], boleto_id: str, pos_id: Any, evento: str, orden_id: Any) -> bool:
    """Arreglo 175: ¿el estado real ya refleja este llenado? (para no agregarlo dos veces si se reintenta)."""
    mismo = (lambda x: orden_id is not None and x is not None and str(x) == str(orden_id))
    pos = next((p for p in est["posiciones"] if p["id"] == pos_id), None)
    cerrada = next((c for c in est["cerradas"] if c.get("id") == pos_id), None)
    if evento in ("COMPRA_LLENADA", "COMPRA_PARCIAL"):
        return any(p["id"] == boleto_id or mismo(p.get("orden_id_compra")) for p in est["posiciones"]) \
            or any(c.get("id") == boleto_id for c in est["cerradas"])
    if evento == "STOP_PUESTO":
        return cerrada is not None or (pos is not None and pos.get("estado_stop") == "ACTIVO"
                                       and (orden_id is None or mismo(pos.get("orden_id_stop"))))
    if evento == "STOP_NO_PUESTO":
        return cerrada is not None or (pos is not None and pos.get("estado_stop") == "SIN_STOP")
    if evento in SALIDAS:
        return any(c.get("boleto_cierre") == boleto_id and str(c.get("motivo", "")).startswith(evento)
                   for c in est["cerradas"]) \
            or any(v.get("boleto") == boleto_id for v in est.get("ventas_sin_anotar", []) if isinstance(v, dict))
    return True     # COMPRA_ENVIADA y COMPRA_NO_LLENADA no cambian el estado


def _solo_falta_renglon(est: dict[str, Any], boleto_id: str, pos_id: Any, evento: str, orden_id: Any,
                        hechos: set) -> bool:
    """Arreglo 175: el estado ya tiene este llenado y llenados.jsonl no (antes del 175 el estado se guardaba primero):
    la compra con ese boleto o id de orden, el stop ACTIVO con ese id de orden, o la salida de ese boleto."""
    if evento in ("COMPRA_LLENADA", "COMPRA_PARCIAL"):
        return not hechos & set(COMPRAS) and _ya_en_estado(est, boleto_id, pos_id, evento, orden_id)
    if evento == "STOP_PUESTO":
        return orden_id is not None and _ya_en_estado(est, boleto_id, pos_id, evento, orden_id) \
            and any(p["id"] == pos_id for p in est["posiciones"])
    return evento in SALIDAS and _ya_en_estado(est, boleto_id, pos_id, evento, orden_id)


def _anexar_llenado(reg: Reglamento, fila: dict[str, Any]) -> None:
    """Arreglo 175: agrega el renglón a llenados.jsonl y lo baja a disco (flush + fsync) antes de tocar el estado."""
    import os
    arch = archivo_llenados(reg)
    arch.parent.mkdir(parents=True, exist_ok=True)
    falta_salto = False         # arreglo 176: si el último renglón quedó cortado, el nuevo va en su propio renglón
    if arch.exists() and arch.stat().st_size > 0:
        with open(arch, "rb") as fb:
            fb.seek(-1, os.SEEK_END)
            falta_salto = fb.read(1) != b"\n"
    with open(arch, "a", encoding="utf-8") as fh:
        if falta_salto:
            fh.write("\n")
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _aplicar_llenado(reg: Reglamento, est: dict[str, Any], b: dict[str, Any], boleto_id: str, evento: str,
                     f: dict[str, Any], pos: dict[str, Any] | None, venta_urgente: bool,
                     ahora: datetime) -> list[str]:
    """Arreglo 175: el cambio al estado real de un llenado ya revisado (`f` es su renglón de llenados.jsonl). Solo
    cambia `est` (lo guarda quien llama) y regresa los mensajes."""
    from . import riesgo as R
    from .exchange import redondear_abajo
    orden_id, cantidad, precio = f.get("orden_id"), f.get("cantidad"), f.get("precio")
    comision, moneda_comision = f.get("comision"), f.get("moneda_comision")
    stop_id, motivo = f.get("stop_id"), f.get("motivo") or ""
    mensajes = [AVISOS_EVENTO[evento]] if evento in AVISOS_EVENTO else []
    if evento == ENVIADA:
        mensajes.append(f"👍 Compra ENVIADA anotada ({boleto_id}). Ahora sí manda la compra: orden_compra del boleto, "
                        f"tal cual. Si se llena, pon el stop EN EL ACTO; si no se llena, registra COMPRA_NO_LLENADA.")
        mensajes.append("⚠️ Hasta que anotes cómo terminó (COMPRA_LLENADA, COMPRA_PARCIAL o COMPRA_NO_LLENADA), "
                        "conciliar --real cuenta esta compra SIN STOP y bloquea las compras.")
    elif evento in ("COMPRA_LLENADA", "COMPRA_PARCIAL"):
        m = moneda(b["simbolo"])
        neta = cantidad - comision if moneda_comision.upper() == m else cantidad
        neta = redondear_abajo(neta, float(b["paso_cantidad"]))
        est["posiciones"].append({
            "id": boleto_id, "simbolo": b["simbolo"], "estrategia": b["estrategia"], "cantidad_comprada": cantidad,
            "cantidad_neta": neta, "precio_llenado": precio, "comision": comision,
            "moneda_comision": moneda_comision.upper(), "stop": b["stop"], "limite_stop": b["limite_stop"],
            "id_stop": b["id_stop"], "orden_id_stop": None, "estado_stop": "SIN_STOP",   # ACTIVO solo con STOP_PUESTO
            "t_entrada": ahora.isoformat(timespec="seconds"), "paso_cantidad": b["paso_cantidad"],
            "orden_id_compra": orden_id,
            "costo_usdt": cantidad * precio + (comision if moneda_comision.upper() == "USDT" else 0.0)})
        mensajes.append(f"👍 Compra anotada: {neta:g} {m} netos a {precio:g}. Si ya pusiste el stop, registra "
                        f"STOP_PUESTO ya; si todavía no, ponlo YA (orden_stop del boleto, u orden_stop_comision_otra_moneda "
                        f"si la comisión no fue en {m}).")
        mensajes.append("⚠️ Mientras no registres STOP_PUESTO, el estado real cuenta esta posición SIN STOP: la siguiente "
                        "ronda real la manda vender a mercado (URGENTE) y bloquea las compras.")
    elif evento == "STOP_PUESTO":
        pos.update(orden_id_stop=orden_id, id_stop=stop_id, estado_stop="ACTIVO")
        est[REVISION] = {"boleto": boleto_id, "desde": ahora.isoformat(timespec="seconds")}     # arreglo 171
        mensajes.append(f"👍 Stop anotado como ACTIVO ({stop_id}).")
        mensajes.append("👉 AHORA MISMO, sin esperar a la ronda de mañana: foto de saldo nueva (spot.getAccount y "
                        "spot.getOpenOrders → registrar-saldo) y conciliar --real. Si sale ❌ o SIN STOP, avisa a THE "
                        "BOSS con prioridad: no se compra nada más (arreglo 171).")
    elif evento == "STOP_NO_PUESTO":
        pos["estado_stop"] = "SIN_STOP"
    elif venta_urgente:      # arreglo 172: no hay posición ni costo conocido; no toca cerradas, capital ni el bloqueo
        com = float(comision or 0.0)
        neto = cantidad * precio - (com if str(moneda_comision or "USDT").upper() == "USDT" else 0.0)
        m = moneda(b["simbolo"])
        est.setdefault("ventas_sin_anotar", []).append({
            "fecha": ahora.isoformat(timespec="seconds"), "boleto": boleto_id, "simbolo": b["simbolo"],
            "cantidad": cantidad, "precio": precio, "comision": com, "moneda_comision": moneda_comision,
            "usdt_neto": round(neto, 8), "cubre": list(b.get("compras_sin_anotar") or [])})
        mensajes.append(f"👍 Venta urgente anotada: {cantidad:g} {m} a {precio:g} (unos {neto:.2f} USDT netos).")
        mensajes.append(f"⚠️ Ese {m} no estaba en el estado real: no entra en las cerradas ni en las cuentas del riesgo. "
                        f"conciliar --real va a mostrar la diferencia en USDT y solo Ángelo la resuelve "
                        f"(ajustar-capital-real); las compras siguen bloqueadas hasta que él diga reanudar --cartera REAL.")
    elif evento in SALIDAS:
        com = float(comision or 0.0)
        neto = cantidad * precio - (com if str(moneda_comision or "USDT").upper() == "USDT" else 0.0)
        ganancia = neto - costo_usdt(pos)
        riesgo_r = float(pos["cantidad_comprada"]) * (float(pos["precio_llenado"]) - float(pos["stop"]))
        est["posiciones"] = [p for p in est["posiciones"] if p is not pos]
        est["cerradas"].append({"id": pos["id"], "simbolo": pos["simbolo"], "estrategia": pos["estrategia"],
                                "cantidad": cantidad, "entrada": pos["precio_llenado"], "salida": precio,
                                "t_entrada": pos["t_entrada"], "t_salida": ahora.isoformat(timespec="seconds"),
                                "motivo": evento if not motivo else f"{evento}: {motivo}", "ganancia_usdt": ganancia,
                                "r": ganancia / riesgo_r if riesgo_r > 0 else None, "comision_venta": com,
                                "boleto_cierre": boleto_id})
        er = R.EstadoCartera(capital=1.0, pico=1.0, capital_inicio_dia=1.0, capital_inicio_semana=1.0,
                             rachas=dict(est.get("rachas", {})), saltar_rondas=dict(est.get("saltar_rondas", {})))
        R.registrar_resultado(reg.para_cartera("A"), er, pos["estrategia"], ganancia, ahora)
        est["rachas"], est["saltar_rondas"] = er.rachas, er.saltar_rondas
        mensajes.append(f"👍 Salida anotada: {cantidad:g} {moneda(pos['simbolo'])} a {precio:g}; resultado {ganancia:+.4f} USDT.")
    else:
        mensajes.append("👍 Anotado: la compra no se llenó; no hay posición (no se reintenta).")
    return mensajes


def registrar_llenado(reg: Reglamento, boleto_id: str, evento: str, orden_id: Any = None, cantidad: float | None = None,
                      precio: float | None = None, comision: float | None = None, moneda_comision: str | None = None,
                      stop_id: str | None = None, motivo: str = "",
                      ahora: datetime | None = None) -> tuple[bool, list[str]]:
    """Anota lo que contestó Binance (lo corre EJECUTOR). Es lo único que da de alta o de baja posiciones reales.
    Regresa (ok, mensajes); los avisos urgentes van primero.

    Arreglo 175: idempotente. El renglón de llenados.jsonl se anota primero (con fsync) y el estado después; si ese
    evento (o ese id de orden) ya está anotado, no se agrega nada: solo se completa lo que haya faltado."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if evento not in EVENTOS:
        return False, [f"evento desconocido {evento}: usa {', '.join(EVENTOS)}"]
    b = buscar_boleto(reg, boleto_id)
    if b is None or b.get("modo") != "REAL":
        return False, [f"no existe el boleto real {boleto_id}"]
    todos = leer_llenados(reg)
    previos = [x for x in todos if x.get("boleto_id") == boleto_id]
    hechos = {x.get("evento") for x in previos}
    est = cargar_estado(reg, ahora.strftime("%Y-%m-%d"))
    pos_id = b.get("posicion_id", boleto_id)
    pos = next((p for p in est["posiciones"] if p["id"] == pos_id), None)
    venta_urgente = b.get("motivo") == MOTIVO_SIN_ANOTAR and pos is None     # arreglo 172: BTC que no estaba anotado
    # Arreglo 175: registrar un llenado es idempotente. Primero se anota el renglón y después el estado: si el EJECUTOR
    # se cayó entre los dos pasos y reintenta, se completa lo que falta, sin agregar nada dos veces.
    if evento in hechos:
        fila_prev = [x for x in previos if x.get("evento") == evento][-1]
        if _ya_en_estado(est, boleto_id, pos_id, evento, fila_prev.get("orden_id")):
            return False, [f"{evento} del boleto {boleto_id} ya está registrado: no se registra dos veces"]
        if evento in ("STOP_PUESTO", "STOP_NO_PUESTO") and pos is None:
            return False, [f"{evento} del boleto {boleto_id} ya está en llenados.jsonl, pero el estado real no tiene la "
                           f"compra: reintenta primero COMPRA_LLENADA (o COMPRA_PARCIAL) con los mismos datos"]
        try:
            hora_prev = datetime.fromisoformat(str(fila_prev.get("hora_utc"))).astimezone(timezone.utc)
        except (TypeError, ValueError):
            hora_prev = ahora
        mensajes = _aplicar_llenado(reg, est, b, boleto_id, evento, fila_prev, pos, venta_urgente, hora_prev)
        guardar_estado(reg, est)
        return True, [f"⚠️ {evento} del boleto {boleto_id} ya estaba en llenados.jsonl, pero el estado real no lo tenía "
                      f"(se cortó entre los dos pasos): completé el estado con lo que ya estaba anotado, sin agregar "
                      f"otro renglón (arreglo 175)."] + mensajes
    orden_repetida = orden_id is not None and any(
        x.get("evento") == evento and x.get("orden_id") is not None and str(x.get("orden_id")) == str(orden_id)
        for x in todos)
    if orden_repetida:
        return False, [f"la orden {orden_id} ya está anotada como {evento} en llenados.jsonl: no agrego nada "
                       f"(arreglo 175)"]
    fila = {"hora_utc": ahora.isoformat(timespec="seconds"), "boleto_id": boleto_id, "evento": evento,
            "orden_id": orden_id, "cantidad": cantidad, "precio": precio, "comision": comision,
            "moneda_comision": moneda_comision, "stop_id": stop_id, "motivo": motivo}
    if venta_urgente:        # arreglo 172: las compras enviadas sin anotar que esta venta deja cerradas
        fila["cubre"] = list(b.get("compras_sin_anotar") or [])
    if _solo_falta_renglon(est, boleto_id, pos_id, evento, orden_id, hechos):
        # Arreglo 175: el estado ya lo tiene (antes se guardaba el estado primero y el renglón después): solo falta
        # el renglón; no se agrega otra posición ni otra salida
        _anexar_llenado(reg, fila)
        return True, [f"⚠️ {evento} del boleto {boleto_id} ya estaba en el estado real y faltaba en llenados.jsonl: anoté "
                      f"solo el renglón; no agregué nada al estado (arreglo 175)."]
    errores = []
    if evento == ENVIADA:
        if b["accion"] != "COMPRAR":
            errores.append("ese boleto no es de compra")
        elif hechos & set(COMPRAS):
            errores.append("la compra de ese boleto ya está registrada: COMPRA_ENVIADA va ANTES de mandarla "
                           "(fuera de orden)")
        elif por_que := _por_que_no_comprar(est, reg):     # arreglos 171 y 173: no se compra nada más
            errores.append(f"NO mandes la compra: {por_que}. Avisa a THE BOSS con este mensaje.")
    elif evento in COMPRAS:
        if b["accion"] != "COMPRAR":
            errores.append("ese boleto no es de compra")
        elif hechos & set(COMPRAS):
            errores.append("la compra de ese boleto ya está registrada")
        elif evento != "COMPRA_NO_LLENADA":
            if None in (cantidad, precio, comision) or not moneda_comision:
                errores.append("faltan --cantidad, --precio, --comision o --moneda-comision")
            elif cantidad <= 0 or cantidad > float(b["cantidad"]) + 1e-12:
                errores.append(f"la cantidad {cantidad:g} es mayor que la del boleto ({b['cantidad']:g}) o no es válida")
            elif precio > float(b["orden_compra"]["price"]) + 1e-9:
                errores.append(f"el precio {precio:g} es mayor que el límite de compra ({b['orden_compra']['price']})")
    elif evento in ("STOP_PUESTO", "STOP_NO_PUESTO"):
        if not hechos & {"COMPRA_LLENADA", "COMPRA_PARCIAL"} or pos is None:
            errores.append(f"{evento} sin una compra llenada antes (fuera de orden)")
        elif evento == "STOP_PUESTO" and (orden_id is None or not stop_id):
            errores.append("faltan --orden-id y --stop-id del stop")
    else:  # salidas
        if venta_urgente:
            if evento != "VENTA_LLENADA":
                errores.append("con una venta urgente (BTC sin anotar) solo se anota VENTA_LLENADA")
            elif None in (cantidad, precio):
                errores.append("faltan --cantidad y --precio")
            elif cantidad <= 0 or cantidad > float(b["cantidad"]) + 1e-12:
                errores.append(f"la cantidad {cantidad:g} es mayor que la de la venta urgente ({float(b['cantidad']):g}) "
                               f"o no es válida")
        elif pos is None:
            errores.append(f"{evento} de una posición que el estado real no tiene (fuera de orden)")
        elif None in (cantidad, precio):
            errores.append("faltan --cantidad y --precio")
        elif cantidad <= 0 or cantidad > float(pos["cantidad_neta"]) + 1e-12:
            errores.append(f"la cantidad {cantidad:g} es mayor que la de la posición ({pos['cantidad_neta']:g})")
    if errores:
        return False, errores
    mensajes = _aplicar_llenado(reg, est, b, boleto_id, evento, fila, pos, venta_urgente, ahora)
    if evento in COMPRAS and ENVIADA not in hechos:    # arreglo 170: se anota igual (ya pasó en Binance), con aviso
        mensajes.append("⚠️ No se anotó COMPRA_ENVIADA antes de mandar esta compra: la próxima vez anótala ANTES de "
                        "mandarla (arreglo 170). Si te caes entre la compra y el registro, así se sabe que pudo quedar "
                        "BTC sin stop.")
    _anexar_llenado(reg, fila)          # arreglo 175: primero el renglón (con fsync) y después el estado
    guardar_estado(reg, est)
    return True, mensajes


def reanudar(reg: Reglamento, ok_angelo: str, bot: str = "THE BOSS", ahora: datetime | None = None) -> tuple[bool, str]:
    """Arreglo 137: Ángelo levanta el freno total o el bloqueo de compras de la cartera REAL (texto obligatorio)."""
    if not ok_angelo or not ok_angelo.strip():
        return False, "Falta el OK de Ángelo (--ok-angelo \"…\"). Sin eso no se reanuda."
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    est = cargar_estado(reg, ahora.strftime("%Y-%m-%d"))
    if not est.get("detenido") and not est.get("bloqueo_compras"):
        return True, "La cartera REAL no estaba detenida ni bloqueada. No cambié nada."
    sin_stop = [p["simbolo"] for p in est["posiciones"] if p["estado_stop"] != "ACTIVO"]
    est.setdefault("reanudaciones", []).append({"fecha": ahora.isoformat(timespec="seconds"), "texto": ok_angelo.strip(),
                                               "bloqueo": est.get("bloqueo_compras"), "detenido": est.get("detenido"),
                                               "por": bot})
    if est.get("detenido"):                           # como en papel: el pico vuelve al último capital medido
        est["pico"] = float(est["capital_inicio_dia"])
    est["detenido"] = False
    est["bloqueo_compras"] = None
    guardar_estado(reg, est)
    aviso =f" OJO: sigue sin stop activo {', '.join(sin_stop)}; la ronda lo cierra." if sin_stop else ""
    return True, f"Cartera REAL reanudada con el OK de Ángelo.{aviso}"


def estado_ok(reg: Reglamento) -> tuple[bool, str]:
    """(True, "") si el estado real se lee bien; si no, (False, el mensaje con qué hacer)."""
    try:
        cargar_estado(reg)
    except EstadoRealDanado as e:
        return False, str(e)
    return True, ""
