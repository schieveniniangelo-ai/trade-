"""Comandos de F1 (SOLO PAPEL): `futuros-papel` y `validar-futuros` (arreglo 151).

`futuros-papel` procesa EN ORDEN las velas de 4 h ya cerradas desde la última corrida, con las monedas de F1, e imprime
un resumen que empieza con «🧪 PAPEL DE FUTUROS — no es una orden». Escribe salida/futuros_papel_<fecha>.json. Nunca
escribe boletos ni toca datos/real/ ni datos/papel/: su estado vive en datos/papel_futuros/F.json.
- Con `activo: false` (hoy) es MODO MUESTRA: enseña señales, tamaño y si cabe o no, pero no guarda posiciones.
- Con `activo: true` solo simula si las monedas de F1 tienen sus escalones verificados (Arreglo 159) y
  VALIDACION_FUTUROS.md dice «PASA»; si no, se queda en modo muestra y lo avisa.
- Si falla un dato, sale con código 0 y el aviso (ese día no hay entradas).
No va dentro de `ronda` ni del real.
`futuros-papel --reiniciar [--si]` (Arreglo 209) empieza F de cero sin borrar nada (como reiniciar-papel). La corrida y
el reinicio usan el candado datos/papel_futuros/ronda.lock.
"""
from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .. import archivos as AR
from .. import backtest as B
from .. import datos as D
from ..estrategias import f1 as F1
from ..reglamento import Reglamento
from . import cartera as C
from . import config as CF
from . import datos_publicos as DP
from . import liquidacion as LQ
from . import tamano as T

ENCABEZADO = "🧪 PAPEL DE FUTUROS — no es una orden"
DUR = timedelta(hours=4)
VELAS_MUESTRA = 6            # modo muestra / primera corrida: las velas de las últimas 24 h


def carpeta_salida(reg: Reglamento) -> Path:
    return AR.carpeta_datos(reg).parent / "salida"


def validacion_pasa(reg: Reglamento) -> bool:
    """¿VALIDACION_FUTUROS.md (junto al reglamento) dice que F1 PASA?"""
    raiz = reg.ruta.parent if reg.ruta is not None else Path(".")
    arch = raiz / "VALIDACION_FUTUROS.md"
    if not arch.exists():
        return False
    return "**Veredicto: F1 PASA.**" in arch.read_text(encoding="utf-8")


def _costos(reg: Reglamento) -> tuple[float, float]:
    return float(reg.costos["comision_futuros_taker_pct"]), float(reg.costos["deslizamiento_pct"]["grande"])


