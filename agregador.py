#!/usr/bin/env python3
"""Agregador de Notícias.

Recolhe notícias (Google Notícias + feeds RSS), remove duplicados, pontua cada
uma pelas palavras-chave e pela confiança da fonte, e envia alertas por Telegram.

Uso:
    python agregador.py                    # execução normal
    python agregador.py --simular          # mostra o que faria, sem enviar nem guardar
    python agregador.py --teste            # envia uma mensagem de teste
    python agregador.py --fontes           # execução normal + procura de fontes novas agora
    python agregador.py --descobrir-chat   # mostra o teu chat id do Telegram

Variáveis de ambiente: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import argparse
import difflib
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
import yaml

try:
    from defusedxml import ElementTree as ET
except ImportError:  # pragma: no cover
    from xml.etree import ElementTree as ET

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "config.yaml"
ESTADO = RAIZ / "estado.json"
UA = "Mozilla/5.0 (compatible; AgregadorNoticias/1.0)"
NIVEIS = ("alta", "media", "baixa")
DIAS_VISTOS = 14


def erro(msg):
    """Mostra um erro. No GitHub Actions aparece também como anotação da execução."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::error::" + msg.replace("\n", " "))
    else:
        print("Erro: " + msg)


def segredos_em_falta(token, chat):
    """Diz exatamente que segredos faltam (nunca mostra os valores)."""
    falta = [n for n, v in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat)) if not v]
    return (f"falta(m) o(s) segredo(s) {' e '.join(falta)} no GitHub "
            "(Settings > Secrets and variables > Actions).") if falta else ""

DOMINIOS_IGNORADOS = {"", "news.google.com", "google.com"}
DECISOES = {"c": "confiavel", "n": "neutra", "b": "bloqueada"}
ROTULOS = {"confiavel": "marcada como confiável", "neutra": "marcada como neutra",
           "bloqueada": "bloqueada"}


# ---------------------------------------------------------------- utilitários

def normalizar(texto):
    """Minúsculas, sem acentos, só letras e números separados por espaços."""
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def limpar_html(texto):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(texto or ""))).strip()


