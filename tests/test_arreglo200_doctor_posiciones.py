"""Arreglo 200: doctor dice las posiciones reales abiertas y los pendientes urgentes; el texto del EJECUTOR real dice qué
comandos siguen con `real.activo: false` y por qué.

doctor agrega dos renglones (solo informan, no cuentan como ❌): «posiciones abiertas» (símbolo, cantidad y estado del
stop, o «ninguna») y «pendientes urgentes» (COMPRA_ENVIADA sin resultado, la REVISION después de una compra y el
bloqueo_compras, o «ninguno»). Con el estado real dañado lo dice con ⚠️. No usan red."""
from datetime import timedelta
from pathlib import Path

from sobreviviente import doctor
from sobreviviente import real as RE

from apoyo_real import AHORA, reg_real
from test_arreglo131_conciliar_real import POS
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent


def _doctor(r, monkeypatch):
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    salida = []
    return doctor.revisar(r, imprimir=salida.append), salida


def test_sin_nada_real(tmp_path, monkeypatch):
    codigo, salida = _doctor(reg_real(tmp_path), monkeypatch)
    assert "ℹ️ Real: posiciones abiertas: ninguna" in salida and "ℹ️ Real: pendientes urgentes: ninguno" in salida
    assert codigo == 0


def test_con_posicion_y_pendientes(compra, monkeypatch):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    est = RE.cargar_estado(r)
    est["posiciones"] = [{**POS, "estado_stop": "SIN_STOP"}]
    est[RE.REVISION] = {"boleto": "20261114-RA-COM-BTC-abcd1234", "desde": AHORA.isoformat()}
    est["bloqueo_compras"] = {"desde": AHORA.isoformat(), "motivo": "SIN STOP: BTC"}
    RE.guardar_estado(r, est)
    codigo, salida = _doctor(r, monkeypatch)
    assert "ℹ️ Real: posiciones abiertas: BTCUSDT 0.00012 (stop SIN_STOP)" in salida
    assert (f"⚠️ Real: pendientes urgentes: COMPRA_ENVIADA sin resultado (boleto {b['boleto_id']}); REVISION después de "
            f"la compra del boleto 20261114-RA-COM-BTC-abcd1234 sin hacer; bloqueo_compras: SIN STOP: BTC → avisa a THE "
            f"BOSS") in salida
    assert not any(x.startswith("❌ Real") for x in salida)       # solo informa


def test_estado_danado(tmp_path):
    r = reg_real(tmp_path)
    RE.archivo_estado(r).parent.mkdir(parents=True)
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    (linea,) = doctor.renglones_posiciones_y_pendientes(r)
    assert linea.startswith("⚠️ Real: no pude leer el estado real para ver posiciones y pendientes (")


def test_llenados_que_no_se_leen(tmp_path, monkeypatch):
    r = reg_real(tmp_path)

    def falla(reg):
        raise OSError("sin permiso")
    monkeypatch.setattr(RE, "compras_sin_anotar", falla)
    assert doctor.renglones_posiciones_y_pendientes(r)[1] == ("⚠️ Real: pendientes urgentes: COMPRA_ENVIADA sin resultado "
                                                             "(boleto no pude leer llenados.jsonl (OSError)) → avisa a "
                                                             "THE BOSS")


def test_el_texto_del_ejecutor_dice_que_sigue_con_el_real_apagado():
    t = (RAIZ / "bots" / "4_EJECUTOR_REAL.md").read_text(encoding="utf-8")
    seccion = t[t.index("Con el dinero real APAGADO (`real.activo: false`"):t.index("\nNunca\n")]
    for cosa in ("`ronda --modo real`", "`ronda --verificar --real`", "`registrar-llenado --real`", "STOP_PUESTO",
                 "STOP_EJECUTADO", "VENTA_ENVIADA", "VENTA_LLENADA", "VENTA_NO_LLENADA", "CIERRE_DE_EMERGENCIA",
                 "COMPRA_ENVIADA", "`registrar-saldo`", "`conciliar --real`", "`doctor`", "por qué"):
        assert cosa in seccion, cosa
