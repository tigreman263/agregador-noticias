"""Decide se já é altura de verificar (corre no GitHub Actions, só com a biblioteca padrão).

Para as execuções automáticas (schedule e acao=agendada) compara a última verificação
(estado.json → execucoes[-1].ts) com o intervalo: 15 min se houver alguma pesquisa
"urgente" (frequencia no config.yaml), senão 60 min. Cada pesquisa vê depois, no
agregador.py, se já é a sua altura. Os pedidos manuais correm sempre. Escreve
correr=sim|nao em GITHUB_OUTPUT.
"""
import json
import os
import re
from datetime import datetime, timezone


def decidir():
    automatica = (os.environ.get("GITHUB_EVENT_NAME") == "schedule"
                  or os.environ.get("ACAO") == "agendada")
    if not automatica:
        return True, "pedido manual"
    try:
        texto = open("config.yaml", encoding="utf-8").read()
        urgente = re.search(r"(?m)^\s+frequencia:\s*[\"']?urgente", texto)
        intervalo = 15 if urgente else 60
    except OSError:
        intervalo = 60
    try:
        execucoes = json.load(open("estado.json", encoding="utf-8")).get("execucoes") or []
        ultima = datetime.fromisoformat(execucoes[-1]["ts"]) if execucoes else None
        if ultima is not None and ultima.tzinfo is None:
            ultima = ultima.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
        ultima = None
    if ultima is None:
        return True, f"primeira verificação (intervalo {intervalo} min)"
    passou = (datetime.now(timezone.utc) - ultima).total_seconds() / 60
    # 2,5 min de folga: o GitHub não acorda o workflow ao segundo
    return (passou >= intervalo - 2.5,
            f"última verificação há {passou:.0f} min; intervalo {intervalo} min")


if __name__ == "__main__":
    correr, motivo = decidir()
    print(("A verificar: " if correr else "Ainda não é altura: ") + motivo)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("correr=" + ("sim" if correr else "nao") + "\n")
