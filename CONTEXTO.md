# Contexto do projeto (para quem continuar o desenvolvimento)

Resume as decisões técnicas, para que outra ferramenta ou pessoa consiga continuar sem o
histórico da conversa. O guia de utilização, passo a passo, está no `README.md`.

## Objetivo

Agregador de notícias pessoal:
1. O utilizador cria **pesquisas** (temas) no painel, com palavras-chave por prioridade
   (alta, média, baixa), palavras obrigatórias e palavras a excluir.
2. O agregador recolhe notícias de várias fontes e procura **fontes novas** todos os dias.
3. Filtra e pontua pelo interesse e pela confiança da fonte (confiáveis, neutras, bloqueadas).
4. Envia **alertas e um resumo diário por Telegram**, com botões para decidir as fontes.

## Decisões já tomadas

- **Sem custos e sem servidor.** Corre no GitHub Actions, no repositório **público**
  `tigreman263/agregador-noticias`. Público porque o Actions é ilimitado (o workflow acorda
  de 15 em 15 minutos) e o painel lê sem token; os segredos ficam protegidos.
- **Frequência configurável (2026-10-10)**: o cron do GitHub não pode ler o config, por
  isso o workflow corre `*/15 * * * *`; um job "decidir" sem fila (`.github/ja_e_altura.py`,
  só biblioteca padrão; repetido no início do job "correr", que tem a fila) compara a
  última `estado.execucoes[-1].ts` com `geral.intervalo_minutos` (por omissão 30, mínimo 30,
  folga de 2,5 min). Se não for altura, os passos seguintes são saltados (sem commit).
  Execuções manuais correm sempre. O painel muda o valor em Início → Frequência.
- **Só Telegram (2026-11-01).** O WhatsApp (CallMeBot, 2026-10-09) aceitava os pedidos
  mas deixou de entregar; foi retirado. `enviar(texto, botoes)` usa a API oficial
  (`sendMessage`, `parse_mode: HTML`, texto escapado com `h()`/`ligacao()`), espera
  `PAUSA_ENVIO` (1 s) entre mensagens e repete após um 429. Segredos `TELEGRAM_BOT_TOKEN` e
  `TELEGRAM_CHAT_ID`; nunca aparecem em logs (`_sem_segredos`). Cada alerta é uma mensagem
  com botões (`botoes_alerta`: ⭐ Confiável / 🚫 Bloquear a fonte); cada fonte sugerida é uma
  mensagem com Confiável / Neutra / Bloquear (`botoes_sugestao`). O resumo é agrupado
  (`juntar_mensagens`, `MAX_MSG` 4000). Dados dos botões: `f|<c|n|b>|<domínio>` (máx. 64
  bytes; acima disso o botão não aparece). Não há "Descartar" no Telegram: o que lá chega já
  saiu da fila; o Descartar continua no painel.
- **Worker do Cloudflare (2026-11-01)**, `extras/cloudflare/worker.js`, um só ficheiro sem
  dependências (colado no painel do Cloudflare, ou `wrangler deploy`). (1) Cron
  `*/15 * * * *` → `workflow_dispatch` com `acao=agendada` (substitui o Google Apps
  Script; se falhar, avisa no Telegram 1 vez por dia, às 9h). (2) Webhook `/telegram`
  (cabeçalho `X-Telegram-Bot-Api-Secret-Token` = SHA-256 de "agregador-webhook:" + token do
  bot, `segredoWebhook`, para não haver mais um segredo; só obedece a
  `TELEGRAM_CHAT_ID`): botões → `decidirFonte` edita linha a linha a secção `fontes:` do
  `config.yaml` (listas de uma linha, como o painel grava; Confiável junta o feed da
  sugestão em `estado.sugeridas`), PUT na API de conteúdos com repetição em 409; commit
  "telegram: …". Comandos `/verificar`, `/estado`, `/fontes`, `/ajuda`; `/start` diz o chat
  id a qualquer pessoa. Abrir a raiz do Worker (GET `/`) faz `setWebhook` + `setMyCommands`
  e testa o token do GitHub (é idempotente). Segredos do Worker: `GITHUB_TOKEN` (Contents +
  Actions RW), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Pedido de 2026-11-01: o
  utilizador quer regularidade (fica o Cloudflare) mas com menos passos. A recolha ficou no GitHub de
  propósito: o plano gratuito dos Workers dá 10 ms de CPU e 50 pedidos por invocação (não
  chega para ler e analisar dezenas de fontes) e não permite o Tailscale do telemóvel.
- **Fontes abertas**: Google Notícias, feeds RSS e páginas de notícias sem RSS. X,
  Instagram e Facebook estão fora por acesso restrito ou pago. Domínios `.br` bloqueados
  no config (`bloqueadas: ["br"]`; `dominio_em` faz correspondência por sufixo).
