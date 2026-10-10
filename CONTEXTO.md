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
| `painel/index.html` | **Painel** ligado ao GitHub (ver abaixo). Publicado no GitHub Pages. |
| `.nojekyll` | Diz ao GitHub Pages para servir os ficheiros tal como estão. |

## O painel (`painel/index.html`)

Página única, sem servidor, publicada em https://tigreman263.github.io/agregador-noticias/painel/ (GitHub Pages a partir da raiz do ramo `main`). Fala diretamente com a API do GitHub (decisão de 2026-10-10, para manter "sem servidor e sem custos"):
- **Lê** `config.yaml`, `estado.json` e as execuções do workflow. O repositório é público, por isso ler funciona sem token.
- **Grava** com um token fine-grained do utilizador (só este repositório; Contents e Actions: Read and write), guardado no `localStorage` desse navegador. Cada gravação é um commit "painel: …".
- Ao gravar, só reescreve a secção mudada (`pesquisas` ou `fontes`) e confirma, antes de gravar, que as outras secções ficaram iguais; os comentários fora dessa secção mantêm-se.
- **Corre ações** (normal, simular, teste, descobrir-fontes) por `workflow_dispatch` e acompanha a execução.
- Mostra o registo que o `agregador.py` guarda no `estado.json`: `execucoes` (últimas 48: notícias lidas/relevantes por pesquisa, alertas, resumo, falhas de fontes, erros) e `enviados` (últimos 100 alertas/itens de resumo enviados).
- YAML lido com js-yaml 4.1.0 (cdnjs). Todo o texto vindo das notícias é escapado (há um token no `localStorage`).

## Estado atual (2026-10-10)

- A versão nova está no GitHub e a correr de 30 em 30 minutos. O teste do WhatsApp foi aceite pelo CallMeBot.
- O site da Câmara da Sertã recusa ligações vindas dos servidores do GitHub ("Connection reset"); localmente funciona.

## Próximos passos sugeridos

1. Criar o token do painel e testar a gravação de uma pesquisa.
2. Resolver o bloqueio da Câmara da Sertã a partir do GitHub (ou depender do Google Notícias).
3. Variantes de palavras (por exemplo "regulação", "regulamento", "regulamentação" devem contar como o mesmo conceito).
5. Mais tarde: ligar ao painel geral Olimpo (junto com o Caçador de Oportunidades e o Argos).
