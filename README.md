<p align="center"><img src="recursos/ryzentune.png" width="96" alt=""></p>

<h1 align="center">RyzenTune</h1>

<p align="center">Assistente para achar, com segurança e um passo de cada vez, os melhores timings de memória
e o Curve Optimizer de processadores <b>AMD Ryzen AM4</b>.</p>

<p align="center">
  <a href="https://github.com/icekinggs/ryzentune/releases/latest"><b>⬇ Baixar o instalador</b></a> ·
  <a href="CHANGELOG.md">Novidades</a>
</p>

---

## Como funciona

**Nada muda na hora: tudo vale a partir do próximo boot.**

### Memória
1. Confira os valores atuais (com o [ZenTimings](https://zentimings.protonrom.com/)) e salve como ponto de partida.
2. **Preparar etapa:** o RyzenTune calcula o próximo passo e mostra uma tabela *campo da BIOS → valor atual → novo*,
   com o caminho do menu da sua placa (MSI, ASUS, Gigabyte, ASRock, Biostar).
3. **Reiniciar na BIOS:** o PC reinicia direto na BIOS e você digita os valores.
4. Ao voltar ao Windows, o app confere sozinho se a placa aceitou. Se a velocidade voltou ao padrão, a etapa é
   marcada como falha.
5. Rode o [TestMem5](https://testmem.tz.ru/) (config *anta777 extreme*) e marque **Passou** ou **Falhou**.

Ordem: frequência com FCLK 1:1 (se falhar, tenta mais uma vez com 1,40 V) → tCL → tRCDRD → tRCDWR → tRP →
tRAS → tRFC → tRRDS/tRRDL/tFAW → tWTRS/tWTRL → tWR/tRTP. Uma falha volta ao último estável e passa para o
próximo ajuste.

### Processador (Ryzen 5000)
Curve Optimizer negativo em todos os núcleos (-5 até -30), aplicado pelo PBO2 Tuner por uma tarefa agendada
**só no próximo boot**. Ele some ao desligar, então um valor ruim nunca impede o PC de ligar. Se o Windows
registrar um desligamento forçado ou erro WHEA, o app volta sozinho ao último valor estável.
Teste com o [CoreCycler](https://github.com/sp00n/corecycler).

## Hardware suportado

| Processador | Memória | Curve Optimizer |
|---|---|---|
| Ryzen 5000 (inclusive X3D e APUs G) | ✔ | ✔ |
| Ryzen 3000 / 4000G | ✔ | — (use o PBO na BIOS) |
| Ryzen 1000 / 2000 / 3000G | ✔ (sem FCLK separado) | — |
| Ryzen 7000+ (AM5/DDR5), Intel | ✖ | ✖ |

## Segurança

- O RyzenTune **nunca grava na BIOS**: você digita os valores, e a placa restaura o padrão se não ligar.
- Tensões propostas: memória até 1,40 V e SoC até 1,125 V.
- O estado fica em `%LOCALAPPDATA%\RyzenTune`, com cópia de segurança automática.
- As atualizações são baixadas das Releases deste repositório, e o SHA-256 é conferido antes de instalar.

> Overclock pode causar travamentos e perda de trabalho não salvo. Use por sua conta e risco.

---

## Desenvolvimento

Requisitos: Windows 10/11, Python 3.12+, [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

```powershell
python RyzenTune.py                                  # rodar do código (pede Administrador)
python -m pytest                                     # testes
powershell -ExecutionPolicy Bypass -File build.ps1   # lint + testes + .exe + autoteste + instalador em dist\
```

| Pasta/arquivo | O que é |
|---|---|
| `ryzentune/motor.py` | lógica da busca (pura, 100% testada) |
| `ryzentune/boot.py` | rotina da tarefa agendada |
| `ryzentune/estado.py` | `estado.json` com trava entre processos, backup e migração |
| `ryzentune/sistema.py` | WMI, eventos, tarefa agendada, reinício, PBO2 Tuner |
| `ryzentune/atualizador.py` | atualização pelas Releases com conferência de hash |
| `ryzentune/janela.py` | interface (tkinter) |
| `instalador/` | script do Inno Setup |

### Lançar uma versão

1. Escreva a seção `## [X.Y.Z] - data` no `CHANGELOG.md` e faça o commit.
2. `powershell -ExecutionPolicy Bypass -File lancar.ps1 X.Y.Z`

O script atualiza a versão, roda lint e testes, cria a tag e envia. O GitHub Actions gera o instalador,
faz o autoteste e publica a release. Os apps instalados avisam da atualização na próxima vez que abrirem.

## Licença

[MIT](LICENSE)
