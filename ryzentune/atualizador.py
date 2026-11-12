"""Atualização automática pelas Releases do GitHub.

Cada release publica dois arquivos:
  RyzenTune-Setup-X.Y.Z.exe          (instalador)
  RyzenTune-Setup-X.Y.Z.exe.sha256   (hash, conferido antes de executar)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request

from .versao import REPO, __version__

UA = {"User-Agent": "RyzenTune-atualizador", "Accept": "application/vnd.github+json"}


def versao_tupla(v: str) -> tuple[int, ...]:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", (v or "").strip())
    if not m:
        raise ValueError(f"versão inválida: {v!r}")
    return tuple(int(x) for x in m.groups())


def mais_nova(remota: str, local: str = __version__) -> bool:
    try:
        return versao_tupla(remota) > versao_tupla(local)
    except ValueError:
        return False


def repo_configurado() -> bool:
    return "/" in REPO and not REPO.startswith("OWNER/")


def _get(url: str, timeout: int = 15) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def escolher_arquivos(release: dict):
    """Acha o instalador e o .sha256 na release. Devolve (url_exe, nome_exe, url_sha) ou None."""
    exe = sha = None
    for a in release.get("assets", []):
        n = a.get("name", "")
        if re.fullmatch(r"RyzenTune-Setup-\d+\.\d+\.\d+\.exe", n):
            exe = (a["browser_download_url"], n)
        elif re.fullmatch(r"RyzenTune-Setup-\d+\.\d+\.\d+\.exe\.sha256", n):
            sha = a["browser_download_url"]
    if exe and sha:
        return exe[0], exe[1], sha
    return None


def verificar() -> dict | None:
    """Devolve {'versao','notas','url','nome','sha_url'} se houver versão mais nova; senão None."""
    if not repo_configurado():
        return None
    rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
    tag = rel.get("tag_name", "")
    if rel.get("draft") or rel.get("prerelease") or not mais_nova(tag):
        return None
    arq = escolher_arquivos(rel)
    if not arq:
        return None
    return {"versao": tag.lstrip("v"), "notas": rel.get("body") or "", "url": arq[0],
            "nome": arq[1], "sha_url": arq[2]}


def sha_esperado(texto: str) -> str:
    m = re.search(r"\b([0-9a-fA-F]{64})\b", texto)
    if not m:
        raise ValueError("arquivo .sha256 inválido")
    return m.group(1).lower()


def baixar(info: dict, progresso=None) -> str:
    """Baixa e confere o hash. Devolve o caminho do instalador (ou levanta exceção)."""
    esperado = sha_esperado(_get(info["sha_url"]).decode("ascii", "replace"))
    pasta = tempfile.mkdtemp(prefix="ryzentune-")
    destino = os.path.join(pasta, info["nome"])
    h = hashlib.sha256()
    req = urllib.request.Request(info["url"], headers={"User-Agent": UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        feito = 0
        while True:
            bloco = r.read(256 * 1024)
            if not bloco:
                break
            f.write(bloco)
            h.update(bloco)
            feito += len(bloco)
            if progresso and total:
                progresso(feito / total)
    if h.hexdigest() != esperado:
        os.remove(destino)
        raise ValueError("o arquivo baixado não confere com o hash publicado; atualização cancelada")
    return destino


def instalar(caminho: str) -> None:
    """Executa o instalador em modo silencioso; ele fecha o app e abre a versão nova no fim."""
    subprocess.Popen([caminho, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     close_fds=True)