- **Páginas sem RSS**: lidas com BeautifulSoup (`ler_pagina`). Com seletores CSS (`item`,
  `titulo`, `resumo`, `data`) ou por deteção automática: agrupa os links pelo tipo de cartão
  e fica com o grupo que mais parece notícias (maior média de pontos, depois o maior),
  prefere títulos de cabeçalhos ao `alt` das imagens e procura a data subindo no cartão
  (datas futuras ignoradas). Notícias sem data ficam com a data da 1.ª vez vistas
  (`estado.raspadas`); na 1.ª leitura de uma página contam como antigas. Se a página
  anunciar um feed, usa-o (`usar_feed: false` ou `--sem-feed` desligam).
- **`local: true`** (só em `feeds_extra`/`paginas_extra`): dispensa as palavras obrigatórias.
- **Feeds escondidos**: `descobrir_feed` tenta os feeds anunciados, links com rss/feed/atom,
  `?format=feed&type=rss` (Joomla) e caminhos habituais. `--procurar-feeds` faz isto para
  os sites que aparecem numa pesquisa do Google Notícias.
- **Sites que bloqueiam o GitHub (2026-10-10)**: a Câmara da Sertã corta as ligações dos
  servidores do GitHub (EUA, Microsoft) em qualquer User-Agent; testado com um workflow de
  diagnóstico. Solução gratuita escolhida pelo utilizador: o telemóvel Android dele como
  saída Tailscale (exit node). Quando uma fonte recusa a ligação, o agregador marca o
  domínio em `estado.bloqueados` (30 dias). O workflow liga-se ao Tailscale (segredos
  `TS_OAUTH_CLIENT_ID`/`TS_OAUTH_SECRET`, etiqueta `tag:ci`, `--accept-dns=false`), corre
  `--buscar-pelo-telemovel` (usa o telemóvel como saída só durante esse passo e guarda
  cópias em `.cache_telemovel/`), e o agregador lê essas cópias (`obter`). Sem os segredos
  ou sem o telemóvel, os passos não fazem nada. NordVPN/VPN paga e Amnezia foram postos de
  lado (custo, ou servidores de centro de dados que podem ser bloqueados à mesma).
- **Sem base de dados.** O estado vive em `estado.json` (gravado só pelo workflow, com
  `git pull --rebase -X theirs` antes do push). O painel nunca o grava: as notícias
  descartadas vão para `painel.json`, que o agregador aplica no início de cada execução.
- **O GitHub é a fonte de verdade** do `config.yaml`: o utilizador edita-o no painel. Não
  copiar versões locais por cima.

## Como pontua (em `agregador.py`)

`nota = (pontos das palavras + bónus) × peso da fonte`

- Palavra: alta 10, média 4, baixa 1. No título vale ×2. Cada palavra conta uma vez por notícia.
- Comparação sem acentos nem maiúsculas. Palavras de até 3 letras só valem inteiras; as
  outras aceitam plurais.
- Palavra de exclusão: a notícia é descartada. Falta de uma palavra obrigatória: também.
- Bónus: +5 por cada fonte extra com a mesma notícia (máx. +15) e +3 se tiver menos de 1 hora.
- Fonte confiável ×1,5, desconhecida ×1,0, bloqueada descartada (também na fila).
- Duplicados: títulos muito parecidos contam como uma só notícia; `vistos` guarda 14 dias.
- Nota ≥ `limite_alerta` (por omissão 25): alerta. Entre `limite_resumo` (por omissão 10)
  e o limite de alerta: resumo diário. Abaixo: ignorada.
- Silêncio (23h–7h): os alertas ficam adiados. Se o envio falhar, ficam adiados e marcados
  como vistos (não duplicam).

## Descoberta de fontes

1 vez por dia, a partir das 9h: pesquisa variações de cada tema, regista que sites publicam
notícias relevantes (`estado.dominios`), escolhe os que têm pelo menos 2 (máx. 5 por dia,
10 por decidir), procura o feed e envia cada uma pelo Telegram com botões. A decisão faz-se
no botão (Worker) ou no painel (Confiável junta também o feed aos feeds gerais). Sem decisão em 14 dias, é esquecida.
Ao apagar uma pesquisa, `esquecer_pesquisas_apagadas` limpa o que ela deixou no estado.

## Estrutura

