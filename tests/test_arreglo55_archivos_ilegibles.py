"""Arreglo 55: un archivo de bot ilegible (anidado sin fin, bytes raros) se trata como "viene mal" (MODO SEGURO),
no como un error técnico que tumba la ronda. Y un conciliacion.json raro cuenta como "no cuadra"."""
import pytest

from sobreviviente import archivos as AR
from sobreviviente import papel as P

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_papel import _datos_dia

ANIDADO = "[" * 200000


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    (tmp_path / "datos" / "papel").mkdir(parents=True)
    return r


@pytest.mark.parametrize("nombre", ["vetos.json", "eventos.json", "exclusiones.json"])
def test_archivo_anidado_sin_fin_es_invalido_no_un_error_tecnico(reg, tmp_path, nombre):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / nombre).write_text(ANIDADO, encoding="utf-8")
    d, errores = AR.leer(r, nombre)
    assert d is None and errores == [f"{nombre} no es JSON válido (demasiados niveles anidados)"]


def test_archivo_con_bytes_raros_es_invalido(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / "vetos.json").write_bytes(bytes([0xFF, 0xFE, 0x81]))
    d, errores = AR.leer(r, "vetos.json")
    assert d is None and "vetos.json no es JSON válido" in errores[0]


def test_ronda_con_vetos_ilegible_va_en_modo_seguro(reg, tmp_path):
    r = _reg_m0(reg, tmp_path, capital=1000.0)
    k = _dia_marea_alta(r)
    (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "datos" / "vetos.json").write_text(ANIDADO, encoding="utf-8")
    out = P.ronda(r, _datos_dia(r, k)[0])                                  # no truena
    assert out["modo_seguro"] is True
    assert not [b for c in out["carteras"].values() for b in c["boletos"] if b["accion"] == "COMPRAR"]
    assert "MODO SEGURO" in P.resumen_corto(out) and "vetos.json viene mal" in P.resumen_corto(out)


@pytest.mark.parametrize("contenido", [b"[1, 2]", b'"ok"', bytes([0xFF, 0xFE]), ANIDADO.encode(), b"{roto"])
def test_conciliacion_rara_cuenta_como_que_no_cuadra(reg, tmp_path, contenido):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / "papel" / "conciliacion.json").write_bytes(contenido)
    assert P.conciliacion_ok(r) is False


def test_conciliacion_buena_sigue_contando(reg, tmp_path):
    r = _reg_tmp(reg, tmp_path)
    (tmp_path / "datos" / "papel" / "conciliacion.json").write_text('{"ok": true}', encoding="utf-8")
    assert P.conciliacion_ok(r) is True
    (tmp_path / "datos" / "papel" / "conciliacion.json").write_text('{"ok": false}', encoding="utf-8")
    assert P.conciliacion_ok(r) is False
