"use strict";
/* Sensores (monitor contínuo com histórico de 15 min) e Desempenho (medições antes e depois). */

const num = (v, casas = 0) => (v == null || isNaN(v) ? "--" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }));
const hora = (t) => new Date(t * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const dataCurta = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/* ================================================================ sensores */
S.mon = { amostras: [], n: 0, picos: {}, erro: null };

async function laçoMonitor() {
  while (true) {
    if (S.pagina === "painel" && !document.hidden) {
      try {
        const r = await api.monitor_desde(S.mon.n);
        if (r && !r.erro && r.amostras) {
          S.mon.amostras.push(...r.amostras);
          if (S.mon.amostras.length > 900) S.mon.amostras.splice(0, S.mon.amostras.length - 900);
          if (r.amostras.length) S.mon.n = r.amostras[r.amostras.length - 1].n;
          S.mon.picos = r.picos || {};
          S.mon.erro = r.erro;
          desenharSensores();
        }
      } catch (_) { /* segue */ }
    }
    await espera(1000);
  }
}

function desenharSensores() {
  const a = S.mon.amostras, u = a[a.length - 1];
  if (!u) return;
  S.vivo = { temp: u.temp, mclk: u.mclk, fclk: u.fclk, uclk: u.uclk, vsoc: u.vsoc };
  desenharVivo();
  animarNumero($("#v-vcore"), u.vcore ?? null, 3);
  const p = S.mon.picos;
  $("#picos").textContent = [p.temp != null && `máx. ${num(p.temp)} °C`, p.mhz && `${num(p.mhz)} MHz`, p.vcore && `${num(p.vcore, 3)} V`]
    .filter(Boolean).join(" · ") + (p.temp != null || p.mhz ? " desde que o app abriu" : "");
  desenharNucleosVivo(u);
  desenharGraficos(a);
}

function desenharNucleosVivo(u) {
  const alvo = $("#nucleos-vivo");
  if (!u.mhz) {
    alvo.innerHTML = `<li class="vazio">${esc(S.mon.erro ? `O Windows não entregou os contadores (${S.mon.erro}).` : "Lendo os núcleos…")}</li>`;
    return;
  }
  const teto = Math.max(5000, ...(u.mhz || []));
  const co = S.estado?.cpu?.teste?.modo === "nucleos" ? S.estado.cpu.teste.valores : S.estado?.cpu?.nucleos?.estavel;
  if (alvo.children.length !== u.mhz.length || alvo.querySelector(".vazio")) {
    alvo.innerHTML = u.mhz.map((_, i) => `<li><span class="nome">Núcleo ${i + 1}</span>
      <span class="barra-mhz"><i></i></span><b class="mhz"></b><span class="uso"><i></i><small></small></span><span class="co"></span></li>`).join("");
  }
  [...alvo.children].forEach((li, i) => {
    li.querySelector(".barra-mhz i").style.width = `${(u.mhz[i] / teto) * 100}%`;
    li.querySelector(".mhz").textContent = `${num(u.mhz[i])} MHz`;
    const uso = u.uso ? u.uso[i] : null;
    li.querySelector(".uso i").style.width = `${uso ?? 0}%`;
    li.querySelector(".uso small").textContent = uso == null ? "" : `${uso}% em uso`;
    li.querySelector(".co").textContent = co ? `CO ${co[i]}` : "";
  });
}

/* ---- gráficos de linha (um por medida: nunca dois eixos no mesmo gráfico) */
const GRAFICOS = [
  { k: "temp", titulo: "Temperatura", un: "°C", casas: 0, min: 30, max: 95 },
  { k: "mhz_max", titulo: "Núcleo mais rápido", un: "MHz", casas: 0, min: 0, max: 5000 },
  { k: "uso_med", titulo: "Uso do processador", un: "%", casas: 0, min: 0, max: 100 },
  { k: "vcore", titulo: "Tensão dos núcleos", un: "V", casas: 3, min: 0.8, max: 1.5 },
];
const hoverGrafico = {};

function serie(a, k) {
  return a.map((x) => ({ t: x.t, v: k === "mhz_max" ? (x.mhz ? Math.max(...x.mhz) : null)
    : k === "uso_med" ? (x.uso ? x.uso.reduce((s, y) => s + y, 0) / x.uso.length : null) : x[k] ?? null }));
}

function desenharGraficos(a) {
  const alvo = $("#graficos");
  const visiveis = GRAFICOS.filter((g) => g.k !== "vcore" || a.some((x) => x.vcore));
  if (alvo.children.length !== visiveis.length) {
    alvo.innerHTML = visiveis.map((g) => `<figure class="grafico" data-k="${g.k}">
      <figcaption><span>${g.titulo}</span><b class="agora"></b></figcaption>
      <div class="plot"><svg viewBox="0 0 300 90" preserveAspectRatio="none" aria-label="${g.titulo} nos últimos 15 minutos" role="img"></svg>
      <div class="dica-grafico" hidden></div></div>
      <div class="eixo-x"><span></span><span>agora</span></div></figure>`).join("");
    $$(".grafico", alvo).forEach((f) => {
      const plot = $(".plot", f);
      plot.addEventListener("mousemove", (ev) => { const r = plot.getBoundingClientRect(); hoverGrafico[f.dataset.k] = (ev.clientX - r.left) / r.width; desenharGraficos(S.mon.amostras); });
      plot.addEventListener("mouseleave", () => { delete hoverGrafico[f.dataset.k]; desenharGraficos(S.mon.amostras); });
    });
  }
  const t1 = a.length ? a[a.length - 1].t : Date.now() / 1000, t0 = t1 - 900;
  visiveis.forEach((g) => {
    const f = $(`.grafico[data-k="${g.k}"]`, alvo), pts = serie(a, g.k).filter((p) => p.v != null && p.t >= t0);
    const vals = pts.map((p) => p.v);
    const lo = Math.min(g.min, ...(vals.length ? [Math.min(...vals)] : [])), hi = Math.max(g.max, ...(vals.length ? [Math.max(...vals)] : []));
    const x = (t) => ((t - t0) / 900) * 300, y = (v) => 86 - ((v - lo) / (hi - lo)) * 80;
    const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    const area = pts.length ? `${d}L${x(pts[pts.length - 1].t).toFixed(1)},86L${x(pts[0].t).toFixed(1)},86Z` : "";
    let hov = "";
    const dica = $(".dica-grafico", f);
    if (hoverGrafico[g.k] != null && pts.length) {
      const tAlvo = t0 + hoverGrafico[g.k] * 900;
      const p = pts.reduce((m, q) => (Math.abs(q.t - tAlvo) < Math.abs(m.t - tAlvo) ? q : m));
      hov = `<line class="cruz" x1="${x(p.t)}" x2="${x(p.t)}" y1="4" y2="86"/><circle class="ponto" cx="${x(p.t)}" cy="${y(p.v)}" r="3.5"/>`;
      dica.hidden = false;
      dica.innerHTML = `<b>${num(p.v, g.casas)} ${g.un}</b><span>${hora(p.t)}</span>`;
      dica.style.left = `${Math.min(78, Math.max(4, (x(p.t) / 300) * 100))}%`;
    } else dica.hidden = true;
    $("svg", f).innerHTML = `<line class="base" x1="0" x2="300" y1="86" y2="86"/>${area ? `<path class="area" d="${area}"/>` : ""}<path class="linha" d="${d}"/>${hov}`;
    $(".agora", f).textContent = vals.length ? `${num(vals[vals.length - 1], g.casas)} ${g.un}` : "--";
    $(".eixo-x span", f).textContent = "15 min atrás";
  });
}

/* ---- travamentos */
async function lerTravamentos() {
  $("#travamentos").innerHTML = `<p class="vazio">Lendo o registro do Windows…</p>`;
  const r = await api.travamentos(30);
  const ev = r && !r.erro ? r.eventos : null;
  if (ev) S.trav = ev;
  if (!ev) { $("#travamentos").innerHTML = `<p class="vazio">Não consegui ler o registro de eventos.</p>`; return; }
  if (!ev.length) {
    $("#travamentos").innerHTML = `<p class="trav-ok"><span>✓</span>Nenhum desligamento forçado nem erro de hardware nos últimos 30 dias.</p>`;
    return;
  }
  const k41 = ev.filter((e) => e.tipo === "desligamento").length, whea = ev.length - k41;
  const dias = Math.floor((Date.now() - new Date(ev[0].quando)) / 864e5);
  $("#travamentos").innerHTML = `<p class="texto">${k41} ${k41 === 1 ? "desligamento forçado" : "desligamentos forçados"} e ${whea} ${whea === 1 ? "erro" : "erros"} de hardware (WHEA).
      O último foi ${dias === 0 ? "hoje" : dias === 1 ? "ontem" : `há ${dias} dias`}.
      ${dias >= 3 ? "Desde então o PC está estável." : "Se não foi falta de energia, algum ajuste pode estar instável."}</p>
    <ol class="trav-lista">${ev.map((e) => `<li class="${e.tipo}"><span>${esc(dataCurta(e.quando))}</span><b>${e.tipo === "whea" ? "Erro de hardware (WHEA)" : "Desligamento forçado"}</b></li>`).join("")}</ol>`;
}

/* ================================================================ desempenho */
const MEDIDAS = [
  { k: "lat_ns", rot: "Latência da memória", curto: "Latência", sub: "tempo de uma leitura", un: "ns", casas: 1, menor: true },
  { k: "leitura", rot: "Leitura", sub: "banda da memória", un: "GB/s", casas: 1 },
  { k: "escrita", rot: "Escrita", sub: "banda da memória", un: "GB/s", casas: 1 },
  { k: "copia", rot: "Cópia", sub: "banda da memória", un: "GB/s", casas: 1 },
  { k: "st", rot: "Um núcleo", curto: "1 núcleo", sub: "pontos do processador", un: "pontos", casas: 0 },
  { k: "mt", rot: "Todos os núcleos", curto: "Todos", sub: "pontos do processador", un: "pontos", casas: 0 },
];
const RUIDO = 2; // % que a mesma medição varia sozinha: abaixo disso é "igual"
let retrato = null, escolhaA = null, escolhaB = null;

async function abrirDesempenho() {
  const r = await api.bench_retrato();
  retrato = r && !r.erro ? r : null;
  desenharDesempenho();
  const st = await api.bench_status();
  if (st?.rodando) acompanharBench();
}

function coCurto(co) {
  const v = String(co ?? "0").trim().split(/\s+/).map(Number);
  if (v.length < 2) return String(co ?? "0");
  const min = Math.min(...v), max = Math.max(...v);
  return min === max ? `${min} (por núcleo)` : `por núcleo, de ${max} a ${min}`;
}

function descrConfig(b) {
  return `Memória ${b.mem} · tRFC ${b.trfc_ns} ns · Curve Optimizer ${coCurto(b.co)}`;
}

function desenharDesempenho() {
  if (!S.estado) return;
  const lista = S.estado.bench || [];
  const ultimo = lista[lista.length - 1];
  const mudou = retrato && ultimo && (retrato.mem !== ultimo.mem || retrato.co !== ultimo.co || retrato.trfc_ns !== ultimo.trfc_ns);
  $("#bench-titulo").textContent = !lista.length ? "Meça agora para guardar o “antes”"
    : mudou ? "Seus ajustes mudaram desde a última medição" : "Medir o desempenho agora";
  $("#bench-retrato").textContent = retrato ? `Valendo agora: ${descrConfig(retrato)}` : "";

  const opc = lista.map((b, i) => `<option value="${i}">${esc(dataCurta(b.quando))} · ${esc(b.rotulo)}${b.st == null ? " (só memória)" : ""}</option>`).join("");
  const a = $("#bench-a"), bsel = $("#bench-b");
  a.innerHTML = bsel.innerHTML = opc;
  if (escolhaA == null || escolhaA >= lista.length) escolhaA = 0;
  if (escolhaB == null || escolhaB >= lista.length) escolhaB = lista.length - 1;
  a.value = escolhaA; bsel.value = escolhaB;
  $(".comparar-escolha").hidden = lista.length < 2;

  const alvo = $("#bench-comparacao");
  if (!lista.length) alvo.innerHTML = `<p class="vazio">Nenhuma medição ainda.</p>`;
  else if (lista.length === 1) alvo.innerHTML = `<p class="nota">Só há uma medição (${esc(descrConfig(lista[0]))}). Depois de cada ajuste, meça de novo para ver a diferença.</p>${comparacao(null, lista[0])}`;
  else {
    const A = lista[escolhaA], B = lista[escolhaB];
    alvo.innerHTML = `<div class="cfg-ab"><p><span>Antes</span>${esc(descrConfig(A))}</p><p><span>Depois</span>${esc(descrConfig(B))}</p></div>${comparacao(A, B)}`;
  }

  $("#bench-tabela").innerHTML = lista.length ? `<thead><tr><th>Quando</th><th>Motivo</th><th>Memória</th><th>CO</th>
      ${MEDIDAS.map((m) => `<th class="n">${m.curto || m.rot}<small>${m.un}</small></th>`).join("")}<th></th></tr></thead>
    <tbody>${lista.map((b, i) => `<tr><td>${esc(dataCurta(b.quando))}</td><td>${esc(b.rotulo)}</td><td>${esc(b.mem)}</td><td title="${esc(b.co)}">${esc(coCurto(b.co))}</td>
      ${MEDIDAS.map((m) => `<td class="n">${num(b[m.k], m.casas)}</td>`).join("")}
      <td><button class="link perigo" data-apagar="${i}" title="Apagar esta medição" aria-label="Apagar esta medição">×</button></td></tr>`).reverse().join("")}</tbody>` : "";
  $$("[data-apagar]").forEach((x) => { x.onclick = async () => {
    const b = lista[+x.dataset.apagar];
    if (await confirmar("Apagar medição", `Apagar a medição de ${dataCurta(b.quando)}?`, "Apagar")) { await chamar("bench_apagar", b.quando); escolhaA = escolhaB = null; desenharDesempenho(); }
  }; });
}

function comparacao(A, B) {
  return `<ol class="comparacao">${MEDIDAS.map((m) => {
    const antes = A ? A[m.k] : null, depois = B[m.k];
    if (depois == null && antes == null) return "";
    const tem = antes != null && depois != null;
    const ganho = tem ? ((m.menor ? antes / depois : depois / antes) - 1) * 100 : null;
    const max = tem ? Math.max(antes, depois) : depois || 1;
    const tag = ganho == null ? `<span class="ganho-tag neutro">${A ? "sem medida" : "referência"}</span>`
      : Math.abs(ganho) < RUIDO ? `<span class="ganho-tag neutro" title="Diferenças abaixo de ${RUIDO}% acontecem entre duas medições iguais">igual</span>`
      : `<span class="ganho-tag ${ganho > 0 ? "melhor" : "pior"}">${ganho > 0 ? "+" : ""}${num(ganho, 1)}% ${ganho > 0 ? "melhor" : "pior"}</span>`;
    return `<li><div class="cmp-rotulo"><b>${m.rot}</b><span>${m.sub}${m.menor ? ", menor é melhor" : ""}</span></div>
      <div class="cmp-barras">
        ${A ? `<div class="cmp-linha antes"><span>Antes</span><i style="width:${tem ? (antes / max) * 100 : 0}%"></i><b>${num(antes, m.casas)}</b></div>` : ""}
        <div class="cmp-linha depois"><span>${A ? "Depois" : "Agora"}</span><i style="width:${depois != null ? (depois / max) * 100 : 0}%"></i><b>${num(depois, m.casas)}</b></div>
      </div><div class="cmp-fim"><small>${m.un}</small>${tag}</div></li>`;
  }).join("")}</ol>`;
}

async function medirDesempenho() {
  const r = await api.bench_iniciar(true, "");
  if (!r || r.erro) { aviso(r ? r.erro : "sem resposta", "erro"); return; }
  acompanharBench();
}

let acompanhando = false;
async function acompanharBench() {
  if (acompanhando) return;
  acompanhando = true;
  $("#bench-medir").disabled = true;
  $("#bench-progresso").hidden = false;
  const ETAPA = { preparando: "Preparando…", "memória": "Medindo a memória (latência e banda)…", "um núcleo": "Medindo um núcleo…", "todos os núcleos": "Medindo todos os núcleos…", pronto: "Pronto" };
  try {
    while (true) {
      const s = await api.bench_status();
      if (!s || s.erro || !s.rodando) {
        if (s?.erro) aviso(`A medição falhou: ${s.erro}`, "erro");
        break;
      }
      $("#bench-barra").style.width = `${Math.round((s.fracao || 0) * 100)}%`;
      $("#bench-etapa").textContent = ETAPA[s.etapa] || s.etapa || "";
      await espera(700);
    }
  } finally {
    acompanhando = false;
    $("#bench-medir").disabled = false;
    $("#bench-progresso").hidden = true;
    const e = await api.obter_estado();
    if (e && !e.erro) { S.estado = e; escolhaB = null; }
    await abrirDesempenho();
  }
}

function ligarPainel() {
  $("#bench-medir").addEventListener("click", medirDesempenho);
  $("#bench-a").addEventListener("change", (ev) => { escolhaA = +ev.target.value; desenharDesempenho(); });
  $("#bench-b").addEventListener("change", (ev) => { escolhaB = +ev.target.value; desenharDesempenho(); });
  $("#trav-ler").addEventListener("click", lerTravamentos);
}
ligarPainel();
