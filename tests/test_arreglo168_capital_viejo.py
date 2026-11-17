"""Arreglo 168: aviso de cartera de papel con capital viejo.

Si una cartera de papel guardada en disco (datos/papel/cartera_X.json) tiene un capital_inicial distinto de
carteras.capital_inicial del reglamento, la ronda y `doctor` lo dicen claro, con el comando para empezar de nuevo
(reiniciar-papel --si). Solo avisa: no cambia ni borra nada, y en doctor no cuenta como ❌. Sin red ni llaves.
"""
import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P
from sobreviviente import python_actual

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo48_doctor import _correr, _internet
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas


def _guardar(r, nombre, capital):
    P.guardar_estado(r, P.estado_nuevo(nombre, capital, "2026-11-01"))


def _bytes(tmp_path):
    carpeta = tmp_path / "datos" / "papel"
    return {p.name: p.read_bytes() for p in carpeta.iterdir() if p.is_file()}


def test_sin_carteras_o_con_el_mismo_capital_no_avisa(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=46.18)
    assert P.avisos_capital_viejo(r) == []
    assert not (tmp_path / "datos").exists()                  # leer no crea nada
    for n in "ABC":
        _guardar(r, n, 46.18)
    assert P.avisos_capital_viejo(r) == []


def test_avisa_cada_cartera_con_capital_viejo_y_junta_las_iguales(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=142.54)
    _guardar(r, "A", 46.18)
    _guardar(r, "B", 46.18)
    _guardar(r, "C", 142.54)
    antes = _bytes(tmp_path)
    (aviso,) = P.avisos_capital_viejo(r)
    assert aviso == (f"⚠️ Las carteras A y B de papel tienen capital viejo (46.18 USDT; el reglamento dice 142.54 USDT en "
                     f"carteras.capital_inicial). Si quieres empezar de nuevo, corre {python_actual()} -m sobreviviente "
                     f"reiniciar-papel --si (no borra nada: archiva datos/papel/).")
    assert _bytes(tmp_path) == antes                          # solo avisa: no cambia ni borra nada
    _guardar(r, "C", 100.0)
    avisos = P.avisos_capital_viejo(r)
    assert len(avisos) == 2 and avisos[1].startswith("⚠️ La cartera C de papel tiene capital viejo (100 USDT;")


def test_un_archivo_danado_o_raro_no_truena(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=142.54)
    carpeta = tmp_path / "datos" / "papel"
    carpeta.mkdir(parents=True)
    (carpeta / "cartera_A.json").write_text("{roto", encoding="utf-8")
    (carpeta / "cartera_B.json").write_text("[1, 2]", encoding="utf-8")
    (carpeta / "cartera_C.json").write_text('{"capital_inicial": "cien"}', encoding="utf-8")
    assert P.avisos_capital_viejo(r) == []                    # lo dañado ya tiene su propio aviso en la ronda


def test_la_ronda_lo_avisa_sin_tocar_las_carteras(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path, capital=46.18)
    k = _dia_marea_alta(r)
    for n in "ABC":
        _guardar(r, n, 30.0)
    cli = ClienteFalso(tmp_path, _velas_completas(), k)
    ahora = (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()
    dd = P.preparar_datos(r, cli, [], ahora=ahora)
    aviso = next(x for x in dd.informativos if "capital viejo" in x)
    assert aviso.startswith("⚠️ Las carteras A, B y C de papel tienen capital viejo (30 USDT; el reglamento dice 46.18")
    assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0
    salida = capsys.readouterr().out
    assert aviso in salida and "reiniciar-papel --si" in salida
    for n in "ABC":                                           # las carteras siguen con su capital (no se cambia nada)
        assert P.cargar_estado(r, n, "")["capital_inicial"] == 30.0
    assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0     # repetida: sale lo que se guardó
    assert aviso in capsys.readouterr().out


def test_doctor_lo_avisa_sin_contarlo_como_falla(reg, tmp_path, monkeypatch):
    r = _reg_m0(reg, tmp_path, capital=142.54)
    _internet(monkeypatch)
    codigo, texto = _correr(r)
    assert codigo == 0 and "capital viejo" not in texto
    _guardar(r, "B", 46.18)
    antes = _bytes(tmp_path)
    codigo, texto = _correr(r)
    assert codigo == 0 and texto.endswith("👍 Todo listo.")
    assert "⚠️ La cartera B de papel tiene capital viejo (46.18 USDT; el reglamento dice 142.54 USDT" in texto
    assert "reiniciar-papel --si" in texto and _bytes(tmp_path) == antes
