"""Leitura de timings/clocks/temperatura e Curve Optimizer em Ryzen (Zen 2/Zen 3, AM4).

Mapa de registradores conforme o ZenStates-Core (irusanov). As funções de decodificação são puras
e recebem um 'ler(endereco)->int', então podem ser testadas sem hardware.
"""
from __future__ import annotations

import struct
import time

# ---------------------------------------------------------------- timings DDR4 (UMC)
UMC_CANAL_PASSO = 1 << 20
MAPA_TIMINGS = {  # nome: (registrador, bit_alto, bit_baixo)
    "ratio": (0x50200, 6, 0), "gdm": (0x50200, 11, 11), "cmd2t": (0x50200, 10, 10),
    "tCL": (0x50204, 5, 0), "tRAS": (0x50204, 14, 8), "tRCDRD": (0x50204, 21, 16), "tRCDWR": (0x50204, 29, 24),
    "tRC": (0x50208, 7, 0), "tRP": (0x50208, 21, 16),
    "tRRDS": (0x5020C, 4, 0), "tRRDL": (0x5020C, 12, 8), "tRTP": (0x5020C, 28, 24),
    "tFAW": (0x50210, 6, 0),
    "tCWL": (0x50214, 5, 0), "tWTRS": (0x50214, 12, 8), "tWTRL": (0x50214, 22, 16),
    "tWR": (0x50218, 6, 0),
    "tRDRDSCL": (0x50220, 27, 24), "tWRWRSCL": (0x50224, 29, 24),
    "tREFI": (0x50230, 15, 0), "tCKE": (0x50254, 28, 24),
    "powerdown": (0x5012C, 28, 28),
}


def bits(v: int, hi: int, lo: int) -> int:
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def canais_ativos(ler) -> list[int]:
    ativos = []
    for ch in range(2):  # AM4: 2 canais
        base = ch * UMC_CANAL_PASSO
        canal = bits(ler(base | 0x50DF0), 19, 19) == 0
        dimm = bits(ler(base | 0x50000), 0, 0) == 1 or bits(ler(base | 0x50008), 0, 0) == 1
        if canal and dimm:
            ativos.append(ch)
    return ativos


def ler_timings(ler) -> dict:
    """Devolve os timings do primeiro canal ativo (os dois canais usam os mesmos valores)."""
    ativos = canais_ativos(ler)
    if not ativos:
        raise ValueError("nenhum canal de memória ativo encontrado")
    base = ativos[0] * UMC_CANAL_PASSO
    cache: dict[int, int] = {}

    def reg(r):
        if r not in cache:
            cache[r] = ler(base | r)
        return cache[r]

    t = {nome: bits(reg(r), hi, lo) for nome, (r, hi, lo) in MAPA_TIMINGS.items()}
    # tRFC: 0x50260 normalmente; 0x50264 quando o primeiro tem o valor padrão de fábrica
    a, b = reg(0x50260), reg(0x50264)
    rfc = b if (a != b and a == 0x21060138) else a
    t["tRFC"], t["tRFC2"], t["tRFC4"] = bits(rfc, 10, 0), bits(rfc, 21, 11), bits(rfc, 31, 22)
    # BGS / BGS Alt
    t["bgs"] = int(not (reg(0x50050) == 0x87654321 and reg(0x50058) == 0x87654321))
    t["bgsalt"] = int(bits(reg(0x500D0), 10, 4) > 0 or bits(reg(0x500D4), 10, 4) > 0)
    t["mts_ratio"] = round(t["ratio"] / 3.0 * 100 * 2)  # BCLK 100 MHz
    t["canais"] = len(ativos)
    return t


# ---------------------------------------------------------------- tabela de energia (PM table)
# deslocamentos em bytes: (FCLK, UCLK, MCLK, VSOC, VDDP, VDDG_IOD, VDDG_CCD)
PM_VERMEER = (0xC0, 0xC8, 0xCC, 0xB4, 0x224, 0x228, 0x22C)
PM_TABELAS = {
    0x380804: PM_VERMEER, 0x380805: PM_VERMEER, 0x380005: PM_VERMEER, 0x380505: PM_VERMEER,
    0x380605: PM_VERMEER, 0x380705: PM_VERMEER, 0x380904: PM_VERMEER, 0x380905: PM_VERMEER,
    0x400001: (0x624, 0x628, 0x62C, 0x19C, 0x89C, None, None),
}


