# Agregador de Notícias

Procura notícias sobre os temas que definires, dá-lhes uma nota e avisa-te por WhatsApp.
Corre sozinho no GitHub, de 30 em 30 minutos, sem servidor e sem custos.

## Instalação (uma vez)

**1. Carregar os ficheiros para o repositório privado `agregador-noticias`**
- No GitHub: **Add file → Upload files** e carrega `agregador.py`, `config.yaml`,
  `requirements.txt` e `estado.json`.
- O agendamento vive numa pasta escondida. Cria-o assim: **Add file → Create new file**,
  no nome escreve `.github/workflows/agregador.yml` (as barras criam as pastas),
  cola lá o conteúdo do ficheiro `.github/workflows/agregador.yml` e faz **Commit changes**.

**2. Ativar o WhatsApp (CallMeBot, gratuito)**
- Guarda nos contactos do telemóvel o número do CallMeBot indicado em callmebot.com
  (secção WhatsApp) e envia-lhe por WhatsApp a frase de ativação que lá aparece.
- Em poucos minutos recebes a resposta "API Activated for your phone number. Your APIKEY is …".
  Se não chegar em 2 minutos, tenta de novo daí a 24 horas.

**3. Guardar os segredos no GitHub**
- Settings → Secrets and variables → Actions → New repository secret
- `WHATSAPP_TELEFONE`: o teu número com indicativo, só algarismos (ex: `351912345678`).
- `WHATSAPP_APIKEY`: a apikey que o CallMeBot te enviou.

**4. Testar**
- Actions → Agregador de Notícias → Run workflow → **teste**. Deves receber uma mensagem no WhatsApp.
- Depois **simular**: mostra no registo o que enviaria, sem enviar nada.
- A partir daí corre sozinho de 30 em 30 minutos.

## Personalizar

Edita `config.yaml` no GitHub (ícone do lápis). Aí defines:
- as **pesquisas**, com palavras-chave de prioridade alta, média e baixa, palavras a excluir
  e palavras **obrigatórias** (ex: `["sertã"]` para só aceitar notícias que falem da Sertã);
- as **fontes** confiáveis, neutras e bloqueadas, feeds RSS e **páginas sem RSS**
  (usa o domínio, ex: `publico.pt`);
- os **limites** de alerta, o horário de silêncio e a hora do resumo diário;
- os **pesos** da pontuação.

## Encontrar feeds RSS escondidos

Muitos sites têm feed RSS mas não o mostram. Para os encontrar a partir de uma pesquisa,
no teu computador:

```
python agregador.py --procurar-feeds "Sertã"
```

Se o texto for o nome de uma pesquisa do `config.yaml`, usa a consulta e as palavras
obrigatórias dela; senão, pesquisa o texto tal como está. A app vê que sites publicaram
sobre o tema no último mês, procura o feed de cada um (os que a página anuncia, os
endereços habituais do WordPress, Joomla, Blogger…) e mostra-te as linhas prontas a
colar em `feeds_extra` da pesquisa (ou em `fontes.feeds`).

A descoberta automática diária usa a mesma procura, por isso as fontes novas sugeridas
por WhatsApp já trazem o feed quando ele existe.

## Sites sem RSS

Muitos sites (câmaras municipais, jornais regionais) não têm feed RSS. Junta-os em
`fontes.paginas` e a app lê a página de notícias diretamente:

```yaml
  paginas:
    - nome: "Câmara da Sertã"
      url: "https://cm-serta.pt/comunicacao/noticias"
```

Só com `nome` e `url`, a app deteta sozinha as notícias da página (fica com os links que
partilham o mesmo tipo de cartão e ignora menus e rodapés; nos links que só têm imagem,
vai buscar o título ao cartão). Se o resultado não for bom, podes indicar seletores CSS:
`item` (cada notícia), `titulo`, `resumo` e `data` (estes três dentro do item).

Para ver o que a app encontra antes de guardar, no teu computador:

```
python agregador.py --testar-pagina https://cm-serta.pt/comunicacao/noticias
python agregador.py --testar-pagina URL --item "div.noticia" --titulo "h2 a" --data "time"
```

