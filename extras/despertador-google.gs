// Despertador do Agregador de Notícias (Google Apps Script).
// Corre nos servidores da Google de 15 em 15 minutos e pede ao GitHub uma verificação
// "agendada"; o agregador só verifica a sério quando já passou o intervalo escolhido no
// painel. Instruções: README.md, passo 2.8.
//
// O token do GitHub NÃO vai neste código: guarda-o em Definições do projeto →
// Propriedades do script, com o nome GITHUB_TOKEN.

const REPOSITORIO = "tigreman263/agregador-noticias";

function verificar() {
  const token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) throw new Error("Falta a propriedade GITHUB_TOKEN (Definições do projeto → Propriedades do script).");
  const resposta = UrlFetchApp.fetch(
    "https://api.github.com/repos/" + REPOSITORIO + "/actions/workflows/agregador.yml/dispatches",
    {
      method: "post",
      contentType: "application/json",
      headers: {
        Authorization: "Bearer " + token.trim(),
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      payload: JSON.stringify({ ref: "main", inputs: { acao: "agendada" } }),
      muteHttpExceptions: true,
    }
  );
  const codigo = resposta.getResponseCode();
  if (codigo !== 204) {
    throw new Error("O GitHub respondeu " + codigo + ": " + resposta.getContentText().slice(0, 200));
  }
  console.log("Pedido enviado ao GitHub (204).");
}

// Corre esta função UMA vez: cria o acionador de 15 em 15 minutos (apaga os antigos).
function instalar() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger("verificar").timeBased().everyMinutes(15).create();
  console.log("Despertador instalado: corre de 15 em 15 minutos.");
}

// Para parar o despertador.
function desinstalar() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  console.log("Despertador desligado.");
}
