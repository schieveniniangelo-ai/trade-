"""Descarga de datos públicos de Binance (sin llaves) y caché local.

- Spot: API principal; si responde 451/403 (bloqueo por región) o falla, usa el respaldo oficial.
- Futuros: API `fapi`; si no se puede, los históricos oficiales de data.binance.vision.
- Históricos: se guardan en `datos/cache/` como CSV comprimido y se actualizan por partes.
"""
from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .reglamento import Reglamento

log = logging.getLogger("sobreviviente.datos")

COLUMNAS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
            "trades", "taker_base", "taker_quote", "ignore"]
MS_POR_INTERVALO = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


class ErrorDatos(Exception):
    """No se pudieron obtener datos confiables."""


class ClienteBinance:
    """Cliente mínimo de datos públicos de Binance, con respaldo automático."""

    def __init__(self, reg: Reglamento, timeout: float = 20.0):
        self.reg = reg
        self.timeout = timeout
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "sobreviviente-pro/1.0"
        # Las descargas usan hasta 16 hilos: el depósito de conexiones debe alcanzar para todos.
        adaptador = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16)
        self.sesion.mount("https://", adaptador)
        d = reg.datos["datos"]
        self.urls_spot = [d["url_principal"], d["url_respaldo"]]
        self.url_futuros = d["url_futuros"]
        self.url_hist = d["url_historicos"]
        self._spot_bloqueado = False
        self.futuros_disponible: bool | None = None
        # Copias viejas usadas porque no se pudo actualizar (la ronda las reporta; > 48 h = MODO SEGURO)
        self.avisos_copias: list[str] = []
        self.edad_copia_max_h: float = 0.0
        self.carpeta = Path(reg.get("datos.carpeta", "datos"))
        if not self.carpeta.is_absolute() and reg.ruta is not None:
            self.carpeta = reg.ruta.parent / self.carpeta
        self.cache = self.carpeta / "cache"

    # ------------------------------------------------------------------ HTTP
    def _get(self, url: str, params: dict[str, Any] | None = None, intentos: int = 3) -> requests.Response:
        ultimo: Exception | None = None
        for i in range(intentos):
            try:
                r = self.sesion.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429 or r.status_code == 418:
                    espera = int(r.headers.get("Retry-After", "5"))
                    log.warning("Binance pide esperar %s s (límite de peticiones)", espera)
                    time.sleep(min(espera, 60))
                    continue
                return r
            except requests.RequestException as e:
                ultimo = e
                time.sleep(1.5 * (i + 1))
        raise ErrorDatos(f"No pude conectarme a {url}: {ultimo}")

    def spot(self, ruta: str, params: dict[str, Any] | None = None) -> Any:
        """GET a la API de Spot, cambiando al respaldo si la principal está bloqueada."""
        urls = self.urls_spot[1:] if self._spot_bloqueado else self.urls_spot
        errores = []
        for base in urls:
            try:
                r = self._get(base + ruta, params)
            except ErrorDatos as e:
                errores.append(str(e))
                continue
            if r.status_code in (451, 403):
                log.info("%s bloqueado por región (%s); uso el respaldo", base, r.status_code)
                if base == self.urls_spot[0]:
                    self._spot_bloqueado = True
                errores.append(f"{base}: {r.status_code}")
                continue
            if r.status_code != 200:
                errores.append(f"{base}: {r.status_code} {r.text[:200]}")
                continue
            return r.json()
        raise ErrorDatos("No pude obtener datos de Spot: " + " | ".join(errores))

    def futuros(self, ruta: str, params: dict[str, Any] | None = None) -> Any:
        """GET a la API pública de Futuros. Lanza ErrorDatos si está bloqueada."""
        if self.futuros_disponible is False:
            raise ErrorDatos("La API de Futuros no está disponible desde esta computadora.")
        r = self._get(self.url_futuros + ruta, params)
        if r.status_code in (451, 403):
            self.futuros_disponible = False
            raise ErrorDatos(f"La API de Futuros respondió {r.status_code} (bloqueo por región).")
        if r.status_code != 200:
            raise ErrorDatos(f"Futuros respondió {r.status_code}: {r.text[:200]}")
        self.futuros_disponible = True
        return r.json()

    # --------------------------------------------------------- exchangeInfo
    def exchange_info(self, mercado: str = "SPOT", forzar: bool = False) -> dict[str, Any]:
        """Reglas del exchange. Caché de `cache_exchangeinfo_horas` (1 día por defecto)."""
        self.cache.mkdir(parents=True, exist_ok=True)
        archivo = self.cache / f"exchangeinfo_{mercado.lower()}.json"
        horas = float(self.reg.get("datos.cache_exchangeinfo_horas", 24))
        if archivo.exists() and not forzar:
            edad = (time.time() - archivo.stat().st_mtime) / 3600
            if edad < horas:
                return json.loads(archivo.read_text())
        try:
            datos = self.spot("/api/v3/exchangeInfo") if mercado == "SPOT" else self.futuros("/fapi/v1/exchangeInfo")
        except ErrorDatos:
            if archivo.exists():
                log.warning("No pude actualizar exchangeInfo de %s; uso la copia guardada", mercado)
                self.anotar_copia(f"las reglas de Binance de {mercado} (exchangeInfo)", archivo.stat().st_mtime)
                return json.loads(archivo.read_text())
            raise
        archivo.write_text(json.dumps(datos))
        return datos

    def anotar_copia(self, que: str, marca_tiempo: float) -> None:
        """Registra que se usó una copia guardada (no actualizada) y qué tan vieja es."""
        edad_h = max(0.0, (time.time() - marca_tiempo) / 3600)
        fecha = datetime.fromtimestamp(marca_tiempo, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.avisos_copias.append(f"se usó una copia de {fecha} de {que}; no está al día")
        self.edad_copia_max_h = max(self.edad_copia_max_h, edad_h)

    # ---------------------------------------------------------------- velas
    def velas_api(self, simbolo: str, intervalo: str, inicio_ms: int, fin_ms: int | None = None,
                  mercado: str = "SPOT") -> pd.DataFrame:
        """Velas desde la API (paginando de 1000 en 1000). Solo velas ya CERRADAS."""
        filas: list[list[Any]] = []
        paso = MS_POR_INTERVALO[intervalo]
        ahora_ms = int(time.time() * 1000)
        fin_ms = fin_ms or ahora_ms
        cursor = inicio_ms
        while cursor < fin_ms:
            params = {"symbol": simbolo, "interval": intervalo, "startTime": cursor, "limit": 1000}
            datos = self.spot("/api/v3/klines", params) if mercado == "SPOT" else \
                self.futuros("/fapi/v1/klines", {**params, "limit": 1500})
            if not datos:
                break
            filas.extend(datos)
            ultimo = int(datos[-1][0])
            if ultimo + paso <= cursor:
                break
            cursor = ultimo + paso
            if len(datos) < 2:
                break
        df = a_dataframe(filas)
        if df.empty:
            return df
        # Quitar la vela que todavía no cierra.
        df = df[df["close_time"] < pd.Timestamp(ahora_ms, unit="ms", tz="UTC")]
        return df[df.index < pd.Timestamp(fin_ms, unit="ms", tz="UTC")]

    def zip_historico(self, ruta: str) -> pd.DataFrame | None:
        """Descarga un .zip mensual de data.binance.vision. None si no existe."""
        r = self._get(f"{self.url_hist}/{ruta}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise ErrorDatos(f"Históricos respondieron {r.status_code} para {ruta}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            nombre = z.namelist()[0]
            crudo = z.read(nombre).decode()
        return pd.read_csv(io.StringIO(crudo), header=None)

    def velas_futuros_historicas(self, simbolo: str, intervalo: str, meses: list[str]) -> pd.DataFrame:
        """Velas de Futuros USDⓈ-M desde los archivos mensuales oficiales."""
        partes = []
        for m in meses:
            df = self.zip_historico(f"data/futures/um/monthly/klines/{simbolo}/{intervalo}/{simbolo}-{intervalo}-{m}.zip")
            if df is not None:
                partes.append(_limpiar_csv_klines(df))
        if not partes:
            return pd.DataFrame()
        return a_dataframe(pd.concat(partes).values.tolist())

    def funding_historico(self, simbolo: str, meses: list[str]) -> pd.Series:
        """Tasas de funding (fracción por periodo de 8 h) desde los archivos mensuales oficiales."""
        partes = []
        for m in meses:
            df = self.zip_historico(f"data/futures/um/monthly/fundingRate/{simbolo}/{simbolo}-fundingRate-{m}.zip")
            if df is None:
                continue
            if not str(df.iloc[0, 0]).isdigit():
                df = df.iloc[1:]
            partes.append(df.iloc[:, [0, 2]].astype(float))
        if not partes:
            return pd.Series(dtype=float)
        x = pd.concat(partes)
        idx = pd.to_datetime(x.iloc[:, 0].astype("int64"), unit="ms", utc=True)
        return pd.Series(x.iloc[:, 1].values, index=idx).sort_index().loc[lambda s: ~s.index.duplicated()]

    def funding_api(self, simbolo: str, inicio_ms: int) -> pd.Series:
        """Funding desde la API de Futuros."""
        filas = []
        cursor = inicio_ms
        while True:
            datos = self.futuros("/fapi/v1/fundingRate", {"symbol": simbolo, "startTime": cursor, "limit": 1000})
            if not datos:
                break
            filas.extend(datos)
            cursor = int(datos[-1]["fundingTime"]) + 1
            if len(datos) < 1000:
                break
        if not filas:
            return pd.Series(dtype=float)
        idx = pd.to_datetime([int(f["fundingTime"]) for f in filas], unit="ms", utc=True)
        return pd.Series([float(f["fundingRate"]) for f in filas], index=idx)


# ---------------------------------------------------------------------------
# Conversión y caché
# ---------------------------------------------------------------------------

def _a_ms(serie: pd.Series) -> pd.Series:
    """Algunos archivos nuevos de Binance usan microsegundos: los paso a milisegundos."""
    s = serie.astype("int64")
    return s.where(s < 10**14, s // 1000)


def _limpiar_csv_klines(df: pd.DataFrame) -> pd.DataFrame:
    if not str(df.iloc[0, 0]).isdigit():  # trae encabezado
        df = df.iloc[1:]
    df = df.iloc[:, :12].copy()
    df.columns = COLUMNAS
    return df


def a_dataframe(filas: list[list[Any]]) -> pd.DataFrame:
    """Convierte filas de klines en un DataFrame con índice de tiempo UTC (apertura de la vela)."""
    if not filas:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "quote_volume", "trades", "close_time"])
    df = pd.DataFrame([f[:12] for f in filas], columns=COLUMNAS)
    df["open_time"] = _a_ms(df["open_time"])
    df["close_time"] = _a_ms(df["close_time"])
    for c in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[c] = df[c].astype(float)
    df["trades"] = df["trades"].astype("int64")
    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df.index.name = "tiempo"
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df[["open", "high", "low", "close", "volume", "quote_volume", "trades", "close_time"]]
    return df[~df.index.duplicated(keep="last")].sort_index()


def guardar(df: pd.DataFrame, archivo: Path) -> None:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    tmp = archivo.with_suffix(".tmp")
    df.drop(columns=["close_time"], errors="ignore").to_csv(tmp, compression="gzip")
    tmp.replace(archivo)


def leer(archivo: Path) -> pd.DataFrame:
    if not archivo.exists():
        return pd.DataFrame()
    df = pd.read_csv(archivo, index_col=0, compression="gzip")
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def ruta_cache(cliente: ClienteBinance, mercado: str, intervalo: str, simbolo: str) -> Path:
    return cliente.cache / mercado.lower() / intervalo / f"{simbolo}.csv.gz"


def actualizar_spot(cliente: ClienteBinance, simbolo: str, intervalo: str, inicio: str,
                    fin: str | None = None) -> pd.DataFrame:
    """Descarga (o completa) el histórico de Spot de un símbolo y lo guarda en caché."""
    archivo = ruta_cache(cliente, "spot", intervalo, simbolo)
    viejo = leer(archivo)
    inicio_ms = int(pd.Timestamp(inicio, tz="UTC").value // 10**6)
    if not viejo.empty:
        inicio_ms = max(inicio_ms, int(viejo.index[-1].value // 10**6) + MS_POR_INTERVALO[intervalo])
    fin_ms = int(pd.Timestamp(fin, tz="UTC").value // 10**6) if fin else None
    nuevo = cliente.velas_api(simbolo, intervalo, inicio_ms, fin_ms)
    if nuevo.empty:
        return viejo
    nuevo = nuevo.drop(columns=["close_time"])
    df = pd.concat([viejo, nuevo]) if not viejo.empty else nuevo
    df = df[~df.index.duplicated(keep="last")].sort_index()
    guardar(df, archivo)
    return df


def meses_entre(inicio: str, fin: str) -> list[str]:
    """Lista de meses 'AAAA-MM' entre dos fechas (incluidas)."""
    p = pd.period_range(pd.Timestamp(inicio), pd.Timestamp(fin), freq="M")
    return [str(x) for x in p]


def actualizar_futuros(cliente: ClienteBinance, simbolo: str, intervalo: str, inicio: str,
                       fin: str) -> tuple[pd.DataFrame, pd.Series]:
    """Velas y funding de Futuros. Usa la API si está disponible; si no, los archivos mensuales."""
    archivo = ruta_cache(cliente, "futuros", intervalo, simbolo)
    archivo_f = cliente.cache / "futuros" / "funding" / f"{simbolo}.csv.gz"
    velas = leer(archivo)
    funding = pd.Series(dtype=float)
    if archivo_f.exists():
        x = pd.read_csv(archivo_f, index_col=0, compression="gzip")
        x.index = pd.to_datetime(x.index, utc=True, format="ISO8601")
        funding = x.iloc[:, 0]
    if velas.empty:
        meses = meses_entre(inicio, fin)
        velas = cliente.velas_futuros_historicas(simbolo, intervalo, meses)
        if not velas.empty:
            guardar(velas, archivo)
            velas = leer(archivo)
        funding = cliente.funding_historico(simbolo, meses)
        if not funding.empty:
            archivo_f.parent.mkdir(parents=True, exist_ok=True)
            funding.rename("funding").to_csv(archivo_f, compression="gzip")
    return velas, funding


def resamplear(df: pd.DataFrame, regla: str = "4h") -> pd.DataFrame:
    """Convierte velas de 1 h en velas de 4 h (o 1 d), alineadas a medianoche UTC como Binance.

    Una vela de 4 h solo se arma si están sus 4 velas de 1 h (si falta alguna, se descarta).
    """
    if df.empty:
        return df
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
           "quote_volume": "sum", "trades": "sum"}
    cols = {k: v for k, v in agg.items() if k in df.columns}
    g = df.resample(regla, label="left", closed="left")
    out = g.agg(cols)
    cuenta = g["close"].count()
    esperado = int(pd.Timedelta(regla) / pd.Timedelta("1h"))
    out = out[cuenta >= esperado]
    return out.dropna(subset=["close"])


def descargar_muchos(funcion, argumentos: list[tuple], hilos: int = 8) -> list[Any]:
    """Corre descargas en paralelo (las peticiones son ligeras y Binance permite muchas por minuto)."""
    resultados = []
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        futuros = [ex.submit(funcion, *a) for a in argumentos]
        for f in futuros:
            try:
                resultados.append(f.result())
            except Exception as e:  # noqa: BLE001 - se registra y se sigue con los demás
                log.warning("Falló una descarga: %s", e)
                resultados.append(None)
    return resultados


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)
