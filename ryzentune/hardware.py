"""Identifica processador, placa-mãe e memória e define os limites de cada geração.

As funções de classificação são puras (testáveis); a leitura do WMI fica em sistema.py.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class PerfilCPU:
    nome: str
    geracao: str            # "zen1", "zen+", "zen2", "zen3", "desconhecida"
    nucleos: int
    x3d: bool
    apu: bool
    suporta_co: bool        # Curve Optimizer só existe em Zen 3
    tem_fclk: bool          # Zen 2/3 têm FCLK separado (1:1 com a memória)
    freqs: list[int] = field(default_factory=list)  # degraus de frequência da memória
    am4: bool = True

    def to_dict(self):
        return asdict(self)


FREQS = {
    "zen1": [2933, 3066, 3200, 3333],
    "zen+": [3200, 3333, 3466, 3600],
    "zen2": [3466, 3600, 3733, 3800],
    "zen3": [3466, 3600, 3733, 3800],
    "zen3apu": [3600, 3800, 4000, 4133],
    "desconhecida": [3466, 3600],
}


def classificar_cpu(nome: str, nucleos: int) -> PerfilCPU:
    n = (nome or "").strip()
    m = re.search(r"Ryzen\s+(?:Threadripper\s+)?\d\s+(?:PRO\s+)?(\d)(\d)\d\d([A-Z0-9]*)", n, re.I)
    if not m or "AMD" not in n.upper():
        return PerfilCPU(n, "desconhecida", nucleos, False, False, False, False,
                         FREQS["desconhecida"], am4=False)
    serie = int(m.group(1))
    sufixo = m.group(3).upper()
    x3d = "X3D" in sufixo
    apu = sufixo.startswith("G")
    am4 = "THREADRIPPER" not in n.upper() and serie <= 5
    # 3000G/3400G (Picasso) são Zen+; 4000G (Renoir) e 5000G (Cezanne) seguem a série
    if serie == 1:
        ger = "zen1"
    elif serie == 2 or (serie == 3 and apu):
        ger = "zen+"
    elif serie in (3, 4):
        ger = "zen2"
    elif serie == 5:
        ger = "zen3"
    else:
        ger = "desconhecida"
        am4 = False
    # 5500/5600G/5700G/5600GT e afins são APU Cezanne: FCLK vai mais alto
    chave = "zen3apu" if ger == "zen3" and apu else ger
    if ger == "zen2" and serie == 4 and apu:
        chave = "zen3apu"  # Renoir também segura FCLK alto
    return PerfilCPU(
        nome=n, geracao=ger, nucleos=max(1, int(nucleos or 1)), x3d=x3d, apu=apu,
        suporta_co=(ger == "zen3"), tem_fclk=ger in ("zen2", "zen3"),
        freqs=list(FREQS[chave]), am4=am4)


def fabricante_placa(texto: str) -> str:
    t = (texto or "").upper()
    for chave, nome in (("MICRO-STAR", "MSI"), ("MSI", "MSI"), ("ASUSTEK", "ASUS"), ("ASUS", "ASUS"),
                        ("GIGABYTE", "Gigabyte"), ("ASROCK", "ASRock"), ("BIOSTAR", "Biostar")):
        if chave in t:
            return nome
    return "Outra"


# Onde ficam os ajustes de memória na BIOS de cada marca
CAMINHO_BIOS = {
    "MSI": ("F7 (modo avançado) → OC. Frequência e tensões na própria tela; timings em "
            "'Advanced DRAM Configuration'. Deixe 'Memory Try It!' em Disabled. Salve com F10.",
            "Se não ligar, a placa tenta 3 vezes e volta sozinha ao padrão. Senão, limpe o CMOS."),
    "ASUS": ("F7 (Advanced Mode) → Ai Tweaker. Timings em 'DRAM Timing Control'. Salve com F10.",
             "Se não ligar, a placa costuma voltar ao padrão sozinha (mensagem 'Overclocking failed'). "
             "Senão, limpe o CMOS."),
    "Gigabyte": ("Tweaker (ou M.I.T.) → Advanced Memory Settings → Memory Sub-timings. Salve com F10.",
                 "Se não ligar, a placa volta ao padrão após algumas tentativas. Senão, limpe o CMOS."),
    "ASRock": ("OC Tweaker → DRAM Configuration. Tensões em 'Voltage Configuration'. Salve com F10.",
               "Se não ligar, desligue da tomada e limpe o CMOS (jumper CLRMOS)."),
    "Biostar": ("O.N.E. → Memory/DRAM Timing. Salve com F10.",
                "Se não ligar, limpe o CMOS."),
    "Outra": ("Procure a seção de overclock/memória (nomes variam). Salve com F10.",
              "Se não ligar, limpe o CMOS (veja o manual da placa)."),
}