Se a página anunciar um feed RSS escondido, a app usa-o sozinha (é mais fiável e traz
datas e resumos); para ver a leitura da página em vez do feed, junta `--sem-feed`.
Se der 0 notícias, o teste diz-te o que podes tentar.

Se uma página (ou feed) só publica notícias de um sítio, como a da Câmara da Sertã,
junta-lhe `local: true`: as notícias dela dispensam as palavras obrigatórias, porque
nem todas dizem "Sertã" no título. Põe estas fontes em `paginas_extra` ou `feeds_extra`
da pesquisa a que dizem respeito (como na pesquisa "Sertã"), e não em `fontes`, senão
dispensam as obrigatórias de todas as pesquisas.

## Descoberta automática de fontes

Uma vez por dia (a partir da hora definida em `config.yaml`, secção `descoberta`), a app:

1. Volta a pesquisar cada tema com variações da consulta e das palavras de prioridade alta.
2. Regista que sites publicam notícias relevantes e ignora os que já classificaste.
3. Escolhe os que apareceram em pelo menos 2 notícias (até 5 por dia, e nunca mais de 10 por decidir).
4. Tenta encontrar o feed RSS de cada um.
5. Envia-te por WhatsApp a lista das fontes novas.

Para decidir, junta o domínio no `config.yaml`:
- `fontes.confiaveis`: a fonte passa a valer ×1,5 (se tinha feed, junta-o também a `fontes.feeds`).
- `fontes.neutras`: deixa de ser sugerida, sem mudar o peso.
- `fontes.bloqueadas`: as notícias dela são descartadas.

Sem decisão em 14 dias, a sugestão é esquecida e não volta. Para forçar a procura já:
Actions → Run workflow → **descobrir-fontes**.

## Como decide o que enviar

`nota = (pontos das palavras + bónus) × peso da fonte`

- Palavra no título vale o dobro da que aparece só no texto. Cada palavra conta uma vez.
- Se faltar uma palavra obrigatória ou aparecer uma a excluir, a notícia é descartada.
  As obrigatórias só filtram, não dão pontos: se quiseres que contem, põe-nas também
  numa prioridade (vê a pesquisa "Sertã" no `config.yaml`, que tem "sertã" nas duas).
- Bónus: +5 por cada fonte extra a publicar o mesmo (máx. +15) e +3 se tiver menos de 1 hora.
- Fonte confiável ×1,5, desconhecida ×1,0, bloqueada é descartada.
- Nota ≥ limite de alerta: mensagem imediata. Entre os dois limites: resumo diário.
- Notícias repetidas em vários sites contam como uma só e nunca são enviadas duas vezes.
- Os alertas de cada verificação vão juntos numa só mensagem, porque o CallMeBot gratuito
  limita o número de mensagens.

## Painel (protótipo)

Abre `painel/index.html` no navegador (duplo clique, não precisa de instalação). Tem as secções Alertas, Pesquisas, Fontes e Definições, com notícias inventadas e a mesma pontuação da app. Serve para experimentares criar pesquisas, classificar fontes e ver a descoberta de fontes. Não envia nada nem altera o `config.yaml`.

Para o contexto completo do projeto (decisões, estado e próximos passos), vê `CONTEXTO.md`.

## Limites desta versão

- Recolhe do Google Notícias, de feeds RSS e de páginas de notícias. X, Instagram e Facebook não estão incluídos.
- O CallMeBot é um serviço gratuito de terceiros: só envia (não há botões nem respostas),
  tem limites de envio e pode ter falhas. Se uma mensagem falhar, os alertas ficam guardados
  e saem na verificação seguinte.
- O painel (`painel/index.html`) é ainda um protótipo em modo teste, não ligado à app real.
- Páginas que só mostram as notícias com JavaScript, ou com certificado de segurança
  inválido, não são lidas pelo raspador (o teste diz-te qual é o caso).
- Notícias de páginas sem data ficam com a data do dia em que a app as viu pela primeira
  vez. Na primeira leitura de uma página, o que já lá estava conta como antigo.
- O GitHub pode atrasar alguns minutos as execuções agendadas.

## Correr no teu computador (opcional)

```
pip install -r requirements.txt
python agregador.py --simular
```

Para enviar de verdade a partir do computador, define antes as variáveis de ambiente
`WHATSAPP_TELEFONE` e `WHATSAPP_APIKEY`.