def dominio_de(url):
    h = urlparse(url or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h


def dominio_em(dominio, lista):
    for d in lista or []:
        d = str(d).lower().strip()
        d = d[4:] if d.startswith("www.") else d
        if d and (dominio == d or dominio.endswith("." + d)):
            return True
    return False


def parse_data(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def ha_quanto_tempo(data, agora):
    if not data:
        return "data desconhecida"
    minutos = int((agora - data).total_seconds() // 60)
    if minutos < 1:
        return "agora mesmo"
    if minutos < 60:
        return f"há {minutos} min"
    if minutos < 60 * 48:
        return f"há {minutos // 60} h"
    return f"há {minutos // 1440} dias"


def esc(t):
    return html.escape(t or "", quote=False)


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


# ------------------------------------------------------------------- recolha

def ler_feed(url, nome_fonte=None):
    """Lê um feed RSS ou Atom e devolve uma lista de notícias (dicionários)."""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    raiz = ET.fromstring(r.content)
    itens = []
    for el in raiz.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        d = {}
        for filho in el:
            nome = _local(filho.tag)
            if nome == "link":
                if "link" not in d or filho.attrib.get("rel") == "alternate":
                    d["link"] = filho.attrib.get("href") or (filho.text or "").strip()
            elif nome in ("title", "description", "summary", "content",
                          "pubdate", "published", "updated"):
                d.setdefault(nome, (filho.text or "").strip())
            elif nome == "source":
                d["fonte_nome"] = (filho.text or "").strip()
                d["fonte_url"] = filho.attrib.get("url", "")
        titulo = limpar_html(d.get("title", ""))
        link = d.get("link", "")
        if not titulo or not link:
            continue
        fonte_nome = d.get("fonte_nome") or ""
        if fonte_nome and titulo.endswith(" - " + fonte_nome):
            titulo = titulo[: -len(" - " + fonte_nome)].strip()
        dominio = dominio_de(d["fonte_url"]) if d.get("fonte_url") else dominio_de(link)
        itens.append({
            "titulo": titulo,
            "resumo": limpar_html(d.get("description") or d.get("summary")
                                  or d.get("content") or ""),
            "link": link,
            "data": parse_data(d.get("pubdate") or d.get("published") or d.get("updated")),
            "dominio": dominio,
            "fonte": fonte_nome or nome_fonte or dominio,
            "site": d.get("fonte_url", ""),
        })
    return itens


def url_google_news(consulta, cfg):
    g = (cfg.get("geral") or {}).get("google_news") or {}
    return ("https://news.google.com/rss/search?q=" + quote_plus(consulta)
            + f"&hl={g.get('hl', 'pt-PT')}&gl={g.get('gl', 'PT')}"
            + f"&ceid={g.get('ceid', 'PT:pt-150')}")


def recolher(pesq, cfg):
    """Vai buscar as notícias de todas as fontes desta pesquisa."""
    pedidos = []
    if pesq.get("consulta"):
        pedidos.append(("Google Notícias", url_google_news(pesq["consulta"], cfg)))
    for f in (cfg.get("fontes") or {}).get("feeds") or []:
        pedidos.append((f.get("nome"), f.get("url")))
    for f in pesq.get("feeds_extra") or []:
        pedidos.append((f.get("nome"), f.get("url")))
    todas = []
    for nome, url in pedidos:
        if not url:
            continue
        try:
            itens = ler_feed(url, nome)
            print(f"  fonte '{nome}': {len(itens)} notícias")
            todas += itens
        except Exception as e:  # uma fonte em baixo não pára as outras
            print(f"  aviso: falhou '{nome}' ({type(e).__name__})")
    return todas


# ---------------------------------------------------------------- pontuação

def pontos_palavras(item, pesq, pesos):
    """Devolve (pontos, palavras encontradas) ou None se tem palavra de exclusão."""
    titulo = " " + normalizar(item["titulo"]) + " "
    texto = " " + normalizar(item["resumo"]) + " "
    for x in pesq.get("excluir") or []:
        xn = normalizar(x)
        if xn and (f" {xn} " in titulo or f" {xn} " in texto):
            return None
    total = 0
    achadas = {n: [] for n in NIVEIS}
    for nivel in NIVEIS:
        for p in (pesq.get("palavras") or {}).get(nivel) or []:
            pn = normalizar(p)
            if not pn:
                continue
            # palavras curtas (ex.: "ia") só valem inteiras; as outras aceitam plurais
            chave = f" {pn} " if len(pn) <= 3 else f" {pn}"
            valor = pesos["pontos"][nivel]
            if chave in titulo:
                total += valor * 2
                achadas[nivel].append(p)
            elif chave in texto:
                total += valor
                achadas[nivel].append(p)
    return total, achadas


def parecidas(a, b):
    """Duas notícias são a mesma história se os títulos forem muito parecidos."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    if len(ta & tb) / len(ta | tb) >= 0.6:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def agrupar(itens):
    grupos = []
    for it in itens:
        tn = normalizar(it["titulo"])
        for g in grupos:
            if g["link"] == it["link"] or parecidas(tn, g["tn"]):
                g["itens"].append(it)
                break
        else:
            grupos.append({"tn": tn, "link": it["link"], "itens": [it]})
    return grupos


def id_de(pesq_nome, titulo):
    base = normalizar(pesq_nome) + "|" + normalizar(titulo)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def avaliar(itens, pesq, cfg, estado, agora_utc):
    """Filtra, agrupa e pontua. Devolve candidatos ordenados por nota."""
    pesos = cfg["pesos"]
    fontes = cfg.get("fontes") or {}
    idade_max = timedelta(hours=(cfg.get("geral") or {}).get("idade_max_horas", 48))
    validos = []
    for it in itens:
        if dominio_em(it["dominio"], fontes.get("bloqueadas")):
            continue
        if it["data"] and agora_utc - it["data"] > idade_max:
            continue
        r = pontos_palavras(it, pesq, pesos)
        if r is None or r[0] == 0:
            continue
        it["kw"], it["achadas"] = r
        validos.append(it)
    registar_dominios(estado, pesq, validos, agora_utc)

    candidatos = []
    for g in agrupar(validos):
        dominios = {i["dominio"] for i in g["itens"]}
        bonus = min((len(dominios) - 1) * pesos["bonus_fonte_extra"],
                    pesos["bonus_fonte_extra_max"])
        melhor, melhor_nota = None, -1
        for i in g["itens"]:
            b = bonus
            if i["data"] and agora_utc - i["data"] < timedelta(hours=1):
                b += pesos["bonus_ultima_hora"]
            confiavel = dominio_em(i["dominio"], fontes.get("confiaveis"))
            peso = pesos["fonte_confiavel"] if confiavel else pesos["fonte_desconhecida"]
            nota = (i["kw"] + b) * peso
            if nota > melhor_nota:
                melhor, melhor_nota, melhor_conf = i, nota, confiavel
        ids = [id_de(pesq["nome"], i["titulo"]) for i in g["itens"]]
        if any(x in estado["vistos"] for x in ids):
            continue
        if melhor_nota >= pesq.get("limite_alerta", 25):
            nivel = "alerta"
        elif melhor_nota >= pesq.get("limite_resumo", 10):
            nivel = "resumo"
        else:
            continue
        candidatos.append({
            "titulo": melhor["titulo"], "link": melhor["link"],
            "fonte": melhor["fonte"], "confiavel": melhor_conf,
            "nota": round(melhor_nota, 1), "pesquisa": pesq["nome"],
            "achadas": melhor["achadas"], "n_fontes": len(dominios),
            "data": melhor["data"].isoformat() if melhor["data"] else None,
            "nivel": nivel, "ids": ids,
        })
    candidatos.sort(key=lambda c: c["nota"], reverse=True)
    return candidatos


# ------------------------------------------------------------------ estado

def carregar_estado():
    base = {"vistos": {}, "resumo": [], "adiados": [], "ultimo_resumo": "",
            "fontes": {"confiavel": [], "neutra": [], "bloqueada": []},
            "feeds_aprovados": [], "sugeridas": {}, "botoes": {}, "dominios": {},
            "ultima_descoberta": "", "update_offset": 0}
    if ESTADO.exists():
        try:
            base.update(json.loads(ESTADO.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print("Aviso: estado.json inválido, a recomeçar do zero.")
    for k in ("confiavel", "neutra", "bloqueada"):
        base["fontes"].setdefault(k, [])
    return base


def guardar_estado(estado):
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


def marcar_visto(estado, cand, agora_utc):
    for i in cand["ids"]:
        estado["vistos"][i] = agora_utc.isoformat()


def podar(estado, agora_utc):
    limite = agora_utc - timedelta(days=DIAS_VISTOS)
    estado["vistos"] = {k: v for k, v in estado["vistos"].items()
                        if parse_data(v) and parse_data(v) > limite}
    limite_dom = agora_utc - timedelta(days=30)
    estado["dominios"] = {d: r for d, r in estado.get("dominios", {}).items()
                          if d in estado["sugeridas"]
                          or (parse_data(r.get("ultima")) or agora_utc) > limite_dom}
    limite_resumo = agora_utc - timedelta(hours=48)
    estado["resumo"] = [c for c in estado["resumo"]
                        if (parse_data(c.get("ts")) or agora_utc) > limite_resumo][-100:]


# ---------------------------------------------------------------- Telegram

def telegram(token, metodo, **dados):
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{metodo}",
                          json=dados, timeout=20)
    except requests.RequestException:
        raise RuntimeError("falha de rede ao contactar o Telegram") from None
    if not r.ok:
        raise RuntimeError(f"Telegram respondeu {r.status_code}: {r.text[:150]}")
    return r.json()


def enviar(token, chat, texto, botoes=None):
    dados = {"chat_id": chat, "text": texto, "parse_mode": "HTML",
             "disable_web_page_preview": False}
    if botoes:
        dados["reply_markup"] = {"inline_keyboard": [
            [{"text": t, "callback_data": c} for t, c in linha] for linha in botoes]}
    telegram(token, "sendMessage", **dados)
    time.sleep(0.6)


def formatar_alerta(c, agora_utc):
    linhas = [f'🔔 <b><a href="{html.escape(c["link"])}">{esc(c["titulo"])}</a></b>']
    estado_fonte = "confiável" if c["confiavel"] else "fonte nova"
    linhas.append(f'{esc(c["fonte"])} ({estado_fonte}) · nota {c["nota"]} · {esc(c["pesquisa"])}')
    palavras = []
    rot = {"alta": "alta", "media": "média", "baixa": "baixa"}
    for n in NIVEIS:
        if c["achadas"].get(n):
            palavras.append(f'{rot[n]}: {esc(", ".join(c["achadas"][n]))}')
    if palavras:
        linhas.append("🔑 " + " · ".join(palavras))
    quando = ha_quanto_tempo(parse_data(c["data"]), agora_utc)
    extra = f' · {c["n_fontes"]} fontes' if c["n_fontes"] > 1 else ""
    linhas.append(f"🕒 {quando}{extra}")
    return "\n".join(linhas)


def enviar_resumo(token, chat, itens):
    itens = sorted(itens, key=lambda c: c["nota"], reverse=True)[:15]
    bloco = [f"📰 <b>Resumo — {len(itens)} notícias</b>"]
    partes, tamanho = [], 0
    for n, c in enumerate(itens, 1):
        linha = (f'\n{n}. <a href="{html.escape(c["link"])}">{esc(c["titulo"])}</a>\n'
                 f'   {esc(c["fonte"])} · nota {c["nota"]} · {esc(c["pesquisa"])}')
        if tamanho + len(linha) > 3500:
            partes.append("".join(bloco))
            bloco, tamanho = [], 0
        bloco.append(linha)
        tamanho += len(linha)
    partes.append("".join(bloco))
    for p in partes:
        enviar(token, chat, p)


def em_silencio(hora, silencio):
    ini, fim = silencio.get("inicio", 23), silencio.get("fim", 7)
    return (hora >= ini or hora < fim) if ini > fim else (ini <= hora < fim)


# ------------------------------------------------------- descoberta de fontes

def registar_dominios(estado, pesq, validos, agora_utc):
    """Guarda que sites publicaram notícias relevantes (base das sugestões)."""
    dom = estado.setdefault("dominios", {})
    for it in validos:
        d = it["dominio"]
        if d in DOMINIOS_IGNORADOS:
            continue
        reg = dom.setdefault(d, {"nome": it["fonte"], "site": it.get("site", ""),
                                 "ids": [], "pesquisas": [], "exemplo": it["titulo"],
                                 "ultima": ""})
        i = id_de(pesq["nome"], it["titulo"])
        if i not in reg["ids"]:
            reg["ids"] = (reg["ids"] + [i])[-20:]
        if pesq["nome"] not in reg["pesquisas"]:
            reg["pesquisas"].append(pesq["nome"])
        if not reg.get("site") and it.get("site"):
            reg["site"] = it["site"]
        reg["ultima"] = agora_utc.isoformat()


def dominios_conhecidos(cfg, estado):
    f = cfg.get("fontes") or {}
    out = set()
    for lista in (f.get("confiaveis"), f.get("bloqueadas")):
        for d in lista or []:
            d = str(d).lower().strip()
            out.add(d[4:] if d.startswith("www.") else d)
    for lista in estado["fontes"].values():
        out.update(lista)
    for fd in f.get("feeds") or []:
        out.add(dominio_de(fd.get("url", "")))
    return out


def aplicar_classificacoes(cfg, estado):
    """Junta o que aprovaste/bloqueaste no Telegram à configuração desta execução."""
    f = cfg.get("fontes") or {}
    f["confiaveis"] = list(f.get("confiaveis") or []) + estado["fontes"]["confiavel"]
    f["bloqueadas"] = list(f.get("bloqueadas") or []) + estado["fontes"]["bloqueada"]
    f["feeds"] = list(f.get("feeds") or []) + estado["feeds_aprovados"]
    cfg["fontes"] = f


def aplicar_decisao(estado, dominio, decisao):
    for lista in estado["fontes"].values():
        if dominio in lista:
            lista.remove(dominio)
    estado["fontes"][decisao].append(dominio)
    sug = estado["sugeridas"].pop(dominio, None)
    estado["feeds_aprovados"] = [f for f in estado["feeds_aprovados"]
                                 if f.get("dominio") != dominio]
    if decisao == "confiavel" and sug and sug.get("feed"):
        estado["feeds_aprovados"].append(
            {"nome": sug["nome"], "url": sug["feed"], "dominio": dominio})
    for codigo, d in list(estado["botoes"].items()):
        if d == dominio:
            del estado["botoes"][codigo]


def descobrir_feed(site):
    """Tenta encontrar o feed RSS/Atom de um site (para o ler diretamente)."""
    if not site:
        return None
    try:
        r = requests.get(site, headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return None
    candidatos = []
    for tag in re.findall(r"<link\b[^>]*>", r.text[:200000], flags=re.I):
        if re.search(r"type=[\"']application/(rss|atom)\+xml[\"']", tag, re.I):
            m = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.I)
            if m:
                candidatos.append(urljoin(r.url, html.unescape(m.group(1))))
    candidatos += [urljoin(r.url, "/feed"), urljoin(r.url, "/rss")]
    for url in candidatos[:4]:
        try:
            if ler_feed(url):
                return url
        except Exception:
            continue
    return None


def descobrir(cfg, estado, agora_utc):
    """Procura fontes novas relevantes e devolve as sugestões a enviar."""
    desc = cfg.get("descoberta") or {}
    pesos = cfg["pesos"]
    for pesq in cfg.get("pesquisas") or []:
        if not pesq.get("ativa", True):
            continue
        consultas = [pesq["consulta"]] if pesq.get("consulta") else []
        consultas += list((pesq.get("palavras") or {}).get("alta") or [])[:3]
        feitas = set()
        for c in consultas:
            if c in feitas:
                continue
            feitas.add(c)
            try:
                itens = ler_feed(url_google_news(c + " when:7d", cfg), "Google Notícias")
            except Exception as e:
                print(f"  aviso: procura de fontes falhou para '{c}' ({type(e).__name__})")
                continue
            validos = []
            for it in itens:
                r = pontos_palavras(it, pesq, pesos)
                if r is not None and r[0] > 0:
                    validos.append(it)
            registar_dominios(estado, pesq, validos, agora_utc)

    conhecidos = dominios_conhecidos(cfg, estado)
    pendentes = estado["sugeridas"]
    espaco = max(0, desc.get("max_pendentes", 10) - len(pendentes))
    limite = min(desc.get("max_sugestoes_por_dia", 5), espaco)
    minimo = desc.get("min_noticias", 2)
    cands = [(d, r) for d, r in estado["dominios"].items()
             if d not in conhecidos and d not in pendentes and len(r["ids"]) >= minimo]
    cands.sort(key=lambda x: len(x[1]["ids"]), reverse=True)
    novas = []
    for d, r in cands[:limite]:
        feed = descobrir_feed(r.get("site")) if desc.get("procurar_feeds", True) else None
        novas.append({"dominio": d, "nome": r["nome"], "n": len(r["ids"]),
                      "pesquisas": r["pesquisas"][:3], "exemplo": r["exemplo"],
                      "site": r.get("site", ""), "feed": feed,
                      "codigo": hashlib.sha1(d.encode("utf-8")).hexdigest()[:8],
                      "em": agora_utc.isoformat()})
    return novas


def texto_sugestao(s):
    linhas = [f'🔎 <b>Fonte nova: {esc(s["nome"])}</b> ({esc(s["dominio"])})',
              f'Apareceu em {s["n"]} notícias relevantes · {esc(", ".join(s["pesquisas"]))}',
              f'Exemplo: {esc(s["exemplo"])}']
    linhas.append("📡 Encontrei o feed dela: se a aprovares, passo a lê-la diretamente."
                  if s["feed"] else
                  "📡 Sem feed próprio: continuo a vê-la pelo Google Notícias.")
    return "\n".join(linhas)


def enviar_sugestao(token, chat, s):
    c = s["codigo"]
    enviar(token, chat, texto_sugestao(s),
           [[("✅ Confiável", f"f:{c}:c"), ("➖ Neutra", f"f:{c}:n"),
             ("🚫 Bloquear", f"f:{c}:b")]])


def processar_botoes(token, chat, estado):
    """Lê os toques nos botões do Telegram e guarda as decisões."""
    if not (token and chat):
        return
    dados = {"allowed_updates": ["callback_query"], "timeout": 0}
    if estado.get("update_offset"):
        dados["offset"] = estado["update_offset"] + 1
    try:
        atualizacoes = telegram(token, "getUpdates", **dados).get("result", [])
    except RuntimeError as e:
        print(f"Aviso: não consegui ler os botões ({e})")
        return
    for u in atualizacoes:
        estado["update_offset"] = max(estado.get("update_offset", 0), u["update_id"])
        cq = u.get("callback_query")
        if not cq:
            continue
        msg = cq.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(chat):
            continue  # só aceita toques vindos da tua conversa
        partes = (cq.get("data") or "").split(":")
        resposta = "Opção desconhecida."
        if len(partes) == 3 and partes[0] == "f" and partes[2] in DECISOES:
            dominio = estado["botoes"].get(partes[1])
            if dominio:
                decisao = DECISOES[partes[2]]
                aplicar_decisao(estado, dominio, decisao)
                resposta = f"{dominio}: {ROTULOS[decisao]}"
                print(f"Botão: {resposta}")
            else:
                resposta = "Esta sugestão já foi tratada."
        try:
            telegram(token, "answerCallbackQuery", callback_query_id=cq["id"], text=resposta)
            if msg.get("message_id"):
                telegram(token, "editMessageReplyMarkup", chat_id=chat,
                         message_id=msg["message_id"], reply_markup={"inline_keyboard": []})
        except RuntimeError:
            pass


# ---------------------------------------------------------------- execução

def executar(cfg, token, chat, simular=False, forcar_fontes=False):
    geral = cfg.get("geral") or {}
    tz = ZoneInfo(geral.get("fuso", "Europe/Lisbon"))
    agora_utc = datetime.now(timezone.utc)
    agora = agora_utc.astimezone(tz)
    estado = carregar_estado()
    podar(estado, agora_utc)

    if not simular and not (token and chat):
        erro(segredos_em_falta(token, chat))
        return 1

    if not simular:
        processar_botoes(token, chat, estado)
    aplicar_classificacoes(cfg, estado)

    novos = []
    for pesq in cfg.get("pesquisas") or []:
        if not pesq.get("ativa", True):
            continue
        print(f"Pesquisa: {pesq['nome']}")
        itens = recolher(pesq, cfg)
        cands = avaliar(itens, pesq, cfg, estado, agora_utc)
        print(f"  {len(cands)} notícias relevantes")
        novos += cands

    desc = cfg.get("descoberta") or {}
    hoje = agora.strftime("%Y-%m-%d")
    devida = (desc.get("ativa", True) and agora.hour >= desc.get("hora", 9)
              and estado["ultima_descoberta"] != hoje
              and not em_silencio(agora.hour, geral.get("silencio") or {}))
    sugestoes = []
    if forcar_fontes or devida:
        print("A procurar fontes novas…")
        sugestoes = descobrir(cfg, estado, agora_utc)
        print(f"  {len(sugestoes)} fontes novas para sugerir")

    imediatos = [c for c in novos if c["nivel"] == "alerta"]
    para_resumo = [c for c in novos if c["nivel"] == "resumo"]
    erro = False

    if simular:
        for c in imediatos:
            print("\n[ALERTA]\n" + re.sub(r"<[^>]+>", "", formatar_alerta(c, agora_utc)))
        for c in para_resumo:
            print(f'\n[RESUMO] nota {c["nota"]} · {c["titulo"]} ({c["fonte"]})')
        for sg in sugestoes:
            print("\n[FONTE NOVA]\n" + re.sub(r"<[^>]+>", "", texto_sugestao(sg)))
        print(f"\nSimulação: {len(imediatos)} alertas, {len(para_resumo)} para o resumo, "
              f"{len(sugestoes)} fontes sugeridas.")
        return 0

    for c in para_resumo:
        c["ts"] = agora_utc.isoformat()
        estado["resumo"].append(c)
        marcar_visto(estado, c, agora_utc)

    silencio = em_silencio(agora.hour, geral.get("silencio") or {})
    fila = sorted(estado["adiados"] + imediatos, key=lambda c: c["nota"], reverse=True)
    estado["adiados"] = []
    if silencio:
        for c in imediatos:
            marcar_visto(estado, c, agora_utc)
        estado["adiados"] = fila[:50]
        print(f"Horário de silêncio: {len(fila)} alertas guardados para mais tarde.")
    else:
        limite = geral.get("max_alertas_por_execucao", 5)
        for pos, c in enumerate(fila):
            if pos >= limite:
                c["ts"] = agora_utc.isoformat()
                estado["resumo"].append(c)
                marcar_visto(estado, c, agora_utc)
                continue
            try:
                enviar(token, chat, formatar_alerta(c, agora_utc))
                marcar_visto(estado, c, agora_utc)
            except RuntimeError as e:
                erro(f"não consegui enviar o alerta: {e}")
                erro = True
                estado["adiados"] = fila[pos:][:50]
                for resto in fila[pos:]:
                    for i in resto["ids"]:
                        estado["vistos"].pop(i, None)
                break

    if (not erro and not silencio and estado["resumo"]
            and agora.hour >= geral.get("hora_resumo", 8)
            and estado["ultimo_resumo"] != hoje):
        try:
            enviar_resumo(token, chat, estado["resumo"])
            estado["resumo"] = []
            estado["ultimo_resumo"] = hoje
        except RuntimeError as e:
            erro(f"não consegui enviar o resumo: {e}")
            erro = True

    if sugestoes:
        for sg in sugestoes:
            try:
                enviar_sugestao(token, chat, sg)
                estado["sugeridas"][sg["dominio"]] = sg
                estado["botoes"][sg["codigo"]] = sg["dominio"]
            except RuntimeError as e:
                erro(f"não consegui enviar a sugestão de fonte: {e}")
                erro = True
                break
    if (forcar_fontes or devida) and not erro:
        estado["ultima_descoberta"] = hoje

    guardar_estado(estado)
    print("Concluído.")
    return 1 if erro else 0


def carregar_config():
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser(description="Agregador de Notícias")
    ap.add_argument("--simular", action="store_true", help="não envia nem guarda nada")
    ap.add_argument("--teste", action="store_true", help="envia uma mensagem de teste")
    ap.add_argument("--descobrir-chat", action="store_true", help="mostra o chat id")
    ap.add_argument("--fontes", action="store_true", help="procura fontes novas agora")
    args = ap.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    try:
        if args.descobrir_chat:
            if not token:
                erro(segredos_em_falta(token, "x"))
                return 1
            vistos = {}
            for u in telegram(token, "getUpdates",
                               allowed_updates=["message", "channel_post"]).get("result", []):
                m = u.get("message") or u.get("channel_post") or {}
                c = m.get("chat") or {}
                if c.get("id") is not None:
                    vistos[c["id"]] = c.get("first_name") or c.get("title") or "?"
            if not vistos:
                print("Nenhuma conversa encontrada. Abre o teu bot no Telegram, "
                      "carrega em Start, envia 'olá' e tenta de novo.")
                return 1
            for cid, nome in vistos.items():
                print(f"Chat id: {cid}  (conversa com: {nome})")
            return 0
        if args.teste:
            if not (token and chat):
                erro(segredos_em_falta(token, chat))
                return 1
            enviar(token, chat, "✅ O agregador de notícias está ligado ao Telegram.")
            print("Mensagem de teste enviada.")
            return 0
        return executar(carregar_config(), token, chat, simular=args.simular,
                        forcar_fontes=args.fontes)
    except RuntimeError as e:
        erro(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
