# Contexto do projeto (para quem continuar o desenvolvimento)

Resume as decisões técnicas, para que outra ferramenta ou pessoa consiga continuar sem o
histórico da conversa. O guia de utilização, passo a passo, está no `README.md`.

## Objetivo

Agregador de notícias pessoal:
1. O utilizador cria **pesquisas** (temas) no painel, com palavras-chave por prioridade
   (alta, média, baixa), palavras obrigatórias e palavras a excluir.
2. O agregador recolhe notícias de várias fontes e procura **fontes novas** todos os dias.
3. Filtra e pontua pelo interesse e pela confiança da fonte (confiáveis, neutras, bloqueadas).
4. Envia **alertas e um resumo diário por WhatsApp** (CallMeBot).

## Decisões já tomadas

- **Sem custos e sem servidor.** Corre no GitHub Actions, no repositório **público**
  `tigreman263/agregador-noticias`. Público porque o Actions é ilimitado (o workflow acorda
  de 5 em 5 minutos) e o painel lê sem token; os segredos ficam protegidos.
- **Frequência configurável (2026-10-10)**: o cron do GitHub não pode ler o config, por
  isso o workflow corre `*/5 * * * *` e o 1.º passo (Python sem dependências) compara a
  última `estado.execucoes[-1].ts` com `geral.intervalo_minutos` (por omissão 30, mínimo 5,
  folga de 2,5 min). Se não for altura, os passos seguintes são saltados (sem commit).
  Execuções manuais correm sempre. O painel muda o valor em Início → Frequência.
- **WhatsApp via CallMeBot (2026-10-09).** Substituiu o Telegram. Gratuito, um pedido HTTP,
  mas só envia (sem botões nem respostas). Por isso as decisões sobre fontes fazem-se no
  painel, que grava no `config.yaml`. Como tem limites de envio apertados, os alertas de
  cada execução vão juntos (`juntar_mensagens`, `MAX_MSG`, `PAUSA_ENVIO`). A API da Meta e a
  Twilio foram postas de lado por custo; bibliotecas não oficiais por risco de bloqueio do
  número e por precisarem de um processo sempre ligado. O telefone segue com "+".
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
10 por decidir), procura o feed e envia a lista por WhatsApp. A decisão faz-se no painel
(Confiável junta também o feed aos feeds gerais). Sem decisão em 14 dias, é esquecida.
Ao apagar uma pesquisa, `esquecer_pesquisas_apagadas` limpa o que ela deixou no estado.

## Estrutura

| Ficheiro | O que é |
|---|---|
| `agregador.py` | Toda a lógica (recolha, raspador, pontuação, WhatsApp, descoberta, telemóvel). |
| `config.yaml` | Pesquisas, fontes, pesos e horários. Editado sobretudo pelo painel. |
| `estado.json` | Estado gravado pelo workflow: `vistos`, `resumo`, `adiados`, `sugeridas`, `dominios`, `raspadas`, `bloqueados`, `execucoes` (48), `enviados` (100). |
| `painel.json` | Notícias descartadas no painel (`descartados`: id + data; o painel apaga as com mais de 30 dias). |
| `.github/workflows/agregador.yml` | Acorda de 5 em 5 min, verifica se é altura (`intervalo_minutos`), Tailscale opcional e ações manuais: normal, teste, simular, descobrir-fontes. |
| `painel/index.html` | Painel (ver abaixo). |
| `.nojekyll` | O GitHub Pages serve os ficheiros tal como estão. |
| `README.md` | Guia passo a passo para o utilizador; mostrado também na secção Ajuda do painel. |
| `.claude/agents/` | Subagentes do Claude Code: recolha-raspador, pontuacao-relevancia, notificacoes-whatsapp, painel-web, verificador e utilizador-tester. |

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

## Estado atual (2026-10-10)

- A correr no GitHub (frequência configurável, 30 min por omissão); envios por WhatsApp a funcionar.
- O utilizador usa o painel com token: pesquisas "Sertã" e "Apoio Estado".
- Falta o utilizador configurar o Tailscale no telemóvel (README, passo 2.7) para a
  Câmara da Sertã ser lida.

## Próximos passos sugeridos

1. Confirmar a leitura da Câmara da Sertã pelo telemóvel depois de configurado o Tailscale.
2. Variantes de palavras ("regulação", "regulamento", "regulamentação" como o mesmo conceito).
3. Botões "útil / não útil" para aprender o que interessa (o CallMeBot não recebe respostas;
   teria de ser no painel).
4. Mais tarde: ligar ao painel geral Olimpo (junto com o Caçador de Oportunidades e o Argos).
