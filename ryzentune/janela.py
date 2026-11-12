"""Interface gráfica (tkinter)."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import atualizador, estado, hardware, motor, sistema
from .versao import NOME, __version__

log = sistema.log

LINKS = {
    "ZenTimings (ler os timings atuais)": "https://zentimings.protonrom.com/",
    "TestMem5 (teste de memória)": "https://testmem.tz.ru/",
    "CoreCycler (teste do Curve Optimizer)": "https://github.com/sp00n/corecycler",
}


class Janela(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{NOME} {__version__}")
        self.geometry("1060x720")
        self.minsize(920, 620)
        self.report_callback_exception = self._erro_tk
        try:
            self.iconbitmap(default=_icone())
        except tk.TclError:
            pass
        st = ttk.Style(self)
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        st.configure("Titulo.TLabel", font=("Segoe UI", 12, "bold"))
        st.configure("Aviso.TLabel", foreground="#b42318")
        st.configure("Ok.TLabel", foreground="#1a7f37")
        st.configure("Banner.TFrame", background="#fff4ce")
        st.configure("Banner.TLabel", background="#fff4ce")

        self._fila = queue.Queue()
        self.after(100, self._processar_fila)
        self.e = estado.carregar()
        self.hw = None         # dicionário lido do WMI
        self.cpu_ok = False     # hardware suportado
        self.info_atualizacao = None

        self._menu()
        self.banner = ttk.Frame(self, style="Banner.TFrame", padding=6)
        self.lbl_banner = ttk.Label(self.banner, style="Banner.TLabel")
        self.lbl_banner.pack(side="left")
        self.btn_banner = ttk.Button(self.banner, text="Atualizar agora", command=self.atualizar_agora)
        self.btn_banner.pack(side="left", padx=8)
        ttk.Button(self.banner, text="Agora não", command=self.banner.pack_forget).pack(side="left")
        ttk.Button(self.banner, text="Pular esta versão", command=self.ignorar_versao).pack(side="left", padx=4)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.ab = {}
        for chave, texto in (("inicio", "Início"), ("mem", "Memória"), ("cpu", "Processador"),
                             ("hist", "Histórico")):
            f = ttk.Frame(self.nb, padding=10)
            self.nb.add(f, text=f"  {texto}  ")
            self.ab[chave] = f
        self.montar_inicio()
        self.montar_mem()
        self.montar_cpu()
        self.montar_hist()
        self.mostrar()
        threading.Thread(target=self._ler_hw, daemon=True).start()
        if self.e["config"]["verificar_atualizacao"]:
            threading.Thread(target=self._verificar_atualizacao, daemon=True).start()

    # ================================================================ infraestrutura
    def na_tela(self, fn, *args, **kwargs):
        """Agenda fn na thread da janela. Pode ser chamado de qualquer thread (tkinter não é thread-safe)."""
        self._fila.put((fn, args, kwargs))

    def _processar_fila(self):
        try:
            while True:
                fn, args, kwargs = self._fila.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as ex:
                    self._erro_tk(type(ex), ex, ex.__traceback__)
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _erro_tk(self, exc, val, tb):
        log.error("erro na janela:\n%s", "".join(traceback.format_exception(exc, val, tb)))
        messagebox.showerror(NOME, f"Algo deu errado: {val}\n\nO estado não foi alterado. "
                                   f"Detalhes em {os.path.join(estado.pasta_dados(), 'ryzentune.log')}")
        self.recarregar()

    def acao(self, fn, *args):
        """Executa fn(e, *args) dentro de uma transação e atualiza a tela."""
        try:
            with estado.transacao() as e:
                r = fn(e, *args)
        except TimeoutError:
            messagebox.showwarning(NOME, "O estado está em uso pela tarefa de boot. Tente de novo em instantes.")
            r = None
        self.recarregar()
        return r

    def recarregar(self):
        self.e = estado.carregar()
        self.mostrar()

    def registrar(self, e, tipo, texto):
        estado.registrar(e, tipo, texto, log)

    def _menu(self):
        m = tk.Menu(self)
        a = tk.Menu(m, tearoff=False)
        for nome, url in LINKS.items():
            a.add_command(label=f"Baixar {nome}", command=lambda u=url: webbrowser.open(u))
        a.add_separator()
        a.add_command(label="Verificar atualização agora", command=self.verificar_manual)
        self.var_auto = tk.BooleanVar(value=self.e["config"]["verificar_atualizacao"])
        a.add_checkbutton(label="Verificar atualização ao abrir", variable=self.var_auto,
                          command=self.trocar_auto)
        a.add_separator()
        a.add_command(label="Abrir pasta de dados (estado e log)",
                      command=lambda: os.startfile(estado.pasta_dados()))
        a.add_command(label=f"Sobre o {NOME}", command=self.sobre)
        m.add_cascade(label="Ajuda", menu=a)
        self.config(menu=m)

    def sobre(self):
        messagebox.showinfo(NOME, f"{NOME} {__version__}\n\nAssistente para achar os melhores timings de memória "
                                  "e o Curve Optimizer em Ryzen AM4.\n\nUse por sua conta e risco: overclock "
                                  "pode causar instabilidade e perda de dados não salvos.")

    def trocar_auto(self):
        v = self.var_auto.get()
        self.acao(lambda e: e["config"].__setitem__("verificar_atualizacao", v))

    # ================================================================ hardware
    def _ler_hw(self):
        hw = sistema.ler_hardware()
        self.na_tela(self._hw_lido, hw)

    def _hw_lido(self, hw):
        self.hw = hw
        if not hw:
            self.lbl_hw.config(text="Não consegui ler o hardware (WMI). Feche e abra de novo.", style="Aviso.TLabel")
            return
        perfil = hardware.classificar_cpu(hw.get("cpu", ""), hw.get("nucleos", 0))
        fab = hardware.fabricante_placa(hw.get("placa_fab", ""))
        self.cpu_ok = perfil.am4

        def aplicar(e):
            antigo = e["cpu"]["perfil"]
            if antigo.get("nome") and antigo["nome"] != perfil.nome:
                self.registrar(e, "CPU", f"Processador trocado ({antigo['nome']} → {perfil.nome}). "
                                         "Curve Optimizer zerado.")
                e["cpu"].update(estavel=0, teste=None, feito=False)
            e["cpu"]["perfil"] = perfil.to_dict()
            e["config"]["placa"] = fab
        self.acao(aplicar)

        txt = (f"Processador: {perfil.nome}  ({perfil.nucleos} núcleos, {perfil.geracao.upper()}"
               f"{', X3D' if perfil.x3d else ''}{', APU' if perfil.apu else ''})\n"
               f"Placa-mãe: {hw.get('placa_fab', '')} {hw.get('placa', '')}  -  BIOS {hw.get('bios', '')}\n"
               f"Memória: {hw.get('pentes')} pente(s), {hw.get('gb')} GB  {hw.get('modelo_ram', '')}  -  "
               f"rodando a {hw.get('ram_mts')} MT/s")
        estilo = "TLabel"
        if not perfil.am4:
            txt += ("\n\n⚠ Este processador não é um Ryzen AM4 (DDR4). O RyzenTune foi feito para Ryzen "
                    "1000 a 5000; os assistentes ficam desativados.")
            estilo = "Aviso.TLabel"
        elif fab == "Outra":
            txt += "\n\n⚠ Marca de placa não reconhecida: os nomes dos menus da BIOS podem ser diferentes."
        self.lbl_hw.config(text=txt, style=estilo)
        threading.Thread(target=self._ler_travamentos, daemon=True).start()
        self.mostrar()

    def _ler_travamentos(self):
        import datetime as dt
        inicio = (dt.datetime.now() - dt.timedelta(days=14)).replace(microsecond=0).isoformat()
        k41, whea = sistema.eventos_desde(inicio)
        self.na_tela(self._travamentos_lidos, k41, whea)

    def _travamentos_lidos(self, k41, whea):
        if k41 > 0 or whea > 0:
            self.lbl_trav.config(text=(
                f"⚠ Nos últimos 14 dias o Windows registrou {k41} desligamento(s) forçado(s) e {whea} erro(s) "
                "de hardware (WHEA). Se isso aconteceu sem overclock, resolva antes: senão não dá para saber "
                "se uma falha veio do ajuste."), style="Aviso.TLabel")
        elif k41 == 0:
            self.lbl_trav.config(text="✔ Nenhum travamento nem erro de hardware nos últimos 14 dias.",
                                 style="Ok.TLabel")

    # ================================================================ atualização
    def _verificar_atualizacao(self, manual=False):
        try:
            info = atualizador.verificar()
            erro = None
        except Exception as ex:  # rede, GitHub fora etc.
            info, erro = None, ex
            log.info("verificação de atualização falhou: %r", ex)
        self.na_tela(self._atualizacao_lida, info, erro, manual)

    def _atualizacao_lida(self, info, erro, manual):
        if info and (manual or info["versao"] != self.e["config"].get("versao_ignorada")):
            self.info_atualizacao = info
            self.lbl_banner.config(text=f"Nova versão {info['versao']} disponível (você tem {__version__}).")
            self.btn_banner.state(["!disabled"])
            self.banner.pack(fill="x", before=self.nb)
        elif manual:
            if erro:
                messagebox.showwarning(NOME, f"Não consegui verificar: {erro}")
            elif not atualizador.repo_configurado():
                messagebox.showinfo(NOME, "Esta é uma versão de desenvolvimento (sem repositório configurado).")
            else:
                messagebox.showinfo(NOME, f"Você já tem a versão mais nova ({__version__}).")

    def verificar_manual(self):
        threading.Thread(target=self._verificar_atualizacao, args=(True,), daemon=True).start()

    def ignorar_versao(self):
        if self.info_atualizacao:
            v = self.info_atualizacao["versao"]
            self.acao(lambda e: e["config"].__setitem__("versao_ignorada", v))
        self.banner.pack_forget()

    def atualizar_agora(self):
        info = self.info_atualizacao
        if not info:
            return
        notas = info["notas"].strip()[:1500]
        if not messagebox.askyesno(NOME, f"Instalar a versão {info['versao']}?\n\n{notas}\n\n"
                                         "O RyzenTune vai fechar e abrir de novo. Seus dados ficam."):
            return
        self.btn_banner.state(["disabled"])
        self.lbl_banner.config(text="Baixando…")

        def baixar():
            try:
                caminho = atualizador.baixar(info, lambda p: self.na_tela(
                    self.lbl_banner.config, text=f"Baixando… {p:.0%}"))
                self.na_tela(self._instalar, caminho)
            except Exception as ex:
                log.error("download da atualização falhou: %r", ex)
                self.na_tela(self._falha_atualizacao, str(ex))
        threading.Thread(target=baixar, daemon=True).start()

    def _falha_atualizacao(self, msg):
        self.btn_banner.state(["!disabled"])
        self.lbl_banner.config(text="A atualização falhou.")
        messagebox.showerror(NOME, f"A atualização falhou: {msg}")

    def _instalar(self, caminho):
        log.info("instalando atualização %s", caminho)
        atualizador.instalar(caminho)
        self.destroy()

    # ================================================================ Início
    def montar_inicio(self):
        f = self.ab["inicio"]
        ttk.Label(f, text="Hardware", style="Titulo.TLabel").pack(anchor="w")
        self.lbl_hw = ttk.Label(f, text="Lendo o hardware…", justify="left", wraplength=1000)
        self.lbl_hw.pack(anchor="w", pady=(2, 4))
        self.lbl_trav = ttk.Label(f, text="", justify="left", wraplength=1000)
        self.lbl_trav.pack(anchor="w", pady=(0, 10))

        ttk.Label(f, text="Como funciona", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(f, justify="left", wraplength=1000, text=(
            "• Nada muda na hora: tudo vale a partir do próximo boot. Memória: você digita na BIOS os valores "
            "mostrados (o app reinicia direto nela). Processador: o Curve Optimizer é aplicado pela tarefa de "
            "boot.\n"
            "• Um ajuste por vez. Passou no teste → o app vai um passo mais longe. Falhou → volta ao último "
            "estável e passa para o próximo ajuste.\n"
            "• Se a memória não ligar, a placa volta ao padrão (ou limpe o CMOS): o app percebe que a "
            "velocidade não bate e marca a falha.\n"
            "• Se o PC travar com o Curve Optimizer, o app vê o registro do Windows e não reaplica o valor.\n"
            "• Teste uma coisa de cada vez: memória OU processador.")).pack(anchor="w", pady=(2, 10))

        ttk.Label(f, text="Ferramentas (menu Ajuda tem os links)", style="Titulo.TLabel").pack(anchor="w")
        g = ttk.Frame(f)
        g.pack(anchor="w", fill="x", pady=4)
        g.columnconfigure(0, weight=1)
        self.var_tm5 = tk.StringVar()
        self.var_cc = tk.StringVar()
        self.var_pbo = tk.StringVar()
        linhas = [
            ("TestMem5 (TM5.exe), use a configuração 'anta777 extreme'", self.var_tm5),
            ("CoreCycler (Run CoreCycler.bat)", self.var_cc),
            ("PBO2 Tuner (PBO2 tuner.exe), só para o Curve Optimizer", self.var_pbo),
        ]
        for i, (txt, var) in enumerate(linhas):
            ttk.Label(g, text=txt).grid(row=i * 2, column=0, columnspan=2, sticky="w", pady=(6, 0))
            en = ttk.Entry(g, textvariable=var)
            en.grid(row=i * 2 + 1, column=0, sticky="we")
            en.bind("<FocusOut>", lambda _e: self.salvar_ferramentas())
            ttk.Button(g, text="Procurar…", command=lambda v=var: self.procurar(v)).grid(
                row=i * 2 + 1, column=1, padx=4)

        ttk.Label(f, text="Tarefa de boot", style="Titulo.TLabel").pack(anchor="w", pady=(12, 0))
        h = ttk.Frame(f)
        h.pack(anchor="w", pady=4)
        self.lbl_tarefa = ttk.Label(h, text="")
        self.lbl_tarefa.pack(side="left")
        ttk.Button(h, text="Reinstalar", command=self.instalar_tarefa).pack(side="left", padx=8)

    def procurar(self, var):
        p = filedialog.askopenfilename(filetypes=[("Programas", "*.exe *.bat *.cmd"), ("Todos", "*.*")])
        if p:
            var.set(os.path.normpath(p))
            self.salvar_ferramentas()

    def salvar_ferramentas(self):
        tm5, cc, pbo = (v.get().strip() for v in (self.var_tm5, self.var_cc, self.var_pbo))
        if (tm5, cc, pbo) == (self.e["ferramentas"]["tm5"], self.e["ferramentas"]["corecycler"],
                              self.e["cpu"]["pbo2"]):
            return

        def f(e):
            e["ferramentas"]["tm5"], e["ferramentas"]["corecycler"], e["cpu"]["pbo2"] = tm5, cc, pbo
        self.acao(f)

    def instalar_tarefa(self):
        ok, msg = sistema.criar_tarefa()
        if not ok:
            messagebox.showerror(NOME, f"Não consegui criar a tarefa:\n{msg}")
        self.mostrar()

    # ================================================================ Memória
    def montar_mem(self):
        f = self.ab["mem"]
        esq = ttk.LabelFrame(f, text=" Último perfil estável ", padding=8)
        esq.pack(side="left", fill="y")
        self.ent_mem = {}
        for i, (k, nome, un) in enumerate(motor.CAMPOS):
            ttk.Label(esq, text=nome).grid(row=i, column=0, sticky="w")
            v = tk.StringVar()
            en = ttk.Entry(esq, textvariable=v, width=8)
            en.grid(row=i, column=1, padx=4, pady=1)
            ttk.Label(esq, text=un).grid(row=i, column=2, sticky="w")
            self.ent_mem[k] = (v, en)
        self.btn_base = ttk.Button(esq, text="Salvar como ponto de partida", command=self.salvar_base)
        self.btn_base.grid(row=len(motor.CAMPOS), column=0, columnspan=3, pady=(8, 0), sticky="we")
        self.lbl_base = ttk.Label(esq, text="", wraplength=260)
        self.lbl_base.grid(row=len(motor.CAMPOS) + 1, column=0, columnspan=3, sticky="w", pady=4)

        d = ttk.Frame(f, padding=(12, 0, 0, 0))
        d.pack(side="left", fill="both", expand=True)
        ttk.Label(d, text="Próxima etapa", style="Titulo.TLabel").pack(anchor="w")
        self.txt_mem = tk.Text(d, height=20, wrap="word", font=("Consolas", 10), relief="flat",
                               background="#f6f6f6")
        self.txt_mem.pack(fill="both", expand=True, pady=4)
        b = ttk.Frame(d)
        b.pack(fill="x")
        self.bm = {}
        for chave, texto, cmd in (
                ("preparar", "1. Preparar etapa", self.mem_preparar),
                ("bios", "2. Reiniciar na BIOS", self.mem_bios),
                ("ja", "Já apliquei e reiniciei", self.mem_ja),
                ("tm5", "3. Abrir TestMem5", lambda: abrir(self.e["ferramentas"]["tm5"], "TestMem5")),
                ("ok", "✔ Passou", self.mem_passou),
                ("falha", "✖ Falhou", self.mem_falhou),
                ("pular", "Pular ajuste", self.mem_pular),
                ("cancelar", "Cancelar etapa", self.mem_cancelar)):
            self.bm[chave] = ttk.Button(b, text=texto, command=cmd)
            self.bm[chave].pack(side="left", padx=2, pady=2)
        ttk.Button(d, text="Recomeçar a busca (mantém o estável)", command=self.mem_recomecar).pack(anchor="w", pady=4)

    def salvar_base(self):
        novo = {}
        for k, nome, _ in motor.CAMPOS:
            txt = self.ent_mem[k][0].get().strip().replace(",", ".")
            try:
                novo[k] = round(float(txt), 3) if k in motor.DECIMAIS else int(float(txt))
            except ValueError:
                messagebox.showerror(NOME, f"Valor inválido em {nome}: {txt!r}")
                return
        if not self.e["cpu"]["perfil"].get("tem_fclk", True):
            novo["fclk"] = 0
        erros = motor.validar_perfil(novo)
        if erros:
            messagebox.showerror(NOME, "Confira:\n" + "\n".join(erros))
            return
        if novo["vdram"] > motor.VDRAM_SEGURA or novo["vsoc"] > motor.VSOC_MAX:
            if not messagebox.askyesno(NOME, "Tensão acima do recomendado para uso diário. Salvar mesmo assim?"):
                return

        def f(e):
            e["mem"].update(estavel=novo, confirmado=True, feitos=[], mais_tensao=False, teste=None)
            self.registrar(e, "Memória", f"Ponto de partida: {novo['freq']} MT/s CL{novo['tCL']}-{novo['tRCDRD']}-"
                                         f"{novo['tRP']}-{novo['tRAS']} tRFC {novo['tRFC']}.")
        self.acao(f)

    def texto_etapa(self, t):
        est = self.e["mem"]["estavel"]
        perfil = t["perfil"]
        onde, se_falhar = hardware.CAMINHO_BIOS.get(self.e["config"].get("placa", "Outra"),
                                                    hardware.CAMINHO_BIOS["Outra"])
        tem_fclk = self.e["cpu"]["perfil"].get("tem_fclk", True)
        lin = [f"Ajuste: {motor.DESCR_ETAPA[t['passo']]}", "", "Na BIOS: " + onde, "",
               f"  {'Campo':<28}{'Atual':>9}{'Novo':>9}"]
        for k, nome, un in motor.CAMPOS:
            if k == "fclk" and not tem_fclk:
                continue
            if perfil[k] != est[k]:
                lin.append(f"→ {nome:<26}{est[k]:>9}{perfil[k]:>9}  {un}")
        lin += ["", "Todos os outros campos: deixe como estão.", se_falhar,
                f"\ntRFC estável: {motor.ns_trfc(est):.0f} ns   nesta etapa: {motor.ns_trfc(perfil):.0f} ns", ""]
        lin.append({
            "preparada": "Situação: PREPARADA. Clique em 'Reiniciar na BIOS' (ou reinicie e aperte DEL).",
            "aplicada": "Situação: APLICADA. Ao voltar ao Windows o app confere se a placa aceitou.",
            "testar": ("Situação: LIGOU. Rode o TestMem5 (anta777 extreme, 3 ciclos ≈ 30-60 min).\n"
                       "Qualquer erro = Falhou. Sem erros = Passou."),
        }[t["situacao"]])
        return "\n".join(lin)

    def mem_preparar(self):
        if not self.e["mem"]["confirmado"]:
            messagebox.showwarning(NOME, "Primeiro confira os valores atuais (ZenTimings ou BIOS), corrija à "
                                         "esquerda e clique em 'Salvar como ponto de partida'.")
            return
        if self.e["cpu"]["teste"]:
            messagebox.showwarning(NOME, "Há um teste de Curve Optimizer em andamento. Teste uma coisa de cada vez.")
            return

        def f(e):
            passo = motor.preparar_mem(e)
            if passo:
                self.registrar(e, "Memória", f"Etapa preparada: {motor.DESCR_ETAPA[passo]}.")
            return passo
        if not self.acao(f):
            messagebox.showinfo(NOME, "Busca concluída: não há mais ajustes a testar. O perfil à esquerda é o "
                                      "seu melhor estável.")

    def mem_bios(self):
        if not sistema.tarefa_ok() and not messagebox.askyesno(
                NOME, "A tarefa de boot não está instalada, então o app não vai conferir sozinho se a placa "
                      "aceitou. Continuar?"):
            return
        if not messagebox.askyesno(NOME, "Salve seus trabalhos. O PC vai reiniciar direto na BIOS em 5 segundos.\n"
                                         "Fotografe a tabela de valores antes. Continuar?"):
            return

        def f(e):
            motor.marcar_aplicada_mem(e)
            self.registrar(e, "Memória", "Reiniciando na BIOS para aplicar a etapa.")
        self.acao(f)
        ok, msg = sistema.reiniciar(bios=True)
        if not ok:
            self.acao(lambda e: e["mem"]["teste"].__setitem__("situacao", "preparada"))
            messagebox.showerror(NOME, f"Não consegui reiniciar direto na BIOS ({msg}).\n"
                                       "Reinicie você mesmo, aperte DEL e depois use 'Já apliquei e reiniciei'.")

    def mem_ja(self):
        vel = sistema.velocidade_ram()

        def f(e):
            t = e["mem"]["teste"]
            if not t:
                return
            if t["situacao"] == "preparada":
                motor.marcar_aplicada_mem(e)
            if vel and abs(vel - t["perfil"]["freq"]) > 10:
                self.registrar(e, "Memória", motor.falhar_mem(e, f"a memória está a {vel} MT/s"))
                return f"A memória está a {vel} MT/s, não a {t['perfil']['freq']}. Etapa marcada como falha."
            t["situacao"] = "testar"
        msg = self.acao(f)
        if msg:
            messagebox.showwarning(NOME, msg)

    def mem_passou(self):
        t = self.e["mem"]["teste"]
        k41, whea = sistema.eventos_desde(t["desde"])
        if k41 > 0 or whea > 0:
            messagebox.showwarning(NOME, f"Houve {k41} desligamento(s) forçado(s) e {whea} erro(s) WHEA desde que "
                                         "a etapa foi aplicada. Ela será marcada como falha.")
            self.acao(lambda e: self.registrar(e, "Memória", motor.falhar_mem(e, "travamento/erro WHEA")))
            return
        self.acao(lambda e: self.registrar(e, "Memória", motor.passar_mem(e)))

    def mem_falhou(self):
        if messagebox.askyesno(NOME, "Marcar como falha?\n\nDepois volte na BIOS e coloque os valores do perfil "
                                     "estável (à esquerda), ou já aplique a próxima etapa, que parte dele."):
            self.acao(lambda e: self.registrar(e, "Memória", motor.falhar_mem(e, "erro no teste")))

    def mem_pular(self):
        self.acao(lambda e: self.registrar(e, "Memória", motor.pular_mem(e)))

    def mem_cancelar(self):
        def f(e):
            e["mem"]["teste"] = None
            self.registrar(e, "Memória", "Etapa cancelada.")
        self.acao(f)

    def mem_recomecar(self):
        if self.e["mem"]["teste"]:
            messagebox.showwarning(NOME, "Termine ou cancele a etapa atual primeiro.")
            return

        def f(e):
            e["mem"].update(feitos=[], mais_tensao=False)
            self.registrar(e, "Memória", "Busca recomeçada a partir do estável.")
        self.acao(f)

    # ================================================================ Processador
    def montar_cpu(self):
        f = self.ab["cpu"]
        ttk.Label(f, text="Curve Optimizer (todos os núcleos)", style="Titulo.TLabel").pack(anchor="w")
        self.lbl_cpu_info = ttk.Label(f, justify="left", wraplength=1000)
        self.lbl_cpu_info.pack(anchor="w", pady=4)
        g = ttk.Frame(f)
        g.pack(anchor="w", pady=6)
        ttk.Label(g, text="Argumentos do PBO2 Tuner ({todos} = o valor repetido para cada núcleo):").grid(
            row=0, column=0, sticky="w")
        self.var_args = tk.StringVar()
        ttk.Entry(g, textvariable=self.var_args, width=40).grid(row=0, column=1, padx=6)
        ttk.Button(g, text="Salvar", command=self.salvar_args).grid(row=0, column=2)

        self.lbl_cpu = ttk.Label(f, text="", font=("Segoe UI", 11), justify="left")
        self.lbl_cpu.pack(anchor="w", pady=10)
        b = ttk.Frame(f)
        b.pack(anchor="w")
        self.bc = {}
        for chave, texto, cmd in (
                ("preparar", "1. Preparar próximo valor", self.cpu_preparar),
                ("reiniciar", "2. Reiniciar agora", self.cpu_reiniciar),
                ("cc", "3. Abrir CoreCycler", lambda: abrir(self.e["ferramentas"]["corecycler"], "CoreCycler")),
                ("ok", "✔ Passou (1-2 dias sem problema)", self.cpu_passou),
                ("falha", "✖ Falhou", self.cpu_falhou),
                ("cancelar", "Cancelar teste", self.cpu_cancelar)):
            self.bc[chave] = ttk.Button(b, text=texto, command=cmd)
            self.bc[chave].pack(side="left", padx=2)
        b2 = ttk.Frame(f)
        b2.pack(anchor="w", pady=8)
        ttk.Button(b2, text="Zerar Curve Optimizer (volta a 0 no próximo boot)",
                   command=self.cpu_zerar).pack(side="left", padx=2)
        ttk.Button(b2, text="Recomeçar a busca", command=self.cpu_recomecar).pack(side="left", padx=2)

    def texto_cpu_info(self):
        p = self.e["cpu"]["perfil"]
        if not p:
            return "Lendo o processador…"
        if not p.get("am4"):
            return "Processador não suportado."
        if not p.get("suporta_co"):
            return (f"O Curve Optimizer só existe no Ryzen 5000 (Zen 3). No seu {p['nome']} use o PBO pela "
                    "BIOS ou foque na memória, que costuma render mais nessa geração.")
        base = ("Um Curve Optimizer negativo baixa a tensão: o processador esquenta menos e segura o boost "
                "por mais tempo. Ele é aplicado pelo PBO2 Tuner na tarefa de boot e some ao desligar, então "
                "um valor ruim nunca impede o PC de ligar.\n"
                "Instabilidade costuma aparecer com o PC parado ou em carga leve. Teste com o CoreCycler por "
                "~1 h e use o PC normalmente por 1-2 dias antes de marcar Passou.")
        if p.get("x3d"):
            base = ("Processadores X3D têm o multiplicador travado: não dá para subir o clock à força. " + base +
                    "\nSe a BIOS tiver 'Kombo Strike' (MSI) ou um Curve Optimizer próprio, ela pode substituir o "
                    "PBO2 Tuner.")
        return base

    def salvar_args(self):
        a = self.var_args.get().strip()
        if "{todos}" not in a and "{c}" not in a:
            messagebox.showerror(NOME, "Os argumentos precisam ter {todos} ou {c}.")
            return
        self.acao(lambda e: e["cpu"].__setitem__("args", a))

    def cpu_preparar(self):
        self.salvar_ferramentas()
        c = self.e["cpu"]
        if not c["pbo2"] or not os.path.isfile(c["pbo2"]):
            messagebox.showwarning(NOME, "Aponte o PBO2 Tuner na aba Início.")
            return
        if not sistema.tarefa_ok():
            messagebox.showwarning(NOME, "A tarefa de boot não está instalada. Clique em 'Reinstalar' na aba Início.")
            return
        if self.e["mem"]["teste"]:
            messagebox.showwarning(NOME, "Há uma etapa de memória em andamento. Teste uma coisa de cada vez.")
            return

        def f(e):
            v = motor.preparar_cpu(e)
            if v is not None:
                self.registrar(e, "CPU", f"Curve Optimizer {v} preparado para o próximo boot.")
            return v
        if self.acao(f) is None:
            messagebox.showinfo(NOME, f"Busca concluída. Melhor valor estável: {self.e['cpu']['estavel']}.")

    def cpu_reiniciar(self):
        if messagebox.askyesno(NOME, "Salve seus trabalhos. Reiniciar em 5 segundos?"):
            ok, msg = sistema.reiniciar(bios=False)
            if not ok:
                messagebox.showerror(NOME, msg)

    def cpu_passou(self):
        t = self.e["cpu"]["teste"]
        k41, whea = sistema.eventos_desde(t["desde"])
        if k41 > 0 or whea > 0:
            self.acao(lambda e: self.registrar(e, "CPU", motor.falhar_cpu(
                e, f"{k41} desligamento(s) forçado(s) e {whea} erro(s) WHEA")))
            messagebox.showwarning(NOME, "O Windows registrou travamento ou erro WHEA. Marcado como falha.")
            return
        self.acao(lambda e: self.registrar(e, "CPU", motor.passar_cpu(e)))

    def cpu_falhou(self):
        if messagebox.askyesno(NOME, "Marcar como falha? No próximo boot volta para o último estável."):
            self.acao(lambda e: self.registrar(e, "CPU", motor.falhar_cpu(e, "marcado pelo usuário")))

    def cpu_cancelar(self):
        def f(e):
            e["cpu"]["teste"] = None
            self.registrar(e, "CPU", "Teste cancelado; o próximo boot usa o último estável.")
        self.acao(f)

    def cpu_zerar(self):
        def f(e):
            e["cpu"].update(estavel=0, teste=None, feito=False)
            self.registrar(e, "CPU", "Curve Optimizer zerado. Vale a partir do próximo boot.")
        self.acao(f)

    def cpu_recomecar(self):
        self.acao(lambda e: e["cpu"].__setitem__("feito", False))

    # ================================================================ Histórico
    def montar_hist(self):
        f = self.ab["hist"]
        self.lst = tk.Listbox(f, font=("Consolas", 10))
        sb = ttk.Scrollbar(f, command=self.lst.yview)
        self.lst.config(yscrollcommand=sb.set)
        self.lst.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

    # ================================================================ tela
    def mostrar(self):
        e = self.e
        on = lambda w, c: w.state(["!disabled"] if c else ["disabled"])  # noqa: E731
        self.lbl_tarefa.config(text="Instalada ✔" if sistema.tarefa_ok() else
                               "Não instalada ou apontando para outro lugar (clique em Reinstalar)")
        for var, valor in ((self.var_tm5, e["ferramentas"]["tm5"]), (self.var_cc, e["ferramentas"]["corecycler"]),
                           (self.var_pbo, e["cpu"]["pbo2"]), (self.var_args, e["cpu"]["args"])):
            if self.focus_get() is None or var.get() == "":
                var.set(valor)

        perfil_cpu = e["cpu"]["perfil"]
        liberado = bool(perfil_cpu) and perfil_cpu.get("am4", False)

        m, t = e["mem"], e["mem"]["teste"]
        for k, _, _ in motor.CAMPOS:
            var, en = self.ent_mem[k]
            var.set(str(m["estavel"][k]))
            on(en, not t)
        on(self.btn_base, not t)
        self.lbl_base.config(text="✔ Conferido" if m["confirmado"] else
                             "⚠ Valores de exemplo (XMP 3200 CL16). Confira no ZenTimings, corrija e salve.",
                             style="Ok.TLabel" if m["confirmado"] else "Aviso.TLabel")
        self.txt_mem.config(state="normal")
        self.txt_mem.delete("1.0", "end")
        if t:
            self.txt_mem.insert("end", self.texto_etapa(t))
        else:
            feitos = ", ".join(motor.DESCR_ETAPA[p] for p in m["feitos"]) or "nenhum"
            self.txt_mem.insert("end", "Nenhuma etapa em andamento. Clique em 'Preparar etapa'.\n\n"
                                       f"Ajustes com limite já encontrado: {feitos}\n\n"
                                       "Antes de começar, rode o TestMem5 com o perfil atual. Se já der erro, "
                                       "o problema não é o overclock.")
        self.txt_mem.config(state="disabled")
        sit = t["situacao"] if t else None
        on(self.bm["preparar"], liberado and not t)
        on(self.bm["bios"], sit == "preparada")
        on(self.bm["ja"], sit in ("preparada", "aplicada"))
        on(self.bm["ok"], sit == "testar")
        on(self.bm["falha"], sit in ("aplicada", "testar"))
        on(self.bm["pular"], bool(t))
        on(self.bm["cancelar"], bool(t))

        c, ct = e["cpu"], e["cpu"]["teste"]
        self.lbl_cpu_info.config(text=self.texto_cpu_info())
        txt = f"Valor estável: {c['estavel']}"
        if ct:
            txt += {"pendente": f"\nEm teste: {ct['valor']}, entra em vigor no PRÓXIMO BOOT (reinicie).",
                    "ativo": f"\nEm teste: {ct['valor']}, ATIVO desde {ct['desde'].replace('T', ' ')}. Rode o "
                             "CoreCycler e use o PC normalmente por 1-2 dias."}[ct["situacao"]]
        elif c["feito"]:
            txt += "\nBusca concluída (limite encontrado)."
        self.lbl_cpu.config(text=txt)
        co_ok = liberado and perfil_cpu.get("suporta_co", False)
        on(self.bc["preparar"], co_ok and not ct)
        on(self.bc["reiniciar"], bool(ct) and ct["situacao"] == "pendente")
        on(self.bc["ok"], bool(ct) and ct["situacao"] == "ativo")
        on(self.bc["falha"], bool(ct) and ct["situacao"] == "ativo")
        on(self.bc["cancelar"], bool(ct))

        self.lst.delete(0, "end")
        for h in reversed(e["historico"]):
            self.lst.insert("end", f"{h['quando'].replace('T', ' ')}  [{h['tipo']}]  {h['texto']}")


def abrir(caminho, nome):
    if not caminho or not os.path.exists(caminho):
        messagebox.showwarning(NOME, f"Aponte o {nome} na aba Início (o menu Ajuda tem o link para baixar).")
        return
    os.startfile(caminho)


def _icone():
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "recursos", "ryzentune.ico")
