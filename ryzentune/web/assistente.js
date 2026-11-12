"use strict";
/* Assistente guiado: decide sozinho, a partir do estado, qual é a próxima coisa a fazer e mostra só isso. */

const TERMOS = {
  freq: ["Velocidade da memória", "DRAM Frequency"], fclk: ["Velocidade do barramento interno", "FCLK Frequency"],
  vdram: ["Tensão da memória", "DRAM Voltage"], vsoc: ["Tensão do controlador de memória", "CPU NB/SoC Voltage"],
  gdm: ["Modo GearDown", "GearDown Mode"],
  tCL: ["Atraso de leitura", "tCL"], tRCDRD: ["Tempo para abrir uma linha (leitura)", "tRCDRD"],
  tRCDWR: ["Tempo para abrir uma linha (escrita)", "tRCDWR"], tRP: ["Tempo para fechar uma linha", "tRP"],
  tRAS: ["Tempo mínimo de linha aberta", "tRAS"], tRC: ["Ciclo completo de uma linha", "tRC"],
  tRFC: ["Tempo de recarga da memória", "tRFC"], tRRDS: ["Intervalo entre ativações (grupos diferentes)", "tRRDS"],
  tRRDL: ["Intervalo entre ativações (mesmo grupo)", "tRRDL"], tFAW: ["Janela de quatro ativações", "tFAW"],
  tWTRS: ["Pausa entre escrita e leitura (grupos diferentes)", "tWTRS"],
  tWTRL: ["Pausa entre escrita e leitura (mesmo grupo)", "tWTRL"], tWR: ["Recuperação depois de escrever", "tWR"],
  tRTP: ["Pausa entre leitura e fechamento", "tRTP"], tCWL: ["Atraso de escrita", "tCWL"],
};
const AJUSTES_SIMPLES = {
  freq: "a velocidade", tCL: "o atraso de leitura", tRCDRD: "o tempo para abrir uma linha (leitura)",
  tRCDWR: "o tempo para abrir uma linha (escrita)", tRP: "o tempo para fechar uma linha",
  tRAS: "o tempo mínimo de linha aberta", tRFC: "o tempo de recarga", grupoRRD: "o intervalo entre ativações",
  grupoWTR: "a pausa entre escrita e leitura", tWR: "a recuperação depois de escrever",
};
const TOTAL_AJUSTES = 10;
const UN = { freq: "MT/s", fclk: "MHz", vdram: "V", vsoc: "V" };
let trilha = "memoria";
let ultimaTela = "";
let preparando = false;
let erroPreparar = "";

function telaUmaCoisaPorVez(outra) {
  const nomes = { processador: "o ajuste do processador", memoria: "o ajuste da memória" };
  return { chave: `um-${outra}`, titulo: "Uma coisa de cada vez",
    texto: `Termine ${nomes[outra]} primeiro. Mexendo nos dois ao mesmo tempo não dá para saber qual causou um travamento.`,
    primario: [outra === "processador" ? "Ir para o processador" : "Ir para a memória", () => trocarTrilha(outra)] };
}

function trocarTrilha(nome) {
  trilhaEscolhida = true;
  trilha = nome;
  $$(".trilha").forEach((x) => x.classList.toggle("ativa", x.dataset.trilha === nome));
  desenharAssistente();
}

function fmt(k, v) {
  if (k === "gdm") return v ? "Ligado" : "Desligado";
  if (k === "vdram" || k === "vsoc") return Number(v).toFixed(3).replace(/0$/, "");
  return v;
}

/* O que digitar na BIOS: o perfil pedido comparado com o que está rodando AGORA no hardware. */
function valoresParaDigitar(perfil) {
  const m = S.estado.mem, L = S.leitura && !S.leitura.erro ? S.leitura : null, t = L?.timings, pm = L?.pm || {};
  const atual = { ...m.estavel };
  if (t) {
    Object.keys(TERMOS).forEach((k) => { if (k in t) atual[k] = t[k]; });
    atual.freq = pm.mclk ? Math.round(pm.mclk * 2) : t.mts_ratio;
    if (pm.fclk) atual.fclk = Math.round(pm.fclk);
  }
  return Object.keys(TERMOS)
    .filter((k) => !(k === "fclk" && !perfil.fclk))
    .filter((k) => (k === "freq" || k === "fclk" ? Math.abs(atual[k] - perfil[k]) > 20 : String(atual[k]) !== String(perfil[k])))
    .map((k) => ({ k, de: atual[k], para: perfil[k] }));
}

