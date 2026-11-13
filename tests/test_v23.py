"""2.3: pulos guardados e retomados, chip pelo SPD, Curve Optimizer por núcleo, monitor e medição."""
import json
import logging

from ryzentune import api, boot, estado, hardware, monitor, motor, zen

NOME = "AMD Ryzen 7 5700X3D 8-Core Processor"
ESTAVEL_REAL = {"gdm": 1, "tCL": 22, "tRCDRD": 25, "tRCDWR": 25, "tRP": 25, "tRAS": 48, "tRC": 73, "tRFC": 630,
                "tRRDS": 7, "tRRDL": 9, "tFAW": 39, "tWTRS": 5, "tWTRL": 14, "tWR": 26, "tRTP": 14, "tCWL": 20,
                "freq": 3600, "fclk": 1800, "vsoc": 0.995, "vdram": 1.35}
# busca como ficou no PC real depois dos 10 cliques em "Pular" (12/11/2026, 23:40)
BUSCA_REAL = {
    "freq": {"lista": [3466, 3600, 3733, 3800], "lo": 1, "hi": 4, "tentativas": 1, "alvo": 1, "repetir": None,
             "indice": 2},
    "tCL": {"lista": [20, 18, 16, 14], "lo": -1, "hi": 4, "tentativas": 0, "alvo": 2, "repetir": None, "indice": 2},
    "tRAS": {"lista": [47], "lo": -1, "hi": 1, "tentativas": 0, "alvo": 0, "repetir": None, "indice": 0},
    "tRFC": {"lista": [340, 330, 320, 310], "lo": -1, "hi": 4, "tentativas": 0, "alvo": 0, "repetir": None,
             "indice": 0},
    "grupoWTR": {"lista": [0], "lo": -1, "hi": 1, "tentativas": 0, "alvo": 0, "repetir": None, "indice": 0},
}


def estado_real():
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu(NOME, 8).to_dict()
    m = e["mem"]
    m.update(estavel=dict(ESTAVEL_REAL), confirmado=True, busca=json.loads(json.dumps(BUSCA_REAL)),
             feitos=["freq", "tCL", "tRAS", "tRFC", "grupoWTR"])
    m.pop("pulados")
    return e


# ---------------------------------------------------------------- pulos
def test_migracao_descobre_os_pulos_do_estado_antigo(tmp_path, monkeypatch):
    monkeypatch.setenv("RYZENTUNE_DADOS", str(tmp_path))
    with open(estado.arq_estado(), "w", encoding="utf-8") as f:
        json.dump(estado_real(), f)
    e = estado.carregar()
    assert e["mem"]["pulados"] == ["freq", "tCL", "tRAS", "tRFC", "grupoWTR"]


def test_limite_encontrado_nao_conta_como_pulo():
    e = estado_real()
    e["mem"]["busca"]["tCL"].update(lo=0, hi=1, tentativas=2)  # passou 20, falhou 18: busca esgotada
    assert "tCL" not in motor.inferir_pulados(e["mem"])


def test_pular_guarda_e_retomar_devolve_a_fila():
    e = estado_real()
    m = e["mem"]
    m["pulados"] = motor.inferir_pulados(m)
    voltaram = motor.retomar_pulados(m, incluir_freq=False)
    assert voltaram == ["tCL", "tRAS", "tRFC", "grupoWTR"]
    assert m["feitos"] == ["freq"] and m["pulados"] == ["freq"]
    assert "tCL" not in m["busca"]  # nunca testado: lista recalculada com o estável e os alvos de agora
    passo, perfil = motor.proxima_etapa_mem(e)
    assert passo == "tCL" and perfil["tCL"] < 22


def test_retomar_mantem_busca_com_tentativas():
    e = estado_real()
    m = e["mem"]
    m["pulados"] = ["freq"]
    motor.retomar_pulados(m)
    assert m["busca"]["freq"]["lo"] == 1  # 3600 já passou: continua daí
    passo, perfil = motor.proxima_etapa_mem(e)
    assert passo == "freq" and perfil["freq"] == 3733


def test_pular_mem_registra_o_pulo():
    e = estado_real()
    m = e["mem"]
    m["feitos"], m["busca"], m["pulados"] = [], {}, []
    motor.preparar_mem(e)
    motor.pular_mem(e)
    assert m["pulados"] == ["freq"] and motor.pulados_mem(m) == ["freq"]


# ---------------------------------------------------------------- chip pelo SPD
class FakeApi(api.Api):
    def __init__(self, pentes):
        super().__init__()
        self._pentes = pentes

    def _ler_spds(self):
        return self._pentes


PENTE = {"slot": 2, "fabricante_dram": "SK Hynix", "densidade_gbit": 8, "largura": 8, "ranks": 2,
         "tamanho_gb": 16, "modelo": "HKED4161CAB2F2HB4", "xmp": {"mts": 3200, "cl": 18}}


def test_escolha_manual_nao_some_mas_o_spd_fica_guardado(tmp_path, monkeypatch):
    monkeypatch.setenv("RYZENTUNE_DADOS", str(tmp_path))
    a = FakeApi([PENTE, dict(PENTE, slot=3)])
    with estado.transacao() as e:
        e["cpu"]["perfil"] = hardware.classificar_cpu(NOME, 8).to_dict()
    a.memoria_escolher_chip("hynix_16")
    r = a.memoria_identificar()
    m = r["estado"]["mem"]
    assert m["chip"]["chip"] == "hynix_16" and m["chip"]["manual"]
    assert m["chip_spd"]["chip"] == "hynix_8"
    r = a.memoria_usar_spd()
    m = r["estado"]["mem"]
    assert m["chip"]["chip"] == "hynix_8" and not m["chip"].get("manual")
    assert m["alvos"]["tRCDRD"] == 20  # 19 do Hynix 8 Gb + 1 por serem 4 ranks no total


