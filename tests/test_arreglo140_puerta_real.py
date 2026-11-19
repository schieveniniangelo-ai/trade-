"""Arreglo 140: abrir la puerta del dinero real (DECISIÓN DE ÁNGELO del 15 nov 2026).

Solo este arreglo cambia el reglamento: M0 pasa de PAPEL a VIVA_MINI (con el comentario de la decisión), se agrega el
bloque `real:` y la versión sube a 2.0.2. Nada más cambia: ni riesgo, ni topes, ni frenos, ni stops, ni salidas, ni
carteras, ni las compuertas de papel (que Ángelo decidió saltarse, y queda escrito). Sin el bloque `real:`, con M0 en
PAPEL, con Futuros encendido o con otra cartera, la ronda real se niega; con todo en orden, `ronda --modo real
--simular` corre. El papel da exactamente lo mismo con M0 en VIVA_MINI. Y el programa sigue sin llaves ni firmas."""
import copy
import gzip
import io
import json
import re
import tokenize
from pathlib import Path

from sobreviviente import __main__ as MAIN
from sobreviviente import archivos as AR
from sobreviviente import real as RE
from sobreviviente import reglamento
from sobreviviente import ronda_real as RR

import oro_papel_escenario as ORO
from apoyo_real import AHORA, reg_abierto, reg_real
from test_arreglo133_compuertas_real import ronda_falsa  # noqa: F401 - fixture

RAIZ = Path(__file__).resolve().parent.parent
ANTES = Path(__file__).parent / "datos_arreglo140" / "reglamento_6ecb2c2.json"
COMENTARIO = (
    "15 nov 2026: DECISIÓN DE ÁNGELO. Pasa a dinero real en Spot con las reglas de la Cartera A (1 % de riesgo, stop de "
    "catástrofe de 15 %), saltándose las compuertas de papel (papel_dias_min 30 y papel_operaciones_min 30, líneas "
    "284-285, y el texto de 6 semanas y 10 operaciones de THE_BOSS.md y MIGRACION.md) y sin haber pasado las compuertas "
    "históricas (VALIDACION_V2.md: 65.6 % contra 90 % del azar; caída p95 59.8 % contra 25 %). Es una decisión de "
    "Ángelo, no del sistema. Compra FOK, venta de emergencia a mercado si falta el stop o si se activó y no se llenó, "
    "STOP_LOSS_LIMIT como en papel; B y C solo en papel. El papel sigue en paralelo para comparar.")
REAL = {"decision_angelo": "2026-11-15", "cartera": "A", "foto_max_minutos": 120, "margen_minimos_pct": 5,
        "no_comprar_cerca_del_stop_pct": 2}


def test_el_reglamento_dice_la_decision():
    r = reglamento.cargar()
    assert r.version == "2.0.3"          # arreglo 152 (domingo 22 nov): el bloque futuros_papel sube la versión
    # Arreglo 185 (DECISIÓN DE ÁNGELO del 22 nov 2026): M0 regresó a PAPEL; la decisión del 15 nov queda en CAMBIOS.md
    assert r.estrategias["M0"]["estado"] == "PAPEL"
    assert all(e["estado"] == "APAGADA" for k, e in r.estrategias.items() if k != "M0")
    assert r.datos["real"] == REAL
    cambios = (RAIZ / "CAMBIOS.md").read_text(encoding="utf-8")
    seccion = cambios[cambios.index("## Reglamento 2.0.2"):cambios.index("## Reglamento 2.0.3")]
    assert "**M0 pasa de PAPEL a VIVA_MINI**" in seccion and "saltarse las compuertas de papel" in seccion
    assert COMENTARIO.startswith("15 nov 2026: DECISIÓN DE ÁNGELO. Pasa a dinero real en Spot")


def test_nada_mas_cambia_en_el_reglamento():
    antes = json.loads(ANTES.read_text(encoding="utf-8"))
    ahora = json.loads(json.dumps(reglamento.cargar().datos, default=str))
    assert antes["version"] == "2.0.1" and antes["estrategias"]["M0"]["estado"] == "PAPEL" and "real" not in antes
    ahora = copy.deepcopy(ahora)
    assert ahora.pop("real") == REAL
    from sobreviviente.futuros import config as FC
    assert ahora.pop("futuros_papel") == FC.POR_DEFECTO    # arreglo 152: solo papel de Futuros, igual a POR_DEFECTO
    ahora["version"] = "2.0.1"
    ahora["estrategias"]["M0"]["estado"] = "PAPEL"
    assert ahora == antes                     # riesgo, topes, frenos, stops, carteras, compuertas, horarios: igual
    c = ahora["validacion"]["compuertas"]
    assert c["papel_dias_min"] == 30 and c["papel_operaciones_min"] == 30          # se saltan, no se cambian
    assert ahora["estrategias"]["M0"]["fijos"] == {"stop_pct": 15}


