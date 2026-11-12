import pytest

from ryzentune import conhecimento, estado, hardware, motor, spd

CPU = hardware.classificar_cpu("AMD Ryzen 7 5700X3D 8-Core Processor", 8).to_dict()


def novo(alvos=None, **base):
    e = estado.novo()
    e["cpu"]["perfil"] = dict(CPU)
    e["mem"]["confirmado"] = True
    e["mem"]["estavel"].update(base)
    e["mem"]["alvos"] = alvos
    return e


def rodar(e, limite_ok):
    """Simula a busca: limite_ok(passo, perfil) diz se a memória aguenta. Devolve a lista de tentativas."""
    tentativas = []
    for _ in range(300):
        passo = motor.preparar_mem(e)
        if not passo:
            return tentativas
        p = e["mem"]["teste"]["perfil"]
        assert motor.validar_perfil(p) == [], p
        ok = limite_ok(passo, p)
        tentativas.append((passo, ok))
        motor.passar_mem(e) if ok else motor.falhar_mem(e, "x")
    raise AssertionError("não terminou")


# ------------------------------------------------------------ busca binária
def test_primeira_tentativa_e_o_alvo():
    alvos = conhecimento.alvos("hynix_8", CPU, 2, 2)
    e = novo(alvos, freq=3600, fclk=1800, tCL=16, tRCDRD=22, tRP=22, tRAS=40, tRC=62, tRFC=630)
    e["mem"]["feitos"] = ["freq", "tCL"]
    motor.preparar_mem(e)
    t = e["mem"]["teste"]
    assert t["passo"] == "tRCDRD" and t["perfil"]["tRCDRD"] == alvos["tRCDRD"] == 19


def test_busca_binaria_acha_o_limite_real_com_menos_reinicios():
    """Memória que aguenta tRCDRD 17 (melhor que a previsão 19). Começando em 26."""
    alvos = conhecimento.alvos("hynix_8", CPU, 2, 2)
    e = novo(alvos, freq=3600, fclk=1800, tCL=16, tRCDRD=26, tRP=26, tRAS=44, tRC=70, tRFC=630)
    e["mem"]["feitos"] = [p for p in motor.ORDEM_MEM if p != "tRCDRD"]
    tent = rodar(e, lambda passo, p: p["tRCDRD"] >= 17)
    assert e["mem"]["estavel"]["tRCDRD"] == 17
    assert len(tent) <= 4  # 19 ok, 18 ok, 17 ok, (piso 17) — de um em um seriam 9
    eco = motor.economia(e["mem"])
    assert eco["usados"] < eco["linear"]


def test_busca_binaria_quando_o_alvo_falha():
    """Memória que só aguenta tRCDRD 23; previsão 19 é otimista demais."""
    alvos = conhecimento.alvos("hynix_8", CPU, 2, 2)
    e = novo(alvos, freq=3600, fclk=1800, tCL=16, tRCDRD=26, tRP=26, tRAS=44, tRC=70, tRFC=630)
    e["mem"]["feitos"] = [p for p in motor.ORDEM_MEM if p != "tRCDRD"]
    tent = rodar(e, lambda passo, p: p["tRCDRD"] >= 23)
    assert e["mem"]["estavel"]["tRCDRD"] == 23
    valores = []
    # 19 falha -> meio entre 26 e 19 -> ... sempre converge
    assert len(tent) <= 4, (tent, valores)


@pytest.mark.parametrize("limite", range(14, 27))
def test_busca_sempre_converge_no_limite(limite):
    alvos = conhecimento.alvos("hynix_8", CPU, 2, 2)
    e = novo(alvos, freq=3600, fclk=1800, tCL=16, tRCDRD=26, tRP=26, tRAS=44, tRC=70, tRFC=630)
    e["mem"]["feitos"] = [p for p in motor.ORDEM_MEM if p != "tRCDRD"]
    rodar(e, lambda passo, p: p["tRCDRD"] >= limite)
    piso = alvos["tRCDRD"] - 2
    assert e["mem"]["estavel"]["tRCDRD"] == max(limite, piso)


def test_frequencia_pula_direto_para_o_alvo_e_tenta_tensao():
    alvos = conhecimento.alvos("micron_8", CPU, 2, 2)  # alvo 3800
    e = novo(alvos)
    motor.preparar_mem(e)
    assert e["mem"]["teste"]["perfil"]["freq"] == 3800
    motor.falhar_mem(e, "x")                          # 3800 @1,35 falha -> repete com 1,40 V
    motor.preparar_mem(e)
    p = e["mem"]["teste"]["perfil"]
    assert p["freq"] == 3800 and p["vdram"] == 1.40
    motor.falhar_mem(e, "x")                          # falhou de novo -> meio do caminho
    motor.preparar_mem(e)
    assert e["mem"]["teste"]["perfil"]["freq"] in (3600, 3733)


