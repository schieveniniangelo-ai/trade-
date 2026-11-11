"""Arreglo 74 (banco de filtros, fase 6): el comando `banco-filtros` y su reporte en salida/.

El comando corre con un recorte mínimo de velas FALSAS guardadas en una carpeta temporal: sin red, sin llaves,
sin tocar el reglamento ni el estado de papel."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from sobreviviente import __main__ as MAIN
from sobreviviente import banco_filtros as BF
from sobreviviente import datos as D
from sobreviviente import descartes as DS
from sobreviviente import reglamento as RGL

from test_arreglo71_banco_filtros_fase3 import CFG, FILTROS, _dos_ventanas
from test_arreglo71_banco_filtros_fase3 import _pool as _pool_fase3
from test_arreglo73_banco_filtros_fase5 import _cfg as _cfg_fase5
from test_arreglo73_banco_filtros_fase5 import _pool as _pool_fase5
from test_v2 import diarias

RAIZ = Path(__file__).resolve().parent.parent
SIMBOLOS = ["BTCUSDT", "AUSDT", "BUSDT", "CUSDT"]


def _huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _proyecto(tmp_path, con_velas=True, con_memes=True):
    """Una carpeta de proyecto mínima: el reglamento de verdad (con el backtest recortado a 2022–2023, que da dos
    ventanas de prueba y la prueba final) y velas diarias falsas ya "descargadas" en datos/cache."""
    texto = (RAIZ / "reglamento.yaml").read_text(encoding="utf-8")
    assert texto.count('fin: "2026-10-31"') == 1
    reglamento = tmp_path / "reglamento.yaml"
    reglamento.write_text(texto.replace('fin: "2026-10-31"', 'fin: "2023-12-31"'), encoding="utf-8")
    cache = tmp_path / "datos" / "cache"
    if con_velas:
        cache.mkdir(parents=True)
        (cache / "resumen_descarga.json").write_text(json.dumps({"universo_alguna_vez": SIMBOLOS}), encoding="utf-8")
        for i, s in enumerate(SIMBOLOS):
            df = diarias(800, semilla=i + 10, tendencia=0.0008 + 0.0003 * i)
            df["quote_volume"] = 5e8 / (i + 1)
            D.guardar(df, cache / "spot" / "1d" / f"{s}.csv.gz")
    if con_memes:
        (tmp_path / "datos").mkdir(parents=True, exist_ok=True)
        (tmp_path / "datos" / "memes.json").write_text(json.dumps({"memes": []}), encoding="utf-8")
    return reglamento


@pytest.fixture
def sin_red(monkeypatch):
    """Cualquier intento de salir a internet o de armar el cliente de Binance hace fallar la prueba."""
    def prohibido(*a, **k):
        raise AssertionError("el banco de filtros no debe usar la red ni el cliente de Binance")

    monkeypatch.setattr(requests.Session, "get", prohibido)
    monkeypatch.setattr(requests.Session, "request", prohibido)
    monkeypatch.setattr(D.ClienteBinance, "__init__", prohibido)


def _correr(reglamento, *extra):
    return MAIN.main(["--reglamento", str(reglamento), "banco-filtros", "--min-operaciones", "3", "--bootstrap", "50",
                      "--semilla", "1", *extra])


# ---------------- El comando ----------------

def test_el_comando_corre_escribe_el_reporte_y_no_toca_nada_mas(tmp_path, sin_red, capsys):
    reglamento = _proyecto(tmp_path)
    antes = (_huella(reglamento), _huella(RAIZ / "reglamento.yaml"))
    archivos_antes = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert _correr(reglamento) == 0
    salida = capsys.readouterr().out
    assert "Listo:" in salida and "Esto solo mide. No cambió ninguna regla" in salida and "Traceback" not in salida
    carpeta = tmp_path / "salida"
    nombres = sorted(p.name for p in carpeta.iterdir())
    assert nombres == ["banco_filtros.md", "banco_filtros_bloqueadas.csv", "banco_filtros_metricas.csv",
                       "banco_filtros_veredictos.csv"]
    # No tocó el reglamento, ni el estado de papel, ni las velas guardadas, ni el registro de los bots
    assert (_huella(reglamento), _huella(RAIZ / "reglamento.yaml")) == antes
    assert not (tmp_path / "datos" / "papel").exists() and not (tmp_path / "datos" / "bots").exists()
    despues = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert [x for x in despues if not x.startswith("salida")] == archivos_antes

    md = (carpeta / "banco_filtros.md").read_text(encoding="utf-8")
    for frase in ("# Banco de pruebas de filtros y descartes", "**Solo mide.**", "no promete ganancias",
                  "DECISIÓN DE ÁNGELO", "## Qué se midió", "## Advertencia de muestra chica",
                  "## Línea base (el reglamento sin tocar)", "## Un filtro cambiado a la vez",
                  "## Señales bloqueadas en la línea base y qué habría pasado con ellas",
                  "## Variación entre ventanas de prueba", "## Lo que este banco no puede probar", "## Qué sigue",
                  "aquí no se buscó ni se eligió ningún parámetro", "No es el efecto completo sobre la cartera",
                  "| 2023-01 | 2022-01-01 a 2022-12-31 | 2023-01-01 a 2023-03-31 |", "| prueba final | — | 2023-07-01 a 2023-12-31 |",
                  "**Motores encendidos en estas corridas:** M0.", "Muestra mínima para opinar:** N = 3",
                  "No hay datos guardados de ESTELA", "No hay copia guardada de las reglas de Binance"):
        assert frase in md, frase
    assert "ESTUDIO, no la operación vigente" not in md                 # por defecto es la línea base vigente
    for cartera in "ABC":
        assert f"### Cartera {cartera}" in md
    for codigo in list(DS.APAGABLES_RIESGO) + [DS.FUERA_DE_UNIVERSO]:
        assert f"| {codigo} | apagar |" in md, codigo                    # lista todos los filtros probados
    for codigo in BF.NO_SE_PRUEBAN:
        assert f"- **{codigo}**" in md, codigo

    metricas = pd.read_csv(carpeta / "banco_filtros_metricas.csv")
    assert set(metricas["cartera"]) == {"A", "B", "C"} and BF.BASE in set(metricas["experimento"])
    assert set(metricas["ventana"]) == {BF.TODAS, "2023-01", "2023-04", "prueba final"}
    assert {"operaciones", "pct_ganadoras", "expectativa_r", "expectativa_usdt", "factor_ganancia", "caida_max_pct",
            "caida_max_mercado_pct", "dif_ganancia_usdt"} <= set(metricas.columns)
    veredictos = pd.read_csv(carpeta / "banco_filtros_veredictos.csv")
    assert len(veredictos) == 3 * (len(DS.APAGABLES_RIESGO) + len(BF.APAGABLES_GENERACION))
    bloqueadas = pd.read_csv(carpeta / "banco_filtros_bloqueadas.csv")
    assert DS.ESTRATEGIA_APAGADA in set(bloqueadas["filtro"])            # M1 y M2 están apagados en el reglamento


def test_sin_velas_guardadas_da_un_error_claro(tmp_path, sin_red, capsys):
    reglamento = _proyecto(tmp_path, con_velas=False)
    assert _correr(reglamento) == 1
    salida = capsys.readouterr().out
    assert "❌ No hay velas guardadas en" in salida and "python -m sobreviviente descargar" in salida
    assert "Traceback" not in salida and not (tmp_path / "salida").exists()


def test_sin_velas_de_btc_da_un_error_claro(tmp_path, sin_red, capsys):
    reglamento = _proyecto(tmp_path)
    (tmp_path / "datos" / "cache" / "spot" / "1d" / "BTCUSDT.csv.gz").unlink()
    assert _correr(reglamento) == 1
    salida = capsys.readouterr().out
    assert "❌ Las velas guardadas no alcanzan para correr el banco: faltan velas de BTC." in salida
    assert "Traceback" not in salida


def test_filtro_motor_o_cartera_que_no_existe(tmp_path, sin_red, capsys):
    reglamento = _proyecto(tmp_path)
    assert _correr(reglamento, "--filtros", "INVENTADO") == 1
    assert "❌ No conozco estos filtros: INVENTADO." in capsys.readouterr().out
    assert _correr(reglamento, "--motores", "M9") == 1
    assert "❌ No existen en el reglamento: M9." in capsys.readouterr().out
    assert _correr(reglamento, "--carteras", "Z") == 1
    assert "❌ No existen en el reglamento: Z." in capsys.readouterr().out
    assert not (tmp_path / "salida").exists()


def test_estudio_con_un_motor_apagado_lo_dice_claro(tmp_path, sin_red, capsys):
    reglamento = _proyecto(tmp_path)
    otra = tmp_path / "otra"
    assert _correr(reglamento, "--encender", "M1", "--carteras", "A", "--filtros", DS.MAX_POSICIONES, DS.CALOR_LLENO,
                   "--nombre", "estudio", "--salida", str(otra), "--sin-prueba-final") == 0
    capsys.readouterr()
    assert sorted(p.name for p in otra.iterdir()) == ["estudio.md", "estudio_bloqueadas.csv", "estudio_metricas.csv",
                                                      "estudio_veredictos.csv"]
    md = (otra / "estudio.md").read_text(encoding="utf-8")
    assert "**Motores encendidos en estas corridas:** M0, M1." in md
    assert "⚠️ **ESTUDIO, no la operación vigente:** M1 está(n) APAGADO(S) en el reglamento" in md
    assert "### Cartera A" in md and "### Cartera B" not in md and "prueba final" not in md.split("## Qué se midió")[1].split("## Advertencia")[0].split("|---|")[1]
    assert f"| {DS.MAX_POSICIONES} | apagar |" in md and f"| {DS.COSTOS} | apagar |" not in md
    assert RGL.cargar(reglamento).estrategias["M1"]["estado"] == "APAGADA"      # el reglamento sigue igual


# ---------------- Lo que se lee de lo guardado ----------------

def test_cargar_guardado_avisa_lo_que_falta(tmp_path, sin_red):
    reglamento = _proyecto(tmp_path, con_memes=False)
    reg = RGL.cargar(reglamento)
    md, veto, avisos = BF.cargar_guardado(reg, avisar=lambda *a: None)
    assert set(md.velas) == set(SIMBOLOS) and veto is None
    assert any("memes.json" in a for a in avisos) and any("exchangeInfo" in a for a in avisos)
    assert any("ESTELA" in a for a in avisos)
    local = BF.CacheLocal(reg)
    assert local.cache == tmp_path / "datos" / "cache" and not hasattr(local, "sesion")


def test_con_datos_de_estela_guardados_se_prueba_su_veto(tmp_path, sin_red):
    reglamento = _proyecto(tmp_path)
    estela = tmp_path / "datos" / "cache" / "estela"
    estela.mkdir()
    dias = pd.date_range("2022-01-01", periods=700, freq="D")
    masa = 0.5 + 0.1 * (pd.Series(range(700)) % 97) / 97                  # sube y vuelve a empezar: a veces en su 10 % más alto
    pd.DataFrame({"dia": dias.strftime("%Y-%m-%d"), "masa_cuentas": masa}).to_csv(estela / "AUSDT.csv.gz", index=False,
                                                                               compression="gzip")
    reg = RGL.cargar(reglamento)
    cfg = BF.ConfigBanco(carteras=("A",), filtros=(DS.VETO_ESTELA,), min_operaciones=3, bootstrap_n=50, semilla=1)
    wf, avisos = BF.ejecutar(reg, cfg, avisar=lambda *a: None)
    assert wf.pool.veto_estela and set(wf.pool.veto_estela) == {"AUSDT"}
    assert not any("ESTELA" in a for a in avisos)
    assert [e for e in wf.corridas["A"]] == [BF.BASE, DS.VETO_ESTELA]
    assert wf.corridas["A"][DS.VETO_ESTELA].experimento.accion == "encender"
    assert f"| {DS.VETO_ESTELA} | encender |" in BF.texto_reporte(wf, avisos)


# ---------------- El reporte ----------------

def test_reporte_con_muestra_suficiente_trae_la_variacion_por_ventana(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), _cfg_fase5(), _pool_fase5(), {})
    md = BF.texto_reporte(wf, ["aviso de prueba"], pd.Timestamp("2026-11-11 12:00", tz="UTC"))
    assert "Generado el 2026-11-11 12:00 UTC" in md and "- ⚠️ aviso de prueba" in md
    assert "**Cartera A, BTC_BAJISTA:** mejor en 0, peor en 2 e igual en 0 de 2 ventanas." in md
    assert "| Ventana | Operaciones (dif.) | Ganancia USDT (dif.) | Caída máx. % (dif.) |" in md
    assert f"| {DS.BTC_BAJISTA} | apagar | 9 (+4) |" in md and f"| {BF.PERDIAN} |" in md and f"| {BF.GANABAN} |" in md
    assert "- **No bloquearon ninguna señal en las ventanas de prueba**" in md and "CALOR_LLENO." in md.split("No bloquearon ninguna señal")[1].split("\n")[0].replace(". Varios", ".")
    assert "ESTUDIO, no la operación vigente" not in md                    # en el reglamento de las pruebas M1 no está apagado
    assert "Ningún filtro llegó a la muestra mínima" not in md
    assert "| A | BTC_BAJISTA | 4 | 4 |" in md                             # 4 señales bloqueadas, 4 episodios distintos
    otra_vez = BF.texto_reporte(wf, ["aviso de prueba"], pd.Timestamp("2026-11-11 12:00", tz="UTC"))
    assert md == otra_vez                                                   # mismo resultado, mismo reporte


def test_reporte_sin_muestra_suficiente_solo_avisa(reg):
    wf = BF.walk_forward(_dos_ventanas(reg), CFG, _pool_fase3(), FILTROS)   # N = 20 y 3 operaciones
    md = BF.texto_reporte(wf)
    assert "Sin datos suficientes: 3 operaciones en las ventanas de prueba (se piden al menos 20)." in md
    assert "Ningún filtro llegó a la muestra mínima (N = 20)" in md
    assert f"| {BF.SIN_DATOS} |" in md and BF.PERDIAN not in md and BF.GANABAN not in md
    assert "sin datos suficientes |" in md.split("## Línea base")[1].split("## Un filtro")[0]   # tampoco el rango de la base


def test_escribir_reporte_crea_los_cuatro_archivos(reg, tmp_path):
    wf = BF.walk_forward(_dos_ventanas(reg), CFG, _pool_fase3(), FILTROS)
    rutas = BF.escribir_reporte(wf, tmp_path / "x" / "y", nombre="prueba")
    assert set(rutas) == {"reporte", "metricas", "bloqueadas", "veredictos"}
    assert all(p.exists() and p.stat().st_size > 0 for p in rutas.values())
    assert rutas["reporte"].name == "prueba.md" and pd.read_csv(rutas["veredictos"])["filtro"].tolist() == \
        [DS.YA_HAY_POSICION, DS.FUERA_DE_UNIVERSO]


# ---------------- Caída a valor de mercado ----------------

def test_la_caida_a_valor_de_mercado_ve_la_perdida_de_lo_abierto(reg):
    r = _dos_ventanas(reg)
    sin = BF.walk_forward(r, CFG, _pool_fase3(), FILTROS)
    assert "caida_max_mercado_pct" not in BF.metricas_corrida(sin, sin.corridas["A"][BF.BASE])[BF.TODAS]
    # BUSDT está abierta del 20 de marzo al 19 de abril: a media vida vale 80 (entró en 100)
    dias = pd.date_range("2023-01-01", "2024-01-01", freq="D", tz="UTC")
    precio = pd.Series(100.0, index=dias)
    precio[(dias >= pd.Timestamp("2023-03-25", tz="UTC")) & (dias <= pd.Timestamp("2023-04-10", tz="UTC"))] = 80.0
    con = BF.walk_forward(r, CFG, _pool_fase3(), FILTROS, cierres={"BUSDT": precio})
    m = BF.metricas_corrida(con, con.corridas["A"][BF.BASE])
    assert m[BF.TODAS]["caida_max_mercado_pct"] > m[BF.TODAS]["caida_max_pct"] > 0
    assert m[BF.TODAS]["caida_max_mercado_pct"] == pytest.approx(2.04 * 20.0 / 1020.0 * 100, abs=0.3)   # ≈ 4 %
    t = BF.tabla_metricas(con)
    assert "dif_caida_max_mercado_pct" in t.columns and "Caída a mercado %" in BF.texto_reporte(con)
