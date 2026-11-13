"""Leitura e gravação do estado (estado.json) com cópia de segurança e migração."""
from __future__ import annotations

import contextlib
import copy
import json
import msvcrt
import os
import shutil
import time

from . import motor

VERSAO_ESTADO = 1


def pasta_dados() -> str:
    p = os.environ.get("RYZENTUNE_DADOS") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "RyzenTune")
    os.makedirs(p, exist_ok=True)
    return p


def arq_estado() -> str:
    return os.path.join(pasta_dados(), "estado.json")


def novo() -> dict:
    return {
        "versao_estado": VERSAO_ESTADO,
        "mem": {"estavel": dict(motor.PADRAO_MEM), "confirmado": False, "teste": None,
                "feitos": [], "mais_tensao": False, "busca": {}, "reinicios": 0,
                "chip": None, "alvos": None, "medicoes": [], "pulados": [], "chip_spd": None},
        "cpu": {"estavel": 0, "teste": None, "feito": False, "perfil": {}, "nucleos": None},
        "bench": [],
        "config": {"verificar_atualizacao": True, "versao_ignorada": "", "animacoes": True},
        "historico": [],
    }


OPACOS = ("estavel", "perfil", "teste", "busca", "alvos", "chip", "chip_spd", "nucleos")


def _mesclar(base: dict, lido: dict) -> dict:
    """Completa chaves que faltam (estado de versão antiga) sem perder o que existe."""
    for k, v in base.items():
        if k not in lido or (isinstance(v, dict) and not isinstance(lido[k], dict)):
            lido[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and k not in OPACOS:
            _mesclar(v, lido[k])
    return lido


def _ler(caminho: str):
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    if not isinstance(dados, dict):
        raise ValueError("estado inválido")
    sem_pulados = isinstance(dados.get("mem"), dict) and "pulados" not in dados["mem"]
    e = _mesclar(novo(), dados)
    for k, v in motor.PADRAO_MEM.items():
        e["mem"]["estavel"].setdefault(k, v)
    if sem_pulados:  # 2.3: os pulos passaram a ser guardados
        e["mem"]["pulados"] = motor.inferir_pulados(e["mem"])
    return e


def carregar() -> dict:
    a = arq_estado()
    for caminho in (a, a + ".bak"):
        if os.path.exists(caminho):
            try:
                return _ler(caminho)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                # guarda o arquivo estragado para análise e tenta o próximo
                try:
                    shutil.copy2(caminho, caminho + ".corrompido")
                except OSError:
                    pass
    return novo()


def salvar(e: dict) -> None:
    a = arq_estado()
    tmp = a + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(a):
        try:
            shutil.copy2(a, a + ".bak")
        except OSError:
            pass
    os.replace(tmp, a)


@contextlib.contextmanager
def transacao(espera_s: float = 30.0):
    """Lê, deixa alterar e grava o estado com trava entre processos (janela x tarefa de boot).
    Se o bloco gerar exceção, nada é gravado."""
    caminho = os.path.join(pasta_dados(), "estado.lock")
    f = open(caminho, "a+b")
    limite = time.monotonic() + espera_s
    while True:
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            if time.monotonic() > limite:
                f.close()
                raise TimeoutError("estado ocupado por outro processo") from None
            time.sleep(0.2)
    try:
        e = carregar()
        yield e
        salvar(e)
    finally:
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        f.close()


def registrar(e: dict, tipo: str, texto: str, log=None) -> None:
    e["historico"].append({"quando": motor.agora_iso(), "tipo": tipo, "texto": texto})
    del e["historico"][:-500]
    if log:
        log.info("[%s] %s", tipo, texto)
