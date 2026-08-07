"""
news_fetcher.py
Busca noticias recientes de fuentes verificadas y confiables.
Combina feeds RSS directos de medios de referencia con Google News,
filtrando siempre por dominio verificado.
"""

import email.utils
import feedparser
import urllib.parse
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Fuentes globales verificadas: feeds RSS de medios de referencia mundial
# Sin filtro por país — todas activas en cualquier búsqueda
# ---------------------------------------------------------------------------
FUENTES_VERIFICADAS = {
    # ── Agencias internacionales (máxima fiabilidad) ─────────────────────────
    "https://feeds.reuters.com/reuters/topNews":                "Reuters",
    "https://feeds.reuters.com/Reuters/worldNews":              "Reuters World",
    "https://apnews.com/hub/ap-top-news?format=rss":            "AP News",
    "https://www.efe.com/efe/espana/portada/rss/":              "EFE",
    # ── Cadenas internacionales en español ───────────────────────────────────
    "https://www.bbc.com/mundo/rss.xml":                        "BBC Mundo",
    "https://rss.dw.com/rdf/rss-en-es":                         "DW Español",
    "https://www.france24.com/es/rss":                          "France 24 ES",
    "https://es.euronews.com/rss":                              "Euronews ES",
    "https://www.rtve.es/api/noticias.rss":                     "RTVE",
    "https://cnnespanol.cnn.com/feed/":                         "CNN Español",
    # ── Cadenas internacionales en inglés ────────────────────────────────────
    "https://feeds.bbci.co.uk/news/rss.xml":                    "BBC",
    "https://www.aljazeera.com/xml/rss/all.xml":                "Al Jazeera",
    "https://www.france24.com/en/rss":                          "France 24",
    "https://rss.dw.com/rdf/rss-en-all":                        "DW English",
    "https://www.theguardian.com/world/rss":                    "The Guardian",
    "https://feeds.npr.org/1001/rss.xml":                       "NPR",
    # ── Prensa escrita de referencia ─────────────────────────────────────────
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada": "El País",
    "https://www.elmundo.es/rss/portada.xml":                   "El Mundo",
    "https://www.elconfidencial.com/rss/espana.xml":            "El Confidencial",
    "https://www.lavanguardia.com/rss/home.xml":                "La Vanguardia",
    "https://europapress.es/rss/rss.aspx":                      "Europapress",
    # ── Prensa Latam verificada ───────────────────────────────────────────────
    "https://www.infobae.com/feeds/rss/":                       "Infobae",
    "https://www.clarin.com/rss/lo-ultimo/":                    "Clarín",
    "https://www.eluniversal.com.mx/rss.xml":                   "El Universal MX",
    "https://www.eltiempo.com/rss/portada.xml":                 "El Tiempo CO",
    "https://www.latercera.com/rss/":                           "La Tercera CL",
    # ── Fuentes institucionales ──────────────────────────────────────────────
    "https://news.un.org/feed/subscribe/es/news/all/rss.xml":   "ONU Noticias",
    "https://www.who.int/rss-feeds/news-english.xml":           "OMS/WHO",
}

# Dominios de confianza para filtrar resultados de Google News
DOMINIOS_CONFIABLES = {
    # Agencias
    "reuters.com", "apnews.com", "efe.com", "afp.com",
    # Cadenas internacionales
    "bbc.com", "bbc.co.uk", "aljazeera.com", "france24.com", "dw.com",
    "euronews.com", "rtve.es", "cnnespanol.cnn.com", "npr.org",
    "theguardian.com", "bloomberg.com", "economist.com",
    "nytimes.com", "washingtonpost.com", "ft.com",
    # Prensa española
    "elpais.com", "elmundo.es", "elconfidencial.com", "lavanguardia.com",
    "europapress.es", "publico.es", "eldiario.es", "abc.es",
    "expansion.com", "cincodias.elpais.com",
    # Prensa Latam
    "infobae.com", "clarin.com", "lanacion.com.ar",
    "eluniversal.com.mx", "milenio.com", "reforma.com",
    "eltiempo.com", "semana.com",
    "latercera.com", "emol.com",
    "elpais.com.uy", "elobservador.com.uy",
    "elcomercio.com", "eluniverso.com",
    # Ciencia e institucional
    "nationalgeographic.com", "scientificamerican.com",
    "nasa.gov", "who.int", "nih.gov", "nature.com", "science.org",
    "agenciasinc.es", "un.org",
}

