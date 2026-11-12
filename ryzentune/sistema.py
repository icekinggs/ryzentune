"""Tudo que conversa com o Windows: WMI, eventos, tarefa agendada, reinício."""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import logging
import logging.handlers
import os
import subprocess
import sys
import tempfile

from . import estado

SEM_JANELA = 0x08000000
TAREFA = "RyzenTune\\AplicarNoBoot"
log = logging.getLogger("ryzentune")


def configurar_log() -> logging.Logger:
    if not log.handlers:
        h = logging.handlers.RotatingFileHandler(os.path.join(estado.pasta_dados(), "ryzentune.log"),
                                                 maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log


def ps(cmd: str, timeout: int = 60) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + cmd],
                           capture_output=True, timeout=timeout, creationflags=SEM_JANELA)
        return r.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError) as ex:
        log.warning("powershell falhou: %r", ex)
        return ""


def ler_hardware() -> dict:
    s = ps("$c=Get-CimInstance Win32_Processor|Select -First 1;$b=Get-CimInstance Win32_BaseBoard;"
           "$v=Get-CimInstance Win32_BIOS;$m=@(Get-CimInstance Win32_PhysicalMemory);"
           "[pscustomobject]@{cpu=$c.Name;nucleos=$c.NumberOfCores;placa_fab=$b.Manufacturer;"
           "placa=$b.Product;bios=$v.SMBIOSBIOSVersion;pentes=$m.Count;"
           "gb=[math]::Round(($m|Measure Capacity -Sum).Sum/1GB);"
           "modelo_ram=(($m|Select -Expand PartNumber -Unique) -join ', ');"
           "ram_mts=($m|Select -First 1).ConfiguredClockSpeed}|ConvertTo-Json -Compress")
    try:
        d = json.loads(s)
        return {k: (v.strip() if isinstance(v, str) else v) for k, v in d.items()}
    except ValueError:
        return {}


def velocidade_ram() -> int:
    s = ps("(Get-CimInstance Win32_PhysicalMemory|Select -First 1).ConfiguredClockSpeed")
    try:
        return int(s)
    except ValueError:
        return 0


def eventos_desde(inicio_iso: str) -> tuple[int, int]:
    """(desligamentos forçados Kernel-Power 41, erros WHEA) desde a data. (-1,-1) se não conseguiu ler."""
    try:
        dt.datetime.fromisoformat(inicio_iso)
    except ValueError:
        return -1, -1
    data = inicio_iso.replace("T", " ")
    s = ps(f"$d=[datetime]::ParseExact('{data}','yyyy-MM-dd HH:mm:ss',$null);"
           "$k=@(Get-WinEvent -FilterHashtable @{LogName='System';Id=41;"
           "ProviderName='Microsoft-Windows-Kernel-Power';StartTime=$d} -EA SilentlyContinue).Count;"
           "$w=@(Get-WinEvent -FilterHashtable @{LogName='System';"
           "ProviderName='Microsoft-Windows-WHEA-Logger';StartTime=$d} -EA SilentlyContinue).Count;"
           "\"$k $w\"")
    try:
        k, w = s.split()
        return int(k), int(w)
    except ValueError:
        return -1, -1


def eh_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (OSError, AttributeError):
        return False


def comando_app() -> tuple[str, str]:
    """(executável, argumentos base) para chamar o próprio app."""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return (w if os.path.exists(w) else exe), f'"{os.path.join(raiz, "RyzenTune.py")}"'


def _xml_tarefa(exe: str, args: str) -> str:
    from xml.sax.saxutils import escape
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>RyzenTune: confere o resultado do último teste e aplica o Curve Optimizer.</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><Delay>PT20S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(exe)}</Command><Arguments>{escape((args + " --boot").strip())}</Arguments></Exec></Actions>
</Task>
"""


def criar_tarefa() -> tuple[bool, str]:
    exe, args = comando_app()
    fd, caminho = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    try:
        with open(caminho, "w", encoding="utf-16") as f:
            f.write(_xml_tarefa(exe, args))
        r = subprocess.run(["schtasks", "/Create", "/TN", TAREFA, "/XML", caminho, "/F"],
                           capture_output=True, creationflags=SEM_JANELA)
        msg = (r.stdout + r.stderr).decode("mbcs", "replace").strip()
        log.info("criar tarefa: %s %s", r.returncode, msg)
        return r.returncode == 0, msg
    finally:
        os.remove(caminho)


def remover_tarefa() -> None:
    subprocess.run(["schtasks", "/Delete", "/TN", TAREFA, "/F"], capture_output=True,
                   creationflags=SEM_JANELA)


def tarefa_ok() -> bool:
    """A tarefa existe e aponta para este executável?"""
    r = subprocess.run(["schtasks", "/Query", "/TN", TAREFA, "/XML"], capture_output=True,
                       creationflags=SEM_JANELA)
    if r.returncode != 0:
        return False
    texto = r.stdout.decode("utf-16", "replace") if r.stdout[:2] in (b"\xff\xfe", b"\xfe\xff") \
        else r.stdout.decode("mbcs", "replace")
    exe, _ = comando_app()
    return exe.lower() in texto.lower()


def reiniciar(bios: bool) -> tuple[bool, str]:
    cmd = ["shutdown", "/r", "/t", "5"] + (["/fw"] if bios else [])
    r = subprocess.run(cmd, capture_output=True, creationflags=SEM_JANELA)
    return r.returncode == 0, (r.stdout + r.stderr).decode("mbcs", "replace").strip()


class InstanciaUnica:
    """Impede duas janelas abertas ao mesmo tempo (gravariam o estado por cima uma da outra)."""

    def __init__(self, nome="Local\\RyzenTune-Janela"):
        self.h = None
        try:
            k = ctypes.windll.kernel32
            self.h = k.CreateMutexW(None, False, nome)
            self.ja_existe = k.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        except (OSError, AttributeError):
            self.ja_existe = False
