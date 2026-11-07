# Contexto do projeto (para quem continuar o desenvolvimento)

Resume as decisões técnicas, para que outra ferramenta ou pessoa consiga continuar sem o
histórico da conversa. O guia de utilização, passo a passo, está no `README.md`.

## Objetivo

Agregador de notícias pessoal:
1. O utilizador cria **pesquisas** (temas) no painel, com 4 perguntas: sítio, assuntos,
   palavras a excluir e frequência (secção "Pesquisas: formato simples").
2. O agregador recolhe notícias de várias fontes e procura **fontes novas** todos os dias.
3. Filtra (sítio E um assunto, sem palavras a excluir, fonte não bloqueada) e ordena por
   uma nota interna que o utilizador não vê.
4. Envia **alertas e um resumo diário por Telegram**, com botões para decidir as fontes.
5. Vigia **páginas** e avisa quando o texto delas muda.

## Decisões já tomadas

- **Sem custos e sem servidor.** Corre no GitHub Actions, no repositório **público**
  `tigreman263/agregador-noticias`. Público porque o Actions é ilimitado (o workflow acorda
  de 15 em 15 minutos) e o painel lê sem token; os segredos ficam protegidos.
- **Frequência**: o cron do GitHub não pode ler o config, por isso o workflow corre
  `*/15 * * * *`; um job "decidir" sem fila (`.github/ja_e_altura.py`, só biblioteca
  padrão) compara a última `estado.execucoes[-1].ts` com 15 min (se houver alguma
  `frequencia: urgente` no config, em pesquisas ou páginas vigiadas; a regex é por linha
  indentada) ou 60 min, com folga de 2,5 min. Se não for altura, o job "correr" é saltado
  (sem commit). Execuções manuais correm sempre. No agregador, `pesquisa_devida` e
  `vigia_devida` saltam, nas execuções automáticas, as pesquisas e páginas que ainda não
  estão na altura (`estado.ultima_pesquisa`, `estado.vigiadas[url].verificado`).
  (Até 2026-11-02 havia um `geral.intervalo_minutos` global; foi retirado.)
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
  "telegram: …". Comandos `/resumo`, `/verificar`, `/estado`, `/fontes`, `/painel`,
  `/ajuda` (e um teclado fixo com os mesmos botões); `/start` e `/id` dizem o chat id a
  qualquer pessoa. Abrir a raiz do Worker (GET `/`) faz `setWebhook` + `setMyCommands`
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
- **`local: true`** (só em `feeds_extra`/`paginas_extra`): dispensa as obrigatórias (o
  sítio); basta um assunto.
- **Feeds escondidos**: `descobrir_feed` tenta os feeds anunciados, links com rss/feed/atom,
  `?format=feed&type=rss` (Joomla) e caminhos habituais. `--procurar-feeds` faz isto para
  os sites que aparecem numa pesquisa do Google Notícias.