| Ficheiro | O que é |
|---|---|
| `agregador.py` | Toda a lógica (recolha, raspador, pontuação, Telegram, descoberta, telemóvel). |
| `config.yaml` | Pesquisas, fontes, pesos e horários. Editado sobretudo pelo painel. |
| `estado.json` | Estado gravado pelo workflow: `vistos`, `resumo`, `adiados`, `sugeridas`, `dominios`, `raspadas`, `bloqueados`, `execucoes` (48), `enviados` (100). |
| `painel.json` | Notícias descartadas no painel (`descartados`: id + data; o painel apaga as com mais de 30 dias). |
| `.github/workflows/agregador.yml` | Acorda de 15 em 15 min, verifica se é altura (`intervalo_minutos`), Tailscale opcional e ações manuais: normal, teste, simular, descobrir-fontes. |
| `painel/index.html` | Painel (ver abaixo). |
| `extras/cloudflare/` | Worker do Cloudflare (`worker.js`) e `wrangler.toml`: despertador e bot do Telegram. |
| `.nojekyll` | O GitHub Pages serve os ficheiros tal como estão. |
| `README.md` | Guia passo a passo para o utilizador; mostrado também na secção Ajuda do painel. |
| `.claude/agents/` | Subagentes do Claude Code: recolha-raspador, pontuacao-relevancia, notificacoes-telegram, painel-web, verificador e utilizador-tester. |

## O painel (`painel/index.html`)

Página única, sem servidor, em https://tigreman263.github.io/agregador-noticias/painel/
(GitHub Pages a partir da raiz do ramo `main`). Fala diretamente com a API do GitHub:
- **Lê** `config.yaml`, `estado.json`, `painel.json`, `README.md` e as execuções do
  workflow (sem token, porque o repositório é público).
- **Grava** com um token fine-grained do utilizador (só este repositório; Contents e
  Actions: Read and write), guardado no `localStorage`. Cada gravação é um commit "painel: …".
  Só reescreve a secção mudada (`pesquisas` ou `fontes`) e confirma que o resto ficou igual.
- **Corre ações** por `workflow_dispatch` e acompanha a execução.
- Secções: Início, Pesquisas, Atividade (com Descartar), Fontes, Ligação, Ajuda (README
  renderizado com marked 12.0.2 + DOMPurify 3.1.6).
- Bibliotecas por cdnjs: js-yaml 4.1.0, marked, DOMPurify. Todo o texto vindo das notícias
  é escapado e o README é sanitizado (há um token no `localStorage`).

## Estado atual (2026-11-01)

- De 2026-10-11 a 2026-11-01 todas as execuções falharam (`NameError: DOMINIOS_IGNORADOS`,
  constante apagada sem querer no commit do Telegram); corrigido. A ação do Tailscale
  também falhava com o nome do anfitrião vazio; o workflow passa agora `hostname`.
- Envios só por Telegram (bot @Agregador_telmo_bot; segredos TELEGRAM_* no GitHub desde
  2026-11-01). Os segredos WHATSAPP_* foram apagados.
- Worker do Cloudflare instalado (2026-11-01) por Workers Builds ligado ao repositório:
  comando `cd extras/cloudflare && npx wrangler deploy`, endereço
  https://agregador-noticias.investrade-telmosilva.workers.dev (o interruptor workers.dev
  teve de ser ligado à mão no Cloudflare; `workers_dev = true` no toml não chegou).
  Webhook do Telegram aponta para `/telegram`; as execuções "automática (Cloudflare)" correm.
- Palavras-chave (2026-11-01): singular e plural contam como a mesma (`singular()`, só na
  última palavra, só acrescenta variantes) e variantes do mesmo conceito juntam-se com "/"
  (`variantes()`/`achar()`), contando uma só vez; nas obrigatórias basta uma, no excluir
  qualquer uma (à palavra inteira). O utilizador não quer trocar os tokens.
- O painel mostra o estado do despertador (Início → Frequência e Ligação → Telegram e
  Cloudflare), a partir do título das execuções; o endereço do Worker fica no localStorage.
- O utilizador usa o painel com token: pesquisas "Sertã" e "Apoio Estado".
- Tailscale configurado (2026-10-10): telemóvel 'Redmi Note 12 Pro+ 5G' aprovado como
  exit node; segredos TS_OAUTH_* no GitHub; a Câmara da Sertã é trazida pelo telemóvel.
- O agendador do GitHub está a falhar muitas execuções automáticas neste repositório
  (desde o 1.º dia, com qualquer versão do código: só 4 a 5 execuções por dia). O
  despertador passou a ser o Worker do Cloudflare (2026-11-01), escolhido pelo utilizador;
  o Google Apps Script e o cron-job.org foram postos de lado. O `schedule` fica como reserva.

## Próximos passos sugeridos

1. Rever a leitura de sites sem RSS (pedido do utilizador em 2026-11-01).
2. Botões "útil / não útil" nos alertas para aprender o que interessa (agora possível, via
   Worker).
3. Mais tarde: ligar ao painel geral Olimpo (junto com o Caçador de Oportunidades e o Argos).