# ---------------------------------------------------------------- Curve Optimizer por núcleo
def cpu_feito(estavel=-15):
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu(NOME, 8).to_dict() | {"suporta_co": True}
    e["cpu"].update(estavel=estavel, feito=True)
    return e


def test_rodada_por_nucleo_desce_todos_e_aplica_lista_no_boot():
    e = cpu_feito()
    v = motor.preparar_nucleos(e)
    assert v == [-20] * 8 and e["cpu"]["teste"]["mudados"] == list(range(8))
    assert motor.valor_co_no_boot(e) == [-20] * 8


def test_nucleos_que_erram_voltam_e_param():
    e = cpu_feito()
    motor.preparar_nucleos(e)
    e["cpu"]["teste"]["situacao"] = "ativo"
    motor.resultado_teste_nucleos(e, [2, 5])
    t, nc = e["cpu"]["teste"], e["cpu"]["nucleos"]
    assert t["situacao"] == "observando"
    assert t["valores"] == [-20, -20, -15, -20, -20, -15, -20, -20]
    assert nc["limite"][2] and nc["limite"][5] and not nc["limite"][0]
    motor.passar_cpu(e)
    assert e["cpu"]["nucleos"]["estavel"] == [-20, -20, -15, -20, -20, -15, -20, -20]
    v = motor.preparar_nucleos(e)
    assert v == [-25, -25, -15, -25, -25, -15, -25, -25]


def test_travar_na_rodada_para_todos_os_que_mudaram():
    e = cpu_feito()
    motor.preparar_nucleos(e)
    e["cpu"]["teste"]["situacao"] = "observando"
    texto = motor.falhar_cpu(e, "1 desligamento")
    assert "FALHOU" in texto and e["cpu"]["teste"] is None
    assert e["cpu"]["nucleos"]["feito"] and all(e["cpu"]["nucleos"]["limite"])
    assert motor.valor_co_no_boot(e) == -15 or motor.valor_co_no_boot(e) == [-15] * 8


def test_nao_passa_de_menos_30():
    e = cpu_feito(-30)
    assert motor.preparar_nucleos(e) is None


def test_ninguem_aguentou_encerra_a_rodada():
    e = cpu_feito()
    motor.preparar_nucleos(e)
    motor.resultado_teste_nucleos(e, list(range(8)))
    assert e["cpu"]["teste"] is None and e["cpu"]["nucleos"]["feito"]


class IO:
    log = logging.getLogger("t")

    def __init__(self, ev=(0, 0)):
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


def test_boot_aplica_a_lista_e_reprova_se_travou(tmp_path, monkeypatch):
    monkeypatch.setenv("RYZENTUNE_DADOS", str(tmp_path))
    e = cpu_feito()
    motor.preparar_nucleos(e)
    e["cpu"]["teste"]["situacao"] = "observando"
    estado.salvar(e)
    io = IO()
    assert boot.rotina(io) == [-20] * 8
    io = IO((1, 0))
    boot.rotina(io)
    assert io.co == [[-15] * 8] or io.co == [-15]
    assert estado.carregar()["cpu"]["teste"] is None


# ---------------------------------------------------------------- hardware (funções puras)
def test_tensao_svi2():
    assert zen.tensao_svi2(0x30 << 16) == 1.25
    assert zen.tensao_svi2(0xFF << 16) is None  # 1,55 - 1,59: inválido


def test_conferencia_da_svi2_com_a_tabela_de_energia():
    assert monitor.conferir_svi2({"vcore": 1.3, "vsoc_svi2": 1.0}, {"vsoc": 1.0}) == {"vcore": 1.3}
    assert monitor.conferir_svi2({"vcore": 1.3, "vsoc_svi2": 1.4}, {"vsoc": 1.0}) == {}


def test_instancias_e_agrupamento_por_nucleo():
    assert monitor.ordenar_instancias(["0,10", "0,2", "_Total", "0,_Total", "0,0"]) == ["0,0", "0,2", "0,10"]
    assert monitor.por_nucleo([10, 30, 50, 70], 2) == [20, 60]
    assert monitor.por_nucleo([3000, 4000, 3500, 3600], 2, maximo=True) == [4000, 3600]


def test_cadeia_de_latencia_visita_todas_as_linhas():
    import numpy as np

    from ryzentune import bench
    arr, inicio = bench.montar_cadeia(np, 1)
    base, linhas = arr.ctypes.data, arr.size // 8
    vistos, p = set(), inicio
    for _ in range(linhas):
        i = (p - base) // 64
        assert i not in vistos
        vistos.add(i)
        p = int(arr[i * 8])
    assert p == inicio and len(vistos) == linhas


def test_laco_de_maquina_segue_a_cadeia():
    import numpy as np

    from ryzentune import bench
    arr, inicio = bench.montar_cadeia(np, 1)
    linhas = arr.size // 8
    f = bench._funcao_perseguicao()
    assert f(inicio, linhas) == inicio  # uma volta completa termina onde começou
