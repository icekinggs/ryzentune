"""Monitoramento contínuo: uma amostra por segundo enquanto a janela está aberta.

Fontes:
- Windows (PDH, não precisa do driver): uso e velocidade de cada núcleo. A velocidade é a mesma do
  Gerenciador de Tarefas: clock base x "% Processor Performance".
- Processador (driver): temperatura Tctl, clocks da memória/FCLK/UCLK, tensão do SoC (tabela de energia) e
  tensão do núcleo pela telemetria SVI2.
"""
from __future__ import annotations

import collections
import ctypes
import threading
import time
import winreg
from ctypes import wintypes

PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2
AMOSTRAS = 900  # 15 minutos


class _Valor(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _Item(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _Valor)]


def clock_base_mhz() -> int:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return int(winreg.QueryValueEx(k, "~MHz")[0])
    except OSError:
        return 0


def ordenar_instancias(nomes: list[str]) -> list[str]:
    """'0,0', '0,1', ... '0,10' em ordem numérica; descarta os totais."""
    def chave(n):
        try:
            g, c = n.split(",")
            return int(g), int(c)
        except ValueError:
            return (1 << 30, 0)
    return sorted((n for n in nomes if "_Total" not in n), key=chave)


class ContadoresWindows:
    """Uso (%) e desempenho (%) de cada processador lógico pela PDH."""

    def __init__(self):
        self.pdh = ctypes.WinDLL("pdh.dll")
        self.q = wintypes.HANDLE()
        self.c_uso = wintypes.HANDLE()
        self.c_perf = wintypes.HANDLE()
        if self.pdh.PdhOpenQueryW(None, None, ctypes.byref(self.q)) != 0:
            raise OSError("PdhOpenQuery falhou")
        add = self.pdh.PdhAddEnglishCounterW
        add.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
        for caminho, h in ((r"\Processor Information(*)\% Processor Utility", self.c_uso),
                           (r"\Processor Information(*)\% Processor Performance", self.c_perf)):
            st = add(self.q, caminho, None, ctypes.byref(h))
            if st != 0 and h is self.c_uso:  # Windows antigo: sem "Utility", usa "Time"
                st = add(self.q, r"\Processor Information(*)\% Processor Time", None, ctypes.byref(h))
            if st != 0:
                raise OSError(f"contador indisponível: {caminho} ({st:#x})")
        self.pdh.PdhCollectQueryData(self.q)

    def _ler(self, contador) -> dict[str, float]:
        f = self.pdh.PdhGetFormattedCounterArrayW
        tam, qtd = wintypes.DWORD(0), wintypes.DWORD(0)
        st = f(contador, PDH_FMT_DOUBLE, ctypes.byref(tam), ctypes.byref(qtd), None) & 0xFFFFFFFF
        if st != PDH_MORE_DATA:
            return {}
        buf = ctypes.create_string_buffer(tam.value)
        if f(contador, PDH_FMT_DOUBLE, ctypes.byref(tam), ctypes.byref(qtd), buf) != 0:
            return {}
        itens = ctypes.cast(buf, ctypes.POINTER(_Item))
        return {itens[i].szName: itens[i].FmtValue.doubleValue for i in range(qtd.value)
                if itens[i].FmtValue.CStatus in (0, 1)}

    def amostra(self) -> tuple[list[float], list[float]]:
        """(uso % de cada processador lógico, desempenho % de cada um)."""
        if self.pdh.PdhCollectQueryData(self.q) != 0:
            return [], []
        uso, perf = self._ler(self.c_uso), self._ler(self.c_perf)
        nomes = ordenar_instancias(list(perf))
        return [min(100.0, uso.get(n, 0.0)) for n in nomes], [perf[n] for n in nomes]

    def fechar(self):
        self.pdh.PdhCloseQuery(self.q)


def por_nucleo(valores: list[float], logicos_por_nucleo: int, maximo=False) -> list[float]:
    """Junta os processadores lógicos de cada núcleo físico (SMT): média do uso, maior velocidade."""
    k = max(1, logicos_por_nucleo)
    grupos = [valores[i:i + k] for i in range(0, len(valores), k)]
    return [max(g) if maximo else sum(g) / len(g) for g in grupos if g]


def conferir_svi2(svi: dict, pm: dict) -> dict:
    """A tensão do SoC pela SVI2 tem de bater com a da tabela de energia: se não bater, o mapa de
    registradores não é o deste processador e nada da SVI2 é mostrado."""
    if not svi.get("vcore"):
        return {}
    ref = pm.get("vsoc")
    if ref and svi.get("vsoc_svi2") and abs(svi["vsoc_svi2"] - ref) > 0.06:
        return {}
    return {"vcore": svi["vcore"]}


class Monitor:
    def __init__(self, abrir_zen, nucleos_fisicos: int):
        self._abrir_zen = abrir_zen
        self.nucleos = max(1, nucleos_fisicos)
        self.amostras: collections.deque = collections.deque(maxlen=AMOSTRAS)
        self.seq = 0
        self.erro = None
        self.base_mhz = clock_base_mhz()
        self._lock = threading.Lock()
        self._fio = None
        self._parar = threading.Event()
        self.picos: dict = {}

    def iniciar(self):
        if self._fio and self._fio.is_alive():
            return
        self._parar.clear()
        self._fio = threading.Thread(target=self._rodar, daemon=True, name="monitor")
        self._fio.start()

    def parar(self):
        self._parar.set()

    def _rodar(self):
        try:
            win = ContadoresWindows()
        except OSError as ex:
            win, self.erro = None, str(ex)
        while not self._parar.wait(1.0):
            a = {"t": round(time.time(), 1)}
            if win:
                try:
                    uso, perf = win.amostra()
                    if perf:
                        k = max(1, len(perf) // self.nucleos)
                        a["uso"] = [round(u) for u in por_nucleo(uso, k)]
                        if self.base_mhz:
                            a["mhz"] = [round(p * self.base_mhz / 100) for p in por_nucleo(perf, k, maximo=True)]
                except OSError:
                    pass
            z = self._abrir_zen()
            if z:
                a["temp"] = z.temperatura()
                pm = {}
                try:
                    pm = z.tabela_energia()
                except Exception:
                    pass
                for k in ("fclk", "uclk", "mclk", "vsoc"):
                    if pm.get(k):
                        a[k] = round(pm[k], 4 if k == "vsoc" else 0)
                a.update(conferir_svi2(z.tensoes_svi2(), pm))
            with self._lock:
                self.seq += 1
                a["n"] = self.seq
                self.amostras.append(a)
                for k in ("temp", "vcore"):
                    if a.get(k) is not None:
                        self.picos[k] = max(self.picos.get(k, a[k]), a[k])
                if a.get("mhz"):
                    self.picos["mhz"] = max(self.picos.get("mhz", 0), max(a["mhz"]))
        if win:
            win.fechar()

    def desde(self, n: int) -> dict:
        with self._lock:
            novas = [a for a in self.amostras if a["n"] > n]
            return {"amostras": novas, "picos": dict(self.picos), "base_mhz": self.base_mhz, "erro": self.erro,
                    "nucleos": self.nucleos}