function tabelaValores(lista) {
  return `<table class="valores"><thead><tr><th>O que mudar</th><th>Está</th><th>Mude para</th></tr></thead><tbody>${
    lista.map(({ k, de, para }) => `<tr><td><span class="nome-simples">${esc(TERMOS[k][0])}</span><span class="nome-bios">na BIOS: ${esc(TERMOS[k][1])}</span></td>
      <td class="de">${esc(fmt(k, de))}</td><td class="para">${esc(fmt(k, para))} <small>${esc(UN[k] || "")}</small></td></tr>`).join("")
  }</tbody></table>`;
}

function ultimoResultado(tipo) {
  const h = [...S.estado.historico].reverse().find((x) => x.tipo === tipo && /^(PASSOU|FALHOU|Curve)/.test(x.texto));
  if (!h) return "";
  const passou = /^PASSOU/.test(h.texto);
  const texto = passou
    ? "O último ajuste passou no teste e foi guardado."
    : "O último ajuste não aguentou. Tudo bem: o RyzenTune guardou o último valor que funcionou e vai tentar um intermediário.";
  return `<div class="resultado ${passou ? "" : "falhou"}"><span>${passou ? "✓" : "↺"}</span><span>${texto}</span></div>`;
}

/* ---------------------------------------------------------------- telas da memória */
function telaMemoria() {
  const m = S.estado.mem, t = m.teste, L = S.leitura;
  const driver = S.init.driver;
  if (!driver.ok) {
    const semAdmin = /0x80070005/.test(driver.erro || "");
    return { chave: "sem-driver", titulo: "Não consegui acessar o hardware",
      texto: semAdmin ? "O Windows negou o acesso: o RyzenTune precisa ser aberto como Administrador. Feche e abra pelo atalho do menu Iniciar (ele pede a permissão sozinho)."
        : driver.instalado ? "O driver de acesso está instalado, mas não respondeu. Reinicie o PC e abra o RyzenTune de novo."
        : "Falta o driver de acesso ao hardware (PawnIO). Reinstale o RyzenTune: o instalador coloca o driver junto." };
  }
  const ajusteN = Math.min(TOTAL_AJUSTES, new Set(m.feitos).size + 1);
  const topo = (passo, total) => ({ topoEsq: `Ajuste ${ajusteN} de ${TOTAL_AJUSTES}`, topoDir: `Passo ${passo} de ${total}`,
    fracao: (new Set(m.feitos).size + (passo - 1) / total) / TOTAL_AJUSTES });

  if (!m.confirmado) {
    const c = m.chip, tm = L?.timings, pm = L?.pm || {};
    const mts = tm ? (pm.mclk ? Math.round(pm.mclk * 2) : tm.mts_ratio) : null;
    const xmpV = c?.pentes?.[0]?.xmp?.tensao;
    const html = !L ? "<p class='vazio'>Lendo a memória…</p>" : L.erro ? `<p class="vazio">Não consegui ler: ${esc(L.erro)}</p>` : `
      <p class="texto">Seus pentes: <b>${esc(S.init.hw.pentes)} × ${Math.round(S.init.hw.gb / Math.max(1, S.init.hw.pentes))} GB</b>${c ? `, com chips <b>${esc(c.nome)}</b>` : ""}.
      Hoje estão a <b>${mts} MT/s</b>, com atraso de leitura <b>${tm.tCL}</b>.${m.alvos ? ` Pelo tipo de chip, devem chegar perto de <b>${m.alvos.freq} MT/s</b> com atrasos menores.` : ""}</p>
      <p class="texto">Falta uma informação que o RyzenTune não consegue ler sozinho: a <b>tensão da memória</b>. Ela aparece na BIOS como "DRAM Voltage". Com o XMP ligado, quase sempre é 1,35 V.</p>
      <label class="campo-tensao">Tensão da memória <input type="number" id="ass-vdram" step="0.005" min="1.10" max="1.45" value="${xmpV || 1.35}"> V</label>`;
    return { chave: "m-inicio", topoEsq: "Começo", topoDir: "", fracao: 0,
      titulo: "Vamos conhecer a sua memória",
      html, primario: L && !L.erro ? ["Começar", async () => {
        const v = parseFloat($("#ass-vdram").value);
        if (!(v >= 1.1 && v <= 1.45)) { aviso("Digite a tensão entre 1,10 e 1,45 V.", "erro"); return; }
        if (await chamar("mem_usar_hardware", v)) await chamar("mem_preparar");
      }] : null,
      detalhes: "O RyzenTune vai ajustar um item de cada vez. Em cada ajuste: você muda os valores na BIOS, ele confere se a BIOS aceitou e testa a memória. Se o teste achar erro, ele volta para o último valor bom e tenta um intermediário." };
  }

  if (!t) {
    if (new Set(m.feitos).size >= TOTAL_AJUSTES || m.busca_concluida) return telaMemoriaPronta();
    if (S.estado.cpu.teste) return telaUmaCoisaPorVez("processador");
    if (erroPreparar) {
      return { chave: "m-erro", titulo: "Não consegui calcular o próximo ajuste", texto: erroPreparar,
        primario: ["Tentar de novo", () => { erroPreparar = ""; desenharAssistente(); }] };
    }
    // entre dois ajustes: prepara o próximo sozinho (não mexe em nada, só calcula)
    if (!preparando) {
      preparando = true;
      api.mem_preparar().then((r) => {
        preparando = false;
        if (!r || r.erro) erroPreparar = r ? r.erro : "sem resposta";
        else { S.estado = r.estado; if (!r.resultado) S.estado.mem.busca_concluida = true; }
        desenhar();
      });
    }
    return { chave: "m-calculando", titulo: "Calculando o próximo ajuste…", texto: "" };
  }

  const nome = AJUSTES_SIMPLES[t.passo] || t.passo;
  if (t.situacao === "preparada") {
    const lista = valoresParaDigitar(t.perfil);
    const [onde, seFalhar] = S.init.bios;
    return { chave: `m-prep-${t.passo}-${t.perfil[t.passo] ?? ""}`, ...topo(1, 3),
      titulo: lista.length === 1 ? "Mude 1 valor na BIOS" : `Mude ${lista.length} valores na BIOS`,
      html: `${ultimoResultado("Memória")}
        <p class="texto">Agora vamos melhorar <b>${esc(nome)}</b>.</p>
        ${lista.length ? tabelaValores(lista) : "<p class='texto'>A BIOS já está com esses valores.</p>"}
        <p class="dica">Tire uma foto desta tela com o celular. Na BIOS: ${esc(onde)}</p>`,
      primario: ["Reiniciar na BIOS", async () => {
        if (await confirmar("Reiniciar na BIOS", "Salve o que estiver aberto. O PC reinicia direto na BIOS em 5 segundos.", "Reiniciar agora"))
          chamar("mem_reiniciar_bios");
      }],
      links: [["Já mudei e reiniciei", conferirMem], ["Pular este ajuste", () => chamar("mem_pular")]],
      detalhes: `Todos os outros campos ficam como estão. ${esc(seFalhar)}` };
  }
  if (t.situacao === "aplicada") {
    return { chave: "m-aplicada", ...topo(2, 3), titulo: "Esperando você reiniciar",
      texto: "Mude os valores na BIOS, salve (F10) e deixe o Windows voltar. O RyzenTune confere sozinho se a BIOS aceitou.",
      primario: ["Já reiniciei: conferir agora", conferirMem],
      links: [["Reiniciar na BIOS", () => chamar("mem_reiniciar_bios")], ["Ver de novo os valores", () => chamar("mem_cancelar").then(() => chamar("mem_preparar"))]] };
  }
  if (t.situacao === "divergente") {
    const lista = (t.diferencas || []).map((d) => ({ k: d.campo, de: d.lido, para: d.esperado }));
    return { chave: "m-diverg", ...topo(2, 3), titulo: "Faltou mudar algo na BIOS",
      html: `<p class="texto">A memória ligou, mas ${lista.length === 1 ? "um valor ficou diferente" : "alguns valores ficaram diferentes"} do pedido:</p>${tabelaValores(lista)}`,
      primario: ["Reiniciar na BIOS para corrigir", () => chamar("mem_reiniciar_bios")],
      links: [["Testar assim mesmo", () => chamar("mem_aceitar_divergencia")]] };
  }
  // testar
  const rodando = S.teste?.rodando && S.teste.tipo === "memoria";
  return { chave: `m-testar-${rodando ? "rodando" : "parado"}`, ...topo(3, 3),
    titulo: rodando ? "Testando a memória…" : "A BIOS aceitou. Agora o teste",
    html: rodando ? `<p class="texto">Pode deixar o PC sozinho. Se aparecer qualquer erro, o RyzenTune volta ao último valor bom.</p><div id="ass-teste"></div>`
      : `<p class="texto">O teste escreve e confere quase toda a memória livre por <b>30 minutos</b>, usando todos os núcleos. Feche jogos e programas pesados antes.</p>`,
    primario: rodando ? null : ["Começar o teste", () => iniciarTesteMem(30, 85)],
    links: rodando ? [] : [["O PC travou ou reiniciou sozinho", async () => {
      if (await confirmar("Travou?", "O ajuste será reprovado e o RyzenTune volta ao último valor bom.", "Sim, travou"))
        chamar("mem_resultado", false, "o PC travou (informado por você)");
    }]] };
}

