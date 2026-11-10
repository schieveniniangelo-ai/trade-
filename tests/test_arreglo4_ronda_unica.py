"""Arreglo 4: la ronda de un mismo día no se repite, y dos procesos a la vez no se pisan."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

RAIZ = Path(__file__).resolve().parent.parent


def _rondas_ok(reg):
    filas = [f for f in AR.leer_registro(reg) if f["tarea"] == "ronda" and f["ok"]]
    nuevas = [f for f in filas if f["detalle"] != "ya existía"]
    repetidas = [f for f in filas if f["detalle"] == "ya existía"]
    return nuevas, repetidas


def test_dos_llamadas_el_mismo_dia_un_solo_juego_de_boletos(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    llamadas = []

    def preparar(*a, **kw):
        llamadas.append(1)
        return dd
    monkeypatch.setattr(P, "preparar_datos", preparar)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    arch = tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json"
    antes = arch.read_text(encoding="utf-8")
    refs_antes = (tmp_path / "datos" / "papel" / "referencias.json").read_text(encoding="utf-8")
    capsys.readouterr()
    assert CR.correr_ronda(r, ahora=ahora + pd.Timedelta(minutes=30).to_pytimedelta(), cliente=object(), memes=[]) == 0
    salida = capsys.readouterr().out
    assert f"la ronda de {dd.dia:%Y-%m-%d} ya corrió" in salida
    assert len(llamadas) == 1                                       # no volvió a bajar datos ni a correr
    assert arch.read_text(encoding="utf-8") == antes                # boletos sin reescribir
    assert (tmp_path / "datos" / "papel" / "referencias.json").read_text(encoding="utf-8") == refs_antes
    nuevas, repetidas = _rondas_ok(r)
    assert len(nuevas) == 1 and len(repetidas) == 1
    bit = (tmp_path / "datos" / "papel" / "bitacora_rondas.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(bit) == 1                                            # no cuenta como ronda nueva
    assert AR.calificacion_bots(r)["THE BOSS"]["tareas"] == 1
    assert "Cartera C" in salida                                    # muestra el resumen guardado


def test_ya_corrio_por_estado_aunque_falte_el_archivo(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **kw: dd)
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    assert CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]) == 0
    (tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json").unlink()
    assert CR.ronda_ya_corrio(r, f"{dd.dia:%Y-%m-%d}")              # el estado de las carteras ya tiene ese día


def test_candado_bloquea_a_un_segundo_dueno(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    with CR.candado_ronda(r):
        with pytest.raises(CR.RondaOcupada):
            with CR.candado_ronda(r, espera_s=0.5):
                pass
    with CR.candado_ronda(r, espera_s=0.5):                         # ya libre
        pass


SCRIPT = textwrap.dedent('''
    import sys, time
    sys.path.insert(0, sys.argv[3]); sys.path.insert(0, sys.argv[4])
    from pathlib import Path
    import pandas as pd
    from sobreviviente import reglamento, papel as P, cli_ronda as CR
    from test_arreglo1_papel import _reg_m0
    from test_papel import _datos_dia
    r = _reg_m0(reglamento.cargar(), Path(sys.argv[1]))
    dd, _ = _datos_dia(r, int(sys.argv[2]))
    def lento(*a, **kw):
        time.sleep(3)
        return dd
    P.preparar_datos = lento
    ahora = (dd.dia + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    sys.exit(CR.correr_ronda(r, ahora=ahora, cliente=object(), memes=[]))
''')


def test_dos_procesos_a_la_vez_no_corrompen_el_estado(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    dd, _ = _datos_dia(r, k)
    script = tmp_path / "correr.py"
    script.write_text(SCRIPT, encoding="utf-8")
    args = [sys.executable, str(script), str(tmp_path), str(k), str(RAIZ / "tests"), str(RAIZ)]
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    procesos = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=entorno) for _ in range(2)]
    salidas = [p.communicate(timeout=120) for p in procesos]
    assert [p.returncode for p in procesos] == [0, 0], [(s[0] + s[1]).decode("utf-8", "replace")[-1200:] for s in salidas]
    textos = [s[0].decode("utf-8", "replace") for s in salidas]
    assert sum("ya corrió" in t for t in textos) == 1                # uno corrió, el otro esperó y vio lo guardado
    boletos = json.loads((tmp_path / "salida" / f"boletos_{dd.dia:%Y-%m-%d}.json").read_text(encoding="utf-8"))
    compras = [b for b in boletos if b["accion"] == "COMPRAR"]
    assert compras and len({b["boleto_id"] for b in boletos}) == len(boletos)   # sin boletos repetidos
    for n in P.CARTERAS:
        assert sum(b["cartera"] == n for b in compras) <= 1
        est = json.loads((tmp_path / "datos" / "papel" / f"cartera_{n}.json").read_text(encoding="utf-8"))
        assert est["ultimo_dia"] == f"{dd.dia:%Y-%m-%d}"
        assert len(est["posiciones"]) == sum(b["cartera"] == n for b in compras)  # sin posiciones duplicadas
    nuevas, repetidas = _rondas_ok(r)
    assert len(nuevas) == 1 and len(repetidas) == 1
