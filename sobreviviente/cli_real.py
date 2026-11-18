"""Comandos del dinero REAL (arreglos 130 a 139). El programa nunca tiene llaves ni firma órdenes: EJECUTOR pone las
órdenes por el conector de Binance y guarda lo que contestó Binance; estos comandos solo leen esos archivos.

  registrar-saldo --cuenta <archivo> --ordenes <archivo>   foto de saldo (spot.getAccount y spot.getOpenOrders)
"""
from __future__ import annotations

from . import archivos as AR
from . import real as RE


def _anotar(reg, bot: str, tarea: str, ok: bool, detalle: str = "") -> None:
    """Arreglo 139: las tareas del real van a datos/bots/registro.jsonl «sin medir» (no tienen horario)."""
    AR.registrar_tarea(reg, bot, tarea, ok, detalle[:160], medir=False)


def _reg(args):
    from .__main__ import _reg as cargar
    return cargar(args)


def precio_publico(reg):
    """Último precio público de Binance (/api/v3/ticker/price, sin llaves). None si falla."""
    from . import datos as D
    cli = D.ClienteBinance(reg)

    def precio(simbolo: str) -> float | None:
        try:
            x = float(cli.spot("/api/v3/ticker/price", {"symbol": simbolo})["price"])
        except Exception:  # noqa: BLE001 - sin precio, la revisión dice ❌ (falla cerrada)
            return None
        return x if x > 0 else None
    return precio


ESPERA_CANDADO_S = 120.0     # arreglo 177: cuánto espera un comando real a que otro suelte datos/real/ronda.lock


def con_candado(reg, bot: str, tarea: str, fn, espera_s: float | None = None) -> int:
    """Arreglo 177: registrar-llenado --real, conciliar --real y registrar-saldo toman el MISMO candado que la ronda
    real (datos/real/ronda.lock): si otro proceso lo tiene, este espera; si no lo suelta a tiempo, sale con aviso sin
    hacer nada."""
    from . import cli_ronda as CR
    espera = float(reg.get("real.espera_candado_s", ESPERA_CANDADO_S)) if espera_s is None else espera_s
    try:
        with CR.candado_ronda(reg, espera_s=espera, carpeta=RE.ruta_real(reg)):
            return fn()
    except CR.RondaOcupada:
        print(f"❌ Otra tarea del dinero real (la ronda real, registrar-llenado --real, conciliar --real o "
              f"registrar-saldo) tiene el candado datos/real/ronda.lock y no lo soltó en {espera:.0f} s: no hice nada. "
              f"Vuelve a correr {tarea} en un momento; si sigue igual, avisa a THE BOSS.")
        _anotar(reg, bot, tarea, False, "candado ocupado (datos/real/ronda.lock): no se hizo nada")
        return 1


def cmd_registrar_saldo(args) -> int:
    reg = _reg(args)
    return con_candado(reg, "EJECUTOR", "registrar-saldo", lambda: _registrar_saldo(reg, args))


def _registrar_saldo(reg, args) -> int:
    ok, mensajes = RE.registrar_saldo(reg, args.cuenta, args.ordenes, precio_publico(reg))
    for m in mensajes:
        print(m if m.startswith("ℹ️") else f"❌ {m}")
    print("👍 Foto de saldo guardada (datos/real/saldo_binance.json)." if ok else
          "❌ La foto de saldo NO sirve: hoy no hay compras reales. Avisa a THE BOSS con este mensaje completo.")
    _anotar(reg, "EJECUTOR", "registrar-saldo", ok, "" if ok else "; ".join(m for m in mensajes if not m.startswith("ℹ️")))
    return 0 if ok else 1


def conciliar_real(reg) -> int:
    """`conciliar --real` (arreglo 131): la foto de saldo contra cartera_REAL.json (con el candado del real, 177)."""
    return con_candado(reg, "CONTADOR", "conciliar --real", lambda: _conciliar_real(reg))


def _conciliar_real(reg) -> int:
    res = RE.conciliar(reg)
    for a in res.get("avisos", []):                     # arreglo 170: el aviso para THE BOSS va antes que todo
        print(a)
    sin_stop = [t for ok, t in res["lineas"] if t.startswith("SIN STOP")]
    for t in sin_stop:                                  # lo más urgente va primero
        print(f"❌ {t}")
    for ok, t in res["lineas"]:
        if t not in sin_stop:
            print(("✅ " if ok else "❌ ") + t)
    print("👍 Las cuentas reales cuadran." if res["ok"] else
          "❌ Lo real NO cuadra: sin compras reales nuevas hasta revisar. Avisa a THE BOSS de inmediato, con prioridad.")
    _anotar(reg, "CONTADOR", "conciliar --real", res["ok"], "; ".join(t for ok, t in res["lineas"] if not ok))
    return 0 if res["ok"] else 1


def verificar_real(reg, fecha: str | None = None, ahora=None, cliente=None) -> int:
    """`ronda --verificar --real` (arreglo 136): revisa SOLO salida/boletos_real_<día>.json."""
    codigo = _verificar_real(reg, fecha, ahora, cliente)
    _anotar(reg, "EJECUTOR", "ronda --verificar --real", codigo == 0, "" if codigo == 0 else "con ❌: no se pone nada")
    return codigo


