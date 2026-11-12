import json
import os

from ryzentune import estado


def test_novo_e_salvar():
    e = estado.novo()
    e["cpu"]["estavel"] = -10
    estado.salvar(e)
    assert estado.carregar()["cpu"]["estavel"] == -10


def test_migra_estado_antigo():
    with open(estado.arq_estado(), "w", encoding="utf-8") as f:
        json.dump({"mem": {"estavel": {"freq": 3600}}, "cpu": {"estavel": -5}}, f)
    e = estado.carregar()
    assert e["mem"]["estavel"]["freq"] == 3600 and e["mem"]["estavel"]["tCL"] == 16
    assert e["cpu"]["estavel"] == -5 and e["cpu"]["perfil"] == {}
    assert e["config"]["verificar_atualizacao"] is True and e["historico"] == []


def test_corrompido_usa_backup():
    e = estado.novo()
    e["cpu"]["estavel"] = -15
    estado.salvar(e)
    estado.salvar(e)  # cria o .bak
    with open(estado.arq_estado(), "w") as f:
        f.write("{lixo")
    assert estado.carregar()["cpu"]["estavel"] == -15
    assert os.path.exists(estado.arq_estado() + ".corrompido")


def test_corrompido_sem_backup_volta_ao_padrao():
    with open(estado.arq_estado(), "w") as f:
        f.write("[]")
    assert estado.carregar()["cpu"]["estavel"] == 0


def test_transacao_grava_e_desfaz_em_erro():
    with estado.transacao() as e:
        e["cpu"]["estavel"] = -20
    assert estado.carregar()["cpu"]["estavel"] == -20
    try:
        with estado.transacao() as e:
            e["cpu"]["estavel"] = -30
            raise RuntimeError
    except RuntimeError:
        pass
    assert estado.carregar()["cpu"]["estavel"] == -20


def test_historico_limitado():
    e = estado.novo()
    for i in range(600):
        estado.registrar(e, "x", str(i))
    assert len(e["historico"]) == 500 and e["historico"][-1]["texto"] == "599"
