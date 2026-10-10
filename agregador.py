#!/usr/bin/env python3
"""Agregador de Notícias.

Recolhe notícias (Google Notícias, feeds RSS e páginas sem RSS), remove duplicados,
pontua cada uma pelas palavras-chave e pela confiança da fonte, e envia alertas
por WhatsApp (CallMeBot).

Uso:
    python agregador.py                    # execução normal
    python agregador.py --simular          # mostra o que faria, sem enviar nem guardar
    python agregador.py --teste            # envia uma mensagem de teste
    python agregador.py --fontes           # execução normal + procura de fontes novas agora
    python agregador.py --testar-pagina URL [--item CSS --titulo CSS ...]
                                           # mostra o que o leitor de páginas encontra

Variáveis de ambiente: WHATSAPP_TELEFONE, WHATSAPP_APIKEY
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
UA = "Mozilla/5.0 (compatible; AgregadorNoticias/1.0)"
UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
NIVEIS = ("alta", "media", "baixa")
DIAS_VISTOS = 14
DIAS_SUGESTAO = 14
CALLMEBOT = "https://api.callmebot.com/whatsapp.php"
MAX_MSG = 3000
PAUSA_ENVIO = 4


def erro(msg):
    """Mostra um erro. No GitHub Actions aparece também como anotação da execução."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::error::" + msg.replace("\n", " "))
    else:
        print("Erro: " + msg)


def segredos_em_falta(telefone, apikey):
    """Diz exatamente que segredos faltam (nunca mostra os valores)."""
    falta = [n for n, v in (("WHATSAPP_TELEFONE", telefone), ("WHATSAPP_APIKEY", apikey))
             if not v]
    if not falta:
        return ""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return (f"falta(m) o(s) segredo(s) {' e '.join(falta)} no GitHub "
                "(Settings > Secrets and variables > Actions).")
    return (f"falta(m) {' e '.join(falta)}. No computador, define-as antes de correr, "
            "por exemplo no PowerShell: $env:WHATSAPP_TELEFONE=\"351912345678\"; "
            "$env:WHATSAPP_APIKEY=\"123456\". No GitHub, são segredos em "
            "Settings > Secrets and variables > Actions.")


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
        d = d.replace(tzinfo=timezone.utc)
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
                return datetime(a, mes, dia, 12, tzinfo=timezone.utc)
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

def ler_feed(url, nome_fonte=None, timeout=20):
    """Lê um feed RSS ou Atom e devolve uma lista de notícias (dicionários)."""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
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
        r = requests.get(url, headers={"User-Agent": UA_NAVEGADOR,
                                       "Accept-Language": "pt-PT,pt;q=0.9"}, timeout=20)
    except requests.exceptions.SSLError:
        raise RuntimeError("o certificado de segurança do site é inválido ou está "
                           "incompleto; o site não pode ser lido em segurança. Procura "
                           "um feed RSS do site ou retira-o da lista") from None
    except requests.exceptions.Timeout:
        raise RuntimeError("o site demorou demasiado a responder") from None
    except requests.RequestException:
        raise RuntimeError("não consegui ligar ao site (endereço errado ou site em baixo)") from None
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


def recolher(pesq, cfg, falhas=None):
    """Vai buscar as notícias de todas as fontes desta pesquisa."""
    fontes = cfg.get("fontes") or {}
    pedidos = []
    if pesq.get("consulta"):
        pedidos.append(("Google Notícias", ler_feed, url_google_news(pesq["consulta"], cfg)))
    for f in (fontes.get("feeds") or []) + (pesq.get("feeds_extra") or []):
        if f.get("url"):
            pedidos.append((f.get("nome"), ler_feed_local if f.get("local") else ler_feed,
                            f["url"]))
    for p in (fontes.get("paginas") or []) + (pesq.get("paginas_extra") or []):
        if p.get("url"):
            pedidos.append((p.get("nome"), ler_pagina, p))
    todas = []
    for nome, leitor, alvo in pedidos:
        try:
            itens = leitor(alvo, nome)
            print(f"  fonte '{nome}': {len(itens)} notícias")
            todas += itens
        except Exception as e:  # uma fonte em baixo não pára as outras
            print(f"  aviso: falhou '{nome}' ({type(e).__name__}: {str(e)[:80]})")
            if falhas is not None:
                falhas.append(f"{pesq['nome']} · {nome}: {type(e).__name__}: {str(e)[:120]}")
    return todas