def _verificar_real(reg, fecha: str | None = None, ahora=None, cliente=None) -> int:
    from datetime import datetime, timezone

    from . import archivos as AR
    from . import cli_ronda as CR
    from . import datos as D
    from . import ronda_real as RR
    from .exchange import filtros_desde_exchangeinfo
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fecha = fecha or CR.fecha_ronda(ahora)
    arch = RR.archivo_boletos(reg, fecha)
    if not AR.hay_archivo(arch):
        print(f"❌ NO HAY RONDA REAL de {fecha}: no pongas nada y avisa a THE BOSS")
        return 1
    try:
        boletos = AR.leer_json_seguro(arch)
    except AR.ArchivoDanado as e:
        print(f"❌ {e} No pongas nada y avisa a THE BOSS.")
        return 1
    if not isinstance(boletos, list):
        print(f"❌ El archivo {arch.name} no trae una lista de boletos: no pongas nada y avisa a THE BOSS")
        return 1
    if not boletos:
        print(f"👍 La ronda real del {fecha} sí corrió: sin boletos reales hoy.")
        return 0
    cli = cliente or D.ClienteBinance(reg)
    try:
        por = {x["symbol"]: x for x in cli.exchange_info("SPOT", forzar=True)["symbols"]}
    except Exception as e:  # noqa: BLE001 - sin reglas de Binance no se aprueba nada
        print(f"❌ No pude leer las reglas de Binance ({type(e).__name__}): no pongas nada")
        return 1
    registrados = {x.get("boleto_id") for x in RE.leer_llenados(reg)}
    problemas = 0
    for i, b in enumerate(boletos):
        nombre = str(b.get("boleto_id") or f"boleto #{i + 1}") if isinstance(b, dict) else f"boleto #{i + 1} (ilegible)"
        try:
            errores = _revisar_real(reg, cli, b, por, ahora, registrados, filtros_desde_exchangeinfo)
        except Exception as e:  # noqa: BLE001 - un boleto mal formado nunca se aprueba
            errores = [f"boleto mal formado ({type(e).__name__}): no lo pongas"]
        print(("✅ " if not errores else "❌ ") + nombre + ("" if not errores else ": " + "; ".join(errores)))
        problemas += bool(errores)
    print("👍 Todos los boletos reales cumplen." if problemas == 0 else
          f"❌ {problemas} boleto(s) real(es) NO se ponen. Avisa a THE BOSS.")
    return 0 if problemas == 0 else 1


def _revisar_real(reg, cli, b, por, ahora, registrados, filtros_desde) -> list[str]:
    from datetime import datetime

    from . import cli_ronda as CR
    if not isinstance(b, dict):
        return ["no es un boleto (formato raro): no lo pongas"]
    if b.get("boleto_id") in registrados:
        return ["YA REGISTRADO: no lo pongas otra vez"]
    f = filtros_desde(por[b["simbolo"]]) if b.get("simbolo") in por else None
    errores = RE.revisar_boleto_real(reg, b, f)
    if b.get("solo_informativo"):
        return errores
    if f is None:
        errores.append("Binance ya no lista esta moneda")
    elif f.estado != "TRADING":
        errores.append(f"Binance tiene esta moneda en estado {f.estado} (no TRADING)")
    if b.get("vence_utc") and ahora > datetime.fromisoformat(str(b["vence_utc"]).replace("Z", "+00:00")):
        errores.append("boleto vencido: no lo pongas")
    if b.get("accion") == "CERRAR" and f is not None:
        venta = {"simbolo": b["simbolo"], "cantidad": b.get("orden_venta", {}).get("quantity")}
        errores += CR._revisar_venta(cli, venta, f)
    return errores


def registrar_llenado_real(reg, args) -> int:
    """`registrar-llenado --real` (arreglo 136): lo corre EJECUTOR con lo que contestó Binance (con el candado del
    real, 177)."""
    return con_candado(reg, args.bot, "registrar-llenado --real", lambda: _registrar_llenado_real(reg, args))


def _registrar_llenado_real(reg, args) -> int:
    try:
        ok, mensajes = RE.registrar_llenado(reg, args.boleto, args.evento or "", args.orden_id, args.cantidad,
                                            args.precio, args.comision, args.moneda_comision, args.stop_id,
                                            args.motivo or "")
    except RE.EstadoRealDanado as e:
        ok, mensajes = False, [str(e)]
    for m in mensajes:
        print(m if ok else f"❌ {m}")
    _anotar(reg, args.bot, "registrar-llenado --real", ok,
            f"{args.boleto} {args.evento or ''}" + ("" if ok else ": " + "; ".join(mensajes)))
    return 0 if ok else 1


def cmd_ajustar_capital_real(args) -> int:
    reg = _reg(args)
    try:
        ok, msg = RE.ajustar_capital(reg, args.usdt, args.ok_angelo)
    except RE.EstadoRealDanado as e:
        ok, msg = False, str(e)
    print(("👍 " if ok else "❌ ") + msg)
    _anotar(reg, "THE BOSS", "ajustar-capital-real", ok, msg)
    return 0 if ok else 2


def registrar(sub) -> None:
    aj = sub.add_parser("ajustar-capital-real", help="REAL, solo Ángelo: registra un depósito, retiro o comisión rara")
    aj.add_argument("--usdt", type=float, required=True, help="USDT total que hay ahora en la cuenta (libre + bloqueado)")
    aj.add_argument("--ok-angelo", dest="ok_angelo", default="", help="texto del OK de Ángelo, tal cual")
    aj.set_defaults(f=cmd_ajustar_capital_real)
    rs = sub.add_parser("registrar-saldo", help="REAL: guarda la foto de saldo que dejó EJECUTOR (getAccount y getOpenOrders)")
    rs.add_argument("--cuenta", required=True, help="respuesta tal cual de spot.getAccount")
    rs.add_argument("--ordenes", required=True, help="respuesta tal cual de spot.getOpenOrders (sin símbolo)")
    rs.set_defaults(f=cmd_registrar_saldo)
