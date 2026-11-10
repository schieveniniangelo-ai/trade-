"""Pruebas del validador del reglamento: si las reglas chocan, el motor no corre."""
import pytest

from sobreviviente import reglamento
from sobreviviente.reglamento import ErrorReglamento, validar


def test_reglamento_real_es_valido():
    r = reglamento.cargar()
    assert r.version
    assert r.riesgo_pct_estrategia("E1") == 1.0
    assert r.riesgo_pct_estrategia("E4") == 0.5
    assert r.get("riesgo.futuros.apalancamiento_max") == 2
    assert r.get("no.existe", "x") == "x"


def test_archivo_inexistente(tmp_path):
    with pytest.raises(ErrorReglamento, match="No encuentro"):
        reglamento.cargar(tmp_path / "nada.yaml")


def test_archivo_vacio(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("")
    with pytest.raises(ErrorReglamento, match="vacío"):
        reglamento.cargar(p)


def test_carga_sin_validar(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("version: '9'\n")
    r = reglamento.cargar(p, validar_al_cargar=False)
    assert r.version == "9"
    with pytest.raises(ErrorReglamento, match="Falta"):
        validar(r)


def _base():
    return reglamento.cargar()


@pytest.mark.parametrize(
    "cambios, texto",
    [
        ({"riesgo.calor_total_max_pct": 0.5}, "calor total"),
        ({"riesgo.calor_total_max_pct": 5.0}, "tope diario"),
        ({"riesgo.tope_semanal_pct": 2.0}, "menor a mayor"),
        ({"riesgo.futuros.margen": "CRUZADO"}, "AISLADO"),
        ({"riesgo.futuros.apalancamiento_max": 5}, "apalancamiento"),
        ({"riesgo.exposicion_max_posicion_spot_pct": 0.8, "riesgo.calor_total_max_pct": 1.0}, "exposición"),
        ({"riesgo.cubeta_memes_max_pct": 0.2}, "cubeta de memes"),
        ({"riesgo.costos.multiplo_minimo": 0.5}, "múltiplo"),
        ({"riesgo.tope_diario_pct": 150}, "porcentaje"),
        ({"riesgo.posiciones_max": {"normales": 0, "memes": 0, "futuros": 0}}, "suman 0"),
        ({"riesgo.riesgo_por_estrategia_pct": {"E3": 0, "E4": 0.5}}, "riesgo de E3"),
    ],
)
def test_choques_detectados(cambios, texto):
    r = _base().copia_con(cambios)
    with pytest.raises(ErrorReglamento) as e:
        validar(r)
    assert texto in str(e.value)


@pytest.mark.parametrize(
    "campo, valor, texto",
    [
        ("estado", "PRENDIDA", "estado"),
        ("mercado", "MARGEN", "mercado"),
        ("lado", "ARRIBA", "lado"),
        ("cubeta", "otra", "cubeta"),
        ("parametros", {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}, "parámetros"),
    ],
)
def test_estrategia_invalida(campo, valor, texto):
    r = _base().copia_con({f"estrategias.E1.{campo}": valor})
    with pytest.raises(ErrorReglamento) as e:
        validar(r)
    assert texto in str(e.value)


def test_corto_en_spot_prohibido():
    r = _base().copia_con({"estrategias.E1.lado": "CORTO"})
    with pytest.raises(ErrorReglamento, match="corto en Spot"):
        validar(r)


def test_futuros_pide_mas_apalancamiento():
    r = _base().copia_con({"estrategias.E5.apalancamiento": 3})
    with pytest.raises(ErrorReglamento, match="pide 3x"):
        validar(r)


def test_memes_vivas_sin_permiso():
    r = _base().copia_con({"estrategias.E4.estado": "VIVA_MINI", "estrategias.E4.permitir_vivo": False})
    with pytest.raises(ErrorReglamento, match="solo van en papel"):
        validar(r)


def test_falta_valor():
    r = _base()
    del r.datos["riesgo"]["tope_diario_pct"]
    with pytest.raises(ErrorReglamento, match="tope_diario_pct"):
        validar(r)


def test_minimo_binance_alcanzable():
    r = _base()
    # 46 USDT × 30 % = 13.8 USDT de posición máxima
    assert validar(r, {"capital": 46.18, "minimos": [1, 5, 5]}) == []
    avisos = validar(r, {"capital": 46.18, "minimos": [5, 100]})
    assert "1 de 2" in avisos[0]
    with pytest.raises(ErrorReglamento, match="ninguna moneda"):
        validar(r, {"capital": 10, "minimos": [5, 10]})


def test_error_explica_en_espanol():
    e = ErrorReglamento(["algo"])
    assert "NO va a operar" in str(e)
    assert e.problemas == ["algo"]


def test_atajo_costos():
    assert _base().costos["comision_spot_pct"] == 0.10
