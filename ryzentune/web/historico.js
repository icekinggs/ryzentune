"use strict";
/* Histórico: linha do tempo por dia, com títulos claros, ruído recolhido e filtros.
   Junta três fontes: o que o RyzenTune registrou, as medições de desempenho e os desligamentos do Windows. */

let filtroHist = "importante";
S.trav = null; // desligamentos forçados e WHEA dos últimos 30 dias (lidos sob demanda)

const NOME_ETAPA = {
  "Frequência": "Velocidade", "tCL (latência CAS)": "Atraso de leitura", tRCDRD: "Abrir linha (leitura)",
  tRCDWR: "Abrir linha (escrita)", tRP: "Fechar linha", tRAS: "Linha aberta mínima", "tRFC (refresh)": "Recarga",
  "tRRDS / tRRDL / tFAW": "Intervalo entre ativações", "tWTRS / tWTRL": "Pausa escrita e leitura", "tWR / tRTP": "Recuperação de escrita",
};
const etapa = (n) => NOME_ETAPA[n] || n;
// tipos que só aparecem no filtro "Tudo"
const ROTINA = new Set(["preparada", "bios", "rotina"]);
const ICONE_HIST = { passou: "✓", falhou: "✕", pulado: "»", aviso: "!", bios: "↻", preparada: "•", rotina: "•", cpu: "⚡",
  chip: "◆", inicio: "▶", medicao: "▮", travou: "✕", whea: "!", cancelado: "–", info: "•" };

/* Transforma o texto gravado em {kind, titulo, detalhe}. O texto original fica disponível no detalhe. */
function classificarHist(x) {
  const t = x.texto;
  let m;
  if ((m = t.match(/^PASSOU '(.+?)'\.\s*(.*)$/))) return { kind: "passou", titulo: `${etapa(m[1])}: aprovado`, detalhe: m[2], etapa: m[1] };
  if ((m = t.match(/^PASSOU (.+?)\.\s*(.*)$/))) return { kind: "passou", titulo: `${m[1]}: aprovado`, detalhe: m[2] };
  if ((m = t.match(/^FALHOU '(.+?)':\s*(.*)$/))) return { kind: "falhou", titulo: `${etapa(m[1])}: reprovado`, detalhe: m[2], etapa: m[1] };
  if ((m = t.match(/^FALHOU (.+?):\s*(.*)$/))) return { kind: "falhou", titulo: `${m[1]}: reprovado`, detalhe: m[2] };
  if ((m = t.match(/^Ajuste '(.+)' pulado/))) return { kind: "pulado", titulo: `${etapa(m[1])}: pulado`, detalhe: "", etapa: m[1] };
  if ((m = t.match(/^Etapa preparada: (.+)\.$/))) return { kind: "preparada", titulo: `Próximo ajuste: ${etapa(m[1])}`, detalhe: "", etapa: m[1] };
  if (/Reiniciando na BIOS/.test(t)) return { kind: "bios", titulo: "Reiniciou na BIOS", detalhe: "" };
  if ((m = t.match(/^A BIOS não aplicou todos os valores da etapa: (.+)\.$/))) return { kind: "aviso", titulo: "A BIOS não aceitou todos os valores", detalhe: m[1] };
  if (/^Etapa aceita/.test(t)) return { kind: "info", titulo: "Etapa aceita com os valores da BIOS", detalhe: "" };
  if ((m = t.match(/^PC ligou com a etapa '(.+?)'\.\s*(.*)$/))) return { kind: "rotina", titulo: `PC ligou com ${etapa(m[1])}`, detalhe: m[2] };
  if ((m = t.match(/^Chip (identificado|escolhido à mão|conforme os pentes): (.+?)\.?$/)))
    return { kind: "chip", titulo: m[1] === "identificado" ? "Chip identificado" : m[1] === "escolhido à mão" ? "Chip escolhido à mão" : "Chip conforme os pentes", detalhe: m[2] };
  if ((m = t.match(/^Ponto de partida (?:lido do hardware|salvo): (.+?)\.?$/))) return { kind: "inicio", titulo: "Ponto de partida", detalhe: m[1] };
  if (/ativado neste boot|aplicado agora/.test(t)) return { kind: "cpu", titulo: t.replace(/\.$/, ""), detalhe: "" };
  if (/preparado/.test(t)) return { kind: "preparada", titulo: t.replace(/\.$/, ""), detalhe: "" };
  if (/cancelad|zerado/i.test(t)) return { kind: "cancelado", titulo: t.replace(/\.$/, ""), detalhe: "" };
  if (/passou no teste de núcleos/.test(t)) return { kind: "passou", titulo: "Teste dos núcleos aprovado", detalhe: t.replace(/^.*?passou no teste de núcleos\.\s*/, "") };
  return { kind: "info", titulo: t.replace(/\.$/, ""), detalhe: "" };
}

