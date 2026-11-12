<p align="center"><img src="recursos/ryzentune.png" width="96" alt=""></p>

<h1 align="center">RyzenTune</h1>

<p align="center">Encontra, com segurança e um passo de cada vez, os melhores timings de memória e o Curve Optimizer
de processadores <b>AMD Ryzen AM4</b>. Tudo dentro de um app só: leitura do hardware, testes e aplicação.</p>

<p align="center">
  <a href="https://github.com/icekinggs/ryzentune/releases/latest"><b>Baixar o instalador</b></a> ·
  <a href="CHANGELOG.md">Novidades</a>
</p>

---

## Como funciona

**Nada muda na hora: tudo vale a partir do próximo boot.**

### Memória
1. O RyzenTune lê os timings que estão rodando agora, direto do controlador de memória do processador. Você
   confirma a tensão da memória e salva como ponto de partida.
2. **Preparar:** ele calcula o próximo passo e mostra o que mudar na BIOS (campo, valor atual e novo), com o caminho
   do menu da sua placa (MSI, ASUS, Gigabyte, ASRock, Biostar).
3. **Aplicar na BIOS:** o PC reinicia direto na BIOS e você digita os valores.
4. **Conferir:** quando o Windows volta, o RyzenTune lê o hardware e confere campo por campo. Se a placa voltou ao
   padrão, a etapa falha. Se algum valor ficou diferente, ele mostra qual.
5. **Testar:** o teste de memória embutido escreve e confere padrões em quase toda a RAM livre, com todos os
   núcleos. Qualquer erro reprova a etapa, e a busca volta ao último valor estável.

Ordem: frequência com FCLK 1:1 (se falhar, tenta de novo com 1,40 V) → tCL → tRCDRD → tRCDWR → tRP → tRAS → tRFC →
tRRDS/tRRDL/tFAW → tWTRS/tWTRL → tWR/tRTP.

### Processador (Ryzen 5000)
Curve Optimizer negativo em todos os núcleos (-5 até -30), aplicado direto no processador **só no próximo boot**.
Ele some ao desligar, então um valor ruim nunca impede o PC de ligar. O teste de núcleos embutido roda uma carga
verificada em cada núcleo, um por vez, alternando com pausas: é nas trocas de clock que o Curve Optimizer instável
falha. Se o Windows registrar travamento ou erro WHEA, o RyzenTune volta sozinho ao último valor estável.

## Hardware suportado

| Processador | Leitura e memória | Curve Optimizer |
|---|---|---|
| Ryzen 5000 Vermeer (5600X, 5800X3D, 5700X3D…) | ✔ | ✔ |
| Ryzen 5000 Cezanne (5600G, 5700G, 5700…) | ✔ | ✔ |
| Ryzen 3000 / 4000G | ✔ | — |
| Ryzen 1000 / 2000 / 3000G | ✔ (sem FCLK separado) | — |
| Ryzen 7000+ (AM5/DDR5), Intel | ✖ | ✖ |

## Segurança

- O RyzenTune **nunca grava na BIOS**: você digita os valores, e a placa restaura o padrão se não ligar.
- Tensões propostas: memória até 1,40 V e SoC até 1,125 V.
- O acesso ao hardware usa o driver [PawnIO](https://pawnio.eu), assinado digitalmente, com os módulos oficiais
  [AMDFamily17 e RyzenSMU](https://github.com/namazso/PawnIO.Modules) (LGPL-2.1). Ele segue a mesma convenção de
  trava (`Access_PCI`) de ZenTimings e HWiNFO, para os programas não se atrapalharem.
- Testes rodam em processos separados: se a memória instável derrubar o teste, o app continua de pé e conta a falha.
- O estado fica em `%LOCALAPPDATA%\RyzenTune`, com cópia de segurança automática.
- As atualizações vêm das Releases deste repositório, com o SHA-256 conferido antes de instalar.

> Overclock pode causar travamentos e perda de trabalho não salvo. Use por sua conta e risco.

## Créditos

- Mapa de registradores de memória, tabela de energia e comandos do SMU: [ZenStates-Core](https://github.com/irusanov/ZenStates-Core), de irusanov.
- Driver e módulos de acesso ao hardware: [PawnIO](https://pawnio.eu), de namazso.

---

## Desenvolvimento

Requisitos: Windows 10/11, Python 3.12+, [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

```powershell
python RyzenTune.py                                  # rodar do código (pede Administrador)
python RyzenTune.py --diagnostico saida.json         # lê o hardware e grava um relatório
python -m pytest                                     # testes
powershell -ExecutionPolicy Bypass -File build.ps1   # lint, testes, .exe, autoteste e instalador em dist\
```

Para ver a interface num navegador comum, com dados de demonstração:
`python -m http.server -d ryzentune/web` e abra `http://localhost:8000/?demo`.

| Arquivo | O que é |
|---|---|
| `ryzentune/motor.py` | lógica da busca (pura, testada) |
| `ryzentune/zen.py` | decodificação de timings, tabela de energia, Curve Optimizer |
| `ryzentune/pawnio.py` | acesso ao driver PawnIO |
| `ryzentune/testes.py` | testes de memória e de núcleos |
| `ryzentune/boot.py` | rotina da tarefa agendada |
| `ryzentune/api.py` | funções chamadas pela interface |
| `ryzentune/web/` | interface (HTML, CSS, JS) |
| `ryzentune/estado.py` | `estado.json` com trava entre processos, backup e migração |
| `instalador/` | script do Inno Setup |

### Lançar uma versão

1. Escreva a seção `## [X.Y.Z] - data` no `CHANGELOG.md` e faça o commit.
2. `powershell -ExecutionPolicy Bypass -File lancar.ps1 X.Y.Z`

## Licença

[MIT](LICENSE). Os módulos do PawnIO incluídos no instalador são LGPL-2.1 (o texto vai junto, em `recursos/pawnio/COPYING`).