# Temas predefinidos → query de búsqueda
CATEGORIAS = {
    "tecnologia": "tecnologia",
    "negocios": "negocios OR economia",
    "mundo": "mundo OR internacional",
    "ciencia": "ciencia",
    "salud": "salud",
    "deportes": "deportes",
    "entretenimiento": "entretenimiento OR cine OR musica",
}

# ---------------------------------------------------------------------------
# Fuentes especializadas por categoría temática
# Formato: categoría → lista de (rss_url, nombre_display)
# ---------------------------------------------------------------------------
FUENTES_POR_CATEGORIA: dict[str, list[tuple[str, str]]] = {
    "salud": [
        ("https://www.who.int/rss-feeds/news-english.xml",                    "OMS/WHO"),
        ("http://feeds.bbci.co.uk/news/health/rss.xml",                       "BBC Health"),
        ("https://feeds.reuters.com/reuters/healthNews",                       "Reuters Health"),
        ("https://medlineplus.gov/rss/healthnews.xml",                        "MedlinePlus"),
        ("https://www.elmundo.es/rss/salud.xml",                              "El Mundo Salud"),
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/bienestar", "El País Bienestar"),
        ("https://www.infobae.com/feeds/rss/salud/",                          "Infobae Salud"),
        ("https://agenciasinc.es/rss",                                        "SINC Ciencia"),
    ],
    "nutricion": [
        ("https://www.who.int/rss-feeds/news-english.xml",                    "OMS/WHO"),
        ("https://medlineplus.gov/rss/healthnews.xml",                        "MedlinePlus"),
        ("http://feeds.bbci.co.uk/news/health/rss.xml",                       "BBC Health"),
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/bienestar", "El País Bienestar"),
        ("https://www.elmundo.es/rss/salud.xml",                              "El Mundo Salud"),
    ],
    "ciencia": [
        ("https://www.nasa.gov/rss/dyn/breaking_news.rss",                    "NASA"),
        ("http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",      "BBC Science"),
        ("https://feeds.reuters.com/reuters/scienceNews",                      "Reuters Science"),
        ("https://www.sciencedaily.com/rss/all.xml",                          "Science Daily"),
        ("https://www.scientificamerican.com/feed.rss",                       "Scientific American"),
        ("https://agenciasinc.es/rss",                                        "SINC"),
        ("https://www.elmundo.es/rss/ciencia.xml",                            "El Mundo Ciencia"),
    ],
    "tecnologia": [
        ("https://feeds.weblogssl.com/xataka",                                "Xataka"),
        ("https://feeds.weblogssl.com/genbeta",                               "Genbeta"),
        ("https://techcrunch.com/feed/",                                      "TechCrunch"),
        ("http://feeds.bbci.co.uk/news/technology/rss.xml",                   "BBC Tech"),
        ("https://feeds.reuters.com/reuters/technologyNews",                   "Reuters Tech"),
        ("https://www.technologyreview.com/feed/",                            "MIT Tech Review"),
    ],
    "economia": [
        ("https://feeds.reuters.com/reuters/businessNews",                    "Reuters Business"),
        ("http://feeds.bbci.co.uk/news/business/rss.xml",                     "BBC Business"),
        ("https://www.expansion.com/rss/economia.xml",                        "Expansión"),
        ("https://cincodias.elpais.com/rss/",                                 "Cinco Días"),
        ("https://feeds.reuters.com/reuters/financialsNews",                   "Reuters Mercados"),
    ],
    "cripto": [
        ("https://www.coindesk.com/arc/outboundfeeds/rss/",                   "CoinDesk"),
        ("https://cointelegraph.com/rss",                                     "Cointelegraph"),
        ("https://cryptoslate.com/feed/",                                     "CryptoSlate"),
        ("https://decrypt.co/feed",                                           "Decrypt"),
    ],
    "deportes": [
        ("https://as.com/rss/tags/ultimas_noticias.xml",                      "AS"),
        ("http://feeds.bbci.co.uk/sport/rss.xml",                             "BBC Sport"),
        ("https://feeds.reuters.com/reuters/sportsNews",                       "Reuters Sport"),
        ("https://www.marca.com/rss/portada.xml",                             "Marca"),
    ],
    "mundo": [
        ("http://feeds.bbci.co.uk/news/world/rss.xml",                        "BBC World"),
        ("https://feeds.reuters.com/Reuters/worldNews",                        "Reuters World"),
        ("https://www.aljazeera.com/xml/rss/all.xml",                         "Al Jazeera"),
        ("https://rss.dw.com/rdf/rss-en-es",                                  "DW Español"),
        ("https://feeds.reuters.com/reuters/topNews",                          "Reuters"),
    ],
    "politica": [
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/espana", "El País España"),
        ("https://www.elmundo.es/rss/espana.xml",                             "El Mundo España"),
        ("https://www.abc.es/rss/feeds/abc_espana.xml",                       "ABC España"),
        ("http://feeds.bbci.co.uk/news/world/europe/rss.xml",                 "BBC Europa"),
        ("https://feeds.reuters.com/reuters/worldNews",                        "Reuters"),
    ],
    "entretenimiento": [
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/cultura", "El País Cultura"),
        ("https://www.elmundo.es/rss/cultura.xml",                            "El Mundo Cultura"),
        ("http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",       "BBC Entertainment"),
    ],
    "medioambiente": [
        ("http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",      "BBC Medio Ambiente"),
        ("https://feeds.reuters.com/reuters/environment",                      "Reuters Environment"),
        ("https://www.nasa.gov/rss/dyn/breaking_news.rss",                    "NASA"),
        ("https://agenciasinc.es/rss",                                        "SINC"),
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/clima-y-medio-ambiente", "El País Clima"),
    ],
}

