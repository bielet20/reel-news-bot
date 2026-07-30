"""
article_extractor.py
Descarga el HTML de un articulo y extrae el texto principal (parrafos),
para tener mas contexto que el titulo/resumen del RSS.
Tambien permite extraer titulo + fuente de una URL suelta (para cuando el
usuario pega un link de un articulo en vez de buscar por tema).
"""

import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

# Headers mas completos que un User-Agent solo: algunos sitios bloquean
# peticiones automatizadas si faltan Accept/Accept-Language/Referer, aunque
# la pagina sea completamente publica para cualquier persona con navegador.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}

# Fragmentos tipicos de avisos de cookies, paywalls y newsletters que NO son
# el contenido real del articulo, pero que muchos sitios ponen en <p> normales
# (por eso un filtro de tags no alcanza, hay que revisar el texto).
FRASES_BASURA = [
    "cookies", "cookie", "consentimiento", "aceptar todo", "rechazar todo",
    "accept all", "reject all", "política de privacidad", "privacy policy",
    "suscríbete", "suscribete", "subscribe", "inicia sesión", "inicia sesion",
    "boletín", "boletin", "newsletter", "anuncios personalizados",
    "personalized ads", "gestionar preferencias", "manage preferences",
    "contenido no personalizado", "non-personalized", "activa las notificaciones",
]

# Etiquetas cuyo id/class suele indicar banners de cookies, paywalls, etc.
SELECTORES_BASURA = [
    "cookie", "consent", "gdpr", "paywall", "newsletter", "subscribe",
    "modal", "popup", "banner", "advert",
]


def _descargar(url: str, timeout: int = 10, intentos: int = 3):
    """
    Descarga la pagina con un par de reintentos con espera si el sitio
    responde 429 (demasiadas peticiones) o 503 (servicio no disponible),
    que suelen ser bloqueos temporales de proteccion anti-bots.
    """
    ultimo_error = None
    for intento in range(intentos):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if resp.status_code in (429, 503) and intento < intentos - 1:
                time.sleep(2 * (intento + 1))
                continue
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as e:
            ultimo_error = e
            if resp.status_code in (429, 503) and intento < intentos - 1:
                time.sleep(2 * (intento + 1))
                continue
            raise
        except Exception as e:
            ultimo_error = e
            raise
    raise ultimo_error


def _es_parrafo_valido(texto: str, min_len: int) -> bool:
    if len(texto) < min_len:
        return False
    texto_lower = texto.lower()
    return not any(frase in texto_lower for frase in FRASES_BASURA)


def _limpiar_soup(soup: BeautifulSoup):
    """Elimina tags que casi nunca son contenido real, incluyendo banners de
    cookies/paywalls/newsletters identificados por su id o clase."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # convertir a lista antes de decomponer: modificar el arbol mientras se
    # itera sobre el mismo generador puede dejar referencias a tags ya
    # eliminados (huerfanos), y tag.get() fallaria sobre ellos.
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue  # ya fue eliminado como hijo de otro tag basura
        atributos = " ".join([
            tag.get("id", "") or "", " ".join(tag.get("class", []) or [])
        ]).lower()
        if any(pista in atributos for pista in SELECTORES_BASURA):
            tag.decompose()


def _extraer_parrafos(soup: BeautifulSoup, min_len_parrafo: int) -> str:
    """
    Extrae el texto principal: prioriza el contenido dentro de <article> si
    existe (ahi suele estar el cuerpo real de la noticia), y filtra parrafos
    que son avisos de cookies/paywalls/newsletters en vez de contenido.
    """
    _limpiar_soup(soup)

    contenedor = soup.find("article") or soup

    parrafos = []
    for p in contenedor.find_all("p"):
        texto = p.get_text(" ", strip=True)
        if _es_parrafo_valido(texto, min_len_parrafo):
            parrafos.append(texto)

    # si el <article> no tenia suficiente texto util, probar con toda la pagina
    if len(" ".join(parrafos).split()) < 30 and contenedor is not soup:
        parrafos = []
        for p in soup.find_all("p"):
            texto = p.get_text(" ", strip=True)
            if _es_parrafo_valido(texto, min_len_parrafo):
                parrafos.append(texto)

    return "\n".join(parrafos)


def extraer_texto(url: str, timeout: int = 10, min_len_parrafo: int = 40) -> str:
    """
    Descarga la pagina y concatena los parrafos <p> con texto sustancial,
    descartando avisos de cookies/paywalls/newsletters.
    Devuelve un string vacio si falla (el pipeline debe usar el resumen del RSS
    como respaldo en ese caso).
    """
    try:
        html = _descargar(url, timeout=timeout)
    except Exception:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    return _extraer_parrafos(soup, min_len_parrafo)


def _extraer_titulo(soup: BeautifulSoup) -> str:
    """Busca el titulo en el orden mas confiable: og:title -> <h1> -> <title>."""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)

    if soup.title and soup.title.get_text(strip=True):
        # muchos sitios agregan " - NombreDelSitio" al final del <title>
        return soup.title.get_text(strip=True).split(" - ")[0].split(" | ")[0]

    return "Articulo sin titulo"


def _extraer_fuente(url: str, soup: BeautifulSoup) -> str:
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        return og_site["content"].strip()
    dominio = urllib.parse.urlparse(url).netloc
    return dominio.replace("www.", "")


def extraer_articulo(url: str, timeout: int = 10, min_len_parrafo: int = 40) -> dict:
    """
    Descarga una URL de articulo y devuelve un dict listo para usar con
    summarizer.generar_guion_reel():
        {titulo, fuente, link, texto}
    Pensado para cuando el usuario pega un link puntual (no viene de una
    busqueda por RSS, asi que no hay titulo/fuente previos).
    """
    html = _descargar(url, timeout=timeout)
    soup = BeautifulSoup(html, "html.parser")

    # el titulo/fuente se leen ANTES de limpiar el soup (por si el titulo
    # estuviera dentro de algun tag que _limpiar_soup luego elimina)
    titulo = _extraer_titulo(soup)
    fuente = _extraer_fuente(url, soup)

    texto = _extraer_parrafos(soup, min_len_parrafo)

    return {
        "titulo": titulo,
        "fuente": fuente,
        "link": url,
        "texto": texto,
    }


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else None
    if url:
        art = extraer_articulo(url)
        print("Titulo:", art["titulo"])
        print("Fuente:", art["fuente"])
        print(art["texto"][:1000])
    else:
        print("Uso: python article_extractor.py <url>")
