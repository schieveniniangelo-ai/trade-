"""Arreglo 150: comando futuros-papel (SOLO PAPEL; con activo: false es modo muestra)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from apoyo_futuros import ClienteFalso, escalones_verificados
from sobreviviente import __main__ as M
from sobreviviente import archivos as AR
from sobreviviente import reglamento as RGL
from sobreviviente import ronda_real
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import datos_publicos as DP


@pytest.fixture
def reg(tmp_path):
    return RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})


def _nada_de_spot(reg):
    datos = AR.carpeta_datos(reg)
    salida = FC.carpeta_salida(reg)
    assert not (datos / "real").exists() and not (datos / "papel").exists()
    assert not list(salida.glob("boletos*")) if salida.exists() else True


def test_modo_muestra_solo_lista_blanca_y_nada_de_spot(reg, capsys):
    antes = ronda_real.compuertas_puerta(reg)
    cli = ClienteFalso(reg)
    assert FC.comando(reg, None, cli) == 0
    texto = capsys.readouterr().out
    assert texto.splitlines()[0] == "🧪 PAPEL DE FUTUROS — no es una orden"
    assert "MUESTRA" in texto and "nada de esto va a EJECUTOR" in texto
    assert cli.urls and all(DP.ruta_permitida(u) for u in cli.urls), [u for u in cli.urls if not DP.ruta_permitida(u)]
    _nada_de_spot(reg)
    assert not C.ruta_estado(reg).exists()                  # modo muestra: no guarda posiciones
    archivos = list(FC.carpeta_salida(reg).glob("futuros_papel_*.json"))
    assert len(archivos) == 1
    out = json.loads(archivos[0].read_text(encoding="utf-8"))
    assert out["solo_papel"] is True and out["no_es_orden"] is True and out["modo"] == "muestra"
    assert out["posiciones"] == [] and out["aperturas"] == []
    assert ronda_real.compuertas_puerta(reg) == antes


def test_si_falla_un_dato_sale_con_codigo_0_y_el_aviso(reg, capsys):
    assert FC.comando(reg, None, ClienteFalso(reg, estado=451)) == 0
    texto = capsys.readouterr().out
    assert "Futuros no disponible" in texto
    _nada_de_spot(reg)


def test_un_error_de_datos_inesperado_tambien_sale_con_0(reg, capsys, monkeypatch):
    def tronar(*a, **k):
        raise FC.D.ErrorDatos("se cayó la red")
    monkeypatch.setattr(FC, "correr", tronar)
    assert FC.comando(reg, None, ClienteFalso(reg)) == 0
    assert "se cayó la red" in capsys.readouterr().out


def test_configuracion_invalida_no_corre(reg, capsys):
    mal = reg.copia_con({"futuros_papel.apalancamiento_tope": 5})
    assert FC.comando(mal, None, ClienteFalso(mal)) == 1
    assert "❌" in capsys.readouterr().out


def test_activo_sin_validacion_que_pase_se_queda_en_muestra(reg, capsys, monkeypatch):
    escalones_verificados(monkeypatch)      # Arreglo 159 (DECISIÓN DE ÁNGELO 2026-11-17)
    activo = reg.copia_con({"futuros_papel.activo": True})
    out = FC.correr(activo, ClienteFalso(activo))
    assert out["modo"] == "muestra" and any("no dice «PASA»" in a for a in out["avisos"])
    assert not C.ruta_estado(activo).exists()


def test_activo_y_validado_guarda_su_estado_y_procesa_en_orden(reg, monkeypatch):
    escalones_verificados(monkeypatch)      # Arreglo 159 (DECISIÓN DE ÁNGELO 2026-11-17)
    activo = reg.copia_con({"futuros_papel.activo": True})
    monkeypatch.setattr(FC, "validacion_pasa", lambda r: True)
    cfg = config.leer(activo)
    cli = ClienteFalso(activo)
    # Estado con una posición abierta en SOL hace 3 velas, con el stop muy lejos: vive las velas nuevas y paga funding
    datos = DP.cargar(cli, cfg)
    v = datos.velas["SOLUSDT"]
    est = C.estado_nuevo(cfg)
    t = C.T.Tamano(True, "cabe", 0.1, 7.0, 1, 7.0, 0.3, 0.4254, None)
    precio = float(v["close"].iloc[-4])
    pos = C.abrir(est, "SOLUSDT", "LARGO", precio, precio, precio * 0.5, t, datetime.now(timezone.utc),
                  FC.F1.gestion(FC.F1.POR_DEFECTO), 0.05)
    pos["vela_abierta"] = v.index[-3].isoformat()
    est["ultima_vela"] = v.index[-4].isoformat()
    C.guardar_estado(activo, est)
    out = FC.correr(activo, cli)
    assert out["modo"] == "papel"
    guardado = C.cargar_estado(activo, cfg)
    assert guardado["ultima_vela"] == v.index[-1].isoformat()
    p = [x for x in guardado["posiciones"] if x["simbolo"] == "SOLUSDT"] + \
        [x for x in guardado["cerradas"] if x["simbolo"] == "SOLUSDT"]
    assert p and p[0]["funding"] < 0                       # el largo pagó el funding positivo
    _nada_de_spot(activo)
    # Otra corrida con los mismos datos: no hay velas nuevas, nada se procesa dos veces
    out2 = FC.correr(activo, cli)
    assert out2["senales"] == [] and out2["cierres"] == []


def test_estado_danado_no_corre(reg, monkeypatch):
    escalones_verificados(monkeypatch)      # Arreglo 159 (DECISIÓN DE ÁNGELO 2026-11-17)
    activo = reg.copia_con({"futuros_papel.activo": True})
    monkeypatch.setattr(FC, "validacion_pasa", lambda r: True)
    arch = C.ruta_estado(activo)
    arch.parent.mkdir(parents=True)
    arch.write_text("{roto", encoding="utf-8")
    out = FC.correr(activo, ClienteFalso(activo))
    assert any("F1 no corre hoy" in a for a in out["avisos"])


def test_validacion_pasa_lee_el_veredicto(tmp_path):
    (tmp_path / "reglamento.yaml").write_text((M.RAIZ / "reglamento.yaml").read_text(encoding="utf-8"),
                                              encoding="utf-8")
    reg = RGL.cargar(tmp_path / "reglamento.yaml")
    assert not FC.validacion_pasa(reg)
    (tmp_path / "VALIDACION_FUTUROS.md").write_text("**Veredicto: F1 NO PASA.**", encoding="utf-8")
    assert not FC.validacion_pasa(reg)
    (tmp_path / "VALIDACION_FUTUROS.md").write_text("**Veredicto: F1 PASA.**", encoding="utf-8")
    assert FC.validacion_pasa(reg)


def test_resumen_con_senales_y_cierres():
    out = {"modo": "muestra", "fecha": "2026-11-17", "capital": 42.54, "posiciones": [], "avisos": ["ojo"],
           "senales": [{"simbolo": "SOLUSDT", "lado": "LARGO", "precio": 71.63, "stop": 68.0, "stop_pct": 5.0,
                        "cabe": True, "razon": "cabe", "cantidad": 0.11, "apalancamiento": 1, "bloqueos": []},
                       {"simbolo": "XRPUSDT", "lado": "CORTO", "precio": 1.0, "stop": 1.05, "stop_pct": 5.0,
                        "cabe": False, "razon": "no cabe: x", "cantidad": 0, "apalancamiento": 0,
                        "bloqueos": ["veto"]}],
           "cierres": [{"simbolo": "BNBUSDT", "lado": "LARGO", "motivo": "stop", "ganancia_usdt": -0.4}]}
    L = FC.resumen(out)
    assert L[0] == FC.ENCABEZADO and any("0.11 a 1x" in x for x in L) and any("no cabe: x" in x for x in L)
    assert any("bloqueada: veto" in x for x in L) and any("Cierre BNBUSDT" in x for x in L) and L[-1] == "ojo"


def test_registrado_en_main_junto_a_futuros_capital_y_fuera_de_ronda_y_real(capsys):
    with pytest.raises(SystemExit):
        M.main(["--help"])
    ayuda = capsys.readouterr().out
    assert "futuros-papel" in ayuda and "futuros-capital" in ayuda
    fuente = (M.RAIZ / "sobreviviente" / "__main__.py").read_text(encoding="utf-8")
    assert fuente.index("futuros-capital") < fuente.index("futuros_cli.registrar") < fuente.index("cli_ronda.registrar")
    for nombre in ("cli_ronda.py", "cli_real.py", "ronda_real.py"):
        assert "futuros-papel" not in (M.RAIZ / "sobreviviente" / nombre).read_text(encoding="utf-8")


def _forzar_senal(monkeypatch, simbolo="SOLUSDT", lado="LARGO"):
    """Señal forzada en la penúltima vela de `simbolo` (la señal de verdad casi nunca cae en las últimas 24 h)."""
    real = FC.F1.senales

    def senales(ctx, p):
        s = real(ctx, p)
        if ctx.simbolo == simbolo:
            k = s.index[-2]
            s.loc[k, "entrada"], s.loc[k, "lado"] = True, lado
            s.loc[k, "stop"] = s.loc[k, "precio"] * (0.95 if lado == "LARGO" else 1.05)
            s.loc[k, "stop_pct"] = 5.0
        return s
    monkeypatch.setattr(FC.F1, "senales", senales)


def test_muestra_ensena_senal_tamano_y_si_cabe(reg, monkeypatch):
    _forzar_senal(monkeypatch)
    out = FC.correr(reg, ClienteFalso(reg))
    f = [x for x in out["senales"] if x["simbolo"] == "SOLUSDT"]
    assert f and f[0]["cabe"] is True and f[0]["apalancamiento"] == 1 and f[0]["cantidad"] > 0
    assert f[0]["bloqueos"] == [] and out["aperturas"] == []        # muestra: no abre nada


def test_poco_volumen_bloquea_la_entrada(reg, monkeypatch):
    _forzar_senal(monkeypatch, lado="CORTO")
    out = FC.correr(reg, ClienteFalso(reg, volumen_dia=5e7))
    f = [x for x in out["senales"] if x["simbolo"] == "SOLUSDT"][0]
    assert any("volumen mediano" in b for b in f["bloqueos"])


def test_activo_y_validado_abre_en_la_apertura_siguiente(reg, monkeypatch):
    escalones_verificados(monkeypatch)      # Arreglo 159 (DECISIÓN DE ÁNGELO 2026-11-17)
    activo = reg.copia_con({"futuros_papel.activo": True})
    monkeypatch.setattr(FC, "validacion_pasa", lambda r: True)
    _forzar_senal(monkeypatch)
    out = FC.correr(activo, ClienteFalso(activo))
    assert out["modo"] == "papel" and len(out["aperturas"]) == 1
    a = out["aperturas"][0]
    assert a["simbolo"] == "SOLUSDT" and a["lado"] == "LARGO" and a["apalancamiento"] == 1
    est = C.cargar_estado(activo, config.leer(activo))
    assert len(est["posiciones"]) == 1 and est["capital"] < 42.54           # pagó la comisión de entrada
    _nada_de_spot(activo)