- **Sites que bloqueiam o GitHub (2026-10-10)**: a Câmara da Sertã corta as ligações dos
  servidores do GitHub (EUA, Microsoft) em qualquer User-Agent; testado com um workflow de
  diagnóstico. Solução gratuita escolhida pelo utilizador: o telemóvel Android dele como
  saída Tailscale (exit node). Quando uma fonte recusa a ligação, o agregador marca o
  domínio em `estado.bloqueados` (regras atuais em "Bloqueados revistos", abaixo). O workflow liga-se ao Tailscale (segredos
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

## Pesquisas: formato simples (2026-11-02)

O utilizador confundia obrigatórias/prioridades/notas e recebia notícias fora do contexto
("apoio" apanhava "apoio na Argentina"). O painel passou a pedir **4 perguntas**, gravadas
assim no `config.yaml`:

- `sitio`: a notícia TEM de o mencionar (variantes com "/"); pode ser um nome
  ("Fundo Ambiental") em vez de um lugar. Vazio = qualquer sítio.
- `assuntos`: lista; tem de ter PELO MENOS UM (variantes de cada um com "/").
- `excluir`: palavras que descartam.
- `frequencia`: `urgente` (verificada de 15 em 15 min, mensagem logo), `hora` (de hora a
  hora, mensagem logo; omissão) ou `diario` (de hora a hora, tudo no resumo diário).

`preparar_pesquisa()` (chamada em `carregar_config`) traduz isto para as regras internas:
obrigatórias = [sitio, todos os assuntos juntos com "/"], palavras.alta = assuntos (ou o
sítio), consulta do Google = variantes do sítio (ou dos assuntos) com `OR` e expressões
entre aspas, `limite_resumo` 1 e `limite_alerta` 1 (ou 10^9 se `diario`). Expressões com
várias palavras ("fundo ambiental") procuram-se inteiras, nunca às palavras soltas. O
formato antigo (`consulta`, `obrigatorias`, `palavras`, `limite_*` escritos à mão) foi
retirado em 2026-11-03, a pedido do utilizador: nenhuma pesquisa o usava.

**Experimentar** (botão no editor do painel): `workflow_dispatch` com `acao=experimentar`
e o input `pesquisa` (JSON com um `pedido` aleatório) → `agregador.py --experimentar`
corre a pesquisa sem enviar nem guardar o estado (vistos vazios) e grava
`experimentar.json` (o que passa, contagens e exemplos dos cortes: sem_sitio,
sem_assunto, excluida, antiga). O job usa o grupo de concorrência `experimentar` (não
espera pelo `agregador`). O painel lê o ficheiro de 8 em 8 s até o `pedido` coincidir.

**Frequência por pesquisa**: `.github/ja_e_altura.py` usa 15 min se houver alguma pesquisa
`urgente` no config (regex), senão 60; no agregador, `pesquisa_devida()` salta, nas
execuções automáticas, as pesquisas cuja `estado.ultima_pesquisa[nome]` ainda não passou
a frequência (folga 2,5 min). Pedidos manuais verificam todas. `geral.intervalo_minutos`
foi retirado do config e do painel.

## Filtro e nota interna (em `agregador.py`)

Desde o formato simples, **o utilizador não vê nem escolhe notas** (2026-11-03: a nota e
os níveis "alta/média/baixa" saíram dos alertas, do resumo e da Atividade do painel). A
nota continua a existir por dentro, só para ordenar:

`nota = (pontos das palavras + bónus) × peso da fonte` (`avaliar`, `pontos_palavras`)

- Filtro: palavra de exclusão (à palavra inteira) descarta; falta de uma obrigatória
  também (fontes `local` dispensam-nas); 0 pontos descarta; fonte bloqueada e notícia com
  mais de `idade_max_horas` também.
- Pontos: alta 10, média 4, baixa 1, ×2 no título, cada palavra (com as suas variantes "/")
  uma vez. Os assuntos são "alta" (ou o sítio, sem assuntos); média e baixa ficam vazias.
- Comparação sem acentos nem maiúsculas; singular/plural iguais (`singular`); palavras de
  até 3 letras só inteiras; expressões de várias palavras só inteiras.
- Bónus: +5 por fonte extra com a mesma notícia (máx. +15), +3 se tiver menos de 1 hora.
  Fonte confiável ×1,5, outra ×1,0.
- Duplicados: títulos muito parecidos contam como uma só notícia (`agrupar`); fica a
  versão de nota mais alta. `vistos` guarda 14 dias.
- Níveis: `limite_resumo` = `limite_alerta` = 1 (tudo o que passa é alerta), ou
  `limite_alerta` 10^9 em `diario` (tudo no resumo).
- A nota decide a ordem da fila de alertas (máx. `max_alertas_por_execucao`, o excesso vai
  para o resumo) e a ordem do resumo (`mensagens_resumo` manda todas, divididas por `juntar_mensagens`;
  até 2026-11-03 só as 15 primeiras, e o resto perdia-se).
- Fontes repetidas: o mesmo endereço nas fontes gerais e nas da pesquisa lê-se uma vez
  (`sem_repetidas`), com as opções da pesquisa (ex.: `local`).
- Silêncio (23h–7h): os alertas ficam adiados (até 50; o excesso vai para o resumo). Se o
  envio falhar, ficam adiados e marcados como vistos (não duplicam).

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
| `estado.json` | Estado gravado pelo workflow: `vistos`, `resumo`, `adiados`, `ultimo_resumo`, `sugeridas`, `sugeridas_antigas`, `dominios`, `ultima_descoberta`, `raspadas`, `paginas_lidas`, `bloqueados`, `lentos`, `testes_diretos`, `ultima_pesquisa`, `vigiadas`, `execucoes` (48), `enviados` (100). |
| `painel.json` | Notícias descartadas no painel (`descartados`: id + data; o painel apaga as com mais de 30 dias) e a limpeza da Atividade. |
| `experimentar.json` | Resultado do botão Experimentar (gravado pelo job `experimentar`). |
| `.github/workflows/agregador.yml` | Acorda de 15 em 15 min, verifica se é altura (`.github/ja_e_altura.py`), Tailscale opcional e ações manuais: normal, teste, simular, descobrir-fontes, agendada, experimentar. |
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
  Só reescreve a secção mudada (`pesquisas`, `fontes` ou `vigiar`) e confirma que o resto
  ficou igual.
- **Corre ações** por `workflow_dispatch` e acompanha a execução.
- Separadores: Início, Pesquisas (com Experimentar), Páginas (vigiadas), Atividade (com
  Descartar e Limpar), Fontes, Ligação, Ajuda (README renderizado com marked 12.0.2 +
  DOMPurify 3.1.6).
- Bibliotecas por cdnjs: js-yaml 4.1.0, marked, DOMPurify. Todo o texto vindo das notícias
  é escapado e o README é sanitizado (há um token no `localStorage`).

## Estado atual (2026-11-07)

- **3.ª via: Google Notícias (2026-11-07)**: o contaspoupanca.pt tem DataDome (403 com
  desafio JavaScript) e recusa também o telemóvel. Pedido do utilizador: todo o site novo
  passa sempre por direto → telemóvel → Google Notícias. `pelo_google(url, cfg)` lê
  `url_google_news("site:dominio")` e fica só com itens desse domínio. Em `recolher()`,
  quando uma fonte falha (exceto a própria procura do Google), usa-se `pelo_google`
  (registo `pelo_google`, `LIDOS_GOOGLE`). Em `vigiar_paginas()`, se o site falha, compara
  os títulos do Google; referência separada em `estado.vigiadas[url].linhas_google`
  (`via`: site/google, `erro_site`); pela via Google só conta o que entra (➕), não o que
  sai. 1.ª passagem para o Google manda "ℹ️ Não consigo ler…"; regresso ao site guarda
  nova referência sem aviso. `notar_acesso` continua a marcar o bloqueio, por isso o
  telemóvel é sempre tentado antes de ficar no Google.

- **Bloqueados revistos (2026-11-03)**: a Médio Tejo ficou presa no telemóvel por um
  único ReadTimeout (2026-11-02 03:45), porque a marca renovava-se a cada leitura pelo
  telemóvel e nunca expirava. Agora: `notar_acesso()` classifica cada ligação (recusa →
  `SITES_BLOQUEADOS`; `Timeout`/`SiteLento` → `SITES_LENTOS`, bloqueio só à 3.ª execução
  seguida, contador em `estado.lentos`; SSL não conta; lido sem cópia do telemóvel →
  `SITES_DIRETOS_OK`, que tira o domínio dos bloqueados). `atualizar_bloqueados()` aplica
  no fim de `executar` (não em simulação). No `--buscar-pelo-telemovel`, cada bloqueado
  sem `telemovel: true` fica de fora 1 vez em 24 h (`estado.testes_diretos`), para a
  verificação o tentar diretamente. A Câmara da Sertã continua a recusar o GitHub
  (ligação cortada pelo servidor, Plesk/nginx); a Médio Tejo voltou a ser lida
  diretamente.

- **Páginas vigiadas (2026-11-03)**: secção `vigiar:` no config.yaml (painel → separador
  Páginas). `vigiar_paginas()` no agregador.py corre em cada execução, depois das
  pesquisas: cada página tem a sua frequência (`FREQ_VIGIAR`: 15/60/1440 min, só nas
  automáticas), compara as linhas de texto visível (`texto_vigiado`, opcionalmente só o
  seletor `parte`) com as guardadas em `estado.vigiadas[url].linhas` (até 30 000
  caracteres), ignorando datas/horas (`RUIDO`) e linhas mudadas de sítio. 1.ª vez manda
  "👀 Comecei a vigiar"; mudança manda "🔎 Mudou" com ➕/➖ e botão de URL; 3 falhas
  seguidas mandam "⚠️". Falha de envio não atualiza a referência (reavisa). No silêncio
  não verifica. Sites que recusam o GitHub entram em `bloqueados` e vão pelo telemóvel
  (`todas_as_fontes` inclui as vigiadas, sem procurar feeds). O `ja_e_altura.py` já apanha
  `frequencia: urgente` das vigiadas (a regex é por linha indentada). Escolhas do
  utilizador: integrado no Agregador, só o texto conta, páginas juntas depois no painel.

- **Recomeço do zero (2026-11-02)**: a pedido do utilizador, apagadas as notícias
  encontradas (`vistos`, `resumo`, `adiados`, `enviados`, `raspadas`, `paginas_lidas` e os
  `descartados` do `painel.json`); fontes, sugestões e bloqueados ficaram.
- Pesquisas atuais: **"Sertã"** (`hora`; sítio Sertã / sertanense / sertaginense;
  assuntos apoio/subsídio/incentivo/comparticipação/candidatura,
  agricultura/agrícola/agricultor, floresta/florestal; `cm-serta.pt` em `paginas_extra`
  com `local: true`) e **"Apoio fundo ambiental"** (`diario`; sítio Fundo Ambiental / Vale
  Eficiência, sem assuntos). `fontes.paginas` tem também `cm-serta.pt` (geral). Página
  vigiada: `cm-serta` (notícias da Câmara, `urgente`, página inteira). O utilizador muda
  isto no painel: confirma sempre no `config.yaml` do GitHub.
- **Bot do Telegram (2026-11-02)**: `/resumo` (o que espera o próximo resumo; se vazio, o
  último resumo enviado, a partir de `enviados` tipo "resumo") e teclado fixo
  (📰 Resumo, 🔄 Verificar, 📊 Estado, 🗂 Fontes, 🖥 Painel — este responde com um botão de
  URL para o painel, porque os botões do teclado fixo não abrem endereços) — o Worker mapeia o texto dos botões
  para os comandos e chama `setMyCommands` no /start e /ajuda. O `agregador.py` põe o
  mesmo teclado (`TECLADO`) em todas as mensagens sem botões próprios (resumo, teste).
- O utilizador julgava que o Worker não respeitava a frequência: via execuções de 15 em
  15 min, mas eram despertares curtos (job "correr" saltado). Explicado no painel.
- **Pendente, por decisão do utilizador ("não vou implementar agora")**: dar o bot à
  esposa. Caminho explicado: grupo do Telegram com os dois e o bot; `/start@bot` no grupo
  dá o id (negativo); trocar `TELEGRAM_CHAT_ID` no GitHub e no Worker; BotFather
  `/setprivacy` → Disable (ou bot administrador) para os botões do teclado funcionarem no
  grupo. Alternativa (precisa de código): aceitar vários chat ids, cada um na sua conversa.

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
- Tailscale configurado (2026-10-10): telemóvel 'Redmi Note 12 Pro+ 5G' aprovado como
  exit node; segredos TS_OAUTH_* no GitHub; a Câmara da Sertã é trazida pelo telemóvel.
- O agendador do GitHub está a falhar muitas execuções automáticas neste repositório
  (desde o 1.º dia, com qualquer versão do código: só 4 a 5 execuções por dia). O
  despertador passou a ser o Worker do Cloudflare (2026-11-01), escolhido pelo utilizador;
  o Google Apps Script e o cron-job.org foram postos de lado. O `schedule` fica como reserva.

## Próximos passos sugeridos

0. Partilhar o bot com a esposa (ver "Pendente" acima), quando o utilizador quiser.
1. Rever a leitura de sites sem RSS (pedido do utilizador em 2026-11-01).
2. Botões "útil / não útil" nos alertas para aprender o que interessa (agora possível, via
   Worker).
3. Mais tarde: ligar ao painel geral Olimpo (junto com o Caçador de Oportunidades e o Argos).
