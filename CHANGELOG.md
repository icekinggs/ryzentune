# Novidades

Formato: cada versão tem uma seção `## [X.Y.Z] - AAAA-MM-DD`. O texto da seção vira a descrição da
release no GitHub e aparece no aviso de atualização do app.

## [2.2.1] - 2026-11-12

Correção: a tela ficava parada em "Teste concluído" depois que o teste da memória terminava.

- O teste passava e o resultado era salvo, mas a tela relia o estado cedo demais e não avançava.
  Agora ela espera o resultado ser salvo (aparece "Salvando o resultado…") e só então segue.
- Se ainda assim parar, a tela "Teste concluído" tem o botão "Continuar".

## [2.2.0] - 2026-11-12

Telas novas no assistente da memória.

- Início: uma ficha do seu PC (processador, placa, memória e velocidade de hoje) e a previsão do chip.
- "Mude na BIOS": o ajuste principal aparece grande e o resto vem numa grade numerada, que cabe numa foto do
  celular.
- Teste de memória com anel de progresso, erros, velocidade e tempo restante no próprio assistente.
- Resultado final com barras de antes e agora (velocidade, tempo de resposta e banda) e o atalho para ajustar o
  processador.
- A velocidade atual passa a vir do registrador da memória; a tabela de energia só é usada quando confere com ele.
- Telas próprias para "lendo", "não consegui ler" e "a BIOS já está com esses valores".

## [2.1.1] - 2026-11-12

Visual mais organizado.

- Tudo centralizado na tela, em qualquer tamanho de janela.
- O assistente ganhou a coluna "Sua memória" / "Seu processador": mostra os ajustes já feitos (com o valor
  alcançado), o atual e os próximos.
- Os níveis do Curve Optimizer têm nome (leve, moderado, forte…).
- Sensores: os botões levam ao assistente; corrigido o medidor de temperatura e o anel de progresso dos testes,
  que podiam ficar vazios.

## [2.1.0] - 2026-11-12

Muito mais simples de usar.

- O app abre num assistente que diz, em uma frase, o que fazer agora, com um botão só. Ele sabe sozinho em que
  ponto você está, inclusive depois de reiniciar.
- Duas trilhas: Memória e Processador. As telas técnicas (timings, testes avulsos) ficam no modo avançado, em
  Ajustes.
- Os nomes técnicos vêm explicados em português ("Tempo para abrir uma linha"), com o nome da BIOS ao lado.
- A tabela do que digitar na BIOS compara com o que está rodando agora no hardware. Depois de uma falha, ela mostra
  exatamente o que mudou, inclusive quando a placa voltou ao padrão.
- Processador: depois do teste dos núcleos, basta usar o PC. Se ficar 24 horas sem travar, o valor é confirmado
  sozinho; se travar, volta sozinho ao anterior.
- No fim, uma tela de resumo com antes e depois.

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
