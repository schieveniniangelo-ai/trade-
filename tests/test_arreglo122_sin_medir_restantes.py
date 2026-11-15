"""Arreglo 122 (G2.2, opción A): las tareas sin horario medido quedan «sin medir» (a_tiempo = null).

Como en los arreglos 89 y 111: THE BOSS `comando X` (comando que truena), `reanudar` (bien o con archivo dañado)
y RADAR `exclusiones.json` (archivo que viene mal en la ronda) no tienen una hora límite, así que no cuentan como
«a tiempo» por defecto. No se les inventa horario. Las que ya pasan a_tiempo explícito lo conservan.
"""
import json
import shutil
from pathlib import Path

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

RAIZ = Path(__file__).resolve().parent.parent


def _linea_estado(r, bot, capsys):
    capsys.readouterr()
    assert CR.mostrar_estado(r, bots=True, dias=7) == 0
    return next(x.strip() for x in capsys.readouterr().out.splitlines() if x.strip().startswith(f"{bot}:"))


def test_comando_que_truena_queda_sin_medir(tmp_path, monkeypatch, capsys):
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")
    ruta = str(tmp_path / "reglamento.yaml")

    def tronar(*a, **kw):
        raise KeyError("curva")
    monkeypatch.setattr(CR, "mostrar_estado", tronar)
    assert MAIN.main(["--reglamento", ruta, "estado"]) == 1
    monkeypatch.undo()
    fila = json.loads((tmp_path / "datos" / "bots" / "registro.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert fila["tarea"] == "comando estado" and fila["ok"] is False and fila["a_tiempo"] is None
    r = MAIN.RGL.cargar(ruta)
    assert _linea_estado(r, "THE BOSS", capsys).startswith("THE BOSS: 1 tareas, sin medir,")


def _detener(r, tmp_path, cartera="C"):
    k = _dia_marea_alta(r)
    P.ronda_cartera(r, cartera, _datos_dia(r, k)[0], [], [])
    arch = tmp_path / "datos" / "papel" / f"cartera_{cartera}.json"
    est = json.loads(arch.read_text(encoding="utf-8"))
    est["detenido"] = True
    arch.write_text(json.dumps(est), encoding="utf-8")
    return arch


def test_reanudar_queda_sin_medir(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path)
    _detener(r, tmp_path)
    assert CR.reanudar(r, "C", "OK, sigue — Ángelo 15/11") == 0
    fila = AR.leer_registro(r)[-1]
    assert fila["tarea"] == "reanudar" and fila["ok"] is True and fila["a_tiempo"] is None
    assert _linea_estado(r, "THE BOSS", capsys).startswith("THE BOSS: 1 tareas, sin medir,")


def test_reanudar_con_archivo_danado_queda_sin_medir(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path)
    arch = _detener(r, tmp_path)
    arch.write_text("{roto", encoding="utf-8")
    bak = arch.with_name(arch.name + ".bak")
    if bak.exists():
        bak.unlink()
    assert CR.reanudar(r, "C", "OK — Ángelo", bot="THE BOSS") == 1
    fila = AR.leer_registro(r)[-1]
    assert fila["tarea"] == "reanudar" and fila["ok"] is False and fila["a_tiempo"] is None
    assert _linea_estado(r, "THE BOSS", capsys).startswith("THE BOSS: 1 tareas, sin medir,")


def test_exclusiones_mal_queda_sin_medir(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "datos" / "exclusiones.json").write_text(json.dumps({"exclusiones": "no es lista"}), encoding="utf-8")
    out = P.ronda(r, _datos_dia(r, k)[0])
    assert out["modo_seguro"] is True
    fila = [f for f in AR.leer_registro(r) if f["bot"] == "RADAR"][-1]
    assert fila["tarea"] == "exclusiones.json" and fila["ok"] is False and fila["a_tiempo"] is None
    assert _linea_estado(r, "RADAR", capsys) == ("RADAR: 1 tareas, sin medir, 1 archivos rechazados, "
                                                 "0 diferencias boleto/llenado")


def test_a_tiempo_explicito_se_conserva(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    AR.registrar_tarea(r, "THE BOSS", "ronda", False, "temprano", a_tiempo=False)
    assert AR.leer_registro(r)[-1]["a_tiempo"] is False
    AR.registrar_tarea(r, "THE BOSS", "ronda", True, "ok", a_tiempo=True)
    assert AR.leer_registro(r)[-1]["a_tiempo"] is True
