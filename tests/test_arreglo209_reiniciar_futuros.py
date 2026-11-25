"""Arreglo 209: `futuros-papel --reiniciar` empieza el papel de Futuros (F) de cero sin borrar nada.

Mismo patrón que `reiniciar-papel` (arreglo 128): sin --si solo explica; con --si mueve todo datos/papel_futuros/ a
datos/papel_futuros/archivo_<fecha UTC>/ con el candado datos/papel_futuros/ronda.lock (el mismo que toma la corrida de
futuros-papel). Nunca toca datos/papel/ (Spot), datos/real/, datos/cache/ ni salida/. Sin red.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from apoyo_futuros import ClienteFalso
from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config

RAIZ = Path(__file__).resolve().parent.parent
AHORA = datetime(2026, 11, 25, 20, 0, tzinfo=timezone.utc)
FUTUROS = {"F.json": {"cartera": "F", "capital": 40.0}, "F.json.bak": {"cartera": "F"}}
OTROS = {"papel/cartera_A.json": '{"cartera": "A"}', "papel/ronda.lock": "", "real/cartera_REAL.json": '{"x": 1}',
         "cache/futuros/4h/SOLUSDT.csv.gz": "1,2", "bots/registro.jsonl": "{}\n"}


@pytest.fixture
def r(tmp_path):
    reg = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})
    reg.ruta = tmp_path / "reglamento.yaml"
    return reg


def _sembrar(tmp_path):
    fut = tmp_path / "datos" / "papel_futuros"
    fut.mkdir(parents=True)
    for nombre, x in FUTUROS.items():
        (fut / nombre).write_text(json.dumps(x), encoding="utf-8")
    (fut / "ronda.lock").write_bytes(b"")
    (fut / "archivo_2026-11-01_000000Z").mkdir()
    (fut / "archivo_2026-11-01_000000Z" / "F.json").write_text("{}", encoding="utf-8")
    (fut / "notas").mkdir()
    (fut / "notas" / "a.txt").write_text("hola", encoding="utf-8")
    for rel, texto in OTROS.items():
        (tmp_path / "datos" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "datos" / rel).write_text(texto, encoding="utf-8")
    sal = tmp_path / "salida"
    sal.mkdir()
    (sal / "futuros_papel_2026-11-24.json").write_text("{}", encoding="utf-8")
    return fut


def _huella(raiz: Path) -> dict[str, str]:
    return {str(p.relative_to(raiz)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob("*")) if p.is_file()}


def _fuera_de_futuros(tmp_path):
    return {k: v for k, v in _huella(tmp_path).items() if not k.startswith("datos/papel_futuros")}


def test_sin_si_solo_explica(r, tmp_path, capsys):
    fut = _sembrar(tmp_path)
    antes = _huella(tmp_path)
    assert FC.reiniciar(r) == 0
    out = capsys.readouterr().out
    assert "--si" in out and "No hice nada" in out and "datos/papel_futuros/archivo_" in out
    assert "No toca datos/papel/ (Spot), datos/real/" in out
    assert _huella(tmp_path) == antes and (fut / "F.json").exists()


def test_con_si_archiva_todo_sin_borrar(r, tmp_path, capsys):
    fut = _sembrar(tmp_path)
    antes = _huella(fut)
    fuera = _fuera_de_futuros(tmp_path)
    assert FC.reiniciar(r, si=True, ahora=AHORA) == 0
    destino = fut / "archivo_2026-11-25_200000Z"
    assert sorted(p.name for p in fut.iterdir()) == ["archivo_2026-11-01_000000Z", "archivo_2026-11-25_200000Z",
                                                     "ronda.lock"]
    assert sorted(p.name for p in destino.iterdir()) == ["F.json", "F.json.bak", "notas"]
    despues = _huella(fut)
    for rel, h in antes.items():                       # nada se borró: todo está en el archivo, igualito
        if rel.startswith("archivo_2026-11-01") or rel == "ronda.lock":
            assert despues[rel] == h
        else:
            assert despues["archivo_2026-11-25_200000Z/" + rel] == h
    assert _fuera_de_futuros(tmp_path) == fuera        # datos/papel, datos/real, cache, bots y salida intactos
    out = capsys.readouterr().out
    assert "👍 Papel de Futuros reiniciado: 3 archivo(s)/carpeta(s)" in out and "42.54" in out


def test_dos_reinicios_en_el_mismo_segundo_no_se_mezclan(r, tmp_path):
    fut = _sembrar(tmp_path)
    assert FC.reiniciar(r, si=True, ahora=AHORA) == 0
    (fut / "F.json").write_text('{"otra": 1}', encoding="utf-8")
    assert FC.reiniciar(r, si=True, ahora=AHORA) == 0
    assert (fut / "archivo_2026-11-25_200000Z_2" / "F.json").read_text(encoding="utf-8") == '{"otra": 1}'
    assert (fut / "archivo_2026-11-25_200000Z" / "F.json.bak").exists()


def test_vacio_no_hace_nada(r, tmp_path, capsys):
    assert FC.reiniciar(r, si=True) == 0
    assert "ya está vacío" in capsys.readouterr().out
    fut = tmp_path / "datos" / "papel_futuros"
    assert [p.name for p in fut.iterdir()] == ["ronda.lock"]


def test_se_niega_si_alguien_tiene_el_candado(r, tmp_path, capsys):
    fut = _sembrar(tmp_path)
    antes = _huella(fut)
    with open(fut / "ronda.lock", "a+b") as f:
        AR.bloquear_archivo(f)
        try:
            assert FC.reiniciar(r, si=True) == 1
        finally:
            AR.desbloquear_archivo(f)
    assert "❌ futuros-papel está corriendo" in capsys.readouterr().out
    assert _huella(fut) == antes
    assert FC.reiniciar(r, si=True) == 0                 # sin candado, sí


def test_la_corrida_de_futuros_papel_toma_el_mismo_candado(r, tmp_path, capsys):
    fut = tmp_path / "datos" / "papel_futuros"
    fut.mkdir(parents=True)
    with open(fut / "ronda.lock", "a+b") as f:
        AR.bloquear_archivo(f)
        try:
            assert FC.comando(r, None, ClienteFalso(r)) == 1
        finally:
            AR.desbloquear_archivo(f)
    out = capsys.readouterr().out
    assert "❌ Otra corrida de futuros-papel (o un reinicio) está usando datos/papel_futuros" in out
    assert FC.comando(r, None, ClienteFalso(r)) == 0


def test_la_siguiente_corrida_arranca_con_estado_nuevo(r, tmp_path):
    _sembrar(tmp_path)
    assert FC.reiniciar(r, si=True) == 0
    est = C.cargar_estado(r, config.leer(r))
    assert est["capital"] == est["capital_inicial"] == 42.54 and est["posiciones"] == [] and est["cerradas"] == []


# ---------------------------------------------------------------------------- por el comando
def _copia_reglamento(tmp_path):
    ruta = tmp_path / "reglamento.yaml"                                    # copia en tmp: datos/ queda en tmp
    if not ruta.exists():
        datos = yaml.safe_load((RAIZ / "reglamento.yaml").read_text(encoding="utf-8"))
        ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ruta


def _main(capsys, tmp_path, *args):
    ruta = _copia_reglamento(tmp_path)
    capsys.readouterr()
    codigo = MAIN.main(["--reglamento", str(ruta), *args])
    return codigo, capsys.readouterr().out


def test_por_el_comando(capsys, tmp_path):
    fut = _sembrar(tmp_path)
    codigo, out = _main(capsys, tmp_path, "futuros-papel", "--reiniciar")
    assert codigo == 0 and "No hice nada" in out and (fut / "F.json").exists()
    codigo, out = _main(capsys, tmp_path, "futuros-papel", "--reiniciar", "--si")
    assert codigo == 0 and "👍 Papel de Futuros reiniciado" in out and not (fut / "F.json").exists()


def test_si_sin_reiniciar_no_hace_nada(capsys, tmp_path):
    fut = _sembrar(tmp_path)
    _copia_reglamento(tmp_path)
    antes = _huella(tmp_path)
    codigo, out = _main(capsys, tmp_path, "futuros-papel", "--si")
    assert codigo == 2 and "--si solo sirve con --reiniciar" in out and "No hice nada" in out
    assert _huella(tmp_path) == antes and (fut / "F.json").exists()


def test_cli_ronda_sigue_usando_el_mismo_candado():
    from sobreviviente import cli_ronda as CR
    assert CR._bloquear is AR.bloquear_archivo and CR._desbloquear is AR.desbloquear_archivo