def correr(reg: Reglamento, cliente: D.ClienteBinance | None = None, ahora: datetime | None = None) -> dict[str, Any]:
    """Una corrida de F1. Regresa el resumen (también lo guarda en salida/futuros_papel_<fecha>.json)."""
    ahora = ahora or datetime.now(timezone.utc)
    cfg = CF.leer(reg, exigir_activacion=False)
    out: dict[str, Any] = {"solo_papel": True, "no_es_orden": True, "fecha": ahora.strftime("%Y-%m-%d"),
                           "hora_utc": ahora.isoformat(timespec="seconds"), "modo": "muestra", "avisos": [],
                           "senales": [], "cierres": [], "aperturas": [], "posiciones": [],
                           "cifras": CF.renglones_origen(cfg)}
    simula = bool(cfg["activo"])
    faltan = CF.escalones_pendientes(cfg) if simula else []
    if faltan:                                   # Arreglo 159: primero escalones, después el «PASA»
        simula = False
        out["avisos"].append(f"escalones sin verificar: {', '.join(faltan)} — activo: true pero F1 se queda en "
                             "modo muestra.")
    elif simula and not validacion_pasa(reg):
        simula = False
        out["avisos"].append("activo: true pero VALIDACION_FUTUROS.md no dice «PASA»: se queda en modo muestra.")
    out["modo"] = "papel" if simula else "muestra"
    cliente = cliente or D.ClienteBinance(reg)
    datos = DP.cargar(cliente, cfg, ahora)
    out["avisos"].extend(datos.avisos)
    try:
        est = C.cargar_estado(reg, cfg) if simula else C.estado_nuevo(cfg, ahora)
    except AR.ArchivoDanado as e:
        out["avisos"].append(f"⚠️ {e}: F1 no corre hoy (nadie inventa otro estado encima).")
        return out
    rf = C.reglamento_f1(reg, cfg)
    vetos, eventos, danado, av = C.leer_vetos_eventos(reg)
    out["avisos"].extend(av)
    if not datos.velas or datos.btc1d is None:
        out["capital"] = est["capital"]
        return out
    com, des = _costos(reg)
    params = dict(F1.POR_DEFECTO)
    gest = F1.gestion(params)
    desde = pd.Timestamp(est["ultima_vela"]) if est.get("ultima_vela") else None
    eventos_vela = []
    contextos = {}
    for s in cfg["monedas"]:
        v = datos.velas.get(s)
        if v is None or v.empty:
            continue
        ctx = F1.armar_contexto(s, v, datos.btc1d, datos.funding.get(s), reg, float(cfg["stop_min_pct"]),
                                float(cfg["stop_max_pct"]))
        sen = F1.senales(ctx, params)
        contextos[s] = (v, ctx, sen)
        pos_idx = range(len(v) - VELAS_MUESTRA, len(v)) if desde is None else \
            [i for i, t in enumerate(v.index) if t > desde]
        for i in pos_idx:
            if i >= 0:
                eventos_vela.append((v.index[i], s, i))
    eventos_vela.sort()
    for t, s, i in eventos_vela:
        v, ctx, sen = contextos[s]
        cierre = (t + DUR).to_pydatetime()
        _gestionar(est, s, v, ctx, sen, i, datos, cfg, com, des, cierre, out, simula)
        C.aplicar_frenos(rf, est, cierre)
        if not bool(sen["entrada"].iloc[i]):
            continue
        lado = sen["lado"].iloc[i]
        precio, stop = float(sen["precio"].iloc[i]), float(sen["stop"].iloc[i])
        fila = {"simbolo": s, "vela": t.isoformat(), "lado": lado, "precio": precio, "stop": stop,
                "stop_pct": round(float(sen["stop_pct"].iloc[i]), 3)}
        bloqueos = C.bloqueos_entrada(rf, est, s, cierre, vetos, eventos, danado)
        if not datos.entradas_ok:
            bloqueos.append("datos de Futuros incompletos o viejos: sin entradas.")
        if datos.volumen.get(s, 0.0) < float(cfg["volumen_mediano_min_usdt"]):
            bloqueos.append(f"volumen mediano de 30 días {datos.volumen.get(s, 0.0):,.0f} USDT < "
                            f"{cfg['volumen_mediano_min_usdt']:,} USDT: hoy no se entra en {s}.")
        info = datos.exchange.get(s)
        if info is None:
            bloqueos.append(f"sin reglas de Binance (exchangeInfo) para {s}.")
            filt = None
        else:
            filt = T.filtros_moneda(info)
        fund_i = ctx.extra.get("funding_8h")
        costos = T.costos_reglamento(reg, float(fund_i.iloc[i]) if fund_i is not None else 0.0)   # Arreglo 158
        tam = C.cabe(cfg, est, s, lado, precio, stop, filt, costos) if filt is not None else \
            T.Tamano(False, "sin reglas")
        fila.update({"cabe": tam.cabe, "razon": tam.razon, "cantidad": tam.cantidad, "valor_usdt": round(tam.valor, 4),
                     "apalancamiento": tam.apalancamiento, "margen_usdt": round(tam.margen, 4),
                     "riesgo_usdt": round(tam.riesgo_usdt, 4), "bloqueos": bloqueos})
        out["senales"].append(fila)
        if simula and tam.cabe and not bloqueos and i + 1 < len(v):
            entrada = B.precio_entrada(float(v["open"].iloc[i + 1]), lado, des)
            # Arreglo 155: tamaño y liquidación con la ENTRADA REAL. Si con ella ya no cabe, no se abre.
            tam = C.cabe(cfg, est, s, lado, entrada, stop, filt, costos)
            fila["abre"] = tam.cabe
            if not tam.cabe:
                fila["razon_entrada"] = tam.razon
                out["avisos"].append(f"{s} {lado}: con la entrada real ({entrada:g}) ya no cabe y no se abre — "
                                     f"{tam.razon}")
                continue
            pos = C.abrir(est, s, lado, entrada, precio, stop, tam, (t + DUR).to_pydatetime(), gest, com)
            pos["abierta_vela"] = int(i + 1)
            pos["vela_abierta"] = v.index[i + 1].isoformat()
            out["aperturas"].append({k: pos[k] for k in ("simbolo", "lado", "entrada", "cantidad", "stop",
                                                         "apalancamiento", "margen", "liquidacion")})
    ultimas = [contextos[s][0].index[-1] for s in contextos]
    if ultimas:
        est["ultima_vela"] = min(ultimas).isoformat()
    est["actualizado"] = ahora.isoformat(timespec="seconds")
    out["capital"] = est["capital"]
    out["posiciones"] = [{k: p[k] for k in ("simbolo", "lado", "entrada", "cantidad", "stop", "apalancamiento",
                                            "margen")} for p in est["posiciones"]]
    out["pausa_hasta"], out["detenido"] = est.get("pausa_hasta"), est.get("detenido")
    if simula:
        C.guardar_estado(reg, est)
    return out


