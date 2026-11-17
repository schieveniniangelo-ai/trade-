"""Arreglo 159: escalones sin verificar bloquean la activación de F1 (SOLO PAPEL).

DECISIÓN DE ÁNGELO 2026-11-17: con `activo: true`, `config.leer` se niega si alguna moneda de F1 tiene sus escalones
sin verificar, y `futuros-papel` se queda en modo muestra con el aviso (sale 0, no es un límite duro roto). Ninguna
prueba escribe `activo: true` en un archivo del repo ni afirma que F1 pase.
"""
from __future__ import annotations

import pytest

from apoyo_futuros import ClienteFalso, escalones_verificados
from sobreviviente import reglamento as RGL
from sobreviviente.futuros import cartera as C
from sobreviviente.futuros import cli as FC
from sobreviviente.futuros import config
from sobreviviente.futuros import liquidacion as LQ


@pytest.fixture
def reg(tmp_path):
    return RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})


@pytest.fixture
def activo(reg):
    return reg.copia_con({"futuros_papel.activo": True})


# --- Con el escalones.json REAL (sin parchar _tabla) ---

def test_leer_con_activo_y_escalones_sin_verificar_lanza(activo):
    faltan = LQ.sin_verificar(config.MONEDAS_PERMITIDAS)
    assert faltan                                        # hoy el json real sigue sin verificar
    with pytest.raises(config.ErrorConfigFuturos) as e:
        config.leer(activo)
    texto = str(e.value)
    assert "escalones sin verificar" in texto
    for s in faltan:
        assert s in texto
    assert "SOLUSDT" in texto


def test_leer_con_el_reglamento_de_hoy_no_lanza(reg):
    cfg = config.leer(reg)
    assert cfg["activo"] is False


def test_leer_sin_exigir_activacion_no_lanza(activo):
    cfg = config.leer(activo, exigir_activacion=False)
    assert cfg["activo"] is True
    assert config.escalones_pendientes(cfg) == LQ.sin_verificar(cfg["monedas"])


def test_un_limite_duro_sigue_lanzando_aunque_no_se_exija_activacion(reg):
    mal = reg.copia_con({"futuros_papel.activo": True, "futuros_papel.apalancamiento_tope": 5})
    with pytest.raises(config.ErrorConfigFuturos):
        config.leer(mal, exigir_activacion=False)


def test_correr_con_activo_y_escalones_sin_verificar_queda_en_muestra(activo, monkeypatch):
    monkeypatch.setattr(FC, "validacion_pasa", lambda r: True)      # aunque el informe dijera PASA
    out = FC.correr(activo, ClienteFalso(activo))
    assert out["modo"] == "muestra"
    av = [a for a in out["avisos"] if a.startswith("escalones sin verificar:")]
    assert len(av) == 1 and "SOLUSDT" in av[0]
    assert not any("no dice «PASA»" in a for a in out["avisos"])
    assert not C.ruta_estado(activo).exists()


def test_correr_sin_pasa_y_sin_escalones_avisa_escalones_primero(activo):
    out = FC.correr(activo, ClienteFalso(activo))
    assert out["modo"] == "muestra"
    assert any(a.startswith("escalones sin verificar:") for a in out["avisos"])
    assert not any("no dice «PASA»" in a for a in out["avisos"])
    assert not C.ruta_estado(activo).exists()


def test_comando_con_activo_y_escalones_sin_verificar_sale_0_en_muestra(activo, capsys):
    assert FC.comando(activo, None, ClienteFalso(activo)) == 0
    texto = capsys.readouterr().out
    assert texto.splitlines()[0] == "🧪 PAPEL DE FUTUROS — no es una orden"
    assert "MUESTRA" in texto and "escalones sin verificar:" in texto
    assert "❌" not in texto
    assert not C.ruta_estado(activo).exists()


def test_comando_con_otro_error_de_limites_sigue_saliendo_1(reg, capsys):
    mal = reg.copia_con({"futuros_papel.activo": True, "futuros_papel.margen": "CRUZADO"})
    assert FC.comando(mal, None, ClienteFalso(mal)) == 1
    assert "❌" in capsys.readouterr().out


# --- Con un json FALSO todo verificado (el patrón del 161) ---

def test_leer_con_escalones_verificados_ya_no_lanza(activo, monkeypatch):
    escalones_verificados(monkeypatch)
    cfg = config.leer(activo)
    assert cfg["activo"] is True and config.escalones_pendientes(cfg) == []


def test_con_escalones_verificados_sigue_valiendo_el_pasa(activo, monkeypatch):
    escalones_verificados(monkeypatch)
    out = FC.correr(activo, ClienteFalso(activo))
    assert out["modo"] == "muestra"
    assert any("no dice «PASA»" in a for a in out["avisos"])
    assert not any(a.startswith("escalones sin verificar:") for a in out["avisos"])
    assert not C.ruta_estado(activo).exists()


def test_nada_pone_activo_true_en_produccion():
    assert config.POR_DEFECTO["activo"] is False
    assert RGL.cargar().get("futuros_papel") is None
