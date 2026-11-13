"""Funções chamadas pela interface (JavaScript → Python via pywebview).

Toda função devolve um dicionário. Erros viram {"erro": "mensagem"} e vão para o log.
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import threading
import traceback

from . import atualizador, bench, conhecimento, estado, hardware, motor, sistema, testes
from .versao import NOME, REPO, __version__

log = sistema.log


def _seguro(fn):
    @functools.wraps(fn)
    def envolto(self, *a, **k):
        try:
            r = fn(self, *a, **k)
            return r if r is not None else {"ok": True}
        except TimeoutError:
            return {"erro": "O estado está em uso pela tarefa de boot. Tente de novo em instantes."}
        except Exception as ex:
            log.error("api.%s falhou:\n%s", fn.__name__, traceback.format_exc())
            return {"erro": str(ex) or ex.__class__.__name__}
    return envolto


def comparar_perfil(esperado: dict, lido: dict) -> list[dict]:
    """Campos que a BIOS não aplicou como pedido (frequência pela razão do MEMCLK)."""
    dif = []
    pares = [("freq", "mts_ratio")] + [(k, k) for k in ("gdm", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRC",
                                                         "tRFC", "tRRDS", "tRRDL", "tFAW", "tWTRS", "tWTRL",
                                                         "tWR", "tRTP", "tCWL")]
    for k_esp, k_lido in pares:
        if k_lido not in lido:
            continue
        a, b = esperado[k_esp], lido[k_lido]
        tolerancia = 20 if k_esp == "freq" else 0
        if abs(a - b) > tolerancia:
            dif.append({"campo": k_esp, "nome": motor.NOMES[k_esp], "esperado": a, "lido": b})
    return dif


def perfil_do_hardware(t: dict, pm: dict, vdram: float, tem_fclk: bool) -> dict:
    p = {k: t[k] for k in ("gdm", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRC", "tRFC", "tRRDS", "tRRDL",
                           "tFAW", "tWTRS", "tWTRL", "tWR", "tRTP", "tCWL")}
    p["freq"] = int(round(pm["mclk"] * 2)) if pm.get("mclk") else t["mts_ratio"]
    p["fclk"] = (int(round(pm["fclk"])) if pm.get("fclk") else p["freq"] // 2) if tem_fclk else 0
    p["vsoc"] = round(pm["vsoc"], 3) if pm.get("vsoc") else 1.10
    p["vdram"] = vdram
    return p


class Api:
    def __init__(self):
        self._janela = None
        self._zen = None
        self._zen_erro = None
        self._zen_lock = threading.Lock()
        self._hw = None
        self._teste = None
        self._info_atualizacao = None
        self._download = {"estado": "parado", "fracao": 0}
        self._monitor = None
        self._bench = {"rodando": False}
        self._mapa_nucleos: dict[int, int] = {}

    # ------------------------------------------------------------ hardware
    def _abrir_zen(self):
        with self._zen_lock:
            if self._zen is None and self._zen_erro is None:
                try:
                    from .zen import Zen
                    self._zen = Zen()
                except Exception as ex:
                    self._zen_erro = str(ex)
                    log.warning("acesso ao hardware indisponível: %s", ex)
            return self._zen

    @_seguro
    def iniciar(self):
        """Chamado pela tela de abertura: detecta o hardware e devolve tudo para montar a interface."""
        self._hw = sistema.ler_hardware()
        perfil = hardware.classificar_cpu(self._hw.get("cpu", ""), self._hw.get("nucleos", 0))
        fab = hardware.fabricante_placa(self._hw.get("placa_fab", ""))
        z = self._abrir_zen()
        codinome = z.codinome() if z else None

        def aplicar(e):
            antigo = e["cpu"]["perfil"]
            if antigo.get("nome") and antigo["nome"] != perfil.nome:
                estado.registrar(e, "CPU", f"Processador trocado ({antigo['nome']} → {perfil.nome}). "
                                           "Curve Optimizer zerado.", log)
                e["cpu"].update(estavel=0, teste=None, feito=False, nucleos=None)
            d = perfil.to_dict()
            d["suporta_co"] = bool(z and z.suporta_co())
            d["codinome"] = codinome
            e["cpu"]["perfil"] = d
            e["config"]["placa"] = fab
            self._confirmar_cpu_se_pronto(e)
        with estado.transacao() as e:
            aplicar(e)
        if self._monitor is None:
            from .monitor import Monitor
            self._monitor = Monitor(self._abrir_zen, perfil.nucleos)
            self._monitor.iniciar()
        inicio = (dt.datetime.now() - dt.timedelta(days=14)).replace(microsecond=0).isoformat()
        k41, whea = sistema.eventos_desde(inicio)
        return {"hw": self._hw, "cpu": perfil.to_dict() | {"codinome": codinome}, "placa": fab,
                "driver": self.driver(), "travamentos": {"k41": k41, "whea": whea},
                "bios": hardware.CAMINHO_BIOS.get(fab, hardware.CAMINHO_BIOS["Outra"]),
                "versao": __version__, "repo": REPO, "estado": self._estado()}

    @_seguro
    def driver(self):
        from . import pawnio
        return {"instalado": pawnio.pasta_instalacao() is not None, "versao": pawnio.versao_instalada(),
                "ok": self._zen is not None, "erro": self._zen_erro}

    @_seguro
    def ao_vivo(self):
        z = self._abrir_zen()
        if not z:
            return {"disponivel": False, "erro": self._zen_erro}
        r = {"disponivel": True, "temp": z.temperatura()}
        try:
            r.update(z.tabela_energia())
        except Exception as ex:
            r["pm_erro"] = str(ex)
        return r

    @_seguro
    def monitor_desde(self, n=0):
        if not self._monitor:
            return {"amostras": [], "picos": {}}
        return self._monitor.desde(int(n or 0))

    @_seguro
    def travamentos(self, dias=30):
        return {"eventos": sistema.eventos_lista(int(dias))}

    @_seguro
    def ler_timings(self):
        z = self._abrir_zen()
        if not z:
            return {"erro": f"Não consegui acessar o hardware: {self._zen_erro}"}
        t = z.timings()
        try:
            pm = z.tabela_energia()
        except Exception:
            pm = {}
        co = None
        try:
            co = z.ler_co()
        except Exception:
            pass
        return {"timings": t, "pm": pm, "co": co}

    # ------------------------------------------------------------ estado
    def _estado(self):
        e = estado.carregar()
        e["historico"] = e["historico"][-200:]
        e["mem"]["economia"] = motor.economia(e["mem"])
        return e

    @_seguro
    def obter_estado(self):
        return self._estado()

    def _acao(self, fn):
        with estado.transacao() as e:
            r = fn(e)
        return {"ok": True, "resultado": r, "estado": self._estado()}

    def _reg(self, e, tipo, texto):
        estado.registrar(e, tipo, texto, log)

    @_seguro
    def config(self, chave, valor):
        if chave not in ("verificar_atualizacao", "animacoes", "versao_ignorada", "avancado"):
            return {"erro": "configuração desconhecida"}
        return self._acao(lambda e: e["config"].__setitem__(chave, valor))

    # ------------------------------------------------------------ memória
    @_seguro
    def mem_usar_hardware(self, vdram):
        """Lê os timings atuais e salva como ponto de partida."""
        vdram = round(float(vdram), 3)
        r = self.ler_timings()
        if "erro" in r:
            return r
        tem_fclk = estado.carregar()["cpu"]["perfil"].get("tem_fclk", True)
        p = perfil_do_hardware(r["timings"], r["pm"], vdram, tem_fclk)
        erros = motor.validar_perfil(p)
        if erros:
            return {"erro": "Valores lidos fora do esperado: " + "; ".join(erros)}

        def f(e):
            e["mem"].update(estavel=p, confirmado=True)
            motor.reiniciar_busca(e["mem"])
            self._reg(e, "Memória", f"Ponto de partida lido do hardware: {p['freq']} MT/s CL{p['tCL']}-"
                                    f"{p['tRCDRD']}-{p['tRP']}-{p['tRAS']} tRFC {p['tRFC']} "
                                    f"({motor.ns_trfc(p):.0f} ns), {vdram} V.")
        return self._acao(f)

    @_seguro
    def mem_salvar_base(self, perfil):
        p = {}
        for k, _, _ in motor.CAMPOS:
            v = perfil[k]
            p[k] = round(float(v), 3) if k in motor.DECIMAIS else int(float(v))
        erros = motor.validar_perfil(p)
        if erros:
            return {"erro": "; ".join(erros)}

        def f(e):
            e["mem"].update(estavel=p, confirmado=True)
            motor.reiniciar_busca(e["mem"])
            self._reg(e, "Memória", f"Ponto de partida salvo: {p['freq']} MT/s CL{p['tCL']}.")
        return self._acao(f)

    @_seguro
    def mem_preparar(self):
        def f(e):
            if not e["mem"]["confirmado"]:
                raise RuntimeError("Defina o ponto de partida primeiro.")
            if e["cpu"]["teste"]:
                raise RuntimeError("Há um teste de Curve Optimizer em andamento. Teste uma coisa de cada vez.")
            passo = motor.preparar_mem(e)
            if passo:
                self._reg(e, "Memória", f"Etapa preparada: {motor.DESCR_ETAPA[passo]}.")
            return passo
        return self._acao(f)

    @_seguro
    def mem_reiniciar_bios(self):
        def f(e):
            motor.marcar_aplicada_mem(e)
            self._reg(e, "Memória", "Reiniciando na BIOS para aplicar a etapa.")
        r = self._acao(f)
        ok, msg = sistema.reiniciar(bios=True)
        if not ok:
            self._acao(lambda e: e["mem"]["teste"].__setitem__("situacao", "preparada"))
            return {"erro": f"Não consegui reiniciar direto na BIOS ({msg}). Reinicie e aperte DEL."}
        return r

    @_seguro
    def mem_conferir(self):
        """Confere no hardware se a BIOS aplicou a etapa (também roda sozinho no boot)."""
        r = self.ler_timings()
        if "erro" in r:
            return r

        def f(e):
            t = e["mem"]["teste"]
            if not t:
                return None
            dif = comparar_perfil(t["perfil"], r["timings"])
            freq_errada = any(d["campo"] == "freq" for d in dif)
            if freq_errada:
                self._reg(e, "Memória", motor.falhar_mem(e, f"a memória está a {r['timings']['mts_ratio']} MT/s "
                                                            "(a BIOS voltou ao padrão)"))
                return {"situacao": "falhou", "diferencas": dif}
            t["diferencas"] = dif
            t["situacao"] = "divergente" if dif else "testar"
            return {"situacao": t["situacao"], "diferencas": dif}
        return self._acao(f)

    @_seguro
    def mem_aceitar_divergencia(self):
        def f(e):
            t = e["mem"]["teste"]
            lido = self.ler_timings()["timings"]
            for d in t.get("diferencas", []):
                if d["campo"] != "freq":
                    t["perfil"][d["campo"]] = lido[d["campo"]]
            t["situacao"] = "testar"
            t["diferencas"] = []
            self._reg(e, "Memória", "Etapa aceita com os valores que a BIOS aplicou.")
        return self._acao(f)

    @_seguro
    def mem_resultado(self, passou: bool, motivo: str = ""):
        def f(e):
            t = e["mem"]["teste"]
            if not t:
                return None
            ok, por_que = passou, motivo
            k41, whea = sistema.eventos_desde(t["desde"])
            if ok and (k41 > 0 or whea > 0):
                ok, por_que = False, f"{k41} travamento(s) e {whea} erro(s) WHEA desde a etapa"
            self._reg(e, "Memória", motor.passar_mem(e) if ok else motor.falhar_mem(e, por_que or "erro no teste"))
            return "passou" if ok else "falhou"
        return self._acao(f)

    @_seguro
    def mem_pular(self):
        return self._acao(lambda e: self._reg(e, "Memória", motor.pular_mem(e)))

    @_seguro
    def mem_aceitar_pulados(self):
        def f(e):
            e["mem"]["pulados"] = []
            self._reg(e, "Memória", "Ajustes pulados mantidos como estão.")
        return self._acao(f)

    @_seguro
    def mem_retomar_pulados(self, incluir_freq=True):
        def f(e):
            if e["mem"]["teste"]:
                raise RuntimeError("Termine ou cancele a etapa aberta primeiro.")
            voltaram = motor.retomar_pulados(e["mem"], bool(incluir_freq))
            if voltaram:
                self._reg(e, "Memória", "Ajustes pulados de volta à fila: "
                                        + ", ".join(motor.DESCR_ETAPA[x] for x in voltaram) + ".")
            return voltaram
        return self._acao(f)

    @_seguro
    def mem_cancelar(self):
        def f(e):
            e["mem"]["teste"] = None
            self._reg(e, "Memória", "Etapa cancelada.")
        return self._acao(f)

    @_seguro
    def mem_recomecar(self):
        def f(e):
            motor.reiniciar_busca(e["mem"])
            self._reg(e, "Memória", "Busca recomeçada a partir do estável.")
        return self._acao(f)

    # ------------------------------------------------------------ inteligência da memória
    def _ler_spds(self) -> list[dict]:
        from . import spd
        from .zen import SMBus
        bus = SMBus()
        try:
            brutos = bus.ler_spds()
        finally:
            bus.fechar()
        r = []
        for slot, dados in sorted(brutos.items()):
            try:
                d = spd.decodificar(dados)
                d["slot"] = slot
                r.append(d)
            except ValueError:
                continue
        return r

    def _aplicar_chip(self, e, chip: dict, pentes: list[dict]):
        perfil_cpu = e["cpu"]["perfil"] or {}
        ranks = sum(p.get("ranks", 1) for p in pentes) or 2
        qtd = len(pentes) or int((self._hw or {}).get("pentes") or 2)
        e["mem"]["chip"] = dict(chip, pentes=pentes)
        e["mem"]["alvos"] = conhecimento.alvos(chip["chip"], perfil_cpu, ranks, qtd)

    @_seguro
    def memoria_identificar(self):
        """Lê o SPD dos pentes, identifica o chip e calcula os alvos."""
        pentes, erro = [], None
        try:
            pentes = self._ler_spds()
        except Exception as ex:
            erro = str(ex)
            log.warning("não consegui ler o SPD: %s", ex)
        chip = conhecimento.identificar(pentes)
        if erro:
            chip["motivo"] += f" ({erro})"
        resumo = [{k: p.get(k) for k in ("slot", "fabricante_dram", "fabricante_modulo", "densidade_gbit",
                                         "largura", "ranks", "tamanho_gb", "modelo", "xmp", "jedec_mts",
                                         "jedec_cl")} for p in pentes]

        def f(e):
            if pentes:
                e["mem"]["chip_spd"] = dict(chip, pentes=resumo)
            atual = e["mem"].get("chip") or {}
            if atual.get("manual"):
                if pentes:
                    atual["pentes"] = resumo
                return  # o usuário escolheu à mão: não sobrescreve (a tela avisa se os pentes discordarem)
            self._aplicar_chip(e, chip, resumo)
            self._reg(e, "Memória", f"Chip identificado: {chip['nome']} (confiança {chip['confianca']}).")
        return self._acao(f)

    @_seguro
    def memoria_escolher_chip(self, chave):
        if chave not in conhecimento.CHIPS:
            return {"erro": "chip desconhecido"}

        def f(e):
            pentes = (e["mem"].get("chip") or {}).get("pentes", [])
            chip = {"chip": chave, "nome": conhecimento.CHIPS[chave]["nome"], "confianca": "escolhido por você",
                    "motivo": "Escolhido à mão.", "manual": True}
            self._aplicar_chip(e, chip, pentes)
            self._reg(e, "Memória", f"Chip escolhido à mão: {chip['nome']}.")
        return self._acao(f)

    @_seguro
    def memoria_usar_spd(self):
        """Volta a usar o chip que o SPD dos pentes indica (desfaz a escolha à mão)."""
        def f(e):
            spd_chip = e["mem"].get("chip_spd")
            if not spd_chip:
                raise RuntimeError("Os pentes ainda não foram lidos.")
            chip = {k: v for k, v in spd_chip.items() if k != "pentes"}
            self._aplicar_chip(e, chip, spd_chip.get("pentes", []))
            # alvos novos: os ajustes que ainda não foram testados recalculam a lista de valores
            for passo, b in list(e["mem"].get("busca", {}).items()):
                if not b.get("tentativas") and passo not in e["mem"]["feitos"]:
                    del e["mem"]["busca"][passo]
            self._reg(e, "Memória", f"Chip conforme os pentes: {chip['nome']}.")
        return self._acao(f)

    @_seguro
    def memoria_opcoes_chip(self):
        return {"opcoes": conhecimento.OPCOES}

    @_seguro
    def memoria_medir(self, rotulo=""):
        """Mede a memória (latência real e banda) e guarda junto com o perfil estável atual."""
        r = bench.medir(False)

        def f(e):
            p = e["mem"]["estavel"]
            med = {"quando": motor.agora_iso(), "freq": p["freq"], "tCL": p["tCL"], "tRCDRD": p["tRCDRD"],
                   "tRFC": p["tRFC"], "gbps": r["copia"], "lat_ns": r["lat_ns"],
                   "lat_cas_ns": round(p["tCL"] * 2000 / p["freq"], 2), "trfc_ns": round(motor.ns_trfc(p))}
            e["mem"].setdefault("medicoes", []).append(med)
            del e["mem"]["medicoes"][:-40]
            self._guardar_bench(e, r, rotulo or "Memória medida")
            return med
        return self._acao(f)

    # ------------------------------------------------------------ desempenho (antes e depois)
    def _retrato(self, e) -> dict:
        """O que está valendo agora: memória (lida do hardware quando dá) e Curve Optimizer."""
        p = dict(e["mem"]["estavel"])
        try:
            z = self._abrir_zen()
            if z:
                t = z.timings()
                p.update({k: t[k] for k in ("tCL", "tRCDRD", "tRP", "tRAS", "tRFC") if k in t})
                p["freq"] = t.get("mts_ratio") or p["freq"]
        except Exception:
            pass
        co = motor.valor_co_no_boot(e)
        return {"mem": f"{p['freq']} CL{p['tCL']}-{p['tRCDRD']}-{p['tRP']}-{p['tRAS']}",
                "trfc_ns": round(motor.ns_trfc(p)), "co": motor.texto_valor(co) if co else "0"}

    def _guardar_bench(self, e, r: dict, rotulo: str) -> dict:
        item = {"quando": motor.agora_iso(), "rotulo": rotulo, **self._retrato(e), **r}
        lista = e.setdefault("bench", [])
        lista.append(item)
        del lista[1:-59]  # guarda a primeira (a referência de antes de tudo) e as 59 últimas
        return item

    @_seguro
    def bench_iniciar(self, completo=True, rotulo=""):
        if self._bench.get("rodando"):
            return {"erro": "Já há uma medição rodando."}
        if self._teste and self._teste.obter().get("rodando"):
            return {"erro": "Espere o teste de estabilidade terminar."}
        self._bench = {"rodando": True, "etapa": "preparando", "fracao": 0}

        def progresso(etapa, fracao):
            self._bench.update(etapa=etapa, fracao=fracao)

        def rodar():
            try:
                r = bench.medir(bool(completo), progresso)
                with estado.transacao() as e:
                    item = self._guardar_bench(e, r, rotulo or "Medição manual")
                self._bench = {"rodando": False, "fracao": 1, "resultado": item}
                log.info("medição de desempenho: %s", r)
            except Exception as ex:
                log.error("medição falhou:\n%s", traceback.format_exc())
                self._bench = {"rodando": False, "erro": str(ex)}
        threading.Thread(target=rodar, daemon=True).start()
        return {"ok": True}

    @_seguro
    def bench_status(self):
        return dict(self._bench)

    @_seguro
    def bench_retrato(self):
        return self._retrato(estado.carregar())

    @_seguro
    def bench_apagar(self, quando):
        def f(e):
            e["bench"] = [b for b in e.get("bench", []) if b["quando"] != quando]
        return self._acao(f)

    # ------------------------------------------------------------ processador
    @_seguro
    def cpu_preparar(self):
        if not sistema.tarefa_ok():
            ok, msg = sistema.criar_tarefa()
            if not ok:
                return {"erro": f"Não consegui criar a tarefa de boot: {msg}"}

        def f(e):
            if not e["cpu"]["perfil"].get("suporta_co"):
                raise RuntimeError("Este processador não tem Curve Optimizer acessível.")
            if e["mem"]["teste"]:
                raise RuntimeError("Há uma etapa de memória em andamento. Teste uma coisa de cada vez.")
            v = motor.preparar_cpu(e)
            if v is not None:
                self._reg(e, "CPU", f"Curve Optimizer {v} preparado para o próximo boot.")
            return v
        return self._acao(f)

    @_seguro
    def cpu_refinar_nucleos(self):
        """Próxima rodada núcleo por núcleo. Aplica na hora, sem reiniciar: se travar, o reinício já volta
        ao último valor bom (a tarefa de boot vê o desligamento e reprova a rodada)."""
        if not sistema.tarefa_ok():
            ok, msg = sistema.criar_tarefa()
            if not ok:
                return {"erro": f"Não consegui criar a tarefa de boot: {msg}"}

        def f(e):
            c = e["cpu"]
            if not c["perfil"].get("suporta_co"):
                raise RuntimeError("Este processador não tem Curve Optimizer acessível.")
            if e["mem"]["teste"]:
                raise RuntimeError("Há uma etapa de memória em andamento. Teste uma coisa de cada vez.")
            if c["teste"]:
                raise RuntimeError("Já há um teste do processador em andamento.")
            if not c["feito"]:
                raise RuntimeError("Primeiro termine o ajuste igual para todos os núcleos.")
            v = motor.preparar_nucleos(e)
            if v is not None:
                self._reg(e, "CPU", f"{motor.descr_co(c['teste'])} preparado.")
            return v
        r = self._acao(f)
        if r["resultado"] is not None:
            r = self.cpu_aplicar_agora()
        return r

    @_seguro
    def cpu_parar_nucleos(self):
        """Encerra a fase núcleo por núcleo com os valores de hoje."""
        def f(e):
            c = e["cpu"]
            if not c.get("nucleos"):
                motor.iniciar_nucleos(e)
            c["nucleos"]["feito"] = True
            self._reg(e, "CPU", f"Curve Optimizer mantido em {motor.resumo_co(c)}.")
        return self._acao(f)

    @_seguro
    def cpu_aplicar_agora(self):
        """Aplica o valor em teste já, sem reiniciar (só para a rodada núcleo por núcleo)."""
        t = estado.carregar()["cpu"]["teste"]
        if not t or t.get("modo") != "nucleos":
            return {"erro": "Nada para aplicar agora."}
        z = self._abrir_zen()
        if not z:
            return {"erro": f"Sem acesso ao hardware: {self._zen_erro}"}
        try:
            z.aplicar_co(list(t["valores"]))
        except Exception as ex:
            log.error("aplicar CO por núcleo:\n%s", traceback.format_exc())
            return {"erro": f"O processador não aceitou agora ({ex}). Reinicie: o valor entra no próximo boot."}

        def f(e):
            tt = e["cpu"]["teste"]
            if tt and tt["situacao"] in ("pendente", "observando"):
                if tt["situacao"] == "pendente":
                    tt["situacao"] = "ativo"
                    tt["desde"] = motor.agora_iso()
                self._reg(e, "CPU", f"{motor.descr_co(tt)} aplicado agora, sem reiniciar.")
        return self._acao(f)

    def _confirmar_cpu_se_pronto(self, e):
        """Depois de 24 h de uso normal sem travar, o valor em observação vira o novo estável."""
        if not motor.observacao_completa(e):
            return
        t = e["cpu"]["teste"]
        k41, whea = sistema.eventos_desde(t["desde"])
        if k41 > 0 or whea > 0:
            self._reg(e, "CPU", motor.falhar_cpu(e, f"{k41} travamento(s) e {whea} erro(s) WHEA durante o uso"))
        elif k41 == 0 and whea == 0:
            self._reg(e, "CPU", motor.passar_cpu(e) + f" Confirmado depois de {motor.HORAS_OBSERVACAO} h sem travar.")

    @_seguro
    def cpu_reiniciar(self):
        ok, msg = sistema.reiniciar(bios=False)
        return {"ok": True} if ok else {"erro": msg}

    @_seguro
    def cpu_resultado(self, passou: bool, motivo: str = ""):
        def f(e):
            t = e["cpu"]["teste"]
            if not t:
                return None
            ok, por_que = passou, motivo
            k41, whea = sistema.eventos_desde(t["desde"])
            if ok and (k41 > 0 or whea > 0):
                ok, por_que = False, f"{k41} travamento(s) e {whea} erro(s) WHEA"
            self._reg(e, "CPU", motor.passar_cpu(e) if ok else motor.falhar_cpu(e, por_que or "erro no teste"))
            return "passou" if ok else "falhou"
        return self._acao(f)

    @_seguro
    def cpu_cancelar(self):
        def f(e):
            e["cpu"]["teste"] = None
            self._reg(e, "CPU", "Teste cancelado; o próximo boot usa o último estável.")
        return self._acao(f)

    @_seguro
    def cpu_zerar(self):
        def f(e):
            e["cpu"].update(estavel=0, teste=None, feito=False, nucleos=None)
            self._reg(e, "CPU", "Curve Optimizer zerado. Vale a partir do próximo boot.")
        return self._acao(f)

    @_seguro
    def cpu_recomecar(self):
        def f(e):
            c = e["cpu"]
            if c.get("nucleos"):  # recomeça só a parte núcleo por núcleo
                c["nucleos"]["limite"] = [v <= motor.CO_MIN for v in c["nucleos"]["estavel"]]
                c["nucleos"]["feito"] = False
            else:
                c["feito"] = False
        return self._acao(f)

    # ------------------------------------------------------------ testes embutidos
    @_seguro
    def teste_memoria(self, minutos, percentual):
        if self._teste and self._teste.obter().get("rodando"):
            return {"erro": "Já há um teste rodando."}
        livre = testes.memoria_livre_mb()
        mb = max(256, int(livre * min(90, max(10, int(percentual))) / 100))
        self._teste = testes.TesteMemoria()
        self._teste.iniciar(mb, float(minutos), self._fim_teste)
        log.info("teste de memória: %s MB por %s min", mb, minutos)
        return {"ok": True, "mb": mb}

    @_seguro
    def teste_nucleos(self, segundos_por_nucleo):
        if self._teste and self._teste.obter().get("rodando"):
            return {"erro": "Já há um teste rodando."}
        cpus = testes.cpus_por_nucleo()
        t = estado.carregar()["cpu"]["teste"]
        if t and t.get("modo") == "nucleos" and t.get("situacao") == "ativo":
            cpus = [cpus[i] for i in t["mudados"] if i < len(cpus)]
            self._mapa_nucleos = {cpu: i for cpu, i in zip(cpus, t["mudados"], strict=False)}
        else:
            self._mapa_nucleos = {}
        self._teste = testes.TesteNucleos()
        self._teste.iniciar(cpus, float(segundos_por_nucleo), self._fim_teste)
        log.info("teste de núcleos: %s, %ss cada", cpus, segundos_por_nucleo)
        return {"ok": True, "nucleos": cpus}

    def _fim_teste(self, s):
        """Teste terminou: se havia etapa esperando teste, registra o resultado sozinho."""
        log.info("teste terminou: %s", {k: s.get(k) for k in ("tipo", "resultado", "erros", "msg")})
        if s.get("resultado") not in ("passou", "falhou"):
            return
        passou = s["resultado"] == "passou"
        motivo = s.get("msg") or f"{s.get('erros', 0)} erro(s) no teste"
        try:
            e = estado.carregar()
            if s["tipo"] == "memoria" and e["mem"]["teste"] and e["mem"]["teste"]["situacao"] == "testar":
                r = self.mem_resultado(passou, motivo)
                if r.get("resultado") == "passou":
                    passo = (e["mem"]["teste"] or {}).get("passo")
                    self.memoria_medir(f"Depois de: {motor.DESCR_ETAPA.get(passo, 'memória')}")
            elif s["tipo"] == "nucleos" and self._mapa_nucleos and e["cpu"]["teste"] \
                    and e["cpu"]["teste"]["situacao"] == "ativo" and e["cpu"]["teste"].get("modo") == "nucleos" \
                    and (passou or any(v == "erro" for v in (s.get("nucleos") or {}).values())):
                falhos = [self._mapa_nucleos[int(c)] for c, v in (s.get("nucleos") or {}).items()
                          if v == "erro" and int(c) in self._mapa_nucleos]
                r = self._acao(lambda e: self._reg(e, "CPU", motor.resultado_teste_nucleos(e, falhos)))
                if falhos and r["estado"]["cpu"]["teste"]:
                    self.cpu_aplicar_agora()  # os que erraram voltam ao valor anterior já
            elif s["tipo"] == "nucleos" and e["cpu"]["teste"] and e["cpu"]["teste"]["situacao"] == "ativo":
                if passou:
                    self._acao(lambda e: self._reg(e, "CPU", motor.observar_cpu(e)))
                else:
                    self.cpu_resultado(False, motivo)
        except Exception:
            log.error("registrar resultado do teste:\n%s", traceback.format_exc())

    @_seguro
    def teste_status(self):
        return self._teste.obter() if self._teste else {"rodando": False}

    @_seguro
    def teste_parar(self):
        if self._teste:
            self._teste.parar()

    # ------------------------------------------------------------ atualização e sistema
    @_seguro
    def atualizacao_verificar(self):
        info = atualizador.verificar()
        self._info_atualizacao = info
        return {"nova": info, "atual": __version__, "configurado": atualizador.repo_configurado()}

    @_seguro
    def atualizacao_instalar(self):
        info = self._info_atualizacao
        if not info:
            return {"erro": "Nenhuma atualização encontrada."}
        self._download = {"estado": "baixando", "fracao": 0}

        def rodar():
            try:
                caminho = atualizador.baixar(info, lambda p: self._download.__setitem__("fracao", p))
                self._download = {"estado": "instalando", "fracao": 1}
                atualizador.instalar(caminho)
                if self._janela:
                    self._janela.destroy()
            except Exception as ex:
                log.error("atualização falhou: %r", ex)
                self._download = {"estado": "erro", "msg": str(ex)}
        threading.Thread(target=rodar, daemon=True).start()
        return {"ok": True}

    @_seguro
    def atualizacao_status(self):
        return self._download

    @_seguro
    def abrir_pasta_dados(self):
        os.startfile(estado.pasta_dados())

    @_seguro
    def abrir_link(self, url):
        if url.startswith("https://"):
            import webbrowser
            webbrowser.open(url)

    @_seguro
    def sobre(self):
        from . import pawnio
        return {"nome": NOME, "versao": __version__, "repo": REPO, "driver": pawnio.versao_instalada(),
                "dados": estado.pasta_dados()}
