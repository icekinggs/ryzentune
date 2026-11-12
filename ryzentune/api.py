"""Funções chamadas pela interface (JavaScript → Python via pywebview).

Toda função devolve um dicionário. Erros viram {"erro": "mensagem"} e vão para o log.
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import threading
import traceback

from . import atualizador, conhecimento, estado, hardware, motor, sistema, testes
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
                e["cpu"].update(estavel=0, teste=None, feito=False)
            d = perfil.to_dict()
            d["suporta_co"] = bool(z and z.suporta_co())
            d["codinome"] = codinome
            e["cpu"]["perfil"] = d
            e["config"]["placa"] = fab
        with estado.transacao() as e:
            aplicar(e)
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
        if chave not in ("verificar_atualizacao", "animacoes", "versao_ignorada"):
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
            if (e["mem"].get("chip") or {}).get("manual"):
                return  # o usuário escolheu à mão: não sobrescreve
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
    def memoria_opcoes_chip(self):
        return {"opcoes": conhecimento.OPCOES}

    @_seguro
    def memoria_medir(self):
        """Mede a banda e guarda junto com a latência do perfil estável atual."""
        gbps = testes.medir_banda()

        def f(e):
            p = e["mem"]["estavel"]
            med = {"quando": motor.agora_iso(), "freq": p["freq"], "tCL": p["tCL"], "tRCDRD": p["tRCDRD"],
                   "tRFC": p["tRFC"], "gbps": gbps, "lat_cas_ns": round(p["tCL"] * 2000 / p["freq"], 2),
                   "trfc_ns": round(motor.ns_trfc(p))}
            e["mem"].setdefault("medicoes", []).append(med)
            del e["mem"]["medicoes"][:-40]
            return med
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
            e["cpu"].update(estavel=0, teste=None, feito=False)
            self._reg(e, "CPU", "Curve Optimizer zerado. Vale a partir do próximo boot.")
        return self._acao(f)

    @_seguro
    def cpu_recomecar(self):
        return self._acao(lambda e: e["cpu"].__setitem__("feito", False))

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
                    self.memoria_medir()  # registra a banda do novo perfil estável
            elif s["tipo"] == "nucleos" and e["cpu"]["teste"] and e["cpu"]["teste"]["situacao"] == "ativo":
                self.cpu_resultado(passou, motivo)
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
