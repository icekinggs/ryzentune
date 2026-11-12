"""Ponto de entrada.

  RyzenTune.exe                          abre o app
  RyzenTune.exe --boot                   rotina da tarefa agendada (sem janela)
  RyzenTune.exe --instalar-tarefa / --remover-tarefa      usados pelo instalador
  RyzenTune.exe --diagnostico <arquivo>  lê o hardware e grava um relatório JSON
  RyzenTune.exe --autoteste              usado pelo build
  (internos) --teste-memoria MB MIN / --teste-nucleo CPU SEG REF
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import traceback

from . import sistema
from .versao import NOME, __version__


class _IO:
    """Ligação real da rotina de boot com o hardware."""
    log = sistema.log
    velocidade_ram = staticmethod(sistema.velocidade_ram)
    eventos_desde = staticmethod(sistema.eventos_desde)

    @staticmethod
    def nome_cpu():
        return sistema.ps("(Get-CimInstance Win32_Processor|Select -First 1).Name").strip()

    @staticmethod
    def ler_timings():
        try:
            from .zen import Zen
            with Zen() as z:
                return z.timings()
        except Exception as ex:
            sistema.log.warning("boot: não consegui ler os timings: %s", ex)
            return None

    @staticmethod
    def aplicar_co(valor):
        try:
            from .zen import Zen
            with Zen() as z:
                z.aplicar_co_todos(valor)
                lido = z.ler_co()
            sistema.log.info("Curve Optimizer %s aplicado; leitura por núcleo: %s", valor, lido)
            return True
        except Exception:
            sistema.log.error("falha ao aplicar o Curve Optimizer:\n%s", traceback.format_exc())
            return False


def _aviso(msg):
    try:
        ctypes.windll.user32.MessageBoxW(None, msg, NOME, 0x10)
    except (OSError, AttributeError):
        print(msg, file=sys.stderr)


def _autoteste(log) -> int:
    try:
        import numpy  # noqa: F401
        import webview  # noqa: F401

        from . import api, boot, estado, hardware, motor, testes, zen  # noqa: F401
        assert motor.validar_perfil(motor.PADRAO_MEM) == []
        assert hardware.classificar_cpu("AMD Ryzen 7 5700X3D 8-Core Processor", 8).suporta_co
        assert testes.carga_referencia() == testes.carga_referencia()
        for arq in ("index.html", "estilo.css", "app.js"):
            assert os.path.isfile(os.path.join(_pasta_web(), arq)), arq
        for arq in ("AMDFamily17.bin", "RyzenSMU.bin"):
            from .pawnio import pasta_recursos
            assert os.path.isfile(os.path.join(pasta_recursos(), "pawnio", arq)), arq
        estado.carregar()
        log.info("autoteste ok %s", __version__)
        return 0
    except Exception:
        log.error("autoteste falhou:\n%s", traceback.format_exc())
        return 3


def _diagnostico(destino: str) -> int:
    from . import pawnio
    r = {"versao": __version__, "admin": sistema.eh_admin(), "hw": sistema.ler_hardware(),
         "pawnio": {"pasta": pawnio.pasta_instalacao(), "versao": pawnio.versao_instalada()}}
    try:
        from .zen import Zen
        with Zen() as z:
            r["codinome"] = z.codinome()
            for nome, fn in (("timings", z.timings), ("pm", z.tabela_energia), ("temp", z.temperatura),
                             ("nucleos", z.nucleos_ativos if z.suporta_co() else lambda: None),
                             ("co", z.ler_co)):
                try:
                    r[nome] = fn()
                except Exception as ex:
                    r[nome + "_erro"] = repr(ex)
    except Exception as ex:
        r["erro"] = repr(ex)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2, default=str)
    return 0


def _pasta_web():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "ryzentune", "web") if getattr(sys, "frozen", False) else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # trabalhadores de teste: rápidos, sem log de arquivo
    if argv[:1] == ["--teste-memoria"]:
        from .testes import trabalhador_memoria
        return trabalhador_memoria(int(argv[1]), float(argv[2]))
    if argv[:1] == ["--teste-referencia"]:
        from .testes import trabalhador_referencia
        return trabalhador_referencia()
    if argv[:1] == ["--teste-nucleo"]:
        from .testes import trabalhador_nucleo
        return trabalhador_nucleo(int(argv[1]), float(argv[2]), argv[3])

    log = sistema.configurar_log()
    if "--versao" in argv:
        print(__version__)
        return 0
    if "--instalar-tarefa" in argv:
        ok, _ = sistema.criar_tarefa()
        return 0 if ok else 1
    if "--remover-tarefa" in argv:
        sistema.remover_tarefa()
        return 0
    if "--autoteste" in argv:
        return _autoteste(log)
    if "--diagnostico" in argv:
        i = argv.index("--diagnostico")
        destino = argv[i + 1] if len(argv) > i + 1 else os.path.join(os.getcwd(), "ryzentune-diagnostico.json")
        return _diagnostico(destino)
    if "--boot" in argv:
        from . import boot
        try:
            log.info("rotina de boot %s", __version__)
            boot.rotina(_IO)
        except Exception:  # nunca pode atrapalhar o boot
            log.error("erro na rotina de boot:\n%s", traceback.format_exc())
            return 1
        return 0

    # ---------------- janela (precisa de Administrador: driver, tarefa agendada, reinício na BIOS)
    if not sistema.eh_admin():
        exe, base = sistema.comando_app()
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, base, os.getcwd(), 1)
        if r > 32:
            return 0
        _aviso(f"O {NOME} precisa de permissão de Administrador para acessar o hardware.")
        return 1
    trava = sistema.InstanciaUnica()
    if trava.ja_existe:
        _aviso(f"O {NOME} já está aberto.")
        return 0
    try:
        import webview

        from .api import Api
        api = Api()
        janela = webview.create_window(
            NOME, url=os.path.join(_pasta_web(), "index.html"), js_api=api,
            width=1240, height=800, min_size=(980, 660), background_color="#0B0D12")
        api._janela = janela
        log.info("janela aberta %s", __version__)
        webview.start(gui="edgechromium", private_mode=True, storage_path=None, debug="--debug" in argv)
    except Exception:
        log.error("erro fatal:\n%s", traceback.format_exc())
        _aviso("Erro inesperado ao abrir a janela. Detalhes no log em %LOCALAPPDATA%\\RyzenTune.")
        return 1
    return 0
