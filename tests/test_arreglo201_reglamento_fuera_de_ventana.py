"""Arreglo 201: doctor avisa «⚠️ reglamento cambiado fuera de la ventana» (no bloquea nada).

La ronda de papel, al terminar, guarda la versión y las cifras del reglamento con que corrió
(datos/papel/reglamento_ultima_ronda.json). doctor compara la versión de hoy con esa: si cambió y hoy (hora de CDMX) no
es `control_cambios.dia_ventana`, sale ⚠️, salvo que el cambio solo baje el riesgo (cifras de riesgo más bajas o iguales,
nada más distinto). Si es el día de la ventana, o el cambio solo baja el riesgo, ℹ️. Solo avisa: no cuenta como ❌."""
import json
from datetime import datetime, timezone

import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import doctor
from sobreviviente import papel as P

from apoyo_real import reg_real
from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas

SABADO = datetime(2026, 11, 21, 20, 0, tzinfo=timezone.utc)      # 2:00 p. m. CDMX del sábado 21 nov
DOMINGO = datetime(2026, 11, 22, 20, 0, tzinfo=timezone.utc)
DOMINGO_UTC_SABADO_CDMX = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)   # 9:00 p. m. CDMX del sábado


def _con_ronda(tmp_path, **cambios_despues):
    r = reg_real(tmp_path)
    doctor.guardar_reglamento_de_la_ronda(r, SABADO)
    hoy = r.copia_con({"version": "2.0.4", **cambios_despues})
    hoy.ruta = r.ruta
    return r, hoy


def test_sin_ronda_o_misma_version_no_dice_nada(tmp_path):
    r = reg_real(tmp_path)
    assert doctor.aviso_reglamento_cambiado(r, SABADO) == ""
    doctor.guardar_reglamento_de_la_ronda(r, SABADO)
    assert json.loads(doctor.archivo_reglamento_ronda(r).read_text(encoding="utf-8"))["version"] == r.version
    assert doctor.aviso_reglamento_cambiado(r, SABADO) == ""


def test_cambio_fuera_de_la_ventana_avisa(tmp_path):
    r, hoy = _con_ronda(tmp_path, **{"riesgo.tope_diario_pct": 4.0})
    assert doctor.aviso_reglamento_cambiado(hoy, SABADO) == (
        f"⚠️ reglamento cambiado fuera de la ventana: {r.version} → 2.0.4 desde la última ronda y hoy es sábado (la "
        f"ventana es el domingo)\n     → Revisa CAMBIOS.md: entre semana solo se aceptan cambios que bajen el riesgo. "
        f"Avisa a Ángelo (no bloquea nada).")
    assert doctor.aviso_reglamento_cambiado(hoy, DOMINGO_UTC_SABADO_CDMX).startswith("⚠️")   # cuenta el día de CDMX


def test_el_dia_de_la_ventana_solo_informa(tmp_path):
    r, hoy = _con_ronda(tmp_path, **{"riesgo.tope_diario_pct": 4.0})
    assert doctor.aviso_reglamento_cambiado(hoy, DOMINGO) == (
        f"ℹ️ Reglamento {r.version} → 2.0.4 desde la última ronda (hoy es domingo: día de la ventana)")


def test_si_solo_baja_el_riesgo_no_avisa(tmp_path):
    r, hoy = _con_ronda(tmp_path, **{"carteras.A.riesgo_por_operacion_pct": 0.5, "riesgo.posiciones_max.memes": 0})
    assert doctor.aviso_reglamento_cambiado(hoy, SABADO).startswith(
        f"ℹ️ Reglamento {r.version} → 2.0.4 desde la última ronda, fuera de la ventana (domingo), pero el cambio solo "
        f"baja el riesgo")
    _, sube = _con_ronda(tmp_path / "b", **{"carteras.A.riesgo_por_operacion_pct": 0.5, "carteras.B.tope_semanal_pct": 9.0})
    assert sube and doctor.aviso_reglamento_cambiado(sube, SABADO).startswith("⚠️")      # una sube: avisa
    _, otra = _con_ronda(tmp_path / "c", **{"ronda.tiempo_max_segundos": 90})
    assert doctor.aviso_reglamento_cambiado(otra, SABADO).startswith("⚠️")                 # no es de riesgo: avisa


def test_solo_baja_el_riesgo_casos():
    assert doctor._solo_baja_el_riesgo({"version": "1", "riesgo.tope_diario_pct": 3.0},
                                       {"version": "2", "riesgo.tope_diario_pct": 2.0})
    assert not doctor._solo_baja_el_riesgo({"riesgo.tope_diario_pct": 3.0}, {"riesgo.tope_diario_pct": "2"})
    assert not doctor._solo_baja_el_riesgo({"riesgo.tope_diario_pct": 3.0}, {})                  # se borró
    assert not doctor._solo_baja_el_riesgo({"real.activo": False}, {"real.activo": True})


def test_archivo_danado(tmp_path):
    r = reg_real(tmp_path)
    doctor.archivo_reglamento_ronda(r).parent.mkdir(parents=True)
    doctor.archivo_reglamento_ronda(r).write_text('{"version": "x", "cifras": 3}', encoding="utf-8")
    assert doctor.aviso_reglamento_cambiado(r, SABADO).startswith(
        "⚠️ No pude leer reglamento_ultima_ronda.json (el reglamento de la última ronda)")


def test_doctor_lo_muestra_y_no_cuenta_como_falla(tmp_path, monkeypatch):
    r, hoy = _con_ronda(tmp_path, **{"riesgo.tope_diario_pct": 4.0})
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    monkeypatch.setattr(doctor, "aviso_reglamento_cambiado", lambda reg: "⚠️ reglamento cambiado fuera de la ventana: x")
    salida = []
    assert doctor.revisar(hoy, imprimir=salida.append) == 0
    assert "⚠️ reglamento cambiado fuera de la ventana: x" in salida


def test_la_ronda_de_papel_lo_guarda(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    cli = ClienteFalso(tmp_path, _velas_completas(), k)
    assert CR.correr_ronda(r, ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime(), cliente=cli, memes=[]) == 0
    guardado = json.loads(doctor.archivo_reglamento_ronda(r).read_text(encoding="utf-8"))
    assert guardado["version"] == r.version and guardado["cifras"]["riesgo.tope_diario_pct"] == r.get(
        "riesgo.tope_diario_pct")
    assert P.ruta_papel(r) == doctor.archivo_reglamento_ronda(r).parent


def test_si_no_se_puede_guardar_la_ronda_sigue(reg, tmp_path, monkeypatch, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    cli = ClienteFalso(tmp_path, _velas_completas(), k)

    def falla(reg, ahora=None):
        raise OSError("disco lleno")
    monkeypatch.setattr(doctor, "guardar_reglamento_de_la_ronda", falla)
    assert CR.correr_ronda(r, ahora=(cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime(), cliente=cli, memes=[]) == 0
    assert "⚠️ No pude guardar el reglamento de esta ronda (OSError)" in capsys.readouterr().out
