"""Arreglo 165: el stop sale pegado a la compra.

Binance tiene órdenes OTO (compra y stop en una sola petición, POST /api/v3/orderList/oto), y aceptan una compra LIMIT
FOK con un STOP_LOSS_LIMIT pendiente. Pero el EJECUTOR solo tiene `spot.newOrder` y `spot.deleteOrder` en el conector:
no hay orderList. Por eso la compra y el stop siguen siendo dos órdenes, y el hueco se deja lo más corto posible:

* el boleto trae el stop LISTO para los dos casos de comisión (`orden_stop` si se cobra en BTC y
  `orden_stop_comision_otra_moneda` si se cobra en BNB u otra moneda): el EJECUTOR elige, no calcula;
* el texto del boleto y el del EJECUTOR ponen el stop EN EL ACTO, antes de `registrar-llenado`;
* con un Binance simulado (saldos, comisión, LOT_SIZE, NOTIONAL, PERCENT_PRICE_BY_SIDE), el stop del boleto siempre
  lo acepta Binance si se respeta `no_comprar_si`, y ningún camino deja una posición sin stop y sin aviso.

Sin red, sin llaves y sin dinero: todo es simulación.
"""
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from sobreviviente import real as RE
from sobreviviente import reglamento
from sobreviviente import ronda_real as RR
from sobreviviente.exchange import filtros_desde_exchangeinfo, redondear_abajo

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo132_boleto_real import EMITIDO, FIXTURE
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

BOTS = Path(__file__).resolve().parent.parent / "bots"
F = filtros_desde_exchangeinfo(json.loads(FIXTURE.read_text(encoding="utf-8")))
DIA2 = AHORA + timedelta(days=1)


class Rechazo(Exception):
    """Lo que Binance contestaría con un error (filtro, saldo, stop que se dispararía al instante)."""


