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
    // O registrador (mts_ratio) é exato. A tabela de energia às vezes vem deslocada (ex.: 1708 em vez de 1600 MHz):
    // se as duas discordarem em mais de 3%, a tabela é ignorada e o FCLK fica com o último valor salvo.
    const pmConfere = pm.mclk && t.mts_ratio && Math.abs(pm.mclk * 2 / t.mts_ratio - 1) < 0.03;
    atual.freq = t.mts_ratio || (pm.mclk ? Math.round(pm.mclk * 2) : atual.freq);
    if (pm.fclk && pmConfere) atual.fclk = Math.round(pm.fclk);
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

/* ---------------------------------------------------------------- peças das telas novas */
const PRINCIPAIS = { freq: ["freq", "fclk"], grupoRRD: ["tRRDS", "tRRDL", "tFAW"], grupoWTR: ["tWTRS", "tWTRL"], tWR: ["tWR", "tRTP"] };
const TELA_OC = ["freq", "fclk", "vdram", "vsoc", "gdm"];
const ICONE = {
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  placa: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 7h4v4H7zM14 7h3M14 10h3M7 15h10M7 18h6"/>',
  ram: '<rect x="3" y="7" width="18" height="10" rx="1"/><path d="M7 7v10M11 7v10M15 7v10M6 17v3M18 17v3"/>',
  vel: '<path d="M4 15a8 8 0 0 1 16 0"/><path d="M12 15l4-5"/><path d="M4 19h16"/>',
};
/* nomes curtos para a grade da BIOS: cabem numa linha ao lado da sigla */
const CURTO_BIOS = {
  freq: "Velocidade da memória", fclk: "Barramento interno", vdram: "Tensão da memória", vsoc: "Tensão do controlador",
  gdm: "Modo GearDown", tCL: "Atraso de leitura", tRCDRD: "Abrir uma linha (leitura)", tRCDWR: "Abrir uma linha (escrita)",
  tRP: "Fechar uma linha", tRAS: "Linha aberta, mínimo", tRC: "Ciclo completo da linha", tRFC: "Recarga da memória",
  tRRDS: "Ativações, outro grupo", tRRDL: "Ativações, mesmo grupo", tFAW: "Janela de 4 ativações",
  tWTRS: "Escrever → ler, outro grupo", tWTRL: "Escrever → ler, mesmo grupo", tWR: "Recuperar após escrever",
  tRTP: "Ler → fechar a linha", tCWL: "Atraso de escrita",
};
const nomeCurtoBios = (k) => `${esc(CURTO_BIOS[k] || TERMOS[k][0])} <span class="sigla">${esc(TERMOS[k][1])}</span>`;
const nomeComBios = (k) => `${esc(TERMOS[k][0])} <span class="sigla">${esc(TERMOS[k][1])}</span>`;
const valorOuNada = (k, v) => (v == null || v === "" ? '<span class="nao-lido">?</span>' : esc(fmt(k, v)));

function nomeCpuCurto(nome) {
  return String(nome || "Processador").replace(/^AMD\s+/, "").replace(/\s+\d+-Core Processor$/i, "").trim();
}

/* Ficha do PC: 4 peças. Cada uma aceita texto, "carregando" (null) ou falta de leitura (""). */
function fichaPc({ mts, tCL, carregando }) {
  const hw = S.init.hw || {}, cpu = S.init.cpu || {}, c = S.estado.mem.chip;
  const pecas = [
    ["cpu", "Processador", nomeCpuCurto(hw.cpu || cpu.nome), `${hw.nucleos || cpu.nucleos || "?"} núcleos${cpu.codinome ? `, ${cpu.codinome}` : ""}`],
    ["placa", "Placa-mãe", `${S.init.placa || ""} ${String(hw.placa || "").replace(/\s*\(.*\)$/, "")}`.trim() || "Não identificada", hw.bios ? `BIOS ${hw.bios}` : ""],
    ["ram", "Memória", hw.pentes ? `${hw.pentes} × ${Math.round(hw.gb / hw.pentes)} GB` : "Pentes não encontrados",
      c?.nome || "Chip não identificado"],
    ["vel", "Rodando hoje", carregando ? null : mts ? `${mts} MT/s` : "", carregando ? null : tCL ? `Atraso de leitura (tCL) ${tCL}` : "Não consegui ler"],
  ];
  return `<ul class="ficha-pc">${pecas.map(([ic, rot, val, sub]) => `<li class="${val === "" ? "falta" : ""}">
      <svg viewBox="0 0 24 24" aria-hidden="true">${ICONE[ic]}</svg>
      <span class="rot">${rot}</span>
      <b>${val == null ? '<span class="lendo">Lendo…</span>' : esc(val || "Não lido")}</b>
      <span class="sub">${sub == null ? "&nbsp;" : esc(sub)}</span></li>`).join("")}</ul>`;
}

