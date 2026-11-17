"""Arreglo 170: anotar la compra ANTES de mandarla (COMPRA_ENVIADA).

Antes, COMPRA_LLENADA se registraba hasta después del stop: si el EJECUTOR se caía entre la compra y el registro, el
estado real no sabía que había BTC. Ahora el EJECUTOR registra COMPRA_ENVIADA ANTES de mandar la compra, y
`conciliar --real`:
* si encuentra un COMPRA_ENVIADA sin COMPRA_LLENADA, COMPRA_PARCIAL ni COMPRA_NO_LLENADA (aunque no haya foto de saldo), o
* BTC en el saldo que el estado real no conoce (la foto fresca lo trae en `sin_estado`),
marca SIN STOP, bloquea las compras (solo Ángelo las reanuda) y da un aviso claro para THE BOSS: poner stop o vender.
El código NO vende solo: no inventa posiciones ni emite boletos de venta. Una compra que ya ocurrió se anota aunque
falte COMPRA_ENVIADA (con un aviso): nunca se rechaza anotar lo que pasó en Binance.
"""
import json
from datetime import timedelta
from pathlib import Path

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_real
from sobreviviente import real as RE
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import Cli, compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
DIA2 = AHORA + timedelta(days=1)
ENVIADA = "COMPRA_ENVIADA"


def _llenar(r, b, evento, minutos=1, **kw):
    return RE.registrar_llenado(r, b["boleto_id"], evento, ahora=AHORA + timedelta(minutes=minutos), **kw)


def _lineas(res):
    return [t for _, t in res["lineas"]]


def test_compra_enviada_se_anota_antes_y_no_cambia_posiciones(compra):
    r, b, _ = compra
    ok, msgs = _llenar(r, b, ENVIADA)
    assert ok and msgs[0].startswith(f"👍 Compra ENVIADA anotada ({b['boleto_id']}). Ahora sí manda la compra")
    assert any("conciliar --real cuenta esta compra SIN STOP" in m for m in msgs)
    assert RE.cargar_estado(r)["posiciones"] == []
    assert [x["evento"] for x in RE.leer_llenados(r)] == [ENVIADA]
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", 2, orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013,
                       moneda_comision="BTC")
    assert ok and msgs[0].startswith("👍 Compra anotada") and not any("COMPRA_ENVIADA" in m for m in msgs)
    assert _llenar(r, b, "STOP_PUESTO", 2, orden_id=888, stop_id=b["id_stop"])[0]
    assert [x["evento"] for x in RE.leer_llenados(r)] == [ENVIADA, "COMPRA_LLENADA", "STOP_PUESTO"]


def test_rechazos_de_compra_enviada(compra):
    r, b, _ = compra
    assert _llenar(r, b, ENVIADA)[0]
    assert "ya está registrado" in _llenar(r, b, ENVIADA)[1][0]
    pos = {**b, "id": b["boleto_id"], "cantidad_neta": 0.00012, "paso_cantidad": 0.00001, "orden_id_stop": None}
    cierre = RE.boleto_cierre_real(r, "2026-11-20", pos, "SIN_STOP")
    RR.archivo_boletos(r, "2026-11-20").write_text(json.dumps([cierre]), encoding="utf-8")
    ok, msgs = RE.registrar_llenado(r, cierre["boleto_id"], ENVIADA)
    assert not ok and "no es de compra" in msgs[0]
    assert [x["evento"] for x in RE.leer_llenados(r)] == [ENVIADA]          # lo rechazado no se anota


def test_compra_enviada_despues_de_la_compra_es_fuera_de_orden(compra):
    r, b, _ = compra
    ok, msgs = _llenar(r, b, "COMPRA_NO_LLENADA")
    assert ok and msgs[0].startswith("👍 Anotado: la compra no se llenó")
    ok, msgs = _llenar(r, b, ENVIADA, 2)
    assert not ok and "ya está registrada" in msgs[0] and "ANTES" in msgs[0]


def test_la_compra_sin_enviada_se_anota_igual_y_avisa(compra):
    r, b, _ = compra
    ok, msgs = _llenar(r, b, "COMPRA_LLENADA", cantidad=0.00013, precio=70000.0, comision=0.00000013,
                       moneda_comision="BTC")
    assert ok and msgs[0].startswith("👍 Compra anotada")            # lo que pasó en Binance nunca se rechaza
    assert msgs[-1].startswith("⚠️ No se anotó COMPRA_ENVIADA antes de mandar esta compra")
    assert len(RE.cargar_estado(r)["posiciones"]) == 1


