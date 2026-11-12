"""Arreglo 47: pruebas de conciliar, del ensayo del Ejecutor (registrar-llenado) y del estado/calificación de bots."""
import json
from argparse import Namespace

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    return r


def _conciliacion(tmp_path):
    return json.loads((tmp_path / "datos" / "papel" / "conciliacion.json").read_text(encoding="utf-8"))


# ---------------- conciliar ----------------

def test_conciliar_con_posicion_abierta_y_operacion_cerrada_cuadra(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    est = P.estado_nuevo("A", 46.18, "2026-11-01")
    est["cerradas"] = [{"ganancia_usdt": 1.50}, {"ganancia_usdt": -0.40}]            # +1.10 ya cobrados
    est["posiciones"] = [{"simbolo": "BTCUSDT", "costo_total": 13.86}]               # 13.86 metidos en BTC
    est["efectivo"] = 46.18 + 1.10 - 13.86
    P.guardar_estado(r, est)
    assert CR.conciliar(r) == 0
    salida = capsys.readouterr().out
    assert "✅ Cartera A: diferencia +0.0000 USDT" in salida and "👍 Las cuentas cuadran." in salida
    c = _conciliacion(tmp_path)
    assert c["ok"] is True and c["diferencias"] == {"A": 0.0, "B": 0.0, "C": 0.0}
    assert AR.leer_registro(r)[-1]["bot"] == "CONTADOR" and AR.leer_registro(r)[-1]["ok"] is True


def test_conciliar_respeta_la_tolerancia(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    assert r.get("conciliacion.tolerancia_usdt") == 0.10
    est = P.estado_nuevo("B", 46.18, "2026-11-01")
    est["efectivo"] = 46.18 + 0.09                                                   # dentro de la tolerancia
    P.guardar_estado(r, est)
    assert CR.conciliar(r) == 0 and _conciliacion(tmp_path)["ok"] is True
    est["efectivo"] = 46.18 - 0.11                                                   # fuera (faltan 11 centavos)
    P.guardar_estado(r, est)
    assert CR.conciliar(r) == 1
    salida = capsys.readouterr().out
    assert "❌ Cartera B: diferencia -0.1100 USDT" in salida and "❌ No cuadra: PAUSA hasta revisar" in salida
    c = _conciliacion(tmp_path)
    assert c["ok"] is False and c["diferencias"]["B"] == -0.11 and c["diferencias"]["A"] == 0.0
    assert P.conciliacion_ok(r) is False                                             # la ronda lo respeta: no abre nada
    assert AR.leer_registro(r)[-1]["ok"] is False


def test_conciliacion_rota_cuenta_como_que_no_cuadra(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    assert P.conciliacion_ok(r) is True                                              # todavía no existe: no estorba
    (tmp_path / "datos" / "papel" / "conciliacion.json").write_text("{dañado", encoding="utf-8")
    assert P.conciliacion_ok(r) is False                                             # por seguridad


# ---------------- registrar-llenado --ensayo ----------------

BOLETO = {"boleto_id": "20261109-C-COM-BTC-abc12345", "accion": "COMPRAR", "simbolo": "BTCUSDT", "cantidad": 0.00018,
          "precio_entrada": 75000.0, "stop": 63750.0}


def _ensayo(reg, tmp_path, monkeypatch, **kw):
    r = _reg_tmp(reg, tmp_path) if not (tmp_path / "datos" / "papel").exists() else reg
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    monkeypatch.setattr(CR, "RAIZ", tmp_path)
    (tmp_path / "salida").mkdir(exist_ok=True)
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text(json.dumps([BOLETO]), encoding="utf-8")
    args = {"boleto": BOLETO["boleto_id"], "ensayo": True, "simbolo": None, "cantidad": None, "precio": None, "stop": None,
            "bot": "EJECUTOR", "reglamento": None}
    args.update(kw)
    return r, CR.cmd_registrar_llenado(Namespace(**args))


def test_ensayo_copiado_igualito(reg, tmp_path, monkeypatch, capsys):
    r, codigo = _ensayo(reg, tmp_path, monkeypatch, simbolo="btcusdt", cantidad=0.00018, precio=75000.0, stop=63750.0)
    assert codigo == 0 and "👍 Copiado igualito al boleto." in capsys.readouterr().out
    fila = AR.leer_registro(r)[-1]
    assert fila["bot"] == "EJECUTOR" and fila["ok"] is True and fila["diferencias"] == 0


def test_ensayo_con_diferencias_las_dice_todas(reg, tmp_path, monkeypatch, capsys):
    r, codigo = _ensayo(reg, tmp_path, monkeypatch, simbolo="ETHUSDT", cantidad=0.0018, precio=75200.0, stop=63000.0)
    salida = capsys.readouterr().out
    assert codigo == 1 and "⚠️ Diferencias con el boleto" in salida and "el boleto se copia exacto" in salida
    for parte in ("moneda ETHUSDT en vez de BTCUSDT", "cantidad 0.0018 en vez de 0.00018",
                  "precio 75200.0 en vez de 75000.0", "stop 63000.0 en vez de 63750.0"):
        assert parte in salida
    assert AR.leer_registro(r)[-1]["diferencias"] == 4
    assert AR.calificacion_bots(r, 1)["EJECUTOR"]["diferencias"] == 4


def test_ensayo_tolera_un_precio_casi_igual(reg, tmp_path, monkeypatch, capsys):
    _, codigo = _ensayo(reg, tmp_path, monkeypatch, precio=75050.0)                  # 0.07 % de diferencia: vale
    assert codigo == 0
    _, codigo = _ensayo(reg, tmp_path, monkeypatch, precio=75100.0)                  # 0.13 %: ya no
    assert codigo == 1


def test_ensayo_boleto_o_archivo_que_no_existe(reg, tmp_path, monkeypatch, capsys):
    r, codigo = _ensayo(reg, tmp_path, monkeypatch, boleto="20261109-C-COM-ETH-noexiste")
    assert codigo == 1 and "❌ No existe el boleto 20261109-C-COM-ETH-noexiste." in capsys.readouterr().out
    _, codigo = _ensayo(r, tmp_path, monkeypatch, boleto="20251231-C-COM-BTC-abc12345")
    assert codigo == 1 and "❌ No encuentro el archivo de boletos de ese día (boletos_2025-12-31.json)." in capsys.readouterr().out
    assert [f["ok"] for f in AR.leer_registro(r)] == [False, False]


def test_sin_ensayo_no_se_registra_nada(reg, tmp_path, monkeypatch, capsys):
    r, codigo = _ensayo(reg, tmp_path, monkeypatch, ensayo=False)
    assert codigo == 2 and "solo se opera en papel: usa --ensayo" in capsys.readouterr().out
    assert AR.leer_registro(r) == []


# ---------------- estado ----------------

def test_estado_muestra_carteras_y_motores(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    for k in r.estrategias:
        r.datos["estrategias"][k]["estado"] = "APAGADA"
    est = P.estado_nuevo("C", 46.18, "2026-11-01")
    est.update(curva={"2026-11-10": 47.25}, posiciones=[{"simbolo": "BTCUSDT"}], cerradas=[{}, {}],
               saltadas_capital=[{}, {}, {}])
    P.guardar_estado(r, est)
    assert CR.mostrar_estado(r) == 0
    salida = capsys.readouterr().out
    assert "Cartera A: 46.18 USDT · 0 abiertas · 0 cerradas · 0 señales saltadas por capital" in salida
    assert "Cartera C: 47.25 USDT · 1 abiertas · 2 cerradas · 3 señales saltadas por capital" in salida
    assert "Motores encendidos: ninguno (todo APAGADO)" in salida
    r.datos["estrategias"]["M0"]["estado"] = "PAPEL"
    CR.mostrar_estado(r)
    assert "Motores encendidos: M0" in capsys.readouterr().out


def test_estado_bots_califica_tareas_a_tiempo_y_rechazos(reg, tmp_path, capsys):
    r = _reg_tmp(reg, tmp_path)
    assert CR.mostrar_estado(r, bots=True) == 0
    assert "Todavía no hay tareas registradas de los bots." in capsys.readouterr().out
    AR.registrar_tarea(r, "THE BOSS", "ronda", True, "0 boletos")
    AR.registrar_tarea(r, "THE BOSS", "ronda", True, "0 boletos; fuera_de_hora", a_tiempo=False)
    AR.registrar_tarea(r, "THE BOSS", "ronda", True, "ya existía")                   # ronda repetida: no cuenta
    AR.registrar_tarea(r, "CENTINELA", "vetos.json", False, "veto mal escrito")
    assert CR.mostrar_estado(r, bots=True, dias=7) == 0
    salida = capsys.readouterr().out
    assert "Calificación de los bots (últimos 7 días):" in salida
    assert "THE BOSS: 2 tareas, 50 % bien y a tiempo, 0 archivos rechazados, 0 diferencias boleto/llenado" in salida
    assert "CENTINELA: 1 tareas, sin medir, 1 archivos rechazados, 0 diferencias boleto/llenado" in salida


def test_registro_con_renglones_rotos_no_tumba_la_calificacion(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    AR.registrar_tarea(r, "RADAR", "verificar", True)
    arch = tmp_path / "datos" / "bots" / "registro.jsonl"
    with open(arch, "a", encoding="utf-8") as f:
        f.write("{roto" + chr(10) + json.dumps({"bot": "RADAR", "cuando": "no es fecha"}) + chr(10))
    AR.registrar_tarea(r, "RADAR", "verificar", True)
    assert AR.calificacion_bots(r, 7)["RADAR"]["tareas"] == 2