# Palabras clave para detectar la categoría de un tema libre
_PALABRAS_CATEGORIA: dict[str, list[str]] = {
    "salud":          ["salud", "health", "medicina", "médico", "medico", "enfermedad",
                       "hospital", "covid", "vacuna", "cáncer", "cancer", "farmaco",
                       "bienestar", "wellness", "mental", "psicología", "psicologia"],
    "nutricion":      ["nutrición", "nutricion", "dieta", "alimentación", "alimentacion",
                       "alimento", "comida", "obesidad", "vitamina", "proteína",
                       "proteina", "vegano", "vegana", "keto", "ayuno"],
    "ciencia":        ["ciencia", "science", "investigación", "investigacion", "estudio",
                       "nasa", "espacio", "space", "física", "química", "biología",
                       "genética", "genetica", "neurociencia", "astronomía", "astronomia"],
    "medioambiente":  ["clima", "cambio climático", "medio ambiente", "sostenible",
                       "emisiones", "co2", "ecología", "ecologia", "biodiversidad",
                       "renovable", "energía verde", "contaminación"],
    "tecnologia":     ["tecnología", "tecnologia", "tech", "ia", "inteligencia artificial",
                       "robot", "software", "hardware", "app", "startup", "openai",
                       "google", "apple", "microsoft", "meta", "chatgpt", "llm"],
    "economia":       ["economía", "economia", "mercado", "bolsa", "inflación",
                       "inflacion", "pib", "finanzas", "banco", "inversión", "inversion",
                       "empresa", "negocio", "paro", "desempleo", "impuesto"],
    "cripto":         ["cripto", "crypto", "bitcoin", "ethereum", "blockchain",
                       "nft", "web3", "defi", "altcoin", "binance", "coinbase"],
    "deportes":       ["deporte", "fútbol", "futbol", "baloncesto", "tenis", "formula 1",
                       "f1", "olimpiadas", "liga", "champions", "nba", "nfl",
                       "atletismo", "ciclismo", "natación"],
    "mundo":          ["internacional", "guerra", "conflicto", "onu", "nato", "otan",
                       "europa", "asia", "africa", "oriente", "diplomacia", "embajada"],
    "politica":       ["política", "politica", "gobierno", "elecciones", "presidente",
                       "congreso", "senado", "parlamento", "partido", "ministro",
                       "ley", "reforma", "decreto", "voto"],
    "entretenimiento": ["cine", "película", "pelicula", "serie", "netflix", "spotify",
                        "música", "musica", "concierto", "álbum", "album",
                        "celebrity", "famoso", "oscar", "grammy"],
}


