"""Comandos del dinero REAL (arreglos 130 a 139). El programa nunca tiene llaves ni firma órdenes: EJECUTOR pone las
órdenes por el conector de Binance y guarda lo que contestó Binance; estos comandos solo leen esos archivos.

  registrar-saldo --cuenta <archivo> --ordenes <archivo>   foto de saldo (spot.getAccount y spot.getOpenOrders)
"""
from __future__ import annotations

from . import real as RE


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


def cmd_registrar_saldo(args) -> int:
    reg = _reg(args)
    ok, mensajes = RE.registrar_saldo(reg, args.cuenta, args.ordenes, precio_publico(reg))
    for m in mensajes:
        print(m if m.startswith("ℹ️") else f"❌ {m}")
    print("👍 Foto de saldo guardada (datos/real/saldo_binance.json)." if ok else
          "❌ La foto de saldo NO sirve: hoy no hay compras reales. Avisa a THE BOSS con este mensaje completo.")
    return 0 if ok else 1


def conciliar_real(reg) -> int:
    """`conciliar --real` (arreglo 131): la foto de saldo contra cartera_REAL.json."""
    res = RE.conciliar(reg)
    sin_stop = [t for ok, t in res["lineas"] if t.startswith("SIN STOP")]
    for t in sin_stop:                                  # lo más urgente va primero
        print(f"❌ {t}")
    for ok, t in res["lineas"]:
        if t not in sin_stop:
            print(("✅ " if ok else "❌ ") + t)
    print("👍 Las cuentas reales cuadran." if res["ok"] else
          "❌ Lo real NO cuadra: sin compras reales nuevas hasta revisar. Avisa a THE BOSS de inmediato, con prioridad.")
    return 0 if res["ok"] else 1


def cmd_ajustar_capital_real(args) -> int:
    reg = _reg(args)
    try:
        ok, msg = RE.ajustar_capital(reg, args.usdt, args.ok_angelo)
    except RE.EstadoRealDanado as e:
        ok, msg = False, str(e)
    print(("👍 " if ok else "❌ ") + msg)
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
