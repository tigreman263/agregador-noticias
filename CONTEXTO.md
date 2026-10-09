# Contexto do projeto (para quem continuar o desenvolvimento)

Este ficheiro resume tudo o que foi decidido até agora, para que outra ferramenta
ou pessoa consiga continuar sem ter o histórico da conversa.

## Objetivo

Agregador de notícias pessoal:
1. Crias uma **pesquisa** (tema). O sistema gera palavras-chave por prioridade (alta, média, baixa) e palavras a excluir.
2. Recolhe notícias de várias fontes e procura **fontes novas** regularmente.
3. Filtra e pontua pelo interesse e pela confiança da fonte. Tu manténs a lista de fontes confiáveis, neutras e bloqueadas.
4. Envia **alertas por Telegram**.

## Decisões já tomadas

- **Sem custos.** Corre no GitHub Actions, num repositório **privado**, de 30 em 30 minutos.
- **Só Telegram.** O WhatsApp não tem bots gratuitos nem fiáveis (a API oficial é paga; as bibliotecas não oficiais arriscam o bloqueio do número). Fica para mais tarde, se se aceitar o custo.
- **Fontes abertas** (Google Notícias e feeds RSS). X, Instagram e Facebook estão fora por acesso restrito ou pago.
- **Sem base de dados.** O estado vive em `estado.json`, que o workflow grava no repositório a cada execução.
- Configuração em `config.yaml`, sem mexer no código.

## Como pontua (em `agregador.py`)

`nota = (pontos das palavras + bónus) × peso da fonte`

- Palavra: alta 10, média 4, baixa 1. No título vale ×2. Cada palavra conta uma vez por notícia.
- Palavras de até 3 letras só valem inteiras; as outras aceitam plurais.
- Palavra de exclusão: a notícia é descartada.
- Bónus: +5 por cada fonte extra a publicar o mesmo (máx. +15) e +3 se tiver menos de 1 hora.
- Fonte confiável ×1,5, desconhecida ×1,0, bloqueada descartada.
- Duplicados: títulos muito parecidos contam como uma só notícia.
- Nota ≥ limite de alerta (25): mensagem imediata. Entre 10 e 24: resumo diário. Abaixo: ignorada.
- Horário de silêncio (23h–7h): os alertas ficam guardados e saem depois. Se o Telegram falhar, nada se perde.

## Descoberta de fontes

1 vez por dia, a partir das 9h: pesquisa variações de cada tema, regista que sites publicam notícias relevantes, escolhe os que têm pelo menos 2 (máx. 5 por dia, 10 por decidir), tenta encontrar o RSS e envia uma mensagem com os botões **Confiável / Neutra / Bloquear**. A decisão é lida na execução seguinte. Só são aceites toques vindos do teu chat.

## Estrutura

| Ficheiro | O que é |
|---|---|
| `agregador.py` | Toda a lógica (recolha, pontuação, Telegram, descoberta). |
| `config.yaml` | Pesquisas, palavras-chave, fontes, pesos e horários. |
| `.github/workflows/agregador.yml` | Agendamento (30 min) e ações manuais: normal, teste, descobrir-chat, simular, descobrir-fontes. |
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

- A app está no GitHub e o agendamento já corre, mas **falha por faltarem os segredos** `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` (Settings > Secrets and variables > Actions). O erro aparece como aviso vermelho na execução.
- Nunca correu com notícias reais nem com o Telegram real. A lógica foi testada só offline.
- Para obter o chat id: abrir o bot, Start, enviar "olá", e correr o workflow com a ação **descobrir-chat**.

## Próximos passos sugeridos

1. Criar os dois segredos, correr **teste** e **simular**, e corrigir o que o uso real mostrar.
2. Botões **Útil / Não útil** nos alertas, para aprender o que interessa.
3. Ligar o painel ao `config.yaml` e ao `estado.json`.
4. Variantes de palavras (por exemplo "regulação", "regulamento", "regulamentação" devem contar como o mesmo conceito).
5. Mais tarde: ligar ao painel geral Olimpo (junto com o Caçador de Oportunidades e o Argos).
