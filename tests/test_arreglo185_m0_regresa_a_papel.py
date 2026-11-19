"""Arreglo 185 (C3, DECISIÓN DE ÁNGELO, ventana del domingo 22 nov 2026): M0 regresa a PAPEL porque no pasó sus
compuertas. Estuvo en VIVA_MINI del 16 al 22 nov (arreglo 140). Con M0 en PAPEL la puerta del real se cierra: `ronda
--modo real` no corre ni escribe nada; `doctor` lo dice (solo informa, no cuenta como ❌). El papel sigue con M0."""
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import doctor
from sobreviviente import real as RE
from sobreviviente import reglamento
from sobreviviente import ronda_real as RR

from apoyo_real import reg_abierto, reg_real

RAIZ = Path(__file__).resolve().parent.parent


def _linea_m0():
    texto = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    m0 = texto[texto.index("\n  M0:\n"):texto.index("\n  M1:\n")]
    (linea,) = [x for x in m0.splitlines() if x.strip().startswith("estado:")]
    return linea


def test_el_reglamento_tiene_m0_en_papel_con_la_decision():
    r = reglamento.cargar()
    assert r.estrategias["M0"]["estado"] == "PAPEL"
    assert all(e["estado"] == "APAGADA" for k, e in r.estrategias.items() if k != "M0")
    comentario = _linea_m0().split("#", 1)[1]
    assert comentario.strip().startswith("22 nov 2026: DECISIÓN DE ÁNGELO. Regresa a PAPEL porque no pasó sus compuertas")
    for frase in ("65.6 % contra 90 % del azar", "caída p95 59.8 % contra 25 %", "papel_dias_min 30",
                  "papel_operaciones_min 30", "arreglo 140", "la ronda real no corre"):
        assert frase in comentario, frase
    # lo demás de M0 no cambia
    assert r.estrategias["M0"]["parametros"] == {"sma": 200} and r.estrategias["M0"]["fijos"] == {"stop_pct": 15}
    assert r.estrategias["M0"]["universo"] == "BTC" and r.estrategias["M0"]["mover_a_entrada"] is False


def test_cambios_lo_anota():
    cambios = (RAIZ / "CAMBIOS.md").read_text(encoding="utf-8")
    seccion = cambios[cambios.index("## Reglamento 2.0.3"):]
    assert "Arreglo 185" in seccion and "**M0 regresa de VIVA_MINI a PAPEL**" in seccion


def test_con_el_reglamento_de_hoy_la_puerta_del_real_esta_cerrada(tmp_path):
    malos = RR.compuertas_puerta(reg_real(tmp_path))
    assert malos[1:] == ["M0 está en PAPEL: el real solo corre con M0 en VIVA_MINI o VIVA → lo decide Ángelo en "
                     "reglamento.yaml (arreglo 140)."]
    assert RR.compuertas_puerta(reg_abierto(tmp_path)) == []       # con M0 en VIVA_MINI se abriría


@pytest.mark.parametrize("simular", [True, False])
def test_la_ronda_real_no_corre_ni_escribe_nada(tmp_path, monkeypatch, capsys, simular):
    r = reg_real(tmp_path)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ronda", "--modo", "real"] + (["--simular"] if simular else [])) == 2
    salida = capsys.readouterr().out
    assert "La ronda real NO corre" in salida and "❌ M0 está en PAPEL" in salida
    assert not RE.archivo_estado(r).exists() and not RR.archivo_boletos(r, "2026-11-15").exists()
    assert AR.leer_registro(r) == []                   # arreglo 186: con el interruptor apagado no escribe nada
    r = reg_abierto(tmp_path / "encendido", **{"estrategias.M0.estado": "PAPEL"})      # encendido, M0 en PAPEL
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ronda", "--modo", "real"] + (["--simular"] if simular else [])) == 2
    salida = capsys.readouterr().out
    assert "La ronda real NO corre. Falta:\n❌ M0 está en PAPEL" in salida
    assert not RE.archivo_estado(r).exists() and not RR.archivo_boletos(r, "2026-11-15").exists()
    filas = AR.leer_registro(r)
    assert (filas == []) if simular else (len(filas) == 1 and filas[0]["ok"] is False)


def _doctor(r, monkeypatch):
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    salida = []
    return doctor.revisar(r, imprimir=salida.append), "\n".join(salida)


def test_doctor_dice_que_el_real_no_corre(tmp_path, monkeypatch):
    codigo, texto = _doctor(reg_real(tmp_path), monkeypatch)
    assert ("ℹ️ Real: M0 está en PAPEL: la ronda real NO corre (el real necesita VIVA_MINI o VIVA). M0 regresó a PAPEL "
            "el 22 nov 2026 porque no pasó sus compuertas (DECISIÓN DE ÁNGELO); el papel sigue igual. Volver a real lo "
            "decide Ángelo en reglamento.yaml.") in texto
    assert codigo == 0                                  # solo informa: no es un ❌


def test_doctor_con_m0_vivo_dice_lo_de_antes(tmp_path, monkeypatch):
    _, texto = _doctor(reg_abierto(tmp_path), monkeypatch)
    assert "ℹ️ Real: M0 está en VIVA_MINI (el real necesita VIVA_MINI o VIVA)" in texto
    assert "NO corre" not in texto


def test_el_papel_sigue_con_m0():
    from sobreviviente import papel as P
    r = reglamento.cargar()
    activas = [k for k in P.MOTORES_V2 if r.estrategias.get(k, {}).get("estado") in ("PAPEL", "VIVA_MINI", "VIVA")]
    assert activas == ["M0"]
