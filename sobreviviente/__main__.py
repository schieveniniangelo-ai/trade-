"""Línea de comandos de Sobreviviente Pro.

Uso:  python -m sobreviviente <comando> [opciones]
Comandos: verificar, descargar, validar (más los de la Fase 5: ronda, registrar-llenado, conciliar, reporte, estado).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path

from . import reglamento as RGL

RAIZ = Path(__file__).resolve().parent.parent


def _reg(args) -> RGL.Reglamento:
    try:
        return RGL.cargar(args.reglamento)
    except RGL.ErrorReglamento as e:
        print(str(e))
        sys.exit(2)


def cmd_verificar(args) -> int:
    """Revisa reglamento, conexión, datos y archivos JSON."""
    from . import datos as D
    reg = _reg(args)
    ok = True
    print(f"✅ Reglamento {reg.version} sin choques.")
    for a in reg.avisos:
        print(f"⚠️  {a}")
    cli = D.ClienteBinance(reg)
    try:
        cli.spot("/api/v3/ping")
        print("✅ Conexión a datos de Spot" + (" (por el respaldo)" if cli._spot_bloqueado else ""))
    except D.ErrorDatos as e:
        ok = False
        print(f"❌ Sin conexión a datos de Spot: {e}")
    try:
        cli.futuros("/fapi/v1/ping")
        print("✅ Conexión a datos de Futuros")
    except D.ErrorDatos as e:
        print(f"⚠️  Futuros no disponible desde esta computadora: {e}")
    try:
        from . import archivos
        for nombre, (datos_json, errores) in archivos.leer_todos(reg).items():
            if errores:
                print(f"⚠️  {nombre}: {'; '.join(errores)} (se ignora)")
            else:
                print(f"✅ {nombre}")
    except ImportError:
        pass
    return 0 if ok else 1


def cmd_descargar(args) -> int:
    from . import datos as D
    from .descarga import descargar_todo
    reg = _reg(args)
    t = time.time()
    r = descargar_todo(reg, D.ClienteBinance(reg), con_futuros=not args.sin_futuros)
    print(f"Listo en {time.time() - t:.0f} s: {len(r['universo_alguna_vez'])} monedas de Spot "
          f"({len(r['deslistados_incluidos'])} ya deslistadas) y {len(r['futuros'])} de Futuros.")
    return 0


def cmd_validar(args) -> int:
    from . import backtest as B
    from . import datos as D
    from . import informe
    from .validacion import evaluar
    warnings.filterwarnings("ignore")
    reg = _reg(args)
    if getattr(args, "v2", False):
        from . import ejecutar_v2
        pasos = args.pasos or ["referencias", "motores", "auditoria", "estela"]
        ejecutar_v2.ejecutar(reg, pasos)
        if args.informe:
            from . import informe_v2
            informe_v2.escribir(reg, RAIZ / "VALIDACION_V2.md")
            print("Listo: VALIDACION_V2.md")
        return 0
    cli = D.ClienteBinance(reg)
    memes = json.loads((RAIZ / "datos" / "memes.json").read_text())["memes"]
    print("Cargando históricos…")
    m = B.cargar_mercado(reg, cli, memes)
    if args.ronda2:
        from . import ronda2
        res, _ = ronda2.ejecutar(m, RAIZ / "VALIDACION_RONDA2.md")
        guardar = {r.clave: {"pasa": r.pasa, "oos": r.oos_r, "ic_inferior": r.ic_inferior,
                             "mc": {k: v for k, v in r.mc.items() if not k.startswith("_")},
                             "azar": {k: v for k, v in r.azar.items() if not k.startswith("_")},
                             "params_finales": r.params_finales, "real": r.real,
                             "compuertas": {k: [ok, t] for k, (ok, t) in r.compuertas.items()}} for r in res}
        (RAIZ / "salida").mkdir(exist_ok=True)
        (RAIZ / "salida" / "validacion_ronda2.json").write_text(json.dumps(guardar, indent=1, default=str))
        print("Listo: VALIDACION_RONDA2.md")
        return 0
    resumen = json.loads((cli.cache / "resumen_descarga.json").read_text())
    claves = args.estrategias or ["E1", "E2", "E3", "E4", "E5"]
    resultados = []
    for k in claves:
        t = time.time()
        print(f"Validando {k} ({reg.estrategias[k]['nombre']})…")
        r = evaluar(m, k, avisar=print)
        print(f"  {k}: {'PASA' if r.pasa else 'NO PASA'} en {time.time() - t:.0f} s")
        resultados.append(r)
    notas = [
        f"**Sesgo de supervivencia:** se usaron {len(resumen['universo_alguna_vez'])} monedas que estuvieron en el "
        f"universo en algún momento, incluidas {len(resumen.get('deslistados_incluidos', []))} que Binance ya deslistó "
        "(por ejemplo LUNA o FTT). No se pudieron incluir pares que Binance borró por completo de su API.",
        f"**Futuros:** {len(m.fut4h)} perpetuos con velas y funding de los archivos oficiales de Binance.",
        f"**Memes:** {len([s for s in m.spot1h if s in m.memes])} memes de la lista actual de `memes.json`. Ojo: la lista "
        "se armó hoy, así que tiene algo de sesgo (incluye memes que sabemos que se hicieron famosas).",
    ]
    informe.escribir(resultados, reg, RAIZ / "VALIDACION.md", notas)
    guardar = {r.clave: {"pasa": r.pasa, "oos": r.oos_r, "cartera": r.oos_cartera, "mc": {k: v for k, v in r.mc.items() if not k.startswith("_")},
                         "azar": {k: v for k, v in r.azar.items() if not k.startswith("_")}, "holdout": r.holdout,
                         "params_finales": r.params_finales, "real": r.real,
                         "compuertas": {k: [ok, t] for k, (ok, t) in r.compuertas.items()}}
               for r in resultados}
    (RAIZ / "salida").mkdir(exist_ok=True)
    (RAIZ / "salida" / "validacion.json").write_text(json.dumps(guardar, indent=1, default=str))
    print("Listo: VALIDACION.md y salida/validacion.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="python -m sobreviviente", description="Sobreviviente Pro")
    p.add_argument("--reglamento", default=None, help="ruta del reglamento (por defecto reglamento.yaml)")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("verificar", help="revisa reglamento, conexión, datos y archivos").set_defaults(f=cmd_verificar)
    d = sub.add_parser("descargar", help="descarga y actualiza los históricos")
    d.add_argument("--sin-futuros", action="store_true")
    d.set_defaults(f=cmd_descargar)
    v = sub.add_parser("validar", help="backtests, walk-forward, Monte Carlo y azar → VALIDACION.md")
    v.add_argument("estrategias", nargs="*", help="E1 E2… (por defecto las de la ronda 1)")
    v.add_argument("--ronda2", action="store_true", help="ronda 2: E1D, E6, E7 y referencias → VALIDACION_RONDA2.md")
    v.add_argument("--v2", action="store_true", help="v2 MAREA: auditoría A1–A9, R0–R2, M0–M2 y ESTELA → VALIDACION_V2.md")
    v.add_argument("--pasos", nargs="*", choices=["referencias", "motores", "auditoria", "estela"],
                   help="v2: solo estos pasos (por defecto todos)")
    v.add_argument("--informe", action="store_true", help="v2: al terminar, escribe VALIDACION_V2.md")
    v.set_defaults(f=cmd_validar)
    try:
        from . import cli_ronda
        cli_ronda.registrar(sub)
    except ImportError:
        pass
    args = p.parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    sys.exit(main())
