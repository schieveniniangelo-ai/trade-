"""Arreglo 43 (T11-2, R11): comando `respaldo` y aviso ℹ️ cuando no hay respaldo reciente. Todo en carpetas temporales."""
import hashlib
import json
import os
import tarfile
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from sobreviviente import cli_ronda as CR
from sobreviviente import respaldo as RESP

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas

AHORA = datetime(2026, 11, 12, 0, 25, tzinfo=timezone.utc)


def _proyecto(reg, tmp_path, **cambios):
    """Un proyecto de mentira con estado de 3 carteras, boletos, registro y archivos de bots."""
    raiz = tmp_path / "proyecto"
    r = reg.copia_con({"datos.carpeta": str(raiz / "datos"), "respaldo.carpeta": str(tmp_path / "respaldos"), **cambios})
    r.ruta = raiz / "reglamento.yaml"
    for carpeta in ("datos/papel", "datos/estela", "datos/bots", "salida"):
        (raiz / carpeta).mkdir(parents=True)
    (raiz / "reglamento.yaml").write_text("version: prueba\n", encoding="utf-8")
    for n in "ABC":
        (raiz / "datos" / "papel" / f"cartera_{n}.json").write_text(json.dumps({"cartera": n, "efectivo": 46.18}), encoding="utf-8")
    (raiz / "datos" / "papel" / "bitacora_rondas.jsonl").write_text('{"dia_procesado": "2026-11-10"}\n', encoding="utf-8")
    (raiz / "datos" / "papel" / "ronda.lock").write_text("", encoding="utf-8")
    (raiz / "datos" / "estela" / "2026-11-10.json").write_text('{"fecha": "2026-11-10"}', encoding="utf-8")
    (raiz / "datos" / "bots" / "registro.jsonl").write_text('{"bot": "RADAR"}\n', encoding="utf-8")
    (raiz / "salida" / "boletos_2026-11-10.json").write_text('[{"boleto_id": "x"}]', encoding="utf-8")
    for nombre in ("vetos", "eventos", "exclusiones"):
        (raiz / "datos" / f"{nombre}.json").write_text(json.dumps({nombre: []}), encoding="utf-8")
    (raiz / "datos" / "memes.json").write_text('{"memes": []}', encoding="utf-8")
    return r, raiz


def _hashes(raiz):
    return {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob("*")) if p.is_file()}


def _nombres(archivo):
    with tarfile.open(archivo, "r:gz") as tar:
        return sorted(m.name for m in tar.getmembers())


def test_respaldo_contiene_lo_importante_y_no_toca_el_origen(reg, tmp_path, capsys):
    r, raiz = _proyecto(reg, tmp_path)
    antes = _hashes(raiz)
    assert RESP.respaldar(r, AHORA) == 0
    archivo = tmp_path / "respaldos" / "respaldo-2026-11-12-0025.tar.gz"
    assert archivo.is_file() and "👍 Respaldo guardado" in capsys.readouterr().out
    adentro = _nombres(archivo)
    for esperado in ("salida/boletos_2026-11-10.json", "datos/papel/cartera_A.json", "datos/papel/cartera_B.json",
                     "datos/papel/cartera_C.json", "datos/papel/bitacora_rondas.jsonl", "datos/bots/registro.jsonl",
                     "datos/estela/2026-11-10.json", "datos/vetos.json", "datos/eventos.json", "datos/exclusiones.json",
                     "datos/memes.json", "reglamento.yaml"):
        assert esperado in adentro, esperado
    assert "datos/papel/ronda.lock" not in adentro                       # el candado no es un dato
    despues = _hashes(raiz)
    registro = "datos/bots/registro.jsonl"                               # lo único que cambia: la tarea del CONTADOR
    assert {k: v for k, v in antes.items() if k != registro} == {k: v for k, v in despues.items() if k != registro}
    ultima = json.loads((raiz / registro).read_text(encoding="utf-8").splitlines()[-1])
    assert ultima["bot"] == "CONTADOR" and ultima["tarea"] == "respaldo" and ultima["ok"] is True