def decodificar_pm(versao: int, dados: bytes) -> dict:
    off = PM_TABELAS.get(versao)
    if off is None:
        return {}
    nomes = ("fclk", "uclk", "mclk", "vsoc", "vddp", "vddg_iod", "vddg_ccd")
    r = {}
    for nome, o in zip(nomes, off, strict=True):
        if o is not None and o + 4 <= len(dados):
            r[nome] = struct.unpack_from("<f", dados, o)[0]
    # conferência de sanidade (tabela errada → descarta tudo)
    ok = 300 <= r.get("fclk", 0) <= 2400 and 300 <= r.get("mclk", 0) <= 2400 and 0.6 <= r.get("vsoc", 0) <= 1.5
    return {k: round(v, 4) for k, v in r.items()} if ok else {}


def temperatura_tctl(v: int) -> float:
    """SMN 0x59800 (THM_TCON_CUR_TMP)."""
    t = (v >> 21) * 0.125
    if (v >> 19) & 1:
        t -= 49.0
    return round(t, 1)


# ---------------------------------------------------------------- telemetria SVI2 (Zen 2 / Zen 3)
SVI2_NUCLEO, SVI2_SOC = 0x5A010, 0x5A00C


def tensao_svi2(v: int) -> float | None:
    """VID de 8 bits nos bits 23:16: tensão = 1,55 V - VID x 6,25 mV. Fora de 0,2-1,6 V é leitura inválida."""
    t = round(1.55 - ((v >> 16) & 0xFF) * 0.00625, 4)
    return t if 0.2 <= t <= 1.6 else None


# ---------------------------------------------------------------- Curve Optimizer
CODINOMES = {1: "Renoir", 2: "Picasso", 3: "Matisse", 6: "Raven Ridge", 7: "Raven Ridge 2", 8: "Summit Ridge",
             9: "Pinnacle Ridge", 11: "Vermeer", 13: "Cezanne", 15: "Dali", 22: "Lucienne"}
# caixa MP1 e comandos de Curve Optimizer (ZenStates-Core: Zen3Settings / APUSettings1_Cezanne)
CO = {
    "Vermeer": {"mp1": (0x3B10530, 0x3B1057C, 0x3B109C4), "set_todos": 0x36, "set_um": 0x35, "get_rsmu": 0x7C,
                "fusivel": 0x30081D98, "fus_shift": 0},
    "Cezanne": {"mp1": (0x3B10528, 0x3B10564, 0x3B10998), "set_todos": 0x55, "set_um": 0x54, "get_rsmu": 0xC3,
                "fusivel": 0x5D448, "fus_shift": 11},
}
SMU_OK = 0x01
SMU_ERROS = {0xFF: "falhou", 0xFE: "comando desconhecido", 0xFD: "rejeitado (pré-requisito)",
             0xFC: "rejeitado (ocupado)", 0x00: "sem resposta"}


def arg_margem(margem: int) -> int:
    """Codificação do ZenStates-Core (MakePsmMarginArg): 16 bits em complemento de dois."""
    return (margem + (0x100000 if margem < 0 else 0)) & 0xFFFF


def mascara_nucleo(ccd: int, nucleo: int) -> int:
    return ((ccd << 28) | ((nucleo % 8) << 20)) & 0xFFF00000


