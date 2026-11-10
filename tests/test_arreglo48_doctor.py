"""Arreglo 48: pruebas de `doctor` (revisa la computadora de Grok Bot). Sin red: las visitas a internet son falsas."""
import requests

from sobreviviente import doctor


def _reg_tmp(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    return r


class _Respuesta:
    def __init__(self, codigo):
        self.status_code = codigo


def _internet(monkeypatch, caidos=(), codigos=None):
    """`caidos`: pedazos de URL sin conexión. `codigos`: pedazo de URL → código HTTP distinto de 200."""
    visitas = []

    def get(url, timeout=None, headers=None):
        visitas.append((url, headers))
        if any(c in url for c in caidos):
            raise requests.ConnectionError("sin conexión")
        for pedazo, codigo in (codigos or {}).items():
            if pedazo in url:
                return _Respuesta(codigo)
        return _Respuesta(200)

    monkeypatch.setattr(doctor.requests, "get", get)
    return visitas


def _correr(reg):
    lineas = []
    return doctor.revisar(reg, imprimir=lineas.append), "\n".join(lineas)


def test_todo_bien(reg, tmp_path, monkeypatch):
    r = _reg_tmp(reg, tmp_path)
    visitas = _internet(monkeypatch)
    codigo, texto = _correr(r)
    assert codigo == 0 and "❌" not in texto and texto.endswith("👍 Todo listo.")
    assert "✅ Binance Spot (respaldo oficial): responde" in texto
    assert f"✅ Se puede escribir en {tmp_path / 'datos'}" in texto
    assert "✅ vetos.json: todavía no existe (se crea vacío; está bien)" in texto
    assert "✅ Sin llaves de Binance en la carpeta (correcto)" in texto
    assert len(visitas) == 4 and all("X-MBX" not in str(h) for _, h in visitas)      # solo rutas públicas, sin llaves
    assert list((tmp_path / "datos").iterdir()) == []                              # la prueba de escritura no deja basura


def test_sin_el_respaldo_oficial_es_falla(reg, tmp_path, monkeypatch):
    r = _reg_tmp(reg, tmp_path)
    _internet(monkeypatch, caidos=["data-api.binance.vision"])
    codigo, texto = _correr(r)
    assert codigo == 1
    assert "❌ Binance Spot (respaldo oficial): sin conexión (ConnectionError)" in texto
    assert "→ Sin esto no hay datos." in texto and "Hay 1 renglón(es) con ❌" in texto


def test_lo_no_indispensable_solo_avisa(reg, tmp_path, monkeypatch):
    r = _reg_tmp(reg, tmp_path)
    _internet(monkeypatch, caidos=["fapi.binance.com"], codigos={"api.binance.com/api/v3/ping": 451})
    codigo, texto = _correr(r)
    assert codigo == 0 and "❌" not in texto and texto.endswith("👍 Todo listo.")
    assert "⚠️ Binance Spot (principal): responde 451" in texto                      # bloqueo por país: normal
    assert "⚠️ Binance Futuros (ESTELA): sin conexión (ConnectionError)" in texto
    assert "Sin esto ESTELA (M3) se queda apagada" in texto


def test_archivo_de_bot_mal_escrito_y_llave_en_la_carpeta(reg, tmp_path, monkeypatch):
    r = _reg_tmp(reg, tmp_path)
    _internet(monkeypatch)
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "vetos.json").write_text('{"vetos": "no es lista"}', encoding="utf-8")
    (tmp_path / "datos" / "eventos.json").write_text('{"eventos": []}', encoding="utf-8")
    (tmp_path / "binance.key").write_text("no debería estar aquí", encoding="utf-8")
    codigo, texto = _correr(r)
    assert codigo == 1 and "Hay 2 renglón(es) con ❌" in texto
    assert "❌ vetos.json: falta la lista 'vetos'" in texto and "la ronda va en modo seguro" in texto
    assert "✅ eventos.json bien escrito" in texto
    assert "❌ Sin llaves de Binance en la carpeta (correcto)" in texto and "Borra cualquier llave" in texto


def test_carpeta_de_datos_sin_permiso(reg, tmp_path, monkeypatch):
    estorbo = tmp_path / "datos"
    estorbo.write_text("soy un archivo, no una carpeta", encoding="utf-8")
    r = _reg_tmp(reg, tmp_path)
    _internet(monkeypatch)
    codigo, texto = _correr(r)
    assert codigo == 1 and f"❌ No se puede escribir en {estorbo}" in texto
    assert "Da permiso de escritura a la carpeta datos/." in texto
