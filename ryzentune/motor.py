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


# ---------------------------------------------------------------- busca inteligente
# Cada ajuste vira uma lista de valores, do menos para o mais agressivo. A busca começa no alvo
# previsto para o chip (conhecimento.py) e depois divide o intervalo ao meio entre o último que passou
# e o primeiro que falhou. Sem previsão, anda um passo de cada vez.
PISO = {"tCL": 12, "tRCDRD": 12, "tRCDWR": 8, "tRP": 12, "trfc_ns": 200}
GRUPO_RRD = [{"tRRDS": 5, "tRRDL": 7, "tFAW": 24}, {"tRRDS": 4, "tRRDL": 6, "tFAW": 16}]


def lista_valores(passo: str, p: dict, cpu: dict, alvos: dict | None) -> list:
    a = alvos or {}

    def descendo(atual, alvo, piso, passo_=1, piso_generico=14):
        fim = max(piso, (alvo - 2) if alvo else piso_generico)
        return list(range(atual - passo_, fim - 1, -passo_))
    if passo == "freq":
        return [f for f in cpu["freqs"] if f > p["freq"]]
    if passo == "tCL":
        return descendo(p["tCL"], a.get("tCL"), PISO["tCL"], 2 if p["gdm"] else 1)
    if passo == "tRCDRD":
        return descendo(p["tRCDRD"], a.get("tRCDRD"), PISO["tRCDRD"])
    if passo == "tRCDWR":
        return list(range(p["tRCDWR"] - 2, PISO["tRCDWR"] - 1, -2))
    if passo == "tRP":
        return descendo(p["tRP"], a.get("tRP"), PISO["tRP"])
    if passo == "tRAS":
        minimo = max(28, p["tCL"] + p["tRCDRD"])
        vals = list(range(p["tRAS"] - 2, minimo, -2))
        return vals + [minimo] if p["tRAS"] > minimo else []
    if passo == "tRFC":
        atual = ns_trfc(p)
        piso = max(PISO["trfc_ns"], a["trfc_ns"] - 40) if a.get("trfc_ns") else 240
        return [ns for ns in range(int(atual // 10) * 10, piso - 1, -10)
                if ns < atual - 1 and math.ceil(ns * p["freq"] / 2000) < p["tRFC"]]
    if passo == "grupoRRD":
        return [i for i, s in enumerate(GRUPO_RRD) if any(min(v, p[k]) < p[k] for k, v in s.items())]
    if passo == "grupoWTR":
        return [0] if p["tWTRS"] > 4 or p["tWTRL"] > 10 else []
    if passo == "tWR":
        return [v for v in (20, 16, 14, 12, 10) if v < p["tWR"]]
    raise ValueError(passo)


def indice_alvo(passo: str, lista: list, alvos: dict | None) -> int:
    """Índice do valor previsto (o mais agressivo que não passa do alvo). 0 sem previsão."""
    if not alvos or not lista:
        return 0
    chave = {"freq": "freq", "tCL": "tCL", "tRCDRD": "tRCDRD", "tRCDWR": "tRCDWR", "tRP": "tRP",
             "tRAS": "tRAS", "tRFC": "trfc_ns"}.get(passo)
    if chave is None or chave not in alvos:
        return len(lista) - 1 if passo in ("grupoRRD", "grupoWTR") else 0
    alvo = alvos[chave]
    mais_agressivo = (lambda v: v > alvo) if passo == "freq" else (lambda v: v < alvo)
    ok = [i for i, v in enumerate(lista) if not mais_agressivo(v)]
    return ok[-1] if ok else 0


def mudanca(passo: str, valor, p: dict, mem: dict, cpu: dict) -> dict:
    if passo == "freq":
        # mantém os tempos em nanossegundos: mesmos ciclos numa frequência maior seriam mais apertados
        escala = valor / p["freq"]
        mud = {"freq": valor, "tRFC": math.ceil(ns_trfc(p) * valor / 2000)}
        for k in ("tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tCWL", "tWR", "tRTP", "tRRDS", "tRRDL", "tFAW",
                  "tWTRS", "tWTRL"):
            mud[k] = math.ceil(p[k] * escala - 0.05)
        if p["gdm"]:  # com GearDown o tCL/tCWL efetivo é par
            mud["tCL"] += mud["tCL"] % 2
            mud["tCWL"] += mud["tCWL"] % 2
        if mem.get("mais_tensao") and p["vdram"] < VDRAM_SEGURA:
            mud["vdram"] = VDRAM_SEGURA
        if valor >= 3733 and cpu["tem_fclk"] and p["vsoc"] < 1.125:
            mud["vsoc"] = 1.125
        return mud
    if passo == "tCL":
        return {"tCL": valor, "tCWL": min(p["tCWL"], valor)}
    if passo == "tRAS":
        return {"tRAS": max(valor, max(28, p["tCL"] + p["tRCDRD"]))}
    if passo == "tRFC":
        return {"tRFC": math.ceil(valor * p["freq"] / 2000)}
    if passo == "grupoRRD":
        return {k: min(v, p[k]) for k, v in GRUPO_RRD[valor].items()}
    if passo == "grupoWTR":
        return {"tWTRS": min(4, p["tWTRS"]), "tWTRL": min(10, p["tWTRL"])}
    if passo == "tWR":
        return {"tWR": valor, "tRTP": min(p["tRTP"], max(5, valor // 2))}
    return {passo: valor}


def _proximo_indice(b: dict):
    if b.get("repetir") is not None:
        return b["repetir"]
    lo, hi = b["lo"], b["hi"]
    if hi - lo <= 1:
        return None
    if not b["tentativas"]:
        return min(max(b["alvo"], lo + 1), hi - 1)
    if hi == len(b["lista"]):
        return lo + 1               # ainda não falhou: avança com cuidado
    return (lo + hi) // 2           # já falhou: divide o intervalo


def proxima_etapa_mem(e: dict):
    """Retorna (passo, perfil_novo) ou (None, None) quando a busca terminou."""
    m, cpu = e["mem"], e["cpu"]["perfil"]
    p = m["estavel"]
    busca = m.setdefault("busca", {})
    for passo in ORDEM_MEM:
        if passo in m["feitos"]:
            continue
        b = busca.get(passo)
        if b is None:
            lista = lista_valores(passo, p, cpu, m.get("alvos"))
            b = busca[passo] = {"lista": lista, "lo": -1, "hi": len(lista), "tentativas": 0,
                                "alvo": indice_alvo(passo, lista, m.get("alvos")), "repetir": None, "indice": None}
        i = _proximo_indice(b)
        if i is None:
            m["feitos"].append(passo)
            continue
        b["indice"] = i
        valor = b["lista"][i]
        return passo, recalcular(dict(p, **mudanca(passo, valor, p, m, cpu)), cpu["tem_fclk"])
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


def _registrar_tentativa(m: dict, passo: str, passou: bool):
    b = m.get("busca", {}).get(passo)
    if not b or b.get("indice") is None:
        return
    b["tentativas"] += 1
    m["reinicios"] = m.get("reinicios", 0) + 1
    if passou:
        b["lo"] = b["indice"]
    b["repetir"] = None


def passar_mem(e: dict) -> str:
    m = e["mem"]
    t = m["teste"]
    _registrar_tentativa(m, t["passo"], True)
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
    _registrar_tentativa(m, passo, False)
    b = m.get("busca", {}).get(passo)
    if passo == "freq" and not m["mais_tensao"] and t["perfil"]["vdram"] < VDRAM_SEGURA:
        m["mais_tensao"] = True
        if b:
            b["repetir"] = b["indice"]
        return f"FALHOU {t['perfil']['freq']} MT/s: {motivo}. Próxima tentativa com {VDRAM_SEGURA} V."
    if b:
        b["hi"] = b["indice"]
    m["mais_tensao"] = False
    if b and _proximo_indice(b) is not None:
        return (f"FALHOU '{DESCR_ETAPA[passo]}': {motivo}. Volta ao estável; "
                "a próxima tentativa fica no meio do caminho.")
    m["feitos"].append(passo)
    return f"FALHOU '{DESCR_ETAPA[passo]}': {motivo}. Limite encontrado; fica o último estável."


def pular_mem(e: dict) -> str:
    t = e["mem"]["teste"]
    e["mem"]["feitos"].append(t["passo"])
    e["mem"]["teste"] = None
    e["mem"]["mais_tensao"] = False
    return f"Ajuste '{DESCR_ETAPA[t['passo']]}' pulado."


def economia(m: dict) -> dict:
    """Reinícios usados x reinícios que a busca de um em um teria usado até o mesmo resultado."""
    usados = linear = 0
    for b in m.get("busca", {}).values():
        usados += b["tentativas"]
        if b["tentativas"]:
            linear += (b["lo"] + 1) + (1 if b["hi"] < len(b["lista"]) else 0)
    return {"usados": usados, "linear": linear}


def reiniciar_busca(m: dict) -> None:
    m.update(feitos=[], mais_tensao=False, teste=None, busca={})

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


HORAS_OBSERVACAO = 24


def observar_cpu(e: dict) -> str:
    """O teste de núcleos passou: agora o app só observa o uso normal antes de confirmar."""
    t = e["cpu"]["teste"]
    t["situacao"] = "observando"
    t["desde_obs"] = agora_iso()
    return (f"Curve Optimizer {t['valor']} passou no teste de núcleos. Agora é usar o PC normalmente: "
            f"sem travar por {HORAS_OBSERVACAO} h, ele é confirmado sozinho.")


def observacao_completa(e: dict, agora: dt.datetime | None = None) -> bool:
    t = e["cpu"]["teste"]
    if not t or t.get("situacao") != "observando":
        return False
    inicio = dt.datetime.fromisoformat(t["desde_obs"])
    return ((agora or dt.datetime.now()) - inicio).total_seconds() >= HORAS_OBSERVACAO * 3600


def valor_co_no_boot(e: dict) -> int:
    c = e["cpu"]
    if not c["perfil"].get("suporta_co"):
        return 0
    return c["teste"]["valor"] if c["teste"] else c["estavel"]
