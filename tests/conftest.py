import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def dados_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("RYZENTUNE_DADOS", str(tmp_path))
    return tmp_path


@pytest.fixture
def e_5700x3d():
    from ryzentune import estado, hardware
    e = estado.novo()
    e["cpu"]["perfil"] = hardware.classificar_cpu("AMD Ryzen 7 5700X3D 8-Core Processor", 8).to_dict()
    e["mem"]["confirmado"] = True
    return e
