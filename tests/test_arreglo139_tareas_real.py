"""Arreglo 139: los comandos del dinero real se anotan en datos/bots/registro.jsonl.

`registrar-saldo`, `conciliar --real`, `ronda --verificar --real`, `registrar-llenado --real`, `ajustar-capital-real` y
`reporte diario --real` quedan como tareas del bot que corresponde, «sin medir» (a_tiempo = null): no tienen horario y no
deben contar como puntuales. La ronda real (`ronda --modo real`) tiene su propia fila y su hora se mide igual que la de
papel: a tiempo si no está FUERA DE HORA, tarde si corrió temprano, sin medir si ya existía. La simulación no escribe
nada, ni en registro.jsonl."""
from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import cli_real
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, cuenta, escribir_entrada, reg_abierto, reg_antes, reg_real
from test_arreglo133_compuertas_real import reg_vivo, ronda_falsa  # noqa: F401 - fixture


def _filas(r, tarea=None):
    return [f for f in AR.leer_registro(r) if tarea is None or f["tarea"] == tarea]


def _usar(monkeypatch, r):
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    monkeypatch.setattr(cli_real, "precio_publico", lambda reg: (lambda s: 70000.0))


def test_registrar_saldo_y_conciliar_real_sin_medir(tmp_path, monkeypatch):
    r = reg_real(tmp_path)
    _usar(monkeypatch, r)
    c, o = escribir_entrada(tmp_path, cuenta(), [])
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 0
    f = _filas(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"], f["a_tiempo"]) == ("EJECUTOR", "registrar-saldo", True, None)
    (tmp_path / "entrada" / "cuenta.json").write_text("{roto", encoding="utf-8")
    assert MAIN.main(["registrar-saldo", "--cuenta", str(c), "--ordenes", str(o)]) == 1
    f = _filas(r)[-1]
    assert (f["tarea"], f["ok"], f["a_tiempo"]) == ("registrar-saldo", False, None) and f["detalle"]
    MAIN.main(["conciliar", "--real"])
    f = _filas(r)[-1]
    assert (f["bot"], f["tarea"], f["a_tiempo"]) == ("CONTADOR", "conciliar --real", None)
    assert not _filas(r, "conciliar")                          # el conciliar de papel tiene su propia fila


def test_verificar_llenado_ajustar_y_reporte_real_sin_medir(tmp_path, monkeypatch):
    r = reg_abierto(tmp_path)                  # arreglo 186: con el interruptor del real encendido
    _usar(monkeypatch, r)
    assert MAIN.main(["ronda", "--verificar", "--real"]) == 1          # no hay ronda real de hoy
    f = _filas(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"], f["a_tiempo"]) == ("EJECUTOR", "ronda --verificar --real", False, None)
    assert not _filas(r, "ronda --verificar")                  # la tarea de papel (con horario) no se toca
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", "R20261115-COMPRAR-BTCUSDT-M0",
                      "--evento", "COMPRA_NO_LLENADA"]) == 1
    f = _filas(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"], f["a_tiempo"]) == ("EJECUTOR", "registrar-llenado --real", False, None)
    assert "R20261115-COMPRAR-BTCUSDT-M0" in f["detalle"]
    MAIN.main(["ajustar-capital-real", "--usdt", "150", "--ok-angelo", ""])
    f = _filas(r)[-1]
    assert (f["bot"], f["tarea"], f["a_tiempo"]) == ("THE BOSS", "ajustar-capital-real", None)
    assert MAIN.main(["reporte", "diario", "--real"]) == 0
    f = _filas(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"], f["a_tiempo"]) == ("CONTADOR", "reporte diario --real", True, None)
    assert MAIN.main(["reporte", "diario"]) == 0               # el de papel se sigue midiendo contra su hora
    f = _filas(r)[-1]
    assert f["tarea"] == "reporte diario" and isinstance(f["a_tiempo"], bool)
    cal = AR.calificacion_bots(r, 7)
    assert cal["EJECUTOR"]["sin_medir"] == 2 and cal["EJECUTOR"]["a_tiempo"] == 0
    assert cal["THE BOSS"]["sin_medir"] == 1 and cal["CONTADOR"]["sin_medir"] == 1


def test_ronda_real_se_mide_como_la_de_papel(tmp_path, ronda_falsa):  # noqa: F811
    r = reg_vivo(tmp_path)
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 0
    f = _filas(r)[-1]
    assert (f["bot"], f["tarea"], f["ok"], f["a_tiempo"]) == ("THE BOSS", "ronda --modo real", True, True)
    assert "día 2026-11-15" in f["detalle"]
    assert not _filas(r, "ronda")                              # fila propia: no se mezcla con la de papel
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 0        # repetida: sin hora que medir
    f = _filas(r)[-1]
    assert (f["tarea"], f["ok"], f["a_tiempo"], f["detalle"]) == ("ronda --modo real", True, None, "ya existía")
    r = reg_vivo(tmp_path / "tarde")
    assert RR.correr(r, AHORA.replace(hour=5), cliente=ronda_falsa, memes=[]) == 0
    f = _filas(r)[-1]
    assert (f["tarea"], f["ok"], f["a_tiempo"]) == ("ronda --modo real", True, False) and "fuera_de_hora" in f["detalle"]
    r = reg_vivo(tmp_path / "temprano")
    assert RR.correr(r, AHORA.replace(minute=2), cliente=ronda_falsa, memes=[]) == 1
    f = _filas(r)[-1]
    assert (f["tarea"], f["ok"], f["a_tiempo"]) == ("ronda --modo real", False, False)


def test_ronda_real_caida_puerta_cerrada_y_simulacion(tmp_path, ronda_falsa, monkeypatch):  # noqa: F811
    r = reg_vivo(tmp_path)
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[], simular=True) == 0
    assert _filas(r) == []                                     # la simulación no escribe nada
    r = reg_abierto(tmp_path / "cerrada", **{"estrategias.M0.estado": "PAPEL"})     # arreglo 186: encendido, M0 en PAPEL
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 2
    f = _filas(r)[-1]
    assert (f["tarea"], f["ok"], f["a_tiempo"]) == ("ronda --modo real", False, None) and "M0" in f["detalle"]
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[], simular=True) == 2
    assert len(_filas(r)) == 1
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **k: (_ for _ in ()).throw(OSError("sin red")))
    r = reg_vivo(tmp_path / "caida")
    assert RR.correr(r, AHORA, cliente=ronda_falsa, memes=[]) == 1
    f = _filas(r)[-1]
    assert (f["tarea"], f["ok"], f["a_tiempo"], f["detalle"]) == ("ronda --modo real", False, True, "sin red")


def test_estado_bots_muestra_las_tareas_reales_sin_medir(tmp_path, monkeypatch, capsys):
    r = reg_real(tmp_path)
    _usar(monkeypatch, r)
    MAIN.main(["conciliar", "--real"])
    capsys.readouterr()
    assert CR.mostrar_estado(r, bots=True, dias=7) == 0
    assert "CONTADOR: 1 tareas, sin medir" in capsys.readouterr().out