/* Lista cronológica de eventos já classificados, das três fontes. */
function eventosHist() {
  const ev = (S.estado.historico || []).map((x) => ({ quando: x.quando, area: x.tipo === "CPU" ? "cpu" : "memoria", texto: x.texto, ...classificarHist(x) }));
  for (const b of S.estado.bench || []) {
    ev.push({ quando: b.quando, area: "medicao", kind: "medicao", titulo: `Desempenho medido: ${b.rotulo}`,
      detalhe: `Latência ${num(b.lat_ns, 1)} ns, leitura ${num(b.leitura, 1)} GB/s${b.st != null ? `, ${num(b.st)} pontos em 1 núcleo, ${num(b.mt)} em todos` : ""}. Memória ${b.mem}, CO ${coCurto(b.co)}.` });
  }
  for (const t of S.trav || []) {
    ev.push({ quando: t.quando, area: "windows", kind: t.tipo === "whea" ? "whea" : "travou",
      titulo: t.tipo === "whea" ? "Erro de hardware (WHEA)" : "Desligamento forçado", detalhe: "Registrado pelo Windows." });
  }
  return ev.sort((a, b) => (a.quando < b.quando ? -1 : a.quando > b.quando ? 1 : 0));
}

const segs = (a, b) => (new Date(b) - new Date(a)) / 1000;

/* Recolhe o ruído: repetições seguidas, "preparada" seguida de "pulado" e sequências de pulos. */
function recolher(ev) {
  const r = [];
  for (const e of ev) {
    const ant = r[r.length - 1];
    if (ant && ant.texto && ant.texto === e.texto && segs(ant.ultimo || ant.quando, e.quando) < 600) {
      ant.vezes = (ant.vezes || 1) + 1; ant.ultimo = e.quando; continue;
    }
    if (ant && ant.kind === "preparada" && e.kind === "pulado" && ant.etapa === e.etapa && segs(ant.quando, e.quando) < 120) {
      r[r.length - 1] = e; continue;
    }
    r.push({ ...e });
  }
  const g = [];
  for (const e of r) {
    const ant = g[g.length - 1];
    if (e.kind === "pulado" && ant && (ant.kind === "pulado" || ant.kind === "grupo-pulados") && segs(ant.ultimo || ant.quando, e.quando) < 300) {
      if (ant.kind === "pulado") g[g.length - 1] = { kind: "grupo-pulados", area: "memoria", quando: ant.quando, itens: [ant, e], ultimo: e.quando };
      else { ant.itens.push(e); ant.ultimo = e.quando; }
      continue;
    }
    g.push(e);
  }
  for (const e of g) {
    if (e.kind !== "grupo-pulados") continue;
    const s = Math.round(segs(e.quando, e.ultimo));
    e.titulo = `${e.itens.length} ajustes pulados em ${s < 60 ? `${s} s` : `${Math.round(s / 60)} min`}`;
    e.detalhe = e.itens.map((x) => etapa(x.etapa)).join(", ");
  }
  return g;
}

function passaFiltro(e) {
  if (filtroHist === "memoria") return e.area === "memoria";
  if (filtroHist === "cpu") return e.area === "cpu";
  if (filtroHist === "importante") return !ROTINA.has(e.kind);
  return true;
}

function rotuloDia(iso) {
  const d = new Date(iso), hoje = new Date();
  const dia = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const dif = Math.round((dia(hoje) - dia(d)) / 864e5);
  if (dif === 0) return "Hoje";
  if (dif === 1) return "Ontem";
  return d.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" }).replace(/^./, (c) => c.toUpperCase());
}