def test_con_el_reglamento_nuevo_la_puerta_esta_abierta(tmp_path):
    assert RR.compuertas_puerta(reg_abierto(tmp_path)) == []


def test_sin_bloque_real_se_niega(tmp_path, monkeypatch, capsys):
    r = reg_real(tmp_path)
    r.datos.pop("real")
    malos = RR.compuertas_puerta(r)
    assert any("real.decision_angelo" in m for m in malos) and any("real.cartera" in m for m in malos)
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ronda", "--modo", "real", "--simular"]) == 2
    assert "La ronda real NO corre" in capsys.readouterr().out


def test_con_m0_en_papel_se_niega(tmp_path):
    r = reg_real(tmp_path)
    r.datos["estrategias"]["M0"]["estado"] = "PAPEL"
    assert [m for m in RR.compuertas_puerta(r) if m.startswith("M0 está en PAPEL")]


def test_con_futuros_encendido_se_niega(tmp_path):
    r = reg_abierto(tmp_path)
    r.datos["estrategias"]["E5"]["estado"] = "PAPEL"
    assert RR.compuertas_puerta(r) == ["E5 está en PAPEL (un motor de Futuros): en real solo corre M0 → déjalo APAGADA."]
    r = reg_abierto(tmp_path)
    r.datos["carteras"]["A"]["posiciones_max"]["futuros"] = 1
    assert "Futuros" in RR.compuertas_puerta(r)[0]


def test_con_otra_cartera_se_niega(tmp_path):
    for otra in ("B", "C", ""):
        r = reg_abierto(tmp_path)
        r.datos["real"]["cartera"] = otra
        assert RR.compuertas_puerta(r) == [f"real.cartera es \"{otra}\": en real solo valen las reglas de la Cartera "
                                           f"A (B y C solo en papel) → déjalo en \"A\"."]


def test_con_todo_en_orden_la_simulacion_corre(tmp_path, monkeypatch, capsys, ronda_falsa):  # noqa: F811
    r = reg_abierto(tmp_path)
    original = RR.correr
    monkeypatch.setattr(RR, "correr", lambda reg, simular=False: original(reg, AHORA, cliente=ronda_falsa, memes=[],
                                                                            simular=simular))
    monkeypatch.setattr(MAIN, "_reg", lambda args: r)
    assert MAIN.main(["ronda", "--modo", "real", "--simular"]) == 0
    salida = capsys.readouterr().out
    assert "Ronda REAL del 2026-11-15" in salida and "SIMULACIÓN: no se escribió nada" in salida
    assert not RE.ruta_real(r).exists() and not RR.archivo_boletos(r, "2026-11-15").exists()
    assert AR.leer_registro(r) == []


def test_el_papel_da_lo_mismo_con_m0_en_viva_mini():
    with gzip.open(Path(__file__).parent / "datos_arreglo133" / "oro_papel_e216bd5.json.gz", "rt", encoding="utf-8") as f:
        antes = json.load(f)
    ahora = ORO.normalizar(ORO.correr(RAIZ, estado_m0="VIVA_MINI"))
    assert ahora["boletos"] == antes["boletos"]
    assert ORO.diferencias(ahora["resumenes"], antes["resumenes"]) == []
    assert ORO.diferencias(ahora["estados"], antes["estados"]) == []


# Lo que firmaría una orden o leería la cuenta con llave. El programa solo lee datos públicos; EJECUTOR pone las órdenes
# por el conector de Binance. Las únicas apariciones permitidas son las que ya existían en 6ecb2c2 (no se agrega ninguna).
FIRMAS = (r"hmac", r"x-mbx-apikey", r"signature", r"recvwindow", r"api[_-]?key", r"secret",
          r"/api/v3/order", r"/api/v3/account", r"/api/v3/myTrades", r"/api/v3/openOrders", r"/sapi/", r"/fapi/v\d/order",
          r"requests\.(post|put|delete|patch)", r"\.(post|put|delete|patch)\(", r"\.request\(", r"urlopen")
YA_EXISTIAN = {("sobreviviente/papel.py", r"/api/v3/order")}   # texto de un boleto de papel (cancelReplace), no una llamada


def test_sin_llaves_ni_firmas_ni_llamadas_firmadas():
    hallazgos = set()
    for arch in sorted((RAIZ / "sobreviviente").rglob("*.py")):
        fuente = arch.read_text(encoding="utf-8-sig")
        nombre = arch.relative_to(RAIZ).as_posix()
        for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
            if tok.type == tokenize.COMMENT:
                continue
            for patron in FIRMAS:
                if re.search(patron, tok.string, re.IGNORECASE):
                    hallazgos.add((nombre, patron))
    assert hallazgos <= YA_EXISTIAN, f"Aparecieron llaves, firmas u órdenes en el código: {sorted(hallazgos - YA_EXISTIAN)}"
