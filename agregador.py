#!/usr/bin/env python3
"""Agregador de Notícias.

Recolhe notícias (Google Notícias, feeds RSS e páginas sem RSS), remove duplicados,
fica com as que falam do sítio e de um assunto de cada pesquisa, e envia-as por
Telegram (logo, ou no resumo diário). Uma nota interna, que o utilizador não vê, só
serve para ordenar (escolher a melhor versão de uma notícia repetida e as primeiras
do resumo). Também vigia páginas (secção "vigiar") e avisa quando o texto muda.
Os botões das mensagens são tratados pelo Worker do Cloudflare
(extras/cloudflare/worker.js), que grava as decisões no config.yaml.

Uso:
    python agregador.py                    # execução normal
    python agregador.py --simular          # mostra o que faria, sem enviar nem guardar
    python agregador.py --teste            # envia uma mensagem de teste
    python agregador.py --fontes           # execução normal + procura de fontes novas agora
    python agregador.py --testar-pagina URL [--item CSS --titulo CSS ...]
                                           # mostra o que o leitor de páginas encontra
    python agregador.py --testar-vigia URL [--parte CSS]
                                           # mostra o texto que a vigilância compara
    python agregador.py --procurar-feeds "TEXTO"
                                           # procura feeds RSS escondidos sobre um tema

Variáveis de ambiente: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import argparse
import difflib
import hashlib
import html
import json
import os
import re
import subprocess
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
from bs4 import BeautifulSoup

try:
    from defusedxml import ElementTree as ET
except ImportError:  # pragma: no cover
    from xml.etree import ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):  # consola do Windows (cp1252) não mostra emojis
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "config.yaml"
ESTADO = RAIZ / "estado.json"
PAINEL = RAIZ / "painel.json"
CACHE_TELEMOVEL = RAIZ / ".cache_telemovel"
DIAS_BLOQUEADO = 30
FUSO_PT = ZoneInfo("Europe/Lisbon")
SITES_BLOQUEADOS = set()   # sites que recusaram a ligação nesta execução
SITES_LENTOS = set()       # sites que só demoraram demais (1 vez não é bloqueio)
SITES_DIRETOS_OK = set()   # sites lidos diretamente pelo GitHub, sem o telemóvel
LENTOS_PARA_BLOQUEIO = 3   # verificações seguidas a demorar demais = bloqueado
HORAS_TESTE_DIRETO = 24    # de quanto em quanto tempo um bloqueado volta a ser testado
LIDOS_TELEMOVEL = []       # fontes lidas a partir da cópia trazida pelo telemóvel
UA = "Mozilla/5.0 (compatible; AgregadorNoticias/1.0)"
UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
NIVEIS = ("alta", "media", "baixa")
DIAS_VISTOS = 14
DIAS_SUGESTAO = 14
MAX_MSG = 4000         # o Telegram aceita até 4096 caracteres por mensagem
PAUSA_ENVIO = 1        # o Telegram limita a ~1 mensagem por segundo no mesmo chat
MAX_BOTAO = 64         # tamanho máximo (bytes) dos dados de um botão do Telegram
# Definido em main() a partir dos segredos TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.
TELEGRAM = {"token": "", "chat": ""}


def erro(msg):
    """Mostra um erro. No GitHub Actions aparece também como anotação da execução."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::error::" + msg.replace("\n", " "))
    else:
        print("Erro: " + msg)


def segredos_em_falta():
    """Diz exatamente que segredos faltam (nunca mostra os valores)."""
    falta = [n for n, v in (("TELEGRAM_BOT_TOKEN", TELEGRAM["token"]),
                            ("TELEGRAM_CHAT_ID", TELEGRAM["chat"])) if not v]
    if not falta:
        return ""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return (f"falta(m) o(s) segredo(s) {' e '.join(falta)} no GitHub "
                "(Settings > Secrets and variables > Actions).")
    return (f"falta(m) {' e '.join(falta)}. No computador, define-as antes de correr, "
            "por exemplo no PowerShell: $env:TELEGRAM_BOT_TOKEN=\"123:ABC\"; "
            "$env:TELEGRAM_CHAT_ID=\"123456789\".")


DOMINIOS_IGNORADOS = {"", "news.google.com", "google.com"}


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


MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
         "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
         "dezembro": 12, "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def parse_data(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            return data_em_texto(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=FUSO_PT)  # datas sem fuso vêm de sites portugueses
    return d.astimezone(timezone.utc)


def data_em_texto(texto):
    """Encontra uma data escrita à portuguesa (09-10-2026, 9/10/2026, 9 de outubro de 2026)."""
    t = normalizar(texto)
    cands = []
    for m in re.finditer(r"\b(\d{4}) (\d{1,2}) (\d{1,2})\b", t):
        cands.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in re.finditer(r"\b(\d{1,2}) (\d{1,2}) (\d{4})\b", t):
        cands.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    for m in re.finditer(r"\b(\d{1,2}) (?:de )?([a-z]{3,9}) (?:de )?(\d{4})\b", t):
        if m.group(2) in MESES:
            cands.append((int(m.group(3)), MESES[m.group(2)], int(m.group(1))))
    for a, mes, dia in cands:
        if 2000 <= a <= 2100:
            try:
                # só o dia: conta desde a meia-noite (senão de manhã ficava "no futuro")
                return datetime(a, mes, dia, tzinfo=FUSO_PT).astimezone(timezone.utc)
            except ValueError:
                continue
    return None


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


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


# ------------------------------------------------------------------- recolha

class SiteInacessivel(RuntimeError):
    """O site não respondeu ou recusou a ligação (pode estar a bloquear o GitHub)."""


class SiteLento(SiteInacessivel):
    """O site demorou demasiado a responder (pode ser só lentidão passageira)."""


def notar_acesso(url, erro=None):
    """Regista como correu a ligação direta a um site, para decidir se precisa do
    telemóvel: recusa = bloqueado; demora = lento (só bloqueia à 3.ª seguida);
    lido sem o telemóvel = livre outra vez."""
    d = dominio_de(url)
    if not d or d in DOMINIOS_IGNORADOS:
        return
    if erro is None:
        if ficheiro_cache(url).exists():
            SITES_BLOQUEADOS.add(d)  # veio pelo telemóvel: continua a precisar dele
        else:
            SITES_DIRETOS_OK.add(d)
        return
    if isinstance(erro, requests.exceptions.SSLError):
        return  # certificado estragado: não é bloqueio, o telemóvel não ajuda
    if isinstance(erro, (requests.Timeout, SiteLento)):
        SITES_LENTOS.add(d)
    elif (isinstance(erro, (requests.ConnectionError, SiteInacessivel))
          or (isinstance(erro, requests.HTTPError) and erro.response is not None
              and erro.response.status_code in (403, 429, 451))):
        SITES_BLOQUEADOS.add(d)


def atualizar_bloqueados(estado, agora_utc):
    """Depois da verificação: junta os bloqueados novos, conta os lentos e liberta os
    que o GitHub conseguiu ler diretamente."""
    bloq, lentos = estado.setdefault("bloqueados", {}), estado.setdefault("lentos", {})
    for d in SITES_DIRETOS_OK - SITES_BLOQUEADOS:
        if d in bloq:
            print(f"O GitHub voltou a conseguir ler {d}: deixa de precisar do telemóvel.")
        bloq.pop(d, None)
        lentos.pop(d, None)
    for d in SITES_LENTOS - SITES_BLOQUEADOS - SITES_DIRETOS_OK:
        lentos[d] = int(lentos.get(d) or 0) + 1
        if lentos[d] >= LENTOS_PARA_BLOQUEIO:
            SITES_BLOQUEADOS.add(d)
    for d in SITES_BLOQUEADOS:  # da próxima vez, o telemóvel vai buscá-los
        bloq[d] = agora_utc.isoformat()
        lentos.pop(d, None)


class Resposta:
    """Página ou feed trazido pelo telemóvel, com a mesma forma da resposta do requests."""

    def __init__(self, url, conteudo):
        self.url, self.content, self.status_code, self.ok = url, conteudo, 200, True

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self):
        pass


def ficheiro_cache(url):
    return CACHE_TELEMOVEL / hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def obter(url, **kw):
    """requests.get, mas usa a cópia trazida pelo telemóvel quando ela existe."""
    f = ficheiro_cache(url)
    if f.exists():
        return Resposta(url, f.read_bytes())
    return requests.get(url, **kw)


def ler_feed(url, nome_fonte=None, timeout=20):
    """Lê um feed RSS ou Atom e devolve uma lista de notícias (dicionários)."""
    r = obter(url, headers={"User-Agent": UA}, timeout=timeout)
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


# ------------------------------------------------- páginas sem RSS (raspador)

LIXO = ("nav", "header", "footer", "aside", "form", "script", "style", "noscript",
        "iframe", "svg", "button", "select")
CAMINHO_NOTICIA = re.compile(
    r"(noticia|news|artigo|article|comunicad|imprensa|destaque|agenda|evento|post|"
    r"/20\d\d/|\d{3,}|[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+)", re.I)
CAMINHO_LIXO = re.compile(
    r"(/tag/|/tags/|/categoria|/category|/autor|/author|/page/|/pagina/|login|registo|"
    r"contact|contato|contacto|privacidade|privacy|cookies|mapa-do-site|sitemap|"
    r"\.(jpg|jpeg|png|gif|webp|pdf|zip|docx?|xlsx?)$)", re.I)
CONTENTOR = re.compile(r"(article|noticia|news|post|item|card|entry|destaque|blog|teaser)",
                       re.I)


