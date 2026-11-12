"""Roda os testes embutidos de verdade, em versão curta (processos filhos reais)."""
import time

from ryzentune import testes


def esperar(t, limite=120):
    fim = time.time() + limite
    while t.obter()["rodando"] and time.time() < fim:
        time.sleep(0.2)
    return t.obter()


def test_referencia_deterministica():
    assert testes.carga_referencia() == testes.carga_referencia()


def test_memoria_curta_passa():
    t = testes.TesteMemoria()
    fim = {}
    t.iniciar(256, 0.08, lambda s: fim.update(s))
    s = esperar(t)
    assert s["resultado"] == "passou", s
    assert s["erros"] == 0 and s["ciclo"] >= 1 and fim["resultado"] == "passou"


def test_memoria_parar():
    t = testes.TesteMemoria()
    t.iniciar(256, 5)
    time.sleep(3)
    t.parar()
    assert esperar(t)["resultado"] == "parado"


def test_nucleos_curto_passa():
    t = testes.TesteNucleos()
    cpus = testes.cpus_por_nucleo()[:2]
    t.iniciar(cpus, 3)
    s = esperar(t)
    assert s["resultado"] == "passou", s
    assert all(v == "ok" for v in s["nucleos"].values())


def test_nucleo_com_referencia_errada_falha():
    t = testes.TesteNucleos()
    original = testes.referencia_em_processo
    try:
        # referência "errada" = o que um núcleo instável produziria; o trabalhador tem que acusar
        testes.referencia_em_processo = lambda: "0" * 64
        t.iniciar([0], 2)
        s = esperar(t)
    finally:
        testes.referencia_em_processo = original
    assert s["resultado"] == "falhou" and s["nucleos"]["0"] == "erro"


def test_cpus_por_nucleo():
    c = testes.cpus_por_nucleo()
    assert c and c[0] == 0 and c == sorted(c)
