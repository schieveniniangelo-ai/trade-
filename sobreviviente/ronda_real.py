"""La ronda REAL (arreglos 133 a 137): Spot, reglas de la Cartera A, motor M0 (solo BTC), solo largo.

Usa los mismos datos y la misma decisión que la Cartera A de papel, pero con el capital y el efectivo REALES de la foto
de saldo y las posiciones del estado real. Nunca simula llenados ni cambia el efectivo: solo emite boletos que EJECUTOR
pone por el conector. Lo que protege (cierres, ventas de emergencia) nunca se bloquea por MODO SEGURO, pausa, tope,
conciliación o falta de datos; las compras sí (falla cerrada).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import archivos as AR
from . import real as RE
from .reglamento import Reglamento

ESTADOS_VIVOS = ("VIVA_MINI", "VIVA")
DECISION_ANGELO = "2026-11-15"
TAREA = "ronda --modo real"     # arreglo 139: fila propia en registro.jsonl, medida igual que la ronda de papel


def archivo_boletos(reg: Reglamento, fecha: str) -> Path:
    return AR.carpeta_datos(reg).parent / "salida" / f"boletos_real_{fecha}.json"


def compuertas_puerta(reg: Reglamento) -> list[str]:
    """Lo que tiene que estar en orden para que la ronda real corra (si falla algo, no corre nada). Cada renglón dice
    qué falta y qué hacer."""
    malos = []
    m0 = reg.estrategias.get("M0", {})
    if m0.get("estado") not in ESTADOS_VIVOS:
        malos.append(f"M0 está en {m0.get('estado')}: el real solo corre con M0 en VIVA_MINI o VIVA "
                     f"→ lo decide Ángelo en reglamento.yaml (arreglo 140).")
    for k, e in reg.estrategias.items():
        if k != "M0" and e.get("estado") != "APAGADA":
            que = "un motor de Futuros" if e.get("mercado") == "FUTUROS" else "un motor"
            malos.append(f"{k} está en {e.get('estado')} ({que}): en real solo corre M0 → déjalo APAGADA.")
    pm = (reg.get("carteras.A.posiciones_max") or {})
    if int(pm.get("futuros", 1)) != 0 or int(pm.get("memes", 1)) != 0:
        malos.append("la Cartera A permite Futuros o memes (posiciones_max): en real están prohibidos → déjalos en 0.")
    if str(reg.get("real.decision_angelo", "")) != DECISION_ANGELO:
        malos.append(f"falta la decisión escrita de Ángelo (real.decision_angelo: \"{DECISION_ANGELO}\" en el reglamento) "
                     f"→ sin ella no hay dinero real.")
    cartera = str(reg.get("real.cartera", ""))       # arreglo 140: B y C nunca van a real
    if cartera != "A":
        malos.append(f"real.cartera es \"{cartera}\": en real solo valen las reglas de la Cartera A (B y C solo en "
                     f"papel) → déjalo en \"A\".")
    ok, msg = RE.estado_ok(reg)
    if not ok:
        malos.append(msg + " → Ángelo revisa datos/real/cartera_REAL.json.")
    return malos


def compuertas_compra(reg: Reglamento, ahora: datetime, hora: dict[str, Any], conc: dict[str, Any],
                      est: dict[str, Any] | None) -> list[str]:
    """Lo que bloquea SOLO las compras nuevas (los cierres que protegen se emiten igual)."""
    malos = []
    if rotos := RE.por_que_llenados_rotos(reg):        # arreglo 176: un renglón ilegible no se brinca en silencio
        malos.append(rotos + ".")
    if hora["estado"] != "OK":
        malos.append(f"ronda FUERA DE HORA ({hora['retraso_min']:.0f} min tarde): hoy no hay compras reales.")
    if not conc["ok"]:
        motivo = "; ".join(conc["errores"]) or json.dumps(conc["diferencias"], ensure_ascii=False)
        malos.append(f"la conciliación real no cuadra o no hay foto de saldo fresca ({motivo[:200]}) → EJECUTOR repite "
                     f"registrar-saldo y CONTADOR corre conciliar --real.")
    if est is not None:
        if est.get("bloqueo_compras"):
            malos.append(f"compras bloqueadas por {est['bloqueo_compras']['motivo']} → solo Ángelo las reanuda "
                         f"(reanudar --cartera REAL o ajustar-capital-real).")
        if est.get("detenido"):
            malos.append("la cartera REAL está DETENIDA por caída máxima → solo Ángelo la reanuda.")
        elif est.get("pausa_hasta") and ahora < datetime.fromisoformat(est["pausa_hasta"]):
            malos.append(f"la cartera REAL está en pausa ({est.get('pausa_motivo', '')}) hasta {est['pausa_hasta']}.")
    return malos


def compuertas_real(reg: Reglamento, ahora: datetime | None = None, hora: dict[str, Any] | None = None) -> list[str]:
    """TODAS las causas por las que hoy no habría compras reales (vacío = todo en orden)."""
    from .cli_ronda import revisar_hora
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    malos = compuertas_puerta(reg)
    if malos:
        return malos
    hora = hora or revisar_hora(reg, ahora)
    return compuertas_compra(reg, ahora, hora, RE.conciliar(reg, ahora, escribir=False), RE.cargar_estado(reg))


def _guardar_bitacora(reg: Reglamento, fila: dict[str, Any]) -> None:
    arch = RE.ruta_real(reg) / "bitacora_real.jsonl"
    arch.parent.mkdir(parents=True, exist_ok=True)
    with open(arch, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


ENCABEZADO = "████ REAL ████"


def _mostrar_guardada(reg: Reglamento, fecha: str, simular: bool = False) -> int:
    try:
        boletos = AR.leer_json_seguro(archivo_boletos(reg, fecha))
    except AR.ArchivoDanado as e:
        print(f"❌ {e}")
        if not simular:
            AR.registrar_tarea(reg, "THE BOSS", TAREA, False, str(e)[:160], medir=False)
        return 1
    if not simular:
        AR.registrar_tarea(reg, "THE BOSS", TAREA, True, "ya existía", medir=False)   # repetida: sin hora que medir
    print(f"{ENCABEZADO} La ronda real de {fecha} ya corrió: no se repite y no se crea nada nuevo.")
    if boletos:
        print("Boletos REALES de esa ronda (ya entregados; NO se vuelven a poner):")
        for b in boletos:
            print("  " + str(b.get("texto", b.get("boleto_id"))))
    else:
        print("Esa ronda no tuvo boletos reales.")
    return 0


def _archivos_bots(reg: Reglamento) -> tuple[bool, list, list]:
    """(modo_seguro, vetos, eventos): lo mismo que lee la ronda de papel de los archivos de los bots."""
    seguro, vetos, eventos = False, [], []
    for nombre, (d, err) in AR.leer_todos(reg).items():
        if err and not (len(err) == 1 and err[0].startswith("no existe")):
            seguro = True
        elif d is not None:
            vetos = d.get("vetos", vetos) if nombre == "vetos.json" else vetos
            eventos = d.get("eventos", eventos) if nombre == "eventos.json" else eventos
    return seguro, vetos, eventos


def capital_real(est: dict[str, Any], foto: dict[str, Any], dd) -> float:
    """USDT total de la foto + lo que valen las posiciones reales (cantidad en la cuenta × cierre de la vela)."""
    import numpy as np
    total = float(foto["usdt_libre"]) + float(foto["usdt_bloqueado"])
    for p in est["posiciones"]:
        act = foto["activos"].get(RE.moneda(p["simbolo"]), {"libre": 0.0, "bloqueado": 0.0})
        v = dd.md.velas.get(p["simbolo"])
        px = float(v["close"].asof(dd.dia)) if v is not None and len(v) else float("nan")
        px = px if np.isfinite(px) else float(p["precio_llenado"])
        total += (float(act["libre"]) + float(act["bloqueado"])) * px
    return total


def _llevar_cuentas(reg: Reglamento, rgc, est: dict[str, Any], capital: float, er, ahora_r: datetime) -> list[str]:
    """Pico, puntos del día y de la semana, topes y pausas de la cartera real (la misma regla que el papel). Solo
    contabilidad del riesgo: las posiciones y el dinero solo cambian con llenados confirmados."""
    from . import riesgo as R
    d0 = R.inicio_dia_utc(ahora_r).isoformat()
    w0 = R.inicio_semana(rgc, ahora_r).isoformat()
    if est.get("semana_ref") != w0:
        est["semana_ref"], est["capital_inicio_semana"] = w0, capital
        er.capital_inicio_semana = capital
    mensajes = R.aplicar_topes(rgc, er, ahora_r)
    if est.get("dia_ref") != d0:
        est["dia_ref"], est["capital_inicio_dia"] = d0, capital
    est["pico"], est["detenido"] = er.pico, er.detenido
    est["pausa_hasta"] = er.pausa_hasta.isoformat() if er.pausa_hasta else None
    est["pausa_motivo"] = er.pausa_motivo
    return mensajes


def _entrada(reg: Reglamento, dd, est: dict[str, Any], foto: dict[str, Any] | None, conc: dict[str, Any],
             sin_compras: list[str], ahora: datetime, out: dict[str, Any], dia_txt: str) -> None:
    """Arreglo 134: la compra real de M0 (solo BTCUSDT), con la misma decisión que la Cartera A de papel."""
    import numpy as np
    import pandas as pd

    from . import descartes as DS
    from . import papel as P
    from . import riesgo as R
    from . import universo as U
    s, clave = "BTCUSDT", "M0"

    def anotar(codigo: str, texto: str, aprobada: bool = False) -> None:
        out["descartes"].append(DS.registro(codigo, texto, s, dia_txt, RE.CARTERA, clave, aprobada, origen="real"))

    rgc = reg.para_cartera("A")
    ahora_r = (dd.dia + P.DIA + pd.Timedelta(minutes=10)).to_pydatetime()
    capital = None
    if foto is not None and conc["ok"]:
        capital = capital_real(est, foto, dd)
        sin_ajuste = not est.get("ajustes") and not est["cerradas"] and not est["posiciones"]
        if sin_ajuste and abs(capital - reg.cifra("carteras.capital_inicial")) > 1.0:
            sin_compras.append(f"el saldo de Binance ({capital:.2f} USDT) no es carteras.capital_inicial "
                               f"({reg.cifra('carteras.capital_inicial'):.2f}) y nadie lo ha ajustado → Ángelo: ajustar-capital-real.")
    seguro, vetos, eventos = _archivos_bots(reg)
    er = None
    if capital is not None:
        posiciones = [R.Posicion(p["simbolo"], "SPOT", "LARGO", p["estrategia"], "normales", float(p["precio_llenado"]),
                                 float(p["stop"]), float(p["cantidad_neta"])) for p in est["posiciones"]]
        er = R.EstadoCartera(capital=capital, pico=max(float(est["pico"]), capital),
                             capital_inicio_dia=float(est["capital_inicio_dia"]),
                             capital_inicio_semana=float(est["capital_inicio_semana"]), posiciones=posiciones,
                             efectivo_spot=float(foto["usdt_libre"]))
        if est.get("pausa_hasta"):
            er.pausa_hasta, er.pausa_motivo = datetime.fromisoformat(est["pausa_hasta"]), est.get("pausa_motivo", "")
        er.detenido = bool(est.get("detenido"))
        er.rachas, er.saltar_rondas = dict(est.get("rachas", {})), dict(est.get("saltar_rondas", {}))
        er.conciliacion_ok = conc["ok"]
        er.datos_ok = dd.datos_ok and not seguro
        out["mensajes"] += _llevar_cuentas(reg, rgc, est, capital, er, ahora_r)   # en cada ronda con foto buena
        out["cuentas_cambiaron"] = True
    params = reg.estrategias[clave]["parametros"]
    sen = P._senales(dd, clave, s, params)
    if sen is None or dd.dia not in sen.index or not bool(sen.at[dd.dia, "entrada"]):
        anotar(DS.SIN_SENAL, "sin señal hoy")
        out["mensajes"].append("M0 sin señal de compra hoy.")
        return
    if sin_compras or er is None:
        anotar(DS.COMPRAS_BLOQUEADAS, "hoy no se compra en real: " + "; ".join(sin_compras)[:160])
        out["mensajes"].append("M0 tiene señal de compra, pero hoy no se compra en real (ver ❌ arriba).")
        return
    md = dd.md
    f = md.filtros.get(s)
    if f is None:
        anotar(DS.SIN_FILTROS_O_PRECIO, "no hay reglas de Binance (filtros) para BTCUSDT")
        out["mensajes"].append("⚠️ No hay reglas de Binance para BTCUSDT: hoy no se compra en real.")
        return
    precio = float(sen.at[dd.dia, "precio"])
    from .exchange import redondear_abajo
    stop = redondear_abajo(float(sen.at[dd.dia, "stop"]), f.tick)
    dia_dec = dd.dia + P.DIA
    vm = md.vol_mediano.at[dia_dec, s] if dia_dec in md.vol_mediano.index and s in md.vol_mediano.columns else 0.0
    desliz = U.deslizamiento(rgc, U.clasificar_liquidez(rgc, float(vm) if np.isfinite(vm) else 0.0, False))
    lim_stop = P.limites_ejecucion(reg)[1]
    cand = R.Candidato(s, "SPOT", "LARGO", clave, "normales", precio, stop, None, P._limite_stop(stop, f, lim_stop),
                       float(rgc.costos["comision_spot_pct"]), desliz)
    vol_m = R.clasificar_volatilidad(rgc, P._num(md.vol_pct.get(s, pd.Series(dtype=float)).get(dd.dia)))
    vol_b = R.clasificar_volatilidad(rgc, P._num(md.btc_vol.get(dd.dia)))
    dec = R.evaluar_candidato(rgc, er, cand, f, ahora_r, regimen_btc=md.marea.get(dd.dia) or "BAJISTA", vol_moneda=vol_m,
                              vol_btc=vol_b, vetos=vetos, eventos=eventos)
    if dec.aprobada and dec.solo_papel:
        anotar(DS.ESTRATEGIA_APAGADA, "la decisión es solo de papel: nunca da boleto real")
        out["mensajes"].append("M0: la decisión es solo de papel; no hay boleto real.")
        return
    if not dec.aprobada:
        anotar(dec.codigo, dec.razon)
        nec = f" (haría falta un capital de unos {dec.capital_necesario:.2f} USDT)" if dec.saltada_por_capital and \
            dec.capital_necesario else ""
        out["mensajes"].append(f"M0 no compra hoy en real: {dec.razon}{nec}.")
        return
    if redondear_abajo(dec.cantidad, f.paso) <= 0:
        anotar(DS.CANTIDAD_CERO, "la cantidad redondeada al paso de Binance queda en 0")
        return
    b = RE.boleto_compra_real(reg, dia_txt, s, precio, stop, dec.cantidad, f, ahora)
    errores = RE.revisar_boleto_real(reg, b, f)
    if errores:
        anotar(DS.TAMANO_O_CAPITAL, "; ".join(errores))
        out["mensajes"].append("❌ El boleto de compra real no pasa su revisión: " + "; ".join(errores) + ". No se emite.")
        return
    anotar(DS.APROBADA, dec.razon, aprobada=True)
    out["boletos"].append(b)


def _cierres(reg: Reglamento, dd, est: dict[str, Any], foto: dict[str, Any] | None, out: dict[str, Any],
             dia: str) -> None:
    """Arreglo 135: salidas y vigilancia del stop de cada posición real. Se emiten SIEMPRE (aunque haya MODO SEGURO,
    pausa, tope o conciliación en ❌): lo que protege nunca se bloquea. Nunca se repone un stop: si falta, se vende."""
    from . import papel as P
    for p in est["posiciones"]:
        s = p["simbolo"]
        m = RE.moneda(s)
        paso = float(p.get("paso_cantidad") or 0.0)
        motivo = None
        if foto is not None:
            st = next((o for o in foto["ordenes_abiertas"] if o.get("clientOrderId") == p["id_stop"]
                       and o.get("lado") == "SELL" and o.get("estado") == "NEW"), None)
            act = foto["activos"].get(m, {"libre": 0.0, "bloqueado": 0.0})
            hay = float(act["libre"]) + float(act["bloqueado"])
            if st is None and hay < max(paso, 1e-12):
                motivo = "STOP_EJECUTADO"
            elif st is None:
                motivo = "SIN_STOP"
            elif p["estado_stop"] != "ACTIVO":
                # Arreglo 137: una posición sin su stop confirmado (o con el stop disparado sin llenar) nunca pasa
                # la noche, aunque la foto de hoy ya traiga una orden con ese id
                motivo = "STOP_SIN_LLENAR" if p["estado_stop"] == "DISPARADO_SIN_LLENAR" else "SIN_STOP"
            else:
                v = dd.md.velas.get(s)
                if v is not None and dd.dia in v.index and float(v.at[dd.dia, "low"]) <= float(p["stop"]) \
                        and float(v.at[dd.dia, "close"]) < float(p["limite_stop"]):
                    motivo = "STOP_SIN_LLENAR"
                    p["estado_stop"] = "DISPARADO_SIN_LLENAR"
                    out["cuentas_cambiaron"] = True
        elif p["estado_stop"] != "ACTIVO":
            motivo = "STOP_SIN_LLENAR" if p["estado_stop"] == "DISPARADO_SIN_LLENAR" else "SIN_STOP"
        else:
            out["mensajes"].append(f"⚠️ {m}: sin foto de saldo fresca no puedo revisar si su stop sigue vivo. "
                                   f"EJECUTOR debe repetir registrar-saldo ya.")
        if motivo in RE.URGENTES and not est.get("bloqueo_compras"):
            est["bloqueo_compras"] = {"desde": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                      "motivo": f"{motivo}: {m}"}
            out["cuentas_cambiaron"] = True
        if motivo is None:
            sen = P._senales(dd, p.get("estrategia", "M0"), s, reg.estrategias.get(p.get("estrategia", "M0"), {})
                             .get("parametros", {}))
            if sen is not None and dd.dia in sen.index and bool(sen.at[dd.dia, "salir"]):
                motivo = "SALIDA_M0"
        if motivo is not None:
            out["boletos"].append(RE.boleto_cierre_real(reg, dia, p, motivo, dd.md.filtros.get(s)))


def _ventas_sin_anotar(reg: Reglamento, dd, est: dict[str, Any], out: dict[str, Any], dia: str,
                       ahora: datetime) -> None:
    """Arreglo 172: el BTC LIBRE que el estado real no conoce (en una foto fresca, aunque haya salido con ❌) sale como
    boleto de VENTA URGENTE, con la misma revisión que los demás boletos reales. Se emite SIEMPRE, como los cierres que
    protegen. Si no se puede armar (sin foto fresca, sin reglas de Binance o sin precio, o abajo del mínimo), no sale
    venta y se dice con ❌ URGENTE qué hacer: nunca se vende a ciegas."""
    import numpy as np

    from .papel import numero_txt as n
    foto, _ = RE.leer_foto(reg, ahora)
    hay = RE.btc_sin_anotar(reg, est, foto, ahora)
    if not hay:
        compras = [str(x.get("boleto_id")) for x in RE.compras_sin_anotar(reg)]
        if compras and not (isinstance(foto, dict) and RE._foto_fresca(reg, foto, ahora)):
            out["urgentes"].append(f"❌ URGENTE: puede haber BTC sin stop (compra enviada sin anotar: boleto "
                                   f"{', '.join(compras)}) y sin una foto de saldo fresca no sé cuánto hay: no sale "
                                   f"venta urgente. EJECUTOR: foto de saldo ya (registrar-saldo) y avisa a THE BOSS con "
                                   f"prioridad; Ángelo decide en Binance.")
        return
    for m, info in hay.items():
        s = m + "USDT"
        f = dd.md.filtros.get(s)
        v = dd.md.velas.get(s)
        px = float(v["close"].asof(dd.dia)) if v is not None and len(v) else float("nan")
        motivo = None
        if f is None:
            motivo = f"no hay reglas de Binance (filtros) para {s}"
        elif not np.isfinite(px) or px <= 0:
            motivo = f"no hay precio de {s} para revisar el mínimo de Binance"
        else:
            b = RE.boleto_venta_sin_anotar(reg, dia, s, info["libre"], px, f, info["compras"])
            errores = RE.revisar_boleto_real(reg, b, f)
            if errores:
                motivo = "; ".join(errores)
            else:
                out["boletos"].append(b)
        if motivo is not None and info["libre"] <= 0:
            out["urgentes"].append(f"❌ URGENTE: hay {n(info['bloqueado'])} {m} sin anotar bloqueados en órdenes abiertas "
                                   f"que el estado real no conoce y nada libre: no sale venta urgente (lo bloqueado no "
                                   f"se toca). Avisa a Ángelo con prioridad: él revisa esas órdenes en Binance.")
        elif motivo is not None:
            bloq = f" (además hay {n(info['bloqueado'])} {m} bloqueados en órdenes abiertas)" if info["bloqueado"] else ""
            out["urgentes"].append(f"❌ URGENTE: hay {n(info['libre'])} {m} libres sin anotar y sin stop{bloq}, pero no "
                                   f"sale venta urgente: {motivo}. Avisa a Ángelo con prioridad: él decide en Binance.")
        if not est.get("bloqueo_compras"):
            est["bloqueo_compras"] = {"desde": ahora.isoformat(timespec="seconds"),
                                      "motivo": f"SIN STOP: {m} en la cuenta que el estado real no conoce"}
            out["cuentas_cambiaron"] = True


def decidir(reg: Reglamento, dd, est: dict[str, Any], foto: dict[str, Any] | None, conc: dict[str, Any],
            sin_compras: list[str], ahora: datetime, escribir: bool = True, fecha: str | None = None) -> dict[str, Any]:
    """Qué boletos reales salen hoy: primero los cierres que protegen (arreglo 135) y la venta urgente del BTC sin
    anotar (172), después la compra (134). Las cuentas del riesgo (pico, topes) se guardan solo con `escribir`."""
    out: dict[str, Any] = {"boletos": [], "mensajes": [], "descartes": [], "urgentes": []}
    dia = fecha or dd.dia.strftime("%Y-%m-%d")    # el día de la ronda: el mismo del archivo salida/boletos_real_<día>.json
    _cierres(reg, dd, est, foto, out, dia)         # primero lo que protege, pase lo que pase
    _ventas_sin_anotar(reg, dd, est, out, dia, ahora)   # arreglo 172: también protege
    if est.get("bloqueo_compras") and not any("compras bloqueadas" in m for m in sin_compras):
        sin_compras.append(f"compras bloqueadas por {est['bloqueo_compras']['motivo']} → solo Ángelo las reanuda "
                           f"(reanudar --cartera REAL o ajustar-capital-real).")
    _entrada(reg, dd, est, foto, conc, sin_compras, ahora, out, dia)
    if escribir and out.pop("cuentas_cambiaron", False):
        RE.guardar_estado(reg, est)
    if escribir:
        try:
            AR.escribir_json_seguro(RE.ruta_real(reg) / "descartes" / f"descartes_{dia}.json",
                                    {"dia": dia, "carteras": {RE.CARTERA: out["descartes"]}}, indent=None)
        except OSError as e:
            out["mensajes"].append(f"No se pudo guardar el registro de descartes real ({type(e).__name__}); "
                                   f"no afecta a los boletos.")
    return out


def correr(reg: Reglamento, ahora: datetime | None = None, cliente=None, memes: list[str] | None = None,
           simular: bool = False) -> int:
    """`ronda --modo real` (con `simular`, corre todo y solo imprime: no escribe estado, boletos ni bitácora)."""
    from . import cli_ronda as CR
    from . import datos as D
    from . import papel as P
    t0 = time.monotonic()
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    puerta = compuertas_puerta(reg)
    if puerta:
        print(f"{ENCABEZADO} La ronda real NO corre. Falta:")
        for m in puerta:
            print(f"❌ {m}")
        if not simular:
            AR.registrar_tarea(reg, "THE BOSS", TAREA, False, "puerta cerrada: " + "; ".join(puerta)[:140], medir=False)
        return 2
    hora = CR.revisar_hora(reg, ahora)
    if hora["estado"] == "TEMPRANO":
        print(f"⏳ Es muy temprano ({hora['hora_real_utc']}): la ronda real es a las {hora['hora_programada_utc']} UTC. "
              f"No corrí nada.")
        if not simular:
            AR.registrar_tarea(reg, "THE BOSS", TAREA, False, "temprano", a_tiempo=False)
        return 1
    fecha = CR.fecha_ronda(ahora)
    fuera = hora["estado"] != "OK"
    if archivo_boletos(reg, fecha).exists() or AR.hay_archivo(archivo_boletos(reg, fecha)):
        return _mostrar_guardada(reg, fecha, simular)
    try:
        candado = CR.candado_ronda(reg, carpeta=RE.ruta_real(reg)) if not simular else _sin_candado()
        with candado:
            if not simular and AR.hay_archivo(archivo_boletos(reg, fecha)):
                return _mostrar_guardada(reg, fecha, simular)
            cli = cliente or D.ClienteBinance(reg)
            dd = P.preparar_datos(reg, cli, memes if memes is not None else CR._memes(), ahora=ahora)
            if getattr(dd, "no_opera", ""):          # arreglo 166: antes de conciliar, decidir o escribir nada
                raise P.BinanceNoOpera(dd.no_opera)
            conc = RE.conciliar(reg, ahora, escribir=not simular)
            est = RE.cargar_estado(reg, fecha)
            foto, por_que_foto = RE.leer_foto(reg, ahora)
            foto = None if por_que_foto else foto            # solo una foto fresca y buena dice si el stop vive
            sin_compras = compuertas_compra(reg, ahora, hora, conc, est)
            out = decidir(reg, dd, est, foto, conc, sin_compras, ahora, escribir=not simular, fecha=fecha)
            if not simular:
                AR.escribir_json_seguro(archivo_boletos(reg, fecha), out["boletos"])
    except P.BinanceNoOpera as e:
        print(ENCABEZADO)
        for m in pendientes_urgentes(reg):           # arreglo 178: lo urgente va antes que lo demás
            print(m)
        print(CR.texto_ronda_saltada(str(e), hora, real=True) + (" SIMULACIÓN: no se escribió nada." if simular else ""))
        if not simular:
            AR.registrar_tarea(reg, "THE BOSS", TAREA, False, f"saltada: {e}"[:160], a_tiempo=not fuera)
        return 1
    except Exception as e:  # noqa: BLE001 - una ronda real caída nunca pasa desapercibida
        motivo = (str(e).strip() or type(e).__name__).splitlines()[0][:160]
        print(ENCABEZADO)
        for m in pendientes_urgentes(reg):           # arreglo 178: también con la red caída
            print(m)
        print(f"❌ La ronda real NO corrió: {motivo}\nHoy no hay boletos reales. Los stops ya puestos siguen "
              f"igual. Avisa a THE BOSS de inmediato.")
        if not simular:
            AR.registrar_tarea(reg, "THE BOSS", TAREA, False, motivo, a_tiempo=not fuera)   # su hora sí se midió
        return 1
    if not simular:
        try:
            _guardar_bitacora(reg, {"hora_real_utc": hora["hora_real_utc"], "dia_procesado": fecha,
                                    "duracion_s": round(time.monotonic() - t0, 1), "fuera_de_hora": hora["estado"] != "OK",
                                    "sin_compras": sin_compras, "boletos": len(out["boletos"]),
                                    "conciliacion_ok": conc["ok"], "modo_seguro": not dd.datos_ok})
        except OSError as e:
            print(f"⚠️ No pude escribir la bitácora real ({type(e).__name__}). La ronda sí corrió.")
        AR.registrar_tarea(reg, "THE BOSS", TAREA, True, f"{len(out['boletos'])} boletos; día {fecha}; "
                           f"{time.monotonic() - t0:.0f} s" + ("; fuera_de_hora" if fuera else ""), a_tiempo=not fuera)
    imprimir(fecha, out, sin_compras, conc, simular)
    return 0


def sin_stop_confirmado(reg: Reglamento) -> list[str]:
    """Arreglo 166: con la ronda saltada no hay boletos, así que las posiciones reales sin stop confirmado (según el
    estado local, sin red) se dicen como URGENTE. Vender sin boleto solo lo decide Ángelo."""
    try:
        est = RE.cargar_estado(reg)
    except RE.EstadoRealDanado as e:
        return [f"❌ URGENTE: no pude leer el estado real ({e}). Ángelo debe revisar en Binance que todo tenga su stop."]
    return [f"❌ URGENTE: {RE.moneda(p['simbolo'])} no tiene stop confirmado (estado {p['estado_stop']}) y hoy no hay "
            f"boletos: avisa a Ángelo con prioridad; vender sin boleto solo lo decide él."
            for p in est["posiciones"] if p.get("estado_stop") != "ACTIVO"]


def pendientes_urgentes(reg: Reglamento) -> list[str]:
    """Arreglo 178: con la ronda saltada (mantenimiento de Binance o red caída) no hay boletos ni conciliación nueva, así
    que lo que el estado LOCAL ya dice que puede estar sin protección sale primero, como URGENTE (sin red): un renglón
    ilegible de llenados.jsonl (176), cada COMPRA_ENVIADA sin su resultado (170), el BTC que la última foto de saldo trae
    y el estado real no conoce (172) y cada posición sin stop confirmado (166). Vender sin boleto solo lo decide Ángelo."""
    from . import papel as P
    out = []
    try:
        rotos = RE.por_que_llenados_rotos(reg)
        pendientes = RE.compras_sin_anotar(reg)
    except OSError as e:
        rotos, pendientes = f"no pude leer llenados.jsonl ({type(e).__name__})", []
    if rotos:
        out.append(f"❌ URGENTE: {rotos}.")
    for x in pendientes:
        bid = x.get("boleto_id")
        try:
            hora = P.hora_cdmx(x["hora_utc"]) if isinstance(x.get("hora_utc"), str) else "sin hora"
        except (TypeError, ValueError):
            hora = "sin hora"
        m = RE._moneda_del_boleto(reg, bid)
        out.append(f"❌ URGENTE: compra enviada sin anotar (boleto {bid}, COMPRA_ENVIADA, {hora}): puede haber {m} SIN "
                   f"STOP en Binance. EJECUTOR: revisa esa compra con spot.getOrder y anota cómo terminó (COMPRA_LLENADA, "
                   f"COMPRA_PARCIAL o COMPRA_NO_LLENADA); avisa a Ángelo con prioridad: vender sin boleto solo lo decide él.")
    try:
        est = RE.cargar_estado(reg)
    except RE.EstadoRealDanado:
        return out + sin_stop_confirmado(reg)
    foto, _ = RE.leer_foto(reg)
    sin_estado = foto.get("sin_estado") if isinstance(foto, dict) else None
    if isinstance(sin_estado, dict):            # leer_foto ya revisó que su hora se entiende
        en_posicion = {RE.moneda(p["simbolo"]) for p in est["posiciones"]}
        hora = P.hora_cdmx(foto["hora_utc"])
        for a, cant in sin_estado.items():
            if a in en_posicion:
                continue
            c = RE._num(cant)
            cant = cant if c is None else format(c, "g")
            out.append(f"❌ URGENTE: la última foto de saldo ({hora}) trae {cant} {a} que el estado real no conoce: no "
                       f"tiene stop anotado. Avisa a Ángelo con prioridad: vender sin boleto solo lo decide él.")
    return out + sin_stop_confirmado(reg)


class _sin_candado:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def imprimir(fecha: str, out: dict[str, Any], sin_compras: list[str], conc: dict[str, Any], simular: bool) -> None:
    urgentes = [b for b in out["boletos"] if b.get("urgente")]
    for b in urgentes:                                   # lo urgente va en la primera línea
        if b.get("motivo") == RE.MOTIVO_SIN_ANOTAR:      # arreglo 172
            print(f"❌ URGENTE: {RE.moneda(b['simbolo'])} sin anotar y sin stop en {b['simbolo']} — EJECUTOR debe "
                  f"venderlo ya (VENTA URGENTE). Avisa a Ángelo con prioridad.")
        else:
            print(f"❌ URGENTE: {b['motivo']} en {b['simbolo']} — EJECUTOR debe cerrar ya. Avisa a Ángelo con prioridad.")
    for m in out.get("urgentes", []):
        print(m)
    print(f"{ENCABEZADO} Ronda REAL del {fecha} — dinero de verdad (Spot, reglas de la Cartera A, solo M0/BTC)."
          + (" SIMULACIÓN: no se escribió nada." if simular else ""))
    for m in sin_compras:
        print(f"❌ Sin compras: {m}")
    for m in out["mensajes"]:
        print(m)
    if out["boletos"]:
        print("Boletos REALES para el EJECUTOR (copiar tal cual):" if not simular else
              "Boletos REALES que saldrían (simulación: NO se ponen):")
        for b in out["boletos"]:
            print("  " + b["texto"])
    else:
        print("Sin boletos reales hoy." + ("" if sin_compras or not conc["ok"] else " 👍"))
