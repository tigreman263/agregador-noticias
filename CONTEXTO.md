# Contexto do projeto (para quem continuar o desenvolvimento)

Este ficheiro resume tudo o que foi decidido até agora, para que outra ferramenta
ou pessoa consiga continuar sem ter o histórico da conversa.

## Objetivo

Agregador de notícias pessoal:
1. Crias uma **pesquisa** (tema). O sistema gera palavras-chave por prioridade (alta, média, baixa) e palavras a excluir.
2. Recolhe notícias de várias fontes e procura **fontes novas** regularmente.
3. Filtra e pontua pelo interesse e pela confiança da fonte. Tu manténs a lista de fontes confiáveis, neutras e bloqueadas.
4. Envia **alertas por WhatsApp** (CallMeBot).

## Decisões já tomadas

- **Sem custos.** Corre no GitHub Actions, num repositório **privado**, de 30 em 30 minutos.
- **WhatsApp via CallMeBot (2026-10-09).** Substituiu o Telegram. É gratuito e funciona com um simples pedido HTTP, mas só envia: não há botões nem leitura de respostas. Por isso as decisões sobre fontes passaram para o `config.yaml` (`confiaveis`, `neutras`, `bloqueadas`). Como tem limites de envio apertados, os alertas de cada execução vão juntos em poucas mensagens. A API oficial da Meta e a Twilio foram postas de lado por custo; bibliotecas não oficiais por risco de bloqueio do número e por precisarem de um processo sempre ligado.
- **Fontes abertas** (Google Notícias, feeds RSS e páginas de notícias sem RSS). X, Instagram e Facebook estão fora por acesso restrito ou pago.
- **Páginas sem RSS**: lidas com BeautifulSoup (`ler_pagina`). Com seletores CSS (`item`, `titulo`, `resumo`, `data`) ou, sem eles, por deteção automática: agrupa os links pelo tipo de cartão e fica com o grupo que mais parece notícias (maior média de pontos, depois o maior; assim ignora menus), prefere títulos de cabeçalhos ao `alt` das imagens e procura a data subindo no cartão (datas futuras são ignoradas). Notícias sem data ficam com a data da 1.ª vez vistas; na 1.ª leitura de uma página contam como antigas. A opção `local: true` (em `paginas_extra`/`feeds_extra`) dispensa as palavras obrigatórias. Se a página anunciar um feed (`<link type=rss/atom>`), `ler_pagina` usa-o em vez de raspar (desliga-se com `usar_feed: false` ou `--sem-feed`).
- **Feeds escondidos**: `descobrir_feed` tenta os feeds anunciados na página, links com rss/feed/atom, `?format=feed&type=rss` (Joomla) e caminhos habituais (`/feed/`, `/rss`, `/rss.xml`, `/atom.xml`, `/index.xml`, `/feeds/posts/default`). `python agregador.py --procurar-feeds "<pesquisa ou texto>"` pesquisa no Google Notícias (30 dias), junta os sites e procura o feed de cada um em paralelo, mostrando YAML pronto a colar. As câmaras da Sertã, Vila de Rei e Oleiros têm feeds escondidos; a Sertã já é lida pelo feed.
- **Sem base de dados.** O estado vive em `estado.json`, que o workflow grava no repositório a cada execução.
- Configuração em `config.yaml`, sem mexer no código.

## Como pontua (em `agregador.py`)

`nota = (pontos das palavras + bónus) × peso da fonte`

- Palavra: alta 10, média 4, baixa 1. No título vale ×2. Cada palavra conta uma vez por notícia.
- Palavras de até 3 letras só valem inteiras; as outras aceitam plurais.
- Palavra de exclusão: a notícia é descartada. Falta de uma palavra **obrigatória**: também.
- Bónus: +5 por cada fonte extra a publicar o mesmo (máx. +15) e +3 se tiver menos de 1 hora.
- Fonte confiável ×1,5, desconhecida ×1,0, bloqueada descartada.
- Duplicados: títulos muito parecidos contam como uma só notícia.
- Nota ≥ `limite_alerta` da pesquisa (por omissão 25): mensagem imediata. Entre `limite_resumo` (por omissão 10) e o limite de alerta: resumo diário. Abaixo: ignorada.
- Horário de silêncio (23h–7h): os alertas ficam guardados e saem depois. Se o WhatsApp falhar, nada se perde.

## Descoberta de fontes

1 vez por dia, a partir das 9h: pesquisa variações de cada tema, regista que sites publicam notícias relevantes, escolhe os que têm pelo menos 2 (máx. 5 por dia, 10 por decidir), tenta encontrar o RSS e envia a lista por WhatsApp. A decisão faz-se juntando o domínio a `fontes.confiaveis`, `fontes.neutras` ou `fontes.bloqueadas`; a sugestão sai da lista de pendentes na execução seguinte. Sem decisão em 14 dias, é esquecida e não volta.

## Estrutura

| Ficheiro | O que é |
|---|---|
| `agregador.py` | Toda a lógica (recolha, raspador de páginas, pontuação, WhatsApp, descoberta). |
| `config.yaml` | Pesquisas, palavras-chave, fontes, páginas sem RSS, pesos e horários. |
| `.github/workflows/agregador.yml` | Agendamento (30 min) e ações manuais: normal, teste, simular, descobrir-fontes. |
| `.claude/agents/` | Equipa de subagentes do Claude Code: recolha-raspador, pontuacao-relevancia, notificacoes-whatsapp, painel-web, verificador e utilizador-tester. |
| `estado.json` | Estado gravado automaticamente pelo workflow. |
| `painel/index.html` | **Painel** (protótipo navegável, ver abaixo). |

## O painel (`painel/index.html`)

Página única, sem dependências nem servidor: abre-se no navegador. Tem quatro secções:
**Alertas**, **Pesquisas**, **Fontes** e **Definições**. Funciona em **modo teste**, com 21 notícias inventadas e a mesma lógica de pontuação do `agregador.py`, e guarda os dados no `localStorage` do navegador.

O que já faz: criar e editar pesquisas, gerar palavras-chave, classificar fontes, simular a descoberta de fontes e ver o efeito nos alertas ao mudar os pesos.

**Ainda não está ligado à app real.** Para isso falta um passo, por decidir:
- ler e gravar o `config.yaml` e o `estado.json` através da API do GitHub (com um token), ou
- servir o painel com um pequeno backend.

A função "Gerar palavras" usa o Claude quando a página corre dentro do Claude e cai numa regra simples fora dele.

## Estado atual

- A versão no GitHub ainda é a antiga (Telegram). A versão local já usa WhatsApp e tem de ser carregada, com os segredos `WHATSAPP_TELEFONE` e `WHATSAPP_APIKEY`.
- `--simular` corre com notícias reais (Google Notícias + página da Câmara da Sertã). O envio real por WhatsApp ainda não foi testado (faltam a apikey do CallMeBot e os segredos).

## Próximos passos sugeridos

1. Ativar o CallMeBot, criar os dois segredos, carregar os ficheiros novos, correr **teste** e **simular**.
2. Painel: passar de Telegram para WhatsApp e mostrar páginas sem RSS e palavras obrigatórias.
3. Ligar o painel ao `config.yaml` e ao `estado.json`.
4. Variantes de palavras (por exemplo "regulação", "regulamento", "regulamentação" devem contar como o mesmo conceito).
5. Mais tarde: ligar ao painel geral Olimpo (junto com o Caçador de Oportunidades e o Argos).