def baixar_pagina(url):
    try:
        r = obter(url, headers={"User-Agent": UA_NAVEGADOR,
                                "Accept-Language": "pt-PT,pt;q=0.9"}, timeout=20)
    except requests.exceptions.SSLError:
        raise RuntimeError("o certificado de segurança do site é inválido ou está "
                           "incompleto; o site não pode ser lido em segurança. Procura "
                           "um feed RSS do site ou retira-o da lista") from None
    except requests.exceptions.Timeout:
        raise SiteLento("o site demorou demasiado a responder") from None
    except requests.RequestException:
        raise SiteInacessivel("não consegui ligar ao site (endereço errado, site em baixo "
                              "ou a bloquear o GitHub)") from None
    if r.status_code in (403, 429, 451):
        raise SiteInacessivel(f"o site recusou o acesso (erro {r.status_code}); pode estar a "
                              "bloquear o GitHub")
    if r.status_code >= 400:
        raise RuntimeError(f"o site respondeu com erro {r.status_code} "
                           "(página inexistente ou acesso recusado)")
    sopa = BeautifulSoup(r.content, "html.parser")
    corpo = sopa.body
    if corpo is not None and len(texto_de(corpo)) < 200 and (
            sopa.find(id=re.compile(r"^(root|app|__next|__nuxt)$")) or sopa.find("noscript")):
        raise RuntimeError("esta página só mostra o conteúdo com JavaScript e não pode ser "
                           "lida; procura um feed RSS do site ou outra página de notícias")
    return r.url, sopa


def texto_de(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


CABECALHOS = ["h1", "h2", "h3", "h4", "h5"]
ALT_GENERICO = re.compile(
    r"^(foto|fotografia|imagem|image|img|logo|banner|thumbnail|miniatura)\b|page-\d+|"
    r"\.(jpe?g|png|gif|webp)$|_\d+$|^\S+$", re.I)


def _texto_do_link(a):
    """Texto do link sem os parágrafos de resumo; se tiver cabeçalhos, o principal."""
    hs = [h for h in a.find_all(CABECALHOS) if len(texto_de(h)) >= 15]
    if hs:
        return texto_de(min(hs, key=lambda h: h.name))  # h1 antes de h2 (autor/rubrica)
    partes = []
    for s in a.find_all(string=True):
        p = s.find_parent("p")
        if p is not None and p.find_parent("a") is a:
            continue
        partes.append(s.strip())
    t = re.sub(r"\s+", " ", " ".join(partes)).strip()
    return re.sub(r"[\s\\/|·–—-]+$", "", t)


def titulo_do_link(a):
    """Devolve (título, forte). Forte quando vem do texto do link ou de um cabeçalho do
    cartão; fraco quando vem do 'alt' de uma imagem (link que só tem imagem)."""
    t = _texto_do_link(a)
    if len(t) >= 15:
        return t, True
    pai = a.parent
    for _ in range(4):  # link-imagem: procura o título no cartão à volta
        if pai is None or pai.name in ("body", "html"):
            break
        hs = pai.find_all(CABECALHOS)
        if len(hs) > 1:
            break  # já é a listagem inteira, não o cartão
        if hs and len(texto_de(hs[0])) >= 15:
            return texto_de(hs[0]), True
        pai = pai.parent
    img = a.find("img")
    for cand in (a.get("title"), a.get("aria-label"), img.get("alt") if img else None):
        cand = (cand or "").strip()
        if len(cand) >= 15 and not ALT_GENERICO.search(cand):
            return cand, False
    return t, False


def contentor_de(a):
    el = a
    for _ in range(5):
        el = el.parent
        if el is None or el.name in ("body", "html"):
            return a.parent
        if el.name in ("article", "li") or CONTENTOR.search(" ".join(el.get("class") or [])):
            return el
    return a.parent


def data_do_bloco(bloco):
    """Procura a data no cartão da notícia, subindo até ao cartão inteiro."""
    el = bloco
    for _ in range(4):
        if el is None or el.name in ("body", "html"):
            return None
        if len(el.find_all(["h1", "h2", "h3", "h4"])) > 1:
            return None  # já apanha outras notícias
        d = _data_em(el)
        if d:
            return d
        el = el.parent
    return None


def _data_em(bloco):
    t = bloco.find("time")
    if t:
        d = parse_data(t.get("datetime") or texto_de(t))
        if d:
            return d
    for el in bloco.find_all(attrs={"class": re.compile(r"(date|data|time|publish)", re.I)}):
        d = parse_data(el.get("datetime") or el.get("content") or texto_de(el))
        if d:
            return d
    return data_em_texto(texto_de(bloco)[:400])


def _sel(bloco, css):
    try:
        return bloco.select_one(css) if css else None
    except Exception:
        return None


def raspar_com_seletores(sopa, base, cfg_pagina):
    itens = []
    try:
        blocos = sopa.select(cfg_pagina["item"])
    except Exception as e:
        raise ValueError(f"seletor 'item' inválido: {e}") from None
    for b in blocos:
        el_t = _sel(b, cfg_pagina.get("titulo")) or b.find(["h1", "h2", "h3", "h4"]) or b
        a = el_t if el_t.name == "a" else (el_t.find("a", href=True) or b.find("a", href=True))
        if b.name == "a" and b.get("href"):
            a = b
        if not a or not a.get("href") or a["href"].strip().startswith(
                ("#", "javascript:", "mailto:", "tel:")):
            continue
        titulo = texto_de(el_t) if el_t is not b else titulo_do_link(a)[0]
        if len(titulo) < 15:
            titulo = titulo_do_link(a)[0]
        el_r = _sel(b, cfg_pagina.get("resumo"))
        el_d = _sel(b, cfg_pagina.get("data"))
        data = None
        if el_d is not None:
            data = parse_data(el_d.get("datetime") or el_d.get("content") or texto_de(el_d))
        itens.append({"titulo": titulo, "link": urljoin(base, a["href"]),
                      "resumo": texto_de(el_r) if el_r else "",
                      "data": data or data_do_bloco(b)})
    return itens


def raspar_automatico(sopa, base):
    """Sem seletores: escolhe os links que parecem notícias."""
    for tag in sopa.find_all(LIXO):
        if tag.name in ("header", "footer") and tag.find_parent(["article", "li"]):
            continue  # cabeçalho de um cartão de notícia, não da página
        if tag.name == "form" and len(tag.find_all("a", limit=11)) > 10:
            continue  # sites ASP.NET põem a página inteira dentro de um <form>
        if not tag.decomposed:
            tag.decompose()
    dominio_base = dominio_de(base)
    caminho_base = urlparse(base).path.rstrip("/")
    por_url, cands = {}, []
    for a in sopa.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base, href).split("#")[0]
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            continue
        d = dominio_de(url)
        if d != dominio_base and not d.endswith("." + dominio_base):
            continue
        caminho = p.path.rstrip("/")
        if not caminho or caminho == caminho_base or CAMINHO_LIXO.search(url):
            continue
        titulo, forte = titulo_do_link(a)
        if len(titulo) < 20 or len(titulo.split()) < 4:
            continue
        if url in por_url:
            # o mesmo link aparece na imagem e no título: fica o título a sério
            anterior = por_url[url]
            if forte and not anterior["forte"]:
                anterior.update(titulo=titulo, forte=True)
            continue
        bloco = contentor_de(a)
        pontos = 0
        if CAMINHO_NOTICIA.search(caminho):
            pontos += 2
        if caminho_base and caminho.startswith(caminho_base + "/"):
            pontos += 2
        if bloco is not None and bloco.name != "body" and (
                bloco.name == "article" or CONTENTOR.search(" ".join(bloco.get("class") or []))):
            pontos += 2
        if a.find_parent(["h1", "h2", "h3", "h4"]) or a.find(["h1", "h2", "h3", "h4"]):
            pontos += 1
        if caminho.count("/") >= 2:
            pontos += 1
        if pontos < 3:
            continue
        resumo = texto_de(bloco).replace(titulo, "").strip()[:300] if bloco else ""
        assinatura = (bloco.name + "." + ".".join(sorted(bloco.get("class") or []))
                      if bloco is not None else "")
        por_url[url] = {"titulo": titulo, "link": url, "resumo": resumo, "forte": forte,
                        "data": data_do_bloco(bloco), "assinatura": assinatura,
                        "pontos": pontos}
        cands.append(por_url[url])
    # as notícias de uma listagem partilham o mesmo tipo de cartão; os menus não
    grupos = {}
    for c in cands:
        grupos.setdefault(c["assinatura"], []).append(c)
    bons = [g for g in grupos.values() if len(g) >= 3]
    if not bons:
        return cands
    # o grupo que mais parece notícias (em média), e só depois o maior
    return max(bons, key=lambda g: (round(sum(c["pontos"] for c in g) / len(g)), len(g)))


def ler_pagina(cfg_pagina, nome_fonte=None):
    """Lê uma página de notícias sem RSS e devolve notícias no mesmo formato dos feeds."""
    base, sopa = baixar_pagina(cfg_pagina["url"])
    if not cfg_pagina.get("item") and cfg_pagina.get("usar_feed", True):
        # a página anuncia um feed escondido? é mais fiável do que ler o HTML
        for link in sopa.find_all("link", href=True,
                                  type=re.compile(r"application/(rss|atom)\+xml", re.I)):
            feed = urljoin(base, link["href"])
            if FEED_LIXO.search(feed):
                continue
            try:
                itens = ler_feed(feed, nome_fonte or cfg_pagina.get("nome"))
            except Exception:
                continue
            if itens:
                for it in itens:
                    it["local"] = bool(cfg_pagina.get("local"))
                    it["via_feed"] = feed
                return itens[: int(cfg_pagina.get("max", 30))]
    if cfg_pagina.get("item"):
        brutos = raspar_com_seletores(sopa, base, cfg_pagina)
    else:
        brutos = raspar_automatico(sopa, base)
    dominio = dominio_de(base)
    nome = nome_fonte or cfg_pagina.get("nome") or dominio
    itens, vistos = [], set()
    for b in brutos:
        if b["link"] in vistos or not b["titulo"]:
            continue
        vistos.add(b["link"])
        itens.append({"titulo": b["titulo"], "resumo": b["resumo"], "link": b["link"],
                      "data": b["data"], "dominio": dominio, "fonte": nome, "site": base,
                      "pagina": cfg_pagina["url"], "local": bool(cfg_pagina.get("local"))})
    return itens[: int(cfg_pagina.get("max", 30))]