def detectar_categoria(tema: str) -> str | None:
    """Detecta la categoría temática de un texto libre. Devuelve None si no hay match claro."""
    tema_lower = tema.lower()
    puntuaciones: dict[str, int] = {}
    for cat, palabras in _PALABRAS_CATEGORIA.items():
        score = sum(1 for p in palabras if p in tema_lower)
        if score > 0:
            puntuaciones[cat] = score
    if not puntuaciones:
        return None
    return max(puntuaciones, key=lambda c: puntuaciones[c])


def buscar_tema_especializado(tema: str, max_por_fuente: int = 6) -> list:
    """
    Busca en fuentes especializadas para el tema dado.
    Detecta la categoría y descarga los feeds correspondientes.
    Devuelve lista con los mismos campos que buscar_noticias().
    """
    categoria = detectar_categoria(tema)
    if not categoria or categoria not in FUENTES_POR_CATEGORIA:
        return []

    fuentes = FUENTES_POR_CATEGORIA[categoria]
    resultado = []

    for rss_url, nombre in fuentes:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:max_por_fuente]:
                fecha = entry.get("published", "")
                recencia = calcular_recencia(fecha)
                resultado.append({
                    "titulo": entry.title,
                    "link": entry.link,
                    "fuente": nombre,
                    "fecha": fecha,
                    "resumen": entry.get("summary", ""),
                    "recencia": recencia,
                    "fuente_verificada": True,
                    "categoria_detectada": categoria,
                })
        except Exception:
            pass

    return resultado


# ---------------------------------------------------------------------------
# Recencia
# ---------------------------------------------------------------------------

def _parsear_fecha(fecha_str: str) -> datetime | None:
    """Parsea fecha RFC 2822 (RSS estándar) o ISO 8601."""
    if not fecha_str:
        return None
    try:
        return email.utils.parsedate_to_datetime(fecha_str)
    except Exception:
        pass
    # ISO 8601 manual fallback
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(fecha_str[:19], fmt[:len(fmt)])
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def calcular_recencia(fecha_str: str) -> dict:
    """Devuelve label legible y si es muy reciente (<3h)."""
    dt = _parsear_fecha(fecha_str)
    if not dt:
        return {"horas": None, "label": "", "muy_reciente": False}

    ahora = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = ahora - dt
    horas = delta.total_seconds() / 3600

    if horas < 0:
        horas = 0.0

    if horas < 1:
        minutos = max(1, int(delta.total_seconds() / 60))
        label = f"Hace {minutos}min"
        muy_reciente = True
    elif horas < 3:
        label = f"Hace {int(horas)}h"
        muy_reciente = True
    elif horas < 12:
        label = f"Hace {int(horas)}h"
        muy_reciente = False
    elif horas < 24:
        label = "Hoy"
        muy_reciente = False
    elif horas < 48:
        label = "Ayer"
        muy_reciente = False
    else:
        dias = int(horas / 24)
        label = f"Hace {dias}d"
        muy_reciente = False

    return {"horas": round(horas, 1), "label": label, "muy_reciente": muy_reciente}


def _es_dominio_confiable(link: str) -> bool:
    """Verifica si una URL pertenece a un medio de confianza."""
    try:
        dominio = urllib.parse.urlparse(link).netloc.lower().replace("www.", "")
        return any(conf in dominio for conf in DOMINIOS_CONFIABLES)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Búsqueda directa en feeds de fuentes verificadas
# ---------------------------------------------------------------------------

