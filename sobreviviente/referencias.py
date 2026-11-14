"""Referencias para comparar (ronda 2): comprar y aguantar, DCA semanal y las versiones "puras"
de la tendencia larga (E6) y la rotación por momentum (E7).

"Pura" = como la describió Ángelo: todo el dinero adentro o afuera, sin el motor de riesgo
(sin 1 % de riesgo por operación ni tope de 30 % por posición). Sirve para ver la idea en sí.
Todas operan en la apertura siguiente a la decisión y pagan comisión + deslizamiento en cada cambio.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metricas import caida_maxima_pct


def metricas_curva(curva: pd.Series, invertido: pd.Series | None = None) -> dict[str, float]:
    """Rendimiento total, anual, caída máxima, volatilidad y 'Sharpe' (rendimiento ÷ volatilidad)."""
    c = curva.dropna()
    if len(c) < 2:
        return {}
    anios = (c.index[-1] - c.index[0]).days / 365.25
    r = c.pct_change().dropna()
    vol = float(r.std() * np.sqrt(365)) * 100
    total = float(c.iloc[-1] / c.iloc[0] - 1) * 100
    anual = float((c.iloc[-1] / c.iloc[0]) ** (1 / anios) - 1) * 100 if anios > 0 else float("nan")
    out = {"rend_total_pct": total, "rend_anual_pct": anual, "caida_max_pct": caida_maxima_pct(c.values),
           "volatilidad_pct": vol, "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else float("nan")}
    if invertido is not None:
        out["tiempo_invertido_pct"] = float(invertido.reindex(c.index).fillna(0).mean() * 100)
    return out


def _abierto_a_abierto(df: pd.DataFrame) -> pd.Series:
    """Rendimiento de apertura a apertura (se opera en aperturas)."""
    return df["open"].shift(-1) / df["open"] - 1.0


def comprar_aguantar(dfs: dict[str, pd.DataFrame], pesos: dict[str, float], inicio, fin, costo_pct: float) -> pd.Series:
    """Compra al inicio (con costo) y no vende nunca."""
    partes = []
    for s, w in pesos.items():
        df = dfs[s]
        o = df["open"][(df.index >= inicio) & (df.index <= fin)]
        partes.append(w * o / o.iloc[0] * (1 - costo_pct / 100))
    return sum(partes)


def dca_semanal(df: pd.DataFrame, inicio, fin, costo_pct: float, dia: int = 0) -> pd.Series:
    """Empieza con 1 en efectivo y lo invierte en partes iguales cada semana (lunes) en BTC."""
    o = df["open"][(df.index >= inicio) & (df.index <= fin)]
    dias_compra = o.index[o.index.day_of_week == dia]
    monto = 1.0 / len(dias_compra)
    efectivo, monedas = 1.0, 0.0
    valores = []
    for t, precio in o.items():
        if t in dias_compra:
            efectivo -= monto
            monedas += monto * (1 - costo_pct / 100) / precio
        valores.append(efectivo + monedas * precio)
    return pd.Series(valores, index=o.index)


def tendencia_pura(dfs: dict[str, pd.DataFrame], simbolos: list[str], sma: int, inicio, fin,
                   costo_pct: float) -> tuple[pd.Series, pd.Series]:
    """Cada moneda es la mitad del dinero: adentro si el cierre de ayer quedó arriba de su media de `sma` días."""
    curvas, invertido = [], []
    for s in simbolos:
        df = dfs[s]
        senal = (df["close"] > df["close"].rolling(sma).mean()).astype(float)
        pos = senal.shift(1).fillna(0.0)            # decidida al cierre de ayer, vigente desde la apertura de hoy
        cambio = pos.diff().abs().fillna(pos)
        r = pos * _abierto_a_abierto(df) - cambio * costo_pct / 100
        r = r[(r.index >= inicio) & (r.index <= fin)].fillna(0)
        curvas.append((1 + r).cumprod() / len(simbolos))
        invertido.append(pos.reindex(r.index) / len(simbolos))
    return sum(curvas), sum(invertido)


def rotacion_pura(spot1d: dict[str, pd.DataFrame], lugar: pd.DataFrame, btc_reg_diario: pd.Series, top: int,
                  inicio, fin, costo_pct: float, dia_rebalanceo: int = 6) -> tuple[pd.Series, pd.Series, int]:
    """Cada semana: las `top` monedas más fuertes en partes iguales (si BTC no está BAJISTA); si no, efectivo."""
    simb = list(lugar.columns)
    ret = pd.DataFrame({s: _abierto_a_abierto(spot1d[s]) for s in simb}).reindex(lugar.index)
    pesos = pd.DataFrame(np.nan, index=lugar.index, columns=simb)
    reb = lugar.index[lugar.index.day_of_week == dia_rebalanceo]
    for t in reb:
        w = pd.Series(0.0, index=simb)
        if btc_reg_diario.get(t) != "BAJISTA":
            elegidas = lugar.loc[t][lugar.loc[t] <= top].index
            if len(elegidas):
                w[elegidas] = 1.0 / len(elegidas)
        pesos.loc[t] = w
    pesos = pesos.ffill().fillna(0.0).shift(1).fillna(0.0)  # decididos al cierre, vigentes desde la apertura siguiente
    rotacion = pesos.diff().abs().sum(axis=1).fillna(pesos.abs().sum(axis=1))
    r = (pesos * ret.fillna(0.0)).sum(axis=1) - rotacion * costo_pct / 100
    r = r[(r.index >= inicio) & (r.index <= fin)]
    operaciones = int((pesos.diff().abs() > 1e-9).sum().sum())
    return (1 + r).cumprod(), pesos.sum(axis=1).reindex(r.index), operaciones


# ---------------------------------------------------------------------------
# v2: referencias obligatorias R0, R1 y R2 (señal al cierre diario, ejecución en la apertura siguiente)
# ---------------------------------------------------------------------------

def r0_aguantar(btc: pd.DataFrame, inicio, fin, costo_pct: float) -> tuple[pd.Series, pd.Series, int]:
    """R0: comprar BTC el primer día y aguantar."""
    curva = comprar_aguantar({"BTCUSDT": btc}, {"BTCUSDT": 1.0}, inicio, fin, costo_pct)
    return curva, pd.Series(1.0, index=curva.index), 1


def r1_marea(btc: pd.DataFrame, marea: pd.Series, inicio, fin, costo_pct: float) -> tuple[pd.Series, pd.Series, int]:
    """R1 (= M0): dentro de BTC si su cierre diario quedó arriba de la media de 200 días; si no, en USDT.
    `marea` = ALCISTA/BAJISTA por vela (índice = apertura del día de la señal)."""
    senal = (marea.reindex(btc.index) == "ALCISTA").astype(float)
    pos = senal.shift(1).fillna(0.0)  # decidida al cierre de D, vigente desde la apertura de D+1
    pos = pos[(pos.index >= inicio) & (pos.index <= fin)]
    # El primer día cuenta como compra si ya está dentro
    cambio = pos.diff().abs()
    cambio.iloc[0] = pos.iloc[0]
    r = pos * _abierto_a_abierto(btc).reindex(pos.index).fillna(0) - cambio * costo_pct / 100
    curva = (1 + r).cumprod()
    operaciones = int((cambio > 0).sum())
    return curva, pos, operaciones


def r2_canasta(velas: dict[str, pd.DataFrame], grandes: pd.DataFrame, vol_mediano: pd.DataFrame, marea: pd.Series,
               inicio, fin, costo_pct: float, n: int = 10) -> tuple[pd.Series, pd.Series, int]:
    """R2: las `n` grandes con más volumen, a partes iguales, rebalanceo mensual; todo a USDT cuando BTC cierra
    bajo su media de 200 días (y de regreso, con la canasta de ese día, cuando vuelve a cerrar arriba).

    `grandes` y `vol_mediano` con índice = día de DECISIÓN. Se simula con unidades reales (las monedas se
    mueven solas entre rebalanceos) y se cobra costo por cada compra y venta. Si una moneda deja de
    cotizar, se vende en su última apertura disponible."""
    dia = pd.Timedelta(days=1)
    idx = pd.date_range(pd.Timestamp(inicio), pd.Timestamp(fin), freq="D")
    simb = sorted(velas)
    aperturas = pd.DataFrame({s: velas[s]["open"] for s in simb}).reindex(idx)
    valores = pd.Series(0.0, index=simb)
    efectivo = 1.0
    curva, invertido = [], []
    operaciones = 0
    previa_alta = False
    for k, t in enumerate(idx):
        px = aperturas.loc[t]
        if k > 0:
            px_prev = aperturas.iloc[k - 1]
            for s in valores.index[valores > 0]:
                if np.isfinite(px[s]) and np.isfinite(px_prev[s]) and px_prev[s] > 0:
                    valores[s] *= px[s] / px_prev[s]
                else:  # dejó de cotizar: se vende al último precio conocido
                    efectivo += valores[s] * (1 - costo_pct / 100)
                    valores[s] = 0.0
                    operaciones += 1
        # Decisión tomada al cierre de ayer (vela t − 1 día), se ejecuta en esta apertura
        alta = marea.get(t - dia) == "ALCISTA"
        rebalanceo = alta and (t.day == 1 or not previa_alta or k == 0)
        objetivo = None
        if not alta and valores.sum() > 0:
            objetivo = pd.Series(0.0, index=simb)
        elif rebalanceo:
            dia_dec = t.floor("D")
            if dia_dec in grandes.index:
                g = grandes.loc[dia_dec]
                vm = vol_mediano.loc[dia_dec].reindex(simb).where(g.reindex(simb).fillna(False).astype(bool))
                vm = vm[[s for s in vm.index if np.isfinite(px.get(s, np.nan))]]
                elegidas = vm.dropna().sort_values(ascending=False).index[:n]
                if len(elegidas):
                    total = efectivo + valores.sum()
                    objetivo = pd.Series(0.0, index=simb)
                    objetivo[elegidas] = total / len(elegidas)
        if objetivo is not None:
            delta = objetivo - valores
            costo = delta.abs().sum() * costo_pct / 100
            operaciones += int((delta.abs() > 1e-12).sum())
            efectivo = efectivo + valores.sum() - objetivo.sum() - costo
            valores = objetivo.copy()
            if efectivo < 0:  # el costo sale de las posiciones a prorrata
                valores *= (valores.sum() + efectivo) / valores.sum()
                efectivo = 0.0
        previa_alta = alta
        total = efectivo + valores.sum()
        curva.append(total)
        invertido.append(valores.sum() / total if total > 0 else 0.0)
    return pd.Series(curva, index=idx), pd.Series(invertido, index=idx), operaciones


def por_anio(curva: pd.Series) -> dict[int, float]:
    """Rendimiento de cada año calendario (%)."""
    out = {}
    for anio, c in curva.groupby(curva.index.year):
        base = curva[curva.index < c.index[0]]
        inicio = base.iloc[-1] if len(base) else c.iloc[0]
        out[int(anio)] = float(c.iloc[-1] / inicio - 1) * 100
    return out
