from ryzentune import api, motor


def lido(**mud):
    t = {k: motor.PADRAO_MEM[k] for k in ("gdm", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRC", "tRFC", "tRRDS",
                                          "tRRDL", "tFAW", "tWTRS", "tWTRL", "tWR", "tRTP", "tCWL")}
    t["mts_ratio"] = motor.PADRAO_MEM["freq"]
    t.update(mud)
    return t


def test_comparar_igual():
    assert api.comparar_perfil(motor.PADRAO_MEM, lido()) == []


def test_comparar_frequencia_com_tolerancia():
    assert api.comparar_perfil(motor.PADRAO_MEM, lido(mts_ratio=3200 + 10)) == []
    dif = api.comparar_perfil(motor.PADRAO_MEM, lido(mts_ratio=2133))
    assert [d["campo"] for d in dif] == ["freq"]


def test_comparar_timing_diferente():
    dif = api.comparar_perfil(motor.PADRAO_MEM, lido(tRFC=600, tCL=18))
    assert {d["campo"] for d in dif} == {"tRFC", "tCL"}
    assert all("nome" in d and "esperado" in d and "lido" in d for d in dif)


def test_perfil_do_hardware_usa_pm_table():
    p = api.perfil_do_hardware(lido(mts_ratio=3600), {"mclk": 1800.0, "fclk": 1800.0, "vsoc": 1.0938}, 1.4, True)
    assert p["freq"] == 3600 and p["fclk"] == 1800 and p["vsoc"] == 1.094 and p["vdram"] == 1.4
    assert motor.validar_perfil(p) == []


def test_perfil_do_hardware_sem_pm_table():
    p = api.perfil_do_hardware(lido(mts_ratio=3466), {}, 1.35, True)
    assert p["freq"] == 3466 and p["fclk"] == 1733 and p["vsoc"] == 1.10


def test_perfil_sem_fclk():
    assert api.perfil_do_hardware(lido(), {}, 1.35, False)["fclk"] == 0


def _etapa_em_teste(a):
    a._acao(lambda e: e["mem"].__setitem__("teste", {"desde": "2026-01-01T00:00:00", "passo": "tCL",
                                                      "perfil": dict(motor.PADRAO_MEM, tCL=14),
                                                      "situacao": "testar"}))


def test_resultado_passou(monkeypatch):
    a = api.Api()
    _etapa_em_teste(a)
    monkeypatch.setattr(api.sistema, "eventos_desde", lambda iso: (0, 0))
    r = a.mem_resultado(True)
    assert r["resultado"] == "passou" and r["estado"]["mem"]["estavel"]["tCL"] == 14


def test_resultado_passou_mas_travou_vira_falha(monkeypatch):
    a = api.Api()
    _etapa_em_teste(a)
    monkeypatch.setattr(api.sistema, "eventos_desde", lambda iso: (1, 0))
    r = a.mem_resultado(True)
    assert r["resultado"] == "falhou" and r["estado"]["mem"]["estavel"]["tCL"] == 16
    assert "travamento" in r["estado"]["historico"][-1]["texto"]


def test_api_devolve_erro_em_vez_de_quebrar(monkeypatch):
    a = api.Api()
    monkeypatch.setattr(api.sistema, "eventos_desde", lambda iso: (_ for _ in ()).throw(RuntimeError("x")))
    a._acao(lambda e: e["mem"].__setitem__("teste", {"desde": "2026-01-01T00:00:00", "passo": "tCL",
                                                      "perfil": motor.PADRAO_MEM, "situacao": "testar"}))
    r = a.mem_resultado(True)
    assert r == {"erro": "x"}
