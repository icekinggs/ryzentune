// Dados de demonstração para ver a interface num navegador comum (index.html?demo). Não é usado no app.
export function criarDemo() {
  const est = {
    freq: 3600, fclk: 1800, vdram: 1.4, vsoc: 1.1, gdm: 1, tCL: 16, tRCDRD: 19, tRCDWR: 19, tRP: 19, tRAS: 36,
    tRC: 55, tRFC: 576, tRRDS: 4, tRRDL: 6, tFAW: 16, tWTRS: 4, tWTRL: 12, tWR: 20, tRTP: 10, tCWL: 16,
  };
  const estado = {
    mem: { estavel: est, confirmado: true, feitos: ["freq", "tCL"], mais_tensao: false,
      chip: { chip: "hynix_8", nome: "SK Hynix 8 Gb (CJR ou DJR)", confianca: "média",
        motivo: "Chips SK Hynix de 8 Gb. O SPD não diferencia o CJR do DJR.",
        pentes: [0, 2].map((slot) => ({ slot, modelo: "HKED4161CAB2F2HB4", tamanho_gb: 16, ranks: 2, fabricante_dram: "SK Hynix",
          densidade_gbit: 8, largura: 8, xmp: { mts: 3200, cl: 16 } })) },
      alvos: { freq: 3600, tCL: 16, tRCDRD: 19, tRP: 19, trfc_ns: 320, nota: "O DJR costuma ir além do previsto; o CJR fica perto." },
      economia: { usados: 6, linear: 11 },
      busca: { freq: { lo: 1 }, tCL: { lo: -1 } },
      medicoes: [
        { quando: "2026-11-12T19:12:00", freq: 3200, tCL: 16, tRCDRD: 18, gbps: 37.5, lat_cas_ns: 10, trfc_ns: 350 },
        { quando: "2026-11-12T19:45:00", freq: 3600, tCL: 16, tRCDRD: 19, gbps: 41.2, lat_cas_ns: 8.89, trfc_ns: 320 },
      ],
      teste: { passo: "tRCDRD", perfil: { ...est, tRCDRD: 18 }, situacao: "preparada", desde: "2026-11-12T20:00:00" } },
    cpu: { estavel: -15, teste: null, feito: false, perfil: { nome: "AMD Ryzen 7 5700X3D 8-Core Processor", geracao: "zen3",
      nucleos: 8, x3d: true, suporta_co: true, tem_fclk: true, am4: true } },
    config: { verificar_atualizacao: true, animacoes: true, placa: "MSI" },
    historico: [
      { quando: "2026-11-12T19:10:00", tipo: "Memória", texto: "Ponto de partida lido do hardware: 3200 MT/s CL16-18-18-36 tRFC 560 (350 ns), 1.35 V." },
      { quando: "2026-11-12T19:40:00", tipo: "Memória", texto: "PASSOU 'Frequência'. Novo estável: 3600 MT/s CL16-19-19-36 tRFC 630 (350 ns)." },
      { quando: "2026-11-12T20:20:00", tipo: "Memória", texto: "FALHOU 'tCL (latência CAS)': 12 erro(s) no teste. Limite encontrado; fica o último estável." },
    ],
  };
  // cenários para conferir as telas do assistente: index.html?demo=inicio | preparada | testar | pronta | obs
  const cenario = new URLSearchParams(location.search).get("demo") || "preparada";
  const m = estado.mem;
  if (new URLSearchParams(location.search).has("semanim")) estado.config.animacoes = false;
  if (cenario === "inicio") { m.confirmado = false; m.teste = null; }
  if (cenario === "testar") m.teste.situacao = "testar";
  if (cenario === "pronta") { m.teste = null; m.feitos = ["freq", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRFC", "grupoRRD", "grupoWTR", "tWR"]; }
  if (cenario === "obs") {
    m.teste = null; m.feitos = ["freq"];
    estado.cpu.teste = { valor: -20, situacao: "observando", desde: "2026-11-12T08:00:00", desde_obs: new Date(Date.now() - 9 * 36e5).toISOString() };
  }
  estado.historico.push({ quando: "2026-11-12T20:40:00", tipo: "Memória", texto: "PASSOU 'tCL (latência CAS)'. Novo estável: 3600 MT/s CL16-19-19-36." });
  let t = 52;
  let teste = { rodando: false };
  const ok = (x = {}) => Promise.resolve({ ok: true, estado, ...x });
  return new Proxy({
    iniciar: () => new Promise((r) => setTimeout(() => r({
      hw: { cpu: "AMD Ryzen 7 5700X3D 8-Core Processor", nucleos: 8, placa_fab: "Micro-Star International Co., Ltd",
        placa: "B450 TOMAHAWK (MS-7C02)", bios: "1.J8", pentes: 2, gb: 32, modelo_ram: "HKED4161CAB2F2HB4", ram_mts: 3600 },
      cpu: { ...estado.cpu.perfil, codinome: "Vermeer" }, placa: "MSI",
      driver: { instalado: true, versao: "2.2.0", ok: true, erro: null }, travamentos: { k41: 4, whea: 0 },
      bios: ["F7 (modo avançado) → OC. Frequência e tensões na própria tela; timings em 'Advanced DRAM Configuration'. Deixe 'Memory Try It!' em Disabled. Salve com F10.",
        "Se não ligar, a placa tenta 3 vezes e volta sozinha ao padrão. Senão, limpe o CMOS."],
      versao: "2.0.0", repo: "icekinggs/ryzentune", estado }), 300)),
    ao_vivo: () => { t += (Math.random() - 0.45) * 3; return Promise.resolve({ disponivel: true, temp: t, fclk: 1800, uclk: 1800, mclk: 1800, vsoc: 1.0938 }); },
    ler_timings: () => Promise.resolve({ timings: { ...est, mts_ratio: 3600, cmd2t: 0, tRDRDSCL: 4, tWRWRSCL: 4, tREFI: 14029, tRFC2: 428, tRFC4: 263 },
      pm: { fclk: 1800, uclk: 1800, mclk: 1800, vsoc: 1.0938 }, co: [-15, -15, -15, -15, -15, -15, -15, -15] }),
    obter_estado: () => Promise.resolve(estado),
    memoria_opcoes_chip: () => Promise.resolve({ opcoes: [["samsung_b", "Samsung B-die"], ["hynix_8", "SK Hynix 8 Gb (CJR ou DJR)"], ["micron_8", "Micron 8 Gb (provável Rev.E)"], ["generico", "Chip não identificado"]] }),
    teste_status: () => {
      if (teste.rodando) { teste.fracao = Math.min(1, teste.fracao + 0.02); if (teste.tipo === "nucleos") { const k = Object.keys(teste.nucleos); const i = Math.floor(teste.fracao * k.length); k.forEach((c, j) => { teste.nucleos[c] = j < i ? "ok" : j === i ? "testando" : "fila"; }); } if (teste.fracao >= 1) { teste.rodando = false; teste.resultado = "passou"; } }
      return Promise.resolve(teste);
    },
    teste_memoria: () => { teste = { rodando: true, tipo: "memoria", fracao: 0, erros: 0, gbps: 38.4, ciclo: 1, mb: 24000, padrao: "aleatório" }; return ok({ mb: 24000 }); },
    teste_nucleos: () => { teste = { rodando: true, tipo: "nucleos", fracao: 0, erros: 0, nucleos: Object.fromEntries([0, 2, 4, 6, 8, 10, 12, 14].map((c) => [c, "fila"])) }; return ok({ nucleos: [0, 2, 4, 6, 8, 10, 12, 14] }); },
    atualizacao_verificar: () => Promise.resolve({ nova: null, atual: "2.0.0", configurado: true }),
  }, { get: (alvo, nome) => alvo[nome] || (() => ok()) });
}