# ---------------------------------------------------------------- pontuação

def contem(chave_norm, texto_norm):
    # palavras curtas (ex.: "ia") só valem inteiras; as outras aceitam plurais
    chave = f" {chave_norm} " if len(chave_norm) <= 3 else f" {chave_norm}"
    return chave in texto_norm


def pontos_palavras(item, pesq, pesos):
    """Devolve (pontos, palavras encontradas), ou None se tem palavra de exclusão
    ou lhe falta uma palavra obrigatória."""
    titulo = " " + normalizar(item["titulo"]) + " "
    texto = " " + normalizar(item["resumo"]) + " "
    for x in pesq.get("excluir") or []:
        xn = normalizar(x)
        if xn and (f" {xn} " in titulo or f" {xn} " in texto):
            return None
    for o in [] if item.get("local") else pesq.get("obrigatorias") or []:
        on = normalizar(o)  # fontes "local" já são do sítio: dispensam as obrigatórias
        if on and not (contem(on, titulo) or contem(on, texto)):
            return None
    total = 0
    achadas = {n: [] for n in NIVEIS}
    for nivel in NIVEIS:
        for p in (pesq.get("palavras") or {}).get(nivel) or []:
            pn = normalizar(p)
            if not pn:
                continue
            valor = pesos["pontos"][nivel]
            if contem(pn, titulo):
                total += valor * 2
                achadas[nivel].append(p)
            elif contem(pn, texto):
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
            "sugeridas": {}, "sugeridas_antigas": [], "dominios": {},
            "ultima_descoberta": "", "enviados": [], "execucoes": []}
    if ESTADO.exists():
        try:
            base.update(json.loads(ESTADO.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print("Aviso: estado.json inválido, a recomeçar do zero.")
    for velha in ("fontes", "feeds_aprovados", "botoes", "update_offset"):
        base.pop(velha, None)  # restos da versão com Telegram
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


# ---------------------------------------------------------------- WhatsApp

def whatsapp(telefone, apikey, texto):
    try:
        r = requests.get(CALLMEBOT, params={"phone": "+" + telefone, "text": texto,
                                            "apikey": apikey}, timeout=30)
    except requests.RequestException:
        raise RuntimeError("falha de rede ao contactar o CallMeBot") from None
    corpo = limpar_html(r.text)
    baixo = corpo.lower()
    # a resposta pode repetir o texto enviado: só "queued" prova que seguiu
    if r.ok and "queued" in baixo:
        return
    if r.ok and not re.search(r"\b(error|invalid|apikey|limit|wait|blocked)\b|not activ",
                              baixo):
        return
    raise RuntimeError(f"CallMeBot respondeu {r.status_code}: {corpo[:200]}")


def enviar(telefone, apikey, texto):
    whatsapp(telefone, apikey, texto)
    time.sleep(PAUSA_ENVIO)  # o CallMeBot gratuito bloqueia envios seguidos


def juntar_mensagens(blocos, maximo=MAX_MSG):
    """Junta blocos de texto em poucas mensagens (o CallMeBot limita o nº de envios).
    Devolve [(texto, [índices dos blocos incluídos])]."""
    msgs = []
    for i, b in enumerate(blocos):
        if msgs and len(msgs[-1][0]) + 2 + len(b) <= maximo:
            msgs[-1] = (msgs[-1][0] + "\n\n" + b, msgs[-1][1] + [i])
        else:
            msgs.append((b[:maximo], [i]))
    return msgs


def formatar_alerta(c, agora_utc):
    estado_fonte = "confiável" if c["confiavel"] else "fonte nova"
    linhas = [f'🔔 *{c["titulo"]}*',
              f'{c["fonte"]} ({estado_fonte}) · nota {c["nota"]} · {c["pesquisa"]}']
    palavras = []
    rot = {"alta": "alta", "media": "média", "baixa": "baixa"}
    for n in NIVEIS:
        if c["achadas"].get(n):
            palavras.append(f'{rot[n]}: {", ".join(c["achadas"][n])}')
    if palavras:
        linhas.append("🔑 " + " · ".join(palavras))
    quando = ha_quanto_tempo(parse_data(c["data"]), agora_utc)
    extra = f' · {c["n_fontes"]} fontes' if c["n_fontes"] > 1 else ""
    linhas.append(f"🕒 {quando}{extra}")
    linhas.append(c["link"])
    return "\n".join(linhas)


def mensagens_resumo(itens):
    total = len(itens)
    itens = sorted(itens, key=lambda c: c["nota"], reverse=True)[:15]
    blocos = [f'{n}. {c["titulo"]}\n   {c["fonte"]} · nota {c["nota"]} · {c["pesquisa"]}\n'
              f'   {c["link"]}' for n, c in enumerate(itens, 1)]
    if blocos:
        resto = f" (as 15 melhores de {total})" if total > len(itens) else ""
        blocos[0] = f"📰 *Resumo — {len(itens)} notícias{resto}*\n\n" + blocos[0]
    return [t for t, _ in juntar_mensagens(blocos)]


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
        consultas += list((pesq.get("palavras") or {}).get("alta") or [])[:3]
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
    linhas = [f'🔎 *Fonte nova: {s["nome"]}* ({s["dominio"]})',
              f'Apareceu em {s["n"]} notícias relevantes · {", ".join(s["pesquisas"])}',
              f'Exemplo: {s["exemplo"]}']
    linhas.append(f'📡 Feed: {s["feed"]}' if s["feed"] else
                  "📡 Sem feed próprio: continuo a vê-la pelo Google Notícias.")
    return "\n".join(linhas)


INSTRUCOES_FONTES = ("Para decidir, edita o config.yaml e junta o domínio a "
                     "fontes.confiaveis, fontes.neutras ou fontes.bloqueadas. "
                     "Se tiver feed e confiares nela, junta-o também a fontes.feeds.")


# ---------------------------------------------------------------- execução

def executar(cfg, telefone, apikey, simular=False, forcar_fontes=False):
    geral = cfg.get("geral") or {}
    tz = ZoneInfo(geral.get("fuso", "Europe/Lisbon"))
    agora_utc = datetime.now(timezone.utc)
    agora = agora_utc.astimezone(tz)
    estado = carregar_estado()
    podar(estado, agora_utc)
    limpar_sugeridas(cfg, estado)

    if not simular and not (telefone and apikey):
        erro(segredos_em_falta(telefone, apikey))
        return 1

    # registo desta execução, para o painel mostrar o que aconteceu
    registo = {"ts": agora_utc.isoformat(), "pesquisas": [], "falhas": [], "alertas": 0,
               "resumo": 0, "sugestoes": 0, "silencio": False, "erros": []}
    novos = []
    for pesq in cfg.get("pesquisas") or []:
        if not pesq.get("ativa", True):
            continue
        print(f"Pesquisa: {pesq['nome']}")
        itens = recolher(pesq, cfg, registo["falhas"])
        cands = avaliar(itens, pesq, cfg, estado, agora_utc)
        print(f"  {len(cands)} notícias relevantes")
        registo["pesquisas"].append({
            "nome": pesq["nome"], "recolhidas": len(itens), "relevantes": len(cands),
            "alertas": sum(1 for c in cands if c["nivel"] == "alerta")})
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
    falhou = False

    if simular:
        for c in imediatos:
            print("\n[ALERTA]\n" + formatar_alerta(c, agora_utc))
        for c in para_resumo:
            print(f'\n[RESUMO] nota {c["nota"]} · {c["titulo"]} ({c["fonte"]})')
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
        for texto, idx in juntar_mensagens([formatar_alerta(c, agora_utc) for c in a_enviar]):
            try:
                enviar(telefone, apikey, texto)
                for i in idx:
                    registar_envio(a_enviar[i], "alerta")
                registo["alertas"] += len(idx)
            except RuntimeError as e:
                falha(f"não consegui enviar os alertas: {e}")
                falhou = True
                estado["adiados"] = a_enviar[idx[0]:]
                break

    if (not falhou and not silencio and estado["resumo"]
            and agora.hour >= geral.get("hora_resumo", 8)
            and estado["ultimo_resumo"] != hoje):
        try:
            for texto in mensagens_resumo(estado["resumo"]):
                enviar(telefone, apikey, texto)
            for c in sorted(estado["resumo"], key=lambda c: c["nota"], reverse=True)[:15]:
                registar_envio(c, "resumo")
            registo["resumo"] = len(estado["resumo"])
            estado["resumo"] = []
            estado["ultimo_resumo"] = hoje
        except RuntimeError as e:
            falha(f"não consegui enviar o resumo: {e}")
            falhou = True

    if sugestoes and not falhou:
        blocos = [texto_sugestao(sg) for sg in sugestoes] + [INSTRUCOES_FONTES]
        try:
            for texto, _ in juntar_mensagens(blocos):
                enviar(telefone, apikey, texto)
            for sg in sugestoes:
                estado["sugeridas"][sg["dominio"]] = sg
            registo["sugestoes"] = len(sugestoes)
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


def carregar_config():
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser(description="Agregador de Notícias")
    ap.add_argument("--simular", action="store_true", help="não envia nem guarda nada")
    ap.add_argument("--teste", action="store_true", help="envia uma mensagem de teste")
    ap.add_argument("--fontes", action="store_true", help="procura fontes novas agora")
    ap.add_argument("--testar-pagina", metavar="URL", help="testa o leitor de páginas")
    ap.add_argument("--item", help="seletor CSS de cada notícia (com --testar-pagina)")
    ap.add_argument("--titulo", help="seletor CSS do título, dentro do item")
    ap.add_argument("--resumo", help="seletor CSS do resumo, dentro do item")
    ap.add_argument("--data", help="seletor CSS da data, dentro do item")
    ap.add_argument("--sem-feed", action="store_true",
                    help="com --testar-pagina: lê a página mesmo que tenha feed")
    ap.add_argument("--procurar-feeds", metavar="PESQUISA",
                    help="procura os feeds RSS (mesmo escondidos) dos sites que publicam "
                         "sobre um tema ou uma pesquisa do config.yaml")
    args = ap.parse_args()

    telefone = re.sub(r"[^\d]", "", os.environ.get("WHATSAPP_TELEFONE", ""))
    apikey = os.environ.get("WHATSAPP_APIKEY", "").strip()

    try:
        if args.testar_pagina:
            return testar_pagina(args)
        if args.procurar_feeds:
            return procurar_feeds(args.procurar_feeds, carregar_config())
        if args.teste:
            if not (telefone and apikey):
                erro(segredos_em_falta(telefone, apikey))
                return 1
            whatsapp(telefone, apikey, "✅ O agregador de notícias está ligado ao WhatsApp.")
            print("Mensagem de teste enviada.")
            return 0
        return executar(carregar_config(), telefone, apikey, simular=args.simular,
                        forcar_fontes=args.fontes)
    except (RuntimeError, ValueError, requests.RequestException) as e:
        erro(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
