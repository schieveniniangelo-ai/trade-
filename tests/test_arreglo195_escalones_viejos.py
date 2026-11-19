"""Arreglo 195 (R96): doctor avisa si escalones.json tiene más de 30 días sin actualizarse.

Las tablas de escalones de Futuros F1 (sobreviviente/futuros/escalones.json) se copiaron a mano de la página pública de
Binance y Binance las cambia: PROPUESTAS.md (N5) dice revisarlas una vez al mes. doctor lo recuerda con ⚠️ cuando su
`fecha` pasa de 30 días (hora de CDMX) o si no se puede leer; si no, ℹ️ con los días. Solo avisa: no es ❌."""
import json
from datetime import datetime, timezone

import pytest

from sobreviviente import doctor
from sobreviviente import reglamento
from sobreviviente.futuros import liquidacion as LQ

R = reglamento.cargar()


def _archivo(tmp_path, fecha="2026-11-17"):
    a = tmp_path / "escalones.json"
    a.write_text(json.dumps({"fecha": fecha, "monedas": {}}), encoding="utf-8")
    return a


def test_el_archivo_de_verdad_tiene_fecha():
    datos = json.loads(LQ.ARCHIVO_ESCALONES.read_text(encoding="utf-8"))
    assert datos["fecha"] == "2026-11-17" and doctor.ESCALONES_MAX_DIAS == 30


@pytest.mark.parametrize("ahora,dias", [
    (datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc), 5),
    (datetime(2026, 12, 17, 18, 0, tzinfo=timezone.utc), 30),               # 30 justos: todavía no avisa
    (datetime(2026, 12, 18, 5, 59, tzinfo=timezone.utc), 30),               # 11:59 p. m. del 17 dic en CDMX
])
def test_al_dia_solo_informa(tmp_path, ahora, dias):
    assert doctor.aviso_escalones(R, ahora, _archivo(tmp_path)) == (
        f"ℹ️ escalones.json (tablas de escalones de Futuros F1): actualizado hace {dias} días (2026-11-17)")


def test_mas_de_30_dias_avisa(tmp_path):
    ahora = datetime(2026, 12, 18, 6, 0, tzinfo=timezone.utc)               # ya es 18 dic en CDMX: 31 días
    assert doctor.aviso_escalones(R, ahora, _archivo(tmp_path)) == (
        "⚠️ escalones.json (tablas de escalones de Futuros F1) tiene 31 días sin actualizarse (fecha 2026-11-17; máximo "
        "30)\n     → Vuelve a copiar las tablas de la página pública Leverage & Margin de Binance, revisa cada cum y pon "
        "la fecha nueva (PROPUESTAS.md, sección N5). Binance las cambia.")


@pytest.mark.parametrize("contenido", ['{"monedas": {}}', '{"fecha": "ayer"}', "{roto", '{"fecha": null}'])
def test_sin_fecha_legible_avisa(tmp_path, contenido):
    a = tmp_path / "escalones.json"
    a.write_text(contenido, encoding="utf-8")
    assert doctor.aviso_escalones(R, archivo=a).startswith("⚠️ No pude leer la fecha de escalones.json")
    assert doctor.aviso_escalones(R, archivo=tmp_path / "no_existe.json").startswith("⚠️ No pude leer la fecha")


def test_doctor_lo_muestra_sin_contarlo_como_falla(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    monkeypatch.setattr(LQ, "ARCHIVO_ESCALONES", _archivo(tmp_path, "2026-01-01"))
    r = R.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    salida = []
    assert doctor.revisar(r, imprimir=salida.append) == 0
    (linea,) = [x for x in salida if "escalones.json" in x]
    assert linea.startswith("⚠️ escalones.json (tablas de escalones de Futuros F1) tiene ")
