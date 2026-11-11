"""Arreglo 85 (B9): las pruebas no miran la carpeta real de respaldos (~/respaldos-sobreviviente).

La ronda completa llama respaldo.aviso_sin_respaldo, que lista la carpeta de respaldos. Esa carpeta sale de
'~/respaldos-sobreviviente' en el reglamento, así que sin aislar, el resultado dependía de la computadora.
conftest.py apunta la carpeta de usuario a un directorio temporal en cada prueba.
"""
from datetime import datetime, timezone

from sobreviviente import reglamento
from sobreviviente import respaldo as RESP

AHORA = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def test_reglamento_cargado_directo_apunta_a_carpeta_temporal(tmp_path):
    c = RESP.carpeta_respaldos(reglamento.cargar())
    assert c.is_relative_to(tmp_path)


def test_fixture_reg_apunta_a_carpeta_temporal(reg, tmp_path):
    assert RESP.carpeta_respaldos(reg).is_relative_to(tmp_path)


def test_aviso_sin_respaldo_no_depende_de_la_computadora(tmp_path):
    r = reglamento.cargar()
    assert RESP.respaldos_existentes(r) == []
    assert RESP.aviso_sin_respaldo(r, AHORA) == [
        "ℹ️ Sin respaldo de datos todavía: corre 'python -m sobreviviente respaldo'"]
