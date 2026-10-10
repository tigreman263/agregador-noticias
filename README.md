# Agregador de Notícias

Procura notícias sobre os temas que escolheres, dá a cada uma uma nota e envia-te as mais
importantes por **WhatsApp**. Corre sozinho no GitHub, de 30 em 30 minutos (ou com a
frequência que escolheres), sem servidor e sem custos. Geres tudo num **painel** que abres no computador ou no telemóvel.

- Repositório: https://github.com/tigreman263/agregador-noticias
- Painel: https://tigreman263.github.io/agregador-noticias/painel/

## Índice

1. [Como funciona](#1-como-funciona)
2. [Instalação passo a passo](#2-instalação-passo-a-passo)
3. [Usar o painel](#3-usar-o-painel)
4. [Criar e afinar pesquisas](#4-criar-e-afinar-pesquisas)
5. [Fontes de notícias](#5-fontes-de-notícias)
6. [O que recebes no WhatsApp](#6-o-que-recebes-no-whatsapp)
7. [Referência do config.yaml](#7-referência-do-configyaml)
8. [Usar no computador (opcional)](#8-usar-no-computador-opcional)
9. [Ficheiros do projeto](#9-ficheiros-do-projeto)
10. [Resolução de problemas](#10-resolução-de-problemas)
11. [Limites](#11-limites)

---

## 1. Como funciona

De 30 em 30 minutos (por omissão; mudas no painel, em **Início → Frequência**), o GitHub
corre o programa `agregador.py`, que:

1. **Recolhe** notícias do Google Notícias (uma pesquisa por tema), dos feeds RSS que
   indicares e de sites sem RSS (lê a página de notícias diretamente).
2. **Filtra e dá nota** a cada notícia, pelas tuas palavras-chave e pela confiança da fonte.
   Notícias repetidas em vários sites contam como uma só.
3. **Envia por WhatsApp**: as de nota alta logo (alerta), as médias num resumo diário.
4. **Guarda** o que já viu e o que fez no `estado.json`, para não repetir nada.
5. Uma vez por dia, **procura fontes novas** e sugere-tas.

| Peça | O que é |
|---|---|
| GitHub Actions | Corre o agregador com a frequência escolhida (gratuito). |
| `config.yaml` | As tuas pesquisas, fontes e regras. Editas no painel. |
| `estado.json` | A memória do agregador (o que já viu, o que enviou, o que está à espera). Gravado pelo GitHub a cada execução; não o edites. |
| `painel.json` | Notícias que descartaste no painel. Gravado pelo painel. |
| Painel | Página para gerir tudo e ver a atividade (GitHub Pages). |
| CallMeBot | Serviço gratuito que entrega as mensagens no teu WhatsApp. |
| Telemóvel + Tailscale | Opcional: vai buscar os sites que bloqueiam o GitHub. |

---

## 2. Instalação passo a passo

Se o repositório `tigreman263/agregador-noticias` já existe e funciona, salta para o passo
que te falta. Para montar de raiz noutra conta, segue todos.

### 2.1 Repositório no GitHub

1. Cria uma conta em github.com (se não tiveres).
2. Cria um repositório novo (**New repository**), por exemplo `agregador-noticias`.
   Tem de ser **público**: o GitHub Actions só é ilimitado em repositórios públicos (o
   workflow acorda de 5 em 5 minutos, o que num privado esgota os 2000 minutos grátis por
   mês), o GitHub Pages grátis exige público e o painel lê sem token.
   Os segredos ficam sempre protegidos; num repositório público, as tuas pesquisas e as
   notícias guardadas ficam visíveis.
3. Carrega todos os ficheiros deste projeto, mantendo as pastas: `agregador.py`,
   `config.yaml`, `requirements.txt`, `estado.json`, `README.md`, `.nojekyll`,
   `.gitignore`, `index.html`, `Abrir Painel.url`, `painel/index.html` e
   `.github/workflows/agregador.yml`. (Noutra conta, troca no `Abrir Painel.url` o
   endereço do painel pelo teu.)
   No site do GitHub: **Add file → Upload files** para os ficheiros normais; para o
   workflow, **Add file → Create new file**, escreve o nome
   `.github/workflows/agregador.yml` (as barras criam as pastas) e cola o conteúdo.

### 2.2 Ativar o WhatsApp (CallMeBot, gratuito)

1. Abre https://www.callmebot.com/blog/free-api-whatsapp-messages/ e segue as instruções
   da secção WhatsApp: guarda o número do CallMeBot nos contactos do telemóvel e envia-lhe
   por WhatsApp a frase de ativação indicada no site.
2. Em poucos minutos recebes "API Activated for your phone number. Your APIKEY is …".
   Se não chegar em 2 minutos, tenta de novo 24 horas depois.
3. Guarda o número da **apikey** (só os algarismos).

O CallMeBot só envia mensagens: não há botões nem respostas. É um serviço gratuito de
terceiros, com limites de envio (por isso os alertas vão agrupados).

### 2.3 Guardar os segredos no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository secret**.

| Nome | Valor |
|---|---|
| `WHATSAPP_TELEFONE` | O teu número com indicativo, só algarismos (ex.: `351912345678`). |
| `WHATSAPP_APIKEY` | A apikey do CallMeBot. |

Ou no terminal, com o GitHub CLI (`gh`), colando o valor quando pedir:

```
gh secret set WHATSAPP_TELEFONE -R tigreman263/agregador-noticias
gh secret set WHATSAPP_APIKEY -R tigreman263/agregador-noticias
```

### 2.4 Primeiro teste

1. No repositório: **Actions → Agregador de Notícias → Run workflow**.
2. Escolhe **teste** e carrega em **Run workflow**. Deves receber no WhatsApp
   "✅ O agregador de notícias está ligado ao WhatsApp".
3. Corre de novo com **simular**: abre a execução e vê no registo o que seria enviado,
   sem enviar nada.
4. A partir daqui o agregador corre sozinho de 30 em 30 minutos (podes mudar no painel,
   secção 3). O GitHub pode atrasar as execuções agendadas alguns minutos, por vezes mais.

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

Sem token, o painel só mostra. Para criar pesquisas, decidir fontes, descartar notícias e
correr ações, precisa de um token do GitHub:

1. Abre https://github.com/settings/personal-access-tokens/new.
2. **Token name**: `painel agregador`. **Expiration**: a que preferires (ex.: 1 ano).
3. **Repository access**: **Only select repositories** → escolhe `agregador-noticias`.
4. **Permissions → Repository permissions**:
   **Contents: Read and write** e **Actions: Read and write**.
5. **Generate token** e copia-o.
6. No painel, secção **Ligação**: cola o token e carrega em **Guardar e testar**.
   Deve aparecer "Ligado: podes ler e gravar".

O token fica guardado só nesse navegador. Num aparelho partilhado, usa
**Esquecer token** no fim. Quando o token expirar, cria outro da mesma forma.

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

---

## 3. Usar o painel

| Secção | O que tem |
|---|---|
| **Início** | Última verificação (correu bem / falhou, com link para o registo), alertas de hoje, notícias à espera, fontes por decidir. **Frequência**: de quanto em quanto tempo o agregador procura (5 minutos a 1 vez por dia). Botões para correr já: **Verificar agora**, **Simular** (mostra no registo o que seria enviado, sem enviar), **Testar WhatsApp** e **Procurar fontes novas**. |
| **Pesquisas** | Criar, editar, pausar e apagar pesquisas. Mostra o resultado da última verificação de cada uma. |
| **Atividade** | Execuções no GitHub, o que a app fez em cada uma (notícias lidas, novas relevantes, alertas, fontes com falha, fontes trazidas pelo telemóvel), o que foi enviado para o WhatsApp, e o que está à espera (alertas adiados e resumo). |
| **Fontes** | Fontes sugeridas pela app (Confiável / Neutra / Bloquear), listas de confiáveis, neutras e bloqueadas, e feeds e sites gerais. |
| **Ligação** | Repositório e token do GitHub, com as instruções para o criar. |
| **Ajuda** | Este documento. |

Notas:

- Tudo o que gravas no painel fica no `config.yaml` do GitHub e vale a partir da
  verificação seguinte. Para ver o efeito logo, usa **Simular**.
- Ao gravar, o painel só reescreve a secção que mudaste; os comentários do resto do
  `config.yaml` mantêm-se.
- **Descartar** (em Atividade): tira uma notícia dos alertas adiados ou do resumo;
  **Descartar todos** (aparece quando há mais do que uma) tira a lista inteira. O painel grava isso em `painel.json` e o agregador tira-as na verificação
  seguinte, sem as enviar.
- "**novas relevantes**" conta só as notícias relevantes que ainda não tinham sido
  vistas. "0 novas relevantes" não é erro: quer dizer que não apareceu nada de novo.
- O painel atualiza sozinho de 5 em 5 minutos; usa **Atualizar** para ver já.
- **Frequência**: o GitHub acorda o agregador de 5 em 5 minutos; se ainda não passou o
  intervalo que escolheste, ele termina logo, sem fazer nada (no separador Actions do
  GitHub vês muitas execuções curtas, é normal). Os botões de **Correr agora** não
  esperam pelo intervalo.

---

## 4. Criar e afinar pesquisas

Cada pesquisa tem:

| Campo | Para que serve |
|---|---|
| Nome | Como aparece nas mensagens. |
| O que procurar | A consulta no Google Notícias (ex.: `Sertã`, `apoios agricultura`). |
| Palavras obrigatórias | A notícia só conta se tiver **todas**. Servem para filtrar um lugar (ex.: `sertã`). Deixa vazio para aceitar qualquer lugar. **Não dão pontos.** |
| Prioridade alta / média / baixa | Palavras que dão pontos: alta 10, média 4, baixa 1. No título valem o dobro. |
| Palavras a excluir | Se aparecer uma, a notícia é descartada. |
| Nota para alerta | A partir desta nota, a notícia é enviada logo (por omissão 25). |
| Nota para resumo | A partir desta nota, vai para o resumo diário (por omissão 10). |
| Fontes só desta pesquisa | Feeds RSS e sites sem RSS só para este tema (ver secção 5). |

### Como é calculada a nota

`nota = (pontos das palavras + bónus) × peso da fonte`

- Cada palavra conta uma vez por notícia. No título vale o dobro.
- A comparação ignora maiúsculas e acentos ("subsídio" = "subsidio"). Palavras de até 3
  letras só contam inteiras; as outras aceitam plurais ("apoio" apanha "apoios").
- Bónus: +5 por cada fonte extra a publicar a mesma notícia (máx. +15) e +3 se tiver
  menos de 1 hora.
- Peso: fonte confiável ×1,5; outra ×1,0; bloqueada é descartada.
- Notícias sem nenhuma palavra das prioridades (0 pontos) são ignoradas.
- Notícias com mais de 48 horas são ignoradas.

### Dicas

- **Evita palavras genéricas em alta.** "apoio" sozinha em alta apanhava notícias de
  "apoio político". Põe-nas em média e usa em alta termos específicos
  (ex.: "fundo perdido", "candidaturas", "PRR", "Portugal 2030", "PEPAC").
- **Não repitas a mesma palavra com e sem acento**: conta como a mesma e soma a dobrar.
- **Para notícias de um lugar**, usa a obrigatória com o nome do lugar e põe-no também
  em baixa (para dar algum ponto), e baixa a nota do resumo (a pesquisa "Sertã" usa 20 e 4).
- **Notícias brasileiras**: o Google Notícias mistura-as. Bloqueia `br` nas fontes
  (secção 5.2).
- **Para ver o efeito** de uma mudança, carrega em **Simular** e abre o registo.
- Quando apagas uma pesquisa, o que ela deixou no estado (notícias à espera, sites
  registados para sugestões) é esquecido sozinho.

---

## 5. Fontes de notícias

### 5.1 Google Notícias

Cada pesquisa procura no Google Notícias pela sua consulta, em português de Portugal
(`geral.google_news`). Não tens de fazer nada.

### 5.2 Confiáveis, neutras e bloqueadas

Listas de domínios (sem `www` nem `https://`), no painel em **Fontes**:

- **Confiáveis**: valem ×1,5.
- **Neutras**: peso normal; deixam de ser sugeridas.
- **Bloqueadas**: as notícias delas são descartadas (também as que já estavam à espera).

Um domínio apanha também os subdomínios e o que acaba nele: `sapo.pt` inclui
`jornaldeabrantes.sapo.pt`; **`br` bloqueia todos os sites `.br`** (Brasil).

### 5.3 Feeds RSS

- **Gerais** (`fontes.feeds`, painel **Fontes**): lidos em todas as pesquisas.
- **Só de uma pesquisa** (`feeds_extra`, painel **Pesquisas → Editar → Fontes só desta
  pesquisa**): um por linha, `Nome | https://endereço-do-feed`.
- **`local`**: junta `| local` à linha (ou `local: true` no `config.yaml`) quando a fonte só
  publica sobre um lugar, como a de uma câmara municipal. As notícias dela dispensam as
  palavras obrigatórias (nem todas dizem o nome do lugar no título). Usa `local` só nas
  fontes de uma pesquisa, nunca nas gerais.

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

Se o texto for o nome de uma pesquisa, usa a consulta e as obrigatórias dela. A app vê
que sites publicaram sobre o tema no último mês, procura o feed de cada um (os que a
página anuncia e os endereços habituais do WordPress, Joomla, Blogger…) e mostra as
linhas prontas a colar. Feeds de sites nacionais (SAPO, Observador…) trazem notícias de
tudo; para temas locais prefere os regionais.

### 5.6 Descoberta automática de fontes

Uma vez por dia (a partir das 9h), a app volta a pesquisar cada tema, vê que sites
publicam notícias relevantes, escolhe os que tiveram pelo menos 2 (até 5 por dia e nunca
mais de 10 por decidir), procura o feed de cada um e envia-te a lista por WhatsApp.
Decide-as no painel, em **Fontes → Sugeridas pela app**: **Confiável** (se tiver feed, é
juntado aos feeds gerais), **Neutra** ou **Bloquear**. Sem decisão em 14 dias, a sugestão
é esquecida. Para procurar já: **Procurar fontes novas** no Início.

### 5.7 Sites que bloqueiam o GitHub

Quando um site recusa a ligação ("Connection reset", "não consegui ligar ao site"), o
agregador marca-o como bloqueado durante 30 dias. Com o telemóvel configurado
(passo 2.7), passa a ser trazido por ele. Para obrigar um site a ir sempre pelo
telemóvel, junta-lhe `telemovel: true` no `config.yaml`.

---

## 6. O que recebes no WhatsApp

- **Alertas** (nota ≥ nota de alerta): numa só mensagem por verificação, até 5
  (`max_alertas_por_execucao`); o excesso vai para o resumo. Cada alerta traz o título, a
  fonte, a nota, a pesquisa, as palavras encontradas, há quanto tempo saiu e o link.
- **Resumo diário** (nota entre as duas notas): uma vez por dia, a partir das 8h
  (`hora_resumo`), com as 15 melhores. Notícias à espera há mais de 48 horas saem da fila.
- **Fontes novas sugeridas**: uma vez por dia (secção 5.6).
- **Horário de silêncio** (23h–7h): nada é enviado; os alertas ficam adiados (até 50; o
  excesso vai para o resumo) e saem depois.
- **Se o envio falhar** (CallMeBot em baixo, limite atingido): os alertas ficam adiados e
  saem na verificação seguinte, sem se perderem nem se repetirem. O resumo também volta a
  tentar; se for tão grande que ocupe duas mensagens e só a segunda falhar, a primeira
  parte pode chegar repetida.

---

## 7. Referência do config.yaml

O painel edita as secções `pesquisas` e `fontes`. As outras editas no GitHub (ícone do
lápis no ficheiro).

| Chave | Por omissão | Significado |
|---|---|---|
| `geral.intervalo_minutos` | 30 | De quantos em quantos minutos procura (mínimo 5). Muda-se no painel, em Início → Frequência. |
| `geral.fuso` | `Europe/Lisbon` | Fuso horário. |
| `geral.idade_max_horas` | 48 | Ignora notícias mais antigas. |
| `geral.max_alertas_por_execucao` | 5 | Alertas por verificação; o excesso vai para o resumo. |
| `geral.silencio` | `{inicio: 23, fim: 7}` | Horas sem envios. |
| `geral.hora_resumo` | 8 | Hora a partir da qual sai o resumo. |
| `geral.google_news` | `pt-PT`, `PT` | Língua e país do Google Notícias. |
| `pesos.pontos` | alta 10, média 4, baixa 1 | Pontos por palavra. |
| `pesos.fonte_confiavel` | 1.5 | Multiplicador das confiáveis. |
| `pesos.fonte_desconhecida` | 1.0 | Multiplicador das outras. |
| `pesos.bonus_fonte_extra` / `bonus_fonte_extra_max` | 5 / 15 | Bónus por fonte extra com a mesma notícia. |
| `pesos.bonus_ultima_hora` | 3 | Bónus para notícias com menos de 1 hora. |
| `fontes.confiaveis` / `neutras` / `bloqueadas` | — | Listas de domínios (secção 5.2). |
| `fontes.feeds` | — | Feeds gerais: `{nome, url, local?, telemovel?}`. |
| `fontes.paginas` | — | Sites sem RSS gerais: `{nome, url, item?, titulo?, resumo?, data?, max?, usar_feed?, local?, telemovel?}`. |
| `descoberta.ativa` | true | Liga a descoberta diária. |
| `descoberta.hora` | 9 | A partir desta hora. |
| `descoberta.max_sugestoes_por_dia` | 5 | Sugestões por dia. |
| `descoberta.max_pendentes` | 10 | Não sugere mais se tiveres estas por decidir. |
| `descoberta.min_noticias` | 2 | Notícias relevantes mínimas para sugerir um site. |
| `descoberta.procurar_feeds` | true | Procura o feed dos sites sugeridos. |
| `pesquisas[]` | — | `nome`, `ativa`, `consulta`, `obrigatorias`, `palavras.alta/media/baixa`, `excluir`, `limite_alerta`, `limite_resumo`, `feeds_extra`, `paginas_extra` (secção 4). |

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

Para enviar a partir do computador, define antes as variáveis (PowerShell):

```
$env:WHATSAPP_TELEFONE="351912345678"; $env:WHATSAPP_APIKEY="123456"
```

Atenção: o `config.yaml` e o `estado.json` verdadeiros estão no GitHub (o painel grava
lá). Antes de usar o computador, descarrega a versão atual do repositório.

---

## 9. Ficheiros do projeto

| Ficheiro | O que é |
|---|---|
| `agregador.py` | Todo o programa: recolha, leitor de páginas, pontuação, WhatsApp, descoberta, telemóvel. |
| `config.yaml` | Pesquisas, fontes e regras. |
| `estado.json` | Memória do agregador, gravada pelo GitHub. Não editar. |
| `painel.json` | Notícias descartadas no painel. |
| `requirements.txt` | Bibliotecas Python (requests, PyYAML, defusedxml, beautifulsoup4). |
| `.github/workflows/agregador.yml` | Acorda de 5 em 5 minutos, verifica conforme `geral.intervalo_minutos`, e ações manuais (normal, teste, simular, descobrir-fontes). |
| `painel/index.html` | O painel. |
| `Abrir Painel.url` / `Abrir Painel.bat` | Abrem o painel no navegador (duplo clique no Windows). |
| `.gitattributes` | Mantém o formato de linhas do Windows nos dois atalhos. |
| `index.html` | Encaminha o endereço curto do GitHub Pages para o painel. |
| `.nojekyll` | Faz o GitHub Pages servir os ficheiros tal como estão. |
| `README.md` | Este documento (também em **Ajuda** no painel). |
| `CONTEXTO.md` | Decisões técnicas, para quem continuar o desenvolvimento. |
| `.claude/` | Agentes e configuração do Claude Code usados no desenvolvimento. |

---

## 10. Resolução de problemas

**Não recebo nada no WhatsApp**
1. No painel, **Início → Última verificação**: se falhou, abre **ver registo**.
2. Carrega em **Testar WhatsApp**. Se não chegar, confirma os segredos
   `WHATSAPP_TELEFONE` e `WHATSAPP_APIKEY` (passo 2.3).
3. Pode simplesmente não haver notícias novas com nota suficiente: vê **Atividade**.

**"CallMeBot respondeu …: apikey can not be empty or it has an invalid format"**
A apikey guardada está errada. Copia só o código que vem a seguir a "APIKEY is" na
mensagem do CallMeBot e volta a guardar o segredo `WHATSAPP_APIKEY`. Confirma que
ativaste o serviço de **WhatsApp** (o CallMeBot tem serviços diferentes para chamadas).

**As execuções automáticas atrasam ou falham uma vez por outra**
O GitHub atrasa as execuções agendadas quando está muito ocupado. É normal; a seguinte
apanha o que ficou para trás.

**"Fonte com falha … Connection reset by peer"**
O site recusa os servidores do GitHub. Ver secção 5.7 e passo 2.7.

**"0 novas relevantes"**
Não apareceu nada de novo com pontos suficientes; as notícias já vistas não contam.

**Chegam notícias fora do tema**
Vê em **Atividade** que pesquisa as trouxe e afina as palavras (secção 4): tira palavras
genéricas de alta, junta palavras a excluir, ou bloqueia a fonte. As que já estão à
espera podes **Descartar**.

**O painel diz "Só leitura"**
Falta o token (passo 2.6). Se diz que o token não é válido ou não tem permissão, cria
outro com **Contents** e **Actions** em **Read and write**.

**O painel diz que o GitHub limitou os pedidos**
Sem token, o GitHub só deixa 60 pedidos por hora. Junta o token, ou espera uma hora.

**Um site sem RSS dá 0 notícias**
Corre `--testar-pagina` (secção 5.4): confirma que é a página com a lista de notícias;
se o site usa JavaScript ou tem o certificado inválido, procura um feed ou retira-o.

**Mudei algo e o painel não mostra**
O GitHub Pages demora 1 a 2 minutos a publicar mudanças ao painel; carrega em
**Atualizar** ou recarrega a página.

---

## 11. Limites

- Fontes: Google Notícias, feeds RSS e páginas de notícias. X, Instagram e Facebook não
  estão incluídos (acesso restrito ou pago).
- O CallMeBot é gratuito e de terceiros: só envia, tem limites de envio e pode falhar.
- Sites que bloqueiam o GitHub só são lidos com o telemóvel Android configurado e com rede.
- Páginas que só mostram notícias com JavaScript, ou com certificado inválido, não são lidas.
- O GitHub pode atrasar as execuções agendadas.
