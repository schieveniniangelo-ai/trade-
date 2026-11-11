"""Comandos de operación diaria (Fase 5 de la especificación, versión v2 en PAPEL).

  ronda --modo papel          la ronda del día (00:10 UTC = 6:10 p. m. CDMX)
  ronda --verificar           revisa los boletos del día contra el reglamento (antes "Guardián")
  registrar-llenado --ensayo  el Ejecutor confirma que copiaría el boleto tal cual (en papel no hay órdenes)
  conciliar                   revisa que las cuentas de papel cuadren
  reporte diario|semanal      textos cortos para Ángelo
  estado [--bots]             cómo van las carteras / calificación de cada bot
  estela --foto               ESTELA: guarda la foto diaria del posicionamiento de los top traders
  respaldo                    copia de seguridad (.tar.gz) del estado de papel, boletos y archivos de bots
  doctor                      revisa que la computadora de Grok Bot tenga todo lo necesario
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _reg(args):
    from .__main__ import _reg as cargar
    return cargar(args)


def _memes() -> list[str]:
    return json.loads((RAIZ / "datos" / "memes.json").read_text(encoding="utf-8"))["memes"]


# Valores por defecto SOLO si faltan en el reglamento (ronda.minuto_minimo_utc y ronda.max_retraso_min).
MINUTO_MINIMO_UTC = 5        # antes de las 00:05 UTC la vela diaria puede no estar completa en Binance
MAX_RETRASO_MIN = 120        # más de 2 horas tarde = FUERA DE HORA (la apertura con la que se llenaría ya es vieja)


def revisar_hora(reg, ahora: datetime) -> dict:
    """Compara la hora real con `ronda.hora_utc` del reglamento.

    TEMPRANO: antes del minuto `ronda.minuto_minimo_utc` (5) del día UTC → no se corre. FUERA_DE_HORA: más de
    `ronda.max_retraso_min` (120) minutos después de la hora de la ronda → corre, pero sin boletos de compra. OK: lo demás."""
    hh, mm = (int(x) for x in str(reg.get("ronda.hora_utc", "00:10")).split(":"))
    minimo = float(reg.get("ronda.minuto_minimo_utc", MINUTO_MINIMO_UTC))
    max_retraso = float(reg.get("ronda.max_retraso_min", MAX_RETRASO_MIN))
    u = ahora.astimezone(timezone.utc)
    minutos = u.hour * 60 + u.minute + u.second / 60
    retraso = minutos - (hh * 60 + mm)
    if minutos < minimo:
        estado = "TEMPRANO"
    elif retraso > max_retraso:
        estado = "FUERA_DE_HORA"
    else:
        estado = "OK"
    return {"estado": estado, "retraso_min": round(retraso, 1), "hora_real_utc": u.isoformat(timespec="seconds"),
            "hora_programada_utc": f"{hh:02d}:{mm:02d}", "max_retraso_min": max_retraso, "minuto_minimo_utc": minimo}


def _guardar_bitacora(reg, fila: dict) -> None:
    from . import papel as P
    arch = P.ruta_papel(reg) / "bitacora_rondas.jsonl"
    arch.parent.mkdir(parents=True, exist_ok=True)
    # Si el último renglón quedó cortado (sin salto de línea), primero se cierra: la fila nueva va en su propio renglón
    falta_salto = False
    if arch.exists() and arch.stat().st_size > 0:
        with open(arch, "rb") as f:
            f.seek(-1, os.SEEK_END)
            falta_salto = f.read(1) != b"\n"
    with open(arch, "a", encoding="utf-8") as f:
        if falta_salto:
            f.write("\n")
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


class RondaOcupada(Exception):
    """Otra ronda tiene el candado y no lo soltó a tiempo."""


def _bloquear(f) -> None:
    if os.name == "nt":  # Windows: equivalente de flock
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:                # Linux / Mac (la computadora de Grok Bot)
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _desbloquear(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def candado_ronda(reg, espera_s: float = 600.0, cada_s: float = 0.2):
    """Candado de archivo (datos/papel/ronda.lock) mientras se bajan datos y se corre la ronda:
    si dos procesos arrancan a la vez, el segundo espera a que el primero termine (hasta `espera_s`)."""
    from . import papel as P
    ruta = P.ruta_papel(reg) / "ronda.lock"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    f = open(ruta, "a+b")
    tomado = False
    limite = time.monotonic() + espera_s
    try:
        while True:
            try:
                _bloquear(f)
                tomado = True
                break
            except OSError:
                if time.monotonic() >= limite:
                    raise RondaOcupada(f"otra ronda sigue corriendo después de {espera_s:.0f} s")
                time.sleep(cada_s)
        yield
    finally:
        if tomado:
            try:
                _desbloquear(f)
            except OSError:
                pass
        f.close()


def fecha_ronda(ahora: datetime) -> str:
    """Día que procesa la ronda: la vela diaria que cerró a las 00:00 UTC (hoy UTC menos un día)."""
    u = ahora.astimezone(timezone.utc)
    return (datetime(u.year, u.month, u.day, tzinfo=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def ronda_ya_corrio(reg, fecha: str) -> bool:
    """Sí, SOLO si ya existe salida/boletos_<fecha>.json (es lo último que escribe la ronda).

    Si la ronda tronó a medias (algunas carteras guardadas, otras no), el archivo no existe y la ronda se vuelve a
    correr: las carteras ya procesadas regresan lo guardado (no se duplican) y al final se escriben los boletos de todas."""
    from . import archivos as AR
    return (AR.carpeta_datos(reg).parent / "salida" / f"boletos_{fecha}.json").exists()


def _mostrar_ronda_guardada(reg, fecha: str) -> int:
    """La ronda de ese día ya corrió: no se reescribe nada; se muestra lo guardado."""
    from . import archivos as AR
    from . import papel as P
    try:
        carteras = {}
        for n in P.CARTERAS:
            r = P.cargar_estado(reg, n, fecha).get("rondas", {}).get(fecha)
            if r:
                carteras[n] = r
        arch_refs = P.ruta_papel(reg) / "referencias.json"
        refs = AR.leer_json_seguro(arch_refs).get(fecha, {}) if AR.hay_archivo(arch_refs) else {}
        arch_b = AR.carpeta_datos(reg).parent / "salida" / f"boletos_{fecha}.json"
        boletos = AR.leer_json_seguro(arch_b) if AR.hay_archivo(arch_b) else []
        fila_bit, saltados = _ultima_bitacora(reg, fecha)
        seguro = bool(fila_bit.get("modo_seguro"))   # ¿esa ronda quedó en MODO SEGURO?
        causa = str(fila_bit.get("causa_modo_seguro") or "")[:200]
        vetos_bit = {}
        for k in ("veto", "veto_info"):              # el veto que frenó compras (⚠️) o el que solo se informó (ℹ️)
            v = fila_bit.get(k)
            if isinstance(v, dict):
                vetos_bit[k] = {"razon": str(v.get("razon", "")), "vence": str(v.get("vence", ""))}
        infos = fila_bit.get("informativos")
        infos = [x for x in infos if isinstance(x, str)] if isinstance(infos, list) else []   # ℹ️ de la ronda original
    except AR.ArchivoDanado as e:
        print(f"❌ {e}")
        AR.registrar_tarea(reg, "THE BOSS", "ronda", False, str(e)[:160])
        return 1
    print(f"la ronda de {fecha} ya corrió (no se repite; esto es lo que se guardó):")
    _avisar_saltados(saltados)
    AR.registrar_tarea(reg, "THE BOSS", "ronda", True, "ya existía")
    avisos = [causa] if seguro and causa else []     # la causa real que guardó la ronda original
    print(P.resumen_corto({"dia": fecha, "carteras": carteras, "referencias": refs, "avisos": avisos,
                           "modo_seguro": seguro, "informativos": infos, **vetos_bit}))
    if boletos:
        print()
        print("Boletos de esa ronda (ya entregados; NO se vuelven a poner):")
        for b in boletos:
            print("  " + b.get("texto", b["boleto_id"]))
    return 0


def correr_ronda(reg, ahora: datetime | None = None, cliente=None, memes: list[str] | None = None) -> int:
    """La ronda del día con todas las revisiones de hora. Regresa 0 si corrió, 1 si no."""
    from . import archivos as AR
    from . import datos as D
    from . import papel as P
    t0 = time.monotonic()
    ahora = ahora or datetime.now(timezone.utc)
    hora = revisar_hora(reg, ahora)
    if hora["estado"] == "TEMPRANO":
        print(f"⏳ Es muy temprano ({hora['hora_real_utc']}): la vela diaria cierra a las 00:00 UTC y Binance puede no tenerla "
              f"completa antes de las 00:{hora['minuto_minimo_utc']:02.0f}. No corrí nada. La ronda es a las {hora['hora_programada_utc']} UTC (6:10 p. m. CDMX).")
        AR.registrar_tarea(reg, "THE BOSS", "ronda", False, f"temprano: antes de las 00:{hora['minuto_minimo_utc']:02.0f} UTC", a_tiempo=False)
        return 1
    fecha = fecha_ronda(ahora)
    if ronda_ya_corrio(reg, fecha):
        return _mostrar_ronda_guardada(reg, fecha)
    fuera = hora["estado"] == "FUERA_DE_HORA"
    if fuera:
        print(f"FUERA DE HORA: la ronda es a las {hora['hora_programada_utc']} UTC y van {hora['retraso_min']:.0f} minutos de "
              f"retraso (máximo {hora['max_retraso_min']:.0f}). Se revisan posiciones y stops, pero NO se generan boletos de compra.")
    try:
        with candado_ronda(reg):
            if ronda_ya_corrio(reg, fecha):  # otro proceso la terminó mientras esperábamos el candado
                return _mostrar_ronda_guardada(reg, fecha)
            cli = cliente or D.ClienteBinance(reg)
            dd = P.preparar_datos(reg, cli, memes if memes is not None else _memes(), ahora=ahora)
            out = P.ronda(reg, dd, bloquear_compras="ronda FUERA DE HORA" if fuera else "")
    except Exception as e:  # noqa: BLE001 - cualquier falla debe verse: una ronda caída nunca pasa desapercibida
        motivo = (str(e).strip() or type(e).__name__).splitlines()[0][:160]
        print(f"❌ La ronda NO corrió: {motivo}\nHoy no hay boletos. Los stops ya puestos siguen igual. Avisa a THE BOSS.")
        AR.registrar_tarea(reg, "THE BOSS", "ronda", False, motivo)
        return 1
    duracion = time.monotonic() - t0
    maximo = float(reg.get("ronda.tiempo_max_segundos", 60))
    n_boletos = sum(len(c["boletos"]) for c in out["carteras"].values())
    try:
        _guardar_bitacora(reg, {"hora_real_utc": hora["hora_real_utc"], "dia_procesado": out["dia"],
                                "duracion_s": round(duracion, 1), "fuera_de_hora": fuera, "retraso_min": hora["retraso_min"],
                                "modo_seguro": out.get("modo_seguro", False), "boletos": n_boletos,
                                "veto": out.get("veto"), "veto_info": out.get("veto_info"),
                                "causa_modo_seguro": P.causa_modo_seguro(out, limite=200) if out.get("modo_seguro") else "",
                                "informativos": out.get("informativos", [])})
    except OSError as e:
        # La ronda ya terminó y sus boletos ya están guardados: que falle la bitácora no la tumba, pero se dice
        print(f"⚠️ No pude escribir la bitácora de rondas ({type(e).__name__}). La ronda sí corrió; si la repites hoy, "
              f"no dirá si quedó en MODO SEGURO o FUERA DE HORA. Avisa a THE BOSS.")
    detalle = f"{n_boletos} boletos; día {out['dia']}; {duracion:.0f} s" + ("; fuera_de_hora" if fuera else "")
    AR.registrar_tarea(reg, "THE BOSS", "ronda", True, detalle, a_tiempo=not fuera)
    if fuera:
        print("FUERA DE HORA — hoy no hay compras.")
    texto = P.resumen_corto(out)
    print(texto)
    # Avisos "⚠️" de las carteras que no cupieron en el resumen de 10 líneas: también se ven en pantalla
    for m, ns in P.avisos_carteras(out).items():
        if m not in texto:
            print(f"⚠️ Cartera{'s' if len(ns) > 1 else ''} {', '.join(ns)}: {m}")
    if duracion > maximo:
        print(f"⚠️ La ronda tardó {duracion:.0f} s (máximo {maximo:.0f} s). Normal el primer día (descarga); si se repite, avisa.")
    todos = [b for c in out["carteras"].values() for b in c["boletos"]]
    if todos:
        print("\nBoletos para el EJECUTOR (copiar tal cual):")
        for b in todos:
            print("  " + b["texto"])
    return 0


def cmd_ronda(args) -> int:
    reg = _reg(args)
    if args.modo != "papel":
        print("Solo existe el modo papel: ninguna estrategia ha pasado las compuertas para dinero real.")
        return 2
    if args.verificar:
        return verificar_boletos(reg)
    return correr_ronda(reg)


def _ultima_bitacora(reg, fecha: str) -> tuple[dict, int]:
    """(última fila de datos/papel/bitacora_rondas.jsonl de ese día o {}, renglones dañados que se saltaron).

    Es JSON por renglón (no un solo documento). Se lee en bytes y cada renglón se decodifica con errors="replace":
    un byte inválido no tumba la lectura. Un renglón que no es JSON o no es un objeto se salta y se cuenta.
    Solo si el archivo no se puede abrir: error claro (mismo manejo que un archivo de estado dañado)."""
    from . import archivos as AR
    from . import papel as P
    arch = P.ruta_papel(reg) / "bitacora_rondas.jsonl"
    if not arch.exists():
        return {}, 0
    try:
        crudo = arch.read_bytes()
    except OSError as e:
        raise AR.ArchivoDanado(f"El archivo {arch.name} está dañado y no se puede leer ({type(e).__name__}). "
                               f"Revisa {arch} antes de volver a verificar.")
    ultima, saltados = {}, 0
    for renglon in crudo.split(b"\n"):
        linea = renglon.decode("utf-8", errors="replace").strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except (ValueError, RecursionError):   # RecursionError: renglón con demasiados "[" o "{" anidados
            saltados += 1
            continue
        if not isinstance(fila, dict):
            saltados += 1
            continue
        if fila.get("dia_procesado") == fecha:
            ultima = fila
    return ultima, saltados


def _avisar_saltados(saltados: int) -> None:
    if saltados:
        print(f"⚠️ bitacora_rondas.jsonl: {saltados} renglón(es) dañado(s) saltado(s)")


def _multiplo(x, paso) -> bool:
    """x es múltiplo exacto de `paso` (tick de precio o paso de cantidad de Binance)."""
    from decimal import Decimal, InvalidOperation
    try:
        return not paso or Decimal(str(x)) % Decimal(str(paso)) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def _n(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _revisar_compra(reg, b: dict, f) -> list[str]:
    """Errores de un boleto COMPRAR contra el reglamento vigente y las reglas de Binance (`f`): stop abajo de la
    entrada, límite del stop en o abajo del stop, riesgo dentro del tope de su cartera, cantidad y precios en los
    pasos de Binance, y que la venta en el stop (cantidad neta × precio límite) llegue al mínimo."""
    errores = []
    cart = reg.para_cartera(b.get("cartera", "A"))
    if b.get("version_reglamento") != reg.version:
        errores.append(f"reglamento {b.get('version_reglamento')} y el vigente es {reg.version}")
    stop, lim = _n(b.get("stop")), _n(b.get("precio_limite_stop"))
    if not (stop < _n(b.get("precio_entrada"))):
        errores.append("el stop no está abajo de la entrada")
    if not (0 < lim <= stop):
        errores.append("el límite del stop no está en o abajo del stop")
    if _n(b.get("riesgo_pct")) > float(cart.riesgo["riesgo_por_operacion_pct"]) * 1.01:
        errores.append(f"arriesga {b.get('riesgo_pct')} % y el tope es {cart.riesgo['riesgo_por_operacion_pct']} %")
    if f is not None:
        cant, cant_stop = _n(b.get("cantidad")), _n(b.get("cantidad_stop", b.get("cantidad")))
        if not _multiplo(b.get("cantidad"), f.paso):
            errores.append("la cantidad no está redondeada al paso de Binance")
        if cant < f.cantidad_min or cant_stop < f.cantidad_min:
            errores.append("la cantidad no llega a la cantidad mínima de Binance (minQty)")
        for nombre, campo in (("el precio de entrada", "precio_entrada"), ("el stop", "stop"),
                              ("el límite del stop", "precio_limite_stop")):
            if not _multiplo(b.get(campo), f.tick):
                errores.append(f"{nombre} no es múltiplo del tick de Binance")
        if cant_stop * lim < f.minimo_usdt:   # el stop vende la cantidad neta al precio límite
            errores.append("la venta en el stop no llega al mínimo de Binance")
    return errores


def _revisar_mover_stop(b: dict, f) -> list[str]:
    """Errores de un boleto MODIFICAR_STOP: el stop solo puede SUBIR, debe traer los dos identificadores (el stop
    que se cancela y el nuevo) y la cantidad y los precios deben cumplir las reglas de Binance."""
    errores = []
    stop, lim = _n(b.get("stop")), _n(b.get("precio_limite_stop"))
    if not b.get("id_stop") or not b.get("id_stop_anterior"):
        errores.append("faltan los id del stop (id_stop e id_stop_anterior)")
    if not (stop > _n(b.get("stop_anterior"))):
        errores.append("el stop nuevo no está arriba del anterior (solo sube)")
    if not (0 < lim <= stop):
        errores.append("el límite del stop no está en o abajo del stop")
    if f is not None:
        for nombre, x in (("el stop", b.get("stop")), ("el límite del stop", b.get("precio_limite_stop"))):
            if not _multiplo(x, f.tick):
                errores.append(f"{nombre} no es múltiplo del tick de Binance")
        cant = b.get("cantidad_stop", b.get("cantidad"))
        if not _multiplo(cant, f.paso):
            errores.append("la cantidad no está redondeada al paso de Binance")
        if _n(cant) < f.cantidad_min:
            errores.append("la cantidad no llega a la cantidad mínima de Binance (minQty)")
        if _n(cant) * lim < f.minimo_usdt:
            errores.append("la venta en el stop no llega al mínimo de Binance")
    return errores


def _precio_promedio(cli, simbolo: str) -> float | None:
    """Precio promedio de Binance (/api/v3/avgPrice, público): el que usa para el mínimo de una orden a mercado."""
    try:
        return float(cli.spot("/api/v3/avgPrice", {"symbol": simbolo})["price"])
    except Exception:  # noqa: BLE001
        return None


def _revisar_venta(cli, b: dict, f) -> list[str]:
    """Errores de un boleto CERRAR a mercado: cantidad mayor que 0, en los pasos de Binance (LOT_SIZE y
    MARKET_LOT_SIZE) y con valor arriba del mínimo. Si no se puede leer el precio solo se avisa: una salida
    nunca se detiene por una lectura de precio."""
    errores = []
    cant = b.get("cantidad_stop", b.get("cantidad"))
    if not _n(cant) > 0:
        errores.append("la cantidad a vender es 0")
    if f is not None:
        # A mercado valen LOT_SIZE y, si existe, también MARKET_LOT_SIZE (uno no sustituye al otro)
        if not _multiplo(cant, f.paso):
            errores.append("la cantidad no está redondeada al paso de Binance (LOT_SIZE)")
        if f.paso_mercado > 0 and not _multiplo(cant, f.paso_mercado):
            errores.append("la cantidad no está redondeada al paso de Binance para órdenes a mercado (MARKET_LOT_SIZE)")
        if _n(cant) < f.cantidad_min:
            errores.append("la cantidad no llega a la cantidad mínima de Binance (minQty)")
        if f.cantidad_min_mercado > 0 and _n(cant) < f.cantidad_min_mercado:
            errores.append("la cantidad no llega al mínimo de Binance para órdenes a mercado (MARKET_LOT_SIZE minQty)")
        if f.cantidad_max_mercado > 0 and _n(cant) > f.cantidad_max_mercado:
            errores.append("la cantidad pasa el máximo de Binance para órdenes a mercado (MARKET_LOT_SIZE maxQty)")
        precio = _precio_promedio(cli, b["simbolo"])
        if precio is None:
            # Una salida no se detiene por una lectura de precio: solo se avisa
            print("⚠️ no pude leer el precio para revisar el mínimo; revísalo a mano")
        elif _n(cant) * precio < f.minimo_usdt:
            errores.append(f"la venta (unos {_n(cant) * precio:.2f} USDT) no llega al mínimo de Binance")
    return errores


def _revisar_boleto(reg, cli, b, por: dict, ahora_utc: datetime) -> list[str]:
    """Todo lo que está mal en UN boleto (lista vacía = se puede poner). Lo que no se reconoce, no se aprueba."""
    from .exchange import filtros_desde_exchangeinfo
    if not isinstance(b, dict):
        return ["no es un boleto (formato raro): no lo pongas"]
    errores = []
    if not b.get("boleto_id"):
        errores.append("no trae boleto_id")
    if b.get("vence") and ahora_utc > datetime.fromisoformat(str(b["vence"]).replace("Z", "+00:00")):
        errores.append("boleto vencido: no lo pongas")
    accion = b.get("accion")
    f = filtros_desde_exchangeinfo(por[b["simbolo"]]) if b.get("simbolo") in por else None
    if accion == "CERRAR" and b.get("tipo_orden") == "YA_EJECUTADO_POR_STOP":
        if "VENDER" in str(b.get("texto", "")).upper():   # solo informa: nunca pide vender
            errores.append("el stop ya se ejecutó: este boleto no debe pedir vender")
    elif accion in ("COMPRAR", "MODIFICAR_STOP") or (accion == "CERRAR" and b.get("tipo_orden") == "MARKET"):
        if f is None:
            errores.append("Binance ya no lista esta moneda")
        elif f.estado != "TRADING":
            errores.append(f"Binance tiene esta moneda en estado {f.estado} (no TRADING)")
        if accion == "COMPRAR":
            errores += _revisar_compra(reg, b, f)
        elif accion == "MODIFICAR_STOP":
            errores += _revisar_mover_stop(b, f)
        else:
            errores += _revisar_venta(cli, b, f)
    elif accion == "CERRAR":
        errores.append(f"tipo de orden desconocido para cerrar ({b.get('tipo_orden')}): no lo pongas")
    else:
        errores.append(f"acción desconocida ({accion}): no lo pongas")
    return errores


def verificar_boletos(reg, fecha: str | None = None, ahora: datetime | None = None) -> int:
    """Revisa cada boleto del día: reglamento vigente, cantidades y precios ya redondeados, riesgo dentro del tope."""
    from . import archivos as AR
    from . import datos as D
    fecha = fecha or fecha_ronda(datetime.now(timezone.utc))   # la ronda lleva la fecha de la vela cerrada (ayer UTC)
    arch = AR.carpeta_datos(reg).parent / "salida" / f"boletos_{fecha}.json"   # = salida/ del proyecto
    if not arch.exists():
        # La ronda SIEMPRE escribe este archivo (vacío si no hubo boletos): si no existe, la ronda no corrió.
        print(f"❌ NO HAY RONDA de {fecha}: no pongas nada y avisa a THE BOSS")
        AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", False, f"no hay ronda de {fecha}")
        return 1
    try:
        boletos = AR.leer_json_seguro(arch)
    except AR.ArchivoDanado as e:
        print(f"❌ {e} No pongas nada y avisa a THE BOSS.")
        AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", False, str(e)[:160])
        return 1
    if not boletos:
        try:
            fila_bit, saltados = _ultima_bitacora(reg, fecha)
            fuera = bool(fila_bit.get("fuera_de_hora"))
        except AR.ArchivoDanado as e:
            print(f"❌ {e}")
            AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", False, str(e)[:160])
            return 1
        _avisar_saltados(saltados)
        if fuera:
            print(f"⚠️ La ronda del {fecha} corrió FUERA DE HORA (sin compras)")
            AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", True, "sin boletos; ronda fuera de hora")
            return 0
        print(f"👍 La ronda del {fecha} sí corrió: hoy no hubo boletos.")
        AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", True, "sin boletos")
        return 0
    cli = D.ClienteBinance(reg)
    try:
        info = cli.exchange_info("SPOT", forzar=True)   # reglas frescas; si Binance no contesta, la copia guardada
        por = {x["symbol"]: x for x in info["symbols"]}
    except Exception as e:  # noqa: BLE001 - sin las reglas de Binance no se puede revisar nada: no se pone nada
        print("❌ No pude leer las reglas de Binance: no pongas nada")
        AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", False, f"sin reglas de Binance ({type(e).__name__})")
        return 1
    for a in getattr(cli, "avisos_copias", []):   # Binance no contestó y se revisa con la copia guardada: se dice
        print("⚠️ " + a[0].upper() + a[1:] + ". Si un boleto falla en Binance por una regla nueva, avisa a THE BOSS.")
    if not isinstance(boletos, list):
        print(f"❌ El archivo {arch.name} no trae una lista de boletos: no pongas nada y avisa a THE BOSS")
        AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", False, "el archivo de boletos no es una lista")
        return 1
    problemas = 0
    ahora_utc = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    for i, b in enumerate(boletos):
        nombre = str(b.get("boleto_id") or f"boleto #{i + 1} (sin id)") if isinstance(b, dict) else f"boleto #{i + 1} (ilegible)"
        try:
            errores = _revisar_boleto(reg, cli, b, por, ahora_utc)
        except Exception as e:  # noqa: BLE001 - un boleto mal formado nunca se aprueba ni tumba la revisión de los demás
            errores = [f"boleto mal formado ({type(e).__name__}): no lo pongas"]
        print(("✅ " if not errores else "❌ ") + nombre + ("" if not errores else ": " + "; ".join(errores)))
        problemas += bool(errores)
    AR.registrar_tarea(reg, "EJECUTOR", "ronda --verificar", problemas == 0, f"{problemas} boletos con problema")
    print("👍 Todos los boletos cumplen el reglamento." if problemas == 0 else
          f"❌ {problemas} boleto(s) NO se ponen. Avísale a THE BOSS.")
    return 0 if problemas == 0 else 1


def cmd_registrar_llenado(args) -> int:
    """En papel (--ensayo): el Ejecutor escribe lo que pondría en Binance y se compara con el boleto."""
    from . import archivos as AR
    reg = _reg(args)
    fecha = args.boleto[:8]
    # La misma carpeta en la que la ronda escribe los boletos y `ronda --verificar` los lee (la del reglamento)
    arch = AR.carpeta_datos(reg).parent / "salida" / f"boletos_{fecha[:4]}-{fecha[4:6]}-{fecha[6:8]}.json"
    if not arch.exists():
        print(f"❌ No encuentro el archivo de boletos de ese día ({arch.name}).")
        AR.registrar_tarea(reg, args.bot, "registrar-llenado", False, "boleto inexistente")
        return 1
    try:
        boletos = AR.leer_json_seguro(arch)
    except AR.ArchivoDanado as e:
        print(f"❌ {e}")
        AR.registrar_tarea(reg, args.bot, "registrar-llenado", False, str(e)[:160])
        return 1
    b = next((x for x in (boletos if isinstance(boletos, list) else [])
              if isinstance(x, dict) and x.get("boleto_id") == args.boleto), None)
    if b is None:
        print(f"❌ No existe el boleto {args.boleto}.")
        AR.registrar_tarea(reg, args.bot, "registrar-llenado", False, "boleto inexistente")
        return 1
    dif = []
    if args.simbolo and args.simbolo.upper() != b["simbolo"]:
        dif.append(f"moneda {args.simbolo} en vez de {b['simbolo']}")
    if args.cantidad is not None and abs(args.cantidad - float(b["cantidad"])) > 1e-12:
        dif.append(f"cantidad {args.cantidad} en vez de {b['cantidad']}")
    ref = b.get("precio_entrada") or b.get("stop")
    if args.precio is not None and ref and abs(args.precio / float(ref) - 1) > 0.001:
        dif.append(f"precio {args.precio} en vez de {ref}")
    if args.stop is not None and b.get("stop") and abs(args.stop - float(b["stop"])) > 1e-12:
        dif.append(f"stop {args.stop} en vez de {b['stop']}")
    if not args.ensayo:
        print("En la v2 solo se opera en papel: usa --ensayo.")
        return 2
    AR.registrar_tarea(reg, args.bot, "registrar-llenado", True, "; ".join(dif), diferencias=len(dif))
    print("👍 Copiado igualito al boleto." if not dif else "⚠️ Diferencias con el boleto: " + "; ".join(dif) +
          ". En dinero real esto NO se vale: el boleto se copia exacto.")
    return 0 if not dif else 1


def cmd_conciliar(args) -> int:
    return conciliar(_reg(args))


def conciliar(reg) -> int:
    """Papel: efectivo + costo de lo abierto debe cuadrar con capital inicial + ganancias cerradas.

    Deja el resultado en datos/papel/conciliacion.json: con ok:false la ronda NO abre posiciones nuevas
    (el motor de riesgo lo respeta) hasta que un conciliar bueno lo ponga en ok:true."""
    from . import archivos as AR
    from . import papel as P
    ok_total = True
    diferencias = {}
    for n in P.CARTERAS:
        try:
            est = P.cargar_estado(reg, n, "")
        except AR.ArchivoDanado as e:
            print(f"❌ {e}")
            AR.registrar_tarea(reg, "CONTADOR", "conciliar", False, str(e)[:160])
            return 1
        cerradas = sum(c["ganancia_usdt"] for c in est["cerradas"])
        costo_abierto = sum(p["costo_total"] for p in est["posiciones"])
        esperado = est["capital_inicial"] + cerradas
        real = est["efectivo"] + costo_abierto
        dif = real - esperado
        tol = float(reg.get("conciliacion.tolerancia_usdt", 0.10))
        ok = abs(dif) <= tol
        ok_total &= ok
        diferencias[n] = round(dif, 6)
        print(f"{'✅' if ok else '❌'} Cartera {n}: diferencia {dif:+.4f} USDT (tolerancia {tol})")
    AR.escribir_json_seguro(P.ruta_papel(reg) / "conciliacion.json",
                            {"fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": ok_total,
                             "diferencias": diferencias})
    AR.registrar_tarea(reg, "CONTADOR", "conciliar", ok_total)
    print("👍 Las cuentas cuadran." if ok_total else "❌ No cuadra: PAUSA hasta revisar. Avísale a THE BOSS.")
    return 0 if ok_total else 1


def reanudar(reg, cartera: str, ok_angelo: str, bot: str = "THE BOSS") -> int:
    """Reanuda una cartera DETENIDA por el freno total, solo con el OK de Ángelo (texto obligatorio).
    detenido=false y el pico vuelve al capital actual, para que la siguiente ronda no se detenga por el mismo pico."""
    from . import archivos as AR
    from . import papel as P
    cartera = cartera.upper()
    if cartera not in P.CARTERAS:
        print(f"❌ No existe la cartera {cartera}. Usa {', '.join(P.CARTERAS)}.")
        return 2
    if not ok_angelo or not ok_angelo.strip():
        print("❌ Falta el OK de Ángelo (--ok-angelo \"…\"). Sin eso no se reanuda.")
        return 2
    arch = P.ruta_papel(reg) / f"cartera_{cartera}.json"
    if not AR.hay_archivo(arch):
        print(f"La Cartera {cartera} no estaba detenida (todavía no ha corrido).")
        return 0
    try:
        est = AR.leer_json_seguro(arch)
    except AR.ArchivoDanado as e:
        print(f"❌ No se puede reanudar: {e}")
        AR.registrar_tarea(reg, bot, "reanudar", False, str(e)[:160])
        return 1
    if not est.get("detenido"):
        print(f"La Cartera {cartera} no estaba detenida. No cambié nada.")
        return 0
    capital = float(list(est["curva"].values())[-1]) if est.get("curva") else float(est["capital_inicial"])
    pico_viejo = float(est.get("pico", capital))
    est["detenido"] = False
    est["pico"] = capital
    est.setdefault("reanudaciones", []).append({"fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                               "texto": ok_angelo.strip(), "pico_anterior": pico_viejo, "pico_nuevo": capital,
                                               "por": bot})
    P.guardar_estado(reg, est)
    AR.registrar_tarea(reg, bot, "reanudar", True, f"Cartera {cartera}: {ok_angelo.strip()}")
    print(f"👍 Cartera {cartera} reanudada con el OK de Ángelo. El pico vuelve a {capital:.2f} USDT (antes {pico_viejo:.2f}).")
    return 0


def cmd_reanudar(args) -> int:
    return reanudar(_reg(args), args.cartera, args.ok_angelo, args.bot)


def cmd_reporte(args) -> int:
    from . import archivos as AR
    from . import reportes
    reg = _reg(args)
    try:
        texto = reportes.diario(reg) if args.tipo == "diario" else reportes.semanal(reg)
    except AR.ArchivoDanado as e:
        print(f"❌ No se pudo hacer el reporte: {e}")
        AR.registrar_tarea(reg, "CONTADOR", f"reporte {args.tipo}", False, str(e)[:160])
        return 1
    print(texto)
    AR.registrar_tarea(reg, "CONTADOR", f"reporte {args.tipo}", True)
    return 0


def cmd_estado(args) -> int:
    return mostrar_estado(_reg(args), args.bots, args.dias)


def mostrar_estado(reg, bots: bool = False, dias: int = 7) -> int:
    from . import archivos as AR
    from . import papel as P
    if bots:
        cal = AR.calificacion_bots(reg, dias)
        if not cal:
            print("Todavía no hay tareas registradas de los bots.")
            return 0
        print(f"Calificación de los bots (últimos {dias} días):")
        for bot, c in sorted(cal.items()):
            pct = c["a_tiempo"] / c["tareas"] * 100 if c["tareas"] else 0
            print(f"  {bot}: {c['tareas']} tareas, {pct:.0f} % bien y a tiempo, {c['rechazos']} archivos rechazados, "
                  f"{c['diferencias']} diferencias boleto/llenado")
        return 0
    for n in P.CARTERAS:
        try:
            est = P.cargar_estado(reg, n, "")
        except AR.ArchivoDanado as e:
            print(f"❌ {e}")
            return 1
        ult = list(est["curva"].values())[-1] if est["curva"] else est["capital_inicial"]
        print(f"Cartera {n}: {ult:.2f} USDT · {len(est['posiciones'])} abiertas · {len(est['cerradas'])} cerradas · "
              f"{len(est['saltadas_capital'])} señales saltadas por capital")
    activas = [k for k, v in reg.estrategias.items() if v.get("estado") != "APAGADA"]
    print("Motores encendidos: " + (", ".join(activas) if activas else "ninguno (todo APAGADO)"))
    return 0


def cmd_estela(args) -> int:
    from . import archivos as AR
    from . import datos as D
    from . import estela_vivo
    reg = _reg(args)
    if not args.foto:
        print("Usa: python -m sobreviviente estela --foto")
        return 2
    ok, msg = estela_vivo.guardar_foto(reg, D.ClienteBinance(reg))
    AR.registrar_tarea(reg, "ESTELA", "estela --foto", ok, msg)
    print(("👍 " if ok else "❌ ") + msg)
    return 0 if ok else 1


def cmd_respaldo(args) -> int:
    """Copia de seguridad del estado de papel, los boletos y los archivos de los bots (no cambia nada de origen)."""
    from . import respaldo
    return respaldo.respaldar(_reg(args))


def cmd_doctor(args) -> int:
    from . import doctor
    return doctor.revisar(_reg(args))


def registrar(sub) -> None:
    r = sub.add_parser("ronda", help="ronda diaria (6:10 p. m. CDMX)")
    r.add_argument("--modo", default="papel", choices=["papel", "real"])
    r.add_argument("--verificar", action="store_true", help="revisa los boletos del día")
    r.set_defaults(f=cmd_ronda)
    ll = sub.add_parser("registrar-llenado", help="el Ejecutor confirma un boleto")
    ll.add_argument("--boleto", required=True)
    ll.add_argument("--ensayo", action="store_true", help="papel: solo compara contra el boleto")
    ll.add_argument("--simbolo")
    ll.add_argument("--cantidad", type=float)
    ll.add_argument("--precio", type=float)
    ll.add_argument("--stop", type=float)
    ll.add_argument("--bot", default="EJECUTOR")
    ll.set_defaults(f=cmd_registrar_llenado)
    sub.add_parser("conciliar", help="revisa que las cuentas cuadren").set_defaults(f=cmd_conciliar)
    ra = sub.add_parser("reanudar", help="reanuda una cartera detenida por el freno total (solo con el OK de Ángelo)")
    ra.add_argument("--cartera", required=True, choices=["A", "B", "C", "a", "b", "c"])
    ra.add_argument("--ok-angelo", required=True, dest="ok_angelo", help="texto del OK de Ángelo, tal cual")
    ra.add_argument("--bot", default="THE BOSS")
    ra.set_defaults(f=cmd_reanudar)
    rp = sub.add_parser("reporte", help="reporte diario o semanal")
    rp.add_argument("tipo", choices=["diario", "semanal"])
    rp.set_defaults(f=cmd_reporte)
    es = sub.add_parser("estado", help="cómo van las carteras")
    es.add_argument("--bots", action="store_true", help="calificación de los bots")
    es.add_argument("--dias", type=int, default=7)
    es.set_defaults(f=cmd_estado)
    et = sub.add_parser("estela", help="ESTELA: foto diaria de los top traders")
    et.add_argument("--foto", action="store_true")
    et.set_defaults(f=cmd_estela)
    sub.add_parser("respaldo", help="copia de seguridad del estado de papel y los boletos").set_defaults(f=cmd_respaldo)
    sub.add_parser("doctor", help="revisa la computadora de Grok Bot").set_defaults(f=cmd_doctor)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(1)