/* "Digite na BIOS": o ajuste principal grande e o resto numa grade numerada que cabe numa foto. */
function listaBios(lista, passo) {
  const chaves = PRINCIPAIS[passo] || [passo];
  const principal = lista.filter((x) => chaves.includes(x.k));
  const resto = lista.filter((x) => !chaves.includes(x.k));
  let n = 0;
  const item = ({ k, de, para }) => `<li><i>${++n}</i><span class="nome">${nomeCurtoBios(k)}</span>
      <span class="de">${valorOuNada(k, de)}</span><span class="para">${esc(fmt(k, para))}</span></li>`;
  const grupo = (titulo, itens) => (itens.length ? `<h4>${titulo}</h4><ol class="bios-grade">${itens.map(item).join("")}</ol>` : "");
  const topo = principal.map(({ k, de, para }) => `<div class="bios-principal-item"><i>${++n}</i>
      <span class="nome">${nomeComBios(k)}</span>
      <span class="troca"><span class="de">${valorOuNada(k, de)}</span><span class="seta" aria-label="mude para">→</span>
      <b>${esc(fmt(k, para))}</b><small>${esc(UN[k] || "")}</small></span></div>`).join("");
  return `${topo ? `<div class="bios-principal">${topo}</div>` : ""}
    ${resto.length ? `<p class="bios-resto">${principal.length ? `Os outros ${resto.length} acompanham a mudança.` : ""} Digite cada um no campo com o nome em destaque.</p>` : ""}
    ${grupo("Frequência e tensões", resto.filter((x) => TELA_OC.includes(x.k)))}
    ${grupo("Timings", resto.filter((x) => !TELA_OC.includes(x.k)))}`;
}

/* Teste de memória dentro do assistente: monta uma vez e depois só atualiza os números (o anel desliza). */
const ANEL_C = 2 * Math.PI * 88;
function desenharTesteAssistente(alvo, s) {
  if (!alvo) return;
  if (!alvo.firstElementChild) {
    alvo.innerHTML = `<div class="teste-ass">
        <div class="teste-anel">
          <svg viewBox="0 0 200 200" aria-hidden="true"><circle class="fundo" cx="100" cy="100" r="88"/>
            <circle class="valor" cx="100" cy="100" r="88" style="stroke-dasharray:${ANEL_C.toFixed(1)}px;stroke-dashoffset:${ANEL_C.toFixed(1)}px"/></svg>
          <div class="centro"><b data-t="pct">0%</b><span data-t="resta"></span></div>
        </div>
        <dl class="teste-numeros">
          <div data-t="caixa-erros"><dt>Erros encontrados</dt><dd data-t="erros">0</dd><span data-t="erros-nota">Zero é o esperado</span></div>
          <div><dt>Velocidade de leitura e escrita</dt><dd><span data-t="gbps">--</span> <small>GB/s</small></dd><span data-t="ciclo"></span></div>
          <div><dt>Memória em teste</dt><dd><span data-t="gb">--</span> <small>GB</small></dd><span data-t="padrao"></span></div>
        </dl>
      </div>
      <p class="teste-aviso" data-t="aviso" role="status"></p>
      <button class="link perigo" data-t="parar">Parar o teste</button>`;
    alvo.querySelector('[data-t="parar"]').onclick = async () => {
      if (await confirmar("Parar o teste", "O ajuste continua esperando um teste completo. Você pode começar de novo depois.", "Parar")) chamar("teste_parar");
    };
  }
  const q = (k) => alvo.querySelector(`[data-t="${k}"]`);
  const f = Math.max(0, Math.min(1, s.fracao || 0)), erros = s.erros || 0, reservando = !s.padrao && f === 0;
  const anel = alvo.querySelector(".teste-anel .valor");
  anel.style.strokeDashoffset = `${(ANEL_C * (1 - f)).toFixed(1)}px`;
  alvo.querySelector(".teste-ass").classList.toggle("com-erro", erros > 0);
  q("pct").textContent = reservando ? "--" : `${Math.round(f * 100)}%`;
  const min = Math.ceil((s.minutos || 30) * (1 - f));
  q("resta").textContent = reservando ? "preparando" : s.rodando ? (min <= 1 ? "falta menos de 1 min" : `faltam ${min} min`) : "concluído";
  q("erros").textContent = erros;
  q("erros-nota").textContent = erros ? "Este valor não aguentou" : "Zero é o esperado";
  q("gbps").textContent = s.gbps ? Number(s.gbps).toFixed(1).replace(".", ",") : "--";
  q("ciclo").textContent = s.ciclo ? `Volta ${s.ciclo} pela memória` : "";
  q("gb").textContent = s.mb ? (s.mb / 1024).toFixed(1).replace(".", ",") : "--";
  q("padrao").textContent = s.padrao ? `Padrão ${s.padrao}` : "";
  q("aviso").textContent = erros
    ? `Encontrou ${erros} ${erros === 1 ? "erro" : "erros"}. Este valor não é estável: o RyzenTune volta para o último que passou e tenta um intermediário.`
    : reservando ? `Reservando ${s.mb ? `${(s.mb / 1024).toFixed(1).replace(".", ",")} GB` : "a memória livre"}. Isso leva alguns segundos.`
    : "Pode deixar o PC sozinho. Não abra jogos nem programas pesados até terminar.";
  q("aviso").className = `teste-aviso${erros ? " erro" : ""}`;
  q("parar").hidden = !s.rodando;
}