class BinanceSimulado:
    """Imita lo que hace Binance Spot con las órdenes del boleto real (solo BTCUSDT). Sin red."""

    def __init__(self, precio, usdt=142.54, comision=("BTC", 0.1), rechazar_stops=0, venta_falla=False,
                 promedio=None, f=F):
        self.f = f
        self.precio = Decimal(str(precio))
        self.promedio = Decimal(str(promedio or precio))       # PERCENT_PRICE_BY_SIDE usa el precio promedio
        self.saldo = {"USDT": Decimal(str(usdt)), "BTC": Decimal(0), "BNB": Decimal("0.5")}
        self.bloqueado = {"USDT": Decimal(0), "BTC": Decimal(0)}
        self.asset_com, self.pct_com = comision[0], Decimal(str(comision[1]))
        self.rechazar_stops = rechazar_stops
        self.venta_falla = venta_falla
        self.abiertas = []
        self.llamadas = []
        self.n = 1000

    def _lote(self, q):
        paso, minimo = Decimal(str(self.f.paso)), Decimal(str(self.f.cantidad_min))
        if q < minimo or (q / paso) != (q / paso).to_integral_value():
            raise Rechazo("Filter failure: LOT_SIZE")

    def nueva_orden(self, o):
        self.llamadas.append(o["type"])
        q = Decimal(o["quantity"])
        self._lote(q)
        self.n += 1
        if o["type"] == "LIMIT":                               # la compra FOK
            assert (o["side"], o["timeInForce"]) == ("BUY", "FOK")
            px = Decimal(o["price"])
            if q * px < Decimal(str(self.f.minimo_usdt)):
                raise Rechazo("Filter failure: NOTIONAL")
            if self.precio > px:
                return {"orderId": self.n, "status": "EXPIRED", "executedQty": "0.00000000", "fills": []}
            costo = q * self.precio
            if costo > self.saldo["USDT"]:
                raise Rechazo("Account has insufficient balance for requested action.")
            self.saldo["USDT"] -= costo
            com = q * self.pct_com / 100
            if self.asset_com == "BTC":
                self.saldo["BTC"] += q - com
            else:
                self.saldo["BTC"] += q
                self.saldo["BNB"] -= Decimal("0.00001")
            return {"orderId": self.n, "status": "FILLED", "executedQty": str(q),
                    "fills": [{"price": str(self.precio), "qty": str(q), "commission": str(com),
                               "commissionAsset": self.asset_com}]}
        if o["type"] == "STOP_LOSS_LIMIT":
            assert (o["side"], o["timeInForce"]) == ("SELL", "GTC")
            if self.rechazar_stops > 0:
                self.rechazar_stops -= 1
                raise Rechazo("rechazo simulado del stop")
            lim, st = Decimal(o["price"]), Decimal(o["stopPrice"])
            if q * lim < Decimal(str(self.f.minimo_usdt)):
                raise Rechazo("Filter failure: NOTIONAL")
            if lim < self.promedio * Decimal(str(self.f.ask_mult_down)) or lim > self.promedio * Decimal(str(self.f.ask_mult_up)):
                raise Rechazo("Filter failure: PERCENT_PRICE_BY_SIDE")
            if st >= self.precio:
                raise Rechazo("Stop price would trigger immediately.")
            if q > self.saldo["BTC"]:
                raise Rechazo("Account has insufficient balance for requested action.")
            self.saldo["BTC"] -= q
            self.bloqueado["BTC"] += q
            self.abiertas.append({**o, "orderId": self.n, "status": "NEW"})
            return {"orderId": self.n, "status": "NEW", "clientOrderId": o["newClientOrderId"]}
        if o["type"] == "MARKET":                              # la venta de emergencia
            assert o["side"] == "SELL"
            if self.venta_falla:
                raise Rechazo("rechazo simulado de la venta")
            if q > self.saldo["BTC"]:
                raise Rechazo("Account has insufficient balance for requested action.")
            self.saldo["BTC"] -= q
            self.saldo["USDT"] += q * self.precio * (1 - Decimal("0.001"))
            return {"orderId": self.n, "status": "FILLED", "executedQty": str(q),
                    "fills": [{"price": str(self.precio), "qty": str(q), "commission": str(q * self.precio / 1000),
                               "commissionAsset": "USDT"}]}
        raise AssertionError(f"el boleto pidió un tipo de orden que no existe en el flujo: {o['type']}")

    def foto(self):
        """Lo que guardaría EJECUTOR de spot.getAccount y spot.getOpenOrders."""
        cta = cuenta(usdt=float(self.saldo["USDT"]), btc=float(self.saldo["BTC"]), btc_bloq=float(self.bloqueado["BTC"]),
                     BNB=float(self.saldo["BNB"]))
        ordenes = [orden_stop(cantidad=o["quantity"], stop=o["stopPrice"], limite=o["price"],
                              client=o["newClientOrderId"], order_id=o["orderId"]) for o in self.abiertas]
        return cta, ordenes


def no_compra(b, px):
    """Las condiciones de `no_comprar_si` del boleto, como las revisa el EJECUTOR con spot.tickerPrice."""
    ns = b["no_comprar_si"]
    return (px > ns["precio_actual_mayor_que"] or px <= ns["precio_actual_menor_o_igual_que"]
            or px > ns["precio_actual_mayor_que_por_percent_price"]
            or float(b["orden_compra"]["quantity"]) * px < ns["valor_menor_que_usdt"])


def stop_elegido(b, respuesta_compra):
    """Paso e del EJECUTOR: elige el stop LISTO según commissionAsset; no calcula nada."""
    moneda = RE.moneda(b["simbolo"])
    asset = respuesta_compra["fills"][0]["commissionAsset"]
    return b["orden_stop"] if asset == moneda else b["orden_stop_comision_otra_moneda"]


@pytest.fixture
def reg():
    r = reglamento.cargar()
    r.datos["estrategias"]["M0"]["estado"] = "VIVA_MINI"
    return r


# ---------------------------------------------------------------- el boleto trae el stop listo

