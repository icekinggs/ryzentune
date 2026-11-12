import struct

import pytest

from ryzentune import zen

ESPERADO = {"ratio": 54, "gdm": 1, "cmd2t": 0, "tCL": 16, "tRAS": 36, "tRCDRD": 19, "tRCDWR": 10, "tRC": 55,
            "tRP": 19, "tRRDS": 4, "tRRDL": 6, "tRTP": 10, "tFAW": 16, "tCWL": 16, "tWTRS": 4, "tWTRL": 12,
            "tWR": 20, "tRDRDSCL": 4, "tWRWRSCL": 4, "tREFI": 14029, "tCKE": 1, "powerdown": 0}


def montar(t, rfc=(576, 428, 263), canal=0, outro_canal_ativo=False):
    """Monta os registradores a partir dos timings, no formato do UMC."""
    regs = {}

    def por(r, valor, hi, lo):
        regs[r] = regs.get(r, 0) | ((valor & ((1 << (hi - lo + 1)) - 1)) << lo)
    for nome, (r, hi, lo) in zen.MAPA_TIMINGS.items():
        por(r, t[nome], hi, lo)
    regs[0x50260] = rfc[0] | (rfc[1] << 11) | (rfc[2] << 22)
    regs[0x50264] = regs[0x50260]
    regs[0x50050] = regs[0x50058] = 0x87654321
    regs[0x50000] = 1
    base = canal * zen.UMC_CANAL_PASSO
    final = {base | (r & 0xFFFFF): v for r, v in regs.items()}
    if outro_canal_ativo:
        final.update({(zen.UMC_CANAL_PASSO * (1 - canal)) | (r & 0xFFFFF): v for r, v in regs.items()})
    else:
        final[(zen.UMC_CANAL_PASSO * (1 - canal)) | 0x50DF0] = 1 << 19  # canal desligado
    return lambda a: final.get(a, 0)


def test_decodifica_todos_os_timings():
    t = zen.ler_timings(montar(ESPERADO))
    for k, v in ESPERADO.items():
        assert t[k] == v, k
    assert (t["tRFC"], t["tRFC2"], t["tRFC4"]) == (576, 428, 263)
    assert t["mts_ratio"] == 3600 and t["bgs"] == 0 and t["canais"] == 1


def test_canal_b_sozinho():
    t = zen.ler_timings(montar(ESPERADO, canal=1))
    assert t["tCL"] == 16 and t["canais"] == 1


def test_dois_canais():
    assert zen.ler_timings(montar(ESPERADO, outro_canal_ativo=True))["canais"] == 2


def test_sem_canal():
    with pytest.raises(ValueError):
        zen.ler_timings(lambda a: (1 << 19) if (a & 0xFFFFF) == 0x50DF0 else 0)


def test_trfc_alternativo():
    ler0 = montar(ESPERADO)

    def ler(a):
        if a == 0x50260:
            return 0x21060138
        if a == 0x50264:
            return 600 | (440 << 11) | (270 << 22)
        return ler0(a)
    assert zen.ler_timings(ler)["tRFC"] == 600


@pytest.mark.parametrize("raw,mts", [(48, 3200), (54, 3600), (56, 3733), (57, 3800)])
def test_frequencia_pela_razao(raw, mts):
    assert zen.ler_timings(montar(dict(ESPERADO, ratio=raw)))["mts_ratio"] == mts


def test_tabela_energia_vermeer():
    dados = bytearray(0x8F0)
    for off, v in ((0xC0, 1800.0), (0xC8, 1800.0), (0xCC, 1800.0), (0xB4, 1.0938), (0x224, 0.9), (0x228, 0.95),
                   (0x22C, 0.95)):
        struct.pack_into("<f", dados, off, v)
    r = zen.decodificar_pm(0x380805, bytes(dados))
    assert r["fclk"] == 1800 and r["mclk"] == 1800 and abs(r["vsoc"] - 1.0938) < 1e-4


def test_tabela_energia_desconhecida_ou_absurda():
    assert zen.decodificar_pm(0x123456, bytes(0x900)) == {}
    assert zen.decodificar_pm(0x380805, bytes(0x900)) == {}  # tudo zero não passa na conferência


def test_temperatura():
    assert zen.temperatura_tctl(int(55 / 0.125) << 21) == 55.0
    assert zen.temperatura_tctl((int(104 / 0.125) << 21) | (1 << 19)) == 55.0


@pytest.mark.parametrize("m,arg", [(0, 0), (-5, 0xFFFB), (-30, 0xFFE2), (5, 5)])
def test_codificacao_margem(m, arg):
    assert zen.arg_margem(m) == arg
    assert zen.margem_de_retorno(arg) == m


def test_mascara_nucleo():
    assert zen.mascara_nucleo(0, 3) == 3 << 20
    assert zen.mascara_nucleo(1, 7) == (1 << 28) | (7 << 20)


class SMUFalso:
    """Simula a caixa de mensagens: responde 1 (OK) ao receber o comando."""

    def __init__(self, enderecos, resposta=1, ocupado=False):
        self.cmd, self.rsp, self.args = enderecos
        self.regs = {self.rsp: 0 if ocupado else 1}
        self.recebidos = []
        self.resposta = resposta

    def ler(self, r):
        return self.regs.get(r, 0)

    def escrever(self, r, v):
        self.regs[r] = v
        if r == self.cmd:
            self.recebidos.append((v, [self.regs.get(self.args + 4 * i, 0) for i in range(6)]))
            self.regs[self.rsp] = self.resposta


def test_caixa_mp1_envia_e_recebe():
    end = zen.CO["Vermeer"]["mp1"]
    s = SMUFalso(end)
    st, args = zen.CaixaSMU(s.ler, s.escrever, end).enviar(0x36, [zen.arg_margem(-10)])
    assert st == 1 and s.recebidos == [(0x36, [0xFFF6, 0, 0, 0, 0, 0])]


def test_caixa_recusa():
    end = zen.CO["Vermeer"]["mp1"]
    s = SMUFalso(end, resposta=0xFE)
    assert zen.CaixaSMU(s.ler, s.escrever, end).enviar(0x36, [0])[0] == 0xFE


def test_caixa_ocupada_desiste():
    end = zen.CO["Vermeer"]["mp1"]
    s = SMUFalso(end, ocupado=True)
    st, _ = zen.CaixaSMU(s.ler, s.escrever, end, tempo_limite=0.05).enviar(0x36, [0])
    assert st == 0 and s.recebidos == []
