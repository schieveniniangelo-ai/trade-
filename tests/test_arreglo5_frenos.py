"""Arreglo 5: los frenos funcionan de verdad — reanudar con el OK de Ángelo, y una conciliación que no cuadra
detiene las compras nuevas."""
import json

import pytest

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia


def _editar_estado(tmp_path, cartera, **cambios):
    arch = tmp_path / "datos" / "papel" / f"cartera_{cartera}.json"
    est = json.loads(arch.read_text(encoding="utf-8"))
    est.update(cambios)
    arch.write_text(json.dumps(est), encoding="utf-8")


def test_detenida_reanudar_y_no_se_vuelve_a_detener(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])
    capital = list(P.cargar_estado(r, "C", "")["curva"].values())[-1]
    _editar_estado(tmp_path, "C", detenido=True, pico=capital * 3)      # simulamos que tocó el freno total
    # Sin reanudar, la siguiente ronda sigue detenida (la caída contra ese pico sigue ahí)
    c1 = P.ronda_cartera(r, "C", _datos_dia(r, k + 1)[0], [], [])
    assert c1["detenido"] is True
    # Reanudar sin texto: se niega
    assert CR.reanudar(r, "C", "   ") == 2
    assert CR.reanudar(r, "C", "OK, sigue — Ángelo 10/11") == 0
    est = P.cargar_estado(r, "C", "")
    assert est["detenido"] is False
    assert est["pico"] == pytest.approx(list(est["curva"].values())[-1])
    assert est["reanudaciones"][-1]["texto"] == "OK, sigue — Ángelo 10/11"
    ultima = AR.leer_registro(r)[-1]
    assert ultima["bot"] == "THE BOSS" and ultima["tarea"] == "reanudar" and ultima["ok"]
    # La ronda siguiente ya no se detiene por el mismo pico
    c2 = P.ronda_cartera(r, "C", _datos_dia(r, k + 2)[0], [], [])
    assert c2["detenido"] is False
    assert P.cargar_estado(r, "C", "")["detenido"] is False


def test_reanudar_si_no_estaba_detenida(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    P.ronda_cartera(r, "A", _datos_dia(r, k)[0], [], [])
    assert CR.reanudar(r, "A", "ok") == 0
    assert "no estaba detenida" in capsys.readouterr().out
    assert "reanudaciones" not in P.cargar_estado(r, "A", "")


def test_conciliar_con_diferencia_no_abre_posiciones(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    k = _dia_marea_alta(r)
    # Una cartera con cuentas que no cuadran (efectivo de más)
    est = P.estado_nuevo("A", 46.18, "2022-01-01")
    est["efectivo"] += 5.0
    P.guardar_estado(r, est)
    assert CR.conciliar(r) == 1
    arch = tmp_path / "datos" / "papel" / "conciliacion.json"
    d = json.loads(arch.read_text(encoding="utf-8"))
    assert d["ok"] is False and "fecha" in d
    c = P.ronda_cartera(r, "C", _datos_dia(r, k)[0], [], [])
    assert not [b for b in c["boletos"] if b["accion"] == "COMPRAR"]
    assert any("conciliación no cuadró" in m for m in c["mensajes"])
    assert not P.cargar_estado(r, "C", "")["posiciones"]
    # Se arregla, conciliar sale bien y la ronda siguiente sí puede comprar
    est["efectivo"] -= 5.0
    P.guardar_estado(r, est)
    assert CR.conciliar(r) == 0
    assert json.loads(arch.read_text(encoding="utf-8"))["ok"] is True
    dd2, _ = _datos_dia(r, k + 1)
    if dd2.md.marea.get(dd2.dia) != "ALCISTA":
        pytest.skip("la marea cambió justo al día siguiente")
    c2 = P.ronda_cartera(r, "C", dd2, [], [])
    assert [b for b in c2["boletos"] if b["accion"] == "COMPRAR"]


def test_conciliacion_rota_cuenta_como_que_no_cuadra(reg, tmp_path):
    r = _reg_m0(reg, tmp_path)
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    (tmp_path / "datos" / "papel" / "conciliacion.json").write_text("{roto", encoding="utf-8")
    assert P.conciliacion_ok(r) is False