def _gestionar(est, s, v, ctx, sen, i, datos, cfg, com, des, cierre, out, simula) -> None:
    """Las posiciones abiertas de la moneda `s` viven la vela `i`: funding, liquidación con la marca y stop."""
    if not simula:
        return
    for pos in [p for p in est["posiciones"] if p["simbolo"] == s]:
        t_vela = v.index[i]
        if t_vela < pd.Timestamp(pos.get("vela_abierta", t_vela)):
            continue
        fnd = datos.funding.get(s)
        if fnd is not None and len(fnd):
            horas = fnd.index.floor("s")
            cobros = fnd[(horas > t_vela) & (horas <= t_vela + DUR)]
            mk = datos.marca.get(s)
            px = float(mk["close"].asof(t_vela)) if mk is not None and len(mk) and t_vela >= mk.index[0] else \
                float(v["close"].iloc[i])
            if len(cobros):
                C.cobrar_funding(pos, cobros, px)
        mk = datos.marca.get(s)
        mh = ml = None
        if mk is not None and t_vela in mk.index:
            mh, ml = float(mk.at[t_vela, "high"]), float(mk.at[t_vela, "low"])
        if pos.get("liquidacion") is not None and not C.marca_ok(mh, ml):
            # Arreglo 202: sin vela de marca la liquidación se revisa con el último precio; se cuenta para el resumen
            out["velas_liq_ultimo_precio"] = int(out.get("velas_liq_ultimo_precio", 0)) + 1
        salir = bool(sen["salir_largo" if pos["lado"] == "LARGO" else "salir_corto"].iloc[i])
        salio, precio, motivo = C.procesar_vela(pos, float(v["open"].iloc[i]), float(v["high"].iloc[i]),
                                                float(v["low"].iloc[i]), float(v["close"].iloc[i]),
                                                float(ctx.atr(14).iloc[i]), mh, ml, salir)
        if salio:
            tarifa = LQ.tarifa_liquidacion(s, datos.exchange.get(s))
            neta = C.cerrar(est, pos, precio, motivo, cierre, cfg, com, des, tarifa)
            out["cierres"].append({"simbolo": s, "lado": pos["lado"], "motivo": motivo, "precio": precio,
                                   "ganancia_usdt": round(neta, 4)})