def margem_de_retorno(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class CaixaSMU:
    """Protocolo de caixa de mensagens do SMU usando leitura/escrita de registrador."""

    def __init__(self, ler_reg, escrever_reg, enderecos, tempo_limite=0.5):
        self.ler, self.escrever = ler_reg, escrever_reg
        self.cmd, self.rsp, self.args = enderecos
        self.tempo_limite = tempo_limite

    def _esperar(self) -> int:
        fim = time.monotonic() + self.tempo_limite
        while True:
            r = self.ler(self.rsp)
            if r != 0 or time.monotonic() > fim:
                return r
            time.sleep(0.0005)

    def enviar(self, msg: int, argumentos=()) -> tuple[int, list[int]]:
        a = list(argumentos) + [0] * (6 - len(argumentos))
        if self._esperar() == 0:
            return 0, []
        self.escrever(self.rsp, 0)
        for i, v in enumerate(a):
            self.escrever(self.args + 4 * i, v & 0xFFFFFFFF)
        self.escrever(self.cmd, msg)
        st = self._esperar()
        return st, [self.ler(self.args + 4 * i) for i in range(6)]


# ---------------------------------------------------------------- acesso real
class Zen:
    """Hardware real via PawnIO. Use como contexto: with Zen() as z: ..."""

    def __init__(self):
        from . import pawnio
        self.pawnio = pawnio
        self.amd = pawnio.Modulo("AMDFamily17.bin")
        try:
            self.smu = pawnio.Modulo("RyzenSMU.bin")
        except pawnio.ErroPawnIO:
            self.smu = None
        self._codinome = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.fechar()

    def fechar(self):
        self.amd.fechar()
        if self.smu:
            self.smu.fechar()

    def ler_smn(self, endereco: int) -> int:
        return self.amd.executar("ioctl_read_smn", [endereco], 1)[0] & 0xFFFFFFFF

    # -- leituras
    def timings(self) -> dict:
        with self.pawnio.TravaPCI():
            return ler_timings(self.ler_smn)

    def temperatura(self) -> float | None:
        try:
            with self.pawnio.TravaPCI():
                return temperatura_tctl(self.ler_smn(0x59800))
        except Exception:
            return None

    def codinome(self) -> str:
        if self._codinome is None:
            n = -1
            if self.smu:
                try:
                    n = self.smu.executar("ioctl_get_code_name", [], 1)[0]
                except self.pawnio.ErroPawnIO:
                    pass
            self._codinome = CODINOMES.get(n, f"desconhecido ({n})")
        return self._codinome

    def tabela_energia(self) -> dict:
        if not self.smu:
            return {}
        with self.pawnio.TravaPCI():
            versao, _base = self.smu.executar("ioctl_resolve_pm_table", [], 2)
            self.smu.executar("ioctl_update_pm_table", [], 0)
            qw = self.smu.executar("ioctl_read_pm_table", [], 0x900 // 8)
        dados = b"".join(struct.pack("<Q", q) for q in qw)
        r = decodificar_pm(versao, dados)
        r["versao_tabela"] = f"0x{versao:06X}"
        return r

    # -- Curve Optimizer
    def suporta_co(self) -> bool:
        return self.smu is not None and self.codinome() in CO

    def _caixa_mp1(self) -> CaixaSMU:
        info = CO[self.codinome()]

        def ler(r):
            return self.smu.executar("ioctl_read_smu_register", [r], 1)[0] & 0xFFFFFFFF

        def escrever(r, v):
            self.smu.executar("ioctl_write_smu_register", [r, v], 0)
        return CaixaSMU(ler, escrever, info["mp1"])

    def aplicar_co_todos(self, margem: int) -> None:
        if not self.suporta_co():
            raise RuntimeError(f"Curve Optimizer não suportado neste processador ({self.codinome()})")
        if not -30 <= margem <= 0:
            raise ValueError("margem fora de -30..0")
        info = CO[self.codinome()]
        with self.pawnio.TravaPCI():
            st, _ = self._caixa_mp1().enviar(info["set_todos"], [arg_margem(margem)])
        if st != SMU_OK:
            raise RuntimeError(f"SMU recusou o Curve Optimizer: {SMU_ERROS.get(st, hex(st))}")

    def aplicar_co_nucleos(self, margens: list[int]) -> None:
        """Uma margem por núcleo, na ordem dos núcleos habilitados (a mesma ordem do Windows)."""
        if not self.suporta_co():
            raise RuntimeError(f"Curve Optimizer não suportado neste processador ({self.codinome()})")
        if any(not -30 <= m <= 0 for m in margens):
            raise ValueError("margem fora de -30..0")
        nucleos = self.nucleos_ativos()
        if len(nucleos) != len(margens):
            raise RuntimeError(f"{len(margens)} valores para {len(nucleos)} núcleos habilitados")
        info = CO[self.codinome()]
        for (ccd, n), m in zip(nucleos, margens, strict=True):
            with self.pawnio.TravaPCI():
                st, _ = self._caixa_mp1().enviar(info["set_um"], [mascara_nucleo(ccd, n) | arg_margem(m)])
            if st != SMU_OK:
                raise RuntimeError(f"SMU recusou o Curve Optimizer do núcleo {n}: {SMU_ERROS.get(st, hex(st))}")

    def aplicar_co(self, valor) -> None:
        """Número = todos os núcleos iguais; lista = um valor por núcleo."""
        if isinstance(valor, list):
            self.aplicar_co_nucleos([int(v) for v in valor])
        else:
            self.aplicar_co_todos(int(valor))

    def tensoes_svi2(self) -> dict:
        """Tensão do núcleo e do SoC pela telemetria SVI2 (o que o regulador da placa informa)."""
        try:
            with self.pawnio.TravaPCI():
                nucleo, soc = self.ler_smn(SVI2_NUCLEO), self.ler_smn(SVI2_SOC)
        except Exception:
            return {}
        return {k: v for k, v in (("vcore", tensao_svi2(nucleo)), ("vsoc_svi2", tensao_svi2(soc))) if v}

    def nucleos_ativos(self) -> list[tuple[int, int]]:
        """(ccd, núcleo físico) habilitados, pelos fusíveis."""
        info = CO[self.codinome()]
        r = []
        with self.pawnio.TravaPCI():
            for ccd in range(2 if self.codinome() == "Vermeer" else 1):
                v = self.ler_smn(info["fusivel"] + (ccd << 25))
                if v in (0xFFFFFFFF,):
                    continue
                desligados = (v >> info["fus_shift"]) & 0xFF
                if desligados == 0xFF:
                    continue
                r += [(ccd, n) for n in range(8) if not (desligados >> n) & 1]
        return r

    def ler_co(self) -> list[int] | None:
        """Lê a margem de cada núcleo (melhor esforço: o comando pode não existir em alguns firmwares)."""
        if not self.suporta_co():
            return None
        info = CO[self.codinome()]
        valores = []
        try:
            for ccd, n in self.nucleos_ativos():
                with self.pawnio.TravaPCI():
                    saida = self.smu.executar("ioctl_send_smu_command",
                                              [info["get_rsmu"], mascara_nucleo(ccd, n), 0, 0, 0, 0, 0], 6)
                valores.append(margem_de_retorno(saida[0]))
        except Exception:
            return None
        return valores or None


# ---------------------------------------------------------------- SPD pelo SMBus (FCH AMD)
class SMBus:
    """Barramento SMBus do chipset (módulo SmbusPIIX4). Usa a porta 0, onde ficam os pentes."""

    TRAVA = "Global\\Access_SMBUS.HTP.Method"

    def __init__(self):
        from . import pawnio
        self.pawnio = pawnio
        self.mod = pawnio.Modulo("SmbusPIIX4.bin")

    def fechar(self):
        self.mod.fechar()

    def _xfer(self, addr, rw, cmd, proto, dados):
        entrada = [addr, rw, cmd, proto] + list(dados)
        return self.mod.executar("ioctl_smbus_xfer", entrada, 1 if rw else 0) or [0]

    def ler_spds(self) -> dict[int, bytes]:
        from .spd import LeitorSPD
        with self.pawnio.TravaPCI(self.TRAVA, 5000):
            anterior = self.mod.executar("ioctl_piix4_port_sel", [0], 1)[0]
            try:
                return LeitorSPD(self._xfer).ler_todos()
            finally:
                if anterior not in (0, 0xFFFFFFFFFFFFFFFF):
                    self.mod.executar("ioctl_piix4_port_sel", [anterior], 1)