function telaMemoriaPronta() {
  const m = S.estado.mem, med = m.medicoes || [];
  const p = m.estavel, ini = med[0];
  const depoisLat = (p.tCL * 2000 / p.freq).toFixed(2);
  return { chave: "m-pronta", topoEsq: "Concluído", topoDir: "", fracao: 1,
    titulo: "Pronto: sua memória está no melhor ponto que aguentou",
    html: `<div class="antes-depois">
        <div><span>Antes</span><b>${ini ? `${ini.freq} CL${ini.tCL}` : "--"}</b><span>${ini ? `${ini.lat_cas_ns} ns, ${ini.gbps} GB/s` : ""}</span></div>
        <span class="seta">→</span>
        <div class="depois"><span>Agora</span><b>${p.freq} CL${p.tCL}</b><span>${depoisLat} ns${med.length ? `, ${med[med.length - 1].gbps} GB/s` : ""}</span></div>
      </div>
      <p class="texto">Os valores já estão salvos na BIOS. Não precisa fazer mais nada.</p>`,
    links: [["Medir de novo", () => chamar("memoria_medir")], ["Recomeçar do zero", async () => {
      if (await confirmar("Recomeçar", "A busca recomeça a partir dos valores atuais.", "Recomeçar")) chamar("mem_recomecar");
    }]] };
}

