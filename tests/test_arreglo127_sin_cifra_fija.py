"""Arreglo 127: ningún «46.18» escrito a mano en sobreviviente/; todo lee el capital del reglamento.

Si falta la clave, error claro (nunca 46.18 de respaldo). Los comentarios de historia sí pueden mencionar la cifra."""
import io
import tokenize
from pathlib import Path
from types import SimpleNamespace

import pytest

from sobreviviente import futuros_capital as FC
from sobreviviente import papel as P
from sobreviviente import reglamento as RGL

PAQUETE = Path(__file__).resolve().parent.parent / "sobreviviente"


def test_no_queda_46_18_en_el_codigo():
    """Busca en los números y textos del código (no en los comentarios, que pueden contar la historia)."""
    malos = []
    for arch in sorted(PAQUETE.rglob("*.py")):
        fuente = arch.read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
            if tok.type in (tokenize.NUMBER, tokenize.STRING, tokenize.FSTRING_MIDDLE) and "46.18" in tok.string:
                malos.append(f"{arch.name}:{tok.start[0]}")
    assert not malos, f"Queda 46.18 escrito a mano en: {malos}"


def _sin(reg, clave):
    r = reg.copia_con({})
    seccion, _, hoja = clave.rpartition(".")
    del r.datos[seccion][hoja]
    return r


def test_sin_capital_en_el_reglamento_error_claro(reg, tmp_path):
    r = _sin(reg.copia_con({"datos.carpeta": str(tmp_path / "datos")}), "carteras.capital_inicial")
    with pytest.raises(RGL.ErrorReglamento) as e:
        P.cargar_estado(r, "A", "2026-11-16")
    assert "carteras.capital_inicial" in str(e.value) and "respaldo" in str(e.value)
    assert "46.18" not in str(e.value)


def test_cifra_rechaza_textos_y_vacios(reg):
    for valor in (None, "142.54", True):
        with pytest.raises(RGL.ErrorReglamento):
            reg.copia_con({"carteras.capital_inicial": valor}).cifra("carteras.capital_inicial")
    assert reg.copia_con({"carteras.capital_inicial": 100}).cifra("carteras.capital_inicial") == 100.0


def test_futuros_capital_sin_capital_real_no_inventa(reg, tmp_path, monkeypatch):
    import pandas as pd
    r = _sin(reg, "backtest.capital_real")

    class Cliente:
        def __init__(self, _r):
            self.cache = tmp_path / "cache"

        def exchange_info(self, mercado="SPOT", forzar=False):
            return {"symbols": [{"symbol": "AUSDT", "status": "TRADING", "filters": []}]}
    velas = pd.DataFrame({c: [1.0] for c in ("open", "high", "low", "close")},
                         index=pd.DatetimeIndex(["2026-11-01"], tz="UTC"))
    monkeypatch.setattr(FC.D, "ClienteBinance", Cliente)
    monkeypatch.setattr(FC.D, "leer", lambda ruta: velas)
    monkeypatch.setattr(FC.D, "resamplear", lambda df, _: df)
    monkeypatch.setattr(FC, "filas", lambda *a, **k: [])
    with pytest.raises(RGL.ErrorReglamento) as e:
        FC.comando(r, SimpleNamespace(simbolos=["AUSDT"], capital=None), avisar=lambda *_: None)
    assert "backtest.capital_real" in str(e.value)
    salida = []
    assert FC.comando(r, SimpleNamespace(simbolos=["AUSDT"], capital=99.0), avisar=salida.append) == 0
    assert "99.00 USDT" in salida[0]
