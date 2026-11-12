"""Lógica da busca de limites (sem Windows, sem janela: tudo aqui é testável)."""
from __future__ import annotations

import datetime as dt
import math

# (chave, nome mostrado, unidade)
CAMPOS = [
    ("freq", "DRAM Frequency", "MT/s"),
    ("fclk", "FCLK Frequency", "MHz"),
    ("vdram", "DRAM Voltage", "V"),
    ("vsoc", "CPU NB/SoC Voltage", "V"),
    ("gdm", "GearDown Mode (1=Enabled)", ""),
    ("tCL", "tCL", ""),
    ("tRCDRD", "tRCDRD", ""),
    ("tRCDWR", "tRCDWR", ""),
    ("tRP", "tRP", ""),
    ("tRAS", "tRAS", ""),
    ("tRC", "tRC", ""),
    ("tRFC", "tRFC (tRFC2/tRFC4 em Auto)", ""),
    ("tRRDS", "tRRDS", ""),
    ("tRRDL", "tRRDL", ""),
    ("tFAW", "tFAW", ""),
    ("tWTRS", "tWTRS", ""),
    ("tWTRL", "tWTRL", ""),
    ("tWR", "tWR", ""),
    ("tRTP", "tRTP", ""),
    ("tCWL", "tCWL", ""),
]
NOMES = {k: n for k, n, _ in CAMPOS}
DECIMAIS = ("vdram", "vsoc")

# Exemplo (XMP 3200 CL16). O usuário confere e corrige antes de começar.
PADRAO_MEM = {
    "freq": 3200, "fclk": 1600, "vdram": 1.35, "vsoc": 1.10, "gdm": 1,
    "tCL": 16, "tRCDRD": 18, "tRCDWR": 18, "tRP": 18, "tRAS": 36, "tRC": 54,
    "tRFC": 560, "tRRDS": 6, "tRRDL": 8, "tFAW": 32, "tWTRS": 4, "tWTRL": 12,
    "tWR": 24, "tRTP": 12, "tCWL": 16,
}