/* ---------------------------------------------------------------- telas do processador */
function telaProcessador() {
  const c = S.estado.cpu, p = c.perfil || {}, t = c.teste;
  if (!p.suporta_co) {
    return { chave: "c-nao", titulo: "Seu processador não tem esse ajuste",
      texto: p.geracao === "zen3" ? "O RyzenTune não conseguiu falar com o controlador do processador. Reinicie o PC e abra o app de novo."
        : "O ajuste de tensão por núcleo (Curve Optimizer) só existe na série Ryzen 5000. No seu processador, o ganho está na memória." };
  }
  const prox = [-5, -10, -15, -20, -25, -30].find((v) => v < c.estavel);
  const explica = `Vamos baixar a tensão do processador aos poucos. Com menos tensão ele esquenta menos e mantém a velocidade máxima por mais tempo${p.x3d ? " (no X3D, é o único jeito de ganhar desempenho)" : ""}.`;
  if (!t) {
    if (S.estado.mem.teste) return telaUmaCoisaPorVez("memoria");
    if (c.feito || prox === undefined) {
      return { chave: "c-pronto", topoEsq: "Concluído", fracao: 1, titulo: `Pronto: ajuste em ${c.estavel}`,
        texto: "Esse é o menor valor que o seu processador aguentou. O RyzenTune aplica sozinho a cada vez que o Windows liga.",
        links: [["Voltar para 0", () => chamar("cpu_zerar")], ["Tentar de novo", () => chamar("cpu_recomecar")]] };
    }
    return { chave: `c-inicio-${prox}`, topoEsq: c.estavel ? `Hoje: ${c.estavel}` : "Começo", fracao: 0,
      titulo: c.estavel ? `Próximo valor: ${prox}` : "Deixar o processador mais frio e rápido",
      html: `${ultimoResultado("CPU")}<p class="texto">${explica}</p>
        <p class="texto">Nada muda agora: o valor só vale depois de reiniciar e some quando o PC desliga. Se algo der errado, basta reiniciar.</p>`,
      primario: [`Preparar ${prox}`, () => chamar("cpu_preparar")] };
  }
  if (t.situacao === "pendente") {
    return { chave: "c-pend", topoEsq: `Valor ${t.valor}`, topoDir: "Passo 1 de 3", fracao: 0.15,
      titulo: "Reinicie para ativar", texto: `O valor ${t.valor} entra em vigor quando o Windows ligar de novo.`,
      primario: ["Reiniciar agora", async () => {
        if (await confirmar("Reiniciar", "Salve o que estiver aberto. O PC reinicia em 5 segundos.", "Reiniciar agora")) chamar("cpu_reiniciar");
      }], links: [["Cancelar", () => chamar("cpu_cancelar")]] };
  }
  if (t.situacao === "ativo") {
    const rodando = S.teste?.rodando && S.teste.tipo === "nucleos";
    return { chave: `c-ativo-${rodando}`, topoEsq: `Valor ${t.valor}`, topoDir: "Passo 2 de 3", fracao: 0.45,
      titulo: rodando ? "Testando os núcleos…" : "Ativo. Agora o teste dos núcleos",
      html: rodando ? `<p class="texto">Um núcleo de cada vez. Pode deixar o PC sozinho.</p><div id="ass-teste"></div>`
        : `<p class="texto">Leva uns <b>16 minutos</b>: cada núcleo recebe uma carga conferida, com pausas no meio. É nas trocas de velocidade que um valor baixo demais falha.</p>`,
      primario: rodando ? null : ["Começar o teste", () => iniciarTesteCpu(120)],
      links: rodando ? [] : [["O PC travou", () => chamar("cpu_resultado", false, "o PC travou (informado por você)")]] };
  }
  // observando
  const ini = new Date(t.desde_obs), horas = (Date.now() - ini.getTime()) / 36e5;
  return { chave: "c-obs", topoEsq: `Valor ${t.valor}`, topoDir: "Passo 3 de 3", fracao: 0.75,
    titulo: "Agora é só usar o PC normalmente",
    html: `<p class="texto">O teste passou. Falta ver se ele aguenta o uso do dia a dia: se o PC ficar <b>24 horas</b> sem travar, o RyzenTune confirma sozinho. Se travar ou reiniciar sozinho, ele volta para o valor anterior.</p>
      <div class="barra-tempo"><i style="width:${Math.min(100, (horas / 24) * 100)}%"></i></div>
      <p class="nota">${Math.min(24, Math.floor(horas))} de 24 horas</p>`,
    links: [["Já usei bastante: confirmar agora", () => chamar("cpu_resultado", true, "")], ["Travou", () => chamar("cpu_resultado", false, "o PC travou (informado por você)")]] };
}

