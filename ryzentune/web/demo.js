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
  const q0 = new URLSearchParams(location.search);
  const cenario = q0.get("demo") || "preparada";
  const m = estado.mem;
  if (new URLSearchParams(location.search).has("semanim")) estado.config.animacoes = false;
  if (cenario === "inicio") { m.confirmado = false; m.teste = null; }
  if (cenario === "testar") m.teste.situacao = "testar";
  if (cenario === "pronta") { m.teste = null; m.feitos = ["freq", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRFC", "grupoRRD", "grupoWTR", "tWR"];
    m.busca = Object.fromEntries(m.feitos.map((k) => [k, { lo: k === "tRAS" ? -1 : 1 }])); }
  if (cenario === "obs") {
    m.teste = null; m.feitos = ["freq"];
    estado.cpu.teste = { valor: -20, situacao: "observando", desde: "2026-11-12T08:00:00", desde_obs: new Date(Date.now() - 9 * 36e5).toISOString() };
  }
  // 2.3: medições, pulos, chip divergente e Curve Optimizer por núcleo
  estado.bench = [
    { quando: "2026-11-12T16:30:00", rotulo: "Antes de tudo", mem: "3200 CL18-22-22-42", trfc_ns: 350, co: "0", lat_ns: 104.2, leitura: 35.1, escrita: 26.0, copia: 34.7, st: 728, mt: 4480 },
    { quando: "2026-11-12T23:36:00", rotulo: "Depois de: Frequência", mem: "3600 CL22-25-25-48", trfc_ns: 350, co: "0", lat_ns: 99.1, leitura: 39.3, escrita: 27.9, copia: 38.7 },
    { quando: "2026-11-13T10:00:00", rotulo: "Medição manual", mem: "3600 CL16-20-20-36", trfc_ns: 300, co: "-20 -25 -15 -25 -20 -25 -20 -25", lat_ns: 86.4, leitura: 42.8, escrita: 29.6, copia: 41.9, st: 761, mt: 4702 },
  ];
  if (cenario === "pulados") {
    m.teste = null; m.feitos = ["freq", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRFC", "grupoRRD", "grupoWTR", "tWR"];
    m.pulados = [...m.feitos]; m.busca = { freq: { lo: 1 } };
    Object.assign(m.estavel, { tCL: 22, tRCDRD: 25, tRCDWR: 25, tRP: 25, tRAS: 48, tRFC: 630 });
  }
  if (cenario === "pulados" || cenario === "chip") {
    m.chip = { ...m.chip, chip: "hynix_16", nome: "SK Hynix 16 Gb (MJR, CJR ou DJR)", manual: true, confianca: "escolhido por você" };
    m.chip_spd = { chip: "hynix_8", nome: "SK Hynix 8 Gb (CJR ou DJR)", confianca: "média" };
  }
  const c = estado.cpu;
  if (cenario === "refinar") { m.teste = null; c.feito = true; c.estavel = -15; }
  if (cenario === "nucleos") {
    m.teste = null; c.feito = true; c.estavel = -15;
    c.nucleos = { estavel: [-20, -20, -15, -20, -20, -15, -20, -20], limite: [false, false, true, false, false, true, false, false], feito: false };
    c.teste = { modo: "nucleos", valores: [-25, -25, -15, -25, -25, -15, -25, -25], mudados: [0, 1, 3, 4, 6, 7], situacao: q0.get("sit") || "observando",
      desde: "2026-11-13T08:00:00", desde_obs: new Date(Date.now() - 5 * 36e5).toISOString() };
  }
  estado.historico.push({ quando: "2026-11-12T20:40:00", tipo: "Memória", texto: "PASSOU 'tCL (latência CAS)'. Novo estável: 3600 MT/s CL16-19-19-36." });
  // estados extras de cada tela: &estado=carregando | erro | vazio, e &rodando para o teste já em andamento
  const q = new URLSearchParams(location.search), est2 = q.get("estado") || "";
  if (cenario === "preparada" && q.has("muitos")) {  // passo da velocidade com XMP 3200 CL18: muda quase tudo (caso real)
    Object.assign(m.estavel, { freq: 3200, fclk: 1600, tCL: 18, tRCDRD: 22, tRCDWR: 22, tRP: 22, tRAS: 42, tRC: 74, tRFC: 560, tRRDS: 6, tRRDL: 8, tFAW: 34, tWTRS: 4, tWTRL: 12, tWR: 24, tRTP: 12, tCWL: 16 });
    m.feitos = []; m.medicoes = [];
    m.teste = { passo: "freq", situacao: "preparada", perfil: { ...m.estavel, freq: 3600, fclk: 1800, tCL: 22, tRCDRD: 25, tRCDWR: 25, tRP: 25, tRAS: 48, tRC: 73, tRFC: 630, tRRDS: 7, tRRDL: 9, tFAW: 38, tWTRS: 5, tWTRL: 14, tWR: 27, tRTP: 14, tCWL: 20 } };
  }
  if (est2 === "vazio") {
    if (cenario === "inicio") { m.chip = null; m.alvos = null; }
    if (cenario === "preparada") m.teste.perfil = { ...m.estavel };
    if (cenario === "pronta") m.medicoes = [];
  }
  if (cenario === "pronta" && est2 === "erro") m.medicoes = m.medicoes.slice(0, 1);
  let t = 52;
  let teste = { rodando: false };
  if (cenario === "testar" && q.has("rodando")) {
    teste = est2 === "carregando" ? { rodando: true, tipo: "memoria", minutos: 30, fracao: 0, erros: 0, gbps: 0, ciclo: 0, mb: 24000, padrao: "" }
      : { rodando: true, tipo: "memoria", minutos: 30, fracao: 0.42, erros: est2 === "erro" ? 12 : 0, gbps: 38.4, ciclo: 3, mb: 24000, padrao: "aleatório" };
  }
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
    ler_timings: () => q.has("muitos") && !est2 ? Promise.resolve({ timings: { ...est, mts_ratio: est.freq }, pm: { fclk: 1708, uclk: 1708, mclk: 1708, vsoc: 1.0 } })  // tabela de energia deslocada, como no print real
      : est2 === "carregando" ? new Promise(() => {})
      : est2 === "erro" && cenario !== "pronta" ? Promise.resolve({ erro: "acesso ao controlador de memória negado (0xC0000022)" })
      : Promise.resolve({ timings: { ...est, mts_ratio: 3600, cmd2t: 0, tRDRDSCL: 4, tWRWRSCL: 4, tREFI: 14029, tRFC2: 428, tRFC4: 263 },
      pm: { fclk: 1800, uclk: 1800, mclk: 1800, vsoc: 1.0938 }, co: [-15, -15, -15, -15, -15, -15, -15, -15] }),
    obter_estado: () => Promise.resolve(estado),
    memoria_opcoes_chip: () => Promise.resolve({ opcoes: [["samsung_b", "Samsung B-die"], ["hynix_8", "SK Hynix 8 Gb (CJR ou DJR)"], ["micron_8", "Micron 8 Gb (provável Rev.E)"], ["generico", "Chip não identificado"]] }),
    memoria_medir: () => est2 === "erro" ? new Promise((r) => setTimeout(() => r({ erro: "o teste de banda foi interrompido pelo Windows" }), 600))
      : est2 === "carregando" ? new Promise(() => {}) : ok({ resultado: { gbps: 41.2 } }),
    teste_status: () => {
      if (teste.rodando && !(est2 === "carregando")) { teste.fracao = Math.min(1, teste.fracao + (q.has("rodando") ? 0.002 : 0.02)); if (teste.tipo === "nucleos") { const k = Object.keys(teste.nucleos); const i = Math.floor(teste.fracao * k.length); k.forEach((c, j) => { teste.nucleos[c] = j < i ? "ok" : j === i ? "testando" : "fila"; }); } if (teste.fracao >= 1) { teste.rodando = false; teste.resultado = "passou"; } }
      return Promise.resolve(teste);
    },
    teste_memoria: () => { teste = { rodando: true, tipo: "memoria", minutos: 30, fracao: 0, erros: 0, gbps: 38.4, ciclo: 1, mb: 24000, padrao: "aleatório" }; return ok({ mb: 24000 }); },
    teste_nucleos: () => { teste = { rodando: true, tipo: "nucleos", fracao: 0, erros: 0, nucleos: Object.fromEntries([0, 2, 4, 6, 8, 10, 12, 14].map((c) => [c, "fila"])) }; return ok({ nucleos: [0, 2, 4, 6, 8, 10, 12, 14] }); },
    monitor_desde: (n) => {
      const agora = Date.now() / 1000, novas = [];
      const gerar = (i, t) => {
        const carga = Math.max(0, Math.sin(i / 40)) * 70 + Math.random() * 8;
        return { n: i, t, temp: 42 + carga * 0.4 + Math.random() * 2, fclk: 1800, uclk: 1800, mclk: 1800, vsoc: 1.0938,
          vcore: 1.05 + carga * 0.004, uso: [0, 1, 2, 3, 4, 5, 6, 7].map((k) => Math.round(Math.min(100, carga * (1 - k * 0.07) + Math.random() * 5))),
          mhz: [0, 1, 2, 3, 4, 5, 6, 7].map((k) => Math.round(3400 + carga * 9 - k * 12 + Math.random() * 40)) };
      };
      if (!n) for (let i = 1; i <= 600; i++) novas.push(gerar(i, agora - (600 - i)));
      else novas.push(gerar(n + 1, agora));
      return Promise.resolve({ amostras: novas, picos: { temp: 77, mhz: 4083, vcore: 1.356 }, base_mhz: 3000, nucleos: 8 });
    },
    travamentos: () => Promise.resolve({ eventos: q0.get("estado") === "vazio" ? [] : [
      { quando: "2026-11-07T11:19:00", tipo: "desligamento" }, { quando: "2026-11-07T10:05:57", tipo: "desligamento" },
      { quando: "2026-11-06T15:08:10", tipo: "desligamento" }, { quando: "2026-11-02T21:03:19", tipo: "desligamento" }] }),
    bench_retrato: () => Promise.resolve({ mem: "3600 CL16-19-19-36", trfc_ns: 320, co: "-15" }),
    bench_status: () => Promise.resolve(q0.has("medindo") ? { rodando: true, etapa: "um núcleo", fracao: 0.55 } : { rodando: false }),
    atualizacao_verificar: () => Promise.resolve({ nova: null, atual: "2.0.0", configurado: true }),
  }, { get: (alvo, nome) => alvo[nome] || (() => ok()) });
}
