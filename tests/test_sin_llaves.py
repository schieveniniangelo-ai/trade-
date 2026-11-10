"""Arreglo 21: el código no usa llaves ni firmas de Binance (solo rutas públicas)."""
import ast
import io
import tokenize
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROHIBIDO = ("x-mbx-apikey", "apikey", "hmac", "signature=", "api_key", "secret")
MENSAJE = ("Aparecieron llaves o firmas en el código: hoy solo se usan rutas públicas de Binance. "
           "Si Ángelo decidió pasar a dinero real, cambia esta prueba a propósito.")


def _lineas_de_boletos(fuente: str) -> set[int]:
    """Líneas de la función texto_boleto (el texto de los boletos se ignora)."""
    out = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "texto_boleto":
            out.update(range(nodo.lineno, (nodo.end_lineno or nodo.lineno) + 1))
    return out


def _codigo_sin_comentarios(fuente: str) -> list[tuple[int, str]]:
    piezas = []
    for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
        if tok.type != tokenize.COMMENT:
            piezas.append((tok.start[0], tok.string))
    return piezas


def test_sin_llaves_ni_firmas_en_el_codigo():
    hallazgos = []
    archivos = sorted(a for a in (RAIZ / "sobreviviente").rglob("*.py") if "tests" not in a.relative_to(RAIZ).parts)
    assert any(a.parent.name == "estrategias" for a in archivos)   # también revisa las subcarpetas
    for arch in archivos:
        fuente = arch.read_text(encoding="utf-8-sig")  # igual que Python: ignora la marca BOM si la hay
        ignorar = _lineas_de_boletos(fuente)
        for linea, texto in _codigo_sin_comentarios(fuente):
            if linea in ignorar:
                continue
            bajo = texto.lower()
            for p in PROHIBIDO:
                if p in bajo:
                    hallazgos.append(f"{arch.relative_to(RAIZ)}:{linea}: {p}")
    assert not hallazgos, MENSAJE + " " + "; ".join(hallazgos)


def test_gitignore_protege_las_llaves():
    texto = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    for p in (".env", "*.key", "secret"):
        assert p in texto, MENSAJE + f" (falta '{p}' en .gitignore)"
