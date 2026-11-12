import logging

from ryzentune import boot, estado, hardware, motor

NOME = "AMD Ryzen 7 5700X3D 8-Core Processor"


class IOFalso:
    log = logging.getLogger("teste")

    def __init__(self, vel=3600, eventos=(0, 0), cpu=NOME):
        self.vel, self.ev, self.cpu, self.pbo = vel, eventos, cpu, []

    def velocidade_ram(self):
        return self.vel

    def eventos_desde(self, iso):
        return self.ev

    def nome_cpu(self):
        return self.cpu

    def rodar_pbo2(self, exe, args):
        self.pbo.append(args)
        return True


def preparar(mem_freq=None, co=None, co_sit="pendente", estavel_co=0):
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu(NOME, 8).to_dict()
    e["cpu"]["pbo2"] = "x.exe"
    e["cpu"]["estavel"] = estavel_co
    e["mem"]["confirmado"] = True
    if mem_freq:
        motor.preparar_mem(e)
        e["mem"]["teste"]["perfil"]["freq"] = mem_freq
        motor.marcar_aplicada_mem(e)
    if co:
        e["cpu"]["teste"] = {"valor": co, "situacao": co_sit, "desde": motor.agora_iso()}
    estado.salvar(e)


def test_memoria_ok_vai_para_teste():
    preparar(mem_freq=3466)
    boot.rotina(IOFalso(vel=3466))
    assert estado.carregar()["mem"]["teste"]["situacao"] == "testar"


def test_memoria_tolerancia_de_arredondamento():
    preparar(mem_freq=3466)
    boot.rotina(IOFalso(vel=3467))
    assert estado.carregar()["mem"]["teste"]["situacao"] == "testar"


def test_memoria_bios_restaurou():
    preparar(mem_freq=3466)
    boot.rotina(IOFalso(vel=3200))
    e = estado.carregar()
    assert e["mem"]["teste"] is None and e["mem"]["mais_tensao"] is True


def test_memoria_travou():
    preparar(mem_freq=3466)
    boot.rotina(IOFalso(vel=3466, eventos=(1, 0)))
    assert estado.carregar()["mem"]["teste"] is None


def test_memoria_velocidade_ilegivel_nao_reprova():
    preparar(mem_freq=3466)
    boot.rotina(IOFalso(vel=0))
    assert estado.carregar()["mem"]["teste"]["situacao"] == "testar"


def test_eventos_ilegiveis_nao_reprovam():
    preparar(co=-10, co_sit="ativo")
    assert boot.rotina(IOFalso(eventos=(-1, -1))) == -10


def test_co_pendente_ativa_e_aplica():
    preparar(co=-10)
    io = IOFalso()
    assert boot.rotina(io) == -10
    assert io.pbo == [["-10"] * 8]
    assert estado.carregar()["cpu"]["teste"]["situacao"] == "ativo"


def test_co_travou_volta_ao_estavel():
    preparar(co=-20, co_sit="ativo", estavel_co=-15)
    io = IOFalso(eventos=(1, 0))
    assert boot.rotina(io) == -15
    e = estado.carregar()
    assert e["cpu"]["teste"] is None and e["cpu"]["feito"] is True


def test_whea_reprova_co():
    preparar(co=-20, co_sit="ativo", estavel_co=0)
    io = IOFalso(eventos=(0, 3))
    assert boot.rotina(io) is None and io.pbo == []


def test_processador_trocado_zera():
    preparar(co=-10, co_sit="ativo", estavel_co=-10)
    io = IOFalso(cpu="AMD Ryzen 7 5800X3D 8-Core Processor")
    assert boot.rotina(io) is None and io.pbo == []
    e = estado.carregar()
    assert e["cpu"]["estavel"] == 0 and e["cpu"]["perfil"] == {}


def test_sem_nada_pendente_nao_faz_nada():
    preparar()
    io = IOFalso()
    assert boot.rotina(io) is None and io.pbo == []
