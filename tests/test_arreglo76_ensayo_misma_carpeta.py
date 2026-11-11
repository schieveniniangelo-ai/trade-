"""Arreglo 76: el ensayo del Ejecutor (registrar-llenado) busca los boletos en la misma carpeta que la ronda y
`ronda --verificar` (la `salida/` junto a `datos.carpeta` del reglamento), no en la raíz del paquete.

Sin red ni llaves: todo en carpetas temporales."""
import json
from argparse import Namespace

from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR

BOLETO = {"boleto_id": "20261109-C-COM-BTC-abc12345", "accion": "COMPRAR", "simbolo": "BTCUSDT", "cantidad": 0.00018,
          "precio_entrada": 75000.0, "stop": 63750.0}
NOMBRE = "boletos_2026-11-09.json"


def _preparar(reg, tmp_path, monkeypatch):
    """Reglamento con `datos.carpeta` en tmp/otro/datos y una RAIZ falsa (tmp/raiz) distinta de esa carpeta."""
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "otro" / "datos")})
    r.ruta = tmp_path / "otro" / "reglamento.yaml"
    (tmp_path / "otro" / "datos").mkdir(parents=True)
    raiz = tmp_path / "raiz"
    (raiz / "salida").mkdir(parents=True)
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    monkeypatch.setattr(CR, "RAIZ", raiz)
    return r, raiz


def _ensayo(**kw):
    args = {"boleto": BOLETO["boleto_id"], "ensayo": True, "simbolo": "BTCUSDT", "cantidad": 0.00018, "precio": 75000.0,
            "stop": 63750.0, "bot": "EJECUTOR", "reglamento": None}
    args.update(kw)
    return CR.cmd_registrar_llenado(Namespace(**args))


def test_ensayo_encuentra_el_boleto_en_la_carpeta_del_reglamento(reg, tmp_path, monkeypatch, capsys):
    r, _ = _preparar(reg, tmp_path, monkeypatch)
    salida = tmp_path / "otro" / "salida"
    assert AR.carpeta_datos(r).parent / "salida" == salida        # la misma que usan la ronda y --verificar
    salida.mkdir()
    (salida / NOMBRE).write_text(json.dumps([BOLETO]), encoding="utf-8")
    assert _ensayo() == 0
    assert "👍 Copiado igualito al boleto." in capsys.readouterr().out
    fila = AR.leer_registro(r)[-1]
    assert fila["bot"] == "EJECUTOR" and fila["ok"] is True and fila["diferencias"] == 0


def test_ensayo_no_lee_el_archivo_de_la_raiz_del_paquete(reg, tmp_path, monkeypatch, capsys):
    r, raiz = _preparar(reg, tmp_path, monkeypatch)
    (raiz / "salida" / NOMBRE).write_text(json.dumps([BOLETO]), encoding="utf-8")   # solo existe en RAIZ/salida
    assert _ensayo() == 1
    assert f"❌ No encuentro el archivo de boletos de ese día ({NOMBRE})." in capsys.readouterr().out
    fila = AR.leer_registro(r)[-1]
    assert fila["ok"] is False and fila["tarea"] == "registrar-llenado"
