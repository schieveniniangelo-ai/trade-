"""Arreglo 39 (decisión de Ángelo: excluir las 104 bStocks) + detección por la firma de permisos de Binance.

Todo con exchangeInfo simulado, sin red."""
import pandas as pd

from sobreviviente import cli_ronda as CR
from sobreviviente import papel as P
from sobreviviente import universo as U

from test_arreglo1_papel import _dia_marea_alta, _reg_m0
from test_arreglo37_bstocks_fuera import BSTOCKS
from test_arreglo6_datos_malos import ClienteFalso, _velas_completas

NUEVAS_88 = ("AAOIB AAPLB ADBEB AGPUB ALABB AMATB AMCB AMDB AMZNB APPB ARMB ASMLB ASTSB AVGOB AXTIB BABAB BBB BEB BMNRB "
             "BOTB BRKBB BSPB COHRB CRDOB CRMB CRWDB CRWVB CYPHB DELLB DJTB EWYB FLNCB FWDIB GEVB GMEB GPROB GSB HIMSB HOODB "
             "HPEB IBMB INTCB INTWB IRENB JPMB KORUB KSTRB LITEB LLYB MDBB METAB MRNAB MRVLB MSFTB MSTRB MUUB MVLLB NFLXB "
             "NOKB ORCLB PDDB PENGB PLTRB PYPLB QNTB QQQB RDDTB RKLBB SECZB SHAZB SKDDB SKHYB SKUUB SMCIB SMHB SNXXB SOXSB "
             "SQQQB STXB TMFB TQQQB TSMB USARB USDEB UVXYB VSTB WENB ZMB").split()
LAS_104 = BSTOCKS + NUEVAS_88
# Firma de permisos como la de SOXLBUSDT (dos grupos para poder probar el orden) y una de cripto, distinta
FIRMA_B = [["SPOT", "TRD_GRP_004", "TRD_GRP_261"], ["MARGIN", "TRD_GRP_005"]]
FIRMA_CRIPTO = [["SPOT", "TRD_GRP_004", "TRD_GRP_015", "TRD_GRP_271"], ["MARGIN", "TRD_GRP_005"]]
CRIPTO = ["BTC", "ETH", "BNB", "ARB", "SHIB"]


def _par(base, firma=None, status="TRADING"):
    s = {"symbol": f"{base}USDT", "baseAsset": base, "quoteAsset": "USDT", "status": status}
    if firma is not None:
        s["permissionSets"] = firma
    return s


def _info(*extra, sin_permisos=False):
    pares = [_par(b, None if sin_permisos else FIRMA_B) for b in LAS_104]
    pares += [_par(b, None if sin_permisos else FIRMA_CRIPTO) for b in CRIPTO]
    return {"symbols": pares + list(extra)}


def test_las_104_quedan_fuera(reg):
    assert len(LAS_104) == len(set(LAS_104)) == 104
    assert set(reg.get("universo.excluir_bases")) == set(LAS_104) | {"BNCB"}   # BNCB: decisión de Ángelo
    cand = U.simbolos_candidatos(reg, _info())
    assert not [s for s in cand if s[:-4] in LAS_104]


def test_cripto_con_b_entra_y_no_avisa(reg):
    cand = U.simbolos_candidatos(reg, _info())
    for b in CRIPTO:
        assert f"{b}USDT" in cand
    assert U.bstocks_detectadas(reg, _info())[1] == []
    assert P.avisos_bstocks(reg, _info()) == []


def test_bstock_nueva_con_la_misma_firma_se_excluye_y_avisa(reg):
    info = _info(_par("ZZZZB", FIRMA_B))
    assert "ZZZZBUSDT" not in U.simbolos_candidatos(reg, info)
    excluidas, raras = U.bstocks_detectadas(reg, info)
    assert "ZZZZB" in excluidas and raras == []
    assert "ℹ️ Nueva bStock excluida automáticamente: ZZZZB; agrégala a excluir_bases." in P.avisos_bstocks(reg, info)


