"use strict";
/* RyzenTune: interface. Conversa com o Python por window.pywebview.api (cada chamada devolve uma Promise). */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

const S = { init: null, estado: null, leitura: null, vivo: null, teste: null, traco: [], pagina: "assistente" };
let api = null;

const NOMES = {
  freq: "Frequência", fclk: "FCLK", vdram: "DRAM Voltage", vsoc: "SoC Voltage", gdm: "GearDown",
  tCL: "tCL", tRCDRD: "tRCDRD", tRCDWR: "tRCDWR", tRP: "tRP", tRAS: "tRAS", tRC: "tRC", tRFC: "tRFC",
  tRRDS: "tRRDS", tRRDL: "tRRDL", tFAW: "tFAW", tWTRS: "tWTRS", tWTRL: "tWTRL", tWR: "tWR", tRTP: "tRTP", tCWL: "tCWL",
};
const CAMPOS = Object.keys(NOMES);
const ETAPAS = {
  freq: "Frequência", tCL: "tCL (latência CAS)", tRCDRD: "tRCDRD", tRCDWR: "tRCDWR", tRP: "tRP", tRAS: "tRAS",
  tRFC: "tRFC (refresh)", grupoRRD: "tRRDS, tRRDL e tFAW", grupoWTR: "tWTRS e tWTRL", tWR: "tWR e tRTP",
};
const UNIDADE = { freq: "MT/s", fclk: "MHz", vdram: "V", vsoc: "V" };

/* ---------------------------------------------------------------- chamadas */
async function chamar(nome, ...args) {
  try {
    const r = await api[nome](...args);
    if (r && r.erro) { aviso(r.erro, "erro"); return null; }
    if (r && r.estado) { S.estado = r.estado; desenhar(); }
    return r;
  } catch (ex) {
    aviso(`Falha ao chamar ${nome}: ${ex}`, "erro");
    return null;
  }
}

function aviso(texto, tipo = "") {
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.textContent = texto;
  $("#avisos").append(t);
  setTimeout(() => { t.classList.add("saindo"); setTimeout(() => t.remove(), 400); }, tipo === "erro" ? 7000 : 4000);
}

function confirmar(titulo, texto, rotulo = "Confirmar") {
  const d = $("#dialogo");
  $("#dialogo-titulo").textContent = titulo;
  $("#dialogo-texto").textContent = texto;
  $("#dialogo-sim").textContent = rotulo;
  d.showModal();
  return new Promise((res) => d.addEventListener("close", () => res(d.returnValue === "sim"), { once: true }));
}

function animarNumero(el, para, casas = 0) {
  if (para == null || isNaN(para)) { el.textContent = "--"; el.dataset.v = ""; return; }
  const de = parseFloat(el.dataset.v);
  el.dataset.v = para;
  const anim = getComputedStyle(document.documentElement).getPropertyValue("--anim").trim() !== "0";
  if (isNaN(de) || !anim) { el.textContent = para.toFixed(casas); return; }
  const t0 = performance.now(), dur = 600;
  const passo = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = (de + (para - de) * e).toFixed(casas);
    if (k < 1) requestAnimationFrame(passo);
  };
  requestAnimationFrame(passo);
}

/* ---------------------------------------------------------------- navegação */
function irPara(p) {
  S.pagina = p;
  $$(".nav").forEach((b) => b.classList.toggle("ativo", b.dataset.pagina === p));
  $$(".pagina").forEach((s) => s.classList.toggle("ativa", s.id === `pagina-${p}`));
  $("main").scrollTop = 0;
  if (p === "memoria" || p === "processador") lerTimings();
  if (p === "memoria" || p === "assistente") identificarChip();
  if (p === "desempenho") abrirDesempenho();
  if (p === "painel") lerTravamentos();
}

/* ---------------------------------------------------------------- abertura */
async function iniciar() {
  const status = $("#abertura-status");
  const frases = ["Ligando os instrumentos", "Identificando o processador", "Abrindo o acesso ao hardware", "Lendo os timings da memória"];
  let i = 0;
  const giro = setInterval(() => { i = Math.min(i + 1, frases.length - 1); status.textContent = frases[i]; }, 650);
  const minimo = espera(2300);
  const r = await api.iniciar();
  await minimo;
  clearInterval(giro);
  if (!r || r.erro) {
    status.textContent = `Não consegui iniciar: ${r ? r.erro : "sem resposta"}`;
    status.style.color = "var(--erro)";
    return;
  }
  S.init = r;
  S.estado = r.estado;
  aplicarAnimacoes();
  $("#abertura").classList.add("saindo");
  $("#app").hidden = false;
  $("#app").classList.add("entrando");
  setTimeout(() => $("#abertura").remove(), 700);
  $("#versao").textContent = `Versão ${r.versao}`;
  desenhar();
  const inicial = location.hash.slice(1);
  if (inicial && $(`#pagina-${inicial}`)) irPara(inicial);
  lerTimings();
  identificarChip();
  laçoMonitor();
  laçoTeste();
  if (S.estado.config.verificar_atualizacao) verificarAtualizacao(false);
  const op = await api.memoria_opcoes_chip();
  if (op && op.opcoes) $("#chip-escolha").innerHTML = op.opcoes.map(([k, n]) => `<option value="${esc(k)}">${esc(n)}</option>`).join("");
  desenharChip();
}

