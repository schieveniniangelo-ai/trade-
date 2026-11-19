"""Arreglo 186 (I10, DECISIÓN DE ÁNGELO, ventana del domingo 22 nov 2026): interruptor `real.activo` en reglamento.yaml.

En el reglamento queda en false. Con false, todo comando que mande o anote órdenes reales sale sin hacer nada y con un
aviso claro: `ronda --modo real` (también con --simular), `ronda --verificar --real` y `registrar-llenado --real`. No
escriben estado, boletos, llenados ni registro. Lo que solo lee o vigila (registrar-saldo, conciliar --real, reportes)
sigue igual. `doctor` muestra el interruptor. Solo `true` exacto lo enciende (falla cerrada)."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import doctor
from sobreviviente import papel as P
from sobreviviente import real as RE
from sobreviviente import reglamento
from sobreviviente import ronda_real as RR

from apoyo_real import AHORA, reg_abierto, reg_real
from test_arreglo134_entradas_real import mundo  # noqa: F401 - fixture
from test_arreglo136_llenados_real import compra  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
APAGADO = "⛔ El dinero real está APAGADO (real.activo: false en reglamento.yaml, DECISIÓN DE ÁNGELO): "


def test_el_reglamento_lo_trae_apagado():
    r = reglamento.cargar()
    assert r.datos["real"]["activo"] is False and RE.real_activo(r) is False
    texto = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    (linea,) = [x for x in texto.splitlines() if x.strip().startswith("activo: false") and "Arreglo 186" in x]
    assert "interruptor del dinero real" in linea
    cambios = (RAIZ / "CAMBIOS.md").read_text(encoding="utf-8")
    assert "Arreglo 186" in cambios[cambios.index("## Reglamento 2.0.3"):]


@pytest.mark.parametrize("valor,activo", [(True, True), (False, False), ("true", False), (1, False), (None, False)])
def test_solo_true_exacto_lo_enciende(tmp_path, valor, activo):
    r = reg_real(tmp_path, **{"real.activo": valor})
    assert RE.real_activo(r) is activo
    r.datos["real"].pop("activo")
    assert RE.real_activo(r) is False                  # si falta, apagado


def test_validar_pide_true_o_false():
    with pytest.raises(reglamento.ErrorReglamento) as e:
        reglamento.validar(reglamento.cargar().copia_con({"real.activo": "si"}))
    assert "real.activo = si: debe ser true o false (arreglo 186)." in e.value.problemas
    reglamento.validar(reglamento.cargar().copia_con({"real.activo": True}))


def test_la_puerta_lo_dice_primero(tmp_path):
    malos = RR.compuertas_puerta(reg_abierto(tmp_path, **{"real.activo": False}))
    assert malos == ["el interruptor real.activo está en false: el dinero real está APAGADO → lo enciende Ángelo en "
                     "reglamento.yaml (arreglo 186)."]
    assert RR.compuertas_puerta(reg_abierto(tmp_path)) == []


@pytest.mark.parametrize("simular", [False, True])
def test_ronda_real_apagada_no_hace_nada(tmp_path, monkeypatch, capsys, simular):
    r = reg_abierto(tmp_path, **{"real.activo": False})
    monkeypatch.setattr(P, "preparar_datos", lambda *a, **k: pytest.fail("con el real apagado no se piden datos"))
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ronda", "--modo", "real"] + (["--simular"] if simular else [])) == 2
    salida = capsys.readouterr().out
    assert salida == (f"████ REAL ████ La ronda real NO corre: {APAGADO}ronda --modo real no hizo nada (no se mandó, no "
                      f"se aprobó y no se anotó ninguna orden real). Encenderlo lo decide Ángelo en reglamento.yaml, en "
                      f"la ventana del domingo.\n")
    assert not RE.ruta_real(r).exists() and AR.leer_registro(r) == []
    assert not RR.archivo_boletos(r, "2026-11-15").exists()


def test_ronda_real_apagada_dice_ademas_lo_que_falta(tmp_path, capsys):
    r = reg_real(tmp_path)                                # el reglamento de hoy: apagado y M0 en PAPEL
    assert RR.correr(r, AHORA, cliente=object(), memes=[]) == 2
    salida = capsys.readouterr().out
    assert salida.startswith(f"████ REAL ████ La ronda real NO corre: {APAGADO}")
    assert "\nAdemás falta:\n❌ M0 está en PAPEL" in salida
    assert not RE.ruta_real(r).exists() and AR.leer_registro(r) == []


def test_registrar_llenado_real_apagado_no_anota(compra, monkeypatch, capsys):
    r, b, _ = compra
    assert RE.registrar_llenado(r, b["boleto_id"], "COMPRA_ENVIADA", ahora=AHORA + timedelta(minutes=1),
                                precio_actual=70000.0)[0]
    antes = RE.archivo_llenados(r).read_bytes()
    estado = RE.archivo_estado(r).read_bytes()
    filas = len(AR.leer_registro(r))
    r.datos["real"]["activo"] = False
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA",
                      "--motivo", "EXPIRED"]) == 2
    assert capsys.readouterr().out == (f"{APAGADO}registrar-llenado --real no hizo nada (no se mandó, no se aprobó y no se "
                                       f"anotó ninguna orden real). Encenderlo lo decide Ángelo en reglamento.yaml, en "
                                       f"la ventana del domingo.\n")
    assert RE.archivo_llenados(r).read_bytes() == antes and RE.archivo_estado(r).read_bytes() == estado
    assert len(AR.leer_registro(r)) == filas
    r.datos["real"]["activo"] = True                     # encendido, el mismo comando sí anota
    assert MAIN.main(["registrar-llenado", "--real", "--boleto", b["boleto_id"], "--evento", "COMPRA_NO_LLENADA",
                      "--motivo", "EXPIRED"]) == 0
    assert RE.leer_llenados(r)[-1]["evento"] == "COMPRA_NO_LLENADA"


def test_verificar_real_apagado_no_aprueba(compra, monkeypatch, capsys):
    r, b, _ = compra
    filas = len(AR.leer_registro(r))
    r.datos["real"]["activo"] = False
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    assert MAIN.main(["ronda", "--verificar", "--real"]) == 2
    salida = capsys.readouterr().out
    assert salida.startswith(f"{APAGADO}ronda --verificar --real no hizo nada") and "✅" not in salida
    assert len(AR.leer_registro(r)) == filas


def test_lo_que_solo_vigila_sigue_igual(compra, monkeypatch, capsys):
    r, b, foto = compra
    r.datos["real"]["activo"] = False
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    capsys.readouterr()
    MAIN.main(["conciliar", "--real"])
    salida = capsys.readouterr().out
    assert "APAGADO" not in salida and json.loads(RE.archivo_conciliacion(r).read_text(encoding="utf-8"))
    assert foto()[0] is True                              # registrar-saldo (la foto) también


def _doctor(r, monkeypatch):
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    salida = []
    return doctor.revisar(r, imprimir=salida.append), "\n".join(salida)


def test_doctor_muestra_el_interruptor(tmp_path, monkeypatch):
    codigo, texto = _doctor(reg_real(tmp_path), monkeypatch)
    assert ("ℹ️ Real: interruptor real.activo: false → el dinero real está APAGADO: ronda --modo real, ronda "
            "--verificar --real y registrar-llenado --real salen sin hacer nada. Encenderlo lo decide Ángelo.") in texto
    assert codigo == 0                                   # solo informa
    _, texto = _doctor(reg_abierto(tmp_path / "encendido"), monkeypatch)
    assert "ℹ️ Real: interruptor real.activo: true (el dinero real está encendido)" in texto and "APAGADO" not in texto
