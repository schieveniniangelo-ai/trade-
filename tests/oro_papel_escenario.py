"""Escenario fijo de la prueba de oro del papel (arreglo 133).

Velas sintéticas de tests/test_v2.diarias (las de test_papel) con una caída fuerte a partir del día 430, para que haya
compras, stops que suben, stops tocados y ventas. Reglamento del checkout con capital 1000 y M0, M1 y M2 en PAPEL; 100
rondas completas (papel.ronda) seguidas. Sirve igual con el código de antes de esta tanda (e216bd5) y con el de hoy."""
import json
import math
import tempfile
from pathlib import Path

import numpy as np

from sobreviviente import diario as DI
from sobreviviente import papel as P
from sobreviviente import reglamento
from sobreviviente.exchange import Filtros
from test_v2 import diarias

DIAS = range(380, 480)


def _velas():
    velas = {}
    for i, s in enumerate(["BTCUSDT", "AUSDT", "BUSDT", "CUSDT"]):
        df = diarias(700, semilla=i + 20, tendencia=0.0012 + 0.0004 * i)
        t = np.arange(len(df))
        caida = np.where(t < 430, 1.0, np.where(t < 455, 0.97 ** (t - 430), 0.97 ** 25))   # −3 % diario por 25 días
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] * caida
        df["quote_volume"] = 5e8
        velas[s] = df
    return velas


def _datos_dia(reg, velas, k):
    recorte = {s: v.iloc[:k + 1] for s, v in velas.items()}
    md = DI.preparar(reg, recorte, None, [], exchange_info={"symbols": []}, btc_largo=recorte["BTCUSDT"])
    md.filtros = {s: Filtros(s, 0.0001, 0.0001, 0.0001, 5.0) for s in recorte}
    aperturas = {s: float(v["open"].iloc[k + 1]) for s, v in velas.items()}
    return P.DatosDia(dia=recorte["BTCUSDT"].index[-1], md=md, apertura_hoy=lambda s: aperturas.get(s))


def correr(raiz: Path, estado_m0: str = "PAPEL") -> dict:
    """`estado_m0` (arreglo 140): con VIVA_MINI, el papel debe dar exactamente lo mismo que con PAPEL."""
    velas = _velas()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        r = reglamento.cargar(Path(raiz) / "reglamento.yaml").copia_con(
            {"datos.carpeta": str(tmp / "datos"), "carteras.capital_inicial": 1000.0})
        for k in r.estrategias:
            r.datos["estrategias"][k]["estado"] = "APAGADA"
        for k in ("M0", "M1", "M2"):
            r.datos["estrategias"][k]["estado"] = "PAPEL"
        r.datos["estrategias"]["M0"]["estado"] = estado_m0
        r.datos["estrategias"]["M1"]["parametros"] = {"n": 20}
        r.datos["version"] = "oro"              # la etiqueta de versión no decide nada (el arreglo 140 la sube)
        r.ruta = tmp / "reglamento.yaml"
        out = {"boletos": {}, "resumenes": {}}
        for k in DIAS:
            res = P.ronda(r, _datos_dia(r, velas, k), avisar=lambda *_: None)
            dia = res["dia"]
            out["boletos"][dia] = json.loads((tmp / "salida" / f"boletos_{dia}.json").read_text(encoding="utf-8"))
            out["resumenes"][dia] = {n: {x: c[x] for x in ("capital", "efectivo", "posiciones", "mensajes", "opera",
                                                           "capital_necesario", "stops_sin_llenar", "no_llenadas",
                                                           "cerradas_hoy", "pausa", "detenido")}
                                     for n, c in res["carteras"].items()}
        out["estados"] = {}
        for n in P.CARTERAS:
            est = json.loads((tmp / "datos" / "papel" / f"cartera_{n}.json").read_text(encoding="utf-8"))
            est.pop("rondas")                       # ya están arriba, día por día (así la referencia pesa menos)
            out["estados"][n] = est
    return json.loads(json.dumps(out, default=str))


def normalizar(datos: dict) -> dict:
    """Lo único que esta tanda cambia a propósito en un boleto de papel (arreglo 132): `modo: "PAPEL"` y el texto que
    empieza con «[PAPEL — NO PONER] ». Se quita para comparar contra la referencia de antes."""
    for boletos in datos["boletos"].values():
        for b in boletos:
            b.pop("modo", None)
            if b.get("texto", "").startswith(P.AVISO_PAPEL if hasattr(P, "AVISO_PAPEL") else "\0"):
                b["texto"] = b["texto"][len(P.AVISO_PAPEL):]
    return datos


def diferencias(a, b, ruta: str = "") -> list[str]:
    """Arreglo 142: dónde difieren `a` y `b`. Todo se compara exacto (textos, llaves, largos, tipos, None, bool) salvo
    los números, que valen iguales si están a 1e-12 relativo o 1e-9 absoluto (un redondeo de 1 ULP, no un centavo)."""
    num = (int, float)
    if isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        return [] if math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9) else [f"{ruta}: {a!r} != {b!r}"]
    if type(a) is not type(b):
        return [f"{ruta}: {a!r} != {b!r}"]
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return [f"{ruta}: llaves {sorted(a)} != {sorted(b)}"]
        return [d for k in a for d in diferencias(a[k], b[k], f"{ruta}/{k}")]
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{ruta}: {len(a)} elementos != {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diferencias(x, y, f"{ruta}[{i}]")]
    return [] if a == b else [f"{ruta}: {a!r} != {b!r}"]
