"""Medição de desempenho para comparar antes e depois de cada ajuste.

- Latência da memória: perseguição de ponteiros (cada leitura depende da anterior) numa área muito maior
  que o cache L3, com um laço de 4 instruções em código de máquina (Python puro mediria a si mesmo).
- Banda: leitura, escrita e cópia com todos os núcleos (numpy solta o GIL).
- Processador: a mesma carga conferida do teste de núcleos, contada por segundo, em um núcleo e em todos.

Tudo roda em processos filhos (--bench-memoria / --bench-cpu), como os testes de estabilidade.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time

from .testes import SEM_JANELA, _ambiente, _comando, emitir, memoria_livre_mb

# laço de perseguição (x64, convenção do Windows: rcx = ponteiro inicial, rdx = quantidade)
#   mov rax, rcx / volta: mov rax, [rax] / dec rdx / jnz volta / ret
CODIGO_PERSEGUICAO = bytes([0x48, 0x89, 0xC8, 0x48, 0x8B, 0x00, 0x48, 0xFF, 0xCA, 0x75, 0xF8, 0xC3])
LINHA = 64


def _funcao_perseguicao():
    k = ctypes.windll.kernel32
    k.VirtualAlloc.restype = ctypes.c_void_p
    k.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
    mem = k.VirtualAlloc(None, 4096, 0x3000, 0x40)  # MEM_COMMIT|MEM_RESERVE, PAGE_EXECUTE_READWRITE
    if not mem:
        raise OSError("VirtualAlloc falhou")
    ctypes.memmove(mem, CODIGO_PERSEGUICAO, len(CODIGO_PERSEGUICAO))
    return ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64)(mem)


def montar_cadeia(np, mb: int, semente: int = 2026):
    """Um ciclo aleatório único por todas as linhas de cache da área: cada linha guarda o endereço da próxima."""
    linhas = mb * 1024 * 1024 // LINHA
    arr = np.zeros(linhas * (LINHA // 8), np.uint64)
    base = arr.ctypes.data
    ordem = np.random.Generator(np.random.PCG64(semente)).permutation(linhas).astype(np.uint64)
    proxima = np.roll(ordem, -1)
    arr[ordem * np.uint64(LINHA // 8)] = np.uint64(base) + proxima * np.uint64(LINHA)
    return arr, base + int(ordem[0]) * LINHA


def latencia_ns(mb: int, passos: int = 3_000_000, repeticoes: int = 7) -> float:
    import numpy as np
    arr, inicio = montar_cadeia(np, mb)
    perseguir = _funcao_perseguicao()
    perseguir(inicio, 500_000)  # aquece (TLB, prefetch desligado pelo acaso)
    melhor = float("inf")
    for _ in range(repeticoes):
        t = time.perf_counter()
        perseguir(inicio, passos)
        melhor = min(melhor, (time.perf_counter() - t) / passos * 1e9)
    del arr
    return round(melhor, 1)


def _em_paralelo(np, n, mb, fn, rodadas=6, segundos=0.5):
    """Banda em GB/s: a melhor de várias rodadas curtas (uma rodada atrapalhada pelo Windows não conta)."""
    por = max(1, mb * 1024 * 1024 // 8 // n)
    blocos = [np.ones(por, np.uint64) for _ in range(n)]
    destinos = [np.empty(por, np.uint64) for _ in range(n)] if fn == "copia" else None

    def rodar(i, fim, totais):
        b = blocos[i]
        while time.perf_counter() < fim:
            if fn == "leitura":
                np.bitwise_xor.reduce(b)
                totais[i] += b.nbytes
            elif fn == "escrita":
                b.fill(i)
                totais[i] += b.nbytes
            else:
                np.copyto(destinos[i], b)
                totais[i] += b.nbytes * 2
    melhor = 0.0
    for _ in range(rodadas):
        totais = [0] * n
        inicio = time.perf_counter()
        ts = [threading.Thread(target=rodar, args=(i, inicio + segundos, totais)) for i in range(n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        melhor = max(melhor, sum(totais) / (time.perf_counter() - inicio) / 1e9)
    return round(melhor, 1)


def trabalhador_memoria() -> int:
    import numpy as np

    from .testes import fixar_cpu
    livre = memoria_livre_mb()
    mb = 1024 if livre > 6000 else 256
    try:
        fixar_cpu(2 if (os.cpu_count() or 1) > 2 else 0)  # longe do núcleo 0, onde caem as interrupções
        emitir(tipo="parcial", etapa="latencia")
        lat = latencia_ns(mb)
        ctypes.windll.kernel32.SetProcessAffinityMask(ctypes.windll.kernel32.GetCurrentProcess(),
                                                      ctypes.c_size_t((1 << (os.cpu_count() or 1)) - 1))
        n = max(1, os.cpu_count() or 1)
        r = {"lat_ns": lat, "area_mb": mb}
        for fn in ("leitura", "escrita", "copia"):
            emitir(tipo="parcial", etapa=fn)
            r[fn] = _em_paralelo(np, n, 512, fn)
        emitir(tipo="fim", **r)
        return 0
    except Exception as ex:
        emitir(tipo="erro", msg=str(ex))
        return 2


def trabalhador_cpu(segundos: float) -> int:
    from .testes import carga_referencia
    carga_referencia()
    fim = time.perf_counter() + segundos
    voltas = 0
    inicio = time.perf_counter()
    while time.perf_counter() < fim:
        carga_referencia()
        voltas += 1
    emitir(tipo="fim", por_s=voltas / (time.perf_counter() - inicio))
    return 0


def _ler_fim(proc, timeout):
    saida, _ = proc.communicate(timeout=timeout)
    fim = None
    for linha in saida.splitlines():
        try:
            d = json.loads(linha)
        except ValueError:
            continue
        if d.get("tipo") in ("fim", "erro"):
            fim = d
    return fim


def _abrir(*args):
    return subprocess.Popen(_comando(*args), stdout=subprocess.PIPE, text=True, env=_ambiente(),
                            creationflags=SEM_JANELA)


def pontos_cpu(segundos: float, processos: int) -> float:
    """Voltas por segundo somadas de 'processos' cópias da carga rodando juntas (x10 = pontos)."""
    ps = [_abrir("--bench-cpu", str(segundos)) for _ in range(processos)]
    total = 0.0
    for p in ps:
        d = _ler_fim(p, segundos + 120)
        if not d or d.get("tipo") != "fim":
            raise RuntimeError("um processo da medição do processador falhou")
        total += d["por_s"]
    return round(total * 10)


def medir(completo: bool, ao_progredir=lambda etapa, fracao: None) -> dict:
    """Roda a medição (≈ 25 s só memória, ≈ 45 s completa) e devolve os números."""
    ao_progredir("memória", 0.05)
    d = _ler_fim(_abrir("--bench-memoria"), 300)
    if not d or d.get("tipo") != "fim":
        raise RuntimeError((d or {}).get("msg") or "a medição da memória falhou")
    r = {k: d[k] for k in ("lat_ns", "leitura", "escrita", "copia", "area_mb")}
    if completo:
        ao_progredir("um núcleo", 0.5)
        r["st"] = max(pontos_cpu(4, 1) for _ in range(3))
        ao_progredir("todos os núcleos", 0.75)
        r["mt"] = pontos_cpu(8, max(1, os.cpu_count() or 1))
    ao_progredir("pronto", 1.0)
    return r
