// Agregador de Notícias — Worker do Cloudflare (plano gratuito).
//
// 1. Despertador: de 15 em 15 minutos (Cron Trigger) pede ao GitHub uma execução
//    "agendada" do workflow, que só verifica se já passou geral.intervalo_minutos.
// 2. Bot do Telegram (webhook): trata os botões das mensagens (Confiável / Neutra /
//    Bloquear), gravando a decisão no config.yaml como o painel faz, e os comandos
//    /verificar, /estado, /fontes e /ajuda.
//
// Variáveis (Settings > Variables and secrets), todas do tipo "Secret":
//   GITHUB_TOKEN        token fine-grained só deste repositório (Contents e Actions: Read and write)
//   TELEGRAM_BOT_TOKEN  token do bot (BotFather)
//   TELEGRAM_CHAT_ID    o teu chat id (o bot diz-to quando lhe mandas /start)
//   WEBHOOK_SECRET      uma palavra-passe inventada por ti (letras, números, _ e -)
// Opcional (texto): REPO, por omissão tigreman263/agregador-noticias.
//
// Depois de publicar, abre uma vez https://<o-teu-worker>.workers.dev/instalar?chave=<WEBHOOK_SECRET>

const REPO_OMISSAO = "tigreman263/agregador-noticias";
const RAMO = "main";
const WORKFLOW = "agregador.yml";
const LISTAS = { c: "confiaveis", n: "neutras", b: "bloqueadas" };
const NOMES = { confiaveis: "Confiável", neutras: "Neutra", bloqueadas: "Bloqueada" };
const COMANDOS = [
  { command: "verificar", description: "Procurar notícias agora" },
  { command: "estado", description: "Como correu a última verificação" },
  { command: "fontes", description: "Fontes sugeridas por decidir" },
  { command: "ajuda", description: "O que este bot faz" },
];

export default {
  async scheduled(evento, env, ctx) {
    ctx.waitUntil(despertar(env));
  },

  async fetch(pedido, env) {
    const url = new URL(pedido.url);
    if (url.pathname === "/telegram" && pedido.method === "POST") {
      if (!env.WEBHOOK_SECRET || pedido.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
        return new Response("proibido", { status: 403 });
      }
      let update;
      try { update = await pedido.json(); } catch (e) { return new Response("ok"); }
      try {
        await tratarUpdate(env, update);
      } catch (e) {
        console.log("erro a tratar o update: " + e.message);
      }
      return new Response("ok"); // sempre 200, senão o Telegram repete o mesmo update
    }
    if (url.pathname === "/instalar") return instalar(env, url);
    return new Response("Agregador de Notícias: o Worker está ligado.\n", { headers: { "content-type": "text/plain; charset=utf-8" } });
  },

  decidirFonte, // só para os testes
};

// ------------------------------------------------------------------ despertador

async function despertar(env) {
  try {
    await correrWorkflow(env, "agendada");
  } catch (e) {
    console.log("despertador falhou: " + e.message);
    // avisa no Telegram, mas só 1 vez por dia (por volta das 9h de Lisboa), para não
    // mandar uma mensagem de 15 em 15 minutos enquanto o problema durar
    const agora = horaLisboa();
    if (agora.hora === 9 && agora.minuto < 15 && env.TELEGRAM_CHAT_ID) {
      await responder(env, env.TELEGRAM_CHAT_ID,
        "⚠️ O despertador do Cloudflare não conseguiu pedir a verificação ao GitHub: " + esc(e.message) +
        "\nConfirma o GITHUB_TOKEN do Worker (pode ter expirado).").catch(() => {});
    }
  }
}

function horaLisboa() {
  const partes = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Lisbon", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date());
  const v = t => Number((partes.find(p => p.type === t) || {}).value);
  return { hora: v("hour"), minuto: v("minute") };
}

// ------------------------------------------------------------------ GitHub

function repo(env) { return env.REPO || REPO_OMISSAO; }