def datar_raspadas(itens, estado, agora_utc):
    """Notícias de páginas sem data ficam com a data da 1.ª vez que foram vistas.
    Na 1.ª leitura de uma página, o que já lá estava conta como antigo, para não
    enviar o arquivo todo de uma vez."""
    vistas = estado.setdefault("raspadas", {})
    lidas = estado.setdefault("paginas_lidas", [])
    agora = agora_utc.isoformat()
    antigo = (agora_utc - timedelta(days=365)).isoformat()
    amanha = agora_utc + timedelta(days=1)
    for it in itens:
        if it.get("pagina") and it["data"] and it["data"] > amanha:
            it["data"] = None  # data de um evento futuro tirada do texto, não da publicação
        if not it.get("pagina") or it["data"]:
            continue
        reg = vistas.get(it["link"])
        if not isinstance(reg, dict):
            reg = {"primeira": agora if it["pagina"] in lidas else antigo}
            vistas[it["link"]] = reg
        reg["ultima"] = agora  # a limpeza conta a partir daqui, não da 1.ª vez
        it["data"] = parse_data(reg["primeira"])
    for p in {it["pagina"] for it in itens if it.get("pagina")}:
        if p not in lidas:
            lidas.append(p)


def ler_feed_local(url, nome_fonte=None):
    itens = ler_feed(url, nome_fonte)
    for it in itens:
        it["local"] = True
    return itens


def url_google_news(consulta, cfg):
    g = (cfg.get("geral") or {}).get("google_news") or {}
    return ("https://news.google.com/rss/search?q=" + quote_plus(consulta)
            + f"&hl={g.get('hl', 'pt-PT')}&gl={g.get('gl', 'PT')}"
            + f"&ceid={g.get('ceid', 'PT:pt-150')}")


def sem_repetidas(gerais, da_pesquisa):
    """Junta as fontes gerais e as da pesquisa, cada endereço uma só vez. Se o mesmo
    endereço está nas duas, valem as opções da pesquisa (ex.: local: true)."""
    por_url = {}
    for f in list(gerais or []) + list(da_pesquisa or []):
        if isinstance(f, dict) and f.get("url"):
            por_url[f["url"].strip().rstrip("/").lower()] = f  # a última ganha, no mesmo lugar
    return list(por_url.values())


def recolher(pesq, cfg, falhas=None):
    """Vai buscar as notícias de todas as fontes desta pesquisa."""
    fontes = cfg.get("fontes") or {}
    pedidos = []
    if pesq.get("consulta"):
        pedidos.append(("Google Notícias", ler_feed, url_google_news(pesq["consulta"], cfg)))
    for f in sem_repetidas(fontes.get("feeds"), pesq.get("feeds_extra")):
        pedidos.append((f.get("nome"), ler_feed_local if f.get("local") else ler_feed,
                        f["url"]))
    for p in sem_repetidas(fontes.get("paginas"), pesq.get("paginas_extra")):
        pedidos.append((p.get("nome"), ler_pagina, p))
    todas = []
    for nome, leitor, alvo in pedidos:
        url = alvo if isinstance(alvo, str) else alvo["url"]
        pelo_telemovel = ficheiro_cache(url).exists()
        try:
            itens = leitor(alvo, nome)
            for it in itens:  # sem data: fica com a da 1.ª vez vista (datar_raspadas)
                if not it["data"]:
                    it.setdefault("pagina", url)
            print(f"  fonte '{nome}': {len(itens)} notícias"
                  + (" (trazidas pelo telemóvel)" if pelo_telemovel else ""))
            if pelo_telemovel:
                LIDOS_TELEMOVEL.append(nome)
            notar_acesso(url)
            todas += itens
        except Exception as e:  # uma fonte em baixo não pára as outras
            print(f"  aviso: falhou '{nome}' ({type(e).__name__}: {str(e)[:80]})")
            if falhas is not None:
                falhas.append(f"{pesq['nome']} · {nome}: {type(e).__name__}: {str(e)[:120]}")
            notar_acesso(url, e)
    return todas


# ---------------------------------------------------------------- pontuação

def contem(chave_norm, texto_norm):
    # palavras curtas (ex.: "ia") só valem inteiras; as outras aceitam plurais
    chave = f" {chave_norm} " if len(chave_norm) <= 3 else f" {chave_norm}"
    return chave in texto_norm


# Plurais comuns em português -> singular (só na última palavra da expressão). Como a
# comparação aceita palavras que começam pela chave, o singular apanha os dois:
# "candidaturas" passa a apanhar também "candidatura", "agricultores" apanha "agricultor".
PLURAIS = (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("res", "r"), ("zes", "z"),
           ("ns", "m"), ("s", ""))


def singular(chave_norm):
    *antes, ultima = chave_norm.split(" ")
    if len(ultima) <= 4:
        return chave_norm
    for fim, novo in PLURAIS:
        if ultima.endswith(fim):
            return " ".join(antes + [ultima[: -len(fim)] + novo])
    return chave_norm


def variantes(entrada):
    """Uma palavra-chave pode juntar variantes do mesmo conceito separadas por "/":
    "regulação / regulamento / regulamentação". Devolve [(texto original, normalizado)],
    já com o singular de cada plural."""
    out = []
    for v in str(entrada or "").split("/"):
        vn = normalizar(v)
        for x in (vn, singular(vn)):
            if x and all(x != n for _, n in out):
                out.append((v.strip(), x))
    return out


def achar(entrada, *textos):
    """Índice do primeiro texto onde aparece alguma variante, e a variante; ou (None, None)."""
    vs = variantes(entrada)
    for i, t in enumerate(textos):
        for orig, vn in vs:
            if contem(vn, t):
                return i, orig
    return None, None


