import datetime as dt
import logging

from ryzentune import api, boot, estado, hardware, motor

NOME = "AMD Ryzen 7 5700X3D 8-Core Processor"


def com_teste(situacao, horas_atras=0):
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu(NOME, 8).to_dict()
    e["cpu"]["estavel"] = -10
    quando = (dt.datetime.now() - dt.timedelta(hours=horas_atras)).replace(microsecond=0).isoformat()
    e["cpu"]["teste"] = {"valor": -15, "situacao": situacao, "desde": quando, "desde_obs": quando}
    return e


def test_observar_muda_situacao():
    e = com_teste("ativo")
    texto = motor.observar_cpu(e)
    assert e["cpu"]["teste"]["situacao"] == "observando" and "24 h" in texto


def test_observacao_completa_so_depois_de_24h():
    assert not motor.observacao_completa(com_teste("observando", 23))
    assert motor.observacao_completa(com_teste("observando", 25))
    assert not motor.observacao_completa(com_teste("ativo", 25))


def test_confirma_sozinho_sem_travamento(monkeypatch):
    monkeypatch.setattr(api.sistema, "eventos_desde", lambda iso: (0, 0))
    e = com_teste("observando", 25)
    api.Api()._confirmar_cpu_se_pronto(e)
    assert e["cpu"]["estavel"] == -15 and e["cpu"]["teste"] is None
    assert "Confirmado" in e["historico"][-1]["texto"]


def test_reprova_se_travou_durante_o_uso(monkeypatch):
    monkeypatch.setattr(api.sistema, "eventos_desde", lambda iso: (1, 0))
    e = com_teste("observando", 25)
    api.Api()._confirmar_cpu_se_pronto(e)
    assert e["cpu"]["estavel"] == -10 and e["cpu"]["teste"] is None and e["cpu"]["feito"]


def test_eventos_ilegiveis_esperam(monkeypatch):
    monkeypatch.setattr(api.sistema, "eventos_desde", lambda iso: (-1, -1))
    e = com_teste("observando", 25)
    api.Api()._confirmar_cpu_se_pronto(e)
    assert e["cpu"]["teste"]["situacao"] == "observando"


class IO:
    log = logging.getLogger("t")

    def __init__(self, ev):
        self.ev, self.co = ev, []

    def ler_timings(self):
        return None

    def velocidade_ram(self):
        return 0

    def eventos_desde(self, iso):
        return self.ev

    def nome_cpu(self):
        return NOME

    def aplicar_co(self, v):
        self.co.append(v)
        return True


def test_boot_reprova_travamento_durante_observacao():
    estado.salvar(com_teste("observando", 3))
    io = IO((1, 0))
    assert boot.rotina(io) == -10
    assert estado.carregar()["cpu"]["teste"] is None


def test_boot_mantem_observacao_sem_travamento():
    estado.salvar(com_teste("observando", 3))
    io = IO((0, 0))
    assert boot.rotina(io) == -15
    assert estado.carregar()["cpu"]["teste"]["situacao"] == "observando"