/* Resultado: três medidas, antes e depois, com a direção do que é melhor. */
let medindo = false, erroMedir = "";
async function medirDeNovo() {
  medindo = true; erroMedir = ""; desenharAssistente();
  const r = await api.memoria_medir().catch((ex) => ({ erro: String(ex) }));
  medindo = false;
  if (!r || r.erro) erroMedir = r ? r.erro : "sem resposta";
  else if (r.estado) S.estado = r.estado;
  desenharAssistente();
}

function linhaComparacao(rotulo, sigla, antes, depois, un, casas, menorMelhor, estado = "") {
  const tem = antes != null && depois != null;
  const ganho = tem ? ((menorMelhor ? antes / depois : depois / antes) - 1) * 100 : null;
  const max = tem ? Math.max(antes, depois) : 1;
  const num = (v) => (v == null ? "--" : Number(v).toFixed(casas).replace(".", ","));
  const etiqueta = estado ? `<span class="ganho-tag neutro">${estado}</span>`
    : ganho == null ? '<span class="ganho-tag neutro">sem medida</span>'
    : `<span class="ganho-tag ${ganho >= 0.5 ? "melhor" : ganho <= -0.5 ? "pior" : "neutro"}">${ganho >= 0.5 ? "+" : ""}${Math.round(ganho)}% ${ganho >= 0.5 ? "melhor" : ganho <= -0.5 ? "pior" : "igual"}</span>`;
  return `<li><div class="cmp-rotulo"><b>${rotulo}</b><span>${sigla}</span></div>
    <div class="cmp-barras">
      <div class="cmp-linha antes"><span>Antes</span><i style="width:${tem ? (antes / max) * 100 : 0}%"></i><b>${num(antes)}</b></div>
      <div class="cmp-linha depois"><span>Agora</span><i style="width:${tem ? (depois / max) * 100 : 0}%"></i><b>${estado ? "…" : num(depois)}</b></div>
    </div>
    <div class="cmp-fim"><small>${un}</small>${etiqueta}</div></li>`;
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
    const ficha = fichaPc({ mts, tCL: tm?.tCL, carregando: !L });
    if (L?.erro) {
      return { chave: "m-inicio-erro", titulo: "Não consegui ler a memória",
        texto: "Outro programa de monitoramento pode estar usando o mesmo acesso. Feche HWiNFO, ZenTimings ou Ryzen Master, se estiverem abertos, e leia de novo.",
        html: `${ficha}<p class="nota">Detalhe para suporte: ${esc(L.erro)}</p>`,
        primario: ["Ler a memória de novo", () => { S.leitura = null; desenharAssistente(); return lerTimings(); }] };
    }
    const semChip = !c || c.chip === "generico" || !m.alvos;
    const previsao = !L ? "" : semChip
      ? `<p class="previsao-ass neutra">Não deu para saber o tipo de chip pelos pentes. A busca funciona igual, só leva alguns ajustes a mais.</p>`
      : `<p class="previsao-ass">Pelo tipo de chip, a sua memória deve chegar perto de <b>${m.alvos.freq} MT/s</b> com atrasos menores que os de hoje.</p>`;
    const html = `${ficha}${previsao}
      <div class="campo-tensao-ass${L ? "" : " desligado"}">
        <label for="ass-vdram">Tensão da memória <span class="sigla">DRAM Voltage</span></label>
        <span class="entrada"><input type="number" id="ass-vdram" step="0.005" min="1.10" max="1.45" value="${xmpV || 1.35}" ${L ? "" : "disabled"}> V</span>
        <p>Veja na BIOS, perto da velocidade. Com XMP ligado, quase sempre é 1,35 V.</p>
      </div>`;
    return { chave: `m-inicio-${L ? "ok" : "lendo"}`,
      titulo: "Confira o seu PC e comece",
      texto: "O RyzenTune já leu as peças. Só falta a tensão da memória, que ele não consegue ler sozinho.",
      html, primario: ["Começar", async () => {
        const v = parseFloat(String($("#ass-vdram").value).replace(",", "."));
        if (!(v >= 1.1 && v <= 1.45)) { aviso("A tensão precisa estar entre 1,10 e 1,45 V. Confira o valor de DRAM Voltage na BIOS.", "erro"); return; }
        if (await chamar("mem_usar_hardware", v)) await chamar("mem_preparar");
      }], primarioDesligado: !L,
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
    const chave = `m-prep-${t.passo}-${t.perfil[t.passo] ?? ""}`;
    const avisoLeitura = !L ? `<p class="aviso-leitura">Lendo o que está rodando agora. Por enquanto, o número antes da seta é o último valor salvo.</p>`
      : L.erro ? `<p class="aviso-leitura erro" title="${esc(L.erro)}">Não consegui ler a memória agora. O número antes da seta é o último valor salvo; os valores novos, em laranja, estão certos.</p>` : "";
    if (!lista.length) {
      return { chave: `${chave}-igual`, ...topo(1, 3), titulo: "A BIOS já está com esses valores",
        html: `${ultimoResultado("Memória")}${avisoLeitura}<p class="texto">Nada para digitar desta vez. O próximo passo é conferir e testar <b>${esc(nome)}</b>.</p>`,
        primario: ["Conferir e testar", conferirMem], links: [["Pular este ajuste", () => chamar("mem_pular")]] };
    }
    return { chave, ...topo(1, 3), larga: lista.length > 6,
      titulo: lista.length === 1 ? "Mude 1 valor na BIOS" : `Mude ${lista.length} valores na BIOS`,
      html: `${ultimoResultado("Memória")}
        <p class="texto">Agora vamos melhorar <b>${esc(nome)}</b>. Tire uma foto desta tela com o celular antes de reiniciar.</p>
        ${avisoLeitura}${listaBios(lista, t.passo)}
        <p class="dica"><b>Onde fica na BIOS:</b> ${esc(onde)}</p>`,
      primario: ["Reiniciar na BIOS", async () => {
        if (await confirmar("Reiniciar na BIOS", "Salve o que estiver aberto. O PC reinicia direto na BIOS em 5 segundos.", "Reiniciar agora"))
          chamar("mem_reiniciar_bios");
      }],
      links: [["Já mudei e reiniciei", conferirMem], ["Pular este ajuste", () => chamar("mem_pular")]],
      detalhes: `Todos os outros campos ficam como estão. ${seFalhar}` };
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
  const st = S.teste?.tipo === "memoria" ? S.teste : null;
  const rodando = !!st?.rodando, terminou = !!st && !st.rodando && ["passou", "falhou"].includes(st.resultado);
  if (rodando || terminou) {
    const comErro = (st.erros || 0) > 0 || st.resultado === "falhou";
    return { chave: "m-testar-rodando", ...topo(3, 3),
      titulo: comErro ? "O teste encontrou erros" : terminou ? "Teste concluído" : "Testando a memória",
      html: `<div id="ass-teste" class="ass-teste"></div>` };
  }
  return { chave: "m-testar-parado", ...topo(3, 3),
    titulo: "A BIOS aceitou. Agora o teste",
    html: `<p class="texto">O teste escreve e confere quase toda a memória livre por <b>30 minutos</b>, usando todos os núcleos. Feche jogos e programas pesados antes de começar.</p>
      <ul class="resumo-teste"><li><b>30</b><span>minutos</span></li><li><b>85%</b><span>da memória livre</span></li><li><b>0</b><span>erros para passar</span></li></ul>`,
    primario: ["Começar o teste", () => iniciarTesteMem(30, 85)],
    links: [["O PC travou ou reiniciou sozinho", async () => {
      if (await confirmar("Travou?", "O ajuste será reprovado e o RyzenTune volta ao último valor bom.", "Sim, travou"))
        chamar("mem_resultado", false, "o PC travou (informado por você)");
    }]] };
}

function telaMemoriaPronta() {
  const m = S.estado.mem, med = m.medicoes || [], p = m.estavel, c = S.estado.cpu;
  const ini = med[0], fim = med.length > 1 ? med[med.length - 1] : null;
  const fimAtual = fim && fim.freq === p.freq && fim.tCL === p.tCL ? fim : null;  // medição antiga não vale como "agora"
  const latAgora = Math.round((p.tCL * 2000 / p.freq) * 100) / 100;
  const ganhou = ini && (p.freq > ini.freq || latAgora < ini.lat_cas_ns);
  const html = `
    ${!ini ? `<p class="aviso-leitura">Não há uma medição de antes da busca, então não dá para mostrar o ganho em números. Os números de "Agora" valem para os valores atuais.</p>` : ""}
    ${erroMedir ? `<p class="aviso-leitura erro" title="${esc(erroMedir)}">Não consegui medir a banda agora. Feche jogos e programas pesados e clique em "Medir de novo".</p>` : ""}
    <ol class="comparacao">
      ${linhaComparacao("Velocidade", "DRAM Frequency", ini?.freq, p.freq, "MT/s", 0, false)}
      ${linhaComparacao("Tempo de resposta", "latência do tCL", ini?.lat_cas_ns, latAgora, "ns", 2, true)}
      ${linhaComparacao("Banda", "leitura e escrita", ini?.gbps, fimAtual?.gbps, "GB/s", 1, false, medindo ? "medindo…" : "")}
    </ol>
    <p class="texto">Os valores já estão salvos na BIOS e valem toda vez que o PC liga. Não precisa fazer mais nada na memória.</p>`;
  const proxCpu = c.perfil?.suporta_co && !c.feito && !c.teste;
  return { chave: "m-pronta", topoEsq: "Concluído", topoDir: `${new Set(m.feitos).size} ajustes`, fracao: 1,
    titulo: ganhou ? "Pronto: sua memória ficou mais rápida" : "Pronto: sua memória está no melhor ponto que aguentou",
    html,
    primario: proxCpu ? ["Ajustar o processador agora", () => trocarTrilha("processador")]
      : !fimAtual && !medindo ? ["Medir a banda agora", medirDeNovo] : null,
    links: [...(proxCpu || fimAtual ? [[medindo ? "Medindo…" : "Medir de novo", () => { if (!medindo) medirDeNovo(); }]] : []), ["Recomeçar do zero", async () => {
      if (await confirmar("Recomeçar do zero", "A busca recomeça a partir dos valores atuais. Os limites encontrados são esquecidos.", "Recomeçar")) chamar("mem_recomecar");
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

/* ---------------------------------------------------------------- coluna "sua jornada" */
const ORDEM = ["freq", "tCL", "tRCDRD", "tRCDWR", "tRP", "tRAS", "tRFC", "grupoRRD", "grupoWTR", "tWR"];
const CURTO = {
  freq: "Velocidade", tCL: "Atraso de leitura", tRCDRD: "Abrir linha (leitura)", tRCDWR: "Abrir linha (escrita)",
  tRP: "Fechar linha", tRAS: "Linha aberta mínima", tRFC: "Recarga", grupoRRD: "Intervalo entre ativações",
  grupoWTR: "Pausa escrita e leitura", tWR: "Recuperação de escrita",
};

function valorAlcancado(passo, p) {
  if (passo === "freq") return `${p.freq}`;
  if (passo === "tRFC") return `${Math.round((p.tRFC * 2000) / p.freq)} ns`;
  if (passo === "grupoRRD") return `${p.tRRDS}/${p.tRRDL}/${p.tFAW}`;
  if (passo === "grupoWTR") return `${p.tWTRS}/${p.tWTRL}`;
  return `${p[passo]}`;
}

function jornadaMemoria() {
  const m = S.estado.mem, p = m.estavel, med = m.medicoes || [];
  const feitos = new Set(m.feitos), atual = m.teste?.passo;
  const proximo = atual || ORDEM.find((x) => !feitos.has(x));
  const inicial = med[0];
  const ganho = !m.confirmado ? `<p class="ganho">Ainda não começou<small>${esc(S.init.hw.pentes)} pentes, ${esc(S.init.hw.gb)} GB</small></p>`
    : `<p class="ganho">${inicial && inicial.freq !== p.freq ? `${inicial.freq} → ` : ""}${p.freq} MT/s<small>CL${p.tCL}, latência ${(p.tCL * 2000 / p.freq).toFixed(1)} ns</small></p>`;
  const itens = ORDEM.map((x) => {
    const busca = m.busca?.[x];
    let cls = "", icone = "", valor = "";
    if (!m.confirmado) { /* ainda não começou: todos neutros */ } else if (feitos.has(x)) {
      const melhorou = busca && busca.lo >= 0;
      cls = melhorou ? "feito" : "falhou";
      icone = melhorou ? "✓" : "–";
      valor = valorAlcancado(x, p);
    } else if (m.confirmado && x === proximo) {
      cls = "atual"; icone = "•";
      valor = m.teste ? valorAlcancado(x, m.teste.perfil) : "";
    }
    return `<li class="${cls}"><i>${icone}</i><span>${esc(CURTO[x])}</span><b>${esc(valor)}</b></li>`;
  }).join("");
  return `<h3>Sua memória</h3>${ganho}<ol class="etapas">${itens}</ol>`;
}

function jornadaProcessador() {
  const c = S.estado.cpu, t = c.teste;
  if (!c.perfil?.suporta_co) return `<h3>Seu processador</h3><p class="ganho">${esc(S.init.cpu.nome || "")}</p>`;
  const valores = [-5, -10, -15, -20, -25, -30];
  const NIVEL = { "-5": "Bem leve", "-10": "Leve", "-15": "Moderado", "-20": "Forte", "-25": "Muito forte", "-30": "Máximo" };
  const limite = c.feito ? valores.find((v) => v < c.estavel) : null;
  const itens = valores.map((v) => {
    let cls = "", icone = "";
    if (v >= c.estavel && c.estavel !== 0) { cls = "feito"; icone = "✓"; }
    if (t && t.valor === v) { cls = "atual"; icone = "•"; }
    if (limite === v) { cls = "falhou"; icone = "–"; }
    return `<li class="${cls}"><i>${icone}</i><span>${NIVEL[v]}</span><b>${v}</b></li>`;
  }).join("");
  return `<h3>Seu processador</h3><p class="ganho">${c.estavel ? `Ajuste ${c.estavel}` : "Sem ajuste"}<small>${esc(S.init.cpu.codinome || "")}, ${S.init.cpu.nucleos} núcleos</small></p><ol class="etapas">${itens}</ol>`;
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
  $("#jornada").innerHTML = trilha === "memoria" ? jornadaMemoria() : jornadaProcessador();
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
        ${tela.primario ? `<button class="botao primario grande" data-acao="p"${tela.primarioDesligado ? " disabled" : ""}>${esc(tela.primario[0])}</button>` : ""}
        ${(tela.links || []).map(([r], i) => `<button class="link" data-acao="${i}">${esc(r)}</button>`).join("")}
      </div>
      ${tela.detalhes ? `<details class="detalhes"><summary>Como funciona</summary><p>${esc(tela.detalhes)}</p></details>` : ""}
    </div>`;
  if (tela.primario) $('[data-acao="p"]', alvo).onclick = (e) => { e.target.disabled = true; Promise.resolve(tela.primario[1]()).finally(() => { e.target.disabled = false; }); };
  (tela.links || []).forEach(([, fn], i) => { $(`[data-acao="${i}"]`, alvo).onclick = fn; });
  $(".assistente-grade").classList.toggle("larga", !!tela.larga);
  if (S.teste && $("#ass-teste")) {
    if (S.teste.tipo === "memoria") desenharTesteAssistente($("#ass-teste"), S.teste);
    else if (S.teste.rodando) desenharTeste($("#ass-teste"), S.teste);
  }
}

function ligarAssistente() {
  $$(".trilha").forEach((b) => b.addEventListener("click", () => trocarTrilha(b.dataset.trilha)));
}
ligarAssistente();
