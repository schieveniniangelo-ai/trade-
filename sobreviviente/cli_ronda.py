"""Comandos de operación diaria (Fase 5 de la especificación, versión v2 en PAPEL).

  ronda --modo papel          la ronda del día (00:10 UTC = 6:10 p. m. CDMX)
  ronda --verificar           revisa los boletos del día contra el reglamento (antes "Guardián")
  registrar-llenado --ensayo  el Ejecutor confirma que copiaría el boleto tal cual (en papel no hay órdenes)
  conciliar                   revisa que las cuentas de papel cuadren
  reporte diario|semanal      textos cortos para Ángelo
  estado [--bots]             cómo van las carteras / calificación de cada bot
  estela --foto               ESTELA: guarda la foto diaria del posicionamiento de los top traders
  doctor                      revisa que la computadora de Grok Bot tenga todo lo necesario
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _reg(args):
    from .__main__ import _reg as cargar
    return cargar(args)


def _memes() -> list[str]:
    return json.loads((RAIZ / "datos" / "memes.json").read_text(encoding="utf-8"))["memes"]


def cmd_ronda(args) -> int:
    from . import archivos as AR
    from . import datos as D
    from . import papel as P
    reg = _reg(args)
    if args.modo != "papel":
        print("Solo existe el modo papel: ninguna estrategia ha pasado las compuertas para dinero real.")
        return 2
    if args.verificar:
        return verificar_boletos(reg)
    cli = D.ClienteBinance(reg)
    try:
        dd = P.preparar_datos(reg, cli, _memes())
    except D.ErrorDatos as e:
        print(f"❌ No pude bajar datos de Binance: {e}\nHoy no hay entradas nuevas. Los stops puestos siguen igual.")
        AR.registrar_tarea(reg, "THE BOSS", "ronda", False, str(e))
        return 1
    out = P.ronda(reg, dd)
    AR.registrar_tarea(reg, "THE BOSS", "ronda", True, f"{sum(len(c['boletos']) for c in out['carteras'].values())} boletos")
    print(P.resumen_corto(out))
    todos = [b for c in out["carteras"].values() for b in c["boletos"]]
    if todos:
        print("\nBoletos para el EJECUTOR (copiar tal cual):")
        for b in todos:
            print("  " + b["texto"])
    return 0


def verificar_boletos(reg, fecha: str | None = None) -> int:
    """Revisa cada boleto del día: reglamento vigente, cantidades y precios ya redondeados, riesgo dentro del tope."""
    from . import archivos as AR
    from . import datos as D
    from .exchange import filtros_desde_exchangeinfo
    from datetime import timedelta
    fecha = fecha or (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()  # la ronda lleva la fecha de la vela cerrada
    arch = RAIZ / "salida" / f"boletos_{fecha}.json"
    if not arch.exists():
        print(f"No hay boletos del {fecha}. Corre primero la ronda. 👍 si ya sabías que hoy no había nada.")
        return 0
    boletos = json.loads(arch.read_text(encoding="utf-8"))
    info = D.ClienteBinance(reg).exchange_info("SPOT")
    por = {x["symbol"]: x for x in info["symbols"]}
    problemas = 0
    for b in boletos:
        errores = []
        if b["accion"] == "COMPRAR":
            f = filtros_desde_exchangeinfo(por[b["simbolo"]]) if b["simbolo"] in por else None
            cart = reg.para_cartera(b.get("cartera", "A"))
            if b.get("version_reglamento") != reg.version:
                errores.append(f"reglamento {b.get('version_reglamento')} y el vigente es {reg.version}")
            if f is None:
                errores.append("Binance ya no lista esta moneda")
            else:
                from decimal import Decimal
                if Decimal(str(b["cantidad"])) % Decimal(str(f.paso)) != 0:
                    errores.append("la cantidad no está redondeada al paso de Binance")
                if b["cantidad"] * b["stop"] < f.minimo_usdt:
                    errores.append("la venta en el stop no llega al mínimo de Binance")
            if not (b["stop"] < b["precio_entrada"]):
                errores.append("el stop no está abajo de la entrada")
            if b["riesgo_pct"] > float(cart.riesgo["riesgo_por_operacion_pct"]) * 1.01:
                errores.append(f"arriesga {b['riesgo_pct']} % y el tope es {cart.riesgo['riesgo_por_operacion_pct']} %")
        print(("✅ " if not errores else "❌ ") + b["boleto_id"] + ("" if not errores else ": " + "; ".join(errores)))
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
    arch = RAIZ / "salida" / f"boletos_{fecha[:4]}-{fecha[4:6]}-{fecha[6:8]}.json"
    if not arch.exists():
        print(f"❌ No encuentro el archivo de boletos de ese día ({arch.name}).")
        AR.registrar_tarea(reg, args.bot, "registrar-llenado", False, "boleto inexistente")
        return 1
    b = next((x for x in json.loads(arch.read_text(encoding="utf-8")) if x["boleto_id"] == args.boleto), None)
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
    """Papel: efectivo + costo de lo abierto debe cuadrar con capital inicial + ganancias cerradas."""
    from . import archivos as AR
    from . import papel as P
    reg = _reg(args)
    ok_total = True
    for n in P.CARTERAS:
        est = P.cargar_estado(reg, n, "")
        cerradas = sum(c["ganancia_usdt"] for c in est["cerradas"])
        costo_abierto = sum(p["costo_total"] for p in est["posiciones"])
        esperado = est["capital_inicial"] + cerradas
        real = est["efectivo"] + costo_abierto
        dif = real - esperado
        tol = float(reg.get("conciliacion.tolerancia_usdt", 0.10))
        ok = abs(dif) <= tol
        ok_total &= ok
        print(f"{'✅' if ok else '❌'} Cartera {n}: diferencia {dif:+.4f} USDT (tolerancia {tol})")
    AR.registrar_tarea(reg, "CONTADOR", "conciliar", ok_total)
    print("👍 Las cuentas cuadran." if ok_total else "❌ No cuadra: PAUSA hasta revisar. Avísale a THE BOSS.")
    return 0 if ok_total else 1


def cmd_reporte(args) -> int:
    from . import archivos as AR
    from . import reportes
    reg = _reg(args)
    texto = reportes.diario(reg) if args.tipo == "diario" else reportes.semanal(reg)
    print(texto)
    AR.registrar_tarea(reg, "CONTADOR", f"reporte {args.tipo}", True)
    return 0


def cmd_estado(args) -> int:
    from . import archivos as AR
    from . import papel as P
    reg = _reg(args)
    if args.bots:
        cal = AR.calificacion_bots(reg, args.dias)
        if not cal:
            print("Todavía no hay tareas registradas de los bots.")
            return 0
        print(f"Calificación de los bots (últimos {args.dias} días):")
        for bot, c in sorted(cal.items()):
            pct = c["a_tiempo"] / c["tareas"] * 100 if c["tareas"] else 0
            print(f"  {bot}: {c['tareas']} tareas, {pct:.0f} % bien y a tiempo, {c['rechazos']} archivos rechazados, "
                  f"{c['diferencias']} diferencias boleto/llenado")
        return 0
    for n in P.CARTERAS:
        est = P.cargar_estado(reg, n, "")
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
    sub.add_parser("doctor", help="revisa la computadora de Grok Bot").set_defaults(f=cmd_doctor)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(1)
