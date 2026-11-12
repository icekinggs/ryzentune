# Novidades

Formato: cada versão tem uma seção `## [X.Y.Z] - AAAA-MM-DD`. O texto da seção vira a descrição da
release no GitHub e aparece no aviso de atualização do app.

## [1.0.0] - 2026-11-12

Primeira versão.

- Assistente de timings de memória para Ryzen AM4 (1000 a 5000): sobe a frequência com FCLK 1:1 e
  depois aperta tCL, tRCD, tRP, tRAS, tRFC e os secundários, um ajuste por vez.
- Mostra exatamente o que mudar na BIOS (MSI, ASUS, Gigabyte, ASRock, Biostar) e reinicia direto nela.
- Detecta sozinho quando a placa não aceitou a etapa (a velocidade voltou ao padrão) ou quando o PC travou.
- Curve Optimizer (Ryzen 5000) aplicado pelo PBO2 Tuner só no próximo boot; se o PC travar ou registrar
  erro WHEA, volta sozinho ao último valor estável.
- Atualização automática pelas Releases do GitHub, com conferência de SHA-256.
