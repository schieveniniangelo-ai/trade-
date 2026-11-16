"""Arreglo 138: reportes y comparación papel contra real.

`estado --real` y `reporte diario --real` (diez líneas o menos, REAL y PAPEL en secciones separadas y nunca sumados,
más la diferencia entre la Cartera A de papel y la real con sus causas). `reporte semanal` agrega la comparación solo si
ya hay dinero real. Los reportes y `estado` de papel salen igual que antes."""
import json

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import reportes

from apoyo_real import reg_real
from test_arreglo131_conciliar_real import POS


@pytest.fixture
def r(tmp_path):
    reg = reg_real(tmp_path)
    for n, cap in (("A", 150.0), ("B", 140.0), ("C", 145.0)):
        est = P.estado_nuevo(n, 142.54, "2026-11-16")
        est["curva"] = {"2026-11-16": cap}
        if n == "A":
            # el papel compró a 60,000 y el real a 70,010: (70,010 − 60,000) × 0.00013 = +1.30 USDT por precio de llenado
            est["posiciones"] = [{"estrategia": "M0", "t_entrada": "2026-11-16 00:00:00+00:00", "entrada": 60000.0}]
        P.guardar_estado(reg, est)
    return reg


def _real(r, **cambios):
    est = {**RE.estado_nuevo(142.54, "2026-11-16"), "posiciones": [{**POS, "t_entrada": "2026-11-16T00:15:00+00:00"}],
           **cambios}
    RE.guardar_estado(r, est)
    return est


def test_reporte_diario_real_separado_y_corto(r):
    _real(r)
    lineas = reportes.diario_real(r).splitlines()
    assert len(lineas) <= 10 and "REAL y PAPEL por separado" in lineas[0]
    assert lineas[1].startswith("REAL: 142.54 USDT en libros (+0.0 % desde 142.54) · 1 abiertas")
    assert "REAL: BTCUSDT 0.00012 con stop 59500 (ACTIVO)" in lineas
    papel = next(x for x in lineas if x.startswith("PAPEL:"))
    assert papel == "PAPEL: Cartera A 150.00 · B 140.00 · C 145.00 USDT (sin dinero real)"
    comp = next(x for x in lineas if x.startswith("Cartera A de papel − real"))
    assert comp.startswith("Cartera A de papel − real: +7.46 USDT. Causas: precio de llenado +1.30 USDT")
    assert "comisiones reales 0.01 USDT" in comp and "0 compra(s) que no se llenaron" in comp
    assert not any(("432" in x or "577" in x) for x in lineas)              # nada sumado (142.54 + 150 + 140 + 145)
    assert "❌ no hay foto de saldo" in "\n".join(lineas) and lineas[-1] == "Necesito tu respuesta (ver ❌ arriba)."


def test_causas_cuentan_no_llenadas_y_dias_de_volatilidad_alta(r):
    _real(r, posiciones=[], bloqueo_compras={"desde": "x", "motivo": "SIN STOP: BTC"})
    RE.ruta_real(r).mkdir(parents=True, exist_ok=True)
    RE.archivo_llenados(r).write_text(json.dumps({"boleto_id": "x", "evento": "COMPRA_NO_LLENADA"}) + "\n{roto\n",
                                      encoding="utf-8")
    (RE.ruta_real(r) / "descartes").mkdir()
    (RE.ruta_real(r) / "descartes" / "descartes_2026-11-17.json").write_text(json.dumps(
        {"dia": "2026-11-17", "carteras": {"REAL": [{"texto": "saltada por capital: la compra (4.20 USDT) no llega"}]}}),
        encoding="utf-8")
    (RE.ruta_real(r) / "descartes" / "descartes_2026-11-18.json").write_text("{roto", encoding="utf-8")
    texto = reportes.diario_real(r)
    assert "1 compra(s) que no se llenaron" in texto and "1 día(s) saltados por capital" in texto
    assert "REAL: ❌ compras detenidas" in texto


def test_estado_real(r, capsys, monkeypatch):
    _real(r, cerradas=[{"simbolo": "BTCUSDT", "ganancia_usdt": -1.2, "motivo": "VENTA_LLENADA"}],
          bloqueo_compras={"desde": "x", "motivo": "SIN STOP: BTC"})
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["estado", "--real"]) == 0
    salida = capsys.readouterr().out
    assert "REAL: 141.34 USDT en libros (arrancó con 142.54) · 1 abiertas · 1 cerradas (-1.2000 USDT)" in salida
    assert "BTCUSDT: 0.00012 comprados a 70010 · stop 59500 límite 59202.5 · ACTIVO" in salida
    assert "cerrada BTCUSDT: -1.2000 USDT" in salida and "❌ compras bloqueadas" in salida
    assert MAIN.main(["reporte", "diario", "--real"]) == 0
    assert "REAL y PAPEL por separado" in capsys.readouterr().out
    RE.archivo_estado(r).write_text("{roto", encoding="utf-8")
    assert MAIN.main(["estado", "--real"]) == 1
    assert MAIN.main(["reporte", "diario", "--real"]) == 1


def test_papel_sale_igual_sin_real_y_semanal_compara_con_real(r):
    diario = reportes.diario(r)
    semanal = reportes.semanal(r)
    assert "PAPEL" in diario.splitlines()[0] and "papel − real" not in semanal     # sin real: igual que antes
    _real(r)
    assert reportes.diario(r) == diario                                            # el diario de papel no cambia
    nuevo = reportes.semanal(r).splitlines()
    assert any(x.startswith("Cartera A de papel − real: ") for x in nuevo)
    assert [x for x in nuevo if not x.startswith("Cartera A de papel − real")] == semanal.splitlines()


def test_apertura_vs_precio_no_lee_boletos_reales(r, tmp_path):
    salida = tmp_path / "salida"
    salida.mkdir()
    (salida / "boletos_real_2026-11-16.json").write_text(json.dumps([{"dif_apertura_pct": 9.0}]), encoding="utf-8")
    assert reportes.apertura_vs_precio(r, "2026-11-10") == ["Apertura vs precio al correr: sin datos todavía."]
