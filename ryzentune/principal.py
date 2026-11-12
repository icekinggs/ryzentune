"""Ponto de entrada.

  RyzenTune.exe                  abre a janela
  RyzenTune.exe --boot           rotina da tarefa agendada (sem janela)
  RyzenTune.exe --instalar-tarefa / --remover-tarefa   usados pelo instalador
  RyzenTune.exe --versao
"""
from __future__ import annotations

import ctypes
import os
import sys
import traceback

from . import sistema
from .versao import NOME, __version__


class _IO:
    log = sistema.log
    velocidade_ram = staticmethod(sistema.velocidade_ram)
    eventos_desde = staticmethod(sistema.eventos_desde)
    rodar_pbo2 = staticmethod(sistema.rodar_pbo2)

    @staticmethod
    def nome_cpu():
        return sistema.ps("(Get-CimInstance Win32_Processor|Select -First 1).Name").strip()


def _aviso(msg):
    try:
        ctypes.windll.user32.MessageBoxW(None, msg, NOME, 0x10)
    except (OSError, AttributeError):
        print(msg, file=sys.stderr)


def _autoteste(log) -> int:
    try:
        import tkinter

        from . import atualizador, boot, estado, hardware, janela, motor  # noqa: F401
        raiz = tkinter.Tk()
        raiz.withdraw()
        raiz.update()
        raiz.destroy()
        assert motor.validar_perfil(motor.PADRAO_MEM) == []
        assert hardware.classificar_cpu("AMD Ryzen 7 5700X3D 8-Core Processor", 8).suporta_co
        estado.carregar()
        log.info("autoteste ok %s", __version__)
        return 0
    except Exception:
        log.error("autoteste falhou:\n%s", traceback.format_exc())
        return 3


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    log = sistema.configurar_log()

    if "--versao" in argv:
        print(__version__)
        return 0
    if "--instalar-tarefa" in argv:
        ok, msg = sistema.criar_tarefa()
        return 0 if ok else 1
    if "--remover-tarefa" in argv:
        sistema.remover_tarefa()
        return 0
    if "--boot" in argv:
        from . import boot
        try:
            log.info("rotina de boot %s", __version__)
            boot.rotina(_IO)
        except Exception:  # nunca pode atrapalhar o boot
            log.error("erro na rotina de boot:\n%s", traceback.format_exc())
            return 1
        return 0

    if "--autoteste" in argv:  # usado pelo build: o executável empacotado abre e fecha a janela
        return _autoteste(log)

    # ---------------- janela (precisa de Administrador: tarefa agendada, reinício na BIOS, eventos)
    if not sistema.eh_admin():
        exe, base = sistema.comando_app()
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, base, os.getcwd(), 1)
        if r > 32:
            return 0
        _aviso(f"O {NOME} precisa de permissão de Administrador para funcionar.")
        return 1
    trava = sistema.InstanciaUnica()
    if trava.ja_existe:
        _aviso(f"O {NOME} já está aberto.")
        return 0
    try:
        from .janela import Janela
        log.info("janela aberta %s", __version__)
        Janela().mainloop()
    except Exception:
        log.error("erro fatal:\n%s", traceback.format_exc())
        _aviso("Erro inesperado. Detalhes no log (menu Ajuda → Abrir pasta de dados).")
        return 1
    return 0
