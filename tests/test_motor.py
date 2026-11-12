import copy

from ryzentune import estado, hardware, motor


def rodar_busca(e, falha):
    """Simula a busca inteira; falha(passo, perfil) decide se a etapa falha."""
    passos = []
    for _ in range(200):
        passo = motor.preparar_mem(e)
        if not passo:
            return passos
        perfil = e["mem"]["teste"]["perfil"]
        assert motor.validar_perfil(perfil) == [], perfil
        if falha(passo, perfil):
            motor.falhar_mem(e, "teste")
            passos.append((passo, "falha"))
        else:
            motor.passar_mem(e)
            passos.append((passo, "ok"))
    raise AssertionError("a busca não terminou")


def test_padrao_valido():
    assert motor.validar_perfil(motor.PADRAO_MEM) == []


def test_busca_termina_tudo_passando(e_5700x3d):
    rodar_busca(e_5700x3d, lambda p, f: False)
    est = e_5700x3d["mem"]["estavel"]
    assert est["freq"] == 3800 and est["fclk"] == 1900
    assert est["tRC"] == est["tRP"] + est["tRAS"]
    assert est["vdram"] <= motor.VDRAM_SEGURA and est["vsoc"] <= motor.VSOC_MAX
    assert set(e_5700x3d["mem"]["feitos"]) == set(motor.ORDEM_MEM)


def test_busca_termina_tudo_falhando(e_5700x3d):
    inicial = copy.deepcopy(e_5700x3d["mem"]["estavel"])
    passos = rodar_busca(e_5700x3d, lambda p, f: True)
    assert e_5700x3d["mem"]["estavel"] == inicial
    # a frequência tenta 2x (1,35 V e depois 1,40 V); os demais, 1x
    assert [p for p, _ in passos].count("freq") == 2


def test_frequencia_tenta_com_mais_tensao(e_5700x3d):
    e = e_5700x3d
    motor.preparar_mem(e)
    assert e["mem"]["teste"]["perfil"]["vdram"] == 1.35
    motor.falhar_mem(e, "x")
    motor.preparar_mem(e)
    t = e["mem"]["teste"]
    assert t["passo"] == "freq" and t["perfil"]["freq"] == 3466 and t["perfil"]["vdram"] == 1.40
    motor.passar_mem(e)
    assert e["mem"]["mais_tensao"] is False
    motor.preparar_mem(e)
    assert e["mem"]["teste"]["perfil"]["freq"] == 3600


def test_trfc_mantem_ns_ao_subir_frequencia(e_5700x3d):
    motor.preparar_mem(e_5700x3d)
    p = e_5700x3d["mem"]["teste"]["perfil"]
    assert abs(motor.ns_trfc(p) - 350) < 1


def test_zen_plus_sem_fclk():
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu("AMD Ryzen 5 2600 Six-Core Processor", 6).to_dict()
    e["mem"]["estavel"]["fclk"] = 0
    rodar_busca(e, lambda p, f: False)
    assert e["mem"]["estavel"]["fclk"] == 0 and e["mem"]["estavel"]["freq"] == 3600


def test_tras_respeita_minimo(e_5700x3d):
    rodar_busca(e_5700x3d, lambda p, f: False)
    est = e_5700x3d["mem"]["estavel"]
    assert est["tRAS"] >= max(28, est["tCL"] + est["tRCDRD"])


def test_validar_perfil_rejeita_absurdos():
    erros = motor.validar_perfil(dict(motor.PADRAO_MEM, vdram=1.6, tCL=5))
    assert any("DRAM Voltage" in x for x in erros) and any("tCL" in x for x in erros)
    p = dict(motor.PADRAO_MEM)
    del p["tRFC"]
    assert motor.validar_perfil(p)


def test_pular(e_5700x3d):
    motor.preparar_mem(e_5700x3d)
    motor.pular_mem(e_5700x3d)
    assert "freq" in e_5700x3d["mem"]["feitos"]
    assert motor.preparar_mem(e_5700x3d) == "tCL"


def test_co_busca(e_5700x3d):
    e = e_5700x3d
    vals = []
    while (v := motor.preparar_cpu(e)) is not None:
        vals.append(v)
        if v == -20:
            motor.falhar_cpu(e, "x")
        else:
            motor.passar_cpu(e)
    assert vals == [-5, -10, -15, -20] and e["cpu"]["estavel"] == -15
    assert motor.valor_co_no_boot(e) == -15


def test_co_nao_aplica_sem_suporte():
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu("AMD Ryzen 7 3700X", 8).to_dict()
    e["cpu"]["estavel"] = -20
    assert motor.valor_co_no_boot(e) == 0
