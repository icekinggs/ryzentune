# Novidades

Formato: cada versão tem uma seção `## [X.Y.Z] - AAAA-MM-DD`. O texto da seção vira a descrição da
release no GitHub e aparece no aviso de atualização do app.

## [2.0.0] - 2026-11-12

Tudo dentro do app, com interface nova.

- Interface nova com abertura animada, painel ao vivo (temperatura, FCLK, UCLK, memória e SoC) e passo a
  passo para cada ajuste.
- Lê os timings, o GearDown, os clocks e as tensões direto do processador. Não precisa mais do ZenTimings.
- Confere sozinho, depois do boot, se a BIOS aplicou exatamente o que foi pedido e mostra o que ficou
  diferente.
- Teste de memória e teste de núcleos embutidos, que reprovam a etapa sozinhos quando acham erro. Não precisa
  mais do TestMem5 nem do CoreCycler.
- Curve Optimizer aplicado direto no processador e lido de volta núcleo por núcleo. Não precisa mais do
  PBO2 Tuner.
- O instalador inclui o driver PawnIO (assinado), usado para acessar o hardware.
- Busca inteligente da memória: lê o SPD dos pentes, identifica o chip (Samsung B-die, Hynix, Micron, Nanya,
  CXMT…), prevê até onde ele costuma chegar e começa cada ajuste nesse valor. Depois divide o intervalo ao meio
  em vez de descer de um em um, chegando ao mesmo resultado com menos reinícios.
- Ao subir a frequência, os timings são afrouxados para manter o tempo em nanossegundos. Antes, os mesmos ciclos
  numa frequência maior ficavam mais apertados e reprovavam frequências que o pente aguentava.
- Mede a banda de cada perfil estável e mostra a latência real em nanossegundos.

## [1.0.0] - 2026-11-12

Primeira versão.

- Assistente de timings de memória para Ryzen AM4 (1000 a 5000): sobe a frequência com FCLK 1:1 e
  depois aperta tCL, tRCD, tRP, tRAS, tRFC e os secundários, um ajuste por vez.
- Mostra exatamente o que mudar na BIOS (MSI, ASUS, Gigabyte, ASRock, Biostar) e reinicia direto nela.
- Detecta sozinho quando a placa não aceitou a etapa (a velocidade voltou ao padrão) ou quando o PC travou.
- Curve Optimizer (Ryzen 5000) aplicado pelo PBO2 Tuner só no próximo boot; se o PC travar ou registrar
  erro WHEA, volta sozinho ao último valor estável.
- Atualização automática pelas Releases do GitHub, com conferência de SHA-256.