def test_verificar_dice_ya_registrado_despues_de_enviada(compra, capsys):
    r, b, _ = compra
    _llenar(r, b, ENVIADA)
    capsys.readouterr()
    assert cli_real.verificar_real(r, "2026-11-15", AHORA + timedelta(minutes=2), Cli()) == 1
    assert f"❌ {b['boleto_id']}: YA REGISTRADO" in capsys.readouterr().out          # no se manda dos veces


def test_compra_enviada_sin_resultado_marca_sin_stop_bloquea_y_no_vende(compra, capsys):
    r, b, foto = compra
    _llenar(r, b, ENVIADA)
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=5))
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    bid = b["boleto_id"]
    assert not res["ok"] and res["sin_stop"] == ["BTC"] and res["diferencias"]["compra_sin_anotar"] == [bid]
    linea = next(t for t in _lineas(res) if t.startswith("SIN STOP: BTC — "))
    assert f"la compra del boleto {bid} se mandó (COMPRA_ENVIADA" in linea and "COMPRA_NO_LLENADA" in linea
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"]["motivo"] == f"SIN STOP: BTC (compra enviada sin anotar, boleto {bid})"
    assert est["posiciones"] == []                                     # no se inventa una posición
    # La ronda de mañana: con señal de compra, no compra y tampoco manda vender nada
    foto(cuenta(), [], ahora=DIA2 - timedelta(minutes=5))
    capsys.readouterr()
    assert RR.correr(r, DIA2, cliente=object(), memes=[]) == 0
    assert json.loads(RR.archivo_boletos(r, "2026-11-16").read_text(encoding="utf-8")) == []
    assert "compras bloqueadas por SIN STOP: BTC (compra enviada sin anotar" in capsys.readouterr().out


def test_sin_foto_fresca_tambien_marca(compra):
    r, b, _ = compra
    _llenar(r, b, ENVIADA)
    res = RE.conciliar(r, AHORA + timedelta(hours=3))                 # la foto ya está vieja
    assert not res["ok"] and res["sin_stop"] == ["BTC"]
    assert any("foto de saldo tiene" in e for e in res["errores"])
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"].startswith("SIN STOP: BTC (compra enviada sin anotar")


def test_con_el_resultado_anotado_ya_no_marca(compra):
    r, b, foto = compra
    assert _llenar(r, b, ENVIADA)[0]
    _llenar(r, b, "COMPRA_LLENADA", 2, orden_id=777, cantidad=0.00013, precio=70100.0, comision=0.00000013,
            moneda_comision="BTC")
    _llenar(r, b, "STOP_PUESTO", 2, orden_id=888, stop_id=b["id_stop"])
    foto(cuenta(usdt=142.54 - 0.00013 * 70100, btc_bloq=0.00012), [orden_stop(client=b["id_stop"], order_id=888)],
         ahora=AHORA + timedelta(minutes=5))
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    assert res["ok"] and res["sin_stop"] == [] and RE.cargar_estado(r)["bloqueo_compras"] is None


def test_enviada_y_no_llenada_cuadra(compra):
    r, b, foto = compra
    assert _llenar(r, b, ENVIADA)[0]
    _llenar(r, b, "COMPRA_NO_LLENADA", 2)
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=5))
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    assert res["ok"] and res["sin_stop"] == [] and RE.cargar_estado(r)["bloqueo_compras"] is None


def test_btc_en_la_cuenta_que_el_estado_no_conoce_marca_sin_stop_y_bloquea(compra):
    r, b, foto = compra
    ok, msgs = foto(cuenta(btc=0.00013), [], ahora=AHORA + timedelta(minutes=5))
    assert not ok and any("que el estado real no conoce" in m for m in msgs)
    assert json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))["sin_estado"] == {"BTC": 0.00013}
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    assert not res["ok"] and res["sin_stop"] == ["BTC"] and res["diferencias"]["sin_estado"] == {"BTC": 0.00013}
    assert "SIN STOP: BTC — hay 0.00013 BTC en Binance que el estado real no conoce (no tiene stop anotado)" in \
        _lineas(res)
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"]["motivo"] == "SIN STOP: BTC en la cuenta que el estado real no conoce"
    assert est["posiciones"] == []


