"""M3 — ESTELA: "copy trade" MEDIDO. ¿El posicionamiento de los top traders de Binance predice algo?

Datos: archivo oficial `data.binance.vision`, ruta `data/futures/um/daily/metrics/<SÍMBOLO>/`, una foto cada
5 minutos. Significado de cada columna (VERIFICADO el 10 nov 2026 comparando fila por fila contra la API
pública de Binance Futuros, error mediano < 0.1 %):

| Columna del archivo                  | Ruta equivalente de la API                       | Qué es |
|---|---|---|
| sum_open_interest                    | /futures/data/openInterestHist (sumOpenInterest)  | contratos abiertos |
| sum_open_interest_value              | ídem (sumOpenInterestValue)                       | contratos abiertos en USDT |
| count_toptrader_long_short_ratio     | /futures/data/topLongShortAccountRatio            | top traders: CUENTAS en largo ÷ en corto |
| sum_toptrader_long_short_ratio       | /futures/data/topLongShortPositionRatio           | top traders: POSICIONES en largo ÷ en corto |
| count_long_short_ratio               | /futures/data/globalLongShortAccountRatio         | TODAS las cuentas: largo ÷ corto |
| sum_taker_long_short_vol_ratio       | /futures/data/takerlongshortRatio                 | volumen de compradores ÷ vendedores agresivos |

"Top traders" = según Binance, el 20 % de usuarios con más margen. Para ESTELA:
- `top_largo`  = r / (1 + r), con r = sum_toptrader_long_short_ratio (posiciones de los top traders);
- `masa_largo` = r / (1 + r), con r = count_long_short_ratio (todas las cuentas);
- `brecha`     = top_largo − masa_largo.
Valor diario = la ÚLTIMA foto antes del cierre de las 00:00 UTC (nada del día siguiente).

Estudio de eventos (hipótesis fijas, sin pescar otras):
- H1 (seguir a los top): el z-score de top_largo sube ≥ z en D días y el de masa_largo no sube →
  el rendimiento de los siguientes 3 y 7 días es MAYOR que el de un día cualquiera.
- H2 (contra la bola): masa_largo en el 10 % más alto de sus 90 días previos → el rendimiento de los
  siguientes 3 y 7 días es MENOR que el de un día cualquiera.
Cada serie se normaliza contra sus propios 90 días previos (z-score móvil, sin contar el día actual).
El rendimiento se mide de la apertura siguiente a la señal (cuando se podría operar) a la apertura h días después.
Efecto = promedio en días con evento − promedio de todos los días elegibles (mismas monedas y fechas).
Pasa si el efecto tiene el signo de la hipótesis en ≥ 70 % de los años Y su intervalo de confianza del 95 %
(remuestreo en bloques de 20 días) no toca el cero.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import pandas as pd

from . import datos as D
from .reglamento import Reglamento

S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
RUTA = "data/futures/um/daily/metrics"
COLUMNAS = ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]
API_EQUIVALENTE = {
    "count_toptrader_long_short_ratio": ("topLongShortAccountRatio", "longShortRatio"),
    "sum_toptrader_long_short_ratio": ("topLongShortPositionRatio", "longShortRatio"),
    "count_long_short_ratio": ("globalLongShortAccountRatio", "longShortRatio"),
    "sum_taker_long_short_vol_ratio": ("takerlongshortRatio", "buySellRatio"),
    "sum_open_interest": ("openInterestHist", "sumOpenInterest"),
}


def parte_larga(r: pd.Series) -> pd.Series:
    """De razón largo/corto a parte en largo: r / (1 + r)."""
    return r / (1.0 + r)


# ---------------------------------------------------------------------------
# Descarga y verificación
# ---------------------------------------------------------------------------

def listar_dias(cli: D.ClienteBinance, simbolo: str) -> list[str]:
    """Fechas (AAAA-MM-DD) con archivo de métricas para un símbolo, leyendo el índice oficial."""
    fechas, marcador = [], ""
    while True:
        params = {"delimiter": "/", "prefix": f"{RUTA}/{simbolo}/"}
        if marcador:
            params["marker"] = marcador
        r = cli._get(S3, params)
        if r.status_code != 200:
            break
        raiz = ET.fromstring(r.content)
        ns = {"s3": raiz.tag.split("}")[0].strip("{")} if raiz.tag.startswith("{") else {}
        llaves = [e.text for e in raiz.iter() if e.tag.endswith("Key")]
        for k in llaves:
            if k.endswith(".zip"):
                fechas.append(k.rsplit("-metrics-", 1)[-1][:10])
        truncado = any(e.text == "true" for e in raiz.iter() if e.tag.endswith("IsTruncated"))
        if not truncado or not llaves:
            break
        marcador = llaves[-1]
        del ns
    return sorted(set(fechas))


def _dia(cli: D.ClienteBinance, simbolo: str, fecha: str) -> dict[str, Any] | None:
    r = cli._get(f"{cli.url_hist}/{RUTA}/{simbolo}/{simbolo}-metrics-{fecha}.zip")
    if r.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]))
    if df.empty or not set(COLUMNAS) <= set(df.columns):
        return {"dia": fecha, "error": "columnas distintas: " + ",".join(df.columns)}
    df["create_time"] = pd.to_datetime(df["create_time"])
    fin_dia = pd.Timestamp(fecha) + pd.Timedelta(days=1)
    df = df[df["create_time"] < fin_dia].sort_values("create_time")  # solo fotos antes del cierre de las 00:00 UTC
    if df.empty:
        return None
    u = df.iloc[-1]
    return {"dia": fecha, "hora_ultima": str(u["create_time"]), "filas": int(len(df)),
            "top_posiciones": float(u["sum_toptrader_long_short_ratio"]),
            "top_cuentas": float(u["count_toptrader_long_short_ratio"]),
            "masa_cuentas": float(u["count_long_short_ratio"]),
            "taker": float(u["sum_taker_long_short_vol_ratio"]), "oi": float(u["sum_open_interest"]),
            "oi_valor": float(u["sum_open_interest_value"])}


def descargar_simbolo(cli: D.ClienteBinance, simbolo: str, inicio: str, fin: str, hilos: int = 12) -> pd.DataFrame:
    """Serie diaria de un símbolo (en caché `datos/cache/estela/`)."""
    arch = cli.cache / "estela" / f"{simbolo}.csv.gz"
    viejo = pd.read_csv(arch, compression="gzip") if arch.exists() else pd.DataFrame(columns=["dia"])
    tiene = set(viejo["dia"].astype(str))
    dias = [d for d in listar_dias(cli, simbolo) if inicio <= d <= fin and d not in tiene]
    filas = []
    if dias:
        with ThreadPoolExecutor(max_workers=hilos) as ex:
            for x in ex.map(lambda d: _dia(cli, simbolo, d), dias):
                if x is not None:
                    filas.append(x)
    df = pd.concat([viejo, pd.DataFrame(filas)], ignore_index=True) if filas else viejo
    if not df.empty:
        df = df.drop_duplicates("dia", keep="last").sort_values("dia")
        arch.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(arch, index=False, compression="gzip")
    return df


def verificar_columnas_api(cli: D.ClienteBinance, simbolo: str = "BTCUSDT") -> dict[str, Any]:
    """Compara un día reciente del archivo contra la API pública de Futuros (solo guarda 30 días)."""
    fecha = (pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    r = cli._get(f"{cli.url_hist}/{RUTA}/{simbolo}/{simbolo}-metrics-{fecha}.zip")
    if r.status_code != 200:
        return {"ok": False, "motivo": f"no hay archivo del {fecha}"}
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        f = pd.read_csv(z.open(z.namelist()[0]))
    f["ts"] = pd.to_datetime(f["create_time"]).dt.tz_localize("UTC")
    f = f.set_index("ts")
    t0 = int(pd.Timestamp(fecha, tz="UTC").timestamp() * 1000)
    out = {"fecha": fecha, "columnas": {}}
    try:
        for col, (ruta, campo) in API_EQUIVALENTE.items():
            datos = cli.futuros(f"/futures/data/{ruta}", {"symbol": simbolo, "period": "5m", "startTime": t0,
                                                          "endTime": t0 + 86_400_000 - 1, "limit": 500})
            x = pd.DataFrame(datos)
            x.index = pd.to_datetime(x["timestamp"].astype("int64"), unit="ms", utc=True)
            comun = f.index.intersection(x.index)
            a, b = f.loc[comun, col].astype(float), x.loc[comun, campo].astype(float)
            err = float(((a - b).abs() / b.abs()).median()) if len(comun) else float("nan")
            out["columnas"][col] = {"api": ruta, "filas": int(len(comun)), "error_mediano": err, "ok": bool(err < 0.01)}
        out["ok"] = all(v["ok"] for v in out["columnas"].values())
    except D.ErrorDatos as e:
        out["ok"] = None
        out["motivo"] = f"la API de Futuros no responde desde esta computadora: {e}"
    return out


# ---------------------------------------------------------------------------
# Indicadores y estudio de eventos
# ---------------------------------------------------------------------------

def z_movil(s: pd.Series, n: int = 90) -> pd.Series:
    """z-score contra los n días PREVIOS (sin contar el actual)."""
    previo = s.shift(1).rolling(n, min_periods=max(30, n // 2))
    return (s - previo.mean()) / previo.std()


def percentil_previo(s: pd.Series, n: int = 90) -> pd.Series:
    """Qué parte (0–100) de los n días previos queda por debajo del valor de hoy."""
    vals = s.to_numpy(float)
    out = np.full(len(vals), np.nan)
    for i in range(n, len(vals)):
        ventana = vals[i - n:i]
        ventana = ventana[np.isfinite(ventana)]
        if len(ventana) >= n // 2 and np.isfinite(vals[i]):
            out[i] = (ventana < vals[i]).mean() * 100
    return pd.Series(out, index=s.index)


def tabla_simbolo(serie: pd.DataFrame, velas: pd.DataFrame, ventana: int = 90) -> pd.DataFrame:
    """Une la serie diaria de posicionamiento con los rendimientos futuros de Spot (índice = día de la señal)."""
    s = serie.copy()
    s.index = pd.to_datetime(s["dia"]).dt.tz_localize("UTC")
    s = s[~s.index.duplicated(keep="last")].sort_index()
    idx = pd.date_range(s.index[0], s.index[-1], freq="D")
    s = s.reindex(idx)
    t = pd.DataFrame(index=idx)
    t["top_largo"] = parte_larga(s["top_posiciones"].astype(float))
    t["masa_largo"] = parte_larga(s["masa_cuentas"].astype(float))
    t["brecha"] = t["top_largo"] - t["masa_largo"]
    t["z_top"] = z_movil(t["top_largo"], ventana)
    t["z_masa"] = z_movil(t["masa_largo"], ventana)
    t["pct_masa"] = percentil_previo(t["masa_largo"], ventana)
    o = velas["open"].reindex(idx)
    for h in (3, 7):
        # Señal al cierre del día D → se opera en la apertura de D+1 → se mide hasta la apertura de D+1+h
        t[f"ret_{h}"] = o.shift(-(1 + h)) / o.shift(-1) - 1
    return t


def eventos(t: pd.DataFrame, hip: str, D_: int = 3, z: float = 1.0, pct: float = 90.0) -> pd.Series:
    if hip == "H1":
        return ((t["z_top"] - t["z_top"].shift(D_)) >= z) & ((t["z_masa"] - t["z_masa"].shift(D_)) <= 0)
    return t["pct_masa"] >= pct


def efecto(panel: pd.DataFrame, col_evento: str, h: int) -> dict[str, Any]:
    ok = panel[f"ret_{h}"].notna()
    p = panel[ok]
    ev = p[p[col_evento]]
    if len(ev) == 0:
        return {"eventos": 0, "efecto_pct": float("nan")}
    return {"eventos": int(len(ev)), "media_evento_pct": float(ev[f"ret_{h}"].mean() * 100),
            "media_todos_pct": float(p[f"ret_{h}"].mean() * 100),
            "efecto_pct": float((ev[f"ret_{h}"].mean() - p[f"ret_{h}"].mean()) * 100)}


def ic_bloques(panel: pd.DataFrame, col_evento: str, h: int, n: int, semilla: int, dias_bloque: int = 20) -> tuple[float, float]:
    """Intervalo de confianza del 95 % del efecto, remuestreando bloques de `dias_bloque` días (todas las monedas juntas)."""
    p = panel[panel[f"ret_{h}"].notna()]
    if p[col_evento].sum() < 5:
        return float("nan"), float("nan")
    d0 = p["dia"].min()
    bloque = ((p["dia"] - d0) / pd.Timedelta(days=dias_bloque)).astype(int).to_numpy()
    grupos = {b: np.flatnonzero(bloque == b) for b in np.unique(bloque)}
    claves = list(grupos)
    r = p[f"ret_{h}"].to_numpy(float)
    e = p[col_evento].to_numpy(bool)
    rng = np.random.default_rng(semilla)
    vals = []
    for _ in range(n):
        sel = np.concatenate([grupos[claves[i]] for i in rng.integers(0, len(claves), len(claves))])
        if e[sel].sum() == 0:
            continue
        vals.append((r[sel][e[sel]].mean() - r[sel].mean()) * 100)
    if not vals:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def estudio(paneles: dict[str, pd.DataFrame], grandes: pd.DataFrame, reg: Reglamento, inicio, fin,
            n_boot: int = 2000) -> dict[str, Any]:
    cfg = reg.estrategias["M3"]
    fij = cfg.get("fijos", {})
    semilla = int(reg.get("validacion.semilla"))
    pct = float(fij.get("percentil_masa", 90))
    horizontes = [int(h) for h in fij.get("horizontes", [3, 7])]
    min_anios = float(fij.get("min_anios_mismo_signo_pct", 70))
    filas = []
    for s, t in paneles.items():
        # Solo días en que la moneda estaba en "grandes" (vigente para decidir al cierre de ese día)
        g = grandes[s].reindex(t.index + pd.Timedelta(days=1)).fillna(False).to_numpy(bool) if s in grandes else np.zeros(len(t), bool)
        x = t[(t.index >= inicio) & (t.index <= fin) & g].copy()
        if x.empty:
            continue
        x["simbolo"] = s
        x["dia"] = x.index
        for D_ in cfg["rejilla"]["D"]:
            for z in cfg["rejilla"]["z"]:
                x[f"H1_D{D_}_z{z}"] = eventos(x, "H1", int(D_), float(z)).to_numpy()
        x["H2"] = eventos(x, "H2", pct=pct).to_numpy()
        filas.append(x)
    if not filas:
        return {"pruebas": [], "panel_filas": 0}
    panel = pd.concat(filas, ignore_index=True)
    panel["anio"] = panel["dia"].dt.year
    pruebas = []
    columnas = [c for c in panel.columns if c.startswith("H1_")] + ["H2"]
    for col in columnas:
        signo = 1 if col.startswith("H1") else -1
        for h in horizontes:
            tot = efecto(panel, col, h)
            lo, hi = ic_bloques(panel, col, h, n_boot, semilla)
            por_anio = {}
            for anio, sub in panel.groupby("anio"):
                por_anio[int(anio)] = efecto(sub, col, h)
            anios_validos = [v for v in por_anio.values() if v["eventos"] >= 5 and np.isfinite(v["efecto_pct"])]
            mismo = sum(1 for v in anios_validos if np.sign(v["efecto_pct"]) == signo)
            pct_mismo = mismo / len(anios_validos) * 100 if anios_validos else 0.0
            ic_sin_cero = bool(np.isfinite(lo) and ((lo > 0 and signo > 0) or (hi < 0 and signo < 0)))
            pruebas.append({"prueba": col, "h": h, "signo_esperado": "+" if signo > 0 else "−", **tot,
                            "ic95": (lo, hi), "por_anio": por_anio, "anios_mismo_signo_pct": pct_mismo,
                            "anios_con_datos": len(anios_validos),
                            "pasa": bool(pct_mismo >= min_anios and ic_sin_cero)})
    return {"pruebas": pruebas, "panel_filas": int(len(panel)), "monedas": sorted(panel["simbolo"].unique()),
            "n_pruebas": len(pruebas), "hay_efecto": any(p["pasa"] for p in pruebas)}


def ejecutar(reg: Reglamento, cli: D.ClienteBinance, avisar=print) -> dict[str, Any]:
    from .ejecutar_v2 import mercado_diario
    from .validacion import fechas
    out: dict[str, Any] = {}
    avisar("ESTELA: verificando que la ruta exista y qué significa cada columna…")
    primeras = listar_dias(cli, "BTCUSDT")
    out["ruta_existe"] = bool(primeras)
    out["btc_desde"] = primeras[0] if primeras else None
    out["verificacion_api"] = verificar_columnas_api(cli)
    if not out["ruta_existe"]:
        out["apagado"] = "La ruta de datos no existe. M3 se queda apagado."
        return out
    md = mercado_diario(reg)
    f = fechas(reg)
    inicio, fin = f["inicio"], f["fin"]
    simbolos = sorted(c for c in md.grandes.columns if md.grandes.loc[md.grandes.index >= inicio, c].any())
    out["simbolos_grandes"] = simbolos
    desde, paneles, sin_perpetuo = {}, {}, []
    calentamiento = (inicio - pd.Timedelta(days=150)).strftime("%Y-%m-%d")
    for s in simbolos:
        dias = listar_dias(cli, s)
        if not dias:
            sin_perpetuo.append(s)
            continue
        desde[s] = dias[0]
        serie = descargar_simbolo(cli, s, calentamiento, fin.strftime("%Y-%m-%d"))
        if serie.empty or "top_posiciones" not in serie:
            sin_perpetuo.append(s)
            continue
        paneles[s] = tabla_simbolo(serie, md.velas[s], int(reg.estrategias["M3"]["fijos"].get("ventana_z", 90)))
        avisar(f"  {s}: datos desde {dias[0]} ({len(serie)} días)")
    out["desde_por_simbolo"] = desde
    out["sin_perpetuo"] = sin_perpetuo
    avisar("ESTELA: estudio de eventos…")
    out["estudio"] = estudio(paneles, md.grandes, reg, inicio, fin)
    out["hay_efecto"] = out["estudio"].get("hay_efecto", False)
    return out