def test_trfc_vai_ao_alvo_em_ns():
    alvos = conhecimento.alvos("micron_8", CPU, 2, 2)  # 300 ns
    e = novo(alvos, freq=3600, fclk=1800, tRFC=630)    # 350 ns
    e["mem"]["feitos"] = [p for p in motor.ORDEM_MEM if p != "tRFC"]
    motor.preparar_mem(e)
    assert round(motor.ns_trfc(e["mem"]["teste"]["perfil"])) == 300


def test_sem_alvos_anda_de_um_em_um():
    e = novo(None)
    e["mem"]["feitos"] = [p for p in motor.ORDEM_MEM if p != "tRCDRD"]
    motor.preparar_mem(e)
    assert e["mem"]["teste"]["perfil"]["tRCDRD"] == 17


def test_reiniciar_busca_limpa_tudo():
    e = novo(conhecimento.alvos("hynix_8", CPU, 2, 2))
    motor.preparar_mem(e)
    motor.passar_mem(e)
    motor.reiniciar_busca(e["mem"])
    assert e["mem"]["busca"] == {} and e["mem"]["feitos"] == [] and e["mem"]["teste"] is None


def _pente_real(passo, p):
    """Pente simulado com limites em nanossegundos (como a memória de verdade)."""
    def ns(k):
        return p[k] * 2000 / p["freq"]
    return (p["freq"] <= 3733 and ns("tCL") >= 8.5 and ns("tRCDRD") >= 10.2 and ns("tRP") >= 9.8
            and p["tRCDWR"] >= 10 and motor.ns_trfc(p) >= 309)


def test_busca_completa_acha_o_otimo_e_economiza_reinicios():
    resultados = {}
    for nome, alvos in (("previsao", conhecimento.alvos("hynix_8", CPU, 2, 2)), ("linear", None)):
        e = novo(alvos)
        resultados[nome] = (len(rodar(e, _pente_real)), dict(e["mem"]["estavel"]))
    (n_prev, p), (n_lin, p_lin) = resultados["previsao"], resultados["linear"]
    # ótimo real: 3733 MT/s, CL16 (8,57 ns), tRCDRD 20 (10,7 ns), tRP 19 (10,2 ns), tRFC 310 ns
    assert (p["freq"], p["tCL"], p["tRCDRD"], p["tRP"], p["tRCDWR"]) == (3733, 16, 20, 19, 10)
    assert round(motor.ns_trfc(p)) == 310
    assert p == p_lin                 # a previsão não muda o resultado, só o caminho
    assert n_prev < n_lin * 0.75      # e economiza reinícios


def test_subir_frequencia_mantem_os_nanossegundos():
    e = novo(None)
    motor.preparar_mem(e)
    p0, p1 = e["mem"]["estavel"], e["mem"]["teste"]["perfil"]
    for k in ("tRCDRD", "tRP", "tRAS"):
        assert p1[k] * 2000 / p1["freq"] >= p0[k] * 2000 / p0["freq"] - 0.05, k
    assert p1["tCL"] % 2 == 0  # GearDown ligado


# ------------------------------------------------------------ conhecimento
def pente(fab, dens, largura=8, ranks=1, xmp=None, modelo="X"):
    d = {"fabricante_dram": fab, "densidade_gbit": dens, "largura": largura, "ranks": ranks, "modelo": modelo}
    if xmp:
        d["xmp"] = xmp
    return d


@pytest.mark.parametrize("p,chip,conf", [
    (pente("Samsung", 8, xmp={"mts": 3200, "cl": 14}), "samsung_b", "alta"),
    (pente("Samsung", 8, xmp={"mts": 3600, "cl": 16}), "samsung_b", "alta"),
    (pente("Samsung", 8, xmp={"mts": 3200, "cl": 16}), "samsung_8_outro", "média"),
    (pente("Samsung", 16), "samsung_16", "média"),
    (pente("SK Hynix", 8), "hynix_8", "média"),
    (pente("SK Hynix", 16), "hynix_16", "média"),
    (pente("Micron", 8), "micron_8", "média"),
    (pente("Micron", 16), "micron_16", "média"),
    (pente("CXMT", 16), "cxmt", "média"),
    (pente("desconhecido (7F 7F)", 8), "generico", "baixa"),
])
def test_identificar(p, chip, conf):
    r = conhecimento.identificar([p, dict(p)])
    assert (r["chip"], r["confianca"]) == (chip, conf)


def test_identificar_sem_spd_e_pentes_misturados():
    assert conhecimento.identificar([])["chip"] == "generico"
    r = conhecimento.identificar([pente("SK Hynix", 8), pente("Micron", 8)])
    assert r["confianca"] == "baixa" and "não são iguais" in r["motivo"]