function resumoHist(ev) {
  const n = (k) => ev.filter((e) => e.kind === k).length;
  const pul = ev.filter((e) => e.kind === "pulado").length;
  const itens = [
    ["passou", n("passou"), n("passou") === 1 ? "aprovado" : "aprovados"],
    ["falhou", n("falhou"), n("falhou") === 1 ? "reprovado" : "reprovados"],
    ["pulado", pul, pul === 1 ? "pulado" : "pulados"],
    ["bios", n("bios"), n("bios") === 1 ? "ida à BIOS" : "idas à BIOS"],
    ["medicao", n("medicao"), n("medicao") === 1 ? "medição" : "medições"],
    ["travou", n("travou") + n("whea"), "travamentos (Windows)"],
  ];
  const ini = (S.estado.historico || [])[0];
  return `<ul class="hist-resumo">${itens.map(([k, v, r]) => `<li class="k-${k}"><b>${v}</b><span>${r}</span></li>`).join("")}</ul>
    ${ini ? `<p class="nota">Desde ${esc(new Date(ini.quando).toLocaleDateString("pt-BR", { day: "numeric", month: "long" }))}. ${S.trav ? "" : "Lendo os travamentos registrados pelo Windows…"}</p>` : ""}`;
}

function itemHist(e) {
  const hora = new Date(e.quando).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const vezes = e.vezes > 1 ? `<span class="vezes">×${e.vezes}</span>` : "";
  const area = { memoria: "Memória", cpu: "Processador", medicao: "Desempenho", windows: "Windows" }[e.area] || "";
  const icone = ICONE_HIST[e.kind === "grupo-pulados" ? "pulado" : e.kind] || "•";
  const corpo = e.kind === "grupo-pulados"
    ? `<details><summary><b>${esc(e.titulo)}</b></summary><p>${esc(e.detalhe)}</p></details>`
    : `<b>${esc(e.titulo)}</b>${vezes}${e.detalhe ? `<p>${esc(e.detalhe)}</p>` : ""}`;
  return `<li class="k-${e.kind === "grupo-pulados" ? "pulado" : e.kind}${ROTINA.has(e.kind) ? " rotina" : ""}">
    <i aria-hidden="true">${icone}</i><time>${hora}</time><div class="corpo">${corpo}</div><span class="area">${area}</span></li>`;
}

function desenharHistorico() {
  if (!S.estado) return;
  const todos = recolher(eventosHist());
  $("#hist-resumo").innerHTML = todos.length ? resumoHist(eventosHist()) : "";
  $$(".hist-filtro").forEach((b) => b.classList.toggle("ativo", b.dataset.f === filtroHist));
  const ev = todos.filter(passaFiltro).reverse();
  if (!ev.length) {
    $("#historico").innerHTML = `<p class="vazio">${todos.length ? "Nada neste filtro." : "Nada por aqui ainda. O histórico começa quando você define o ponto de partida da memória."}</p>`;
    return;
  }
  let html = "", diaAtual = "";
  for (const e of ev) {
    const d = rotuloDia(e.quando);
    if (d !== diaAtual) { html += `${diaAtual ? "</ol>" : ""}<h3 class="hist-dia">${esc(d)}</h3><ol class="hist-lista">`; diaAtual = d; }
    html += itemHist(e);
  }
  $("#historico").innerHTML = `${html}</ol>`;
}

async function abrirHistorico() {
  desenharHistorico();
  if (S.trav) return;
  const r = await api.travamentos(30).catch(() => null);
  S.trav = r && !r.erro ? r.eventos : [];
  desenharHistorico();
}

async function copiarHistorico() {
  const linhas = recolher(eventosHist()).map((e) => `${e.quando.replace("T", " ")}  ${e.titulo}${e.vezes > 1 ? ` (×${e.vezes})` : ""}${e.detalhe ? ` — ${e.detalhe}` : ""}`);
  const texto = `RyzenTune ${S.init?.versao || ""}: histórico\n${linhas.join("\n")}\n`;
  try { await navigator.clipboard.writeText(texto); aviso("Histórico copiado. Cole onde quiser (Ctrl+V)."); }
  catch (_) {
    const ta = document.createElement("textarea");
    ta.value = texto; document.body.append(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove();
    aviso(ok ? "Histórico copiado. Cole onde quiser (Ctrl+V)." : "Não consegui copiar.", ok ? "" : "erro");
  }
}

function ligarHistorico() {
  $$(".hist-filtro").forEach((b) => b.addEventListener("click", () => { filtroHist = b.dataset.f; desenharHistorico(); }));
  $("#hist-copiar").addEventListener("click", copiarHistorico);
}
ligarHistorico();
