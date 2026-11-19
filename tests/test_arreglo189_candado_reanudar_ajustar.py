"""Arreglo 189 (R99): `reanudar --cartera REAL` y `ajustar-capital-real` usan el candado de la ronda real
(`cli_real.con_candado`, datos/real/ronda.lock), como registrar-llenado, conciliar --real y registrar-saldo (177).

Los dos leen y guardan cartera_REAL.json: sin candado podían pisarse con la ronda real o con un registrar-llenado (por
ejemplo, la ronda guarda su copia vieja encima del bloqueo que Ángelo acaba de quitar). Si otro proceso tiene el candado,
esperan (⏳) hasta ESPERA_CANDADO_S; si no lo sueltan a tiempo, salen con ❌ y no hacen nada. Las pruebas usan un
segundo PROCESO de verdad que toma el candado."""
import inspect

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import cli_real
from sobreviviente import cli_ronda as CR
from sobreviviente import real as RE

from apoyo_real import reg_abierto
from test_arreglo177_candado_real import otro_proceso  # noqa: F401 - fixture


def _bloqueada(tmp_path):
    r = reg_abierto(tmp_path)
    est = RE.cargar_estado(r)
    est["bloqueo_compras"] = {"desde": "2026-11-16T00:15:00+00:00", "motivo": "SIN STOP: BTC"}
    RE.guardar_estado(r, est)
    return r


def test_los_dos_usan_con_candado():
    assert "cli_real.con_candado(reg, bot, \"reanudar --cartera REAL\"" in inspect.getsource(CR.reanudar)
    assert "con_candado(reg, \"THE BOSS\", \"ajustar-capital-real\"" in inspect.getsource(cli_real.cmd_ajustar_capital_real)


def test_reanudar_real_sale_con_aviso_si_no_sueltan_el_candado(tmp_path, otro_proceso, monkeypatch, capsys):  # noqa: F811
    r = _bloqueada(tmp_path)
    antes = RE.archivo_estado(r).read_bytes()
    otro_proceso(r, 30)
    monkeypatch.setattr(cli_real, "ESPERA_CANDADO_S", 0.3)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["reanudar", "--cartera", "REAL", "--ok-angelo", "ya revisé en Binance"]) == 1
    salida = capsys.readouterr().out.splitlines()
    assert salida[0].startswith("⏳ Otra tarea del real")
    assert salida[1].startswith("❌ reanudar --cartera REAL: otra tarea del real sigue usando datos/real después de 0 s "
                                "(candado datos/real/ronda.lock). No hice nada")
    assert RE.archivo_estado(r).read_bytes() == antes                      # el bloqueo sigue
    f = AR.leer_registro(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"], f["detalle"]) == ("THE BOSS", "reanudar --cartera REAL", False,
                                                            "candado ocupado: no se hizo nada")


def test_reanudar_real_espera_a_que_suelten_y_luego_reanuda(tmp_path, otro_proceso, capsys):  # noqa: F811
    r = _bloqueada(tmp_path)
    otro_proceso(r, 1.5)
    assert CR.reanudar(r, "REAL", "ya revisé en Binance") == 0
    salida = capsys.readouterr().out
    assert salida.startswith("⏳ Otra tarea del real") and "👍 Cartera REAL reanudada con el OK de Ángelo." in salida
    assert RE.cargar_estado(r)["bloqueo_compras"] is None


def test_ajustar_capital_sale_con_aviso_si_no_sueltan_el_candado(tmp_path, otro_proceso, monkeypatch, capsys):  # noqa: F811
    r = _bloqueada(tmp_path)
    antes = RE.archivo_estado(r).read_bytes()
    otro_proceso(r, 30)
    monkeypatch.setattr(cli_real, "ESPERA_CANDADO_S", 0.3)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ajustar-capital-real", "--usdt", "150", "--ok-angelo", "depósito de 7.46"]) == 1
    salida = capsys.readouterr().out.splitlines()
    assert salida[1].startswith("❌ ajustar-capital-real: otra tarea del real sigue usando datos/real")
    assert RE.archivo_estado(r).read_bytes() == antes
    f = AR.leer_registro(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"]) == ("THE BOSS", "ajustar-capital-real", False)


def test_ajustar_capital_espera_a_que_suelten_y_luego_ajusta(tmp_path, otro_proceso, monkeypatch, capsys):  # noqa: F811
    r = _bloqueada(tmp_path)
    otro_proceso(r, 1.5)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ajustar-capital-real", "--usdt", "150", "--ok-angelo", "depósito de 7.46"]) == 0
    salida = capsys.readouterr().out
    assert salida.startswith("⏳ Otra tarea del real") and "👍 Capital real ajustado con el OK de Ángelo" in salida
    est = RE.cargar_estado(r)
    assert est["bloqueo_compras"] is None and est["ajustes"][-1]["usdt"] == 150


def test_sin_nadie_mas_corren_derecho(tmp_path, monkeypatch, capsys):
    r = _bloqueada(tmp_path)
    assert CR.reanudar(r, "REAL", "") == 2                                  # sin OK: igual que antes
    assert "Falta el OK de Ángelo" in capsys.readouterr().out
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ajustar-capital-real", "--usdt", "150", "--ok-angelo", ""]) == 2
    salida = capsys.readouterr().out
    assert "⏳" not in salida and "Falta el OK de Ángelo" in salida
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert CR.reanudar(r, "REAL", "ok") == 1 and "No se puede reanudar" in capsys.readouterr().out
