"""SPD dos pentes DDR4 (EE1004): leitura pelo SMBus e decodificação.

Segurança: o SPD é uma EEPROM gravável. Este módulo SÓ escreve nos endereços de seleção de página
(0x36 = página 0, 0x37 = página 1) e SÓ lê dos endereços 0x50-0x57. Qualquer outra escrita é recusada
antes de chegar ao driver.
"""
from __future__ import annotations

PAGINA = {0: 0x36, 1: 0x37}
ENDERECOS_SPD = range(0x50, 0x58)
SMBUS_BYTE_DATA = 2

# ID JEDEC do fabricante dos chips (byte de continuação com paridade, byte do código)
FABRICANTES = {
    (0x80, 0xCE): "Samsung", (0x80, 0xAD): "SK Hynix", (0x80, 0x2C): "Micron", (0x83, 0x0B): "Nanya",
    (0x8A, 0x91): "CXMT", (0x80, 0x98): "Kioxia", (0x85, 0x1C): "Spectek", (0x83, 0x9E): "Elpida",
}
DENSIDADE_GB = {0: 0.25, 1: 0.5, 2: 1, 3: 2, 4: 4, 5: 8, 6: 16, 7: 32}
LARGURA = {0: 4, 1: 8, 2: 16, 3: 32}


class EscritaProibida(Exception):
    pass


class LeitorSPD:
    """Lê o SPD pelo módulo SmbusPIIX4 do PawnIO. 'xfer(addr, rw, cmd, proto, dados)' faz a transferência."""

    def __init__(self, xfer):
        self._xfer = xfer

    def _escrever_pagina(self, pagina: int):
        addr = PAGINA[pagina]
        if addr not in (0x36, 0x37):
            raise EscritaProibida(hex(addr))
        self._xfer(addr, 0, 0x00, SMBUS_BYTE_DATA, [0x00])

    def _ler_byte(self, addr: int, offset: int) -> int:
        if addr not in ENDERECOS_SPD:
            raise EscritaProibida(f"leitura fora do SPD: {hex(addr)}")
        return self._xfer(addr, 1, offset, SMBUS_BYTE_DATA, [])[0] & 0xFF

    def presente(self, addr: int) -> bool:
        try:
            self._escrever_pagina(0)
            return self._ler_byte(addr, 2) == 0x0C  # tipo DDR4
        except EscritaProibida:
            raise
        except Exception:
            return False

    def ler(self, addr: int) -> bytes:
        dados = bytearray()
        try:
            for pagina in (0, 1):
                self._escrever_pagina(pagina)
                dados += bytes(self._ler_byte(addr, i) for i in range(256))
        finally:
            try:
                self._escrever_pagina(0)  # sempre deixa na página 0 (a BIOS e outros programas esperam isso)
            except EscritaProibida:
                raise
            except Exception:
                pass
        return bytes(dados)

    def ler_todos(self) -> dict[int, bytes]:
        r = {}
        for addr in ENDERECOS_SPD:
            if self.presente(addr):
                r[addr - 0x50] = self.ler(addr)
        return r


# ---------------------------------------------------------------- decodificação
def _ftb(b: int) -> int:
    return b - 256 if b > 127 else b


def _tempo_ps(mtb: int, ftb: int) -> int:
    return mtb * 125 + _ftb(ftb)


def _texto(b: bytes) -> str:
    return bytes(c for c in b if 32 <= c < 127).decode("ascii").strip()


def decodificar(s: bytes) -> dict:
    """Decodifica 512 bytes de SPD DDR4. Campos que não passam na conferência ficam de fora."""
    if len(s) < 384 or s[2] != 0x0C:
        raise ValueError("não é um SPD DDR4")
    r: dict = {}
    dens = s[4] & 0x0F
    r["densidade_gbit"] = DENSIDADE_GB.get(dens)
    r["largura"] = LARGURA.get(s[12] & 0x07)
    r["ranks"] = ((s[12] >> 3) & 0x07) + 1
    barramento = 8 << (s[13] & 0x07)
    if r["densidade_gbit"] and r["largura"]:
        r["tamanho_gb"] = round(r["densidade_gbit"] / 8 * (barramento / r["largura"]) * r["ranks"])
    r["fabricante_dram"] = FABRICANTES.get((s[350], s[351]), f"desconhecido ({s[350]:02X} {s[351]:02X})")
    r["fabricante_modulo"] = FABRICANTES.get((s[320], s[321]), f"{s[320]:02X} {s[321]:02X}")
    r["modelo"] = _texto(s[329:349])
    r["revisao_dram"] = s[349]

    # JEDEC
    tck = _tempo_ps(s[18], s[125])
    if 600 <= tck <= 1300:
        r["jedec_mts"] = round(2_000_000 / tck / 2) * 2
        taa = _tempo_ps(s[24], s[123])
        r["jedec_cl"] = -(-taa // tck)

    # XMP 2.0 (perfil 1): melhor esforço, só aceita se fizer sentido
    if len(s) >= 512 and s[384] == 0x0C and s[385] == 0x4A:
        try:
            p = 393
            tck = _tempo_ps(s[p + 3], s[p + 38])
            taa = _tempo_ps(s[p + 8], s[p + 37])
            trcd = _tempo_ps(s[p + 9], s[p + 36])
            trp = _tempo_ps(s[p + 10], s[p + 35])
            if 400 <= tck <= 1000:
                mts = round(2_000_000 / tck / 2) * 2
                cl = -(-taa // tck)
                if 2133 <= mts <= 5333 and 10 <= cl <= 30:
                    xmp = {"mts": mts, "cl": cl, "trcd": -(-trcd // tck), "trp": -(-trp // tck)}
                    v = s[p]
                    tensao = (v >> 7) + (v & 0x7F) / 100
                    if 1.1 <= tensao <= 1.6:
                        xmp["tensao"] = round(tensao, 2)
                    r["xmp"] = xmp
        except (IndexError, ZeroDivisionError):
            pass
    return r