def test_el_tar_se_abre_y_cada_json_se_lee(reg, tmp_path):
    r, raiz = _proyecto(reg, tmp_path)
    assert RESP.respaldar(r, AHORA) == 0
    with tarfile.open(tmp_path / "respaldos" / "respaldo-2026-11-12-0025.tar.gz", "r:gz") as tar:
        miembros = [m for m in tar.getmembers() if m.name.endswith(".json")]
        assert len(miembros) >= 9
        for m in miembros:
            json.loads(tar.extractfile(m).read().decode("utf-8"))
        cartera = json.loads(tar.extractfile("datos/papel/cartera_B.json").read().decode("utf-8"))
    assert cartera == {"cartera": "B", "efectivo": 46.18}


def test_conserva_los_ultimos_y_no_borra_archivos_ajenos(reg, tmp_path):
    r, _ = _proyecto(reg, tmp_path, **{"respaldo.guardar_ultimos": 3})
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    (carpeta / "fotos-de-la-familia.tar.gz").write_text("ajeno", encoding="utf-8")
    (carpeta / "respaldo-viejo.txt").write_text("ajeno", encoding="utf-8")
    (carpeta / "respaldo-2020-01-01-0000.tar.gz.bak").write_text("ajeno", encoding="utf-8")
    for i in range(5):
        assert RESP.respaldar(r, AHORA + timedelta(days=i)) == 0
    quedan = sorted(p.name for p in carpeta.iterdir() if RESP.fecha_de_respaldo(p.name))
    assert quedan == ["respaldo-2026-11-14-0025.tar.gz", "respaldo-2026-11-15-0025.tar.gz", "respaldo-2026-11-16-0025.tar.gz"]
    for ajeno in ("fotos-de-la-familia.tar.gz", "respaldo-viejo.txt", "respaldo-2020-01-01-0000.tar.gz.bak"):
        assert (carpeta / ajeno).read_text(encoding="utf-8") == "ajeno"


def test_json_de_origen_danado_se_respalda_tal_cual_y_avisa(reg, tmp_path, capsys):
    r, raiz = _proyecto(reg, tmp_path)
    (raiz / "datos" / "papel" / "cartera_A.json").write_text("{dañado", encoding="utf-8")
    assert RESP.respaldar(r, AHORA) == 0
    salida = capsys.readouterr().out
    assert "⚠️ datos/papel/cartera_A.json estaba dañado; se respaldó tal cual" in salida
    with tarfile.open(tmp_path / "respaldos" / "respaldo-2026-11-12-0025.tar.gz", "r:gz") as tar:
        assert tar.extractfile("datos/papel/cartera_A.json").read().decode("utf-8") == "{dañado"


