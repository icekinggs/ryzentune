"""Rotina que roda ao entrar no Windows (tarefa agendada).

1. Confere se a etapa de memória aplicada na BIOS "pegou" (a velocidade bate) e se não houve travamento.
2. Ativa o Curve Optimizer pendente ou detecta que o último valor travou o PC e volta ao estável.
3. Aplica o Curve Optimizer (ele some ao desligar, por isso é reaplicado a cada boot).
"""
from __future__ import annotations

from . import estado, motor

TOLERANCIA_MTS = 10


def rotina(io) -> int | None:
    """io precisa ter: velocidade_ram(), eventos_desde(iso), nome_cpu(), rodar_pbo2(exe, args), log.
    Devolve o valor de Curve Optimizer aplicado (ou None)."""
    log = io.log
    with estado.transacao() as e:
        # ---------------- memória
        t = e["mem"]["teste"]
        if t and t.get("situacao") == "aplicada":
            vel = io.velocidade_ram()
            k41, _ = io.eventos_desde(t["desde"])
            alvo = t["perfil"]["freq"]
            if vel and abs(vel - alvo) > TOLERANCIA_MTS:
                estado.registrar(e, "Memória", motor.falhar_mem(
                    e, f"a memória voltou para {vel} MT/s (a etapa não ligou e a BIOS restaurou)"), log)
            elif k41 > 0:
                estado.registrar(e, "Memória", motor.falhar_mem(e, "o PC desligou/travou depois de aplicar"), log)
            else:
                t["situacao"] = "testar"
                extra = "" if vel else " (não consegui ler a velocidade: confira no ZenTimings)"
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
            elif ct["situacao"] == "ativo":
                k41, whea = io.eventos_desde(ct["desde"])
                if k41 > 0 or whea > 0:
                    estado.registrar(e, "CPU", motor.falhar_cpu(
                        e, f"{k41} desligamento(s) forçado(s) e {whea} erro(s) WHEA"), log)
        valor = motor.valor_co_no_boot(e)
        exe, modelo, nucleos = c["pbo2"], c["args"], c["perfil"].get("nucleos", 0)

    if valor and nucleos:
        io.rodar_pbo2(exe, motor.args_pbo2(modelo, valor, nucleos))
        return valor
    return None
