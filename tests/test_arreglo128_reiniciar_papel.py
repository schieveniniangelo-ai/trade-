"""Arreglo 128: `reiniciar-papel --si` archiva TODO datos/papel/ sin borrar nada y la siguiente ronda arranca de cero.

No toca datos/bots/registro.jsonl, datos/real/ ni datos/cache/. Se niega si la ronda tiene el candado (lo intenta tomar
con el mismo mecanismo de la ronda; ronda.lock nunca se borra)."""
import json
import shutil
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P
from sobreviviente import reglamento

from test_papel import _datos_dia

RAIZ = Path(__file__).resolve().parent.parent

PAPEL = {"cartera_A.json": {"cartera": "A", "efectivo": 50.0}, "cartera_A.json.bak": {"cartera": "A"},
         "cartera_B.json": {"cartera": "B"}, "cartera_C.json": {"cartera": "C"},
         "referencias.json": {"2026-11-14": {"R0": 46.18}}, "rondas_viejas_A.json": {"2026-08-01": {}},
         "conciliacion.json": {"ok": True}, "grandes.json": ["BTCUSDT"], "saltadas.json": []}


@pytest.fixture
def r(tmp_path):
    reg = reglamento.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})
    for k in reg.estrategias:
        reg.datos["estrategias"][k]["estado"] = "APAGADA"
    reg.ruta = tmp_path / "reglamento.yaml"
    return reg


def _sembrar(tmp_path):
    papel = tmp_path / "datos" / "papel"
    (papel / "descartes").mkdir(parents=True)
    for nombre, x in PAPEL.items():
        (papel / nombre).write_text(json.dumps(x), encoding="utf-8")
    (papel / "descartes" / "2026-11-14.json").write_text("[]", encoding="utf-8")
    (papel / "bitacora_rondas.jsonl").write_text('{"dia_procesado": "2026-11-14"}\n', encoding="utf-8")
    (papel / "ronda.lock").write_bytes(b"")
    otros = {"bots/registro.jsonl": '{"bot": "EJECUTOR"}\n', "real/cartera_REAL.json": '{"cartera": "REAL"}',
             "cache/spot/x.csv": "1,2"}
    for rel, texto in otros.items():
        (tmp_path / "datos" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "datos" / rel).write_text(texto, encoding="utf-8")
    return papel, otros


def test_sin_si_solo_explica(r, tmp_path, capsys):
    papel, _ = _sembrar(tmp_path)
    antes = sorted(p.name for p in papel.iterdir())
    assert CR.reiniciar_papel(r) == 0
    salida = capsys.readouterr().out
    assert "--si" in salida and "No hice nada" in salida and "142.54" in salida
    assert sorted(p.name for p in papel.iterdir()) == antes


def test_archiva_todo_sin_borrar_y_no_toca_bots_real_ni_cache(r, tmp_path, capsys):
    papel, otros = _sembrar(tmp_path)
    assert CR.reiniciar_papel(r, si=True) == 0
    assert "👍 Papel reiniciado" in capsys.readouterr().out
    quedan = sorted(p.name for p in papel.iterdir())
    assert len(quedan) == 2 and quedan[0] == "archivo_" + quedan[0][len("archivo_"):] and quedan[1] == "ronda.lock"
    arch = papel / quedan[0]
    for nombre, x in PAPEL.items():
        assert json.loads((arch / nombre).read_text(encoding="utf-8")) == x
    assert (arch / "descartes" / "2026-11-14.json").read_text(encoding="utf-8") == "[]"
    assert (arch / "bitacora_rondas.jsonl").exists()
    for rel, texto in otros.items():
        assert (tmp_path / "datos" / rel).read_text(encoding="utf-8") == texto


def test_dos_veces_no_pierde_nada(r, tmp_path, capsys):
    papel, _ = _sembrar(tmp_path)
    assert CR.reiniciar_papel(r, si=True) == 0
    primero = sorted(str(p.relative_to(papel)) for p in papel.rglob("*"))
    assert CR.reiniciar_papel(r, si=True) == 0
    assert "no había nada que archivar" in capsys.readouterr().out
    assert sorted(str(p.relative_to(papel)) for p in papel.rglob("*")) == primero
    # Una ronda nueva y otro reinicio el mismo segundo: carpeta distinta, la primera intacta
    (papel / "cartera_A.json").write_text("{}", encoding="utf-8")
    from datetime import datetime, timezone
    fijo = datetime(2026, 11, 15, 20, 0, tzinfo=timezone.utc)
    assert CR.reiniciar_papel(r, si=True, ahora=fijo) == 0
    (papel / "cartera_B.json").write_text("{}", encoding="utf-8")
    assert CR.reiniciar_papel(r, si=True, ahora=fijo) == 0
    archivos = sorted(p.name for p in papel.iterdir() if p.name.startswith("archivo_"))
    assert len(archivos) == 3
    assert "archivo_2026-11-15_200000Z" in archivos and "archivo_2026-11-15_200000Z_2" in archivos
    assert {str(p.relative_to(papel)) for p in papel.rglob("*")} >= set(primero)   # el primer archivo sigue completo


def test_se_niega_si_la_ronda_tiene_el_candado(r, tmp_path, capsys):
    papel, _ = _sembrar(tmp_path)
    antes = sorted(p.name for p in papel.iterdir())
    with CR.candado_ronda(r, espera_s=0):
        assert CR.reiniciar_papel(r, si=True) == 1
    assert "❌ La ronda está corriendo" in capsys.readouterr().out
    assert sorted(p.name for p in papel.iterdir()) == antes
    assert CR.reiniciar_papel(r, si=True) == 0               # sin candado, sí


def test_la_ronda_siguiente_arranca_en_142_54_y_dia_1(r, tmp_path, capsys):
    _sembrar(tmp_path)
    assert CR.reiniciar_papel(r, si=True) == 0
    for n in P.CARTERAS:
        est = P.cargar_estado(r, n, "2026-11-16")
        assert est["capital_inicial"] == est["pico"] == est["capital_inicio_semana"] == est["capital_inicio_dia"] == 142.54
        assert est["cerradas"] == [] and est["curva"] == {}
    dd, _ = _datos_dia(r, 400)
    P.ronda_cartera(r, "A", dd, [], [])
    est = P.cargar_estado(r, "A", "")
    assert est["inicio"] == (dd.dia + P.DIA).strftime("%Y-%m-%d")
    assert est["pico"] == est["capital_inicio_semana"] == 142.54
    capsys.readouterr()
    assert CR.mostrar_estado(r) == 0
    salida = capsys.readouterr().out
    assert "Cartera A: 142.54 USDT · 0 abiertas · 0 cerradas" in salida
    assert f"Papel: día 1 desde {est['inicio']} (0 operaciones cerradas en la Cartera A)" in salida


def test_estado_sin_rondas_y_comando(tmp_path, capsys):
    shutil.copy(RAIZ / "reglamento.yaml", tmp_path / "reglamento.yaml")
    ruta = str(tmp_path / "reglamento.yaml")
    assert MAIN.main(["--reglamento", ruta, "estado"]) == 0
    assert "Papel: todavía sin rondas (el día 1 es la próxima ronda)" in capsys.readouterr().out
    assert MAIN.main(["--reglamento", ruta, "reiniciar-papel"]) == 0
    assert "No hice nada" in capsys.readouterr().out
    assert MAIN.main(["--reglamento", ruta, "reiniciar-papel", "--si"]) == 0
    assert "no había nada que archivar" in capsys.readouterr().out
