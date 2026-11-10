"""Arreglo 53: un boleto mal formado o desconocido nunca se aprueba ni tumba la verificación; el registro de bots
aguanta renglones raros."""
import json

import test_arreglo34_verificar_completo as T34
from sobreviviente import archivos as AR
from sobreviviente import cli_ronda as CR
from sobreviviente import datos as D


def _verificar_lista(reg, tmp_path, monkeypatch, capsys, contenido):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    for b in contenido if isinstance(contenido, list) else []:
        if isinstance(b, dict) and b.get("accion") == "COMPRAR" and b.get("version_reglamento") == "":
            b["version_reglamento"] = r.version
    (tmp_path / "salida").mkdir(exist_ok=True)
    (tmp_path / "salida" / "boletos_2026-11-09.json").write_text(json.dumps(contenido), encoding="utf-8")
    info = {"symbols": [{"symbol": "ETHUSDT", "status": "TRADING", "filters": T34.FILTROS}]}
    monkeypatch.setattr(D.ClienteBinance, "exchange_info", lambda self, mercado="SPOT", forzar=False: info)
    monkeypatch.setattr(D.ClienteBinance, "spot", lambda self, ruta, params=None: {"price": "3000"})
    codigo = CR.verificar_boletos(r, "2026-11-09", ahora=T34.AHORA)
    return r, codigo, capsys.readouterr().out


def test_un_boleto_ilegible_no_tumba_la_revision_de_los_demas(reg, tmp_path, monkeypatch, capsys):
    bueno = T34._base("COMPRAR")
    _, codigo, salida = _verificar_lista(reg, tmp_path, monkeypatch, capsys, [bueno, "texto suelto", 123, None])
    assert codigo == 1 and "Traceback" not in salida
    assert f"✅ {bueno['boleto_id']}" in salida
    assert "❌ boleto #2 (ilegible): no es un boleto (formato raro): no lo pongas" in salida
    assert "❌ 3 boleto(s) NO se ponen" in salida


def test_boleto_con_campos_rotos_da_error_y_no_traceback(reg, tmp_path, monkeypatch, capsys):
    roto = T34._base("COMPRAR")
    roto["vence"] = "mañana en la tarde"                                  # fecha que no se puede leer
    sin_id = T34._base("MODIFICAR_STOP")
    del sin_id["boleto_id"]
    _, codigo, salida = _verificar_lista(reg, tmp_path, monkeypatch, capsys, [roto, sin_id])
    assert codigo == 1 and "Traceback" not in salida
    assert f"❌ {roto['boleto_id']}: boleto mal formado (ValueError): no lo pongas" in salida
    assert "❌ boleto #2 (sin id): no trae boleto_id" in salida


def test_accion_o_tipo_desconocido_no_se_aprueba(reg, tmp_path, monkeypatch, capsys):
    raro = {**T34._base("CERRAR"), "boleto_id": "x-vender-todo", "accion": "VENDER_TODO"}
    otro = {**T34._base("CERRAR"), "boleto_id": "x-cerrar-raro", "tipo_orden": "LIMIT_RARO"}
    _, codigo, salida = _verificar_lista(reg, tmp_path, monkeypatch, capsys, [raro, otro])
    assert codigo == 1
    assert "❌ x-vender-todo: acción desconocida (VENDER_TODO): no lo pongas" in salida
    assert "❌ x-cerrar-raro: tipo de orden desconocido para cerrar (LIMIT_RARO): no lo pongas" in salida


def test_archivo_de_boletos_que_no_es_lista(reg, tmp_path, monkeypatch, capsys):
    r, codigo, salida = _verificar_lista(reg, tmp_path, monkeypatch, capsys, {"boletos": "no es lista"})
    assert codigo == 1 and "no trae una lista de boletos: no pongas nada" in salida and "Traceback" not in salida
    assert AR.leer_registro(r)[-1]["ok"] is False


def test_los_boletos_buenos_siguen_pasando(reg, tmp_path, monkeypatch, capsys):
    buenos = [T34._base("COMPRAR"), T34._base("MODIFICAR_STOP"), T34._base("CERRAR"),
              T34._base("CERRAR", tipo="YA_EJECUTADO_POR_STOP")]
    for i, b in enumerate(buenos):
        b["boleto_id"] += f"-{i}"
    _, codigo, salida = _verificar_lista(reg, tmp_path, monkeypatch, capsys, buenos)
    assert codigo == 0 and salida.count("✅") == 4 and "👍 Todos los boletos cumplen el reglamento." in salida


def test_ensayo_con_archivo_de_boletos_raro_no_truena(reg, tmp_path, monkeypatch, capsys):
    from argparse import Namespace
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    monkeypatch.setattr(CR, "_reg", lambda args: r)
    monkeypatch.setattr(CR, "RAIZ", tmp_path)
    (tmp_path / "salida").mkdir()
    for contenido in ({"no": "lista"}, ["texto", 5, {"sin": "id"}]):
        (tmp_path / "salida" / "boletos_2026-11-09.json").write_text(json.dumps(contenido), encoding="utf-8")
        args = Namespace(boleto="20261109-C-COM-BTC-abc", ensayo=True, simbolo=None, cantidad=None, precio=None, stop=None,
                         bot="EJECUTOR", reglamento=None)
        assert CR.cmd_registrar_llenado(args) == 1
        assert "❌ No existe el boleto 20261109-C-COM-BTC-abc." in capsys.readouterr().out


def test_registro_con_renglones_raros_no_tumba_nada(reg, tmp_path):
    r = reg.copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    AR.registrar_tarea(r, "RADAR", "verificar", True)
    arch = tmp_path / "datos" / "bots" / "registro.jsonl"
    nl = chr(10).encode()
    with open(arch, "ab") as f:
        f.write(b"123" + nl + b'"texto"' + nl + bytes([0xFF, 0xFE]) + nl + b"[" * 100000 + nl
                + json.dumps({"bot": "RADAR", "cuando": 5}).encode() + nl
                + json.dumps({"bot": "CONTADOR", "cuando": "2099-01-01T00:00:00", "ok": True, "a_tiempo": True}).encode() + nl)
    filas = AR.leer_registro(r)
    assert all(isinstance(f, dict) for f in filas) and len(filas) == 3
    cal = AR.calificacion_bots(r, 7)
    assert cal["RADAR"]["tareas"] == 1 and cal["CONTADOR"]["tareas"] == 1       # fecha sin zona: se acepta
