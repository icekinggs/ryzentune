"""Base de conhecimento: identifica o chip da memória pelo SPD e prevê até onde ele costuma chegar.

Os alvos são o que a maioria dos pentes de cada chip alcança em Ryzen AM4 com no máximo 1,40 V
(conhecimento da comunidade de overclock, o mesmo que alimentava o "DRAM Calculator for Ryzen").
São palpites para começar a busca no lugar certo: o teste é sempre quem decide.
"""
from __future__ import annotations

# alvo a 1,35-1,40 V, dois pentes de um rank. tRFC em nanossegundos.
CHIPS = {
    "samsung_b": {"nome": "Samsung B-die", "freq": 3800, "tCL": 14, "tRCDRD": 15, "tRCDWR": 8, "tRP": 15,
                  "tRAS": 30, "trfc_ns": 260, "nota": "O melhor chip DDR4: timings bem apertados."},
    "samsung_8_outro": {"nome": "Samsung 8 Gb (C-die ou D-die)", "freq": 3600, "tCL": 18, "tRCDRD": 20,
                        "tRCDWR": 12, "tRP": 20, "tRAS": 38, "trfc_ns": 350,
                        "nota": "Chips mais modestos: costumam travar com tCL baixo."},
    "samsung_16": {"nome": "Samsung 16 Gb (M-die ou A-die)", "freq": 3600, "tCL": 16, "tRCDRD": 20,
                   "tRCDWR": 12, "tRP": 20, "tRAS": 36, "trfc_ns": 350, "nota": ""},
    "hynix_8": {"nome": "SK Hynix 8 Gb (CJR ou DJR)", "freq": 3600, "tCL": 16, "tRCDRD": 19, "tRCDWR": 12,
                "tRP": 19, "tRAS": 36, "trfc_ns": 320,
                "nota": "O DJR costuma ir além do previsto; o CJR fica perto."},
    "hynix_16": {"nome": "SK Hynix 16 Gb (MJR, CJR ou DJR)", "freq": 3600, "tCL": 16, "tRCDRD": 20,
                 "tRCDWR": 12, "tRP": 20, "tRAS": 36, "trfc_ns": 350, "nota": ""},
    "micron_8": {"nome": "Micron 8 Gb (provável Rev.E)", "freq": 3800, "tCL": 16, "tRCDRD": 19, "tRCDWR": 12,
                 "tRP": 19, "tRAS": 36, "trfc_ns": 300,
                 "nota": "Gosta de frequência alta; o tRFC não desce muito."},
    "micron_16": {"nome": "Micron 16 Gb (provável Rev.B)", "freq": 3800, "tCL": 16, "tRCDRD": 19,
                  "tRCDWR": 12, "tRP": 19, "tRAS": 36, "trfc_ns": 330, "nota": ""},
    "nanya": {"nome": "Nanya", "freq": 3600, "tCL": 18, "tRCDRD": 21, "tRCDWR": 14, "tRP": 21, "tRAS": 40,
              "trfc_ns": 350, "nota": ""},
    "cxmt": {"nome": "CXMT (ChangXin)", "freq": 3600, "tCL": 18, "tRCDRD": 22, "tRCDWR": 14, "tRP": 22,
             "tRAS": 40, "trfc_ns": 380, "nota": "Chip comum em módulos de marcas chinesas; varia bastante."},
    "generico": {"nome": "Chip não identificado", "freq": 3600, "tCL": 18, "tRCDRD": 21, "tRCDWR": 14,
                 "tRP": 21, "tRAS": 40, "trfc_ns": 380,
                 "nota": "Sem o fabricante dos chips, a previsão é conservadora."},
}
OPCOES = [(k, v["nome"]) for k, v in CHIPS.items()]


def identificar(spds: list[dict]) -> dict:
    """spds = SPDs decodificados. Devolve {"chip", "nome", "confianca", "motivo"}."""
    if not spds:
        return {"chip": "generico", "nome": CHIPS["generico"]["nome"], "confianca": "baixa",
                "motivo": "Não consegui ler o SPD dos pentes."}
    s = spds[0]
    fab, dens = s.get("fabricante_dram", ""), s.get("densidade_gbit")
    misturados = len({(x.get("fabricante_dram"), x.get("densidade_gbit"), x.get("modelo")) for x in spds}) > 1
    xmp = s.get("xmp") or {}
    latencia = xmp["cl"] * 2000 / xmp["mts"] if xmp.get("cl") else None

    def r(chip, conf, motivo):
        if misturados:
            conf, motivo = "baixa", motivo + " Atenção: os pentes não são iguais, então o pior deles manda."
        return {"chip": chip, "nome": CHIPS[chip]["nome"], "confianca": conf, "motivo": motivo}

    base = f"Chips {fab} de {dens:g} Gb" if dens else f"Chips {fab}"
    if fab == "Samsung" and dens == 8:
        if latencia and latencia <= 9.0 and s.get("largura") == 8:
            return r("samsung_b", "alta", f"{base}, x8, com XMP {xmp['mts']} CL{xmp['cl']}: só o B-die vem assim.")
        return r("samsung_8_outro", "média", f"{base}, mas o XMP não é de B-die.")
    if fab == "Samsung" and dens == 16:
        return r("samsung_16", "média", base + ".")
    if fab == "SK Hynix" and dens == 8:
        return r("hynix_8", "média", base + ". O SPD não diferencia o CJR do DJR.")
    if fab == "SK Hynix" and dens == 16:
        return r("hynix_16", "média", base + ".")
    if fab == "Micron" and dens == 8:
        return r("micron_8", "média", base + ". Quase todos os Micron 8 Gb atuais são Rev.E.")
    if fab == "Micron" and dens == 16:
        return r("micron_16", "média", base + ".")
    if fab == "Nanya":
        return r("nanya", "média", base + ".")
    if fab == "CXMT":
        return r("cxmt", "média", base + ".")
    return r("generico", "baixa", f"O fabricante dos chips não foi reconhecido ({fab}).")


def alvos(chip: str, cpu: dict, ranks_total: int, pentes: int) -> dict:
    """Alvos ajustados ao processador e à configuração de pentes."""
    a = dict(CHIPS.get(chip, CHIPS["generico"]))
    freqs = cpu.get("freqs") or [3466, 3600]
    freq = a["freq"]
    if cpu.get("apu") and chip in ("samsung_b", "micron_8", "micron_16", "hynix_8"):
        freq = 4000  # APUs seguram FCLK alto
    if ranks_total > 2 or pentes > 2:
        freq = min(freq, 3600)  # mais ranks = mais carga no controlador
        a["tRCDRD"] += 1
        a["tRP"] += 1
    freq = max([f for f in freqs if f <= freq] or [freqs[0]])
    a["freq"] = freq
    return a
