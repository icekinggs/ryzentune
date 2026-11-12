import hashlib
import io
import json

import pytest

from ryzentune import atualizador


def test_versoes():
    assert atualizador.mais_nova("v1.0.1", "1.0.0")
    assert atualizador.mais_nova("1.10.0", "1.9.9")
    assert not atualizador.mais_nova("v1.0.0", "1.0.0")
    assert not atualizador.mais_nova("v0.9.0", "1.0.0")
    assert not atualizador.mais_nova("lixo", "1.0.0")


def test_escolher_arquivos():
    rel = {"assets": [
        {"name": "RyzenTune-Setup-1.2.0.exe", "browser_download_url": "u1"},
        {"name": "RyzenTune-Setup-1.2.0.exe.sha256", "browser_download_url": "u2"},
        {"name": "outro.zip", "browser_download_url": "u3"}]}
    assert atualizador.escolher_arquivos(rel) == ("u1", "RyzenTune-Setup-1.2.0.exe", "u2")
    assert atualizador.escolher_arquivos({"assets": rel["assets"][:1]}) is None


def test_sha_esperado():
    h = "a" * 64
    assert atualizador.sha_esperado(f"{h.upper()}  RyzenTune-Setup-1.0.0.exe\n") == h
    with pytest.raises(ValueError):
        atualizador.sha_esperado("nada")


class Resp(io.BytesIO):
    def __init__(self, dados):
        super().__init__(dados)
        self.headers = {"Content-Length": str(len(dados))}


def _info():
    return {"url": "http://x/exe", "sha_url": "http://x/sha", "nome": "RyzenTune-Setup-9.9.9.exe"}


def test_baixar_confere_hash(monkeypatch):
    dados = b"instalador" * 1000
    monkeypatch.setattr(atualizador, "_get", lambda url, timeout=15: hashlib.sha256(dados).hexdigest().encode())
    monkeypatch.setattr(atualizador.urllib.request, "urlopen", lambda req, timeout=60: Resp(dados))
    with open(atualizador.baixar(_info()), "rb") as f:
        assert f.read() == dados


def test_baixar_hash_errado_cancela(monkeypatch):
    monkeypatch.setattr(atualizador, "_get", lambda url, timeout=15: b"0" * 64)
    monkeypatch.setattr(atualizador.urllib.request, "urlopen", lambda req, timeout=60: Resp(b"adulterado"))
    with pytest.raises(ValueError):
        atualizador.baixar(_info())


def test_verificar_sem_repo(monkeypatch):
    monkeypatch.setattr(atualizador, "REPO", "OWNER/ryzentune")
    assert atualizador.verificar() is None


@pytest.mark.parametrize("rel,espera", [
    ({"tag_name": "v99.0.0", "prerelease": True, "assets": []}, False),
    ({"tag_name": "v0.0.1", "assets": []}, False),
    ({"tag_name": "v99.0.0", "body": "novidades", "assets": [
        {"name": "RyzenTune-Setup-99.0.0.exe", "browser_download_url": "a"},
        {"name": "RyzenTune-Setup-99.0.0.exe.sha256", "browser_download_url": "b"}]}, True),
])
def test_verificar(monkeypatch, rel, espera):
    monkeypatch.setattr(atualizador, "REPO", "dono/ryzentune")
    monkeypatch.setattr(atualizador, "_get", lambda url, timeout=15: json.dumps(rel).encode())
    r = atualizador.verificar()
    assert (r is not None) == espera
    if espera:
        assert r["versao"] == "99.0.0" and r["url"] == "a"
