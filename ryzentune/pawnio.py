"""Acesso ao hardware pelo driver PawnIO (assinado, de namazso) e seus módulos oficiais.

O driver é instalado pelo instalador do RyzenTune (PawnIO_setup.exe -install -silent).
Os módulos (.bin assinados, LGPL-2.1) vão dentro do app em recursos/pawnio.
API usada (PawnIOLib.h): pawnio_open, pawnio_load, pawnio_execute, pawnio_close, pawnio_version.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import winreg
from ctypes import wintypes

CHAVE_DESINSTALAR = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO"


class ErroPawnIO(Exception):
    pass


def pasta_recursos() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "recursos")


def pasta_instalacao() -> str | None:
    """Pasta do PawnIO instalado (ou None)."""
    for vista in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE_DESINSTALAR, 0, winreg.KEY_READ | vista) as k:
                local, _ = winreg.QueryValueEx(k, "InstallLocation")
                if local and os.path.isdir(local):
                    return local
        except OSError:
            continue
    padrao = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PawnIO")
    return padrao if os.path.isfile(os.path.join(padrao, "PawnIOLib.dll")) else None


def versao_instalada() -> str | None:
    for vista in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE_DESINSTALAR, 0, winreg.KEY_READ | vista) as k:
                return str(winreg.QueryValueEx(k, "DisplayVersion")[0])
        except OSError:
            continue
    return None


class TravaPCI:
    """Mutex global usado por ZenTimings, HWiNFO, LibreHardwareMonitor etc. para não colidirem no
    acesso PCI/SMN. Segurar enquanto conversa com o SMU."""

    _local = threading.RLock()

    def __init__(self, nome="Global\\Access_PCI", espera_ms=5000):
        self.nome, self.espera_ms, self.h = nome, espera_ms, None

    def __enter__(self):
        TravaPCI._local.acquire()
        k = ctypes.windll.kernel32
        k.CreateMutexW.restype = wintypes.HANDLE
        self.h = k.CreateMutexW(None, False, self.nome)
        if self.h:
            r = k.WaitForSingleObject(self.h, self.espera_ms)
            if r not in (0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED
                k.CloseHandle(self.h)
                self.h = None
                TravaPCI._local.release()
                raise ErroPawnIO("outro programa está usando o acesso ao hardware (tente de novo)")
        return self

    def __exit__(self, *a):
        k = ctypes.windll.kernel32
        if self.h:
            k.ReleaseMutex(self.h)
            k.CloseHandle(self.h)
            self.h = None
        TravaPCI._local.release()
        return False


class _Biblioteca:
    _inst = None

    def __init__(self):
        pasta = pasta_instalacao()
        if not pasta:
            raise ErroPawnIO("driver PawnIO não instalado")
        try:
            self.dll = ctypes.WinDLL(os.path.join(pasta, "PawnIOLib.dll"))
        except OSError as ex:
            raise ErroPawnIO(f"não consegui carregar PawnIOLib.dll: {ex}") from None
        d = self.dll
        d.pawnio_open.argtypes = [ctypes.POINTER(wintypes.HANDLE)]
        d.pawnio_load.argtypes = [wintypes.HANDLE, ctypes.c_char_p, ctypes.c_size_t]
        d.pawnio_execute.argtypes = [wintypes.HANDLE, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                                     ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t,
                                     ctypes.POINTER(ctypes.c_size_t)]
        d.pawnio_close.argtypes = [wintypes.HANDLE]
        d.pawnio_version.argtypes = [ctypes.POINTER(wintypes.ULONG)]
        for f in (d.pawnio_open, d.pawnio_load, d.pawnio_execute, d.pawnio_close, d.pawnio_version):
            f.restype = ctypes.c_long  # HRESULT

    @classmethod
    def obter(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst


def _ok(hr: int, oque: str):
    if hr < 0:
        raise ErroPawnIO(f"{oque} falhou (HRESULT 0x{hr & 0xFFFFFFFF:08X})")


class Modulo:
    """Um módulo PawnIO carregado (cada módulo usa o seu próprio handle)."""

    def __init__(self, nome_bin: str):
        self.lib = _Biblioteca.obter()
        caminho = os.path.join(pasta_recursos(), "pawnio", nome_bin)
        with open(caminho, "rb") as f:
            blob = f.read()
        h = wintypes.HANDLE()
        _ok(self.lib.dll.pawnio_open(ctypes.byref(h)), "pawnio_open (rode como Administrador)")
        self.h = h
        hr = self.lib.dll.pawnio_load(h, blob, len(blob))
        if hr < 0:
            self.fechar()
            _ok(hr, f"carregar {nome_bin}")
        self.nome = nome_bin

    def executar(self, funcao: str, entrada=(), n_saida: int = 0) -> list[int]:
        ent = (ctypes.c_uint64 * max(1, len(entrada)))(*[int(x) & 0xFFFFFFFFFFFFFFFF for x in entrada])
        sai = (ctypes.c_uint64 * max(1, n_saida))()
        n = ctypes.c_size_t(0)
        _ok(self.lib.dll.pawnio_execute(self.h, funcao.encode("ascii"), ent, len(entrada), sai, n_saida,
                                        ctypes.byref(n)), f"{self.nome}:{funcao}")
        return [int(sai[i]) for i in range(min(n.value, n_saida))]

    def fechar(self):
        if getattr(self, "h", None):
            self.lib.dll.pawnio_close(self.h)
            self.h = None

    def __del__(self):
        try:
            self.fechar()
        except Exception:
            pass


def versao_driver() -> str | None:
    try:
        v = wintypes.ULONG()
        if _Biblioteca.obter().dll.pawnio_version(ctypes.byref(v)) >= 0:
            x = v.value
            return f"{x >> 16}.{(x >> 8) & 0xFF}.{x & 0xFF}"
    except (ErroPawnIO, OSError):
        pass
    return None
