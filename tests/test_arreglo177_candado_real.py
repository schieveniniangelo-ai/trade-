"""Arreglo 177: registrar-llenado --real, conciliar --real y registrar-saldo usan el MISMO candado que la ronda real.

Antes solo la ronda real tomaba datos/real/ronda.lock (ronda_real.correr). Si el EJECUTOR anotaba un llenado mientras la
ronda real (o un conciliar, o una foto de saldo) leía y guardaba cartera_REAL.json, uno podía pisar lo del otro. Ahora
los tres comandos toman el mismo candado: si otro proceso lo tiene, el segundo espera; si no lo suelta a tiempo
(`real.espera_candado_s`, 120 s si el reglamento no lo dice), sale con ❌ y no hace nada.
"""
import json
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_real
from sobreviviente import real as RE

from apoyo_real import AHORA, escribir_entrada
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
TOMAR = """
import sys, time
from pathlib import Path
from sobreviviente import cli_ronda as CR
carpeta, segundos = Path(sys.argv[1]), float(sys.argv[2])
with CR.candado_ronda(None, espera_s=5, carpeta=carpeta):
    (carpeta / "tomado.txt").write_text("si", encoding="utf-8")
    time.sleep(segundos)
"""


@pytest.fixture
def otro_proceso(tmp_path):
    """Otro proceso (como la ronda real) toma datos/real/ronda.lock durante `segundos`."""
    procesos = []

    def tomar(r, segundos):
        carpeta = RE.ruta_real(r)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "tomado.txt").unlink(missing_ok=True)
        p = subprocess.Popen([sys.executable, "-c", TOMAR, str(carpeta), str(segundos)], cwd=RAIZ)
        procesos.append(p)
        limite = time.monotonic() + 60
        while not (carpeta / "tomado.txt").exists():
            assert p.poll() is None and time.monotonic() < limite, "el otro proceso no tomó el candado"
            time.sleep(0.05)
        return p
    yield tomar
    for p in procesos:
        p.kill() if p.poll() is None else None
        p.wait()


def _corto(r, segundos=0.3):
    return r.copia_con({"real.espera_candado_s": segundos})


def test_registrar_llenado_con_el_candado_tomado_sale_con_aviso(compra, otro_proceso, monkeypatch, capsys):
    r, b, _ = compra
    r2 = _corto(r)
    r2.ruta = r.ruta
    otro_proceso(r2, 30)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r2)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA"]) == 1
    salida = capsys.readouterr().out
    assert salida.startswith("❌ Otra tarea del dinero real (la ronda real, registrar-llenado --real, conciliar --real o "
                             "registrar-saldo) tiene el candado datos/real/ronda.lock y no lo soltó en 0 s: no hice nada.")
    assert "Vuelve a correr registrar-llenado --real en un momento" in salida
    assert RE.leer_llenados(r) == []                                     # no se anotó nada
    tareas = [json.loads(x) for x in (RE.ruta_real(r).parent / "bots" / "registro.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert tareas[-1]["tarea"] == "registrar-llenado --real" and tareas[-1]["ok"] is False


def test_el_segundo_espera_y_despues_anota(compra, otro_proceso):
    r, b, _ = compra
    r.datos.setdefault("real", {})["espera_candado_s"] = 60
    otro_proceso(r, 1.5)
    t0 = time.monotonic()
    args = type("A", (), {"boleto": b["boleto_id"], "evento": "COMPRA_NO_LLENADA", "orden_id": None, "cantidad": None,
                          "precio": None, "comision": None, "moneda_comision": None, "stop_id": None,
                          "motivo": None, "bot": "EJECUTOR"})()
    assert cli_real.registrar_llenado_real(r, args) == 0
    assert time.monotonic() - t0 >= 0.5                                  # esperó a que el otro soltara
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["COMPRA_NO_LLENADA"]


def test_conciliar_con_el_candado_tomado_sale_con_aviso(compra, otro_proceso, capsys):
    r, b, _ = compra
    RE.archivo_conciliacion(r).unlink(missing_ok=True)
    otro_proceso(r, 30)
    capsys.readouterr()
    assert cli_real.con_candado(r, "CONTADOR", "conciliar --real", lambda: cli_real._conciliar_real(r),
                                espera_s=0.3) == 1
    assert "Vuelve a correr conciliar --real en un momento" in capsys.readouterr().out
    assert not RE.archivo_conciliacion(r).exists()


def test_conciliar_y_registrar_saldo_sin_nadie_mas_corren_normal(mundo, tmp_path, monkeypatch, capsys):
    r, _, foto, _ = mundo
    c, o = escribir_entrada(tmp_path, {"canTrade": True}, [])
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(cli_real, "precio_publico", lambda reg: (lambda s: 70000.0))
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 1   # cuenta rota: ❌ normal
    assert "La foto de saldo NO sirve" in capsys.readouterr().out
    assert (RE.ruta_real(r) / "ronda.lock").exists()                     # tomó el candado del real
    assert MAIN.main(["conciliar", "--real"]) == 1
    assert "Lo real NO cuadra" in capsys.readouterr().out


def test_registrar_saldo_con_el_candado_tomado_sale_con_aviso(mundo, tmp_path, otro_proceso, monkeypatch, capsys):
    r, _, foto, _ = mundo
    r2 = _corto(r)
    r2.ruta = r.ruta
    c, o = escribir_entrada(tmp_path, {"canTrade": True}, [])
    otro_proceso(r2, 30)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r2)
    monkeypatch.setattr(cli_real, "precio_publico", lambda reg: (lambda s: 70000.0))
    capsys.readouterr()
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 1
    assert "Vuelve a correr registrar-saldo en un momento" in capsys.readouterr().out
    assert not RE.archivo_saldo(r).exists()                              # no escribió la foto


def test_la_ronda_real_usa_el_mismo_candado(mundo, otro_proceso, monkeypatch, capsys):
    """La ronda real espera el mismo datos/real/ronda.lock (si no lo suelta a tiempo, no corre)."""
    from sobreviviente import cli_ronda as CR
    r, _, foto, correr = mundo
    foto()
    original = CR.candado_ronda
    monkeypatch.setattr(CR, "candado_ronda", lambda reg, **kw: original(reg, **{**kw, "espera_s": 0.3}))
    otro_proceso(r, 30)
    assert correr(AHORA + timedelta(minutes=1)) == 1
    assert "otra ronda sigue corriendo" in capsys.readouterr().out
