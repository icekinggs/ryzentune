import logging

from ryzentune import boot, estado, hardware, motor

NOME = "AMD Ryzen 7 5700X3D 8-Core Processor"


def timings_de(perfil, **mud):
    t = {k: perfil[k] for k in ("gdm", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRC", "tRFC", "tRRDS", "tRRDL",
                                "tFAW", "tWTRS", "tWTRL", "tWR", "tRTP", "tCWL")}
    t["mts_ratio"] = perfil["freq"]
    t.update(mud)
    return t


class IOFalso:
    log = logging.getLogger("teste")

    def __init__(self, timings=None, vel=0, eventos=(0, 0), cpu=NOME, co_ok=True):
        self.t, self.vel, self.ev, self.cpu, self.co_ok, self.co = timings, vel, eventos, cpu, co_ok, []

    def ler_timings(self):
        return self.t

    def velocidade_ram(self):
        return self.vel

    def eventos_desde(self, iso):
        return self.ev

    def nome_cpu(self):
        return self.cpu

    def aplicar_co(self, valor):
        self.co.append(valor)
        return self.co_ok


def preparar(mem=False, co=None, co_sit="pendente", estavel_co=0):
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu(NOME, 8).to_dict()
    e["cpu"]["estavel"] = estavel_co
    e["mem"]["confirmado"] = True
    if mem:
        motor.preparar_mem(e)          # etapa de frequência: 3200 -> 3466
        motor.marcar_aplicada_mem(e)
    if co:
        e["cpu"]["teste"] = {"valor": co, "situacao": co_sit, "desde": motor.agora_iso()}
    estado.salvar(e)
    return e


def perfil_teste():
    return estado.carregar()["mem"]["teste"]["perfil"]


def test_memoria_aplicada_certinho_vai_para_teste():
    preparar(mem=True)
    boot.rotina(IOFalso(timings=timings_de(perfil_teste())))
    assert estado.carregar()["mem"]["teste"]["situacao"] == "testar"


def test_memoria_bios_restaurou_padrao():
    preparar(mem=True)
    boot.rotina(IOFalso(timings=timings_de(motor.PADRAO_MEM)))
    e = estado.carregar()
    assert e["mem"]["teste"] is None and e["mem"]["mais_tensao"] is True


def test_memoria_bios_aplicou_parcialmente():
    preparar(mem=True)
    p = perfil_teste()
    boot.rotina(IOFalso(timings=timings_de(p, tRFC=p["tRFC"] + 20)))
    t = estado.carregar()["mem"]["teste"]
    assert t["situacao"] == "divergente" and [d["campo"] for d in t["diferencas"]] == ["tRFC"]


def test_memoria_travou():
    preparar(mem=True)
    boot.rotina(IOFalso(timings=timings_de(perfil_teste()), eventos=(1, 0)))
    assert estado.carregar()["mem"]["teste"] is None


def test_memoria_sem_leitura_usa_velocidade():
    preparar(mem=True)
    boot.rotina(IOFalso(timings=None, vel=3200))
    assert estado.carregar()["mem"]["teste"] is None  # 3200 != 3466: falhou
    preparar(mem=True)
    boot.rotina(IOFalso(timings=None, vel=3466))
    assert estado.carregar()["mem"]["teste"]["situacao"] == "testar"


def test_eventos_ilegiveis_nao_reprovam():
    preparar(co=-10, co_sit="ativo")
    assert boot.rotina(IOFalso(eventos=(-1, -1))) == -10


def test_co_pendente_ativa_e_aplica():
    preparar(co=-10)
    io = IOFalso()
    assert boot.rotina(io) == -10 and io.co == [-10]
    assert estado.carregar()["cpu"]["teste"]["situacao"] == "ativo"


def test_co_travou_volta_ao_estavel():
    preparar(co=-20, co_sit="ativo", estavel_co=-15)
    io = IOFalso(eventos=(1, 0))
    assert boot.rotina(io) == -15 and io.co == [-15]
    e = estado.carregar()
    assert e["cpu"]["teste"] is None and e["cpu"]["feito"] is True


def test_whea_reprova_co():
    preparar(co=-20, co_sit="ativo", estavel_co=0)
    io = IOFalso(eventos=(0, 3))
    assert boot.rotina(io) is None and io.co == []


def test_falha_ao_aplicar_fica_registrada():
    preparar(co=-10)
    assert boot.rotina(IOFalso(co_ok=False)) is None
    assert "Não consegui aplicar" in estado.carregar()["historico"][-1]["texto"]


def test_processador_trocado_zera():
    preparar(co=-10, co_sit="ativo", estavel_co=-10)
    io = IOFalso(cpu="AMD Ryzen 7 5800X3D 8-Core Processor")
    assert boot.rotina(io) is None and io.co == []
    e = estado.carregar()
    assert e["cpu"]["estavel"] == 0 and e["cpu"]["perfil"] == {}


def test_sem_nada_pendente_nao_faz_nada():
    preparar()
    io = IOFalso()
    assert boot.rotina(io) is None and io.co == []
