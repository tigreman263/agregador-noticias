# Agregador de Notícias

Procura notícias sobre os temas que definires, dá-lhes uma nota e avisa-te por Telegram.
Corre sozinho no GitHub, de 30 em 30 minutos, sem servidor e sem custos.

## Instalação (uma vez)

**1. Carregar os ficheiros para o repositório privado `agregador-noticias`**
- No GitHub: **Add file → Upload files** e carrega `agregador.py`, `config.yaml`,
  `requirements.txt` e `estado.json`.
- O agendamento vive numa pasta escondida. Cria-o assim: **Add file → Create new file**,
  no nome escreve `.github/workflows/agregador.yml` (as barras criam as pastas),
  cola lá o conteúdo do ficheiro `agregador.yml` que veio junto e faz **Commit changes**.

**2. Guardar o token (já feito se seguiste o guia anterior)**
- Settings → Secrets and variables → Actions → New repository secret
- Nome `TELEGRAM_BOT_TOKEN`, valor: o token do @BotFather.

**3. Descobrir o teu chat id**
- No Telegram, abre o teu bot, carrega em Start e envia "olá".
- No GitHub: separador **Actions → Agregador de Notícias → Run workflow**,
  escolhe **descobrir-chat** e corre. Abre a execução e procura a linha `Chat id: ...`.
- Cria um segundo segredo: nome `TELEGRAM_CHAT_ID`, valor: esse número.

**4. Testar**
- Actions → Run workflow → **teste**. Deves receber uma mensagem no Telegram.
- Depois **simular**: mostra no registo o que enviaria, sem enviar nada.
- A partir daí corre sozinho de 30 em 30 minutos.

## Personalizar

Edita `config.yaml` no GitHub (ícone do lápis). Aí defines:
- as **pesquisas**, com palavras-chave de prioridade alta, média e baixa e palavras a excluir;
- as **fontes** confiáveis, bloqueadas e feeds RSS extra (usa o domínio, ex: `publico.pt`);
- os **limites** de alerta, o horário de silêncio e a hora do resumo diário;
- os **pesos** da pontuação.

## Descoberta automática de fontes

Uma vez por dia (a partir da hora definida em `config.yaml`, secção `descoberta`), a app:

1. Volta a pesquisar cada tema com variações da consulta e das palavras de prioridade alta.
2. Regista que sites publicam notícias relevantes e ignora os que já classificaste.
3. Escolhe os que apareceram em pelo menos 2 notícias (até 5 por dia, e nunca mais de 10 por decidir).
4. Tenta encontrar o feed RSS de cada um.
5. Envia-te uma mensagem no Telegram por fonte, com os botões **Confiável / Neutra / Bloquear**.

Ao tocar num botão, a decisão fica guardada na verificação seguinte (até 30 minutos depois):
- **Confiável**: a fonte passa a valer ×1,5 e, se tinha feed, passa a ser lida diretamente.
- **Neutra**: deixa de ser sugerida, sem mudar o peso.
- **Bloquear**: as notícias dela são descartadas.

Só os toques vindos da tua conversa são aceites. Para forçar a procura já: Actions → Run workflow → **descobrir-fontes**.

## Como decide o que enviar

`nota = (pontos das palavras + bónus) × peso da fonte`

- Palavra no título vale o dobro da que aparece só no texto. Cada palavra conta uma vez.
- Bónus: +5 por cada fonte extra a publicar o mesmo (máx. +15) e +3 se tiver menos de 1 hora.
- Fonte confiável ×1,5, desconhecida ×1,0, bloqueada é descartada.
- Nota ≥ limite de alerta: mensagem imediata. Entre os dois limites: resumo diário.
- Notícias repetidas em vários sites contam como uma só e nunca são enviadas duas vezes.

## Painel (protótipo)

Abre `painel/index.html` no navegador (duplo clique, não precisa de instalação). Tem as secções Alertas, Pesquisas, Fontes e Definições, com notícias inventadas e a mesma pontuação da app. Serve para experimentares criar pesquisas, classificar fontes e ver a descoberta de fontes. Não envia nada nem altera o `config.yaml`.

Para o contexto completo do projeto (decisões, estado e próximos passos), vê `CONTEXTO.md`.

## Limites desta primeira versão

- Recolhe do Google Notícias e de feeds RSS que indiques. X, Instagram e Facebook não estão incluídos.
- Ainda não tem os botões Útil / Não útil nos alertas.
- O painel (`painel/index.html`) é ainda um protótipo em modo teste, não ligado à app real. A gestão faz-se editando `config.yaml`.
- Só Telegram. O WhatsApp fica para mais tarde.
- O GitHub pode atrasar alguns minutos as execuções agendadas.

## Correr no teu computador (opcional)

```
pip install -r requirements.txt
python agregador.py --simular
```