function aplicarAnimacoes() {
  const on = S.estado?.config?.animacoes !== false;
  document.documentElement.dataset.animacoes = on ? "on" : "off";
}

/* ---------------------------------------------------------------- ao vivo */
function desenharVivo() {
  const v = S.vivo || {};
  const t = v.temp;
  animarNumero($("#temp"), t ?? null, 0);
  const arco = $("#arco-temp");
  const frac = t == null ? 0 : Math.max(0, Math.min(1, (t - 20) / 75));
  arco.style.strokeDashoffset = `${252 * (1 - frac)}px`;
  arco.style.stroke = t >= 85 ? "var(--erro)" : t >= 75 ? "var(--acao)" : "var(--sinal)";
  animarNumero($("#v-mclk"), v.mclk ? v.mclk * 2 : null, 0);
  animarNumero($("#v-fclk"), v.fclk ?? null, 0);
  animarNumero($("#v-uclk"), v.uclk ?? null, 0);
  animarNumero($("#v-vsoc"), v.vsoc ?? null, 3);
  if (t != null) {
    S.traco.push(t);
    if (S.traco.length > 60) S.traco.shift();
    const min = Math.min(...S.traco) - 2, max = Math.max(...S.traco) + 2;
    $("#traco").setAttribute("points", S.traco.map((y, i) => `${(i / 59) * 300},${38 - ((y - min) / (max - min)) * 34}`).join(" "));
  }
}

async function lerTimings() {
  const r = await api.ler_timings();
  if (r && !r.erro) S.leitura = r;
  else S.leitura = { erro: r ? r.erro : "sem resposta" };
  desenharMemoria();
  desenharCpu();
  desenharAssistente();
}

/* ---------------------------------------------------------------- desenho geral */
function desenhar() {
  if (!S.init) return;
  document.documentElement.dataset.avancado = S.estado.config.avancado ? "on" : "off";
  desenharAssistente();
  desenharPainel();
  desenharMemoria();
  desenharCpu();
  desenharHistorico();
  desenharAjustes();
  const pend = S.estado.mem.teste || S.estado.cpu.teste;
  $$(".nav").forEach((b) => b.querySelector(".contador")?.remove());
  if (S.estado.mem.teste) $('.nav[data-pagina="memoria"]').insertAdjacentHTML("beforeend", '<i class="contador"></i>');
  if (S.estado.cpu.teste) $('.nav[data-pagina="processador"]').insertAdjacentHTML("beforeend", '<i class="contador"></i>');
  void pend;
}

