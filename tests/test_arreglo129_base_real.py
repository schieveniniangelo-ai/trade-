"""Arreglo 129: base del dinero real (cierra R2 y R11).

datos/real/ fuera de git, estado datos/real/cartera_REAL.json con la forma de una cartera de papel más los campos de
cada posición real, respaldo que lo incluye, reiniciar-papel que no lo toca, y falla cerrada si está dañado."""
import json
import tarfile
from pathlib import Path

import pytest

from sobreviviente import cli_ronda as CR
from sobreviviente import real as RE
from sobreviviente import reglamento
from sobreviviente import respaldo

RAIZ = Path(__file__).resolve().parent.parent

POSICION = {"id": "20261116-RA-COM-BTC-abcd1234", "simbolo": "BTCUSDT", "estrategia": "M0",
            "cantidad_comprada": 0.00013, "cantidad_neta": 0.00012, "precio_llenado": 70010.0, "comision": 0.00000013,
            "moneda_comision": "BTC", "stop": 59500.0, "limite_stop": 59202.5, "id_stop": "sp0123456789abcdef",
            "orden_id_stop": 123, "estado_stop": "ACTIVO", "t_entrada": "2026-11-16T00:12:00+00:00"}


@pytest.fixture
def r(tmp_path):
    reg = reglamento.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})
    reg.ruta = tmp_path / "reglamento.yaml"
    return reg


def test_datos_real_fuera_de_git():
    lineas = [x.strip() for x in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "datos/real/" in lineas


def test_estado_nuevo_y_forma(r, tmp_path):
    assert RE.ruta_real(r) == tmp_path / "datos" / "real"
    est = RE.cargar_estado(r, "2026-11-16")
    assert est["cartera"] == "REAL" and est["reglas_de"] == "A" and est["inicio"] == "2026-11-16"
    for k in ("capital_inicial", "pico", "capital_inicio_dia", "capital_inicio_semana"):
        assert est[k] == 142.54
    assert est["posiciones"] == [] and est["cerradas"] == [] and est["pausa_hasta"] is None and est["rachas"] == {}
    assert not RE.archivo_estado(r).exists()            # leer no crea nada: solo los llenados confirmados lo cambian
    est["posiciones"].append(dict(POSICION))
    RE.guardar_estado(r, est)
    assert RE.cargar_estado(r)["posiciones"][0] == POSICION
    assert RE.estado_ok(r) == (True, "")


@pytest.mark.parametrize("contenido, palabra", [
    ("{roto", "dañado"),
    (json.dumps([1, 2]), "formato raro"),
    (json.dumps({**RE.estado_nuevo(142.54, ""), "cartera": "A"}), "cartera"),
    (json.dumps({**RE.estado_nuevo(142.54, ""), "posiciones": [{"simbolo": "BTCUSDT"}]}), "le falta"),
    (json.dumps({**RE.estado_nuevo(142.54, ""), "posiciones": [{**POSICION, "estado_stop": "QUIZA"}]}), "estado_stop"),
    (json.dumps({**RE.estado_nuevo(142.54, ""), "pico": "mucho"}), "no es un número"),
    (json.dumps({**RE.estado_nuevo(142.54, ""), "posiciones": {}}), "listas"),
    (json.dumps({**RE.estado_nuevo(142.54, ""), "posiciones": [7]}), "no es un objeto"),
])
def test_estado_danado_error_claro_sin_usar_la_copia(r, contenido, palabra):
    est = RE.estado_nuevo(142.54, "")
    est["posiciones"].append(dict(POSICION))
    RE.guardar_estado(r, est)
    RE.guardar_estado(r, est)                            # deja una copia .bak sana con la posición
    RE.archivo_estado(r).write_text(contenido, encoding="utf-8")
    with pytest.raises(RE.EstadoRealDanado) as e:
        RE.cargar_estado(r)
    assert palabra in str(e.value) and "NO compra" in str(e.value)
    ok, msg = RE.estado_ok(r)
    assert ok is False and msg == str(e.value)


def test_falta_el_archivo_pero_hay_copia_no_se_inventa_uno_nuevo(r):
    RE.guardar_estado(r, RE.estado_nuevo(142.54, ""))
    RE.guardar_estado(r, RE.estado_nuevo(142.54, ""))
    RE.archivo_estado(r).unlink()
    with pytest.raises(RE.EstadoRealDanado, match="copia"):
        RE.cargar_estado(r)


def test_respaldo_incluye_datos_real(r, tmp_path):
    RE.guardar_estado(r, RE.estado_nuevo(142.54, "2026-11-16"))
    (RE.ruta_real(r) / "saldos").mkdir(parents=True)
    (RE.ruta_real(r) / "saldos" / "2026-11-16_001.json").write_text("{}", encoding="utf-8")
    assert respaldo.respaldar(r, avisar=lambda *_: None) == 0
    (_, arch), = respaldo.respaldos_existentes(r)
    with tarfile.open(arch, "r:gz") as tar:
        nombres = tar.getnames()
    assert "datos/real/cartera_REAL.json" in nombres and "datos/real/saldos/2026-11-16_001.json" in nombres


def test_reiniciar_papel_no_toca_el_real(r, capsys):
    RE.guardar_estado(r, RE.estado_nuevo(142.54, "2026-11-16"))
    (RE.ruta_real(r).parent / "papel").mkdir(parents=True)
    (RE.ruta_real(r).parent / "papel" / "cartera_A.json").write_text("{}", encoding="utf-8")
    antes = RE.archivo_estado(r).read_bytes()
    assert CR.reiniciar_papel(r, si=True) == 0
    assert RE.archivo_estado(r).read_bytes() == antes and sorted(p.name for p in RE.ruta_real(r).iterdir()) == \
        ["cartera_REAL.json"]