def pontos_palavras(item, pesq, pesos):
    """Devolve (pontos, palavras encontradas), ou None se tem palavra de exclusão
    ou lhe falta uma palavra obrigatória."""
    titulo = " " + normalizar(item["titulo"]) + " "
    texto = " " + normalizar(item["resumo"]) + " "
    for x in pesq.get("excluir") or []:
        # excluir é à palavra inteira (cada variante separada por "/")
        for xv in str(x).split("/"):
            xn = normalizar(xv)
            if xn and (f" {xn} " in titulo or f" {xn} " in texto):
                return None
    for o in [] if item.get("local") else pesq.get("obrigatorias") or []:
        # fontes "local" já são do sítio: dispensam as obrigatórias; numa obrigatória com
        # variantes ("sertã / sertanense") basta uma delas
        if variantes(o) and achar(o, titulo, texto)[0] is None:
            return None
    total = 0
    achadas = {n: [] for n in NIVEIS}
    for nivel in NIVEIS:
        for p in (pesq.get("palavras") or {}).get(nivel) or []:
            # as variantes do mesmo conceito contam uma só vez (no título, o dobro)
            onde, qual = achar(p, titulo, texto)
            if onde is None:
                continue
            total += pesos["pontos"][nivel] * (2 if onde == 0 else 1)
            achadas[nivel].append(qual)
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
    datar_raspadas(itens, estado, agora_utc)
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
        melhor, melhor_nota, melhor_conf = None, -1, False
        for i in g["itens"]:
            b = bonus
            if i["data"] and timedelta(0) <= agora_utc - i["data"] < timedelta(hours=1):
                b += pesos["bonus_ultima_hora"]
            confiavel = dominio_em(i["dominio"], fontes.get("confiaveis"))
            peso = pesos["fonte_confiavel"] if confiavel else pesos["fonte_desconhecida"]
            nota = (i["kw"] + b) * peso
            if nota > melhor_nota:
                melhor, melhor_nota, melhor_conf = i, nota, confiavel
        ids = [id_de(pesq["nome"], i["titulo"]) for i in g["itens"]]
        if any(x in estado["vistos"] for x in ids):
            continue
        if melhor_nota >= pesq["limite_alerta"]:
            nivel = "alerta"
        elif melhor_nota >= pesq["limite_resumo"]:
            nivel = "resumo"
        else:
            continue
        candidatos.append({
            "titulo": melhor["titulo"], "link": melhor["link"], "dominio": melhor["dominio"],
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
            "sugeridas": {}, "sugeridas_antigas": [], "dominios": {},
            "ultima_descoberta": "", "enviados": [], "execucoes": [], "bloqueados": {}, "lentos": {}, "testes_diretos": {},
            "ultima_pesquisa": {}, "vigiadas": {}}
    if ESTADO.exists():
        try:
            base.update(json.loads(ESTADO.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print("Aviso: estado.json inválido, a recomeçar do zero.")
    return base


def carregar_descartados():
    """Ids das notícias que descartaste no painel (ficheiro painel.json, gravado por ele)."""
    try:
        dados = json.loads(PAINEL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    lista = dados.get("descartados") if isinstance(dados, dict) else None
    if not isinstance(lista, list):
        return set()
    out = set()
    for x in lista:
        i = x.get("id") if isinstance(x, dict) else x
        if isinstance(i, (str, int)) and str(i):
            out.add(str(i))
    return out


def aplicar_descartados(estado):
    descartados = carregar_descartados()
    if not descartados:
        return
    antes = len(estado["adiados"]) + len(estado["resumo"])
    for k in ("adiados", "resumo"):
        estado[k] = [c for c in estado[k] if not descartados.intersection(c.get("ids") or [])]
    tirados = antes - len(estado["adiados"]) - len(estado["resumo"])
    if tirados:
        print(f"Descartadas no painel: {tirados} notícias tiradas dos adiados/resumo.")


def esquecer_pesquisas_apagadas(cfg, estado):
    """Quando apagas uma pesquisa, o que ela deixou no estado deixa de contar."""
    nomes = {p.get("nome") for p in cfg.get("pesquisas") or []}
    if not nomes:
        return
    for k in ("adiados", "resumo"):
        estado[k] = [c for c in estado[k] if c.get("pesquisa") in nomes]
    for d, r in list(estado.get("dominios", {}).items()):
        r["pesquisas"] = [p for p in r.get("pesquisas", []) if p in nomes]
        if not r["pesquisas"]:
            del estado["dominios"][d]
    for d, s in list(estado["sugeridas"].items()):
        if not any(p in nomes for p in s.get("pesquisas", [])):
            del estado["sugeridas"][d]
    estado["ultima_pesquisa"] = {n: t for n, t in estado.get("ultima_pesquisa", {}).items()
                                 if n in nomes}


def pesquisa_devida(pesq, estado, agora_utc):
    """Nas execuções automáticas, cada pesquisa só é verificada quando passou a sua
    frequência; os pedidos manuais (painel, /verificar) verificam todas."""
    if not execucao_automatica():
        return True
    try:
        ultima = datetime.fromisoformat(estado["ultima_pesquisa"][pesq["nome"]])
    except (KeyError, TypeError, ValueError):
        return True
    # 2,5 min de folga: o despertador não acorda ao segundo
    return (agora_utc - ultima).total_seconds() / 60 >= FREQUENCIAS[frequencia(pesq)] - 2.5


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
    limite_bloq = agora_utc - timedelta(days=DIAS_BLOQUEADO)
    estado["bloqueados"] = {d: ts for d, ts in estado.get("bloqueados", {}).items()
                            if (parse_data(ts) or agora_utc) > limite_bloq}
    limite_rasp = agora_utc - timedelta(days=180)
    estado["raspadas"] = {k: v for k, v in estado.get("raspadas", {}).items()
                          if isinstance(v, dict)
                          and (parse_data(v.get("ultima")) or agora_utc) > limite_rasp}
    limite_sug = agora_utc - timedelta(days=DIAS_SUGESTAO)
    for d, s in list(estado["sugeridas"].items()):
        if (parse_data(s.get("em")) or agora_utc) < limite_sug:
            del estado["sugeridas"][d]  # sem decisão: não volta a ser sugerida
            if d not in estado["sugeridas_antigas"]:
                estado["sugeridas_antigas"].append(d)


# ---------------------------------------------------------------- Telegram

def _sem_segredos(texto):
    """Tira o token e o chat de qualquer texto que vá para logs públicos."""
    for segredo in (TELEGRAM["token"], TELEGRAM["chat"]):
        if segredo:
            texto = texto.replace(segredo, "***")
    return re.sub(r"bot\d+:[\w-]+", "bot***", texto)


def botao(texto, dados):
    """Botão do Telegram; None se os dados passarem o limite (ex.: domínio enorme)."""
    if len(dados.encode("utf-8")) > MAX_BOTAO:
        return None
    return {"text": texto, "callback_data": dados}


def teclado(*linhas):
    """Junta linhas de botões, sem os que ficaram de fora (None)."""
    linhas = [[b for b in linha if b] for linha in linhas]
    linhas = [l for l in linhas if l]
    return {"inline_keyboard": linhas} if linhas else None


def _pedir_envio(corpo):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM['token']}/sendMessage",
                          json=corpo, timeout=30)
    except requests.RequestException:
        raise RuntimeError("falha de rede ao contactar o Telegram") from None
    try:
        dados = r.json()
    except ValueError:
        dados = {}
    return r, dados


# Teclado fixo por baixo da conversa (os botões enviam o texto; o Worker do Cloudflare
# responde-lhes). Vai nas mensagens sem botões próprios, para aparecer sem /start.
TECLADO = {"keyboard": [[{"text": "📰 Resumo"}, {"text": "🔄 Verificar"}],
                        [{"text": "📊 Estado"}, {"text": "🗂 Fontes"}],
                        [{"text": "🖥 Painel"}]],
           "resize_keyboard": True, "is_persistent": True}


def enviar(texto, botoes=None):
    """Envia uma mensagem (HTML) pelo Telegram, com botões opcionais (sem eles, leva o
    teclado fixo)."""
    if segredos_em_falta():
        raise RuntimeError(segredos_em_falta())
    corpo = {"chat_id": TELEGRAM["chat"], "text": texto[:MAX_MSG], "parse_mode": "HTML",
             "disable_web_page_preview": True}
    corpo["reply_markup"] = botoes or TECLADO
    for _ in range(3):  # demasiadas mensagens seguidas (429): espera o que o Telegram pede
        r, dados = _pedir_envio(corpo)
        if r.status_code != 429:
            break
        time.sleep(min(int((dados.get("parameters") or {}).get("retry_after") or 5), 30))
    if r.status_code == 400 and "parse_mode" in corpo:
        # o Telegram recusou o HTML ou os botões: manda em texto simples, para esta notícia
        # não ficar presa nos adiados a bloquear todas as outras
        simples = html.unescape(re.sub(r"<[^>]+>", "", texto))[:MAX_MSG]
        r, dados = _pedir_envio({"chat_id": TELEGRAM["chat"], "text": simples,
                                 "disable_web_page_preview": True})
    if not (r.ok and dados.get("ok")):
        motivo = _sem_segredos(str(dados.get("description") or r.text[:120]))
        raise RuntimeError(f"Telegram respondeu {r.status_code}: {motivo}")
    time.sleep(PAUSA_ENVIO)


def juntar_mensagens(blocos, maximo=MAX_MSG):
    """Junta blocos de texto em poucas mensagens.
    Devolve [(texto, [índices dos blocos incluídos])]."""
    msgs = []
    for i, b in enumerate(blocos):
        if msgs and len(msgs[-1][0]) + 2 + len(b) <= maximo:
            msgs[-1] = (msgs[-1][0] + "\n\n" + b, msgs[-1][1] + [i])
        else:
            msgs.append((b[:maximo], [i]))
    return msgs


def h(texto):
    """Escapa texto para as mensagens em HTML do Telegram."""
    return html.escape(str(texto or ""), quote=True)


def ligacao(titulo, url):
    if re.match(r"https?://", url or ""):
        return f'<a href="{h(url)}">{h(titulo)}</a>'
    return h(titulo)


def formatar_alerta(c, agora_utc):
    estado_fonte = "confiável" if c["confiavel"] else "fonte nova"
    linhas = [f'🔔 <b>{ligacao(c["titulo"], c["link"])}</b>',
              f'{h(c["fonte"])} ({estado_fonte}) · {h(c["pesquisa"])}']
    palavras = [p for n in NIVEIS for p in c["achadas"].get(n) or []]
    if palavras:
        linhas.append("🔑 " + h(", ".join(palavras)))
    quando = ha_quanto_tempo(parse_data(c["data"]), agora_utc)
    extra = f' · {c["n_fontes"]} fontes' if c["n_fontes"] > 1 else ""
    linhas.append(f"🕒 {quando}{extra}")
    return "\n".join(linhas)


def botoes_alerta(c):
    """Decidir a fonte da notícia logo no alerta (o Worker grava no config.yaml)."""
    d = c.get("dominio") or ""
    if not d or d in DOMINIOS_IGNORADOS or ":" in d:  # com porta, o Worker não o aceita
        return None
    if c.get("confiavel"):
        return teclado([botao("🚫 Bloquear " + d, "f|b|" + d)])
    return teclado([botao("⭐ Confiável", "f|c|" + d), botao("🚫 Bloquear fonte", "f|b|" + d)])


def mensagens_resumo(itens):
    """Devolve [(texto, [notícias nessa mensagem])], com todas as notícias, pela ordem da
    nota interna; juntar_mensagens divide-as por várias mensagens se for preciso."""
    itens = sorted(itens, key=lambda c: c["nota"], reverse=True)
    blocos = [f'{n}. {ligacao(c["titulo"], c["link"])}\n'
              f'   {h(c["fonte"])} · {h(c["pesquisa"])}'
              for n, c in enumerate(itens, 1)]
    if blocos:
        n_txt = "1 notícia" if len(itens) == 1 else f"{len(itens)} notícias"
        blocos[0] = f"📰 <b>Resumo — {n_txt}</b>\n\n" + blocos[0]
    return [(t, [itens[i] for i in idx]) for t, idx in juntar_mensagens(blocos)]


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


def dominios_decididos(cfg):
    """Domínios que já classificaste no config.yaml."""
    f = cfg.get("fontes") or {}
    out = set()
    for lista in (f.get("confiaveis"), f.get("bloqueadas"), f.get("neutras")):
        for d in lista or []:
            d = str(d).lower().strip()
            out.add(d[4:] if d.startswith("www.") else d)
    for fd in (f.get("feeds") or []) + (f.get("paginas") or []):
        out.add(dominio_de(fd.get("url", "")))
    return out


def limpar_sugeridas(cfg, estado):
    """Esquece as sugestões que já decidiste no config.yaml."""
    decididos = dominios_decididos(cfg)
    for d in list(estado["sugeridas"]):
        if dominio_em(d, decididos):
            del estado["sugeridas"][d]


CAMINHOS_FEED = ("/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml",
                 "/feeds/posts/default")
FEED_LIXO = re.compile(r"(comments|comentarios|/wp-json|oembed)", re.I)


def feeds_anunciados(base, texto):
    """Feeds que a página anuncia: <link type=rss/atom> e links com rss/feed/atom."""
    texto = texto[:300000]
    out = []
    for tag in re.findall(r"<link\b[^>]*>", texto, flags=re.I):
        if re.search(r"type=[\"']application/(rss|atom)\+xml[\"']", tag, re.I):
            m = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.I)
            if m:
                out.append(urljoin(base, html.unescape(m.group(1))))
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"']*(?:rss|feed|atom)[^\"']*)[\"']",
                         texto, re.I):
        out.append(urljoin(base, html.unescape(m.group(1))))
    return [u for u in dict.fromkeys(out)
            if u.startswith("http") and not FEED_LIXO.search(u)]