def resumen(out: dict[str, Any]) -> list[str]:
    L = [ENCABEZADO, f"Modo {out['modo'].upper()} ({out['fecha']}). F1 es SOLO PAPEL: nada de esto va a EJECUTOR."]
    if "capital" in out:
        L.append(f"Capital de papel de F1: {out['capital']:.2f} USDT; posiciones abiertas: {len(out['posiciones'])}.")
    for f in out["senales"]:
        estado = "cabe" if f["cabe"] else "no cabe"
        extra = f" — {f['razon']}" if not f["cabe"] else f" ({f['cantidad']:g} a {f['apalancamiento']}x)"
        L.append(f"• {f['simbolo']} {f['lado']} a {f['precio']:g}, stop {f['stop']:g} ({f['stop_pct']} %): {estado}{extra}"
                 + (f"; bloqueada: {f['bloqueos'][0]}" if f["bloqueos"] else ""))
    for c in out["cierres"]:
        L.append(f"• Cierre {c['simbolo']} {c['lado']} por {c['motivo']}: {c['ganancia_usdt']:+.4f} USDT")
    if not out["senales"] and not out["cierres"]:
        L.append("Sin señales nuevas.")
    if out.get("velas_liq_ultimo_precio"):
        L.append(f"Velas revisadas con el último precio (faltaba la marca): {out['velas_liq_ultimo_precio']}.")
    L += out["avisos"]
    return L


def carpeta_futuros(reg: Reglamento) -> Path:
    """datos/papel_futuros/: estado de F (y su candado ronda.lock). Nada de Spot ni del real vive aquí."""
    return C.ruta_estado(reg).parent


class FuturosOcupado(Exception):
    """Arreglo 209: otra corrida de futuros-papel (o un reinicio) tiene el candado."""


@contextmanager
def candado_futuros(reg: Reglamento):
    """Arreglo 209: datos/papel_futuros/ronda.lock, con el mismo mecanismo que la ronda de papel (archivos.
    bloquear_archivo). No espera: si otro lo tiene, FuturosOcupado. El archivo ronda.lock nunca se borra."""
    carpeta = carpeta_futuros(reg)
    carpeta.mkdir(parents=True, exist_ok=True)
    f = open(carpeta / "ronda.lock", "a+b")
    try:
        try:
            AR.bloquear_archivo(f)
        except OSError:
            raise FuturosOcupado("datos/papel_futuros/ronda.lock está tomado")
        try:
            yield carpeta
        finally:
            AR.desbloquear_archivo(f)
    finally:
        f.close()


def reiniciar(reg: Reglamento, si: bool = False, ahora: datetime | None = None) -> int:
    """Arreglo 209: empieza el papel de Futuros (F) de cero sin borrar nada, con el patrón de reiniciar-papel.

    Con `si`, mueve TODO lo que hay en datos/papel_futuros/ (F.json, su .bak y lo demás) a
    datos/papel_futuros/archivo_<fecha y hora UTC>/, con el candado de futuros-papel. Nunca toca datos/papel/ (Spot),
    datos/real/, datos/cache/ ni salida/. La siguiente corrida crea F con `futuros_papel.capital_papel`. Sin `si` solo
    explica."""
    cap = float(CF.leer(reg, exigir_activacion=False)["capital_papel"])
    if not si:
        print("futuros-papel --reiniciar empieza el papel de Futuros (F) de cero: mueve todo datos/papel_futuros/ a "
              "datos/papel_futuros/archivo_<fecha UTC>/ (no borra nada) y la siguiente corrida arranca F con "
              f"{cap:g} USDT (futuros_papel.capital_papel).\n"
              "No toca datos/papel/ (Spot), datos/real/, datos/cache/ ni salida/. Para hacerlo, agrega --si (cuando no "
              "esté corriendo futuros-papel).\nNo hice nada.")
        return 0
    try:
        with candado_futuros(reg) as carpeta:
            mover = sorted(p for p in carpeta.iterdir()
                           if p.name != "ronda.lock" and not (p.is_dir() and p.name.startswith("archivo_")))
            if not mover:
                print("👍 datos/papel_futuros/ ya está vacío: no había nada que archivar. La siguiente corrida arranca "
                      "de cero.")
                return 0
            u = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
            destino = carpeta / f"archivo_{u:%Y-%m-%d_%H%M%S}Z"
            n = 1
            while destino.exists():          # dos reinicios en el mismo segundo: nunca se mezcla con uno anterior
                n += 1
                destino = carpeta / f"archivo_{u:%Y-%m-%d_%H%M%S}Z_{n}"
            destino.mkdir()
            for p in mover:
                os.replace(p, destino / p.name)
    except FuturosOcupado:
        print("❌ futuros-papel está corriendo (tiene el candado datos/papel_futuros/ronda.lock). No moví nada; vuelve a "
              "intentarlo cuando termine.")
        return 1
    print(f"👍 Papel de Futuros reiniciado: {len(mover)} archivo(s)/carpeta(s) movidos a "
          f"{destino.relative_to(carpeta.parent)} (no se borró nada). La siguiente corrida arranca F con {cap:g} USDT.")
    return 0