def test_alvos_respeitam_processador_e_ranks():
    zen_plus = hardware.classificar_cpu("AMD Ryzen 5 2600 Six-Core Processor", 6).to_dict()
    assert conhecimento.alvos("samsung_b", zen_plus, 2, 2)["freq"] <= 3600
    assert conhecimento.alvos("samsung_b", CPU, 4, 4)["freq"] == 3600
    apu = hardware.classificar_cpu("AMD Ryzen 5 5600G with Radeon Graphics", 6).to_dict()
    assert conhecimento.alvos("samsung_b", apu, 2, 2)["freq"] == 4000


def test_todos_os_alvos_geram_perfis_validos():
    for chave in conhecimento.CHIPS:
        a = conhecimento.alvos(chave, CPU, 2, 2)
        p = motor.recalcular(dict(motor.PADRAO_MEM, freq=a["freq"], tCL=a["tCL"], tRCDRD=a["tRCDRD"],
                                  tRCDWR=a["tRCDWR"], tRP=a["tRP"], tRAS=a["tRAS"],
                                  tRFC=round(a["trfc_ns"] * a["freq"] / 2000)), True)
        assert motor.validar_perfil(p) == [], chave


# ------------------------------------------------------------ SPD
def spd_ddr4(fab=(0x80, 0xAD), dens=5, org=0x01, xmp=True):
    s = bytearray(512)
    s[2] = 0x0C
    s[4] = dens
    s[12] = org          # x8, 1 rank
    s[13] = 0x03         # 64 bits
    s[18] = 0x05         # tCK 625 ps (3200)
    s[24] = 0x6E         # tAA 13,75 ns
    s[125] = 0x00
    s[123] = 0x00
    s[320:322] = bytes([0x80, 0xAD])
    s[329:349] = b"HKED4161CAB2F2HB4   "
    s[350:352] = bytes(fab)
    if xmp:
        s[384], s[385] = 0x0C, 0x4A
        p = 393
        s[p] = 0x80 | 35   # 1,35 V
        s[p + 3] = 0x04    # tCK 500 ps (4000)? -> com FTB +55 = 555 ps (3600)
        s[p + 38] = 55
        s[p + 8] = 0x47    # tAA 8,875 ns
        s[p + 37] = 0
        s[p + 9] = 0x55
        s[p + 10] = 0x55
    return bytes(s)


def test_decodificar_spd():
    d = spd.decodificar(spd_ddr4())
    assert d["fabricante_dram"] == "SK Hynix" and d["densidade_gbit"] == 8
    assert d["largura"] == 8 and d["ranks"] == 1 and d["tamanho_gb"] == 8
    assert d["modelo"] == "HKED4161CAB2F2HB4"
    assert d["jedec_mts"] == 3200 and d["jedec_cl"] == 22
    assert d["xmp"]["mts"] == 3604 or d["xmp"]["mts"] == 3600
    assert d["xmp"]["tensao"] == 1.35


def test_spd_nao_ddr4():
    with pytest.raises(ValueError):
        spd.decodificar(bytes(512))


def test_xmp_absurdo_e_ignorado():
    s = bytearray(spd_ddr4())
    s[393 + 3] = 0xFF
    assert "xmp" not in spd.decodificar(bytes(s))


class BarramentoFalso:
    def __init__(self, conteudo):
        self.conteudo = conteudo   # {endereco: bytes512}
        self.pagina = 0
        self.escritas = []

    def xfer(self, addr, rw, cmd, proto, dados):
        if rw == 0:
            self.escritas.append(addr)
            if addr == 0x36:
                self.pagina = 0
            elif addr == 0x37:
                self.pagina = 1
            return [0]
        if addr not in self.conteudo:
            raise OSError("sem resposta")
        return [self.conteudo[addr][self.pagina * 256 + cmd]]


def test_leitor_le_as_duas_paginas_e_volta_para_a_zero():
    s = spd_ddr4()
    bus = BarramentoFalso({0x50: s, 0x52: s})
    r = spd.LeitorSPD(bus.xfer).ler_todos()
    assert set(r) == {0, 2} and r[0] == s
    assert bus.pagina == 0
    assert set(bus.escritas) <= {0x36, 0x37}   # NUNCA escreve na EEPROM


def test_leitor_recusa_escrita_fora_da_pagina():
    leitor = spd.LeitorSPD(lambda *a: [0])
    with pytest.raises(spd.EscritaProibida):
        leitor._ler_byte(0x18, 0)
    original = spd.PAGINA[0]
    try:
        spd.PAGINA[0] = 0x50  # simula um bug que tentaria escrever na EEPROM
        with pytest.raises(spd.EscritaProibida):
            leitor._escrever_pagina(0)
    finally:
        spd.PAGINA[0] = original
