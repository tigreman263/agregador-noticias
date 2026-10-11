// Despertador do agregador em Cloudflare Workers (gratuito).
// De 15 em 15 minutos pede ao GitHub uma verificação (workflow_dispatch, acao=agendada).
// O agregador só verifica a sério quando já passou geral.intervalo_minutos, por isso
// pedidos a mais não fazem mal (e podes manter também o despertador da Google).
//
// Configuração (ver README, secção 2.9):
//   - Cron Trigger: */15 * * * *
//   - Segredo do Worker: GITHUB_TOKEN (token fine-grained, só Actions: Read and write)

const REPO = "tigreman263/agregador-noticias";
const WORKFLOW = "agregador.yml";

async function acordar(env) {
  if (!env.GITHUB_TOKEN) throw new Error("falta o segredo GITHUB_TOKEN no Worker");
  let ultimo = "";
  for (let tentativa = 1; tentativa <= 3; tentativa++) {
    try {
      const r = await fetch(
        `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.GITHUB_TOKEN}`,
            Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "despertador-agregador",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ ref: "main", inputs: { acao: "agendada" } }),
        }
      );
      if (r.status === 204) return;  // pedido aceite
      ultimo = `GitHub respondeu ${r.status}`;
      if (r.status === 401 || r.status === 403 || r.status === 404) break;  // token/permissões: repetir não ajuda
    } catch (e) {
      ultimo = "falha de rede";
    }
    await new Promise((res) => setTimeout(res, 2000 * tentativa));
  }
  throw new Error(`não consegui acordar o agregador: ${ultimo}`);
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(acordar(env));
  },
  // Abrir o endereço do Worker no navegador só mostra que está vivo (não acorda nada).
  async fetch() {
    return new Response("Despertador do agregador: ativo. Corre por agendamento.");
  },
};