def comando(reg: Reglamento, args=None, cliente: D.ClienteBinance | None = None,
            ahora: datetime | None = None) -> int:
    if getattr(args, "reiniciar", False):                       # Arreglo 209
        return reiniciar(reg, getattr(args, "si", False))
    if getattr(args, "si", False):
        print("❌ --si solo sirve con --reiniciar (futuros-papel --reiniciar --si). No hice nada.")
        return 2
    try:
        CF.leer(reg, exigir_activacion=False)   # Arreglo 159: escalones sin verificar → modo muestra, no código 1
    except CF.ErrorConfigFuturos as e:
        print(ENCABEZADO)
        print(f"❌ {e}")
        return 1
    try:
        with candado_futuros(reg):              # Arreglo 209: el mismo candado que futuros-papel --reiniciar
            try:
                out = correr(reg, cliente, ahora)
            except D.ErrorDatos as e:      # red de seguridad: un dato que falla nunca tumba el comando
                out = {"solo_papel": True, "no_es_orden": True, "modo": "muestra", "senales": [], "cierres": [],
                       "posiciones": [], "fecha": (ahora or datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
                       "avisos": [f"⚠️ Falló un dato de Futuros ({e}): hoy F1 no tiene entradas."]}
    except FuturosOcupado:
        print(ENCABEZADO)
        print("❌ Otra corrida de futuros-papel (o un reinicio) está usando datos/papel_futuros (candado ronda.lock). "
              "No hice nada; vuelve a intentarlo cuando termine.")
        return 1
    for linea in resumen(out):
        print(linea)
    sal = carpeta_salida(reg)
    AR.escribir_json_seguro(sal / f"futuros_papel_{out['fecha']}.json", out)
    return 0


def commit_actual(raiz: Path) -> str:
    """El commit corto de la carpeta (para el registro); si git no contesta, vacío."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=raiz, capture_output=True, text=True,
                           timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def comando_validar(reg: Reglamento, args=None, cliente: D.ClienteBinance | None = None) -> int:
    """`validar-futuros [--variante X]`: backtest y compuertas → VALIDACION_FUTUROS_<variante>.md (junto al
    reglamento; F1 base también VALIDACION_FUTUROS.md, el que lee futuros-papel) y un renglón en VARIANTES_FUTUROS.md.
    Solo mide: ningún veredicto escribe `activo`."""
    from . import validar as VF
    from . import variantes as VR
    variante = getattr(args, "variante", None) or "F1"
    VR.variante(variante)
    cfg = CF.leer(reg, exigir_activacion=False)   # solo mide; la compuerta «escalones» ya lo juzga (Arreglo 159)
    raiz = reg.ruta.parent if reg.ruta is not None else Path(".")
    if getattr(args, "holdout", False):
        return _validar_holdout(reg, args, cliente, cfg, variante, raiz)
    cliente = cliente or D.ClienteBinance(reg)
    print(f"🧪 VALIDAR FUTUROS {variante} — SOLO PAPEL (solo mide)")
    m = VF.cargar_mercado(reg, cliente, cfg)
    if not any(len(v) for v in m.velas.values()) or m.btc1d.empty:
        print("❌ No hay datos de Futuros para validar (data.binance.vision no respondió o no hay velas).")
        for a in m.avisos:
            print(f"⚠️  {a}")
        return 1
    res = VF.evaluar(m, robustez_on=not getattr(args, "sin_robustez", False), variante=variante)
    commit = getattr(args, "commit", "") or commit_actual(raiz)
    nombre = f"VALIDACION_FUTUROS_{variante}.md"
    texto = VF.informe(res, m, raiz / nombre, commit)
    if variante == "F1":
        (raiz / "VALIDACION_FUTUROS.md").write_text(texto, encoding="utf-8")
    VR.registrar_corrida(raiz / VR.ARCHIVO_REGISTRO, VF.fila_registro(res, commit))
    print(f"{variante} {res.veredicto}. Detalle en {nombre}; renglón agregado a {VR.ARCHIVO_REGISTRO}.")
    for k, (ok, txt) in res.compuertas.items():
        print(f"{'✅' if ok else '❌'} {k}: {txt}")
    return 0


def _validar_holdout(reg: Reglamento, args, cliente, cfg: dict[str, Any], variante: str, raiz: Path) -> int:
    """`validar-futuros --variante X --holdout` (Arreglo 162): el holdout de monedas, UNA vez y solo con pase previo."""
    from . import validar as VF
    from . import variantes as VR
    print(f"🧪 HOLDOUT DE MONEDAS {variante} — SOLO PAPEL (solo mide)")
    ok, razon = VR.puede_holdout(VR.leer_registro(raiz / VR.ARCHIVO_REGISTRO), variante)
    if not ok:
        print(f"❌ No se abre el holdout: {razon}")
        return 1
    cliente = cliente or D.ClienteBinance(reg)
    cfg_h = {**cfg, "monedas": list(VR.MONEDAS_HOLDOUT)}
    m = VF.cargar_mercado(reg, cliente, cfg_h, respaldo=VR.RESPALDO_HOLDOUT)
    if not any(len(v) for v in m.velas.values()) or m.btc1d.empty:
        print("❌ No hay datos de Futuros para el holdout (data.binance.vision no respondió): no se abrió.")
        return 1
    res = VF.evaluar_holdout(m, variante)
    commit = getattr(args, "commit", "") or commit_actual(raiz)
    nombre = f"VALIDACION_FUTUROS_{variante}_holdout.md"
    VF.informe_holdout(res, m, raiz / nombre, commit)
    VR.registrar_corrida(raiz / VR.ARCHIVO_REGISTRO, VF.fila_registro(res, commit, tipo="holdout"))
    print(f"Holdout {variante}: {res.veredicto}. Detalle en {nombre}; renglón agregado a {VR.ARCHIVO_REGISTRO}.")
    for k, (bien, txt) in res.compuertas.items():
        print(f"{'✅' if bien else '❌'} {k}: {txt}")
    return 0


def registrar(sub) -> None:
    from ..reglamento import cargar
    from .variantes import VARIANTES as VR_VARIANTES

    def _reg(args):
        return cargar(args.reglamento)

    fp = sub.add_parser("futuros-papel", help="F1 de Futuros SOLO PAPEL: procesa las velas de 4 h cerradas (con "
                                              "activo: false es modo muestra). No es una orden ni genera boletos.")
    fp.add_argument("--reiniciar", action="store_true",
                    help="empieza F de cero: archiva datos/papel_futuros/ sin borrar nada (sin --si solo explica)")
    fp.add_argument("--si", action="store_true", help="con --reiniciar: sí, archivar")
    fp.set_defaults(f=lambda a: comando(_reg(a), a))
    vf = sub.add_parser("validar-futuros", help="backtest y compuertas estrictas de F1 → VALIDACION_FUTUROS.md "
                                                "(solo datos públicos de data.binance.vision)")
    vf.add_argument("--sin-robustez", dest="sin_robustez", action="store_true", help="omite la robustez ±20 %%")
    vf.add_argument("--commit", default="", help="commit que se anota en el informe (si no, el de git)")
    vf.add_argument("--variante", default="F1", choices=sorted(VR_VARIANTES),
                    help="variante declarada de la Hipótesis 004 (por defecto F1)")
    vf.add_argument("--holdout", action="store_true",
                    help="abre el holdout de monedas de la variante (UNA vez, solo si pasó las 15 compuertas sin "
                         "contar escalones)")
    vf.set_defaults(f=lambda a: comando_validar(_reg(a), a))
