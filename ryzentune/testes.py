"""Testes de estabilidade embutidos (rodam em processos separados: se a memória/núcleo instável
derrubar o processo, a janela continua de pé e conta como falha).

Trabalhadores (processo filho, imprimem JSON por linha no stdout):
  --teste-memoria  <MB> <minutos>
  --teste-nucleo   <cpu_logica> <segundos>
Coordenadores (na janela): TesteMemoria, TesteNucleos.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

BLOCO = 8 * 1024 * 1024 // 8   # 8 MB em uint64 (limita a memória temporária da conferência)
SEM_JANELA = 0x08000000


def emitir(**d):
    sys.stdout.write(json.dumps(d) + "\n")
    sys.stdout.flush()


# ================================================================ memória (trabalhador)
def _padroes(np):
    full = np.uint64(0xFFFFFFFFFFFFFFFF)
    return [
        ("zeros/uns", lambda i0, n: np.zeros(n, np.uint64), lambda i0, n: np.full(n, full, np.uint64)),
        ("xadrez", lambda i0, n: np.full(n, np.uint64(0xAAAAAAAAAAAAAAAA), np.uint64),
         lambda i0, n: np.full(n, np.uint64(0x5555555555555555), np.uint64)),
        ("endereço", lambda i0, n: np.arange(i0, i0 + n, dtype=np.uint64) * np.uint64(0x9E3779B97F4A7C15),
         None),
        ("aleatório", None, None),
    ]


def _aleatorio(np, semente, i0, n):
    return np.random.Generator(np.random.PCG64([semente, i0])).integers(0, 2**63, n, dtype=np.uint64,
                                                                         endpoint=False) * np.uint64(2) + np.uint64(1)


def _fatia(np, arr, nome, gerar, inverso, semente, parar):
    """Escreve e confere um padrão (e o inverso) na fatia. Devolve nº de palavras erradas."""
    erros = 0
    total = arr.size
    passos = [(gerar, False)]
    if inverso is not None:
        passos.append((inverso, False))
    else:
        passos.append((gerar, True))  # inversão do mesmo padrão
    for gen, inverter in passos:
        for i0 in range(0, total, BLOCO):
            if parar.is_set():
                return erros
            n = min(BLOCO, total - i0)
            v = gen(i0, n)
            arr[i0:i0 + n] = ~v if inverter else v
        for i0 in range(0, total, BLOCO):
            if parar.is_set():
                return erros
            n = min(BLOCO, total - i0)
            v = gen(i0, n)
            esperado = ~v if inverter else v
            erros += int(np.count_nonzero(arr[i0:i0 + n] != esperado))
    return erros


def trabalhador_memoria(mb: int, minutos: float):
    import numpy as np
    nthreads = max(1, os.cpu_count() or 1)
    palavras = mb * 1024 * 1024 // 8
    por_thread = palavras // nthreads
    try:
        fatias = [np.empty(por_thread, np.uint64) for _ in range(nthreads)]
        for f in fatias:
            f.fill(0)  # força a alocação física agora
    except MemoryError:
        emitir(tipo="erro", msg=f"não consegui reservar {mb} MB")
        return 2
    padroes = _padroes(np)
    parar = threading.Event()
    lock = threading.Lock()
    estado = {"erros": 0, "bytes": 0, "ciclo": 0, "padrao": ""}
    fim = time.monotonic() + minutos * 60

    def rodar(idx, arr):
        semente = 12345 + idx
        ciclo = 0
        while not parar.is_set() and time.monotonic() < fim:
            for nome, gen, inv in padroes:
                if parar.is_set() or time.monotonic() >= fim:
                    break
                if gen is None:  # aleatório
                    s = semente + ciclo * 1000

                    def gen(i0, n, s=s):
                        return _aleatorio(np, s, i0, n)
                e = _fatia(np, arr, nome, gen, inv, semente, parar)
                with lock:
                    estado["erros"] += e
                    estado["bytes"] += arr.nbytes * 4
                    estado["padrao"] = nome
            ciclo += 1
            with lock:
                estado["ciclo"] = max(estado["ciclo"], ciclo)

    ts = [threading.Thread(target=rodar, args=(i, f), daemon=True) for i, f in enumerate(fatias)]
    inicio = time.monotonic()
    for t in ts:
        t.start()
    while any(t.is_alive() for t in ts):
        time.sleep(1)
        with lock:
            dec = time.monotonic() - inicio
            emitir(tipo="progresso", erros=estado["erros"], ciclo=estado["ciclo"], padrao=estado["padrao"],
                   gbps=round(estado["bytes"] / max(dec, 0.001) / 1e9, 2),
                   fracao=min(1.0, dec / (minutos * 60)))
    emitir(tipo="fim", erros=estado["erros"], ciclos=estado["ciclo"])
    return 0


# ================================================================ núcleo (trabalhador)
def carga_referencia() -> str:
    """Calcula um resumo determinístico (inteiro + ponto flutuante + SHA)."""
    import numpy as np
    rng = np.random.Generator(np.random.PCG64(2026))
    a = rng.standard_normal((160, 160))
    b = rng.standard_normal((160, 160))
    h = hashlib.sha256()
    m = a
    for _ in range(6):
        m = np.tanh(m @ b) + a
    h.update(m.tobytes())
    x = np.arange(1, 300_001, dtype=np.int64)
    h.update(((x * x) % 1_000_003 ^ (x >> 3)).sum().tobytes())
    f = np.fft.rfft(a.ravel())
    h.update(np.fft.irfft(f, a.size).round(9).tobytes())
    d = bytes(range(256)) * 4096
    for _ in range(8):
        d = hashlib.sha256(d).digest() * 32768
    h.update(d[:64])
    return h.hexdigest()


def fixar_cpu(cpu_logica: int):
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    if not k.SetProcessAffinityMask(k.GetCurrentProcess(), 1 << cpu_logica):
        raise OSError("não consegui fixar o processo no núcleo")


def trabalhador_nucleo(cpu_logica: int, segundos: float, referencia: str):
    fixar_cpu(cpu_logica)
    fim = time.monotonic() + segundos
    voltas = erros = 0
    while time.monotonic() < fim:
        # rajada de carga + pausa curta: as trocas de clock/tensão são onde o CO instável falha
        t_carga = time.monotonic() + 1.5
        while time.monotonic() < t_carga:
            if carga_referencia() != referencia:
                erros += 1
            voltas += 1
        time.sleep(0.25)
        emitir(tipo="progresso", voltas=voltas, erros=erros,
               fracao=min(1.0, 1 - (fim - time.monotonic()) / segundos))
    emitir(tipo="fim", voltas=voltas, erros=erros)
    return 0


# ================================================================ coordenadores (na janela)
def _comando(*args) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, os.path.join(raiz, "RyzenTune.py"), *args]


def _ambiente():
    env = dict(os.environ)
    for v in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        env[v] = "1"  # um núcleo = uma thread; resultado determinístico
    return env


def trabalhador_referencia():
    emitir(tipo="ref", hash=carga_referencia())
    return 0


def referencia_em_processo() -> str:
    r = subprocess.run(_comando("--teste-referencia"), capture_output=True, text=True, env=_ambiente(),
                       creationflags=SEM_JANELA, timeout=120)
    for linha in r.stdout.splitlines():
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        if d.get("tipo") == "ref":
            return d["hash"]
    raise RuntimeError(f"não consegui calcular a referência (código {r.returncode})")


class _Base:
    def __init__(self):
        self.proc = None
        self.parado = False
        self.status = {"rodando": False}
        self._lock = threading.Lock()

    def _ler_saida(self, proc, ao_receber):
        for linha in proc.stdout:
            try:
                ao_receber(json.loads(linha))
            except ValueError:
                continue
        return proc.wait()

    def parar(self):
        self.parado = True
        p = self.proc
        if p and p.poll() is None:
            p.terminate()

    def obter(self):
        with self._lock:
            return dict(self.status)


class TesteMemoria(_Base):
    def iniciar(self, mb: int, minutos: float, ao_terminar=None):
        self.status = {"rodando": True, "tipo": "memoria", "mb": mb, "minutos": minutos, "fracao": 0,
                       "erros": 0, "ciclo": 0, "gbps": 0, "padrao": "", "resultado": None, "inicio": time.time()}

        def rodar():
            try:
                self.proc = subprocess.Popen(_comando("--teste-memoria", str(mb), str(minutos)),
                                             stdout=subprocess.PIPE, text=True, env=_ambiente(),
                                             creationflags=SEM_JANELA)

                def receber(d):
                    with self._lock:
                        if d["tipo"] in ("progresso", "fim"):
                            self.status.update({k: v for k, v in d.items() if k != "tipo"})
                        elif d["tipo"] == "erro":
                            self.status["msg"] = d["msg"]
                codigo = self._ler_saida(self.proc, receber)
            except OSError as ex:
                codigo, self.status["msg"] = -1, str(ex)
            with self._lock:
                s = self.status
                s["rodando"] = False
                if self.parado:
                    s["resultado"] = "parado"
                elif codigo != 0:
                    s["resultado"] = "falhou"
                    s.setdefault("msg", f"o teste caiu (código {codigo}): sinal de memória instável")
                else:
                    s["resultado"] = "passou" if s.get("erros", 0) == 0 else "falhou"
                    s["fracao"] = 1.0
            if ao_terminar:
                ao_terminar(self.obter())
        threading.Thread(target=rodar, daemon=True).start()


class TesteNucleos(_Base):
    def iniciar(self, nucleos: list[int], segundos_por_nucleo: float, ao_terminar=None):
        """nucleos = CPUs lógicas a testar (uma por núcleo físico)."""
        self.status = {"rodando": True, "tipo": "nucleos", "nucleos": {str(c): "fila" for c in nucleos},
                       "atual": None, "fracao": 0, "erros": 0, "resultado": None, "inicio": time.time()}

        def rodar():
            try:
                # a referência é calculada num processo filho com o mesmo ambiente dos trabalhadores
                # (1 thread de BLAS): com várias threads a ordem das somas muda e o resultado também
                ref = referencia_em_processo()
                if ref != referencia_em_processo():
                    raise RuntimeError("o resultado de referência variou (sistema instável)")
            except Exception as ex:
                with self._lock:
                    self.status.update(rodando=False, resultado="falhou", msg=str(ex))
                if ao_terminar:
                    ao_terminar(self.obter())
                return
            for i, cpu in enumerate(nucleos):
                if self.parado:
                    break
                with self._lock:
                    self.status["atual"] = cpu
                    self.status["nucleos"][str(cpu)] = "testando"
                res = {"erros": 0}
                try:
                    self.proc = subprocess.Popen(
                        _comando("--teste-nucleo", str(cpu), str(segundos_por_nucleo), ref),
                        stdout=subprocess.PIPE, text=True, env=_ambiente(), creationflags=SEM_JANELA)

                    def receber(d, i=i, res=res):
                        with self._lock:
                            if d["tipo"] in ("progresso", "fim"):
                                res["erros"] = d.get("erros", 0)
                                self.status["fracao"] = (i + d.get("fracao", 0)) / len(nucleos)
                    codigo = self._ler_saida(self.proc, receber)
                except OSError:
                    codigo = -1
                if self.parado:
                    break
                ok = codigo == 0 and res["erros"] == 0
                with self._lock:
                    self.status["nucleos"][str(cpu)] = "ok" if ok else "erro"
                    if not ok:
                        self.status["erros"] += max(1, res["erros"])
            with self._lock:
                s = self.status
                s["rodando"] = False
                s["atual"] = None
                s["resultado"] = "parado" if self.parado else ("passou" if s["erros"] == 0 else "falhou")
                if not self.parado:
                    s["fracao"] = 1.0
            if ao_terminar:
                ao_terminar(self.obter())
        threading.Thread(target=rodar, daemon=True).start()


def memoria_livre_mb() -> int:
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return int(m.ullAvailPhys // (1024 * 1024))


def cpus_por_nucleo() -> list[int]:
    """Uma CPU lógica por núcleo físico (a primeira de cada par SMT)."""
    try:
        import subprocess as sp
        s = sp.run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor | Measure NumberOfCores -Sum).Sum;"
                    "(Get-CimInstance Win32_Processor | Measure NumberOfLogicalProcessors -Sum).Sum"],
                   capture_output=True, text=True, creationflags=SEM_JANELA, timeout=30).stdout.split()
        fisicos, logicos = int(s[0]), int(s[1])
    except Exception:
        logicos = os.cpu_count() or 1
        fisicos = logicos
    passo = max(1, logicos // max(1, fisicos))
    return list(range(0, fisicos * passo, passo))


def medir_banda(segundos: float = 3.0, mb: int = 512) -> float:
    """Banda de cópia da memória (GB/s), com todos os núcleos. Rápido: só para comparar perfis."""
    import numpy as np
    n = max(1, os.cpu_count() or 1)
    por = mb * 1024 * 1024 // 8 // n
    fontes = [np.ones(por, np.uint64) for _ in range(n)]
    destinos = [np.empty(por, np.uint64) for _ in range(n)]
    totais = [0] * n
    fim = time.perf_counter() + segundos

    def copiar(i):
        while time.perf_counter() < fim:
            np.copyto(destinos[i], fontes[i])
            totais[i] += fontes[i].nbytes * 2  # leitura + escrita
    inicio = time.perf_counter()
    ts = [threading.Thread(target=copiar, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return round(sum(totais) / (time.perf_counter() - inicio) / 1e9, 1)