def feed_valido(url):
    try:
        return len(ler_feed(url, timeout=10)) >= 1
    except Exception:
        return False


def descobrir_feed(site):
    """Procura o feed RSS/Atom de um site, mesmo que não esteja à vista: os que a página
    anuncia, os endereços habituais (WordPress, Blogger…) e o formato do Joomla."""
    if not site:
        return None
    try:
        r = requests.get(site, headers={"User-Agent": UA_NAVEGADOR}, timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return None
    p = urlparse(r.url)
    raiz = f"{p.scheme}://{p.netloc}"
    pagina = r.url.split("#")[0]
    candidatos = feeds_anunciados(r.url, r.text)
    candidatos.append(pagina + ("&" if "?" in pagina else "?") + "format=feed&type=rss")
    candidatos += [raiz + c for c in CAMINHOS_FEED]
    for url in list(dict.fromkeys(candidatos))[:10]:
        if feed_valido(url):
            return url
    return None


def procurar_feeds(texto, cfg, maximo=15):
    """Pesquisa um tema, vê que sites publicam sobre ele e procura o feed de cada um."""
    from concurrent.futures import ThreadPoolExecutor
    pesq = next((p for p in cfg.get("pesquisas") or []
                 if normalizar(p.get("nome")) == normalizar(texto)), None)
    consulta = (pesq or {}).get("consulta") or texto
    print(f"A pesquisar \"{consulta}\" no Google Notícias (últimos 30 dias)…")
    itens = ler_feed(url_google_news(consulta + " when:30d", cfg), "Google Notícias")
    if pesq:  # respeita as obrigatórias e as exclusões da pesquisa
        itens = [it for it in itens if pontos_palavras(it, pesq, cfg["pesos"]) is not None]
    sites = {}
    for it in itens:
        d = it["dominio"]
        if d in DOMINIOS_IGNORADOS:
            continue
        reg = sites.setdefault(d, {"nome": it["fonte"], "site": it["site"] or f"https://{d}",
                                   "n": 0})
        reg["n"] += 1
    escolhidos = sorted(sites.items(), key=lambda x: -x[1]["n"])[:maximo]
    if not escolhidos:
        print("Nenhum site encontrado para esta pesquisa.")
        return 1
    f = cfg.get("fontes") or {}
    ja_tens = {dominio_de(x.get("url", "")) for x in f.get("feeds") or []}
    for p in cfg.get("pesquisas") or []:
        ja_tens |= {dominio_de(x.get("url", "")) for x in p.get("feeds_extra") or []}
    print(f"A procurar o feed de {len(escolhidos)} sites…\n")
    with ThreadPoolExecutor(max_workers=8) as ex:
        feeds = list(ex.map(lambda x: descobrir_feed(x[1]["site"]), escolhidos))
    novos = []
    for (d, reg), feed in zip(escolhidos, feeds):
        if dominio_em(d, f.get("bloqueadas")):
            estado_txt = "bloqueada no config"
        elif dominio_em(d, ja_tens):
            estado_txt = "já está no config"
        elif feed:
            estado_txt = feed
            novos.append((reg["nome"], feed))
        else:
            estado_txt = "sem feed"
        print(f"{reg['n']:3} notícias · {reg['nome']} ({d})\n      {estado_txt}")
    if not novos:
        print("\nNão há feeds novos para juntar.")
        return 0
    destino = f'feeds_extra da pesquisa "{pesq["nome"]}"' if pesq else "fontes.feeds"
    print(f"\nPara os usar, cola em {destino} no config.yaml:\n")
    for nome, feed in novos:
        print(f'      - {{nome: "{nome.replace(chr(34), "")}", url: "{feed}"}}')
    print("\nDica: os feeds de sites nacionais (SAPO, Observador…) trazem notícias de tudo. "
          "As palavras-chave filtram-nas, mas para temas locais prefere os sites regionais "
          "e os que aparecem em mais notícias.")
    return 0


def descobrir(cfg, estado, agora_utc):
    """Procura fontes novas relevantes e devolve as sugestões a enviar."""
    desc = cfg.get("descoberta") or {}
    pesos = cfg["pesos"]
    for pesq in cfg.get("pesquisas") or []:
        if not pesq.get("ativa", True):
            continue
        consultas = [pesq["consulta"]] if pesq.get("consulta") else []
        consultas += [str(p).split("/")[0].strip() for p in  # 1.ª variante de cada
                      list((pesq.get("palavras") or {}).get("alta") or [])[:3]]
        for c in dict.fromkeys(consultas):
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

    decididos = dominios_decididos(cfg)
    pendentes = estado["sugeridas"]
    antigas = set(estado["sugeridas_antigas"])
    espaco = max(0, desc.get("max_pendentes", 10) - len(pendentes))
    limite = min(desc.get("max_sugestoes_por_dia", 5), espaco)
    minimo = desc.get("min_noticias", 2)
    cands = [(d, r) for d, r in estado["dominios"].items()
             if not dominio_em(d, decididos) and d not in pendentes and d not in antigas
             and len(r["ids"]) >= minimo]
    cands.sort(key=lambda x: len(x[1]["ids"]), reverse=True)
    novas = []
    for d, r in cands[:limite]:
        feed = descobrir_feed(r.get("site")) if desc.get("procurar_feeds", True) else None
        novas.append({"dominio": d, "nome": r["nome"], "n": len(r["ids"]),
                      "pesquisas": r["pesquisas"][:3], "exemplo": r["exemplo"],
                      "site": r.get("site", ""), "feed": feed,
                      "em": agora_utc.isoformat()})
    return novas


def texto_sugestao(s):
    nome = ligacao(s["nome"], s.get("site") or "")
    linhas = [f'🔎 <b>Fonte nova: {nome}</b> ({h(s["dominio"])})',
              f'Apareceu em {s["n"]} notícias relevantes · {h(", ".join(s["pesquisas"]))}',
              f'Exemplo: {h(s["exemplo"])}']
    linhas.append(f'📡 Feed: {h(s["feed"])}' if s["feed"] else
                  "📡 Sem feed próprio: continuo a vê-la pelo Google Notícias.")
    linhas.append("Escolhe abaixo (ou no painel, em Fontes).")
    return "\n".join(linhas)


def botoes_sugestao(s):
    """Confiável (junta também o feed), Neutra ou Bloquear; o Worker grava no config.yaml."""
    d = s["dominio"]
    if ":" in d:
        return None
    return teclado([botao("⭐ Confiável", "f|c|" + d), botao("😐 Neutra", "f|n|" + d),
                    botao("🚫 Bloquear", "f|b|" + d)])


# ---------------------------------------------------------------- execução

def executar(cfg, simular=False, forcar_fontes=False):
    geral = cfg.get("geral") or {}
    tz = ZoneInfo(geral.get("fuso", "Europe/Lisbon"))
    agora_utc = datetime.now(timezone.utc)
    agora = agora_utc.astimezone(tz)
    estado = carregar_estado()
    podar(estado, agora_utc)
    limpar_sugeridas(cfg, estado)
    esquecer_pesquisas_apagadas(cfg, estado)
    aplicar_descartados(estado)
    bloqueadas = (cfg.get("fontes") or {}).get("bloqueadas")
    for k in ("adiados", "resumo"):  # fontes bloqueadas depois de a notícia entrar na fila
        estado[k] = [c for c in estado[k] if not dominio_em(c.get("dominio", ""), bloqueadas)]

    if not simular and segredos_em_falta():
        erro(segredos_em_falta())
        return 1

    # registo desta execução, para o painel mostrar o que aconteceu
    registo = {"ts": agora_utc.isoformat(), "pesquisas": [], "falhas": [], "alertas": 0,
               "resumo": 0, "sugestoes": 0, "silencio": False, "erros": []}
    novos = []
    for pesq in cfg.get("pesquisas") or []:
        if not pesq.get("ativa", True):
            continue
        if not pesquisa_devida(pesq, estado, agora_utc):
            print(f"Pesquisa: {pesq['nome']} — ainda não é altura ({frequencia(pesq)})")
            continue
        estado["ultima_pesquisa"][pesq["nome"]] = agora_utc.isoformat()
        print(f"Pesquisa: {pesq['nome']}")
        itens = recolher(pesq, cfg, registo["falhas"])
        cands = avaliar(itens, pesq, cfg, estado, agora_utc)
        print(f"  {len(cands)} notícias relevantes")
        registo["pesquisas"].append({
            "nome": pesq["nome"], "recolhidas": len(itens), "relevantes": len(cands),
            "alertas": sum(1 for c in cands if c["nivel"] == "alerta")})
        novos += cands
    vigiar_paginas(cfg, estado, agora_utc, agora, registo, simular)
    if not simular:
        atualizar_bloqueados(estado, agora_utc)
    registo["pelo_telemovel"] = sorted(set(LIDOS_TELEMOVEL))
    registo["bloqueados"] = sorted(SITES_BLOQUEADOS)

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
    falhou = False

    if simular:
        for c in imediatos:
            print("\n[ALERTA]\n" + formatar_alerta(c, agora_utc))
        for c in para_resumo:
            print(f'\n[RESUMO] {c["titulo"]} ({c["fonte"]}) · {c["pesquisa"]}')
        for sg in sugestoes:
            print("\n[FONTE NOVA]\n" + texto_sugestao(sg))
        print(f"\nSimulação: {len(imediatos)} alertas, {len(para_resumo)} para o resumo, "
              f"{len(sugestoes)} fontes sugeridas.")
        return 0

    for c in para_resumo:
        c["ts"] = agora_utc.isoformat()
        estado["resumo"].append(c)
        marcar_visto(estado, c, agora_utc)

    silencio = em_silencio(agora.hour, geral.get("silencio") or {})
    fila, ids_na_fila = [], set()
    for c in sorted(estado["adiados"] + imediatos, key=lambda c: c["nota"], reverse=True):
        if not ids_na_fila.intersection(c["ids"]):
            fila.append(c)
            ids_na_fila.update(c["ids"])
    # tudo o que está na fila conta como visto: assim, se o envio falhar, a mesma
    # notícia não volta a entrar como nova na execução seguinte (fica só nos adiados)
    for c in fila:
        marcar_visto(estado, c, agora_utc)
    estado["adiados"] = []
    def registar_envio(c, tipo):
        estado["enviados"].append({
            "tipo": tipo, "ts": agora_utc.isoformat(), "titulo": c["titulo"],
            "link": c["link"], "fonte": c["fonte"], "nota": c["nota"],
            "pesquisa": c["pesquisa"]})

    def falha(msg):
        erro(msg)
        registo["erros"].append(msg)

    if silencio:
        registo["silencio"] = True
        estado["adiados"] = fila[:50]
        for c in fila[50:]:
            c["ts"] = agora_utc.isoformat()
            estado["resumo"].append(c)
        print(f"Horário de silêncio: {len(fila)} alertas guardados para mais tarde.")
    else:
        limite = geral.get("max_alertas_por_execucao", 5)
        a_enviar, excesso = fila[:limite], fila[limite:]
        for c in excesso:
            c["ts"] = agora_utc.isoformat()
            estado["resumo"].append(c)
        # uma mensagem por alerta, cada uma com os botões da sua fonte
        for i, c in enumerate(a_enviar):
            try:
                enviar(formatar_alerta(c, agora_utc), botoes_alerta(c))
                registar_envio(c, "alerta")
                registo["alertas"] += 1
            except RuntimeError as e:
                falha(f"não consegui enviar os alertas: {e}")
                falhou = True
                estado["adiados"] = a_enviar[i:]
                break

    # o resumo do dia sai na 1.ª verificação depois da hora_resumo; se nesse momento não
    # houver nada, o dia fica dado como tratado (senão o 1.º item que aparecesse à tarde
    # disparava logo o "resumo do dia")
    if (not falhou and not silencio and agora.hour >= geral.get("hora_resumo", 8)
            and estado["ultimo_resumo"] != hoje):
        total = len(estado["resumo"])
        try:
            for texto, itens_msg in mensagens_resumo(estado["resumo"]):
                enviar(texto)
                ids_msg = {i for c in itens_msg for i in c["ids"]}
                estado["resumo"] = [c for c in estado["resumo"]
                                    if not ids_msg.intersection(c["ids"])]
                for c in itens_msg:
                    registar_envio(c, "resumo")
            registo["resumo"] = total
            estado["resumo"] = []  # tudo seguiu
            estado["ultimo_resumo"] = hoje
        except RuntimeError as e:
            # o que já seguiu saiu da fila; o resto vai na verificação seguinte
            falha(f"não consegui enviar o resumo: {e}")
            falhou = True

    if sugestoes and not falhou:
        try:
            for sg in sugestoes:  # cada sugestão fica registada logo que a mensagem dela segue
                enviar(texto_sugestao(sg), botoes_sugestao(sg))
                estado["sugeridas"][sg["dominio"]] = sg
                registo["sugestoes"] += 1
        except RuntimeError as e:
            falha(f"não consegui enviar as sugestões de fontes: {e}")
            falhou = True
    if (forcar_fontes or devida) and not falhou:
        estado["ultima_descoberta"] = hoje

    estado["enviados"] = estado["enviados"][-100:]
    estado["execucoes"] = (estado["execucoes"] + [registo])[-48:]
    guardar_estado(estado)
    print("Concluído.")
    return 1 if falhou else 0


def testar_pagina(args):
    """Mostra o que o leitor de páginas extrai de um site, para afinar os seletores."""
    cfg_pagina = {"url": args.testar_pagina, "item": args.item, "titulo": args.titulo,
                  "resumo": args.resumo, "data": args.data, "usar_feed": not args.sem_feed}
    itens = ler_pagina(cfg_pagina)
    via_feed = itens[0].get("via_feed") if itens else None
    modo = ("feed RSS escondido" if via_feed else
            "seletores" if args.item else "deteção automática")
    print(f"{len(itens)} notícias encontradas ({modo}) em {args.testar_pagina}\n")
    for n, it in enumerate(itens, 1):
        quando = it["data"].strftime("%Y-%m-%d") if it["data"] else "sem data"
        print(f"{n:2}. {it['titulo']}\n    {quando} · {it['link']}")
    if via_feed:
        print(f"\nA página anuncia um feed ({via_feed}) e a app usa-o sozinha. "
              "Para ver a leitura da página em vez do feed, junta --sem-feed.")
        return 0
    feed = descobrir_feed(args.testar_pagina)
    if feed:
        print(f"\nNota: este site tem feed RSS ({feed}). É melhor pô-lo em fontes.feeds.")
    elif not itens:
        print("O que podes fazer:\n"
              "- confirma que o endereço é a página com a LISTA de notícias (não a página "
              "inicial nem uma notícia);\n"
              "- se o site carrega as notícias com JavaScript, não pode ser lido: procura "
              "outra página ou um feed RSS;\n"
              "- se no navegador vês as notícias, pede a alguém para indicar os seletores "
              "CSS (--item e --titulo) ou retira o site da lista.")
    return 0 if itens else 1


def todas_as_fontes(cfg):
    f = cfg.get("fontes") or {}
    out = list(f.get("feeds") or []) + list(f.get("paginas") or [])
    for p in cfg.get("pesquisas") or []:
        if p.get("ativa", True):
            out += list(p.get("feeds_extra") or []) + list(p.get("paginas_extra") or [])
    out += [dict(v, vigiar=True) for v in vigias(cfg)]
    return [x for x in out if x.get("url")]


def no_tailscale(*args):
    return subprocess.run(["sudo", "tailscale", *args], capture_output=True, text=True,
                          timeout=60)


def buscar_pelo_telemovel(cfg):
    """Antes da verificação: vai buscar, pela internet do telemóvel (Tailscale, saída
    'exit node'), os sites que recusam o GitHub. Guarda cópias que o agregador usa a
    seguir. Se o telemóvel não estiver disponível, não faz nada."""
    estado = carregar_estado()
    agora_utc = datetime.now(timezone.utc)
    bloqueados = list(estado.get("bloqueados") or {})
    alvo = [x for x in todas_as_fontes(cfg)
            if x.get("telemovel") or dominio_em(dominio_de(x["url"]), bloqueados)]
    # uma vez por dia, cada site bloqueado fica de fora do telemóvel: a verificação tenta-o
    # diretamente e, se o GitHub já entrar, ele sai da lista dos bloqueados
    testes = estado.setdefault("testes_diretos", {})
    limite = agora_utc - timedelta(hours=HORAS_TESTE_DIRETO)
    a_testar = set()
    for x in alvo:
        d = dominio_de(x["url"])
        if not x.get("telemovel") and (parse_data(testes.get(d)) or limite) <= limite:
            a_testar.add(d)
    if a_testar:
        for d in a_testar:
            testes[d] = agora_utc.isoformat()
        estado["testes_diretos"] = {d: t for d, t in testes.items() if d in bloqueados}
        guardar_estado(estado)
        print("Teste diário: estes sites vão ser lidos diretamente pelo GitHub, para ver se "
              "ainda precisam do telemóvel: " + ", ".join(sorted(a_testar)))
        alvo = [x for x in alvo if dominio_de(x["url"]) not in a_testar]
    if not alvo:
        print("Nenhum site precisa do telemóvel.")
        return 0
    try:
        st = no_tailscale("status", "--json")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Tailscale indisponível ({type(e).__name__}).")
        return 0
    if st.returncode:
        print("Tailscale indisponível: " + st.stderr.strip()[:200])
        return 0
    pares = list((json.loads(st.stdout).get("Peer") or {}).values())
    saidas = [p for p in pares if p.get("ExitNodeOption") and p.get("Online")]
    if not saidas:
        print("O telemóvel não está disponível como saída. Estes sites ficam de fora desta vez.")
        if not pares:
            print("  Não vejo nenhum aparelho na rede Tailscale (confirma que o telemóvel usa a "
                  "mesma conta e que a política deixa a etiqueta tag:ci ver os aparelhos).")
        for p in pares:
            print(f"  aparelho '{p.get('HostName', '?')}' ({p.get('OS', '?')}): "
                  f"{'ligado' if p.get('Online') else 'DESLIGADO (abre a app e liga o Tailscale)'}, "
                  f"{'saída aprovada' if p.get('ExitNodeOption') else 'NÃO é saída (liga Run as exit node na app e aprova em Machines > Edit route settings > Use as exit node)'}")
        return 0
    ip, nome = saidas[0]["TailscaleIPs"][0], saidas[0].get("HostName", "?")
    r = no_tailscale("set", "--exit-node=" + ip)
    if r.returncode:
        print("Não consegui sair pelo telemóvel: " + r.stderr.strip()[:200])
        return 0
    print(f"A sair pela internet de '{nome}' para {len(alvo)} fonte(s)…")
    CACHE_TELEMOVEL.mkdir(exist_ok=True)
    try:
        time.sleep(3)
        trazidos = set()  # a mesma fonte pode estar em várias pesquisas: traz uma vez só
        for x in alvo:
            urls = [x["url"]]
            for i, url in enumerate(urls):
                if url in trazidos:
                    continue
                trazidos.add(url)
                try:
                    resp = requests.get(url, headers={"User-Agent": UA_NAVEGADOR,
                                                      "Accept-Language": "pt-PT,pt;q=0.9"},
                                        timeout=30)
                    resp.raise_for_status()
                except requests.RequestException as e:
                    print(f"  falhou pelo telemóvel: {x.get('nome') or url} ({type(e).__name__})")
                    continue
                ficheiro_cache(url).write_bytes(resp.content)
                print(f"  {x.get('nome') or url}: trazido ({len(resp.content) // 1024} KB)")
                if i == 0 and not x.get("item") and not x.get("vigiar"):  # páginas: traz também o feed que anunciem
                    urls += feeds_anunciados(resp.url, resp.text)[:2]
    finally:
        r = no_tailscale("set", "--exit-node=")
        if r.returncode:  # sem isto, o resto da execução sairia toda pelo telemóvel
            print("Não consegui deixar de sair pelo telemóvel; a desligar o Tailscale.")
            no_tailscale("down")
    return 0


# ------------------------------------------------ páginas vigiadas (mudanças)
# Secção "vigiar" do config.yaml (o painel preenche-a, no separador Páginas). Cada página:
#   nome, url, parte (opcional: seletor CSS; só essa parte da página conta),
#   frequencia ("urgente" 15 min, "hora", "diario" 1 vez por dia) e ativa.
# Compara só o texto visível, sem datas, horas nem "há 5 minutos", que mudam sozinhos.
FREQ_VIGIAR = {"urgente": 15, "hora": 60, "diario": 24 * 60}
MAX_TEXTO_VIGIADO = 30000   # caracteres guardados por página no estado.json
MAX_LINHAS_AVISO = 8        # linhas novas/retiradas mostradas na mensagem
FALHAS_PARA_AVISAR = 3      # avisa quando a página falha 3 vezes seguidas
_MESES_CURTOS = "jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez"
RUIDO = [re.compile(p, re.I) for p in (
    r"\b\d{1,2}[:h]\d{2}(:\d{2})?\b",                              # 14:05, 14h05
    r"\b\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}\b",                         # 03/11/2026, 2026-11-03
    r"\bh[aá]\s+(cerca\s+de\s+)?(\d+|um|uma)\s+\w+",                # há 5 minutos
    r"\b\d{1,2}\s+(de\s+)?(" + _MESES_CURTOS + r")[a-zç]*\.?(\s+(de\s+)?\d{4})?",  # 3 de nov 2026
    r"\b(" + _MESES_CURTOS + r")[a-zç]*\.?\s+\d{1,2},?\s+\d{4}",    # Nov 3, 2026
)]


def vigias(cfg, todas=False):
    out = []
    for v in cfg.get("vigiar") or []:
        if (isinstance(v, dict) and re.match(r"https?://", str(v.get("url") or ""))
                and (todas or v.get("ativa", True))):
            out.append(v)
    return out


def freq_vigia(v):
    f = str(v.get("frequencia") or "hora").strip().lower()
    return f if f in FREQ_VIGIAR else "hora"


def nome_vigia(v):
    return str(v.get("nome") or "").strip() or dominio_de(v["url"])


def parte_vigia(v):
    return str(v.get("parte") or "").strip()


def texto_vigiado(sopa, parte=""):
    """Linhas de texto visível da página (ou só da parte indicada)."""
    for el in sopa(["script", "style", "noscript", "template", "svg", "iframe"]):
        el.decompose()
    parte = str(parte or "").strip()
    if parte:
        try:
            alvo = sopa.select(parte)
        except Exception:
            raise RuntimeError(f"a parte '{parte}' não é um seletor CSS válido") from None
        if not alvo:
            raise RuntimeError(f"não encontrei a parte '{parte}' na página (o site pode ter "
                               "mudado o desenho; corrige ou apaga a parte no painel)")
    else:
        alvo = [sopa.body or sopa]
    linhas, total = [], 0
    for el in alvo:
        for linha in el.get_text("\n").split("\n"):
            linha = re.sub(r"\s+", " ", linha).strip()
            if linha and total < MAX_TEXTO_VIGIADO:
                linhas.append(linha)
                total += len(linha) + 1
    return linhas


def sem_ruido(linha):
    for r in RUIDO:
        linha = r.sub("#", linha)
    return linha


def diferencas(antigas, novas):
    """(linhas novas, linhas que saíram), ignorando datas/horas e linhas só mudadas de sítio."""
    a = [sem_ruido(x) for x in antigas]
    b = [sem_ruido(x) for x in novas]
    mais, menos = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            menos += [(a[i], antigas[i]) for i in range(i1, i2)]
        if tag in ("replace", "insert"):
            mais += [(b[j], novas[j]) for j in range(j1, j2)]
    chaves_mais, chaves_menos = {k for k, _ in mais}, {k for k, _ in menos}
    mais_f = [t for k, t in mais if k not in chaves_menos]    # mudou só de sítio, ou
    menos_f = [t for k, t in menos if k not in chaves_mais]   # só a data/hora mudou
    return mais_f, menos_f


def formatar_mudanca(v, mais, menos, agora):
    def bloco(simbolo, titulo, linhas):
        if not linhas:
            return []
        out = [f"{simbolo} <b>{titulo}</b>"]
        out += ["• " + h(x if len(x) <= 200 else x[:200] + "…") for x in linhas[:MAX_LINHAS_AVISO]]
        if len(linhas) > MAX_LINHAS_AVISO:
            out.append(f"<i>… e mais {len(linhas) - MAX_LINHAS_AVISO} linhas</i>")
        return out
    linhas = [f'🔎 <b>Mudou: {ligacao(nome_vigia(v), v["url"])}</b>']
    if parte_vigia(v):
        linhas.append(f"<i>só a parte {h(parte_vigia(v))}</i>")
    linhas += bloco("➕", "Novo", mais) + bloco("➖", "Saiu", menos)
    linhas.append("🕒 " + agora.strftime("%d/%m %H:%M"))
    return "\n".join(linhas)


def botao_abrir(url):
    return {"inline_keyboard": [[{"text": "🌐 Abrir a página", "url": url}]]}


def execucao_automatica():
    return (os.environ.get("GITHUB_EVENT_NAME") == "schedule"
            or os.environ.get("ACAO") == "agendada")


def vigia_devida(v, reg, agora_utc):
    """Nas execuções automáticas, só quando passou a frequência; nas manuais, sempre."""
    if not execucao_automatica():
        return True
    ultima = parse_data((reg or {}).get("verificado"))
    if not ultima:
        return True
    return (agora_utc - ultima).total_seconds() / 60 >= FREQ_VIGIAR[freq_vigia(v)] - 2.5


def vigiar_paginas(cfg, estado, agora_utc, agora, registo, simular=False):
    """Verifica as páginas vigiadas que já estão na altura e avisa do que mudou.
    No horário de silêncio não verifica: a mudança é apanhada (e avisada) a seguir."""
    paginas = vigias(cfg)
    urls = {v["url"] for v in vigias(cfg, todas=True)}
    regs = estado.setdefault("vigiadas", {})
    for u in list(regs):  # páginas apagadas no painel
        if u not in urls:
            del regs[u]
    if not paginas:
        return
    if not simular and em_silencio(agora.hour, (cfg.get("geral") or {}).get("silencio") or {}):
        print(f"Páginas vigiadas: horário de silêncio, ficam para depois ({len(paginas)}).")
        return
    resumo = {"verificadas": 0, "mudaram": 0, "falharam": 0}
    for v in paginas:
        url, nome, parte = v["url"], nome_vigia(v), parte_vigia(v)
        reg = dict(regs.get(url) or {})
        if reg.get("linhas") is not None and reg.get("parte", "") != parte:
            reg.pop("linhas")  # mudaste a parte vigiada: nova referência, sem aviso falso
        if not vigia_devida(v, reg, agora_utc):
            print(f"Página vigiada: {nome} — ainda não é altura ({freq_vigia(v)})")
            continue
        print(f"Página vigiada: {nome}")
        resumo["verificadas"] += 1
        try:
            _, sopa = baixar_pagina(url)
            novas = texto_vigiado(sopa, parte)
            if not novas:
                raise RuntimeError("a página (ou a parte vigiada) não tem texto")
            if ficheiro_cache(url).exists():
                LIDOS_TELEMOVEL.append(nome)
            notar_acesso(url)
        except Exception as e:  # uma página em baixo não pára as outras
            notar_acesso(url, e)
            motivo = str(e)[:200] or type(e).__name__
            print(f"  falhou: {motivo}")
            resumo["falharam"] += 1
            registo["falhas"].append(f"Página vigiada · {nome}: {motivo}")
            if simular:
                continue
            reg.update({"falhas": reg.get("falhas", 0) + 1, "erro": motivo,
                        "verificado": agora_utc.isoformat()})
            if reg["falhas"] == FALHAS_PARA_AVISAR:
                try:
                    enviar(f"⚠️ <b>Não consigo ler {ligacao(nome, url)}</b> "
                           f"({FALHAS_PARA_AVISAR} tentativas seguidas).\n{h(motivo)}",
                           botao_abrir(url))
                except RuntimeError as e2:
                    registo["erros"].append(f"não consegui avisar da falha em {nome}: {e2}")
            regs[url] = reg
            continue

        antigas = reg.get("linhas")
        mais, menos = ([], []) if antigas is None else diferencas(antigas, novas)
        if antigas is None:  # 1.ª vez: guarda a referência e confirma que está a funcionar
            so_parte = f" (só a parte {h(parte)})" if parte else ""
            texto = (f"👀 <b>Comecei a vigiar {ligacao(nome, url)}</b>\n"
                     f"{len(novas)} linhas de texto{so_parte}. Aviso-te quando alguma coisa mudar.")
        else:
            texto = formatar_mudanca(v, mais, menos, agora) if (mais or menos) else None
        if simular:
            print(f"  {len(novas)} linhas" + (f"\n[PÁGINA]\n{texto}" if texto else " · sem mudanças"))
            continue
        if texto:
            try:
                enviar(texto, botao_abrir(url))
            except RuntimeError as e:
                # não atualiza a referência: a mesma mudança é avisada na próxima vez
                registo["erros"].append(f"não consegui avisar da mudança em {nome}: {e}")
                continue
        if mais or menos:
            resumo["mudaram"] += 1
            reg["mudou"] = agora_utc.isoformat()
            reg["mudanca"] = {"mais": mais[:20], "menos": menos[:20],
                              "n_mais": len(mais), "n_menos": len(menos)}
            estado["enviados"].append({"tipo": "pagina", "ts": agora_utc.isoformat(),
                                       "titulo": "Mudou: " + nome, "link": url,
                                       "fonte": dominio_de(url), "nota": 0,
                                       "pesquisa": "Páginas vigiadas"})
            print(f"  MUDOU: +{len(mais)} / -{len(menos)} linhas")
        else:
            print(f"  {len(novas)} linhas · "
                  + ("referência guardada" if antigas is None else "sem mudanças"))
        reg.update({"linhas": novas, "verificado": agora_utc.isoformat(), "falhas": 0,
                    "erro": "", "parte": parte})
        reg.setdefault("desde", agora_utc.isoformat())
        regs[url] = reg
    registo["paginas"] = resumo


def testar_vigia(args):
    """Mostra o texto que a vigilância compara numa página (para escolher a parte)."""
    _, sopa = baixar_pagina(args.testar_vigia)
    linhas = texto_vigiado(sopa, args.parte)
    print(f"{len(linhas)} linhas de texto em {args.testar_vigia}"
          + (f" (parte {args.parte})" if args.parte else "") + "\n")
    for linha in linhas[:60]:
        print("  " + linha[:160])
    if len(linhas) > 60:
        print(f"  … e mais {len(linhas) - 60}")
    return 0


# As pesquisas (o painel preenche-as): "sitio", "assuntos", "excluir" e
# "frequencia". A notícia passa se falar do sítio E de pelo menos um dos assuntos.
# A frequência diz de quanto em quanto tempo a pesquisa é verificada e como avisa:
#   urgente: de 15 em 15 min, mensagem logo · hora: de hora a hora, mensagem logo ·
#   diario: de hora a hora (para não perder nada), tudo no resumo diário.
FREQUENCIAS = {"urgente": 15, "hora": 60, "diario": 60}


def frequencia(p):
    f = str(p.get("frequencia") or "hora").strip().lower()
    return f if f in FREQUENCIAS else "hora"


def consulta_google(entrada_ou_lista):
    """'Sertã / sertanense' -> 'Sertã OR sertanense' (expressões entre aspas)."""
    partes = []
    for e in entrada_ou_lista if isinstance(entrada_ou_lista, list) else [entrada_ou_lista]:
        for v in str(e or "").split("/"):
            v = v.strip()
            if v and v not in partes:
                partes.append(v)
    return " OR ".join(f'"{v}"' if " " in v else v for v in partes)


def preparar_pesquisa(p):
    """Traduz as 4 perguntas para as regras internas: obrigatórias (o sítio e, juntos, os
    assuntos), palavras que pontuam (os assuntos, ou o sítio), procura do Google Notícias e
    limites (tudo o que passa é alerta; em "diario" tudo vai para o resumo)."""
    if not isinstance(p, dict):
        return p
    sitio = str(p.get("sitio") or "").strip()
    assuntos = [str(a).strip() for a in p.get("assuntos") or [] if str(a).strip()]
    p["obrigatorias"] = ([sitio] if sitio else []) + ([" / ".join(assuntos)] if assuntos else [])
    p["palavras"] = {"alta": assuntos or ([sitio] if sitio else []), "media": [], "baixa": []}
    p["consulta"] = consulta_google(sitio or assuntos)
    p["limite_resumo"] = 1
    p["limite_alerta"] = 10 ** 9 if frequencia(p) == "diario" else 1
    return p


def carregar_config():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for p in cfg.get("pesquisas") or []:
        preparar_pesquisa(p)
    return cfg


def motivo_corte(item, pesq):
    """Porque é que uma notícia não passou nos filtros (para o Experimentar)."""
    titulo = " " + normalizar(item["titulo"]) + " "
    texto = " " + normalizar(item["resumo"]) + " "
    for x in pesq.get("excluir") or []:
        for xv in str(x).split("/"):
            xn = normalizar(xv)
            if xn and (f" {xn} " in titulo or f" {xn} " in texto):
                return "excluida"
    obrig = [] if item.get("local") else pesq.get("obrigatorias") or []
    for i, o in enumerate(obrig):
        if variantes(o) and achar(o, titulo, texto)[0] is None:
            return "sem_sitio" if (i == 0 and pesq.get("sitio")) else "sem_assunto"
    return "sem_assunto"


def experimentar(cfg):
    """Corre uma pesquisa (vinda do painel, em PESQUISA) sem enviar nem guardar nada, e
    escreve o resultado em experimentar.json para o painel mostrar."""
    pedido = json.loads(os.environ.get("PESQUISA") or "{}")
    pesq = preparar_pesquisa(dict(pedido, nome=pedido.get("nome") or "Experiência"))
    agora_utc = datetime.now(timezone.utc)
    estado = carregar_estado()
    estado["vistos"] = {}  # mostra tudo o que passa, mesmo o que já foi enviado
    idade_max = timedelta(hours=(cfg.get("geral") or {}).get("idade_max_horas", 48))
    bloqueadas = (cfg.get("fontes") or {}).get("bloqueadas")
    print(f"Experimentar: {pesq['nome']} (Google Notícias: {pesq.get('consulta')})")
    falhas = []
    itens = recolher(pesq, cfg, falhas)
    cands = avaliar(itens, pesq, cfg, estado, agora_utc)
    cortes = {"sem_sitio": 0, "sem_assunto": 0, "excluida": 0, "antiga": 0}
    exemplos = {k: [] for k in cortes}
    passaram = {i for c in cands for i in c["ids"]}
    vistos_tit = set()
    for it in itens:
        if dominio_em(it["dominio"], bloqueadas):
            continue
        if id_de(pesq["nome"], it["titulo"]) in passaram or normalizar(it["titulo"]) in vistos_tit:
            continue
        vistos_tit.add(normalizar(it["titulo"]))
        if it["data"] and agora_utc - it["data"] > idade_max:
            m = "antiga"
        else:
            m = motivo_corte(it, pesq)
        cortes[m] += 1
        if len(exemplos[m]) < 5:
            exemplos[m].append({"titulo": it["titulo"], "link": it["link"], "fonte": it["fonte"]})
    res = {
        "pedido": pedido.get("pedido", ""), "ts": agora_utc.isoformat(),
        "nome": pesq["nome"], "consulta": pesq.get("consulta", ""),
        "recolhidas": len(itens), "idade_max_horas": idade_max.total_seconds() / 3600,
        "passam": [{k: c[k] for k in ("titulo", "link", "fonte", "nivel", "achadas", "data")}
                   for c in cands[:40]],
        "n_passam": len(cands), "cortes": cortes, "exemplos": exemplos, "falhas": falhas,
    }
    with open("experimentar.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"Passam {len(cands)}; cortadas: {cortes}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Agregador de Notícias")
    ap.add_argument("--simular", action="store_true", help="não envia nem guarda nada")
    ap.add_argument("--teste", action="store_true", help="envia uma mensagem de teste")
    ap.add_argument("--experimentar", action="store_true",
                    help="(painel) corre a pesquisa em PESQUISA e grava experimentar.json")
    ap.add_argument("--fontes", action="store_true", help="procura fontes novas agora")
    ap.add_argument("--testar-pagina", metavar="URL", help="testa o leitor de páginas")
    ap.add_argument("--item", help="seletor CSS de cada notícia (com --testar-pagina)")
    ap.add_argument("--titulo", help="seletor CSS do título, dentro do item")
    ap.add_argument("--resumo", help="seletor CSS do resumo, dentro do item")
    ap.add_argument("--data", help="seletor CSS da data, dentro do item")
    ap.add_argument("--sem-feed", action="store_true",
                    help="com --testar-pagina: lê a página mesmo que tenha feed")
    ap.add_argument("--testar-vigia", metavar="URL",
                    help="mostra o texto que a vigilância de páginas compara nesta página")
    ap.add_argument("--parte", help="com --testar-vigia: seletor CSS da parte a vigiar")
    ap.add_argument("--procurar-feeds", metavar="PESQUISA",
                    help="procura os feeds RSS (mesmo escondidos) dos sites que publicam "
                         "sobre um tema ou uma pesquisa do config.yaml")
    ap.add_argument("--buscar-pelo-telemovel", action="store_true",
                    help="(GitHub) traz pelo telemóvel os sites que bloqueiam o GitHub")
    args = ap.parse_args()

    TELEGRAM["token"] = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM["chat"] = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    try:
        if args.testar_pagina:
            return testar_pagina(args)
        if args.testar_vigia:
            return testar_vigia(args)
        if args.experimentar:
            return experimentar(carregar_config())
        if args.buscar_pelo_telemovel:
            return buscar_pelo_telemovel(carregar_config())
        if args.procurar_feeds:
            return procurar_feeds(args.procurar_feeds, carregar_config())
        if args.teste:
            enviar("✅ O agregador de notícias está ligado ao Telegram.")
            print("Mensagem de teste enviada.")
            return 0
        return executar(carregar_config(), simular=args.simular, forcar_fontes=args.fontes)
    except (RuntimeError, ValueError, requests.RequestException) as e:
        erro(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
