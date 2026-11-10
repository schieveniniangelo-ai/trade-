"""Arreglo 37 (decisión de Ángelo): las bStocks (valores tokenizados, no cripto) quedan fuera del universo."""
from sobreviviente import universo as U

BSTOCKS = ["SNDKB", "SOXLB", "SPCXB", "CRCLB", "MUB", "NVDAB", "TSLAB", "CBRSB", "COINB", "DRAMB", "GLWB", "GOOGLB",
           "NBISB", "QCOMB", "SPYB", "WDCB"]


def test_ninguna_bstock_entra_al_universo(reg):
    lista = reg.get("universo.excluir_bases")
    assert set(BSTOCKS) <= set(lista) and len(set(lista)) == 105      # las 104 bStocks + BNCB (decisión de Ángelo)
    bases = ["BTC", "ETH"] + BSTOCKS
    info = {"symbols": [{"symbol": f"{b}USDT", "baseAsset": b, "quoteAsset": "USDT", "status": "TRADING"} for b in bases]}
    candidatos = U.simbolos_candidatos(reg, info)
    assert "BTCUSDT" in candidatos and "ETHUSDT" in candidatos
    assert not [s for s in candidatos if s[:-len("USDT")] in BSTOCKS]