async function gh(env, caminho, opcoes = {}) {
  if (!env.GITHUB_TOKEN) throw new Error("falta o segredo GITHUB_TOKEN no Worker");
  const r = await fetch("https://api.github.com" + caminho, {
    method: opcoes.method || "GET",
    headers: {
      "Accept": opcoes.accept || "application/vnd.github+json",
      "Authorization": "Bearer " + env.GITHUB_TOKEN,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "agregador-noticias-worker",
      ...(opcoes.body ? { "Content-Type": "application/json" } : {}),
    },
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined,
  });
  if (r.status === 204) return null;
  const texto = await r.text();
  if (!r.ok) {
    let msg = "";
    try { msg = JSON.parse(texto).message || ""; } catch (e) {}
    const erro = new Error(r.status === 401 ? "o GitHub recusou o token (inválido ou expirado)"
      : r.status === 403 || r.status === 404 ? "o token não tem permissão (" + r.status + (msg ? ": " + msg : "") + ")"
      : "o GitHub respondeu " + r.status + (msg ? ": " + msg : ""));
    erro.status = r.status;
    throw erro;
  }
  return opcoes.accept && opcoes.accept.includes("raw") ? texto : JSON.parse(texto);
}

async function correrWorkflow(env, acao) {
  await gh(env, `/repos/${repo(env)}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST", body: { ref: RAMO, inputs: { acao } },
  });
}

function b64dec(s) {
  const bin = atob(String(s).replace(/\s/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, c => c.charCodeAt(0)));
}
function b64enc(texto) {
  const by = new TextEncoder().encode(texto);
  let bin = "";
  for (let i = 0; i < by.length; i += 0x8000) bin += String.fromCharCode.apply(null, by.subarray(i, i + 0x8000));
  return btoa(bin);
}

async function lerFicheiro(env, caminho) {
  const d = await gh(env, `/repos/${repo(env)}/contents/${caminho}?ref=${RAMO}`);
  return { texto: b64dec(d.content), sha: d.sha };
}

async function lerEstado(env) {
  const texto = await gh(env, `/repos/${repo(env)}/contents/estado.json?ref=${RAMO}`, { accept: "application/vnd.github.raw+json" });
  try { return JSON.parse(texto) || {}; } catch (e) { return {}; }
}

// ------------------------------------------------------------------ config.yaml
// Edição linha a linha, só dentro da secção "fontes:" (os comentários e o resto do ficheiro
// ficam como estão). As listas confiaveis/neutras/bloqueadas estão no formato de uma linha
// que o painel grava: confiaveis: ["a.pt", "b.pt"].

function lerListaYaml(dentro) {
  const s = dentro.trim();
  if (!s) return [];
  return s.split(",").map(x => x.trim().replace(/^(["'])(.*)\1$/, "$2")).filter(Boolean);
}

function linhaLista(chave, itens, comentario) {
  return "  " + chave + ": [" + itens.map(x => JSON.stringify(x)).join(", ") + "]" + (comentario ? "  " + comentario : "");
}

// Devolve o novo texto do config.yaml (ou o mesmo, se nada mudar).
function decidirFonte(texto, dominio, lista, sugestao) {
  const eol = texto.includes("\r\n") ? "\r\n" : "\n";
  const L = texto.split(/\r?\n/);
  const ini = L.findIndex(l => /^fontes:[ \t]*(#.*)?$/.test(l));
  if (ini < 0) throw new Error("não encontrei a secção 'fontes' no config.yaml");
  let fim = L.length;
  for (let i = ini + 1; i < L.length; i++) if (/^[A-Za-z_]/.test(L[i])) { fim = i; break; }

  for (const chave of ["confiaveis", "neutras", "bloqueadas"]) {
    const re = new RegExp("^  " + chave + ":[ \\t]*(.*)$");
    let j = -1;
    for (let i = ini + 1; i < fim; i++) if (re.test(L[i])) { j = i; break; }
    if (j < 0) {
      // a chave não existe: cria-a logo a seguir a "fontes:"
      const novos = chave === lista ? [dominio] : [];
      L.splice(ini + 1, 0, linhaLista(chave, novos));
      fim++;
      continue;
    }
    const m = L[j].match(/^  [a-z]+:[ \t]*\[([^\]]*)\][ \t]*(#.*)?$/);
    if (!m) throw new Error("a lista '" + chave + "' do config.yaml não está no formato de uma linha; decide no painel");
    const antes = lerListaYaml(m[1]);
    let depois = antes.filter(x => x !== dominio);
    if (chave === lista) depois = antes.includes(dominio) ? antes : depois.concat([dominio]); // já lá estava: não mexe na ordem
    if (depois.join("\n") !== antes.join("\n")) L[j] = linhaLista(chave, depois, m[2]);
  }

  // Confiável com feed: junta-o também aos feeds gerais (como o painel)
  if (lista === "confiaveis" && sugestao && /^https?:\/\//.test(sugestao.feed || "")) {
    const seccao = L.slice(ini, fim).join("\n");
    if (!seccao.includes(sugestao.feed)) {
      const item = "    - {nome: " + JSON.stringify(String(sugestao.nome || dominio)) + ", url: " + JSON.stringify(sugestao.feed) + "}";
      const k = L.findIndex((l, i) => i > ini && i < fim && /^  feeds:/.test(l));
      if (k < 0) {
        let ult = fim - 1;
        while (ult > ini && (L[ult].trim() === "" || /^#/.test(L[ult]))) ult--;
        L.splice(ult + 1, 0, "  feeds:", item);
      } else if (/^  feeds:[ \t]*\[[ \t]*\][ \t]*(#.*)?$/.test(L[k])) {
        L.splice(k, 1, "  feeds:", item);
      } else if (/^  feeds:[ \t]*(#.*)?$/.test(L[k])) {
        let ult = k;
        for (let i = k + 1; i < fim; i++) {
          if (/^    \S/.test(L[i]) || /^  - /.test(L[i])) ult = i;
          else if (L[i].trim() === "" || /^\s*#/.test(L[i])) continue;
          else break;
        }
        L.splice(ult + 1, 0, item);
      }
      // outro formato (ex.: feeds: [{...}]) fica como está: o painel trata disso
    }
  }
  return L.join(eol);
}

async function gravarDecisao(env, dominio, lista) {
  let sugestao = null;
  if (lista === "confiaveis") {
    try { sugestao = ((await lerEstado(env)).sugeridas || {})[dominio] || null; } catch (e) {}
  }
  for (let tentativa = 0; tentativa < 3; tentativa++) {
    const f = await lerFicheiro(env, "config.yaml");
    const novo = decidirFonte(f.texto, dominio, lista, sugestao);
    if (novo === f.texto) return false; // já estava assim
    try {
      await gh(env, `/repos/${repo(env)}/contents/config.yaml`, {
        method: "PUT",
        body: { message: "telegram: " + dominio + " em " + lista, content: b64enc(novo), sha: f.sha, branch: RAMO },
      });
      return true;
    } catch (e) {
      if (e.status !== 409 && e.status !== 422) throw e; // 409/422: o ficheiro mudou entretanto
    }
  }
  throw new Error("o config.yaml estava sempre a mudar; tenta outra vez");
}

// ------------------------------------------------------------------ Telegram

async function tg(env, metodo, corpo) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${metodo}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo),
  });
  const d = await r.json().catch(() => ({}));
  if (!d.ok) throw new Error("Telegram (" + metodo + "): " + (d.description || r.status));
  return d.result;
}

function responder(env, chat, texto, extra = {}) {
  return tg(env, "sendMessage", { chat_id: chat, text: texto, parse_mode: "HTML", disable_web_page_preview: true, ...extra });
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

const DOMINIO_OK = /^([a-z0-9-]+\.)*[a-z0-9-]+$/;

async function tratarUpdate(env, u) {
  if (u.callback_query) return tratarBotao(env, u.callback_query);
  const m = u.message;
  if (!m || !m.chat || typeof m.text !== "string") return;
  const chat = String(m.chat.id);
  const cmd = m.text.trim().split(/\s+/)[0].split("@")[0].toLowerCase();

  // /start e /id respondem a qualquer pessoa, só com o chat id dela (para a instalação)
  if (cmd === "/start" || cmd === "/id") {
    const meu = chat === String(env.TELEGRAM_CHAT_ID || "");
    return responder(env, chat, meu
      ? "👋 Olá! Estou ligado ao agregador. Escreve /ajuda para veres o que faço."
      : "👋 O teu chat id é <code>" + esc(chat) + "</code>.\nGuarda-o como <b>TELEGRAM_CHAT_ID</b> no Worker do Cloudflare e nos segredos do GitHub.");
  }
  if (chat !== String(env.TELEGRAM_CHAT_ID || "")) return; // o bot é só teu: ignora os outros

  if (cmd === "/verificar") {
    try {
      await correrWorkflow(env, "normal");
      return responder(env, chat, "🔄 Pedi uma verificação. Se houver notícias, chegam daqui a 2 ou 3 minutos.");
    } catch (e) {
      return responder(env, chat, "❌ Não consegui pedir a verificação: " + esc(e.message));
    }
  }
  if (cmd === "/estado") return responder(env, chat, await textoEstado(env));
  if (cmd === "/fontes") return enviarFontes(env, chat);
  return responder(env, chat,
    "<b>Agregador de Notícias</b>\n" +
    "Envio-te os alertas e o resumo diário. Nos botões decides as fontes (fica gravado no config.yaml).\n\n" +
    "/verificar — procurar notícias agora\n/estado — como correu a última verificação\n" +
    "/fontes — fontes sugeridas por decidir\n/ajuda — esta mensagem");
}

async function tratarBotao(env, cq) {
  const chat = String((cq.message && cq.message.chat && cq.message.chat.id) || "");
  const aviso = texto => tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: texto.slice(0, 190), show_alert: texto.length > 60 }).catch(() => {});
  if (chat !== String(env.TELEGRAM_CHAT_ID || "")) return aviso("Este bot é privado.");
  const [tipo, letra, dominio] = String(cq.data || "").split("|");
  const lista = LISTAS[letra];
  if (tipo !== "f" || !lista || !DOMINIO_OK.test(dominio || "")) return aviso("Já tratado.");
  try {
    const mudou = await gravarDecisao(env, dominio, lista);
    await aviso(mudou ? "Guardado: " + dominio + " → " + NOMES[lista] : dominio + " já estava em " + NOMES[lista]);
    await tg(env, "editMessageReplyMarkup", {
      chat_id: chat, message_id: cq.message.message_id,
      reply_markup: { inline_keyboard: [[{ text: "✅ " + dominio + " → " + NOMES[lista], callback_data: "x" }]] },
    }).catch(() => {});
  } catch (e) {
    await aviso("Não consegui gravar: " + e.message);
  }
}

function quando(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "?";
  return d.toLocaleString("pt-PT", { timeZone: "Europe/Lisbon", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function textoEstado(env) {
  let est;
  try { est = await lerEstado(env); } catch (e) { return "❌ Não consegui ler o estado: " + esc(e.message); }
  const ex = (est.execucoes || []).slice(-1)[0];
  const linhas = ["📊 <b>Estado do agregador</b>"];
  if (ex) {
    linhas.push("Última verificação: " + quando(ex.ts) + (ex.silencio ? " (silêncio)" : ""));
    linhas.push("Alertas enviados nessa: " + (ex.alertas || 0));
    for (const p of ex.pesquisas || []) linhas.push("• " + esc(p.nome) + ": " + (p.recolhidas || 0) + " recolhidas, " + (p.relevantes || 0) + " relevantes");
    if ((ex.falhas || []).length) linhas.push("⚠️ Fontes com falha: " + ex.falhas.length);
    for (const e of (ex.erros || []).slice(0, 3)) linhas.push("❌ " + esc(String(e).slice(0, 200)));
  } else {
    linhas.push("Ainda não há verificações registadas.");
  }
  linhas.push("", "À espera do resumo: " + (est.resumo || []).length,
    "Alertas adiados: " + (est.adiados || []).length,
    "Fontes por decidir: " + Object.keys(est.sugeridas || {}).length + (Object.keys(est.sugeridas || {}).length ? " (/fontes)" : ""));
  return linhas.join("\n");
}

async function enviarFontes(env, chat) {
  let sug;
  try { sug = (await lerEstado(env)).sugeridas || {}; } catch (e) { return responder(env, chat, "❌ Não consegui ler o estado: " + esc(e.message)); }
  const lista = Object.values(sug).slice(0, 10);
  if (!lista.length) return responder(env, chat, "Não há fontes por decidir. 👍");
  for (const s of lista) {
    const d = String(s.dominio || "");
    const botoes = ["c", "n", "b"].map(l => ({ text: { c: "⭐ Confiável", n: "😐 Neutra", b: "🚫 Bloquear" }[l], callback_data: "f|" + l + "|" + d }))
      .filter(b => new TextEncoder().encode(b.callback_data).length <= 64);
    await responder(env, chat,
      "🔎 <b>" + esc(s.nome || d) + "</b> (" + esc(d) + ")\nApareceu em " + (s.n || 0) + " notícias relevantes\nExemplo: " + esc(s.exemplo || "") +
      (s.feed ? "\n📡 Feed: " + esc(s.feed) : ""),
      botoes.length ? { reply_markup: { inline_keyboard: [botoes] } } : {});
  }
}

// ------------------------------------------------------------------ instalação

async function instalar(env, url) {
  const txt = (s, status = 200) => new Response(s + "\n", { status, headers: { "content-type": "text/plain; charset=utf-8" } });
  if (!env.WEBHOOK_SECRET || url.searchParams.get("chave") !== env.WEBHOOK_SECRET) {
    return txt("Chave errada. Abre /instalar?chave=<o teu WEBHOOK_SECRET>.", 403);
  }
  if (!/^[A-Za-z0-9_-]{1,256}$/.test(env.WEBHOOK_SECRET)) {
    return txt("O WEBHOOK_SECRET só pode ter letras, números, _ e - (é uma regra do Telegram).", 400);
  }
  const res = [];
  try {
    await tg(env, "setWebhook", {
      url: url.origin + "/telegram", secret_token: env.WEBHOOK_SECRET,
      allowed_updates: ["message", "callback_query"], drop_pending_updates: true,
    });
    await tg(env, "setMyCommands", { commands: COMANDOS });
    res.push("✅ Telegram: o bot passa a falar com este Worker.");
  } catch (e) {
    res.push("❌ Telegram: " + e.message + " (confirma o TELEGRAM_BOT_TOKEN)");
  }
  res.push(env.TELEGRAM_CHAT_ID ? "✅ TELEGRAM_CHAT_ID definido."
    : "⚠️ Falta o TELEGRAM_CHAT_ID: manda /start ao bot, ele responde com o número; guarda-o no Worker e no GitHub.");
  try {
    await gh(env, `/repos/${repo(env)}/actions/workflows/${WORKFLOW}`);
    await lerFicheiro(env, "config.yaml");
    res.push("✅ GitHub: o token chega ao repositório " + repo(env) + " (para gravar e correr precisa de Contents e Actions: Read and write).");
  } catch (e) {
    res.push("❌ GitHub: " + e.message);
  }
  res.push("", "Falta só confirmar que o Cron Trigger */15 * * * * está ativo (Settings > Trigger events).");
  return txt(res.join("\n"));
}
