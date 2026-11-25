"""Arreglo 206: `registrar-permisos` revisa los permisos de la llave de Binance desde un archivo guardado.

EJECUTOR guarda tal cual la respuesta de GET /sapi/v1/account/apiRestrictions y corre
`registrar-permisos --archivo <json>`. Retiros, Futuros, Margen, transferencias internas y universales y opciones deben
estar en false; Spot en true; ipRestrict en true solo se recomienda (aviso). El resultado va a datos/real/permisos.json
y doctor lo muestra con su fecha. El programa no usa llaves ni llama a la red, y la ronda real NO lo exige (eso lo
decide Ángelo después). Sin red.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from sobreviviente import __main__ as MAIN
from sobreviviente import doctor
from sobreviviente import permisos as PM
from sobreviviente import reglamento as RGL

BUENO = {"ipRestrict": True, "createTime": 1700000000000, "enableInternalTransfer": False, "enableFutures": False,
         "enablePortfolioMarginTrading": False, "enableVanillaOptions": False, "permitsUniversalTransfer": False,
         "enableReading": True, "enableSpotAndMarginTrading": True, "enableWithdrawals": False, "enableMargin": False}


@pytest.fixture
def reg(tmp_path):
    r = RGL.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos")})
    r.ruta = tmp_path / "reglamento.yaml"
    return r


def _archivo(tmp_path, datos, nombre="apiRestrictions.json"):
    a = tmp_path / nombre
    a.write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding="utf-8")
    return a


def test_la_llave_bien_configurada_pasa(reg, tmp_path):
    ahora = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)
    res = PM.registrar(reg, _archivo(tmp_path, BUENO), ahora)
    assert res["ok"] and res["problemas"] == [] and res["avisos"] == []
    guardado = json.loads(PM.ruta(reg).read_text(encoding="utf-8"))
    assert guardado["ok"] is True and guardado["fecha_utc"] == "2026-11-25T18:00:00+00:00"
    assert guardado["campos"]["enableWithdrawals"] is False and guardado["archivo"] == "apiRestrictions.json"
    assert PM.ruta(reg) == tmp_path / "datos" / "real" / "permisos.json"


@pytest.mark.parametrize("campo", PM.DEBEN_SER_FALSE)
def test_cada_permiso_peligroso_en_true_falla(reg, tmp_path, campo):
    assert len(PM.DEBEN_SER_FALSE) == 6
    res = PM.registrar(reg, _archivo(tmp_path, {**BUENO, campo: True}))
    assert not res["ok"] and res["problemas"] == [f"{campo} está en true: debe ser false"]


def test_sin_spot_falla(reg, tmp_path):
    res = PM.registrar(reg, _archivo(tmp_path, {**BUENO, "enableSpotAndMarginTrading": False}))
    assert not res["ok"] and "enableSpotAndMarginTrading está en false" in res["problemas"][0]


def test_sin_ip_restringida_solo_avisa(reg, tmp_path):
    res = PM.registrar(reg, _archivo(tmp_path, {**BUENO, "ipRestrict": False}))
    assert res["ok"] and res["problemas"] == [] and "ipRestrict" in res["avisos"][0]


@pytest.mark.parametrize("cambio,texto", [
    ({"enableWithdrawals": None}, "falta enableWithdrawals"),
    ({"enableFutures": "false"}, "falta enableFutures"),                 # texto, no booleano: no se adivina
    ({"enableSpotAndMarginTrading": 1}, "falta enableSpotAndMarginTrading"),
])
def test_campo_faltante_o_que_no_es_booleano_falla(reg, tmp_path, cambio, texto):
    datos = {k: v for k, v in {**BUENO, **cambio}.items() if v is not None}
    res = PM.registrar(reg, _archivo(tmp_path, datos))
    assert not res["ok"] and any(p.startswith(texto) for p in res["problemas"])


@pytest.mark.parametrize("contenido", ["{roto", "[]", '"hola"'])
def test_json_roto_o_que_no_es_objeto_falla(reg, tmp_path, contenido):
    res = PM.registrar(reg, _archivo(tmp_path, contenido))
    assert not res["ok"] and res["campos"] == {}
    assert PM.ruta(reg).exists()                                          # se guarda también lo que no pasa


def test_archivo_que_no_existe_falla(reg, tmp_path):
    res = PM.registrar(reg, tmp_path / "no_existe.json")
    assert not res["ok"] and "no pude leer" in res["problemas"][0]


# ---------------------------------------------------------------------------- comando
def _correr(capsys, tmp_path, *args):
    import yaml
    ruta = tmp_path / "reglamento.yaml"
    if not ruta.exists():                                                  # copia en tmp: datos/ queda en tmp
        datos = yaml.safe_load((_raiz() / "reglamento.yaml").read_text(encoding="utf-8"))
        ruta.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    capsys.readouterr()
    codigo = MAIN.main(["--reglamento", str(ruta), *args])
    return codigo, capsys.readouterr().out


def _raiz():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent


def test_el_comando_bueno_sale_0(capsys, tmp_path):
    codigo, out = _correr(capsys, tmp_path, "registrar-permisos", "--archivo", str(_archivo(tmp_path, BUENO)))
    assert codigo == 0 and "👍 Permisos de la llave bien" in out
    assert (tmp_path / "datos" / "real" / "permisos.json").exists()


def test_el_comando_malo_sale_1_y_dice_por_que(capsys, tmp_path):
    a = _archivo(tmp_path, {**BUENO, "enableWithdrawals": True, "ipRestrict": False})
    codigo, out = _correr(capsys, tmp_path, "registrar-permisos", "--archivo", str(a))
    assert codigo == 1
    assert "❌ enableWithdrawals está en true: debe ser false" in out and "⚠️ ipRestrict" in out
    assert "❌ Los permisos de la llave NO están bien" in out


def test_el_comando_usa_el_candado_del_real(capsys, tmp_path, monkeypatch):
    from sobreviviente import cli_real
    usado = []
    original = cli_real.con_candado
    monkeypatch.setattr(cli_real, "con_candado", lambda reg, bot, tarea, hacer: usado.append(tarea) or original(
        reg, bot, tarea, hacer))
    codigo, _ = _correr(capsys, tmp_path, "registrar-permisos", "--archivo", str(_archivo(tmp_path, BUENO)))
    assert codigo == 0 and usado == ["registrar-permisos"]


# ---------------------------------------------------------------------------- doctor
def _doctor(reg, monkeypatch):
    monkeypatch.setattr(doctor.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
    salida = []
    codigo = doctor.revisar(reg, salida.append)
    return codigo, "\n".join(salida)


def test_doctor_sin_archivo_solo_informa(reg, monkeypatch):
    codigo, texto = _doctor(reg, monkeypatch)
    assert "ℹ️ Permisos de la llave de Binance: sin registrar" in texto
    assert "❌ Permisos" not in texto


def test_doctor_con_permisos_buenos_dice_la_fecha(reg, tmp_path, monkeypatch):
    PM.registrar(reg, _archivo(tmp_path, BUENO), datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
    _, texto = _doctor(reg, monkeypatch)
    assert "✅ Permisos de la llave de Binance: bien (registrados el 2026-11-24)" in texto


def test_doctor_con_permisos_malos_es_falla(reg, tmp_path, monkeypatch):
    PM.registrar(reg, _archivo(tmp_path, {**BUENO, "enableFutures": True}),
                 datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
    codigo, texto = _doctor(reg, monkeypatch)
    assert codigo == 1
    assert "❌ Permisos de la llave de Binance: enableFutures está en true: debe ser false (registrados el 2026-11-24)" \
        in texto


def test_doctor_con_aviso_de_ip(reg, tmp_path, monkeypatch):
    PM.registrar(reg, _archivo(tmp_path, {**BUENO, "ipRestrict": False}))
    _, texto = _doctor(reg, monkeypatch)
    assert "✅ Permisos de la llave de Binance: bien" in texto and "⚠️ ipRestrict" in texto


def test_doctor_con_archivo_danado(reg, monkeypatch):
    PM.ruta(reg).parent.mkdir(parents=True, exist_ok=True)
    PM.ruta(reg).write_text("{roto", encoding="utf-8")
    _, texto = _doctor(reg, monkeypatch)
    assert "❌ Permisos de la llave de Binance: datos/real/permisos.json no se puede leer" in texto


# ---------------------------------------------------------------------------- lo que NO cambia
def test_la_ronda_real_no_lo_exige():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent / "sobreviviente"
    for nombre in ("ronda_real.py", "real.py", "riesgo.py", "papel.py"):
        assert "permisos" not in (raiz / nombre).read_text(encoding="utf-8").lower(), nombre


def test_solo_lee_el_archivo_sin_red_ni_llaves():
    from pathlib import Path
    texto = (Path(__file__).resolve().parent.parent / "sobreviviente" / "permisos.py").read_text(encoding="utf-8")
    assert "requests" not in texto and "ClienteBinance" not in texto and "import os" not in texto
