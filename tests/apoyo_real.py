"""Piezas comunes para las pruebas del dinero real (arreglos 129 a 141): respuestas falsas del conector de Binance,
sin red ni llaves."""
import json
from datetime import datetime, timezone
from pathlib import Path

from sobreviviente import reglamento

AHORA = datetime(2026, 11, 16, 0, 12, tzinfo=timezone.utc)   # 6:12 p. m. CDMX del domingo 15 nov
UPDATE_TIME = 1763251900000      # el updateTime fijo de `cuenta()` (es de nov 2025: más viejo que cualquier llenado)


def reg_real(tmp_path, **cambios):
    r = reglamento.cargar().copia_con({"datos.carpeta": str(tmp_path / "datos"), **cambios})
    r.ruta = tmp_path / "reglamento.yaml"
    return r


def reg_abierto(tmp_path, **cambios):
    """Arreglo 185: el reglamento con la puerta del real ABIERTA (M0 en VIVA_MINI), como estuvo del 16 al 22 nov 2026.
    Desde el 22 nov (DECISIÓN DE ÁNGELO) el reglamento de verdad tiene M0 en PAPEL: el real no corre."""
    return reg_real(tmp_path, **{"estrategias.M0.estado": "VIVA_MINI", **cambios})


def reg_antes(tmp_path, **cambios):
    """El reglamento como estaba antes del arreglo 140 (M0 en PAPEL y sin el bloque `real:`): la puerta cerrada."""
    r = reg_real(tmp_path, **{"estrategias.M0.estado": "PAPEL", **cambios})
    r.datos.pop("real", None)
    return r


def cuenta(usdt=142.54, usdt_bloq=0.0, btc=0.0, btc_bloq=0.0, can_trade=True, envolver=False, **otros):
    balances = [{"asset": "USDT", "free": f"{usdt:.8f}", "locked": f"{usdt_bloq:.8f}"},
                {"asset": "BTC", "free": f"{btc:.8f}", "locked": f"{btc_bloq:.8f}"},
                {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"}]
    balances += [{"asset": a, "free": f"{v:.8f}", "locked": "0.00000000"} for a, v in otros.items()]
    x = {"makerCommission": 10, "takerCommission": 10, "canTrade": can_trade, "canWithdraw": False,
         "canDeposit": True, "updateTime": UPDATE_TIME, "accountType": "SPOT", "balances": balances,
         "permissions": ["SPOT"]}
    return {"data": x} if envolver else x


def orden_stop(cantidad="0.00012000", stop="59500.00000000", limite="59202.50000000", client="sp0123456789abcdef",
               order_id=123, estado="NEW", lado="SELL", tipo="STOP_LOSS_LIMIT", simbolo="BTCUSDT"):
    return {"symbol": simbolo, "orderId": order_id, "clientOrderId": client, "price": limite, "origQty": cantidad,
            "executedQty": "0.00000000", "status": estado, "timeInForce": "GTC", "type": tipo, "side": lado,
            "stopPrice": stop, "time": 1763251900000}


def escribir_entrada(tmp_path, cta, ordenes):
    carpeta = Path(tmp_path) / "entrada"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "cuenta.json").write_text(json.dumps(cta), encoding="utf-8")
    (carpeta / "ordenes.json").write_text(json.dumps(ordenes), encoding="utf-8")
    return carpeta / "cuenta.json", carpeta / "ordenes.json"


def al_dia(cta, ahora):
    """Arreglo 184: la misma cuenta con updateTime de un minuto antes de `ahora` (la hora de la foto), si traía el fijo
    de `cuenta()`. Así una foto tomada después de un llenado se ve como la de verdad (Binance la actualizó al llenar)."""
    import copy
    cta = copy.deepcopy(cta)
    x = cta.get("data", cta) if isinstance(cta, dict) else cta
    if isinstance(x, dict) and x.get("updateTime") == UPDATE_TIME:
        x["updateTime"] = int(ahora.timestamp() * 1000) - 60_000
    return cta
