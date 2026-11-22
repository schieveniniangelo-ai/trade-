"""Arreglo 204: prueba de integración «día simulado» de punta a punta (SOLO PRUEBAS; no cambia nada del paquete).

Cada pieza del día real ya tenía su prueba, pero ninguna recorría el día completo que pide bots/THE_BOSS.md (el día de
prueba antes de la primera ronda real). Esta lo recorre con los comandos de verdad (`__main__.main` con
`--reglamento` apuntando a una COPIA en la carpeta temporal), sin red ni llaves y con respuestas falsas de Binance:

1. registrar-saldo con una foto falsa de Spot;      6. conciliar --real;
2. ronda --modo real --simular (no escribe nada);   7. ronda --verificar --real;
3. ronda --modo real (saca el boleto de compra);    8. reporte diario y reporte diario --real;
4. registrar-llenado --real con el llenado falso;   9. doctor.
5. registrar-saldo con la foto nueva;

La copia del reglamento tiene M0 en VIVA_MINI y real.activo: true; el reglamento.yaml de verdad no se toca. Se revisa
que no salga ninguna ❌ inesperada, que nada se escriba fuera de la carpeta temporal y que el estado final cuadre con la
foto. El segundo caso apaga el real (real.activo: false) con la posición abierta: solo se frenan las compras; el stop
ejecutado se arma, se verifica y se anota.

La hora: los comandos toman `datetime.now()` (a veces con import dentro de la función), así que la prueba la fija con
una subclase de datetime (como `_Fijo` de test_arreglo91) puesta en el módulo datetime y en los módulos del paquete.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib
import json
import os
import pkgutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

import sobreviviente
from sobreviviente import __main__ as MAIN
from sobreviviente import cli_real
from sobreviviente import datos as D
from sobreviviente import doctor
from sobreviviente import real as RE
from sobreviviente import reglamento as RGL
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, al_dia, cuenta, orden_stop
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture (datos falsos de M0)
from test_arreglo136_llenados_real import Cli

RAIZ = Path(__file__).resolve().parent.parent
REAL_DT = _dt.datetime
FECHA = "2026-11-15"                     # la ronda de las 6:12 p. m. CDMX del domingo 15 nov lleva la vela del 15
FECHA2 = "2026-11-16"
CANT, PRECIO, COMISION_BTC = 0.00013, 70100.0, 0.00000013
USDT_TRAS_COMPRA = 142.54 - CANT * PRECIO
USDT_TRAS_STOP = USDT_TRAS_COMPRA + 0.00012 * 59300.0 - 0.0071
APAGADO = "⛔ El dinero real está APAGADO (real.activo: false en reglamento.yaml, DECISIÓN DE ÁNGELO): "


# ---------------------------------------------------------------------------- hora fija
class _Meta(type):
    def __instancecheck__(cls, obj):                 # un datetime de verdad también «es» datetime para el código
        return isinstance(obj, REAL_DT)


class Reloj(REAL_DT, metaclass=_Meta):
    momento = AHORA

    @classmethod
    def now(cls, tz=None):
        m = cls.momento
        return m.astimezone(tz) if tz is not None else m.astimezone().replace(tzinfo=None)

    @classmethod
    def utcnow(cls):
        return cls.momento.astimezone(_dt.timezone.utc).replace(tzinfo=None)


def _fijar_hora(monkeypatch, momento):
    Reloj.momento = momento
    for info in pkgutil.walk_packages(sobreviviente.__path__, "sobreviviente."):    # todos cargados ANTES de cambiar
        if info.name != "sobreviviente.__main__":
            importlib.import_module(info.name)
    monkeypatch.setattr(_dt, "datetime", Reloj)
    for nombre, mod in list(sys.modules.items()):
        if (nombre == "sobreviviente" or nombre.startswith("sobreviviente.")) and getattr(mod, "datetime", None) is REAL_DT:
            monkeypatch.setattr(mod, "datetime", Reloj)


# ---------------------------------------------------------------------------- huellas (nada fuera de tmp)
def _huella_repo():
    git = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=RAIZ, capture_output=True,
                         text=True, check=False).stdout
    archivos = {}
    for carpeta in ("datos", "salida"):
        for p in (RAIZ / carpeta).rglob("*"):
            if p.is_file():
                st = p.stat()
                archivos[str(p)] = (st.st_size, st.st_mtime_ns)
    return git, archivos, hashlib.sha256((RAIZ / "reglamento.yaml").read_bytes()).hexdigest()


def _huella_tmp(tmp_path):
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in Path(tmp_path).rglob("*") if p.is_file()}


# ---------------------------------------------------------------------------- el mundo falso
def _reglamento(tmp_path, activo=True):
    """Copia PROPIA del reglamento en tmp: M0 en VIVA_MINI, las demás apagadas y real.activo como se pida."""
    datos = yaml.safe_load((RAIZ / "reglamento.yaml").read_text(encoding="utf-8"))
    for k in datos["estrategias"]:
        datos["estrategias"][k]["estado"] = "APAGADA"
    datos["estrategias"]["M0"]["estado"] = "VIVA_MINI"
    datos["real"]["activo"] = activo
    ruta = Path(tmp_path) / "reglamento.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    reg = RGL.cargar(ruta)
    assert Path(reg.get("datos.carpeta", "datos")).is_absolute() is False   # datos/ queda junto a la copia, en tmp
    return ruta, reg


@pytest.fixture
def dia(tmp_path, monkeypatch, capsys, mundo):  # noqa: F811 - mundo: datos falsos de M0 (arreglo 134)
    """(correr, foto, reg_activo, ruta). `correr(*args)` corre el CLI de verdad con la copia del reglamento."""
    _, cfg, _, _ = mundo
    ruta, reg = _reglamento(tmp_path)
    monkeypatch.setattr(cli_real, "precio_publico", lambda r: (lambda s: 70000.0))     # spot.tickerPrice falso
    monkeypatch.setattr(D, "ClienteBinance", Cli)                                       # exchangeInfo falso, sin red
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    _fijar_hora(monkeypatch, AHORA)
    huella = _huella_repo()

    def correr(*args, ruta_reg=ruta):
        capsys.readouterr()
        codigo = MAIN.main(["--reglamento", str(ruta_reg), *args])
        return codigo, capsys.readouterr().out

    def foto(cta, ordenes, momento):
        """EJECUTOR deja getAccount y getOpenOrders en tmp/entrada y corre registrar-saldo (paso 1 y 5)."""
        Reloj.momento = momento
        carpeta = Path(tmp_path) / "entrada"
        carpeta.mkdir(exist_ok=True)
        c, o = carpeta / "cuenta.json", carpeta / "ordenes.json"
        c.write_text(json.dumps(al_dia(cta, momento)), encoding="utf-8")
        o.write_text(json.dumps(list(ordenes)), encoding="utf-8")
        for p in (c, o):
            os.utime(p, (momento.timestamp() - 60, momento.timestamp() - 60))
        return correr("registrar-saldo", "--cuenta", str(c), "--ordenes", str(o))

    yield correr, foto, reg, cfg
    assert _huella_repo() == huella, "algo se escribió fuera de la carpeta temporal"


def _sin_cruces(salida, permitidas=()):
    """Ninguna ❌ inesperada. Los boletos traen la instrucción «si sale ❌, no la mandes»: esa no es una ❌."""
    def cruz(x):
        return "❌" in x.replace("si sale ❌", "").replace("Si sale ❌", "")
    malas = [x for x in salida.splitlines() if cruz(x) and not any(p in x for p in permitidas)]
    assert not malas, malas


def _boletos(reg, fecha):
    return json.loads(RR.archivo_boletos(reg, fecha).read_text(encoding="utf-8"))


def _dia_con_compra(dia, tmp_path):
    """Los pasos 1 a 7 del día: hasta dejar la posición real abierta con su stop. Regresa el boleto."""
    correr, foto, reg, _ = dia
    # 1. registrar-saldo con la foto de Spot de las 6:07 p. m.
    codigo, salida = foto(cuenta(), [], AHORA - timedelta(minutes=5))
    assert codigo == 0 and "👍 Foto de saldo guardada" in salida
    _sin_cruces(salida)
    # 2. ronda --modo real --simular: corre todo y no escribe NADA
    Reloj.momento = AHORA
    antes = _huella_tmp(tmp_path)
    codigo, salida = correr("ronda", "--modo", "real", "--simular")
    assert codigo == 0 and "Boletos REALES que saldrían (simulación: NO se ponen)" in salida
    _sin_cruces(salida)
    assert _huella_tmp(tmp_path) == antes and not RR.archivo_boletos(reg, FECHA).exists()
    # 3. ronda --modo real: sale el boleto de compra
    codigo, salida = correr("ronda", "--modo", "real")
    assert codigo == 0
    _sin_cruces(salida)
    (b,) = _boletos(reg, FECHA)
    assert b["accion"] == "COMPRAR" and b["modo"] == "REAL" and b["orden_compra"]["quantity"] == "0.00013"
    assert b["texto"] in salida
    # (antes de poner la compra, EJECUTOR la verifica: debe salir ✅)
    Reloj.momento = AHORA + timedelta(minutes=1)
    codigo, salida = correr("ronda", "--verificar", "--real")
    assert codigo == 0 and f"✅ {b['boleto_id']}" in salida
    _sin_cruces(salida)
    # 4. registrar-llenado --real: COMPRA_ENVIADA, COMPRA_LLENADA y STOP_PUESTO con lo que contestó Binance (falso)
    Reloj.momento = AHORA + timedelta(minutes=2)
    for evento, extra in (("COMPRA_ENVIADA", ["--precio-actual", "70000"]),
                          ("COMPRA_LLENADA", ["--orden-id", "777", "--cantidad", str(CANT), "--precio", str(PRECIO),
                                              "--comision", f"{COMISION_BTC:.8f}", "--moneda-comision", "BTC"]),
                          ("STOP_PUESTO", ["--orden-id", "888", "--stop-id", b["id_stop"]])):
        codigo, salida = correr("registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", evento, *extra)
        assert codigo == 0, (evento, salida)
        _sin_cruces(salida)
    assert [x["evento"] for x in RE.leer_llenados(reg)] == ["COMPRA_ENVIADA", "COMPRA_LLENADA", "STOP_PUESTO"]
    # 5. registrar-saldo con la foto nueva: el BTC está bloqueado en el stop
    codigo, salida = foto(cuenta(usdt=USDT_TRAS_COMPRA, btc_bloq=0.00012),
                          [orden_stop(client=b["id_stop"], order_id=888)], AHORA + timedelta(minutes=5))
    assert codigo == 0
    _sin_cruces(salida)
    # 6. conciliar --real: cuadra y hace la revisión justo después de la compra
    Reloj.momento = AHORA + timedelta(minutes=6)
    codigo, salida = correr("conciliar", "--real")
    assert codigo == 0 and f"revisión justo después de la compra (boleto {b['boleto_id']}): cuadra" in salida
    _sin_cruces(salida)
    return b


def test_dia_simulado_completo_con_el_real_encendido(dia, tmp_path):
    correr, _, reg, _ = dia
    b = _dia_con_compra(dia, tmp_path)
    # 7. ronda --verificar --real: el boleto ya se anotó, así que lo correcto es que NO se ponga otra vez. Las únicas ❌
    # esperadas son esa y su cuenta; nada más.
    Reloj.momento = AHORA + timedelta(minutes=7)
    codigo, salida = correr("ronda", "--verificar", "--real")
    assert codigo == 1
    assert salida.splitlines() == [f"❌ {b['boleto_id']}: YA REGISTRADO: no lo pongas otra vez",
                                   "❌ 1 boleto(s) real(es) NO se ponen. Avisa a THE BOSS."]
    # 8. reporte diario (papel) y con lo real
    for args in (("reporte", "diario"), ("reporte", "diario", "--real")):
        codigo, salida = correr(*args)
        assert codigo == 0, (args, salida)
        _sin_cruces(salida)
    # 9. doctor: todo en orden y ve la posición real con su stop
    codigo, salida = correr("doctor")
    assert codigo == 0 and "👍 Todo listo." in salida, salida
    assert "posiciones abiertas: BTCUSDT" in salida and "pendientes urgentes: ninguno" in salida
    _sin_cruces(salida)
    # El estado final cuadra con la última foto
    est = RE.cargar_estado(reg)
    (pos,) = est["posiciones"]
    assert pos["simbolo"] == "BTCUSDT" and pos["estado_stop"] == "ACTIVO" and pos["id"] == b["boleto_id"]
    # la neta es lo comprado menos la comisión en BTC, redondeado hacia abajo al paso de Binance (0.00001): 0.00012,
    # justo lo que la última foto tiene de BTC (todo bloqueado en el stop)
    assert pos["cantidad_comprada"] == pytest.approx(CANT) and pos["cantidad_neta"] == pytest.approx(0.00012)
    assert est["bloqueo_compras"] is None and RE.REVISION not in est
    foto_final = json.loads(RE.archivo_saldo(reg).read_text(encoding="utf-8"))
    conc = RE.conciliar(reg, AHORA + timedelta(minutes=8), escribir=False)
    assert conc["ok"] and conc["sin_stop"] == [] and conc["diferencias"] == {}, conc
    assert json.loads(RE.archivo_saldo(reg).read_text(encoding="utf-8")) == foto_final


def test_dia_siguiente_con_el_real_apagado_solo_se_frenan_las_compras(dia, tmp_path):
    correr, foto, reg, cfg = dia
    b = _dia_con_compra(dia, tmp_path)
    ruta_apagado, _ = _reglamento(Path(tmp_path), activo=False)        # misma carpeta: misma posición abierta
    dia2 = AHORA + timedelta(days=1)
    # el stop se ejecutó durante la noche: la foto ya no tiene la orden y solo queda polvo de BTC
    codigo, salida = foto(cuenta(usdt=USDT_TRAS_STOP, btc=0.000009), [], dia2 - timedelta(minutes=5))
    assert codigo == 0
    _sin_cruces(salida)
    Reloj.momento = dia2
    codigo, salida = correr("ronda", "--modo", "real", ruta_reg=ruta_apagado)
    assert codigo == 2 and f"La ronda real NO corre: {APAGADO}" in salida
    (cierre,) = _boletos(reg, FECHA2)                               # nunca sale una compra; sí el cierre que protege
    assert cierre["accion"] == "CERRAR" and cierre["motivo"] == "STOP_EJECUTADO" and "COMPRAR" not in salida
    # comprar sigue frenado…
    codigo, salida = correr("registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_ENVIADA",
                            "--precio-actual", "70000", ruta_reg=ruta_apagado)
    assert codigo == 2 and salida.startswith(f"{APAGADO}registrar-llenado --real no hizo nada")
    # …pero el cierre se verifica y el stop ejecutado se anota
    Reloj.momento = dia2 + timedelta(minutes=1)
    codigo, salida = correr("ronda", "--verificar", "--real", ruta_reg=ruta_apagado)
    assert codigo == 0 and f"✅ {cierre['boleto_id']}" in salida
    _sin_cruces(salida)
    codigo, salida = correr("registrar-llenado", "--real", "--boleto", cierre["boleto_id"], "--evento",
                            "STOP_EJECUTADO", "--cantidad", "0.00012", "--precio", "59300", "--comision", "0.0071",
                            "--moneda-comision", "USDT", ruta_reg=ruta_apagado)
    assert codigo == 0, salida
    _sin_cruces(salida)
    est = RE.cargar_estado(reg)
    assert est["posiciones"] == [] and len(est["cerradas"]) == 1
    assert [x["evento"] for x in RE.leer_llenados(reg)][-1] == "STOP_EJECUTADO"