def test_compra_enviada_de_un_boleto_que_ya_no_se_encuentra_tambien_marca(compra):
    r, b, _ = compra
    arch = RE.archivo_llenados(r)
    arch.parent.mkdir(parents=True, exist_ok=True)
    with open(arch, "a", encoding="utf-8") as f:            # renglones que ya no tienen su boleto en salida/
        f.write(json.dumps({"evento": ENVIADA, "boleto_id": "20261115-RA-COM-ETH-1234abcd"}) + "\n")
        f.write(json.dumps({"evento": ENVIADA, "boleto_id": "raro"}) + "\n")
    res = RE.conciliar(r, AHORA + timedelta(minutes=6))
    assert not res["ok"] and res["sin_stop"] == ["ETH", "?"]
    assert any(t.startswith("SIN STOP: ETH — la compra del boleto 20261115-RA-COM-ETH-1234abcd se mandó "
                            "(COMPRA_ENVIADA, sin hora)") for t in _lineas(res))
    assert RE.cargar_estado(r)["bloqueo_compras"]["motivo"].startswith("SIN STOP: ETH (compra enviada sin anotar")


def test_el_btc_que_ya_se_anoto_no_sale_como_desconocido(compra):
    r, b, foto = compra
    foto(cuenta(btc=0.00013), [], ahora=AHORA + timedelta(minutes=5))     # el EJECUTOR se cayó antes de anotar
    assert _llenar(r, b, "COMPRA_LLENADA", 6, cantidad=0.00013, precio=70000.0, comision=0.0, moneda_comision="BNB")[0]
    res = RE.conciliar(r, AHORA + timedelta(minutes=7))
    assert not res["ok"]                                              # la foto salió con ❌: hay que repetirla
    assert "sin_estado" not in res["diferencias"] and res["sin_anotar"] == []
    assert not any("que el estado real no conoce (no tiene stop anotado)" in t for t in _lineas(res))


def test_polvo_o_foto_vieja_no_marcan(compra):
    r, b, foto = compra
    ok, msgs = foto(cuenta(btc=0.000001), [], ahora=AHORA + timedelta(minutes=5))       # unos 0.07 USDT: polvo
    assert ok and "sin_estado" not in json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))
    assert RE.conciliar(r, AHORA + timedelta(minutes=6))["sin_stop"] == []
    foto(cuenta(btc=0.00013), [], ahora=AHORA + timedelta(minutes=7))
    res = RE.conciliar(r, AHORA + timedelta(hours=4))                 # foto vieja: no se juzga con ella
    assert not res["ok"] and res["sin_stop"] == [] and RE.cargar_estado(r)["bloqueo_compras"] is None


def test_simulando_no_escribe(compra):
    r, b, foto = compra
    _llenar(r, b, ENVIADA)
    antes = RE.archivo_conciliacion(r).read_bytes()
    res = RE.conciliar(r, AHORA + timedelta(minutes=6), escribir=False)
    assert res["sin_stop"] == ["BTC"] and not res["ok"]
    assert RE.cargar_estado(r)["bloqueo_compras"] is None and RE.archivo_conciliacion(r).read_bytes() == antes


def test_el_aviso_para_the_boss_sale_primero(compra, monkeypatch, capsys):
    r, b, _ = compra
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", ENVIADA]) == 0
    capsys.readouterr()
    assert cli_real.conciliar_real(r) == 1
    salida = capsys.readouterr().out.splitlines()
    assert salida[0] == ("❌ URGENTE para THE BOSS, prioridad máxima: puede haber BTC SIN STOP en Binance que el estado "
                         "real no tiene anotado. Avisa a Ángelo YA: en Binance hay que ponerle stop a ese BTC o venderlo "
                         "a mercado (lo decide él). El programa NO vende solo. Después se anota lo que pasó con "
                         "registrar-llenado --real. Las compras reales quedan bloqueadas hasta que Ángelo las reanude "
                         "(reanudar --cartera REAL).")
    assert salida[1].startswith("❌ SIN STOP: BTC — la compra del boleto")
    assert salida[-1].startswith("❌ Lo real NO cuadra")


def test_textos_del_boleto_del_ejecutor_y_del_contador(compra):
    r, b, _ = compra
    assert b["antes_de_comprar"].startswith(f"registrar-llenado --real --boleto {b['boleto_id']} --evento COMPRA_ENVIADA")
    t = b["texto"]
    assert t.index("No compres si") < t.index("registra COMPRA_ENVIADA") < t.index("HUECO SIN STOP") \
        < t.index("registra COMPRA_LLENADA")
    assert "si sale ❌, no la mandes" in t
    ej = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    paso4 = ej[ej.index("4. Boleto de COMPRA"):ej.index("5. Boleto de CIERRE")]
    assert paso4.index("tickerPrice") < paso4.index("--evento COMPRA_ENVIADA") \
        < paso4.index("copiando campo por campo `orden_compra`")
    assert "NO mandes la compra" in paso4
    co = (RAIZ / "bots" / "5_CONTADOR_REAL.md").read_text(encoding="utf-8")
    assert "👍 del EJECUTOR" in co and "COMPRA_ENVIADA" in co
