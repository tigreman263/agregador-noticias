# Agregador de Notícias

Procura notícias sobre os temas que escolheres e envia-te por **Telegram** as que falam
do sítio e dos assuntos que te interessam, com botões para decidires as fontes. Também
**vigia páginas** (editais, concursos, apoios) e avisa-te quando mudam. Corre sozinho no
GitHub, com a frequência que escolheres em cada pesquisa (de 15 em 15 minutos, de hora a
hora ou uma vez por dia), acordado por um Worker gratuito do Cloudflare, sem servidor e
sem custos. Geres tudo num **painel** que abres no computador ou no telemóvel.

- Repositório: https://github.com/tigreman263/agregador-noticias
- Painel: https://tigreman263.github.io/agregador-noticias/painel/

> **Neste projeto, os três tokens do GitHub (Worker, painel no computador e painel no
> telemóvel) estão sem validade (No expiration): não há nada a renovar.** Se criares
> tokens novos, escolhe também **No expiration**; se escolheres uma data, vê a
> [secção 12](#12-manutenção-o-que-expira-e-como-renovar) e põe um lembrete.

## Índice

1. [Como funciona](#1-como-funciona)
2. [Instalação passo a passo](#2-instalação-passo-a-passo)
   - [2.1 Repositório no GitHub](#21-repositório-no-github)
   - [2.2 Criar o bot do Telegram](#22-criar-o-bot-do-telegram)
   - [2.3 Guardar os segredos no GitHub](#23-guardar-os-segredos-no-github)
   - [2.4 Primeiro teste](#24-primeiro-teste)
   - [2.5 Publicar o painel (GitHub Pages)](#25-publicar-o-painel-github-pages)
   - [2.6 Token do painel (para editar)](#26-token-do-painel-para-editar)
   - [2.7 (Opcional) Telemóvel para sites que bloqueiam o GitHub](#27-opcional-telemóvel-para-sites-que-bloqueiam-o-github)
   - [2.8 Cloudflare: despertador e botões do Telegram](#28-cloudflare-despertador-e-botões-do-telegram)
3. [Usar o painel](#3-usar-o-painel)
4. [Criar e afinar pesquisas](#4-criar-e-afinar-pesquisas)
   - [Como as palavras são comparadas](#como-as-palavras-são-comparadas)
   - [Por que ordem chegam](#por-que-ordem-chegam)
   - [Dicas](#dicas)
5. [Fontes de notícias](#5-fontes-de-notícias)
   - [5.1 Google Notícias](#51-google-notícias)
   - [5.2 Confiáveis, neutras e bloqueadas](#52-confiáveis-neutras-e-bloqueadas)
   - [5.3 Feeds RSS](#53-feeds-rss)
   - [5.4 Sites sem RSS](#54-sites-sem-rss)
   - [5.5 Encontrar feeds RSS escondidos](#55-encontrar-feeds-rss-escondidos)
   - [5.6 Descoberta automática de fontes](#56-descoberta-automática-de-fontes)
   - [5.7 Sites que bloqueiam o GitHub](#57-sites-que-bloqueiam-o-github)
   - [5A. Vigiar páginas (avisos de mudanças)](#5a-vigiar-páginas-avisos-de-mudanças)
6. [O que recebes no Telegram](#6-o-que-recebes-no-telegram)
7. [Referência do config.yaml](#7-referência-do-configyaml)
8. [Usar no computador (opcional)](#8-usar-no-computador-opcional)
9. [Ficheiros do projeto](#9-ficheiros-do-projeto)
10. [Resolução de problemas](#10-resolução-de-problemas)
11. [Limites](#11-limites)
12. [Manutenção: o que expira e como renovar](#12-manutenção-o-que-expira-e-como-renovar)

---

## 1. Como funciona

Cada pesquisa tem a sua frequência (**urgente**: de 15 em 15 minutos; **de hora a hora**;
ou **uma vez por dia**, só no resumo). Quando chega a altura, o GitHub corre o programa
`agregador.py`, que:

1. **Recolhe** notícias do Google Notícias (uma procura por pesquisa), dos feeds RSS que
   indicares e de sites sem RSS (lê a página de notícias diretamente).
2. **Filtra**: fica só com as que falam do **sítio** e de **pelo menos um assunto** da
   pesquisa, e que não têm nenhuma palavra a excluir. Notícias repetidas em vários sites
   contam como uma só.
3. **Envia por Telegram**: nas pesquisas urgentes e de hora a hora, uma mensagem logo por
   notícia; nas de uma vez por dia, tudo no resumo diário.
4. **Vigia as páginas** que escolheste e avisa se o texto delas mudou.
5. **Guarda** o que já viu e o que fez no `estado.json`, para não repetir nada.
6. Uma vez por dia, **procura fontes novas** e sugere-tas.

| Peça | O que é |
|---|---|
| GitHub Actions | Corre o agregador com a frequência escolhida (gratuito). |
| `config.yaml` | As tuas pesquisas, páginas vigiadas, fontes e regras. Editas no painel. |
| `estado.json` | A memória do agregador (o que já viu, o que enviou, o que está à espera). Gravado pelo GitHub a cada execução; não o edites. |
| `painel.json` | Notícias que descartaste no painel. Gravado pelo painel. |
| Painel | Página para gerir tudo e ver a atividade (GitHub Pages). |
| Bot do Telegram | Entrega os alertas, o resumo, os avisos das páginas vigiadas e as fontes sugeridas (gratuito). |
| Worker do Cloudflare | Acorda o agregador de 15 em 15 minutos (o agendador do GitHub salta execuções) e trata os botões e comandos do bot (gratuito). |
| Telemóvel + Tailscale | Opcional: vai buscar os sites que bloqueiam o GitHub. |

Os horários são os de Portugal (`geral.fuso`). Entre as 23h e as 7h (horário de silêncio)
nada é enviado: fica guardado e chega de manhã.

---

## 2. Instalação passo a passo

Se o repositório `tigreman263/agregador-noticias` já existe e funciona, salta para o passo
que te falta. Para montar de raiz noutra conta, segue todos.

### 2.1 Repositório no GitHub

1. Cria uma conta em github.com (se não tiveres).
2. Cria um repositório novo (**New repository**), por exemplo `agregador-noticias`.
   Tem de ser **público**: o GitHub Actions só é ilimitado em repositórios públicos (o
   workflow acorda de 15 em 15 minutos, o que num privado esgota os 2000 minutos grátis
   por mês), o GitHub Pages grátis exige público e o painel lê sem token.
   Os segredos ficam sempre protegidos; num repositório público, as tuas pesquisas e as
   notícias guardadas ficam visíveis.
3. Carrega todos os ficheiros deste projeto, mantendo as pastas (a lista completa está
   na [secção 9](#9-ficheiros-do-projeto)). Os indispensáveis: `agregador.py`,
   `config.yaml`, `requirements.txt`, `estado.json`, `painel/index.html`,
   `.github/workflows/agregador.yml`, `.github/ja_e_altura.py` e
   `extras/cloudflare/` (`worker.js` e `wrangler.toml`). (Noutra conta, troca no
   `Abrir Painel.url` e no `Abrir Painel.bat` o endereço do painel pelo teu.)
   No site do GitHub: **Add file → Upload files** para os ficheiros normais; para os que
   estão em pastas começadas por ponto, **Add file → Create new file**, escreve o nome
   (por exemplo `.github/workflows/agregador.yml`; as barras criam as pastas) e cola o
   conteúdo.

### 2.2 Criar o bot do Telegram

1. No Telegram, procura **@BotFather**, escreve `/newbot`, escolhe um nome e um utilizador
   (terminado em `bot`). Ele devolve o **token** (`123456:ABC…`). É secreto: não o partilhes.
2. Abre o teu bot novo, carrega em **Iniciar** e escreve `olá`.
3. No navegador, abre `https://api.telegram.org/bot<TOKEN>/getUpdates` (troca `<TOKEN>`
   pelo token). Procura `"chat":{"id":123456789` — esse número é o teu **chat id**.
   (Se aparecer só `"ok":true` e `"result":[]`, o token está certo mas o bot ainda não
   recebeu nenhuma mensagem tua: escreve-lhe outra vez e recarrega.) Depois de
   instalares o Worker (passo 2.8), basta mandar `/start` ao bot para ele te dizer o número.

### 2.3 Guardar os segredos no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository secret**.

| Nome | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | O token dado pelo @BotFather. |
| `TELEGRAM_CHAT_ID` | O teu chat id (passo 2.2). |

Ou no terminal, com o GitHub CLI (`gh`), colando o valor quando pedir:

```
gh secret set TELEGRAM_BOT_TOKEN -R tigreman263/agregador-noticias
gh secret set TELEGRAM_CHAT_ID -R tigreman263/agregador-noticias
```

### 2.4 Primeiro teste

1. No repositório: **Actions → Agregador de Notícias → Run workflow**.
2. Escolhe **teste** e carrega em **Run workflow**. Deves receber no Telegram
   "✅ O agregador de notícias está ligado ao Telegram".
3. Corre de novo com **simular**: abre a execução e vê no registo o que seria enviado,
   sem enviar nada.
4. A partir daqui o agregador corre sozinho, com a frequência de cada pesquisa (secção
   4). Sem o Worker do Cloudflare (passo 2.8), o GitHub salta muitas execuções.

### 2.5 Publicar o painel (GitHub Pages)

1. No repositório: **Settings → Pages**.
2. Em **Build and deployment → Source**, escolhe **Deploy from a branch**; em **Branch**,
   `main` e `/ (root)`. Guarda.
3. Ao fim de 1 a 2 minutos o painel fica em
   `https://<o-teu-utilizador>.github.io/<repositório>/painel/`.
   Neste projeto: https://tigreman263.github.io/agregador-noticias/painel/
4. No telemóvel, abre o endereço e usa **Adicionar ao ecrã principal** para o teres
   como uma app.

No computador, o atalho **`Abrir Painel.url`** (na pasta do projeto) abre o painel com
duplo clique; se não abrir, usa o **`Abrir Painel.bat`**. O endereço curto https://tigreman263.github.io/agregador-noticias/ também
leva ao painel. Também podes abrir `painel/index.html` com duplo clique.

### 2.6 Token do painel (para editar)

Sem token, o painel só mostra. Para criar pesquisas, vigiar páginas, decidir fontes,
descartar notícias e correr ações, precisa de um token do GitHub:

1. Abre https://github.com/settings/personal-access-tokens/new.
2. **Token name**: `painel agregador`. **Expiration**: **No expiration** (recomendado:
   o token só dá acesso a este repositório e assim nunca expira).
3. **Repository access**: **Only select repositories** → escolhe `agregador-noticias`.
4. **Permissions → Repository permissions**:
   **Contents: Read and write** e **Actions: Read and write**.
5. **Generate token** e copia-o.
6. No painel, secção **Ligação**: cola o token e carrega em **Guardar e testar**.
   Deve aparecer "Ligado: podes ler e gravar".

O token fica guardado **só nesse navegador**: o painel no telemóvel e o painel no
computador precisam cada um de ter o token colado em **Ligação** (podes usar o mesmo
token nos dois, ou um para cada; se o painel disser "para correr ações, junta primeiro um
token em Ligação", é isto que falta nesse aparelho). Para passar o token para o
telemóvel, cola-o nas **Mensagens guardadas** do Telegram, copia-o de lá e apaga a
mensagem. Num aparelho partilhado, usa **Esquecer token** no fim.

Se escolheste uma data de validade em vez de **No expiration**, põe um lembrete uma
semana antes: quando o token expira, o painel passa a "só leitura". Como renovar:
[secção 12](#12-manutenção-o-que-expira-e-como-renovar).

### 2.7 (Opcional) Telemóvel para sites que bloqueiam o GitHub

Alguns sites (como o da Câmara da Sertã) recusam ligações vindas dos servidores do
GitHub, que estão nos EUA. O agregador marca-os sozinho como bloqueados e, com isto
configurado, vai buscá-los antes de cada verificação pela internet do teu telemóvel
Android, que tem endereço português. Só esses sites passam pelo telemóvel; tudo o resto
continua direto. Usa o **Tailscale** (gratuito para uso pessoal). Só funciona com
**Android** (o iPhone não deixa o Tailscale servir de saída).

**No telemóvel**

1. Instala o **Tailscale** (Play Store) e entra com uma conta (Google, GitHub…).
2. Na app, abre o menu e liga **Run as exit node**.
3. Nas definições do Android: **Apps → Tailscale → Bateria → Sem restrições**, para o
   sistema não a desligar.

**Na consola do Tailscale** (https://login.tailscale.com/admin, no computador)

4. **Machines** → no telemóvel, menu **…**:
   - **Edit route settings** → marca **Use as exit node**;
   - **Disable key expiry** (senão terias de voltar a entrar de 180 em 180 dias).
5. **Access controls**: junta esta linha dentro das chavetas principais da política e
   guarda:
   ```
   "tagOwners": {"tag:ci": ["autogroup:admin"]},
   ```
   Se a política já tiver uma secção `"tagOwners"`, não a repitas: junta só
   `"tag:ci": ["autogroup:admin"]` dentro dela.
6. **Settings → OAuth clients → Generate OAuth client**: marca **Auth Keys → Write**,
   escolhe a etiqueta **tag:ci** e gera. Copia o **Client ID** e o **Client secret**.

**No GitHub**

7. Guarda os dois valores como segredos:

   | Nome | Valor |
   |---|---|
   | `TS_OAUTH_CLIENT_ID` | Client ID do Tailscale |
   | `TS_OAUTH_SECRET` | Client secret do Tailscale |

   ```
   gh secret set TS_OAUTH_CLIENT_ID -R tigreman263/agregador-noticias
   gh secret set TS_OAUTH_SECRET -R tigreman263/agregador-noticias
   ```
8. No painel, carrega em **Verificar agora** e, quando acabar, outra vez. A primeira
   verificação marca o site como bloqueado; a seguinte já o vai buscar pelo telemóvel.
   Em **Atividade → O que a app fez**, a fonte aparece com a etiqueta **pelo telemóvel**.
   (O **Simular** não serve para isto: não grava nada, por isso não marca o site nem
   mostra a etiqueta.)

Sem estes segredos, ou com o telemóvel sem rede, os passos do telemóvel não fazem nada e o
resto corre igual (os sites bloqueados ficam de fora dessa vez). O consumo é mínimo:
alguns megabytes de dados por dia.

### 2.8 Cloudflare: despertador e botões do Telegram

O agendador do GitHub salta muitas execuções (em vez de 15 em 15 minutos, corre só algumas
vezes por dia). Um **Worker do Cloudflare** (gratuito, sempre ligado, não precisa do PC nem
do telemóvel) faz duas coisas:

- de 15 em 15 minutos pede ao GitHub uma verificação; o agregador só verifica a sério
  quando chega a altura de alguma pesquisa ou página vigiada (cada uma tem a sua
  frequência);
- recebe os toques nos **botões** das mensagens (Confiável / Neutra / Bloquear) e grava a
  decisão no `config.yaml`, e responde aos comandos `/resumo`, `/verificar`, `/estado`, `/fontes`, `/painel` e
  `/ajuda`.

O código é um só ficheiro, `extras/cloudflare/worker.js`, sem dependências.

**1. Token do GitHub para o Worker**

1. Abre https://github.com/settings/personal-access-tokens/new.
2. **Token name**: `worker agregador`. **Expiration**: **No expiration** (recomendado;
   com uma data, o despertador e o bot param quando ela chegar).
3. **Repository access**: **Only select repositories** → `agregador-noticias`.
4. **Permissions → Repository permissions**: **Contents: Read and write** e
   **Actions: Read and write**.
5. **Generate token** e copia-o (começa por `github_pat_`).

**2. Criar o Worker ligado ao GitHub** (recomendado: atualiza-se sozinho quando o
`worker.js` muda)

1. Cria uma conta gratuita em https://dash.cloudflare.com (não pede cartão).
2. **Computação → Workers e Pages → Criar → Importar um repositório** (Import a
   repository). Liga a tua conta do GitHub e escolhe `agregador-noticias`.
3. Em **Configure seu aplicativo**:
   - **Nome do projeto**: `agregador-noticias`;
   - **Comando da build**: vazio;
   - **Comando de implantação**: `cd extras/cloudflare && npx wrangler deploy`
     (o Worker está nessa pasta; sem o `cd`, a implantação falha).

   Carrega em **Implantar** e espera pelo ✅. O Cron de 15 em 15 minutos vem no
   `wrangler.toml`, não é preciso criá-lo.
4. No Worker → **Configurações → Variáveis e segredos → Adicionar**. Junta as três de uma
   vez (botão **+ Adicionar** para mais linhas) e **marca a caixa "Segredo" em cada uma**:
   uma variável sem essa caixa é apagada sempre que o Worker se publica de novo a partir
   do GitHub.

   | Nome | Valor |
   |---|---|
   | `GITHUB_TOKEN` | O token do passo 1. |
   | `TELEGRAM_BOT_TOKEN` | O token do bot (o mesmo do GitHub). |
   | `TELEGRAM_CHAT_ID` | O teu chat id (o mesmo do GitHub). |

5. **Configurações → Domínios e rotas → URL do Worker**: liga o interruptor da linha
   **Produção** (`agregador-noticias.<a-tua-conta>.workers.dev`). Se ficar desligado, o
   painel do Worker diz "Nenhum URL habilitado" e o bot não consegue falar com ele.
6. **Configurações → Compilação → Caminhos de observação de build → Incluir**:
   `extras/cloudflare/*`. Assim o Worker só se publica de novo quando o código dele muda,
   e não sempre que o agregador grava o `estado.json`.
7. Abre no navegador o endereço do Worker
   (`https://agregador-noticias.<a-tua-conta>.workers.dev`). Isto liga o bot ao Worker e
   deve mostrar três ✅ (Telegram, chat id e GitHub). Guarda o endereço no painel, em
   **Ligação → Telegram e Cloudflare**.
8. No Telegram, escreve `/estado` ao bot: deve responder com a última verificação. No
   painel, **Início → Frequência** passa a mostrar "despertador ligado".

**Alternativa: colar o código à mão** (não se atualiza sozinho)

**Workers e Pages → Criar → Create Worker** (modelo "Hello World"), nome
`agregador-noticias`, **Deploy** → **Editar código**: cola todo o
`extras/cloudflare/worker.js` e **Deploy**. Depois, os passos 4, 5 e 7 de cima, e ainda
**Configurações → Trigger events → Adicionar → Cron Triggers**: `*/15 * * * *`. Sempre que
o `worker.js` mudar no repositório, tens de o colar de novo.

Quem preferir o terminal pode publicar com o Wrangler, dentro de `extras/cloudflare`:
`npx wrangler deploy` e `npx wrangler secret put GITHUB_TOKEN` (e os outros dois).

O agendador do próprio GitHub continua ligado como reserva; os dois respeitam o mesmo
intervalo, sem verificações nem mensagens repetidas. Se o pedido ao GitHub falhar (token
expirado), o bot avisa-te uma vez por dia, por volta das 9h. O bot só obedece ao teu chat
id; a outras pessoas responde apenas com o chat id delas.

---

## 3. Usar o painel

| Secção | O que tem |
|---|---|
| **Início** | Última verificação (correu bem / falhou, com link para o registo), alertas de hoje, notícias à espera, fontes por decidir. **Frequência**: a frequência de cada pesquisa ativa e se o despertador do Cloudflare está ligado. Botões para correr já: **Verificar agora**, **Simular** (mostra no registo o que seria enviado, sem enviar), **Testar Telegram** e **Procurar fontes novas**. |
| **Pesquisas** | Criar, editar, pausar e apagar pesquisas, com o botão **Experimentar** (secção 4). Mostra o resultado da última verificação de cada uma. |
| **Páginas** | Páginas vigiadas: juntar (**+ Vigiar**), editar, pausar e apagar. Mostra a última verificação, o número de linhas de texto, a última mudança e o que mudou (secção 5A). |
| **Atividade** | Execuções no GitHub, o que a app fez em cada uma (notícias lidas, novas relevantes, alertas, fontes com falha, fontes trazidas pelo telemóvel), o que foi enviado para o Telegram, e o que está à espera (alertas adiados e resumo). |
| **Fontes** | Fontes sugeridas pela app (Confiável / Neutra / Bloquear; também se decide nos botões do Telegram), listas de confiáveis, neutras e bloqueadas, e feeds e sites gerais. |
| **Ligação** | Repositório e token do GitHub, com as instruções para o criar. **Telegram e Cloudflare**: endereço do Worker (botão **Verificar o Worker**), estado do despertador e onde estão os segredos. |
| **Ajuda** | Este documento. |

Notas:

- Tudo o que gravas no painel fica no `config.yaml` do GitHub e vale a partir da
  verificação seguinte. Para ver o efeito logo, usa **Simular**.
- Ao gravar, o painel só reescreve a secção que mudaste; os comentários do resto do
  `config.yaml` mantêm-se.
- **Descartar** (em Atividade): tira uma notícia dos alertas adiados ou do resumo;
  **Descartar todos** (aparece quando há mais do que uma) tira a lista inteira. O painel grava isso em `painel.json` e o agregador tira-as na verificação
  seguinte, sem as enviar.
- **Limpar** (em Atividade → O que a app fez): esconde o que já lá estava, para veres só
  o que acontecer a seguir. Nada é apagado: **Mostrar tudo** volta a mostrar o histórico.
  Com o token, a limpeza fica gravada em `painel.json` e vale em todos os aparelhos.
- "**novas relevantes**" conta só as notícias relevantes que ainda não tinham sido
  vistas. "0 novas relevantes" não é erro: quer dizer que não apareceu nada de novo.
- O painel atualiza sozinho de 5 em 5 minutos; usa **Atualizar** para ver já.
- **Frequência**: escolhe-se em cada pesquisa (pergunta 4): ⚡ urgente (de 15 em 15 min,
  mensagem logo), 🕐 de hora a hora (mensagem logo) ou 📰 uma vez por dia (tudo no resumo
  diário). O Worker do Cloudflare acorda o agregador de 15 em 15 minutos; se nenhuma
  pesquisa estiver na altura, ele termina logo, sem fazer nada (no separador Actions do
  GitHub vês muitas execuções curtas, é normal). Os botões de **Correr agora** verificam
  todas as pesquisas logo.

---

## 4. Criar e afinar pesquisas

No painel, cada pesquisa tem um nome e responde a **4 perguntas**:

| Pergunta | Exemplo | O que faz |
|---|---|---|
| 1. De que sítio tem de falar? | `Sertã, sertanense` | A notícia **tem** de ter uma destas formas. Vazio = qualquer sítio. |
| 2. E de que assuntos? (um por linha) | `apoio, subsídio, candidatura`<br>`agricultura, agrícola`<br>`floresta, florestal` | E tem de ter **pelo menos um** assunto. Na mesma linha, palavras com o mesmo sentido. |
| 3. O que nunca te interessa? | `futebol, acidente` | Se tiver uma, é deitada fora. |
| 4. Quando avisar? | ⚡ urgente / 🕐 de hora a hora / 📰 uma vez por dia | Urgente: verifica de 15 em 15 min e manda mensagem logo. De hora a hora: verifica de hora a hora e manda mensagem logo. Uma vez por dia: verifica de hora a hora (para não perder nada) e junta tudo no resumo diário. |

**Regra:** passa se tiver o **sítio E um assunto**, e nenhuma palavra a excluir. Não há
pontos nem notas para escolher: a pergunta 4 decide se chega como mensagem ou no resumo.
Sem assuntos, basta falar do sítio. A procura no Google Notícias é feita pelo sítio (ou,
sem sítio, pelos assuntos). No painel separas as variantes por vírgulas; no
`config.yaml` ficam separadas por `/`.

**Experimentar:** antes de gravar, o botão **Experimentar** corre a pesquisa no GitHub
(1 a 3 minutos, sem enviar nada) e mostra as notícias das últimas 48 h que passariam e as
que foram cortadas — "não falam do sítio", "falam do sítio mas não de um assunto" (se
alguma te interessava, falta-lhe um assunto), "palavra a excluir" e "antigas".

**Fontes só desta pesquisa** (opcional, em **Editar → Fontes só desta pesquisa**): feeds e
sites sem RSS que só esta pesquisa lê (secções 5.3 e 5.4). Com `| local`, a fonte só
publica deste sítio (ex.: o site da Câmara) e basta-lhe ter um assunto.

No `config.yaml` fica assim (variantes separadas por `/`):

```yaml
  - nome: "Sertã"
    sitio: "Sertã / sertanense"
    assuntos:
      - "apoio / subsídio / candidatura"
      - "floresta / florestal"
    excluir: []
```

### Como as palavras são comparadas

- A comparação ignora maiúsculas e acentos ("subsídio" = "subsidio").
- **Singular e plural são a mesma palavra**, nos dois sentidos: "candidaturas" apanha
  "candidatura", "agricultores" apanha "agricultor", "ações" apanha "ação". Palavras
  maiores apanham também as que começam por elas ("apoio" apanha "apoios").
- Palavras de até 3 letras (ex.: "PRR") só contam inteiras.
- Várias palavras juntas contam como **expressão inteira**: `fundo ambiental` não apanha
  "fundo" nem "ambiental" soltos.
- **Variantes** (separadas por vírgulas no painel, por `/` no `config.yaml`): basta
  aparecer uma. No sítio, basta uma forma; num assunto, basta uma palavra da linha; nas
  palavras a excluir, qualquer uma descarta (aqui só à palavra inteira).
- Procura-se no título e no resumo da notícia.
- Notícias com mais de 48 horas (`geral.idade_max_horas`) e de fontes bloqueadas são
  ignoradas.

### Por que ordem chegam

Não há notas para escolher, mas a app ordena as notícias por dentro: as que têm um assunto
no **título**, mais **assuntos**, saíram em **várias fontes**, têm **menos de 1 hora** ou
vêm de uma **fonte confiável** ficam à frente. Isto decide:

- qual versão de uma notícia repetida chega (a melhor fonte);
- quais vão primeiro quando há mais de 5 alertas numa verificação (o resto vai para o
  resumo);
- a ordem das notícias no resumo diário.

As regras desta ordenação estão em `pesos` no `config.yaml` (secção 7); não precisas de
mexer nelas.

### Dicas

- **Evita assuntos genéricos sozinhos.** "apoio" apanha "apoio político" ou "apoio na
  Argentina"; o sítio (pergunta 1) já ajuda a cortar, e a pergunta 3 corta o resto.
- **Põe na mesma linha** as palavras com o mesmo sentido (`agricultura, agrícola,
  agricultor`); linhas diferentes são assuntos diferentes.
- **Não precisas de repetir** a mesma palavra com e sem acento, nem em singular e plural.
- **Notícias brasileiras**: o Google Notícias mistura-as. Bloqueia `br` nas fontes
  (secção 5.2).
- **Para ver o efeito** de uma mudança, carrega em **Experimentar** dentro da pesquisa.
- Quando apagas uma pesquisa, o que ela deixou no estado (notícias à espera, sites
  registados para sugestões) é esquecido sozinho.

---

## 5. Fontes de notícias

### 5.1 Google Notícias

Cada pesquisa procura no Google Notícias pelo seu sítio (ou, sem sítio, pelos assuntos),
em português de Portugal (`geral.google_news`). Não tens de fazer nada.

### 5.2 Confiáveis, neutras e bloqueadas

Listas de domínios (sem `www` nem `https://`), no painel em **Fontes**:

- **Confiáveis**: ficam à frente das outras (secção 4, "Por que ordem chegam") e o alerta
  diz "(confiável)".
- **Neutras**: contam como as outras; só deixam de ser sugeridas.
- **Bloqueadas**: as notícias delas são descartadas (também as que já estavam à espera).

Um domínio apanha também os subdomínios e o que acaba nele: `sapo.pt` inclui
`jornaldeabrantes.sapo.pt`; **`br` bloqueia todos os sites `.br`** (Brasil).

### 5.3 Feeds RSS

- **Gerais** (`fontes.feeds`, painel **Fontes**): lidos em todas as pesquisas.
- **Só de uma pesquisa** (`feeds_extra`, painel **Pesquisas → Editar → Fontes só desta
  pesquisa**): um por linha, `Nome | https://endereço-do-feed`.
- **`local`**: junta `| local` à linha (ou `local: true` no `config.yaml`) quando a fonte só
  publica sobre um lugar, como a de uma câmara municipal. As notícias dela não precisam de
  falar do sítio (nem todas dizem o nome do lugar), basta-lhes um assunto. Usa `local` só nas
  fontes de uma pesquisa, nunca nas gerais.
- Se o mesmo endereço estiver nas gerais e nas de uma pesquisa, é lido uma só vez, com as
  opções da pesquisa (por exemplo o `local`). Vale também para os sites sem RSS.

### 5.4 Sites sem RSS

Para sites sem feed (câmaras, jornais regionais), junta a página com a **lista** de
notícias em **Sites sem RSS** (`paginas` / `paginas_extra`), com nome e endereço.

- Sem mais nada, a app deteta as notícias sozinha: fica com os links que partilham o
  mesmo tipo de cartão (ignora menus e rodapés), prefere o título ao texto das imagens e
  procura a data no cartão.
- Se a página anunciar um feed RSS escondido, a app usa-o sozinha (mais fiável), a não
  ser que tenhas indicado seletores CSS.
- Notícias sem data ficam com a data do dia em que a app as viu pela primeira vez. Na
  primeira leitura de uma página, o que já lá estava conta como antigo (não envia o
  arquivo todo).
- Se a deteção não for boa, indica seletores CSS no `config.yaml`: `item` (cada notícia),
  e dentro dele `titulo`, `resumo` e `data`. Outras opções: `max` (quantas notícias ler,
  por omissão 30) e `usar_feed: false` (não usar o feed escondido).

Para testar um site no computador (secção 8):

```
python agregador.py --testar-pagina https://cm-serta.pt/comunicacao/noticias
python agregador.py --testar-pagina URL --item "div.noticia" --titulo "h2 a" --data "time"
python agregador.py --testar-pagina URL --sem-feed
```

Se der 0 notícias, o teste diz o que tentar. Não dá para ler páginas que só mostram as
notícias com JavaScript, nem sites com o certificado de segurança inválido.

### 5.5 Encontrar feeds RSS escondidos

Muitos sites têm feed mas não o mostram. No computador:

```
python agregador.py --procurar-feeds "Sertã"
```

Se o texto for o nome de uma pesquisa, usa o sítio e os assuntos dela. A app vê
que sites publicaram sobre o tema no último mês, procura o feed de cada um (os que a
página anuncia e os endereços habituais do WordPress, Joomla, Blogger…) e mostra as
linhas prontas a colar. Feeds de sites nacionais (SAPO, Observador…) trazem notícias de
tudo; para temas locais prefere os regionais.

### 5.6 Descoberta automática de fontes

Uma vez por dia (a partir das 9h), a app volta a pesquisar cada tema, vê que sites
publicam notícias relevantes, escolhe os que tiveram pelo menos 2 (até 5 por dia e nunca
mais de 10 por decidir), procura o feed de cada um e envia-te cada site numa mensagem do
Telegram com três botões: **Confiável** (se tiver feed, é juntado aos feeds gerais),
**Neutra** ou **Bloquear**. Também podes decidir no painel, em **Fontes → Sugeridas pela
app**, ou pedir a lista outra vez com `/fontes`. Sem decisão em 14 dias, a sugestão
é esquecida. Para procurar já: **Procurar fontes novas** no Início.

### 5.7 Sites que bloqueiam o GitHub

Não é o GitHub que bloqueia: são alguns sites que recusam ligações vindas dos centros de
dados (os computadores do GitHub ficam nos Estados Unidos). O telemóvel tem um endereço
português normal, por isso entra.

- Quando um site **recusa** a ligação ("Connection reset", "não consegui ligar ao site",
  erro 403/429/451), o agregador marca-o como bloqueado e, com o telemóvel configurado
  (passo 2.7), passa a ser trazido por ele.
- Quando um site só **demora demasiado**, uma vez não conta: só fica bloqueado se demorar
  em **3 verificações seguidas**.
- **Uma vez por dia**, cada site bloqueado é lido diretamente pelo GitHub (sem o telemóvel)
  para ver se ainda é preciso. Se entrar, sai da lista; se não, volta ao telemóvel na
  verificação seguinte. Também sai da lista se, com o telemóvel desligado, o GitHub o
  conseguir ler.
- Um site bloqueado que não volte a ser usado é esquecido ao fim de 30 dias.
- Para obrigar um site a ir sempre pelo telemóvel (sem o teste diário), junta-lhe
  `telemovel: true` no `config.yaml`.

**Três vias, por esta ordem.** Cada site (fonte de notícias ou página vigiada) é lido:

1. **diretamente pelo GitHub**;
2. se recusar, **pelo telemóvel** (na verificação seguinte, com o passo 2.7 feito);
3. se mesmo assim não der (telemóvel desligado, ou sites com proteção anti-robôs que
   recusam qualquer programa, como o contaspoupanca.pt), **pelo Google Notícias**: a app
   procura `site:dominio` e usa as notícias desse site que o Google conhece.

Pelo Google Notícias, uma página vigiada só avisa de **notícias novas desse site** (não de
outras mudanças no texto da página), e o Google pode demorar um pouco a mostrá-las. Na
primeira vez que uma página passa a ser lida assim, recebes um aviso no Telegram; no painel
fica com a etiqueta **pelo Google Notícias**. Quando o site volta a poder ser lido, a app
regressa à página sozinha. Não precisas de fazer nada quando juntas um site novo.

---

## 5A. Vigiar páginas (avisos de mudanças)

Além das notícias, a app pode vigiar páginas da internet e avisar-te no Telegram quando
o texto delas muda: a lista de editais ou concursos de uma câmara, uma página de apoios,
um regulamento, preços, etc.

**Como juntar uma página:** no painel, separador **Páginas** → **+ Vigiar** → endereço,
nome, de quanto em quanto tempo (15 min, de hora a hora ou 1 vez por dia) → Guardar.
A secção fica gravada em `vigiar:` no `config.yaml`.

**O que acontece:**
- Na 1.ª verificação a app guarda o texto da página e manda-te **👀 Comecei a vigiar**.
- Daí em diante compara o texto. Se mudou, manda **🔎 Mudou: nome da página**, com as
  linhas novas (➕) e as que saíram (➖), até 8 de cada, e um botão **🌐 Abrir a página**.
- **Não contam como mudança:** datas, horas, "há 5 minutos", e linhas que só mudaram de
  sítio. Também não conta o código da página (scripts, estilos) — só o texto visível.
- Se a página não puder ser lida 3 vezes seguidas, manda **⚠️ Não consigo ler** (uma vez).
  Se o site bloquear o GitHub, passa a ser trazido pelo telemóvel (passo 2.7), como os
  sites de notícias.
- No horário de silêncio não verifica; o que mudar durante a noite é avisado de manhã.
- Pedir já: **Verificar agora** no Início, ou `/verificar` no Telegram, verifica todas.

**Avisos a mais?** Há páginas com partes que mudam sempre (destaques, "mais lidas",
publicidade). Em **Editar → 4. Só uma parte da página**, indica o seletor CSS da parte que
interessa (por exemplo `#editais` ou `.lista-noticias`). Para ver o texto que a app lê:

```
python agregador.py --testar-vigia "https://www.exemplo.pt/editais"
python agregador.py --testar-vigia "https://www.exemplo.pt/editais" --parte "#editais"
```

Mudar a parte faz a app guardar uma referência nova (sem aviso de mudança).

**Limite:** páginas que só mostram o conteúdo com JavaScript não podem ser lidas (o painel
mostra o erro); procura outra página do mesmo site.

---

## 6. O que recebes no Telegram

- **Alertas** (pesquisas urgentes e de hora a hora): uma mensagem por notícia, até 5 por
  verificação (`max_alertas_por_execucao`); o excesso vai para o resumo. Cada alerta traz o
  título (com o link), a fonte (e se é confiável ou nova), a pesquisa, os assuntos
  encontrados, há quanto tempo saiu e, se saiu em vários sites, quantos. Os botões
  **⭐ Confiável** e **🚫 Bloquear fonte** decidem logo a fonte dessa notícia (numa fonte
  já confiável, só aparece Bloquear).
- **Resumo diário** (pesquisas de uma vez por dia, e o excesso dos alertas): uma vez por
  dia, na primeira verificação a partir das 8h (`hora_resumo`). Traz todas as notícias à
  espera, pela ordem da secção 4; se forem muitas, vêm divididas por várias mensagens.
  Notícias à espera há mais de 48 horas saem da fila.
- **Fontes novas sugeridas**: uma vez por dia, com botões (secção 5.6).
- **Páginas vigiadas**: 👀 ao começar, 🔎 quando o texto muda, ⚠️ se não a consegue ler
  (secção 5A).
- **Horário de silêncio** (23h–7h): nada é enviado; os alertas ficam adiados (até 50; o
  excesso vai para o resumo) e saem depois.
- **Se o envio falhar** (Telegram em baixo, token errado): os alertas ficam adiados e saem
  na verificação seguinte, sem se perderem nem se repetirem. O resumo também volta a
  tentar; se ocupar duas mensagens e só a segunda falhar, a primeira pode chegar repetida.

Comandos do bot (precisam do Worker, passo 2.8):

| Comando | O que faz |
|---|---|
| `/resumo` (botão 📰 Resumo) | Mostra as notícias à espera do próximo resumo diário; se não houver, o último resumo enviado. |
| `/verificar` | Procura notícias já (os alertas chegam em 2 a 3 minutos). |
| `/estado` | Última verificação, notícias à espera e fontes por decidir. |
| `/fontes` | Volta a mostrar as fontes sugeridas por decidir, com botões. |
| `/painel` (botão 🖥 Painel) | Responde com um botão que abre o painel de gestão no navegador. |
| `/ajuda` | Lista os comandos. |

Depois de mandares `/start`, aparece por baixo da conversa um **teclado fixo** com os botões
📰 Resumo, 🔄 Verificar, 📊 Estado, 🗂 Fontes e 🖥 Painel (fazem o mesmo que os comandos).

Ao tocar num botão, a decisão fica gravada no `config.yaml` (commit "telegram: …") e vale
a partir da verificação seguinte. Para desfazer, usa o painel (**Fontes**).

---

## 7. Referência do config.yaml

O painel edita as secções `pesquisas`, `fontes` e `vigiar`. As outras editas no GitHub (ícone do
lápis no ficheiro).

| Chave | Por omissão | Significado |
|---|---|---|
| `geral.fuso` | `Europe/Lisbon` | Fuso horário. |
| `geral.idade_max_horas` | 48 | Ignora notícias mais antigas. |
| `geral.max_alertas_por_execucao` | 5 | Alertas por verificação; o excesso vai para o resumo. |
| `geral.silencio` | `{inicio: 23, fim: 7}` | Horas sem envios. |
| `geral.hora_resumo` | 8 | Hora a partir da qual sai o resumo. |
| `geral.google_news` | `pt-PT`, `PT` | Língua e país do Google Notícias. |
| `pesos.*` | — | Só para a ordenação interna (secção 4, "Por que ordem chegam"); não decidem o que chega. |
| `pesos.pontos` | alta 10, média 4, baixa 1 | Por palavra encontrada (no título, o dobro). Os assuntos contam como "alta" (média e baixa ficam por usar). |
| `pesos.fonte_confiavel` | 1.5 | Multiplicador das confiáveis. |
| `pesos.fonte_desconhecida` | 1.0 | Multiplicador das outras. |
| `pesos.bonus_fonte_extra` / `bonus_fonte_extra_max` | 5 / 15 | Por cada fonte extra com a mesma notícia. |
| `pesos.bonus_ultima_hora` | 3 | Para notícias com menos de 1 hora. |
| `fontes.confiaveis` / `neutras` / `bloqueadas` | — | Listas de domínios (secção 5.2). |
| `fontes.feeds` | — | Feeds gerais: `{nome, url, local?, telemovel?}`. |
| `fontes.paginas` | — | Sites sem RSS gerais: `{nome, url, item?, titulo?, resumo?, data?, max?, usar_feed?, local?, telemovel?}`. |
| `descoberta.ativa` | true | Liga a descoberta diária. |
| `descoberta.hora` | 9 | A partir desta hora. |
| `descoberta.max_sugestoes_por_dia` | 5 | Sugestões por dia. |
| `descoberta.max_pendentes` | 10 | Não sugere mais se tiveres estas por decidir. |
| `descoberta.min_noticias` | 2 | Notícias relevantes mínimas para sugerir um site. |
| `descoberta.procurar_feeds` | true | Procura o feed dos sites sugeridos. |
| `pesquisas[]` | — | `nome`, `ativa`, `sitio`, `assuntos`, `excluir`, `frequencia` (`urgente`/`hora`/`diario`), `feeds_extra`, `paginas_extra` (secção 4). |
| `vigiar[]` | `[]` | Páginas vigiadas: `nome`, `url`, `parte` (seletor CSS opcional), `frequencia` (`urgente` 15 min / `hora` / `diario` 1 vez por dia), `ativa`, `telemovel?` (secção 5A). |

---

## 8. Usar no computador (opcional)

Não é preciso para o dia a dia; serve para testar sites e procurar feeds.

1. Instala o Python 3.12 (python.org) e, numa pasta com os ficheiros do projeto:
   ```
   pip install -r requirements.txt
   ```
2. Comandos:

| Comando | O que faz |
|---|---|
| `python agregador.py --simular` | Mostra o que seria enviado, sem enviar nem gravar. |
| `python agregador.py` | Execução normal (envia; precisa dos segredos como variáveis de ambiente). |
| `python agregador.py --teste` | Envia uma mensagem de teste. |
| `python agregador.py --fontes` | Execução normal + procura de fontes novas já. |
| `python agregador.py --testar-pagina URL` | Mostra o que a app lê de um site (opções `--item`, `--titulo`, `--resumo`, `--data`, `--sem-feed`). |
| `python agregador.py --procurar-feeds "TEXTO"` | Procura feeds RSS escondidos dos sites que publicam sobre um tema. |
| `python agregador.py --testar-vigia URL` | Mostra o texto que a vigilância de páginas compara (opção `--parte CSS`). |

Há mais dois comandos que não são para usar à mão: `--experimentar` (o botão
**Experimentar** do painel) e `--buscar-pelo-telemovel` (o passo do telemóvel no GitHub).

Para enviar a partir do computador, define antes as variáveis (PowerShell):

```
$env:TELEGRAM_BOT_TOKEN="123456:ABC..."; $env:TELEGRAM_CHAT_ID="123456789"
```

Atenção: o `config.yaml` e o `estado.json` verdadeiros estão no GitHub (o painel grava
lá). Antes de usar o computador, descarrega a versão atual do repositório.

---

## 9. Ficheiros do projeto

| Ficheiro | O que é |
|---|---|
| `agregador.py` | Todo o programa: recolha, leitor de páginas, filtro e ordenação, Telegram, páginas vigiadas, descoberta, telemóvel. |
| `config.yaml` | Pesquisas, páginas vigiadas, fontes e regras. |
| `estado.json` | Memória do agregador, gravada pelo GitHub. Não editar. |
| `painel.json` | Notícias descartadas e limpeza da atividade, gravadas pelo painel. |
| `experimentar.json` | Resultado do último **Experimentar** do painel (gravado pelo GitHub). |
| `requirements.txt` | Bibliotecas Python (requests, PyYAML, defusedxml, beautifulsoup4). |
| `.github/workflows/agregador.yml` | Acorda de 15 em 15 minutos, verifica quando alguma pesquisa ou página está na altura (`frequencia`), e ações manuais (normal, teste, simular, descobrir-fontes, agendada, experimentar). |
| `.github/ja_e_altura.py` | Decide, em cada execução automática, se já é altura (15 min se houver pesquisas ou páginas urgentes, senão 60). |
| `painel/index.html` | O painel. |
| `Abrir Painel.url` / `Abrir Painel.bat` | Abrem o painel no navegador (duplo clique no Windows). |
| `.gitattributes` | Mantém o formato de linhas do Windows nos dois atalhos. |
| `index.html` | Encaminha o endereço curto do GitHub Pages para o painel. |
| `.nojekyll` | Faz o GitHub Pages servir os ficheiros tal como estão. |
| `extras/cloudflare/worker.js` | Worker do Cloudflare: despertador e bot do Telegram (passo 2.8). |
| `extras/cloudflare/wrangler.toml` | Configuração do Worker (nome, Cron de 15 em 15 minutos, endereço workers.dev), usada quando o Cloudflare o publica a partir do GitHub. |
| `README.md` | Este documento (também em **Ajuda** no painel). |
| `CONTEXTO.md` | Decisões técnicas, para quem continuar o desenvolvimento. |
| `.claude/` | Agentes e configuração do Claude Code usados no desenvolvimento. |

---

## 10. Resolução de problemas

**Não recebo nada no Telegram**
1. No painel, **Início → Última verificação**: se falhou, abre **ver registo**.
2. Carrega em **Testar Telegram**. Se falhar, o registo diz porquê: "Unauthorized" = o
   `TELEGRAM_BOT_TOKEN` está errado; "chat not found" = o `TELEGRAM_CHAT_ID` está errado ou
   ainda não carregaste em **Iniciar** no bot.
3. Pode simplesmente não haver notícias novas que falem do sítio e de um assunto: vê
   **Atividade**, ou carrega em **Experimentar** na pesquisa para veres o que foi cortado.

**Os botões não fazem nada / o bot não responde aos comandos**
Abre de novo o endereço do Worker (`…workers.dev`, passo 2.8) e vê qual dos três
pontos tem ❌. No Cloudflare, **Workers → agregador-noticias → Logs** mostra os erros. Se o
bot diz "Não consegui gravar … permissão", o `GITHUB_TOKEN` do Worker precisa de
**Contents: Read and write**.

**O agregador não corre de X em X tempo**
O agendador do GitHub salta muitas execuções (costuma correr só de 4 em 4 ou de 6 em 6
horas); não é do agregador. Configura o Worker do Cloudflare (passo 2.8). Em
**Atividade → Execuções no GitHub** vês as automáticas ("automática (Cloudflare)"); se não
aparecerem, confirma o Cron Trigger e o `GITHUB_TOKEN` do Worker. Para verificar já:
**Verificar agora** no painel, ou `/verificar` no Telegram.

**"Fonte com falha … Connection reset by peer"**
O site recusa os servidores do GitHub. Ver secção 5.7 e passo 2.7.

**O Worker diz "Nenhum URL habilitado" ou o endereço `…workers.dev` não abre**
No Cloudflare, **Configurações → Domínios e rotas → URL do Worker**: liga o interruptor
da linha **Produção** e espera um minuto.

**A implantação do Worker falha no passo "Deploying"**
O comando de implantação tem de entrar na pasta do Worker:
`cd extras/cloudflare && npx wrangler deploy` (**Configurações → Compilação**). Depois,
**Implantações → Tentar compilar novamente**.

**Um segredo do Worker desapareceu**
Foi criado sem a caixa **Segredo** marcada, e o Worker publicou-se de novo a partir do
GitHub. Cria-o outra vez, com a caixa marcada.

**Um token expirou**
Segue a [secção 12](#12-manutenção-o-que-expira-e-como-renovar). Sinais: o bot avisa às
9h que o despertador falhou (token do Worker), o painel diz que o token não é válido ou
fica em "só leitura" (token do painel).

**As notícias da Câmara deixaram de chegar / o registo diz "telemóvel DESLIGADO" ou "NÃO é saída"**
No registo da execução, no passo **Buscar pelo telemóvel os sites bloqueados**, aparece o
estado do telemóvel:
- **DESLIGADO**: abre a app Tailscale no telemóvel e liga-a.
- **NÃO é saída**: na app, menu **⋮ → Run as exit node**. Se continuar, na consola do
  Tailscale (**Machines → telemóvel → … → Edit route settings**) marca **Use as exit node**.
- Para não voltar a acontecer: **Apps → Tailscale → Bateria → Sem restrições** no Android.

Depois, **Verificar agora** no painel: em **Atividade**, a fonte volta a aparecer com
**pelo telemóvel**.

**"0 novas relevantes"**
Não apareceu nenhuma notícia nova que falasse do sítio e de um assunto; as notícias já
vistas não contam.

**Chegam notícias fora do tema**
O alerta diz que pesquisa a trouxe e que assuntos encontrou. Afina essa pesquisa
(secção 4): troca um assunto genérico por palavras mais específicas, junta palavras a
excluir, ou bloqueia a fonte (botão **🚫 Bloquear fonte** no próprio alerta). Usa
**Experimentar** para confirmar. As que já estão à espera podes **Descartar** no painel.

**O painel diz "Só leitura"**
Falta o token (passo 2.6). Se diz que o token não é válido ou não tem permissão, cria
outro com **Contents** e **Actions** em **Read and write**.

**O painel diz que o GitHub limitou os pedidos**
Sem token, o GitHub só deixa 60 pedidos por hora. Junta o token, ou espera uma hora.

**Um site sem RSS dá 0 notícias**
Corre `--testar-pagina` (secção 5.4): confirma que é a página com a lista de notícias;
se o site usa JavaScript ou tem o certificado inválido, procura um feed ou retira-o.

**Recebo avisos de mudança a mais numa página vigiada**
A página tem partes que mudam sempre. Indica só a parte que interessa (secção 5A,
"Avisos a mais?").

**Mudei algo e o painel não mostra**
O GitHub Pages demora 1 a 2 minutos a publicar mudanças ao painel; carrega em
**Atualizar** ou recarrega a página.

---

## 11. Limites

- Fontes: Google Notícias, feeds RSS e páginas de notícias. X, Instagram e Facebook não
  estão incluídos (acesso restrito ou pago).
- O plano gratuito do Cloudflare chega com folga (100 000 pedidos por dia; o Worker usa
  cerca de 100). A recolha continua no GitHub, porque o Worker gratuito não tem tempo de
  processamento para ler e analisar dezenas de sites, nem pode usar o telemóvel.
- Sites que bloqueiam o GitHub só são lidos com o telemóvel Android configurado e com rede.
- Páginas que só mostram notícias com JavaScript, ou com certificado inválido, não são lidas.
- Sem o Worker do Cloudflare (passo 2.8), o GitHub corre só algumas vezes por dia e os
  botões do Telegram não fazem nada.

---

## 12. Manutenção: o que expira e como renovar

Quase tudo funciona sem prazo. **Só os tokens do GitHub podem expirar**, e só se lhes
deres uma data de validade.

**Situação atual (2026-11-01):** os três tokens (`worker agregador`, `painel telemovel` e
`Agregador de Noticias`, o do painel no computador) estão **sem validade** (No
expiration). Vês isto em https://github.com/settings/personal-access-tokens (aparece "This
token has no expiration date"; o aviso amarelo é só o GitHub a lembrar que é menos
seguro, o que aqui não é problema porque cada token só dá acesso a este repositório).
**Não há nada a renovar.**

Se um dia criares ou regenerares um token **com data**, anota-a e põe um lembrete uma
semana antes (o GitHub também costuma mandar um email uns dias antes). A tabela diz o que
pararia:

| O quê | Expira? | O que deixa de funcionar | Sinal |
|---|---|---|---|
| Token do GitHub do **Worker** (`GITHUB_TOKEN` no Cloudflare) | Não (sem validade); só se lhe deres uma data | O despertador (o GitHub volta a correr só algumas vezes por dia), os botões e os comandos do bot | O bot avisa às 9h; no painel, **Início → Frequência** fica a vermelho |
| Token do **painel no computador** | Não (sem validade); só se lhe deres uma data | Gravar pesquisas e fontes e correr ações no computador | O painel diz que o token não é válido ou fica em "só leitura" |
| Token do **painel no telemóvel** | Não (sem validade); só se lhe deres uma data | O mesmo, no telemóvel | O mesmo, no telemóvel |
| Token do **bot do Telegram** | Não (só se o revogares) | — | — |
| `TELEGRAM_CHAT_ID` | Não | — | — |
| Tailscale (telemóvel) | Não, se desligaste o **key expiry** (passo 2.7) | As notícias da Câmara | Registo: "telemóvel DESLIGADO" (ver secção 10) |
| Tailscale OAuth (`TS_OAUTH_*`) | Não (só se o apagares) | — | — |
| Cloudflare, GitHub Pages, Telegram | Não (gratuitos, sem prazo) | — | — |

Os alertas e o resumo **não dependem de nenhum token que expire**: mesmo com tudo
expirado, o GitHub continua a enviar (só que poucas vezes por dia).

### Renovar ou substituir um token do GitHub (5 minutos)

Serve quando um token expirou, foi apagado, ou queres trocá-lo por segurança. O mais
simples é **regenerar** o token: fica com as mesmas permissões e só muda o valor e a data.
O valor antigo deixa logo de funcionar, por isso cola o novo de seguida (passo 4).

1. Abre https://github.com/settings/personal-access-tokens (Settings → Developer
   settings → Personal access tokens → Fine-grained tokens).
2. Carrega no token (`worker agregador` ou `painel agregador`).
3. **Regenerate token** → em **Expiration** escolhe **No expiration** →
   **Regenerate token**. Copia o valor novo (`github_pat_…`): só aparece esta vez.
   (Se o token já tiver sido apagado, cria um novo como no passo 2.6, com **Contents** e
   **Actions** em **Read and write** e só o repositório `agregador-noticias`.)
4. Cola-o onde ele é usado:
   - **Token do Worker**: Cloudflare → **Workers e Pages → agregador-noticias →
     Configurações → Variáveis e segredos** → `GITHUB_TOKEN` → editar → cola →
     **Implantar**. Confirma abrindo o endereço do Worker (três ✅).
   - **Token do painel**: em cada aparelho onde usas o painel, **Ligação** → cola no campo
     do token → **Guardar e testar** ("Ligado: podes ler e gravar").
5. Se escolheste uma data em vez de **No expiration**, põe um lembrete no calendário.

### Verificação rápida (uma vez por semana, 1 minuto)

- No Telegram, `/estado`: a última verificação deve ser de há menos de uma hora.
- No painel, **Início**: "despertador ligado" a verde e a última verificação "correu bem".
- Em **Atividade**: as fontes com falha (se a Câmara aparecer, vê o telemóvel, secção 10).