def test_misma_firma_sin_b_entra_y_es_rara(reg):
    info = _info(_par("ZZZZ", FIRMA_B))
    assert "ZZZZUSDT" in U.simbolos_candidatos(reg, info)
    assert U.bstocks_detectadas(reg, info)[1] == ["ZZZZUSDT"]
    assert P.avisos_bstocks(reg, info) == [
        "ℹ️ Par raro en Binance (¿acción tokenizada?): ZZZZUSDT. Si no es cripto, agrégala a universo.excluir_bases; "
        "si lo es, a universo.permitir_con_B."]


def test_bncb_con_firma_casi_igual_entra_y_es_rara(reg):
    info = _info(_par("BNCB", [FIRMA_B[0]]))                     # le falta un grupo
    sin_bncb = reg.copia_con({"universo.excluir_bases": LAS_104})  # como antes de que Ángelo la sacara del universo
    assert "BNCBUSDT" in U.simbolos_candidatos(sin_bncb, info)
    assert U.bstocks_detectadas(sin_bncb, info) == (set(LAS_104), ["BNCBUSDT"])
    assert "BNCBUSDT" not in U.simbolos_candidatos(reg, info)     # hoy: fuera por decisión de Ángelo, sin aviso
    assert U.bstocks_detectadas(reg, info)[1] == []


def test_grupos_en_otro_orden_dan_lo_mismo(reg):
    revuelta = [list(reversed(FIRMA_B[1])), list(reversed(FIRMA_B[0]))]
    info = _info(_par("ZZZZB", revuelta))
    assert "ZZZZB" in U.bstocks_detectadas(reg, info)[0]
    assert "ZZZZBUSDT" not in U.simbolos_candidatos(reg, info)


def test_copia_vieja_sin_permisos_no_truena_y_vale_la_lista(reg):
    info = _info(_par("ZZZZB"), sin_permisos=True)
    cand = U.simbolos_candidatos(reg, info)
    assert not [s for s in cand if s[:-4] in LAS_104]
    assert "BTCUSDT" in cand and "BNBUSDT" in cand
    excluidas, _ = U.bstocks_detectadas(reg, info)
    assert excluidas == set(reg.get("universo.excluir_bases"))    # sin firma no se adivina nada: solo la lista fija


class _ClienteConParRaro(ClienteFalso):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.velas["ZZZZUSDT"] = self.velas["AUSDT"]
        self.apertura["ZZZZUSDT"] = self.apertura["AUSDT"]

    def exchange_info(self, mercado="SPOT", forzar=False):
        info = super().exchange_info(mercado, forzar)
        filtros = info["symbols"][0]["filters"]
        for s in info["symbols"]:
            s["permissionSets"] = FIRMA_CRIPTO
        info["symbols"] += [{**_par("SOXLB", FIRMA_B), "filters": filtros}, {**_par("ZZZZ", FIRMA_B), "filters": filtros}]
        return info


def test_ronda_con_par_raro_avisa_sin_modo_seguro_y_con_pulgar(reg, tmp_path, capsys):
    r = _reg_m0(reg, tmp_path)
    r.datos["estrategias"]["M0"]["estado"] = "APAGADA"
    k = _dia_marea_alta(r)
    cli = _ClienteConParRaro(tmp_path, _velas_completas(), k)
    ahora = (cli.hoy + pd.Timedelta(minutes=10)).to_pydatetime()
    for vez in ("primera", "repetida"):
        assert CR.correr_ronda(r, ahora=ahora, cliente=cli, memes=[]) == 0
        salida = capsys.readouterr().out
        assert ("ya corrió" in salida) == (vez == "repetida")
        assert "ℹ️ Par raro en Binance (¿acción tokenizada?):" in salida and "ZZZZUSDT" in salida, vez
        assert "MODO SEGURO" not in salida and "👍 No necesito nada de ti." in salida, vez