def test_carpeta_que_no_se_puede_escribir_da_error_sin_dejar_nada_a_medias(reg, tmp_path, monkeypatch, capsys):
    r, raiz = _proyecto(reg, tmp_path)
    assert RESP.respaldar(r, AHORA) == 0                                  # un respaldo anterior, bueno
    anterior = tmp_path / "respaldos" / "respaldo-2026-11-12-0025.tar.gz"
    huella = hashlib.sha256(anterior.read_bytes()).hexdigest()
    capsys.readouterr()

    def sin_permiso(origen, destino):
        raise PermissionError("no se puede escribir aquí")

    monkeypatch.setattr(os, "replace", sin_permiso)                       # falla justo al final
    assert RESP.respaldar(r, AHORA + timedelta(days=1)) == 1
    salida = capsys.readouterr().out
    assert "❌ No pude guardar el respaldo" in salida and "Traceback" not in salida
    assert sorted(p.name for p in (tmp_path / "respaldos").iterdir()) == [anterior.name]     # ni .tmp ni respaldo nuevo
    assert hashlib.sha256(anterior.read_bytes()).hexdigest() == huella
    ultima = json.loads((raiz / "datos" / "bots" / "registro.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert ultima["tarea"] == "respaldo" and ultima["ok"] is False


def test_carpeta_de_respaldo_imposible_da_error(reg, tmp_path, capsys):
    estorbo = tmp_path / "no-es-carpeta"
    estorbo.write_text("soy un archivo", encoding="utf-8")
    r, _ = _proyecto(reg, tmp_path, **{"respaldo.carpeta": str(estorbo / "respaldos")})
    assert RESP.respaldar(r, AHORA) == 1
    assert "❌ No pude guardar el respaldo" in capsys.readouterr().out
    assert estorbo.read_text(encoding="utf-8") == "soy un archivo"


def test_no_sigue_enlaces_simbolicos(reg, tmp_path):
    r, raiz = _proyecto(reg, tmp_path)
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "secreto.json").write_text('{"no": "debe salir"}', encoding="utf-8")
    try:
        os.symlink(fuera / "secreto.json", raiz / "datos" / "papel" / "enlace.json")
        os.symlink(fuera, raiz / "datos" / "papel" / "carpeta_enlazada", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("esta computadora no deja crear enlaces simbólicos")
    assert RESP.respaldar(r, AHORA) == 0
    adentro = _nombres(tmp_path / "respaldos" / "respaldo-2026-11-12-0025.tar.gz")
    assert not [n for n in adentro if "enlace" in n or "secreto" in n]
    assert "datos/papel/cartera_A.json" in adentro


def test_aviso_sin_respaldo(reg, tmp_path):
    r, _ = _proyecto(reg, tmp_path)
    assert r.get("respaldo.max_horas_sin_respaldo") == 48 and r.get("respaldo.guardar_ultimos") == 14
    assert RESP.aviso_sin_respaldo(r, AHORA) == ["ℹ️ Sin respaldo de datos todavía: corre 'python -m sobreviviente respaldo'"]
    assert RESP.respaldar(r, AHORA - timedelta(days=3)) == 0
    assert RESP.aviso_sin_respaldo(r, AHORA) == ["ℹ️ Sin respaldo de datos desde 2026-11-09: corre 'python -m sobreviviente respaldo'"]
    assert RESP.respaldar(r, AHORA) == 0
    assert RESP.aviso_sin_respaldo(r, AHORA) == []


def test_ronda_sin_respaldo_informa_sin_modo_seguro_y_con_pulgar(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path).copia_con({"respaldo.carpeta": str(tmp_path / "respaldos")})
    r.ruta = tmp_path / "reglamento.yaml"
    r.datos["estrategias"]["M0"]["estado"] = "APAGADA"
    k = _dia_marea_alta(r)
    cli = ClienteFalso(tmp_path, _velas_completas(), k)
    ahora = (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()
    for vez in ("primera", "repetida"):
        assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0
        salida = capsys.readouterr().out
        assert ("ya corrió" in salida) == (vez == "repetida")
        assert "ℹ️ Sin respaldo de datos todavía: corre 'python -m sobreviviente respaldo'" in salida, vez
        assert "MODO SEGURO" not in salida and "👍 No necesito nada de ti." in salida, vez


def test_ronda_con_respaldo_de_hoy_no_avisa(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path).copia_con({"respaldo.carpeta": str(tmp_path / "respaldos")})
    r.ruta = tmp_path / "reglamento.yaml"
    r.datos["estrategias"]["M0"]["estado"] = "APAGADA"
    k = _dia_marea_alta(r)
    cli = ClienteFalso(tmp_path, _velas_completas(), k)
    ahora = (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    assert RESP.respaldar(r, ahora - timedelta(hours=1)) == 0
    capsys.readouterr()
    assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0
    assert "Sin respaldo" not in capsys.readouterr().out


def test_lo_que_el_sistema_marca_como_enlace_no_entra(reg, tmp_path, monkeypatch):
    """Igual que la prueba anterior, pero sin depender de que la computadora deje crear enlaces (Windows)."""
    from pathlib import Path
    r, raiz = _proyecto(reg, tmp_path)
    (raiz / "datos" / "papel" / "enlace.json").write_text('{"no": "debe salir"}', encoding="utf-8")
    (raiz / "datos" / "papel" / "carpeta_enlazada").mkdir()
    (raiz / "datos" / "papel" / "carpeta_enlazada" / "secreto.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "is_symlink", lambda self: "enla" in self.name)
    assert RESP.respaldar(r, AHORA) == 0
    adentro = _nombres(tmp_path / "respaldos" / "respaldo-2026-11-12-0025.tar.gz")
    assert not [n for n in adentro if "enlace" in n or "secreto" in n]
    assert "datos/papel/cartera_A.json" in adentro
