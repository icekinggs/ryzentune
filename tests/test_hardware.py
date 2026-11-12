import pytest

from ryzentune.hardware import classificar_cpu, fabricante_placa


@pytest.mark.parametrize("nome,ger,x3d,apu,co,fclk,am4", [
    ("AMD Ryzen 7 5700X3D 8-Core Processor", "zen3", True, False, True, True, True),
    ("AMD Ryzen 7 5800X3D 8-Core Processor", "zen3", True, False, True, True, True),
    ("AMD Ryzen 5 5600X 6-Core Processor", "zen3", False, False, True, True, True),
    ("AMD Ryzen 5 5600G with Radeon Graphics", "zen3", False, True, True, True, True),
    ("AMD Ryzen 7 3700X 8-Core Processor", "zen2", False, False, False, True, True),
    ("AMD Ryzen 5 PRO 4650G with Radeon Graphics", "zen2", False, True, False, True, True),
    ("AMD Ryzen 5 3400G with Radeon Vega Graphics", "zen+", False, True, False, False, True),
    ("AMD Ryzen 5 2600 Six-Core Processor", "zen+", False, False, False, False, True),
    ("AMD Ryzen 7 1700 Eight-Core Processor", "zen1", False, False, False, False, True),
    ("AMD Ryzen 7 7800X3D 8-Core Processor", "desconhecida", True, False, False, False, False),
    ("Intel(R) Core(TM) i7-12700K", "desconhecida", False, False, False, False, False),
    ("", "desconhecida", False, False, False, False, False),
])
def test_classificar(nome, ger, x3d, apu, co, fclk, am4):
    p = classificar_cpu(nome, 8)
    assert (p.geracao, p.x3d, p.apu, p.suporta_co, p.tem_fclk, p.am4) == (ger, x3d, apu, co, fclk, am4)
    assert p.freqs and p.freqs == sorted(p.freqs)


def test_nucleos_invalidos():
    assert classificar_cpu("AMD Ryzen 5 5600X", None).nucleos == 1


@pytest.mark.parametrize("txt,esperado", [
    ("Micro-Star International Co., Ltd", "MSI"), ("ASUSTeK COMPUTER INC.", "ASUS"),
    ("Gigabyte Technology Co., Ltd.", "Gigabyte"), ("ASRock", "ASRock"), (None, "Outra"), ("XYZ", "Outra")])
def test_fabricante(txt, esperado):
    assert fabricante_placa(txt) == esperado