ORDEM_MEM = ["freq", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRFC", "grupoRRD", "grupoWTR", "tWR"]
DESCR_ETAPA = {
    "freq": "Frequência",
    "tCL": "tCL (latência CAS)",
    "tRCDRD": "tRCDRD",
    "tRCDWR": "tRCDWR",
    "tRP": "tRP",
    "tRAS": "tRAS",
    "tRFC": "tRFC (refresh)",
    "grupoRRD": "tRRDS / tRRDL / tFAW",
    "grupoWTR": "tWTRS / tWTRL",
    "tWR": "tWR / tRTP",
}
TRFC_NS = [350, 320, 300, 280, 260, 240]
VDRAM_SEGURA = 1.40     # máximo que o app propõe
VDRAM_MAX = 1.45        # acima disso o app não aceita
VSOC_MAX = 1.15
CO_PASSOS = [-5, -10, -15, -20, -25, -30]

LIMITES = {  # validação do perfil digitado
    "freq": (1600, 5000), "fclk": (0, 2200), "vdram": (1.10, VDRAM_MAX), "vsoc": (0.80, 1.25),
    "gdm": (0, 1), "tCL": (10, 30), "tRCDRD": (10, 30), "tRCDWR": (6, 30), "tRP": (10, 30),
    "tRAS": (20, 60), "tRC": (30, 100), "tRFC": (150, 1200), "tRRDS": (3, 12), "tRRDL": (4, 14),
    "tFAW": (12, 60), "tWTRS": (2, 12), "tWTRL": (4, 24), "tWR": (8, 32), "tRTP": (4, 16),
    "tCWL": (9, 30),
}


def agora_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def validar_perfil(p: dict) -> list[str]:
    erros = []
    for k, _, _ in CAMPOS:
        if k not in p:
            erros.append(f"{NOMES[k]}: faltando")
            continue
        lo, hi = LIMITES[k]
        if not (lo <= p[k] <= hi):
            erros.append(f"{NOMES[k]}: {p[k]} fora de {lo}–{hi}")
    if not erros and p["tRC"] < p["tRP"] + p["tRAS"] - 2:
        erros.append("tRC deveria ser ≈ tRP + tRAS")
    return erros


def ns_trfc(p: dict) -> float:
    return p["tRFC"] * 2000.0 / p["freq"]


def recalcular(p: dict, tem_fclk: bool) -> dict:
    p["tRC"] = p["tRP"] + p["tRAS"]
    p["fclk"] = p["freq"] // 2 if tem_fclk else 0
    return p


def candidato(passo: str, p: dict, mem: dict, cpu: dict) -> dict | None:
    """Próxima alteração mais agressiva do ajuste 'passo', ou None se acabou."""
    if passo == "freq":
        maiores = [f for f in cpu["freqs"] if f > p["freq"]]
        if not maiores:
            return None
        f = maiores[0]
        mud = {"freq": f, "tRFC": math.ceil(ns_trfc(p) * f / 2000)}
        if mem.get("mais_tensao") and p["vdram"] < VDRAM_SEGURA:
            mud["vdram"] = VDRAM_SEGURA
        if f >= 3733 and cpu["tem_fclk"] and p["vsoc"] < 1.125:
            mud["vsoc"] = 1.125
        return mud
    if passo == "tCL":
        v = p["tCL"] - (2 if p["gdm"] else 1)
        return {"tCL": v, "tCWL": min(p["tCWL"], v)} if v >= 14 else None
    if passo == "tRCDRD":
        v = p["tRCDRD"] - 1
        return {"tRCDRD": v} if v >= 14 else None
    if passo == "tRCDWR":
        v = p["tRCDWR"] - 2
        return {"tRCDWR": v} if v >= 8 else None
    if passo == "tRP":
        v = p["tRP"] - 1
        return {"tRP": v} if v >= 14 else None
    if passo == "tRAS":
        minimo = max(28, p["tCL"] + p["tRCDRD"])
        return {"tRAS": max(p["tRAS"] - 2, minimo)} if p["tRAS"] > minimo else None
    if passo == "tRFC":
        atual = ns_trfc(p)
        for ns in TRFC_NS:
            clk = math.ceil(ns * p["freq"] / 2000)
            if clk < p["tRFC"] and ns < atual - 1:
                return {"tRFC": clk}
        return None
    if passo == "grupoRRD":
        for s in ({"tRRDS": 5, "tRRDL": 7, "tFAW": 24}, {"tRRDS": 4, "tRRDL": 6, "tFAW": 16}):
            novo = {k: min(v, p[k]) for k, v in s.items()}
            if any(novo[k] < p[k] for k in novo):
                return novo
        return None
    if passo == "grupoWTR":
        novo = {"tWTRS": min(4, p["tWTRS"]), "tWTRL": min(10, p["tWTRL"])}
        return novo if any(novo[k] < p[k] for k in novo) else None
    if passo == "tWR":
        for v in (20, 16, 14, 12, 10):
            if v < p["tWR"]:
                return {"tWR": v, "tRTP": min(p["tRTP"], max(5, v // 2))}
        return None
    raise ValueError(passo)


def proxima_etapa_mem(e: dict):
    """Retorna (passo, perfil_novo) ou (None, None) quando a busca terminou."""
    m, cpu = e["mem"], e["cpu"]["perfil"]
    p = m["estavel"]
    for passo in ORDEM_MEM:
        if passo in m["feitos"]:
            continue
        mud = candidato(passo, p, m, cpu)
        if mud is None:
            m["feitos"].append(passo)
            continue
        return passo, recalcular(dict(p, **mud), cpu["tem_fclk"])
    return None, None


def preparar_mem(e: dict):
    passo, perfil = proxima_etapa_mem(e)
    if passo:
        e["mem"]["teste"] = {"passo": passo, "perfil": perfil, "situacao": "preparada", "desde": agora_iso()}
    return passo


def marcar_aplicada_mem(e: dict):
    t = e["mem"]["teste"]
    t["situacao"] = "aplicada"
    t["desde"] = agora_iso()


def passar_mem(e: dict) -> str:
    m = e["mem"]
    t = m["teste"]
    m["estavel"] = t["perfil"]
    if t["passo"] == "freq":
        m["mais_tensao"] = False
    m["teste"] = None
    p = t["perfil"]
    return (f"PASSOU '{DESCR_ETAPA[t['passo']]}'. Novo estável: {p['freq']} MT/s "
            f"CL{p['tCL']}-{p['tRCDRD']}-{p['tRP']}-{p['tRAS']} tRFC {p['tRFC']} ({ns_trfc(p):.0f} ns).")


def falhar_mem(e: dict, motivo: str) -> str:
    m = e["mem"]
    t = m["teste"]
    passo = t["passo"]
    m["teste"] = None
    if passo == "freq" and not m["mais_tensao"] and t["perfil"]["vdram"] < VDRAM_SEGURA:
        m["mais_tensao"] = True
        return f"FALHOU {t['perfil']['freq']} MT/s: {motivo}. Próxima tentativa com {VDRAM_SEGURA} V."
    m["feitos"].append(passo)
    m["mais_tensao"] = False
    return f"FALHOU '{DESCR_ETAPA[passo]}': {motivo}. Limite encontrado; fica o último estável."


def pular_mem(e: dict) -> str:
    t = e["mem"]["teste"]
    e["mem"]["feitos"].append(t["passo"])
    e["mem"]["teste"] = None
    e["mem"]["mais_tensao"] = False
    return f"Ajuste '{DESCR_ETAPA[t['passo']]}' pulado."


# ---------------------------------------------------------------- processador
def proximo_co(e: dict):
    c = e["cpu"]
    if c["feito"]:
        return None
    prox = [v for v in CO_PASSOS if v < c["estavel"]]
    return prox[0] if prox else None


def preparar_cpu(e: dict):
    v = proximo_co(e)
    if v is not None:
        e["cpu"]["teste"] = {"valor": v, "situacao": "pendente", "desde": agora_iso()}
    return v


def passar_cpu(e: dict) -> str:
    c = e["cpu"]
    v = c["teste"]["valor"]
    c["estavel"] = v
    c["teste"] = None
    return f"PASSOU Curve Optimizer {v}. Novo estável."


def falhar_cpu(e: dict, motivo: str) -> str:
    c = e["cpu"]
    v = c["teste"]["valor"]
    c["teste"] = None
    c["feito"] = True
    return f"FALHOU Curve Optimizer {v}: {motivo}. Voltando para {c['estavel']}."


def valor_co_no_boot(e: dict) -> int:
    c = e["cpu"]
    if not c["perfil"].get("suporta_co"):
        return 0
    return c["teste"]["valor"] if c["teste"] else c["estavel"]


def args_pbo2(modelo: str, valor: int, nucleos: int) -> list[str]:
    """'{c}' = valor de um núcleo; '{todos}' = o valor repetido para cada núcleo."""
    texto = modelo.replace("{todos}", " ".join([str(valor)] * nucleos)).replace("{c}", str(valor))
    return texto.split()
