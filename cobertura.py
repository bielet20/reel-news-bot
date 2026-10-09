"""
cobertura.py
Consigue el TEXTO REAL de una noticia antes de hacer el reel.

Problema (2026-10-05): las noticias que llegan por Google News traen como
"resumen" solo un <a href> con el titular. El Gestor mandaba eso al guionista,
la IA respondía CONTENIDO_INSUFICIENTE y salía la plantilla de emergencia
("¿Sabías esto sobre <titular>? <titular> Sígueme...") → reels de 11 s que el
piloto automático publicaba.

Orden:
  1. Resolver el enlace de Google News a la URL real del medio y extraerla.
  2. Si el medio bloquea (Reuters da 401 incluso con Chromium), buscar la misma
     historia en Google News y extraer el primer medio con titular parecido
     y texto suficiente.
"""
import json
import re
from urllib.parse import quote

import requests

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
# Sin esta cookie, desde la UE Google devuelve la página de consentimiento.
_CONSENT = {"CONSENT": "YES+cb", "SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVzIAEaBgiA_LyaBg"}

MIN_PALABRAS_ARTICULO = 150
SIM_MIN_TITULAR = 0.30


def es_google_news(url: str) -> bool:
    return "news.google.com" in (url or "")


def resolver_google_news(url: str, timeout: int = 15) -> str | None:
    """URL real del medio a partir de un enlace news.google.com/rss/articles/…"""
    m = re.search(r"/articles/([^?/]+)", url or "")
    if not m:
        return None
    gid = m.group(1)
    try:
        html = requests.get(f"https://news.google.com/rss/articles/{gid}", headers=_UA,
                            cookies=_CONSENT, timeout=timeout).text
        sg = re.search(r'data-n-a-sg="([^"]+)"', html)
        ts = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not (sg and ts):
            return None
        inner = (f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,'
                 f'null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
                 f'"{gid}",{ts.group(1)},"{sg.group(1)}"]')
        r = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={**_UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data=f"f.req={quote(json.dumps([[['Fbv4je', inner]]]))}", timeout=timeout)
        real = json.loads(json.loads(r.text.split("\n\n")[1])[0][2])[1]
        return real if isinstance(real, str) and real.startswith("http") else None
    except Exception as e:
        print(f"   [cobertura] No se pudo resolver Google News: {e}")
        return None


def _extraer(url: str) -> str:
    from article_extractor import extraer_texto
    try:
        return extraer_texto(url) or ""
    except Exception:
        return ""


def _titular_limpio(titulo: str) -> str:
    # "OpenAI's Altman says ... - Reuters" → sin el medio del final
    return re.sub(r"\s+[-—|]\s+[^-—|]{2,40}$", "", titulo or "").strip()


def texto_de_noticia(noticia: dict, min_palabras: int = MIN_PALABRAS_ARTICULO,
                     max_intentos: int = 6) -> dict | None:
    """{texto, url, medio} con el artículo completo, o None si no se encontró
    ningún medio con texto suficiente sobre ESA historia."""
    from news_fetcher import _sim_titulo, _tokens_titulo

    link = noticia.get("link", "")
    probadas: set[str] = set()

    real = resolver_google_news(link) if es_google_news(link) else link
    if real:
        probadas.add(real)
        texto = _extraer(real)
        if len(texto.split()) >= min_palabras:
            return {"texto": texto, "url": real, "medio": noticia.get("fuente", "")}
        print(f"   [cobertura] {real[:80]} → {len(texto.split())} palabras (bloqueado o corto)")

    titular = _titular_limpio(noticia.get("titulo_original") or noticia.get("titulo", ""))
    if not titular:
        return None
    tok_ref = _tokens_titulo(titular)
    try:
        import feedparser
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={quote(titular)}&hl=en-US&gl=US&ceid=US:en")
    except Exception as e:
        print(f"   [cobertura] Búsqueda falló: {e}")
        return None

    intentos = 0
    for e in feed.entries:
        if intentos >= max_intentos:
            break
        medio = (e.get("source") or {}).get("title", "")
        if _sim_titulo(tok_ref, _tokens_titulo(e.get("title", ""))) < SIM_MIN_TITULAR:
            continue  # otra noticia distinta
        url = resolver_google_news(e.link) if es_google_news(e.link) else e.link
        if not url or url in probadas:
            continue
        probadas.add(url)
        intentos += 1
        texto = _extraer(url)
        if len(texto.split()) >= min_palabras:
            print(f"   [cobertura] Texto de {medio}: {len(texto.split())} palabras")
            return {"texto": texto, "url": url, "medio": medio}
    return None
