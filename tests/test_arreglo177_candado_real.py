"""Arreglo 177 (I1): registrar-llenado --real, conciliar --real y registrar-saldo usan el MISMO candado que la ronda real
(datos/real/ronda.lock, ronda_real.correr).

Antes podían correr a la vez que la ronda real (o entre ellos) y pisarse cartera_REAL.json: por ejemplo, la ronda carga
el estado, el EJECUTOR anota STOP_PUESTO y la ronda guarda su copia vieja encima. Ahora, si otro proceso tiene el
candado, el comando espera (⏳) hasta `ESPERA_CANDADO_S`; si no lo sueltan a tiempo, sale con ❌ y no hace nada.
Las pruebas usan un segundo PROCESO de verdad que toma el candado.
"""
import json
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import cli_real
from sobreviviente import real as RE

from apoyo_real import AHORA, cuenta, escribir_entrada
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
TOMAR = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, sys.argv[3])\n"
    "from sobreviviente import cli_ronda as CR\n"
    "with CR.candado_ronda(None, espera_s=5, carpeta=Path(sys.argv[1])):\n"
    "    print('TOMADO', flush=True)\n"
    "    time.sleep(float(sys.argv[2]))\n"
)


@pytest.fixture
def otro_proceso():
    """Arranca otro proceso de Python que toma datos/real/ronda.lock por `segundos` y espera a que lo tenga."""
    procesos = []

    def tomar(reg, segundos):
        p = subprocess.Popen([sys.executable, "-c", TOMAR, str(RE.ruta_real(reg)), str(segundos), str(RAIZ)],
                             stdout=subprocess.PIPE, text=True)
        procesos.append(p)
        assert p.stdout.readline().strip() == "TOMADO"
        return p
    yield tomar
    for p in procesos:
        p.kill() if p.poll() is None else None
        p.wait(timeout=30)


def test_es_el_mismo_candado_que_la_ronda_real(compra):
    r, _, _ = compra
    assert cli_real.archivo_candado(r) == RE.ruta_real(r) / "ronda.lock"
    import inspect
    from sobreviviente import ronda_real as RR
    assert "CR.candado_ronda(reg, carpeta=RE.ruta_real(reg))" in inspect.getsource(RR.correr)


def test_conciliar_sale_con_aviso_si_no_sueltan_el_candado(compra, otro_proceso, monkeypatch, capsys):
    r, b, foto = compra
    foto(cuenta(), [], ahora=AHORA + timedelta(minutes=1))
    antes = RE.archivo_conciliacion(r).read_bytes()
    otro_proceso(r, 30)
    monkeypatch.setattr(cli_real, "ESPERA_CANDADO_S", 0.3)
    capsys.readouterr()
    assert cli_real.conciliar_real(r) == 1
    salida = capsys.readouterr().out.splitlines()
    assert salida[0].startswith("⏳ Otra tarea del real (la ronda real, registrar-llenado, conciliar o registrar-saldo) "
                                "está usando datos/real: espero hasta 0 s")
    assert salida[1].startswith("❌ conciliar --real: otra tarea del real sigue usando datos/real después de 0 s "
                                "(candado datos/real/ronda.lock). No hice nada")
    assert RE.archivo_conciliacion(r).read_bytes() == antes                # no se tocó
    f = AR.leer_registro(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"], f["detalle"]) == ("CONTADOR", "conciliar --real", False,
                                                            "candado ocupado: no se hizo nada")


def test_registrar_llenado_espera_a_que_suelten_y_luego_anota(compra, otro_proceso, monkeypatch, capsys):
    r, b, _ = compra
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    otro_proceso(r, 1.5)
    t0 = time.monotonic()
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA",
                      "--motivo", "EXPIRED"]) == 0
    assert time.monotonic() - t0 >= 0.5                                    # esperó al otro proceso
    salida = capsys.readouterr().out
    assert salida.startswith("⏳ Otra tarea del real") and "👍 Anotado: la compra no se llenó" in salida
    assert [x["evento"] for x in RE.leer_llenados(r)] == ["COMPRA_NO_LLENADA"]


def test_registrar_llenado_no_anota_nada_si_no_sueltan(compra, otro_proceso, monkeypatch, capsys):
    r, b, _ = compra
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(cli_real, "ESPERA_CANDADO_S", 0.3)
    otro_proceso(r, 30)
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA",
                      "--motivo", "EXPIRED"]) == 1
    assert "❌ registrar-llenado --real: otra tarea del real sigue usando datos/real" in capsys.readouterr().out
    assert RE.leer_llenados(r) == [] and not RE.archivo_llenados(r).exists()
    f = AR.leer_registro(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"]) == ("EJECUTOR", "registrar-llenado --real", False)


def test_registrar_saldo_no_escribe_la_foto_si_no_sueltan(compra, otro_proceso, monkeypatch, capsys, tmp_path):
    r, _, _ = compra
    antes = RE.archivo_saldo(r).read_bytes()
    c, o = escribir_entrada(tmp_path / "otra", cuenta(usdt=100.0), [])
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(cli_real, "precio_publico", lambda reg: (lambda s: 70000.0))
    monkeypatch.setattr(cli_real, "ESPERA_CANDADO_S", 0.3)
    otro_proceso(r, 30)
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 1
    assert "❌ registrar-saldo: otra tarea del real sigue usando datos/real" in capsys.readouterr().out
    assert RE.archivo_saldo(r).read_bytes() == antes


def test_sin_nadie_mas_corre_derecho_sin_esperar(compra, monkeypatch, capsys, tmp_path):
    r, _, _ = compra
    c, o = escribir_entrada(tmp_path / "otra", cuenta(), [])
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(cli_real, "precio_publico", lambda reg: (lambda s: 70000.0))
    capsys.readouterr()
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 0
    salida = capsys.readouterr().out
    assert "⏳" not in salida and "👍 Foto de saldo guardada" in salida
    assert json.loads(RE.archivo_saldo(r).read_text(encoding="utf-8"))["ok"] is True
    assert cli_real.conciliar_real(r) == 0 and "⏳" not in capsys.readouterr().out