function desenharPainel() {
  const { hw, cpu, driver, travamentos } = S.init;
  $("#painel-sub").textContent = `${cpu.nome || "Processador"}${cpu.codinome ? ` (${cpu.codinome})` : ""}`;
  const dv = $("#aviso-driver");
  if (!driver.ok) {
    dv.hidden = false;
    dv.className = "aviso erro";
    dv.textContent = driver.instalado
      ? `O driver PawnIO está instalado, mas não respondeu (${driver.erro}). Reinicie o PC e abra o RyzenTune de novo.`
      : "O driver PawnIO não está instalado, então não dá para ler nem ajustar o hardware. Reinstale o RyzenTune.";
  } else dv.hidden = true;
  const tv = $("#aviso-travamentos");
  if (travamentos.k41 > 0 || travamentos.whea > 0) {
    tv.hidden = false;
    tv.textContent = `Nos últimos 14 dias o Windows registrou ${travamentos.k41} desligamento(s) forçado(s) e ${travamentos.whea} erro(s) de hardware (WHEA). Se isso aconteceu sem overclock, resolva antes: senão não dá para saber se uma falha veio do ajuste.`;
  } else tv.hidden = true;

  $("#ficha-sistema").innerHTML = [
    ["Processador", `${cpu.nome}`], ["Núcleos", `${cpu.nucleos}`],
    ["Placa-mãe", `${hw.placa_fab || ""} ${hw.placa || ""}`], ["BIOS", hw.bios],
    ["Memória", `${hw.pentes} × ${Math.round(hw.gb / Math.max(1, hw.pentes))} GB`], ["Módulos", hw.modelo_ram],
  ].map(([a, b]) => `<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join("");

  const m = S.estado.mem;
  const p = m.estavel;
  const total = 10, feitos = new Set(m.feitos).size;
  $("#resumo-mem").innerHTML = m.confirmado
    ? `<p class="resumo-num">${p.freq} MT/s CL${p.tCL}</p>
       <p>${feitos} de ${total} ajustes com limite encontrado.</p>
       <p>${m.teste ? `<span class="etiqueta acao">Em andamento: ${esc(ETAPAS[m.teste.passo])}</span>` : `<span class="etiqueta">Nenhuma etapa aberta</span>`}</p>`
    : `<p>Leia os timings atuais e defina o ponto de partida para começar.</p>`;

  const c = S.estado.cpu;
  $("#resumo-cpu").innerHTML = !c.perfil.suporta_co
    ? `<p>Não disponível neste processador.</p>`
    : `<p class="resumo-num">${c.estavel}</p><p>Valor estável aplicado a cada boot.</p>
       <p>${c.teste ? `<span class="etiqueta acao">Testando ${c.teste.valor} (${c.teste.situacao === "pendente" ? "reinicie" : "ativo"})</span>` : c.feito ? `<span class="etiqueta ok">Limite encontrado</span>` : `<span class="etiqueta">Pronto para a próxima etapa</span>`}</p>`;
}

/* ---------------------------------------------------------------- memória */
function blocoTiming(rotulo, valor, destaque = false) {
  return `<div class="timing${destaque ? " destaque" : ""}"><b>${esc(valor)}</b><span>${esc(rotulo)}</span></div>`;
}

function desenharMemoria() {
  if (!S.init) return;
  const alvo = $("#timings-agora");
  const L = S.leitura;
  const m = S.estado.mem;
  if (!L) alvo.innerHTML = `<p class="vazio">Lendo os timings…</p>`;
  else if (L.erro) alvo.innerHTML = `<p class="vazio">Não consegui ler os timings: ${esc(L.erro)}</p>`;
  else {
    const t = L.timings, pm = L.pm || {};
    const mts = pm.mclk ? Math.round(pm.mclk * 2) : t.mts_ratio;
    alvo.innerHTML = [
      blocoTiming("MT/s", mts, true), blocoTiming("FCLK (MHz)", pm.fclk ? Math.round(pm.fclk) : "--", true),
      blocoTiming("GearDown", t.gdm ? "Ligado" : "Desligado"), blocoTiming("Comando", t.cmd2t ? "2T" : "1T"),
      ...["tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRC"].map((k) => blocoTiming(k, t[k])),
      blocoTiming(`tRFC (${Math.round((t.tRFC * 2000) / mts)} ns)`, t.tRFC),
      ...["tRRDS", "tRRDL", "tFAW", "tWTRS", "tWTRL", "tWR", "tRTP", "tCWL", "tRDRDSCL", "tWRWRSCL", "tREFI"].map((k) => blocoTiming(k, t[k])),
      blocoTiming("SoC (V)", pm.vsoc ? pm.vsoc.toFixed(3) : "--"),
    ].join("");
  }
  $("#ponto-partida").hidden = !(L && !L.erro) || (m.confirmado && !!m.teste);
  if (m.confirmado) $("#mem-usar").textContent = "Usar como novo ponto de partida";
  if (m.estavel?.vdram && !$("#vdram").dataset.mexido) $("#vdram").value = m.estavel.vdram;

  // perfil estável
  const p = m.estavel;
  $("#perfil-estavel").innerHTML = m.confirmado
    ? CAMPOS.filter((k) => !(k === "fclk" && !p.fclk)).map((k) => blocoTiming(NOMES[k] + (UNIDADE[k] ? ` (${UNIDADE[k]})` : ""), k === "gdm" ? (p[k] ? "Ligado" : "Desligado") : p[k])).join("")
    : `<p class="vazio">Ainda não definido.</p>`;
  $("#limites").textContent = m.feitos.length ? `Limite encontrado em: ${[...new Set(m.feitos)].map((f) => ETAPAS[f]).join(", ")}.` : "";

  desenharEtapaMem();
  desenharChip();
}

/* ---------------------------------------------------------------- inteligência */
let identificando = false, chipLidoNestaSessao = false;
async function identificarChip(forcar = false) {
  // lê os pentes uma vez por sessão mesmo com chip já salvo: assim a tela percebe se a escolha à mão
  // discorda do que o SPD diz
  if (identificando || (!forcar && chipLidoNestaSessao)) return;
  identificando = true;
  chipLidoNestaSessao = true;
  $("#chip-nome").textContent = "Lendo os pentes…";
  await chamar("memoria_identificar");
  identificando = false;
  desenharChip();
}

function desenharChip() {
  const m = S.estado.mem, c = m.chip, a = m.alvos;
  if (!c) { if (!identificando) $("#chip-nome").textContent = "Ainda não identificado."; return; }
  const cls = { alta: "ok", "média": "sinal", baixa: "acao" }[c.confianca] || "";
  $("#chip-nome").innerHTML = `${esc(c.nome)}<span class="etiqueta ${cls}">confiança ${esc(c.confianca)}</span>`;
  $("#chip-motivo").textContent = c.motivo + (a?.nota ? ` ${a.nota}` : "");
  const sel = $("#chip-escolha");
  if (sel.options.length) sel.value = c.chip;

  $("#chip-pentes").innerHTML = (c.pentes || []).map((p) => {
    const xmp = p.xmp ? `, XMP ${p.xmp.mts} CL${p.xmp.cl}` : "";
    return `<span class="pente">Slot ${p.slot + 1}: <b>${esc(p.modelo || "sem nome")}</b>, ${p.tamanho_gb ?? "?"} GB, ${p.ranks} rank${p.ranks > 1 ? "s" : ""}, chips ${esc(p.fabricante_dram)} ${p.densidade_gbit ?? "?"} Gb x${p.largura ?? "?"}${esc(xmp)}</span>`;
  }).join("");

  if (a) {
    const e = m.estavel, nsAtual = (e.tRFC * 2000) / e.freq;
    const itens = [
      ["Frequência", e.freq, a.freq, " MT/s", e.freq >= a.freq],
      ["tCL", e.tCL, a.tCL, "", e.tCL <= a.tCL],
      ["tRCDRD", e.tRCDRD, a.tRCDRD, "", e.tRCDRD <= a.tRCDRD],
      ["tRP", e.tRP, a.tRP, "", e.tRP <= a.tRP],
      ["tRFC", Math.round(nsAtual), a.trfc_ns, " ns", nsAtual <= a.trfc_ns + 1],
    ];
    $("#chip-previsao").innerHTML = `<div class="previsao">${itens.map(([n, agora, alvo, u, ok]) =>
      `<div class="prev${ok ? " chegou" : ""}"><span>${esc(n)}</span><b>${agora}</b><i>até</i><b class="alvo">${alvo}</b>${u ? `<span>${esc(u.trim())}</span>` : ""}</div>`).join("")}</div>`;
  } else $("#chip-previsao").innerHTML = "";

  const eco = m.economia || { usados: 0, linear: 0 };
  $("#chip-economia").textContent = eco.usados
    ? `A previsão começa cada ajuste no valor esperado para o seu chip e depois divide o intervalo ao meio. Até agora: ${eco.usados} reinício(s); de um em um seriam ${eco.linear}.`
    : "A previsão começa cada ajuste no valor esperado para o seu chip e depois divide o intervalo ao meio: menos reinícios para chegar ao mesmo resultado.";

  const med = m.medicoes || [];
  if (!med.length) { $("#medicoes").innerHTML = `<p class="vazio">Nenhuma medição ainda.</p>`; return; }
  const melhorLat = Math.min(...med.map((x) => x.lat_cas_ns));
  $("#medicoes").innerHTML = `<table class="tabela-medicoes"><thead><tr><th>Perfil</th><th>Latência CAS</th><th>tRFC</th><th>Banda</th><th>Quando</th></tr></thead><tbody>${
    [...med].reverse().map((x) => `<tr class="${x.lat_cas_ns === melhorLat ? "melhor" : ""}"><td>${x.freq} CL${x.tCL}-${x.tRCDRD}</td><td class="num">${x.lat_cas_ns.toFixed(2)} ns</td><td class="num">${x.trfc_ns} ns</td><td class="num">${x.gbps} GB/s</td><td>${esc(x.quando.replace("T", " ").slice(0, 16))}</td></tr>`).join("")
  }</tbody></table>`;
}

function marcarPassos(lista, atual, ordem) {
  const i = ordem.indexOf(atual);
  $$("li", lista).forEach((li, j) => {
    li.classList.toggle("feito", i >= 0 && j < i);
    li.classList.toggle("atual", j === i);
  });
}

function tabelaDiferencas(est, nov) {
  const linhas = CAMPOS.filter((k) => nov[k] !== est[k] && !(k === "fclk" && !nov.fclk))
    .map((k) => `<tr><td>${esc(NOMES[k])}</td><td class="num">${esc(est[k])}</td><td class="num novo">${esc(nov[k])}</td><td>${esc(UNIDADE[k] || "")}</td></tr>`);
  return `<table class="tabela-dif"><thead><tr><th>Campo na BIOS</th><th>Agora</th><th>Novo</th><th></th></tr></thead><tbody>${linhas.join("")}</tbody></table>`;
}

function desenharEtapaMem() {
  const m = S.estado.mem, t = m.teste, corpo = $("#etapa-corpo");
  const [onde, seFalhar] = S.init.bios;
  $("#mem-pular").hidden = $("#mem-cancelar").hidden = !t;
  const mapa = { preparada: "preparada", aplicada: "aplicada", divergente: "conferir", testar: "testar" };
  marcarPassos($("#mem-passos"), t ? mapa[t.situacao] : null, ["preparada", "aplicada", "conferir", "testar"]);

  if (!m.confirmado) { corpo.innerHTML = `<p>Defina o ponto de partida no quadro acima para o RyzenTune calcular o primeiro ajuste.</p>`; return; }
  if (!t) {
    const acabou = new Set(m.feitos).size >= 10;
    corpo.innerHTML = acabou
      ? `<p>Busca concluída. O perfil estável abaixo é o melhor que a sua memória aguentou.</p>`
      : `<p>O RyzenTune vai calcular o próximo valor mais agressivo, sempre a partir do último estável.</p>
         <div class="botoes"><button class="botao primario" id="mem-preparar">Preparar o próximo ajuste</button></div>`;
    $("#mem-preparar")?.addEventListener("click", () => chamar("mem_preparar").then((r) => r && !r.resultado && aviso("Busca concluída.", "ok")));
    return;
  }
  const titulo = `<p class="resumo-num">${esc(ETAPAS[t.passo])}</p>`;
  if (t.situacao === "preparada") {
    corpo.innerHTML = `${titulo}${tabelaDiferencas(m.estavel, t.perfil)}
      <p class="caminho-bios">${esc(onde)}</p>
      <p class="nota">Todos os outros campos ficam como estão. ${esc(seFalhar)}</p>
      <div class="botoes"><button class="botao primario" id="mem-bios">Reiniciar na BIOS</button>
      <button class="botao" id="mem-ja">Já apliquei e reiniciei</button></div>`;
    $("#mem-bios").onclick = async () => {
      if (await confirmar("Reiniciar na BIOS", "Salve seus trabalhos. O PC reinicia direto na BIOS em 5 segundos.\nFotografe a tabela antes, para digitar os valores.", "Reiniciar agora"))
        chamar("mem_reiniciar_bios");
    };
    $("#mem-ja").onclick = conferirMem;
  } else if (t.situacao === "aplicada") {
    corpo.innerHTML = `${titulo}<p>Quando o Windows voltar, o RyzenTune lê os timings e confere sozinho se a BIOS aplicou a etapa.</p>
      <div class="botoes"><button class="botao primario" id="mem-conf">Conferir agora</button></div>`;
    $("#mem-conf").onclick = conferirMem;
  } else if (t.situacao === "divergente") {
    const linhas = (t.diferencas || []).map((d) => `<tr><td>${esc(d.nome)}</td><td class="num">${esc(d.esperado)}</td><td class="num errado">${esc(d.lido)}</td></tr>`).join("");
    corpo.innerHTML = `${titulo}<p>A BIOS não aplicou tudo o que foi pedido:</p>
      <table class="tabela-dif"><thead><tr><th>Campo</th><th>Pedido</th><th>Na memória</th></tr></thead><tbody>${linhas}</tbody></table>
      <div class="botoes"><button class="botao primario" id="mem-bios2">Corrigir na BIOS</button>
      <button class="botao" id="mem-aceitar">Testar assim mesmo</button></div>`;
    $("#mem-bios2").onclick = async () => {
      if (await confirmar("Reiniciar na BIOS", "O PC reinicia direto na BIOS em 5 segundos.", "Reiniciar agora")) chamar("mem_reiniciar_bios");
    };
    $("#mem-aceitar").onclick = () => chamar("mem_aceitar_divergencia");
  } else if (t.situacao === "testar") {
    const rodando = S.teste?.rodando && S.teste.tipo === "memoria";
    corpo.innerHTML = `${titulo}<p>A memória ligou com os valores novos. Agora o teste: qualquer erro reprova a etapa e o RyzenTune volta ao último estável.</p>
      ${rodando ? "" : `<div class="linha-campos"><label>Duração <select id="etapa-min"><option value="15">15 min</option><option value="30" selected>30 min</option><option value="60">1 hora</option></select></label></div>
      <div class="botoes"><button class="botao primario" id="mem-testar">Testar a memória</button>
      <button class="botao perigo" id="mem-falhou">Travou ou deu erro</button></div>`}
      <div id="etapa-teste"></div>`;
    $("#mem-testar")?.addEventListener("click", () => iniciarTesteMem(+$("#etapa-min").value, 85));
    $("#mem-falhou")?.addEventListener("click", async () => {
      if (await confirmar("Marcar como falha", "A etapa será reprovada. Volte na BIOS para os valores do perfil estável (ou aplique a próxima etapa, que parte dele).", "Marcar como falha"))
        chamar("mem_resultado", false, "marcado como falha pelo usuário");
    });
    if (rodando) desenharTeste($("#etapa-teste"), S.teste);
  }
}

async function conferirMem() {
  const r = await chamar("mem_conferir");
  const s = r?.resultado?.situacao;
  if (s === "testar") aviso("A BIOS aplicou a etapa. Agora é hora do teste.", "ok");
  else if (s === "falhou") aviso("A memória voltou ao padrão: a etapa não ligou e foi marcada como falha.", "erro");
  else if (s === "divergente") aviso("Alguns valores ficaram diferentes do pedido.", "erro");
}

/* ---------------------------------------------------------------- processador */
function desenharCpu() {
  if (!S.init) return;
  const c = S.estado.cpu, perfil = c.perfil || {}, t = c.teste;
  const x = $("#cpu-explica");
  if (!perfil.suporta_co) {
    x.innerHTML = `<h3>Não disponível</h3><p>${perfil.geracao === "zen3"
      ? "O RyzenTune não conseguiu falar com o controlador deste processador. Confira o aviso do driver no Painel."
      : "O Curve Optimizer só existe na série Ryzen 5000. Neste processador, a memória é onde está o ganho."}</p>`;
    $("#bloco-cpu-etapa").hidden = true;
  } else {
    x.innerHTML = `<h3>Como funciona</h3><p>${perfil.x3d ? "Processadores X3D têm o multiplicador travado, então não dá para subir o clock à força. " : ""}Um Curve Optimizer negativo diminui a tensão de cada núcleo: o processador esquenta menos e segura o boost alto por mais tempo.</p>
      <p>O valor é aplicado pelo RyzenTune logo depois que você entra no Windows e some quando o PC desliga. Um valor ruim nunca impede o PC de ligar, e se o Windows registrar travamento ou erro de hardware o RyzenTune volta sozinho ao último valor estável.</p>`;
    $("#bloco-cpu-etapa").hidden = false;
  }

  const co = S.leitura?.co;
  $("#co-fonte").textContent = co ? "Lido do processador agora" : "Leitura por núcleo indisponível neste firmware";
  const valores = co || Array.from({ length: perfil.nucleos || 8 }, () => null);
  $("#co-barras").innerHTML = valores.map((v, i) => `<div class="barra"><div class="tubo"><i style="height:${v == null ? 0 : (Math.abs(v) / 30) * 100}%"></i></div><b>${v == null ? "--" : v}</b><span>Núcleo ${i}</span></div>`).join("");

  const passo = !t ? "preparar" : t.situacao;
  marcarPassos($("#cpu-passos"), t ? passo : null, ["preparar", "pendente", "ativo"]);
  const corpo = $("#cpu-corpo");
  if (!t) {
    const prox = [-5, -10, -15, -20, -25, -30].find((v) => v < c.estavel);
    corpo.innerHTML = c.feito || prox === undefined
      ? `<p>Busca concluída. O valor estável <b>${c.estavel}</b> é aplicado a cada boot.</p>`
      : `<p>Estável agora: <b>${c.estavel}</b>. Próximo valor a testar: <b>${prox}</b>, em todos os núcleos.</p>
         <div class="botoes"><button class="botao primario" id="cpu-preparar">Preparar ${prox}</button></div>`;
    $("#cpu-preparar")?.addEventListener("click", () => chamar("cpu_preparar"));
  } else if (t.situacao === "pendente") {
    corpo.innerHTML = `<p class="resumo-num">${t.valor}</p><p>Preparado. Ele entra em vigor no próximo boot.</p>
      <div class="botoes"><button class="botao primario" id="cpu-reiniciar">Reiniciar agora</button>
      <button class="botao fantasma" id="cpu-cancelar">Cancelar</button></div>`;
    $("#cpu-reiniciar").onclick = async () => {
      if (await confirmar("Reiniciar", "Salve seus trabalhos. O PC reinicia em 5 segundos.", "Reiniciar agora")) chamar("cpu_reiniciar");
    };
    $("#cpu-cancelar").onclick = () => chamar("cpu_cancelar");
  } else {
    const rodando = S.teste?.rodando && S.teste.tipo === "nucleos";
    corpo.innerHTML = `<p class="resumo-num">${t.valor}</p><p>Ativo desde ${esc(t.desde.replace("T", " "))}. Teste os núcleos e depois use o PC normalmente por um ou dois dias: instabilidade de Curve Optimizer costuma aparecer com o PC parado ou em carga leve.</p>
      ${rodando ? "" : `<div class="botoes"><button class="botao primario" id="cpu-testar">Testar os núcleos</button>
      <button class="botao" id="cpu-passou">Passou: usei 1-2 dias sem travar</button>
      <button class="botao perigo" id="cpu-falhou">Travou ou deu erro</button></div>`}
      <div id="cpu-teste"></div>`;
    $("#cpu-testar")?.addEventListener("click", () => iniciarTesteCpu(180));
    $("#cpu-passou")?.addEventListener("click", () => chamar("cpu_resultado", true, ""));
    $("#cpu-falhou")?.addEventListener("click", async () => {
      if (await confirmar("Marcar como falha", "No próximo boot volta para o último valor estável.", "Marcar como falha")) chamar("cpu_resultado", false, "marcado como falha pelo usuário");
    });
    if (rodando) desenharTeste($("#cpu-teste"), S.teste);
  }
}

/* ---------------------------------------------------------------- testes */
async function iniciarTesteMem(min, pct) {
  const r = await chamar("teste_memoria", min, pct);
  if (r) { aviso(`Testando ${(r.mb / 1024).toFixed(1)} GB de memória.`); S.teste = { rodando: true, tipo: "memoria", fracao: 0, erros: 0 }; desenhar(); desenharPainelTeste(); }
}
async function iniciarTesteCpu(seg) {
  const r = await chamar("teste_nucleos", seg);
  if (r) { aviso(`Testando ${r.nucleos.length} núcleos.`); S.teste = { rodando: true, tipo: "nucleos", fracao: 0, erros: 0, nucleos: {} }; desenhar(); desenharPainelTeste(); }
}

function desenharTeste(alvo, s) {
  if (!alvo) return;
  const pct = Math.round((s.fracao || 0) * 100);
  const cor = s.erros > 0 ? "var(--erro)" : s.resultado === "passou" ? "var(--ok)" : "var(--sinal)";
  const anel = `<svg class="anel" viewBox="0 0 150 150"><circle class="anel-fundo" cx="75" cy="75" r="62"/>
    <circle class="anel-valor" cx="75" cy="75" r="62" style="stroke:${cor};stroke-dashoffset:${389.6 * (1 - (s.fracao || 0))}px"/>
    <text x="75" y="75">${pct}%</text></svg>`;
  let corpo;
  if (s.tipo === "memoria") {
    corpo = `<div class="metricas"><div class="${s.erros ? "com-erro" : ""}"><b>${s.erros ?? 0}</b><span>erros</span></div>
      <div><b>${s.gbps ?? 0}</b><span>GB/s</span></div><div><b>${s.ciclo ?? 0}</b><span>ciclos</span></div>
      <div><b>${s.mb ? (s.mb / 1024).toFixed(1) : "--"}</b><span>GB em teste</span></div></div>
      <p class="nota">${s.padrao ? `Padrão: ${esc(s.padrao)}` : "Reservando a memória…"}</p>`;
  } else {
    const n = s.nucleos || {};
    corpo = `<div class="nucleos-grade">${Object.entries(n).map(([cpu, est], i) => `<div class="nucleo ${est}">${i}</div>`).join("")}</div>
      <div class="metricas"><div class="${s.erros ? "com-erro" : ""}"><b>${s.erros ?? 0}</b><span>erros</span></div></div>`;
  }
  const fim = s.resultado ? `<p><span class="etiqueta ${s.resultado === "passou" ? "ok" : s.resultado === "falhou" ? "erro" : ""}">${{ passou: "Passou", falhou: "Falhou", parado: "Parado" }[s.resultado]}</span> ${esc(s.msg || "")}</p>`
    : `<div class="botoes"><button class="botao perigo pequeno" data-parar>Parar o teste</button></div>`;
  alvo.innerHTML = `<div class="progresso-teste">${anel}<div>${corpo}${fim}</div></div>`;
  alvo.querySelector("[data-parar]")?.addEventListener("click", () => chamar("teste_parar"));
}

function desenharPainelTeste() {
  const p = $("#painel-teste");
  if (!S.teste || (!S.teste.rodando && !S.teste.resultado)) { p.hidden = true; return; }
  p.hidden = false;
  desenharTeste(p, S.teste);
  $("#t-mem").disabled = $("#t-cpu").disabled = !!S.teste.rodando;
}

async function laçoTeste() {
  let estavaRodando = false;
  while (true) {
    try {
      const s = await api.teste_status();
      // "ativo" = rodando ou terminou mas o resultado ainda está sendo salvo (registrado === false)
      const ativo = !!s && !s.erro && (s.rodando || s.registrado === false);
      if (s && !s.erro && (ativo || estavaRodando)) {
        S.teste = s;
        desenharPainelTeste();
        desenharTeste($("#etapa-teste"), s);
        desenharTeste($("#cpu-teste"), s);
        if (S.pagina === "assistente") { if ($("#ass-teste") && ativo) { if (s.tipo === "memoria") desenharTesteAssistente($("#ass-teste"), s); else desenharTeste($("#ass-teste"), s); } else desenharAssistente(); }
        if (estavaRodando && !ativo) {
          aviso(s.resultado === "passou" ? "Teste concluído sem erros." : s.resultado === "falhou" ? `O teste falhou. ${s.msg || ""}` : "Teste parado.",
            s.resultado === "passou" ? "ok" : s.resultado === "falhou" ? "erro" : "");
          const e = await api.obter_estado();
          if (e && !e.erro) { S.estado = e; desenhar(); }
        }
        estavaRodando = ativo;
      }
    } catch (_) { /* segue */ }
    await espera(estavaRodando ? 700 : 2000);
  }
}

/* ---------------------------------------------------------------- histórico e ajustes */
function desenharHistorico() {
  const h = [...S.estado.historico].reverse();
  $("#historico").innerHTML = h.length ? h.map((x) => {
    const cls = /^PASSOU/.test(x.texto) ? "passou" : /^FALHOU/.test(x.texto) ? "falhou" : "";
    return `<li class="${cls}"><time>${esc(x.quando.replace("T", " "))}, ${esc(x.tipo.toLowerCase())}</time>${esc(x.texto)}</li>`;
  }).join("") : `<li>Nada por aqui ainda. O histórico começa quando você define o ponto de partida da memória.</li>`;
}

function desenharAjustes() {
  const c = S.estado.config;
  $("#cfg-atualizar").checked = !!c.verificar_atualizacao;
  $("#cfg-animacoes").checked = c.animacoes !== false;
  $("#cfg-avancado").checked = !!c.avancado;
  const d = S.init.driver;
  $("#ficha-driver").innerHTML = [["Driver PawnIO", d.instalado ? `Instalado (${d.versao || "versão ?"})` : "Não instalado"],
    ["Acesso", d.ok ? "Funcionando" : `Indisponível${d.erro ? `: ${d.erro}` : ""}`],
    ["Codinome", S.init.cpu.codinome || "--"]].map(([a, b]) => `<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join("");
}

async function verificarAtualizacao(manual) {
  const r = await (manual ? chamar("atualizacao_verificar") : api.atualizacao_verificar().catch(() => null));
  if (!r || r.erro) { if (manual) $("#cfg-atualizacao-msg").textContent = "Não consegui verificar agora."; return; }
  if (r.nova && (manual || r.nova.versao !== S.estado.config.versao_ignorada)) {
    $("#faixa-texto").textContent = `A versão ${r.nova.versao} está disponível. Você tem a ${r.atual}.`;
    $("#faixa-atualizacao").hidden = false;
  } else if (manual) $("#cfg-atualizacao-msg").textContent = r.configurado ? `Você já tem a versão mais nova (${r.atual}).` : "Versão de desenvolvimento.";
}

async function instalarAtualizacao() {
  if (!(await confirmar("Instalar a atualização", "O RyzenTune vai fechar, instalar e abrir de novo. Seus dados ficam.", "Instalar"))) return;
  if (!(await chamar("atualizacao_instalar"))) return;
  const t = $("#faixa-texto");
  $("#faixa-instalar").disabled = true;
  while (true) {
    const s = await api.atualizacao_status();
    if (s.estado === "erro") { t.textContent = `A atualização falhou: ${s.msg}`; $("#faixa-instalar").disabled = false; return; }
    t.textContent = s.estado === "instalando" ? "Instalando…" : `Baixando… ${Math.round((s.fracao || 0) * 100)}%`;
    await espera(400);
  }
}

/* ---------------------------------------------------------------- eventos fixos */
function ligarEventos() {
  $$(".nav").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.pagina)));
  $$("[data-ir]").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.ir)));
  $("#mem-ler").onclick = lerTimings;
  $("#vdram").addEventListener("input", (e) => { e.target.dataset.mexido = "1"; });
  $("#mem-usar").onclick = async () => {
    const v = parseFloat($("#vdram").value);
    if (!(v >= 1.1 && v <= 1.45)) { aviso("Digite a tensão da memória entre 1,10 e 1,45 V.", "erro"); return; }
    if (S.estado.mem.confirmado && !(await confirmar("Novo ponto de partida", "A busca recomeça a partir dos valores que estão rodando agora.", "Usar estes valores"))) return;
    const r = await chamar("mem_usar_hardware", v);
    if (r) aviso("Ponto de partida salvo.", "ok");
  };
  $("#mem-pular").onclick = () => pularComConfirmacao();
  $("#chip-ler").onclick = () => identificarChip(true);
  $("#chip-escolha").onchange = (e) => chamar("memoria_escolher_chip", e.target.value);
  $("#mem-medir").onclick = async (e) => {
    e.target.disabled = true;
    e.target.textContent = "Medindo…";
    const r = await chamar("memoria_medir");
    e.target.disabled = false;
    e.target.textContent = "Medir o perfil atual";
    if (r) aviso(`Banda medida: ${r.resultado.gbps} GB/s.`, "ok");
  };
  $("#mem-cancelar").onclick = () => chamar("mem_cancelar");
  $("#mem-recomecar").onclick = async () => {
    if (await confirmar("Recomeçar a busca", "Os limites encontrados são esquecidos e a busca recomeça a partir do perfil estável.", "Recomeçar")) chamar("mem_recomecar");
  };
  $("#cpu-zerar").onclick = async () => {
    if (await confirmar("Voltar para 0", "O Curve Optimizer volta para 0 a partir do próximo boot.", "Voltar para 0")) chamar("cpu_zerar");
  };
  $("#cpu-recomecar").onclick = () => chamar("cpu_recomecar");
  $("#t-mem").onclick = () => iniciarTesteMem(+$("#t-mem-min").value, +$("#t-mem-pct").value);
  $("#t-cpu").onclick = () => iniciarTesteCpu(+$("#t-cpu-seg").value);
  $("#cfg-atualizar").onchange = (e) => chamar("config", "verificar_atualizacao", e.target.checked);
  $("#cfg-avancado").onchange = (e) => chamar("config", "avancado", e.target.checked);
  $("#cfg-animacoes").onchange = async (e) => { await chamar("config", "animacoes", e.target.checked); aplicarAnimacoes(); };
  $("#cfg-verificar").onclick = () => verificarAtualizacao(true);
  $("#cfg-pasta").onclick = () => chamar("abrir_pasta_dados");
  $("#cfg-codigo").onclick = () => chamar("abrir_link", `https://github.com/${S.init.repo}`);
  $("#faixa-instalar").onclick = instalarAtualizacao;
  $("#faixa-depois").onclick = () => { $("#faixa-atualizacao").hidden = true; };
  document.addEventListener("keydown", (e) => { if (e.key === "F5") e.preventDefault(); });
  document.addEventListener("contextmenu", (e) => e.preventDefault());
}

/* ---------------------------------------------------------------- partida */
ligarEventos();
window.addEventListener("pywebviewready", () => { api = window.pywebview.api; iniciar(); });
if (new URLSearchParams(location.search).has("demo")) {
  import("./demo.js").then((m) => { api = m.criarDemo(); iniciar(); });
}
