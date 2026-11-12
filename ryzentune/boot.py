"""Rotina que roda ao entrar no Windows (tarefa agendada).

1. Confere no hardware se a etapa de memória aplicada na BIOS "pegou" (timings lidos = pedidos).
2. Ativa o Curve Optimizer pendente ou detecta que o último valor travou o PC e volta ao estável.
3. Aplica o Curve Optimizer direto no processador (ele some ao desligar; por isso, a cada boot).
"""
from __future__ import annotations

from . import estado, motor
from .api import comparar_perfil

TOLERANCIA_MTS = 20


def rotina(io) -> int | None:
    """io precisa ter: ler_timings() -> dict|None, velocidade_ram(), eventos_desde(iso), nome_cpu(),
    aplicar_co(valor) -> bool, log. Devolve o valor de Curve Optimizer aplicado (ou None)."""
    log = io.log
    with estado.transacao() as e:
        # ---------------- memória
        t = e["mem"]["teste"]
        if t and t.get("situacao") == "aplicada":
            k41, _ = io.eventos_desde(t["desde"])
            lido = io.ler_timings()
            if lido:
                dif = comparar_perfil(t["perfil"], lido)
                vel = lido.get("mts_ratio", 0)
            else:
                dif, vel = [], io.velocidade_ram()
                if vel and abs(vel - t["perfil"]["freq"]) > TOLERANCIA_MTS:
                    dif = [{"campo": "freq"}]
            if any(d["campo"] == "freq" for d in dif):
                estado.registrar(e, "Memória", motor.falhar_mem(
                    e, f"a memória voltou para {vel} MT/s (a etapa não ligou e a BIOS restaurou)"), log)
            elif k41 > 0:
                estado.registrar(e, "Memória", motor.falhar_mem(e, "o PC desligou/travou depois de aplicar"), log)
            elif dif:
                t["situacao"] = "divergente"
                t["diferencas"] = dif
                estado.registrar(e, "Memória", "A BIOS não aplicou todos os valores da etapa: " + ", ".join(
                    f"{d['nome']} {d['lido']} (pedido {d['esperado']})" for d in dif) + ".", log)
            else:
                t["situacao"] = "testar"
                extra = "" if lido else " (não consegui ler os timings; conferi só a velocidade)"
                estado.registrar(e, "Memória", f"PC ligou com a etapa '{motor.DESCR_ETAPA[t['passo']]}'. "
                                               f"Falta o teste.{extra}", log)

        # ---------------- processador
        c = e["cpu"]
        nome = io.nome_cpu()
        if nome and c["perfil"].get("nome") and nome != c["perfil"]["nome"]:
            estado.registrar(e, "CPU", f"Processador trocado ({c['perfil']['nome']} → {nome}). "
                                       "Curve Optimizer zerado; abra o RyzenTune.", log)
            c.update(estavel=0, teste=None, feito=False, perfil={})
            return None
        ct = c["teste"]
        if ct:
            if ct["situacao"] == "pendente":
                ct["situacao"] = "ativo"
                ct["desde"] = motor.agora_iso()
                estado.registrar(e, "CPU", f"Curve Optimizer {ct['valor']} ativado neste boot.", log)
            elif ct["situacao"] in ("ativo", "observando"):
                k41, whea = io.eventos_desde(ct["desde"])
                if k41 > 0 or whea > 0:
                    estado.registrar(e, "CPU", motor.falhar_cpu(
                        e, f"{k41} desligamento(s) forçado(s) e {whea} erro(s) WHEA"), log)
        valor = motor.valor_co_no_boot(e)

    if valor:
        ok = io.aplicar_co(valor)
        if not ok:
            with estado.transacao() as e:
                estado.registrar(e, "CPU", f"Não consegui aplicar o Curve Optimizer {valor} neste boot "
                                           "(veja o log).", log)
            return None
        return valor
    return None