def test_el_boleto_trae_el_stop_listo_para_los_dos_casos_de_comision(reg):
    b = RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, 0.00013, F, EMITIDO)
    st, otra = b["orden_stop"], b["orden_stop_comision_otra_moneda"]
    assert st["quantity"] == "0.00012" and otra["quantity"] == "0.00013" == b["orden_compra"]["quantity"]
    assert {k: v for k, v in otra.items() if k != "quantity"} == {k: v for k, v in st.items() if k != "quantity"}
    assert "HUECO SIN STOP" in b["hueco_sin_stop"] and "OTO" in b["hueco_sin_stop"] and "conector" in b["hueco_sin_stop"]
    reglas = b["reglas_para_la_cantidad_del_stop"]
    assert "orden_stop tal cual" in reglas and "orden_stop_comision_otra_moneda tal cual" in reglas and "PARCIAL" in reglas
    assert RE.revisar_boleto_real(reg, b, F) == []


def test_la_revision_rechaza_un_stop_listo_distinto_o_que_falta(reg):
    b = RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, 0.00013, F, EMITIDO)
    sin = {k: v for k, v in b.items() if k != "orden_stop_comision_otra_moneda"}
    assert any("falta orden_stop_comision_otra_moneda" in e for e in RE.revisar_boleto_real(reg, sin, F))
    otro_precio = json.loads(json.dumps(b))
    otro_precio["orden_stop_comision_otra_moneda"]["stopPrice"] = "60000"
    assert any("no es el mismo stop" in e for e in RE.revisar_boleto_real(reg, otro_precio, F))
    de_menos = json.loads(json.dumps(b))
    de_menos["orden_stop_comision_otra_moneda"]["quantity"] = "0.00012"
    assert any("no es por toda la compra" in e for e in RE.revisar_boleto_real(reg, de_menos, F))


def test_el_texto_del_boleto_pone_el_stop_antes_de_registrar(reg):
    b = RE.boleto_compra_real(reg, "2026-11-15", "BTCUSDT", 70000.0, 59500.0, 0.00013, F, EMITIDO)
    t = b["texto"]
    assert t.index("No compres si") < t.index("HUECO SIN STOP") < t.index("orden_stop (0.00012 BTC)") \
        < t.index("orden_stop_comision_otra_moneda (0.00013 BTC)") < t.index("registra COMPRA_LLENADA")
    assert "EN EL ACTO" in t and "ni registrar-llenado" in t and "FOK" in t and "promesa de ganancia" in t