/* ---------------------------------------------------------------- desenho */
let trilhaEscolhida = false;

function desenharAssistente() {
  if (!S.init) return;
  if (!trilhaEscolhida) {  // abre na trilha que está em andamento
    trilhaEscolhida = true;
    if (S.estado.cpu.teste && !S.estado.mem.teste) trocarTrilha("processador");
  }
  const tela = trilha === "memoria" ? telaMemoria() : telaProcessador();
  const alvo = $("#assistente");
  const nova = tela.chave !== ultimaTela;
  ultimaTela = tela.chave;
  const temTopo = tela.topoEsq || tela.topoDir;
  alvo.innerHTML = `<div class="tela${nova ? " nova" : ""}">
      ${temTopo ? `<div class="tela-topo"><span>${esc(tela.topoEsq || "")}</span><span>${esc(tela.topoDir || "")}</span></div>
      <div class="progresso"><i style="width:${Math.round((tela.fracao || 0) * 100)}%"></i></div>` : ""}
      <h2>${esc(tela.titulo)}</h2>
      ${tela.texto ? `<p class="texto">${esc(tela.texto)}</p>` : ""}
      ${tela.html || ""}
      <div class="acoes-tela">
        ${tela.primario ? `<button class="botao primario grande" data-acao="p">${esc(tela.primario[0])}</button>` : ""}
        ${(tela.links || []).map(([r], i) => `<button class="link" data-acao="${i}">${esc(r)}</button>`).join("")}
      </div>
      ${tela.detalhes ? `<details class="detalhes"><summary>Como funciona</summary><p>${esc(tela.detalhes)}</p></details>` : ""}
    </div>`;
  if (tela.primario) $('[data-acao="p"]', alvo).onclick = (e) => { e.target.disabled = true; Promise.resolve(tela.primario[1]()).finally(() => { e.target.disabled = false; }); };
  (tela.links || []).forEach(([, fn], i) => { $(`[data-acao="${i}"]`, alvo).onclick = fn; });
  if (S.teste?.rodando) desenharTeste($("#ass-teste"), S.teste);
}

function ligarAssistente() {
  $$(".trilha").forEach((b) => b.addEventListener("click", () => trocarTrilha(b.dataset.trilha)));
}
ligarAssistente();