def buscar_fuentes_directas(pais: str = "ES", max_por_fuente: int = 6) -> list:
    """
    Descarga RSS directo de todas las fuentes verificadas globales.
    Son noticias de primera mano, sin pasar por Google News.
    El parámetro pais ya no filtra feeds — solo se conserva por compatibilidad.
    """
    resultado = []
    for rss_url, nombre in FUENTES_VERIFICADAS.items():
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:max_por_fuente]:
                fecha = entry.get("published", "")
                recencia = calcular_recencia(fecha)
                resultado.append({
                    "titulo": entry.title,
                    "link": entry.link,
                    "fuente": nombre,
                    "fecha": fecha,
                    "resumen": entry.get("summary", ""),
                    "recencia": recencia,
                    "fuente_verificada": True,
                })
        except Exception:
            pass
    return resultado


# ---------------------------------------------------------------------------
# Búsqueda por tema en Google News (filtrada por dominio confiable)
# ---------------------------------------------------------------------------

def buscar_noticias(tema: str, idioma: str = "es-419", pais: str = "US",
                    max_resultados: int = 10, solo_confiables: bool = True) -> list:
    """
    Busca noticias sobre un tema usando el feed RSS de Google News.
    Con solo_confiables=True (defecto) filtra por dominio verificado.

    Devuelve lista de dicts: {titulo, link, fuente, fecha, resumen, recencia, fuente_verificada}
    """
    query = CATEGORIAS.get(tema.lower(), tema)
    query_encoded = urllib.parse.quote(query)
    url = (
        f"https://news.google.com/rss/search?q={query_encoded}"
        f"&hl={idioma}&gl={pais}&ceid={pais}:{idioma}"
    )

    feed = feedparser.parse(url)

    noticias = []
    for entry in feed.entries[:max_resultados * 3]:  # fetch extra to allow filtering
        fuente = ""
        if hasattr(entry, "source") and hasattr(entry.source, "title"):
            fuente = entry.source.title

        link = entry.link
        verificada = _es_dominio_confiable(link)

        if solo_confiables and not verificada:
            continue

        fecha = entry.get("published", "")
        recencia = calcular_recencia(fecha)

        noticias.append({
            "titulo": entry.title,
            "link": link,
            "fuente": fuente,
            "fecha": fecha,
            "resumen": entry.get("summary", ""),
            "recencia": recencia,
            "fuente_verificada": verificada,
        })

        if len(noticias) >= max_resultados:
            break

    return noticias


def buscar_variadas(temas=None, por_tema: int = 3, pais: str = "ES") -> list:
    """
    Junta noticias de varias fuentes:
    1. Feeds RSS directos de fuentes verificadas (prioridad)
    2. Google News filtrado por tema y dominio confiable

    Resultado ordenado por recencia.
    """
    # 1. Fuentes directas
    directas = buscar_fuentes_directas(pais=pais, max_por_fuente=4)

    # 2. Google News por categorías
    if temas is None:
        temas = list(CATEGORIAS.keys())

    google_news = []
    for tema in temas:
        items = buscar_noticias(tema, max_resultados=por_tema, solo_confiables=True)
        for it in items:
            it["tema"] = tema
        google_news.extend(items)

    # Combinar con deduplicación por título
    todos = directas + google_news
    vistos = set()
    unicos = []
    for item in todos:
        key = item["titulo"][:50].lower().strip()
        if key not in vistos:
            vistos.add(key)
            unicos.append(item)

    # Ordenar por recencia (las más recientes primero, las sin fecha al final)
    def _sort_key(it):
        horas = it.get("recencia", {}).get("horas")
        return horas if horas is not None else 9999.0

    unicos.sort(key=_sort_key)
    return unicos


if __name__ == "__main__":
    import json
    print("=== Fuentes directas verificadas (ES) ===")
    noticias = buscar_fuentes_directas(pais="ES", max_por_fuente=2)
    for n in noticias[:6]:
        rec = n["recencia"]
        print(f"  [{rec['label']}] {n['titulo'][:60]} — {n['fuente']}")

    print("\n=== Google News filtrado (tecnología) ===")
    noticias = buscar_noticias("tecnologia", max_resultados=5)
    for n in noticias:
        rec = n["recencia"]
        print(f"  [{rec['label']}] {n['titulo'][:60]} — {n['fuente']} ({'✓' if n['fuente_verificada'] else '?'})")