def test_el_ejecutor_pone_el_stop_antes_de_registrar_y_no_tiene_oto():
    t = (BOTS / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso4 = t[t.index("4. Boleto de COMPRA"):t.index("5. Boleto de CIERRE")]
    compra_ = paso4.index("copiando campo por campo `orden_compra`")
    stop = paso4.index("pon el stop con `spot.newOrder`")
    registro = paso4.index("--evento COMPRA_LLENADA --orden-id")
    assert compra_ < paso4.index("HUECO SIN STOP") < stop < paso4.index("está en estado NEW") < registro
    assert "`orden_stop`" in paso4 and "`orden_stop_comision_otra_moneda`" in paso4 and "No calcules nada" in paso4
    # Las herramientas del conector no traen orderList (OTO): por eso son dos órdenes
    herramientas = next(x for x in t.splitlines() if "Solo usas estas herramientas del conector" in x)
    assert "orderList" not in herramientas and "spot.newOrder" in herramientas


# ---------------------------------------------------------------- Binance siempre acepta el stop del boleto

def _casos():
    r = reglamento.cargar()
    r.datos["estrategias"]["M0"]["estado"] = "VIVA_MINI"
    for capital in (60.0, 142.54, 300.0, 1000.0):
        for precio in (30000.0, 70000.0, 110000.0):
            for stop_pct in (3.0, 8.0, 15.0):
                stop = redondear_abajo(precio * (1 - stop_pct / 100), F.tick)
                cant = redondear_abajo(min(capital * 0.01 / (precio - stop), capital * 0.3 / precio), F.paso)
                if cant <= 0:
                    continue
                b = RE.boleto_compra_real(r, "2026-11-15", "BTCUSDT", precio, stop, cant, F, EMITIDO)
                if RE.revisar_boleto_real(r, b, F):
                    continue                                # ese boleto nunca se emite
                umbral = b["no_comprar_si"]["precio_actual_menor_o_igual_que"]
                for px in (umbral * 1.0001, precio, float(b["orden_compra"]["price"])):
                    if not no_compra(b, px):
                        yield capital, precio, stop_pct, b, px


CASOS = list(_casos())


def test_la_rejilla_tiene_casos_de_verdad():
    assert len(CASOS) >= 30 and len({c[0] for c in CASOS}) >= 3 and len({c[2] for c in CASOS}) == 3


@pytest.mark.parametrize("comision", [("BTC", 0.1), ("BTC", 0.075), ("BNB", 0.075), ("BNB", 0.1)])
def test_binance_acepta_el_stop_del_boleto_en_toda_la_rejilla(comision):
    for capital, precio, stop_pct, b, px in CASOS:
        bn = BinanceSimulado(px, usdt=capital, comision=comision)
        compra_ = bn.nueva_orden(b["orden_compra"])
        assert compra_["status"] == "FILLED", (capital, precio, stop_pct, px)
        orden = stop_elegido(b, compra_)
        bn.nueva_orden(orden)                               # Rechazo = la prueba falla: posición sin stop
        assert bn.llamadas == ["LIMIT", "STOP_LOSS_LIMIT"]  # nada entre la compra y el stop
        # Lo que queda sin stop es polvo: menos del mínimo de Binance (no se puede proteger ni vender aparte)
        assert float(bn.saldo["BTC"]) * px < F.minimo_usdt, (capital, precio, stop_pct, px, comision)


def test_si_el_ejecutor_eligiera_mal_binance_lo_rechazaria():
    """Con la comisión en BTC, el stop por toda la compra pide más BTC del que hay: por eso hay dos órdenes listas."""
    capital, precio, stop_pct, b, px = CASOS[0]
    bn = BinanceSimulado(px, usdt=capital, comision=("BTC", 0.1))
    bn.nueva_orden(b["orden_compra"])
    with pytest.raises(Rechazo, match="insufficient balance"):
        bn.nueva_orden(b["orden_stop_comision_otra_moneda"])


# ---------------------------------------------------------------- ningún camino deja una posición sin stop y callada

def ejecutor(r, b, bn):
    """El EJECUTOR siguiendo al pie de la letra el paso 4 de bots/4_EJECUTOR_REAL.md (c a h)."""
    hecho = []

    def registrar(evento, **kw):
        ok, msgs = RE.registrar_llenado(r, b["boleto_id"], evento, ahora=AHORA + timedelta(minutes=2), **kw)
        assert ok, msgs
        hecho.append((evento, msgs))

    res = bn.nueva_orden(b["orden_compra"])                                     # c
    if res["status"] != "FILLED":                                               # d
        registrar("COMPRA_NO_LLENADA")
        return hecho
    orden = stop_elegido(b, res)                                                # e: en el acto, sin calcular
    stop = None
    for _ in range(2):                                                          # h: un solo reintento
        try:
            stop = bn.nueva_orden(orden)
            break
        except Rechazo:
            continue
    fill = res["fills"][0]
    datos_compra = dict(orden_id=res["orderId"], cantidad=float(res["executedQty"]), precio=float(fill["price"]),
                        comision=float(fill["commission"]), moneda_comision=fill["commissionAsset"])
    if stop is not None:                                                        # f y g
        assert stop["status"] == "NEW"
        registrar("COMPRA_LLENADA", **datos_compra)
        registrar("STOP_PUESTO", orden_id=stop["orderId"], stop_id=orden["newClientOrderId"])
        return hecho
    libre = redondear_abajo(float(bn.saldo["BTC"]), F.paso)                     # h: venta de emergencia
    try:
        venta = bn.nueva_orden({"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": f"{libre:.5f}"})
    except Rechazo:
        venta = None
    registrar("COMPRA_LLENADA", **datos_compra)
    registrar("STOP_NO_PUESTO")
    if venta is not None:
        vf = venta["fills"][0]
        registrar("CIERRE_DE_EMERGENCIA", cantidad=float(venta["executedQty"]), precio=float(vf["price"]),
                  comision=float(vf["commission"]), moneda_comision="USDT")
    return hecho


ESCENARIOS = {
    "no_se_llena": dict(precio=70300.0),
    "stop_puesto_comision_btc": dict(precio=70100.0),
    "stop_puesto_comision_bnb": dict(precio=70100.0, comision=("BNB", 0.075)),
    "stop_rechazado_una_vez": dict(precio=70100.0, rechazar_stops=1),
    "stop_rechazado_y_venta_de_emergencia": dict(precio=70100.0, rechazar_stops=2),
    "stop_rechazado_y_la_venta_tambien_falla": dict(precio=70100.0, rechazar_stops=2, venta_falla=True),
}


@pytest.mark.parametrize("nombre", list(ESCENARIOS))
def test_ningun_camino_deja_una_posicion_sin_stop_y_sin_aviso(compra, capsys, nombre):  # noqa: F811
    r, b, foto = compra
    bn = BinanceSimulado(**ESCENARIOS[nombre])
    hecho = ejecutor(r, b, bn)
    est = RE.cargar_estado(r)
    if nombre == "no_se_llena":
        assert [e for e, _ in hecho] == ["COMPRA_NO_LLENADA"] and est["posiciones"] == []
    elif nombre.startswith("stop_puesto") or nombre == "stop_rechazado_una_vez":
        (p,) = est["posiciones"]
        assert p["estado_stop"] == "ACTIVO"
        _, msgs = hecho[0]
        assert msgs[0].startswith("👍 Compra anotada") and any("SIN STOP" in m for m in msgs)
    elif nombre == "stop_rechazado_y_venta_de_emergencia":
        assert est["posiciones"] == [] and any("COMPRA SIN STOP, VENDIDA A MERCADO" in m for _, ms in hecho for m in ms)
    else:
        (p,) = est["posiciones"]
        assert p["estado_stop"] == "SIN_STOP" and any("COMPRA SIN STOP" in m for _, ms in hecho for m in ms)
    # Al día siguiente: foto de lo que hay en Binance, conciliar y ronda real
    capsys.readouterr()
    cta, ordenes = bn.foto()
    ok, msgs = foto(cta, ordenes, ahora=DIA2 - timedelta(minutes=5))
    assert ok, msgs
    conc = RE.conciliar(r, DIA2 - timedelta(minutes=2))
    correr = lambda: RR.correr(r, DIA2, cliente=object(), memes=[])  # noqa: E731
    assert correr() == 0
    boletos = json.loads(RR.archivo_boletos(r, "2026-11-16").read_text(encoding="utf-8"))
    salida = capsys.readouterr().out
    est = RE.cargar_estado(r)
    urgentes = {x["posicion_id"] for x in boletos if x.get("urgente")}
    for p in est["posiciones"]:                          # la regla: con stop ACTIVO, o cierre urgente y sin compras
        assert p["estado_stop"] == "ACTIVO" or (p["id"] in urgentes and est["bloqueo_compras"]
                                                and salida.startswith("❌ URGENTE"))
    if nombre == "stop_rechazado_y_la_venta_tambien_falla":
        assert conc["sin_stop"] == ["BTC"] and urgentes == {b["boleto_id"]}
        assert not [x for x in boletos if x["accion"] == "COMPRAR"]
    elif est["posiciones"]:
        assert conc["ok"] and not urgentes


def test_si_el_ejecutor_no_anota_la_compra_nadie_compra_y_se_avisa(compra, capsys):  # noqa: F811
    """Si el EJECUTOR compra y se cae antes de anotar nada, el BTC que el estado no conoce frena las compras con ❌."""
    r, b, foto = compra
    bn = BinanceSimulado(70100.0)
    bn.nueva_orden(b["orden_compra"])
    cta, ordenes = bn.foto()
    ok, msgs = foto(cta, ordenes, ahora=DIA2 - timedelta(minutes=5))
    assert not ok and any("que el estado real no conoce" in m for m in msgs)
    capsys.readouterr()
    assert RR.correr(r, DIA2, cliente=object(), memes=[]) == 0
    assert not [x for x in json.loads(RR.archivo_boletos(r, "2026-11-16").read_text(encoding="utf-8"))
                if x["accion"] == "COMPRAR"]
    assert "❌ Sin compras" in capsys.readouterr().out
