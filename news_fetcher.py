"""
news_fetcher.py
Busca noticias recientes de fuentes verificadas y confiables.
Combina feeds RSS directos de medios de referencia con Google News,
filtrando siempre por dominio verificado.
"""

import email.utils
import re
import unicodedata
import urllib.parse
from datetime import datetime, timezone

import feedparser

feedparser.USER_AGENT = (
    "Mozilla/5.0 (compatible; ReelNewsBot/1.0; +https://github.com/reel-news-bot)"
)


def _gnews_site(dominio: str, query: str, hl: str = "en", gl: str = "US") -> str:
    q = urllib.parse.quote(f"site:{dominio} ({query})")
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl}"


# ---------------------------------------------------------------------------
# Fuentes globales verificadas: feeds RSS de medios de referencia mundial
# Sin filtro por país — todas activas en cualquier búsqueda
# ---------------------------------------------------------------------------
FUENTES_VERIFICADAS = {
    # ── Agencias internacionales (máxima fiabilidad) ─────────────────────────
    "https://feeds.reuters.com/reuters/topNews":                "Reuters",
    _gnews_site("reuters.com", "news", hl="es", gl="ES"):       "Reuters ES",
    "https://feeds.apnews.com/rss/apf-topnews":                 "AP News",
    _gnews_site("apnews.com", "news", hl="en", gl="US"):         "AP World",
    "https://www.efe.com/efe/espana/portada/rss/":              "EFE",
    _gnews_site("afp.com", "news", hl="es", gl="ES"):           "AFP",
    # ── Cadenas internacionales en español ───────────────────────────────────
    "https://www.bbc.com/mundo/rss.xml":                        "BBC Mundo",
    "https://rss.dw.com/rdf/rss-en-es":                         "DW Español",
    "https://www.france24.com/es/rss":                          "France 24 ES",
    "https://es.euronews.com/rss":                              "Euronews ES",
    "https://www.rtve.es/api/noticias.rss":                     "RTVE",
    "https://cnnespanol.cnn.com/feed/":                         "CNN Español",
    "https://www.swissinfo.ch/spa/rss/news":                    "Swissinfo ES",
    _gnews_site("rfi.fr", "noticias", hl="es", gl="ES"):        "RFI Español",
    # ── Cadenas internacionales en inglés ────────────────────────────────────
    "https://feeds.bbci.co.uk/news/rss.xml":                    "BBC",
    "https://www.aljazeera.com/xml/rss/all.xml":                "Al Jazeera",
    "https://www.france24.com/en/rss":                          "France 24",
    "https://rss.dw.com/rdf/rss-en-all":                        "DW English",
    "https://www.theguardian.com/world/rss":                    "The Guardian",
    "https://feeds.npr.org/1001/rss.xml":                       "NPR",
    "https://feeds.skynews.com/feeds/rss/world.xml":            "Sky News",
    "https://abcnews.go.com/abcnews/topstories":                "ABC News",
    "https://feeds.nbcnews.com/nbcnews/public/news":            "NBC News",
    "https://www.cbsnews.com/latest/rss/main":                  "CBS News",
    "https://www.cbc.ca/cmlink/rss-topstories":                 "CBC Canada",
    "https://www.independent.co.uk/news/rss":                   "The Independent",
    "https://api.axios.com/feed/":                              "Axios",
    "https://rss.politico.com/politics-news.xml":               "Politico",
    "https://www.theatlantic.com/feed/all/":                    "The Atlantic",
    "https://foreignpolicy.com/feed/":                          "Foreign Policy",
    "https://www.foreignaffairs.com/rss.xml":                   "Foreign Affairs",
    # ── Asia-Pacífico y Oriente Medio ────────────────────────────────────────
    "https://www3.nhk.or.jp/nhkworld/en/news/feeds/":           "NHK World",
    "https://www.scmp.com/rss/91/feed":                         "SCMP",
    "https://www.thehindu.com/feeder/default.rss":              "The Hindu",
    "https://www.dawn.com/feed":                                "Dawn",
    "https://www.arabnews.com/rss.xml":                         "Arab News",
    "https://www.jpost.com/rss/rssfeedsfrontpage.aspx":         "Jerusalem Post",
    "https://www.middleeasteye.net/rss":                        "Middle East Eye",
    # ── Prensa escrita de referencia ─────────────────────────────────────────
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada": "El País",
    "https://www.elmundo.es/rss/portada.xml":                   "El Mundo",
    "https://www.elconfidencial.com/rss/espana.xml":            "El Confidencial",
    "https://www.lavanguardia.com/rss/home.xml":                "La Vanguardia",
    "https://europapress.es/rss/rss.aspx":                      "Europapress",
    "https://www.eldiario.es/rss/":                             "El Diario",
    "https://www.publico.es/rss/":                              "Público",
    "https://www.20minutos.es/rss/":                            "20 Minutos",
    "https://www.abc.es/rss/feeds/abc_portada.xml":             "ABC España",
    "https://www.elespanol.com/rss/":                           "El Español",
    "https://cadenaser.com/ser/rss/":                           "Cadena SER",
    "https://www.elperiodico.com/es/rss/rss_portada.xml":       "El Periódico",
    # ── Prensa Latam ampliada ─────────────────────────────────────────────────
    "https://www.infobae.com/feeds/rss/":                       "Infobae",
    "https://www.clarin.com/rss/lo-ultimo/":                    "Clarín",
    "https://www.lanacion.com.ar/arc/outboundfeeds/rss/":       "La Nación AR",
    "https://www.perfil.com/rss/":                              "Perfil AR",
    "https://www.eluniversal.com.mx/rss.xml":                   "El Universal MX",
    "https://www.milenio.com/rss":                              "Milenio MX",
    "https://www.proceso.com.mx/?feed=rss2":                    "Proceso MX",
    "https://www.elfinanciero.com.mx/rss/":                     "El Financiero MX",
    "https://www.eltiempo.com/rss/portada.xml":                 "El Tiempo CO",
    "https://www.semana.com/rss/":                              "Semana CO",
    "https://www.latercera.com/rss/":                           "La Tercera CL",
    "https://www.emol.com/rss/":                                "Emol CL",
    "https://www.biobiochile.cl/feed":                          "BioBio CL",
    "https://elcomercio.pe/rss/portada.xml":                    "El Comercio PE",
    "https://rpp.pe/rss":                                       "RPP PE",
    "https://www.eluniverso.com/rss":                           "El Universo EC",
    "https://www.elpais.com.uy/rss/":                           "El País UY",
    "https://www.elobservador.com.uy/rss":                      "El Observador UY",
    "https://www.elnacional.com/feed/":                         "El Nacional VE",
    # ── Fact-checkers globales ───────────────────────────────────────────────
    "https://factual.afp.com/es/rss":                           "AFP Factual",
    "https://chequeado.com/feed/":                              "Chequeado AR",
    "https://www.animalpolitico.com/feed":                      "Animal Político MX",
    _gnews_site("maldita.es", "verificacion OR bulo"):          "Maldita",
    _gnews_site("fullfact.org", "fact check"):                  "Full Fact",
    _gnews_site("politifact.com", "fact check"):                "PolitiFact",
    # ── Medios de negocios y finanzas ────────────────────────────────────────
    "https://www.cnbc.com/id/100003114/device/rss/rss.html":    "CNBC",
    "https://feeds.businessinsider.com/custom/all":             "Business Insider",
    "https://fortune.com/feed/fortune-feeds/?id=3230629":       "Fortune",
    "https://www.expansion.com/rss/economia.xml":               "Expansión",
    "https://cincodias.elpais.com/rss/":                        "Cinco Días",
    "https://feeds.bloomberg.com/markets/news.rss":             "Bloomberg Markets",
    # ── Ciencia y tecnología de referencia ───────────────────────────────────
    "https://www.sciencenews.org/feed":                         "Science News",
    "https://www.statnews.com/feed/":                           "STAT News",
    "https://phys.org/rss-feed.xml":                            "Phys.org",
    "https://www.scientificamerican.com/platform/morgue/rss/":  "Scientific American",
    "https://www.nationalgeographic.com/content/natgeo/en_us/news.rss": "Nat Geo",
    "https://venturebeat.com/feed/":                            "VentureBeat",
    "https://www.cnet.com/rss/news/":                           "CNET",
    "https://www.engadget.com/rss.xml":                         "Engadget",
    "https://www.theregister.com/headlines.atom":               "The Register",
    # ── Medioambiente y clima ────────────────────────────────────────────────
    "https://www.carbonbrief.org/feed/":                        "Carbon Brief",
    "https://e360.yale.edu/feed":                               "Yale E360",
    "https://grist.org/feed/":                                  "Grist",
    # ── Fuentes institucionales ──────────────────────────────────────────────
    "https://news.un.org/feed/subscribe/es/news/all/rss.xml":   "ONU Noticias",
    "https://www.who.int/rss-feeds/news-english.xml":           "OMS/WHO",
    "https://www.cdc.gov/media/feeds/news.xml":                 "CDC",
    "https://www.nih.gov/news-events/news-releases/feed":        "NIH",
    "https://www.nasa.gov/rss/dyn/breaking_news.rss":           "NASA",
}

# Dominios de confianza para filtrar resultados de Google News
DOMINIOS_CONFIABLES = {
    # Agencias internacionales
    "reuters.com", "apnews.com", "efe.com", "afp.com", "factcheck.afp.com",
    "ap.org", "dpa.com", "pa.media",
    # Fact-checkers globales
    "maldita.es", "newtral.es", "fullfact.org", "factual.afp.com",
    "chequeado.com", "animalpolitico.com", "politifact.com", "snopes.com",
    "colombiacheck.com", "elsabueso.mx", "verificado.mx", "afpfactual.com",
    "firstdraftnews.org", "factcheck.org",
    # Cadenas internacionales en español
    "bbc.com", "bbc.co.uk", "france24.com", "dw.com", "euronews.com",
    "rtve.es", "cnnespanol.cnn.com", "swissinfo.ch", "rfi.fr",
    # Cadenas internacionales en inglés
    "aljazeera.com", "npr.org", "theguardian.com", "skynews.com", "sky.com",
    "abcnews.go.com", "nbcnews.com", "cbsnews.com", "cbc.ca",
    "independent.co.uk", "economist.com",
    "bloomberg.com", "ft.com", "wsj.com",
    "nytimes.com", "washingtonpost.com",
    "axios.com", "politico.com", "theatlantic.com",
    "foreignpolicy.com", "foreignaffairs.com", "cfr.org",
    # Asia-Pacífico y Oriente Medio
    "nhk.or.jp", "nhk.jp", "scmp.com", "thehindu.com", "dawn.com",
    "arabnews.com", "jpost.com", "haaretz.com",
    "middleeasteye.net", "almonitor.com",
    "straitstimes.com", "abc.net.au", "smh.com.au",
    # Europa anglófona y continental
    "euractiv.com", "euobserver.com", "politico.eu",
    "lemonde.fr", "liberation.fr", "lefigaro.fr",
    "spiegel.de", "zeit.de", "sueddeutsche.de",
    "corriere.it", "repubblica.it",
    # Prensa española
    "elpais.com", "elmundo.es", "elconfidencial.com", "lavanguardia.com",
    "europapress.es", "publico.es", "eldiario.es", "abc.es",
    "expansion.com", "cincodias.elpais.com", "elespanol.com",
    "20minutos.es", "cadenaser.com", "elperiodico.com",
    "lasexta.com", "antena3.com", "larazon.es",
    # Prensa Latam
    "infobae.com", "clarin.com", "lanacion.com.ar", "perfil.com",
    "eluniversal.com.mx", "milenio.com", "reforma.com", "proceso.com.mx",
    "jornada.com.mx", "elfinanciero.com.mx",
    "eltiempo.com", "semana.com", "elcolombiano.com", "larepublica.co",
    "latercera.com", "emol.com", "biobiochile.cl", "elmostrador.cl",
    "elcomercio.pe", "rpp.pe", "larepublica.pe",
    "eluniverso.com", "elcomercio.com",
    "elpais.com.uy", "elobservador.com.uy",
    "elnacional.com", "globovision.com",
    "elnuevoherald.com", "univision.com", "telemundo.com",
    # Prensa África
    "allafrica.com", "dailymaverick.co.za", "mg.co.za", "nairaland.com",
    # Instituciones y gobierno
    "un.org", "who.int", "nih.gov", "nasa.gov", "cdc.gov",
    "worldbank.org", "imf.org", "oecd.org", "ec.europa.eu",
    "whitehouse.gov", "state.gov", "europa.eu",
    # Ciencia y salud
    "nature.com", "science.org", "nationalgeographic.com",
    "scientificamerican.com", "newscientist.com",
    "sciencenews.org", "sciencedaily.com", "phys.org",
    "statnews.com", "medscape.com", "medpagetoday.com",
    "mayoclinic.org", "health.harvard.edu", "medlineplus.gov",
    "agenciasinc.es", "eurekalert.org", "livescience.com",
    "space.com", "popsci.com",
    # IA y tecnología verificada
    "technologyreview.com", "arstechnica.com", "ieee.org", "spectrum.ieee.org",
    "wired.com", "theverge.com", "404media.co", "techmeme.com",
    "techcrunch.com", "xataka.com", "genbeta.com",
    "venturebeat.com", "cnet.com", "engadget.com", "zdnet.com",
    "theregister.com", "9to5mac.com", "9to5google.com",
    "openai.com", "anthropic.com", "deepmind.google", "ai.google",
    "huggingface.co", "mistral.ai",
    # Finanzas y negocios
    "cnbc.com", "businessinsider.com", "fortune.com", "barrons.com",
    "marketwatch.com", "seekingalpha.com",
    "coindesk.com", "cointelegraph.com", "decrypt.co",
    # Medioambiente
    "carbonbrief.org", "e360.yale.edu", "grist.org", "insideclimatenews.org",
    "cleantechnica.com",
}

# 1 agencia/ciencia  2 prensa de referencia  3 especialista  4 alerta/PR
NIVEL_DOMINIO = {
    # Agencias nivel 1
    "reuters.com": 1, "apnews.com": 1, "ap.org": 1, "afp.com": 1, "efe.com": 1,
    "factual.afp.com": 1, "factcheck.afp.com": 1,
    # Ciencia y salud institucional nivel 1
    "nature.com": 1, "science.org": 1,
    "who.int": 1, "nih.gov": 1, "nasa.gov": 1, "cdc.gov": 1, "un.org": 1,
    "technologyreview.com": 1, "arstechnica.com": 1,
    "ieee.org": 1, "spectrum.ieee.org": 1,
    # Prensa de referencia nivel 2
    "bbc.com": 2, "bbc.co.uk": 2,
    "ft.com": 2, "bloomberg.com": 2, "nytimes.com": 2, "wsj.com": 2,
    "economist.com": 2, "npr.org": 2, "theguardian.com": 2,
    "washingtonpost.com": 2, "elpais.com": 2, "newscientist.com": 2,
    "maldita.es": 2, "newtral.es": 2, "fullfact.org": 2, "chequeado.com": 2,
    "politifact.com": 2, "animalpolitico.com": 2, "agenciasinc.es": 2,
    "france24.com": 2, "dw.com": 2, "aljazeera.com": 2,
    "rtve.es": 2, "euronews.com": 2,
    "nhk.or.jp": 2, "nhk.jp": 2, "scmp.com": 2, "thehindu.com": 2,
    "abcnews.go.com": 2, "nbcnews.com": 2, "cbsnews.com": 2, "cbc.ca": 2,
    "independent.co.uk": 2, "axios.com": 2, "politico.com": 2,
    "theatlantic.com": 2, "foreignpolicy.com": 2, "foreignaffairs.com": 2,
    "swissinfo.ch": 2, "sciencenews.org": 2, "statnews.com": 2, "phys.org": 2,
    "scientificamerican.com": 2, "nationalgeographic.com": 2,
    "carbonbrief.org": 2, "cnbc.com": 2,
    "lavanguardia.com": 2, "elmundo.es": 2, "elconfidencial.com": 2,
    "europapress.es": 2, "infobae.com": 2, "clarin.com": 2, "lanacion.com.ar": 2,
    "eltiempo.com": 2, "latercera.com": 2,
    # Especialistas nivel 3
    "wired.com": 3, "theverge.com": 3, "404media.co": 3,
    "techmeme.com": 3, "theregister.com": 3,
    "openai.com": 3, "anthropic.com": 3, "deepmind.google": 3, "ai.google": 3,
    "cnet.com": 3, "engadget.com": 3, "zdnet.com": 3,
    "businessinsider.com": 3, "fortune.com": 3,
    "e360.yale.edu": 3, "grist.org": 3, "insideclimatenews.org": 3,
    "dawn.com": 3, "arabnews.com": 3, "middleeasteye.net": 3,
    "eldiario.es": 3, "publico.es": 3, "elperiodico.com": 3,
    "semana.com": 3, "emol.com": 3, "elcomercio.pe": 3,
    # Alertas/PR nivel 4
    "techcrunch.com": 4, "xataka.com": 4, "genbeta.com": 4, "venturebeat.com": 4,
    "coindesk.com": 4, "cointelegraph.com": 4, "decrypt.co": 4,
}

_ORG_DOMINIO = {
    # Agencias
    "reuters.com": "Reuters", "apnews.com": "AP", "ap.org": "AP",
    "afp.com": "AFP", "efe.com": "EFE",
    "factual.afp.com": "AFP Factual", "factcheck.afp.com": "AFP Factual",
    # Ciencia/institución
    "nature.com": "Nature", "science.org": "Science",
    "technologyreview.com": "MIT Technology Review",
    "arstechnica.com": "Ars Technica", "ieee.org": "IEEE",
    "spectrum.ieee.org": "IEEE",
    "who.int": "OMS", "nih.gov": "NIH", "nasa.gov": "NASA",
    "cdc.gov": "CDC", "un.org": "ONU",
    "newscientist.com": "New Scientist", "agenciasinc.es": "SINC",
    "scientificamerican.com": "Scientific American",
    "nationalgeographic.com": "Nat Geo",
    "sciencenews.org": "Science News", "statnews.com": "STAT News",
    "phys.org": "Phys.org",
    # Prensa anglosajona referencia
    "bbc.com": "BBC", "bbc.co.uk": "BBC",
    "ft.com": "FT", "bloomberg.com": "Bloomberg",
    "nytimes.com": "NYT", "wsj.com": "WSJ",
    "economist.com": "Economist", "npr.org": "NPR",
    "theguardian.com": "Guardian", "washingtonpost.com": "Washington Post",
    "aljazeera.com": "Al Jazeera",
    "france24.com": "France 24", "dw.com": "DW",
    "euronews.com": "Euronews", "swissinfo.ch": "Swissinfo",
    "abcnews.go.com": "ABC News", "nbcnews.com": "NBC News",
    "cbsnews.com": "CBS News", "cbc.ca": "CBC",
    "independent.co.uk": "The Independent",
    "axios.com": "Axios", "politico.com": "Politico",
    "theatlantic.com": "The Atlantic",
    "foreignpolicy.com": "Foreign Policy",
    "foreignaffairs.com": "Foreign Affairs",
    "cnbc.com": "CNBC", "businessinsider.com": "Business Insider",
    "fortune.com": "Fortune",
    # Asia/Oriente Medio
    "nhk.or.jp": "NHK World", "nhk.jp": "NHK World",
    "scmp.com": "SCMP", "thehindu.com": "The Hindu",
    "dawn.com": "Dawn", "arabnews.com": "Arab News",
    "middleeasteye.net": "Middle East Eye",
    # España
    "rtve.es": "RTVE", "elpais.com": "El País",
    "elmundo.es": "El Mundo", "lavanguardia.com": "La Vanguardia",
    "elconfidencial.com": "El Confidencial", "europapress.es": "Europapress",
    "eldiario.es": "El Diario", "publico.es": "Público",
    "elperiodico.com": "El Periódico",
    # Latam
    "infobae.com": "Infobae", "clarin.com": "Clarín",
    "lanacion.com.ar": "La Nación", "eltiempo.com": "El Tiempo",
    "semana.com": "Semana", "latercera.com": "La Tercera",
    "emol.com": "Emol", "elcomercio.pe": "El Comercio",
    # Fact-checkers
    "maldita.es": "Maldita", "newtral.es": "Newtral",
    "fullfact.org": "Full Fact", "chequeado.com": "Chequeado",
    "politifact.com": "PolitiFact", "animalpolitico.com": "Animal Político",
    # Tech
    "wired.com": "Wired", "theverge.com": "The Verge",
    "404media.co": "404 Media", "techcrunch.com": "TechCrunch",
    "xataka.com": "Xataka", "genbeta.com": "Genbeta",
    "openai.com": "OpenAI", "anthropic.com": "Anthropic",
    "deepmind.google": "DeepMind", "techmeme.com": "Techmeme",
    "venturebeat.com": "VentureBeat", "cnet.com": "CNET",
    "engadget.com": "Engadget", "theregister.com": "The Register",
    # Medioambiente
    "carbonbrief.org": "Carbon Brief",
    "e360.yale.edu": "Yale E360", "grist.org": "Grist",
    # Cripto
    "coindesk.com": "CoinDesk", "cointelegraph.com": "Cointelegraph",
    "decrypt.co": "Decrypt",
}

NIVEL_FEED = {
    # Agencias nivel 1
    "Reuters": 1, "Reuters ES": 1, "Reuters Tech": 1, "Reuters AI": 1,
    "Reuters World": 1, "Reuters Science": 1, "Reuters Health": 1,
    "Reuters Business": 1, "Reuters Sport": 1, "Reuters Environment": 1,
    "AP News": 1, "AP Tech": 1, "AP World": 1, "AFP": 1, "AFP Factual": 1, "EFE": 1,
    # Instituciones nivel 1
    "OMS/WHO": 1, "NIH": 1, "NASA": 1, "CDC": 1, "ONU Noticias": 1,
    # Ciencia nivel 1
    "Nature": 1, "Science": 1,
    "MIT Tech Review": 1, "MIT Tech Review AI": 1,
    "Ars Technica AI": 1, "IEEE Spectrum": 1,
    "Science News": 1, "STAT News": 1, "Phys.org": 1,
    "Scientific American": 1, "Nat Geo": 1,
    # Prensa de referencia nivel 2
    "BBC": 2, "BBC Tech": 2, "BBC Mundo": 2, "BBC Science": 2,
    "BBC Health": 2, "BBC World": 2, "BBC Business": 2, "BBC Sport": 2,
    "BBC Europa": 2, "BBC Entertainment": 2, "BBC Medio Ambiente": 2,
    "FT Tech": 2, "FT AI": 2, "Bloomberg Tech": 2, "Bloomberg Markets": 2,
    "NYT Tech": 2, "El País Tech": 2, "Guardian AI": 2,
    "Maldita Tecnología": 2, "NPR": 2, "New Scientist": 2,
    "Al Jazeera": 2, "France 24": 2, "France 24 ES": 2, "DW English": 2,
    "DW Español": 2, "Euronews ES": 2, "RTVE": 2, "CNN Español": 2,
    "Swissinfo ES": 2, "RFI Español": 2,
    "NHK World": 2, "SCMP": 2, "The Hindu": 2,
    "ABC News": 2, "NBC News": 2, "CBS News": 2, "CBC Canada": 2,
    "The Independent": 2, "Axios": 2, "Politico": 2,
    "The Atlantic": 2, "Foreign Policy": 2, "Foreign Affairs": 2,
    "CNBC": 2, "Maldita": 2, "Newtral": 2, "Full Fact": 2,
    "Chequeado AR": 2, "Animal Político MX": 2, "PolitiFact": 2,
    "El País": 2, "El Mundo": 2, "La Vanguardia": 2, "Europapress": 2,
    "Infobae": 2, "Clarín": 2, "La Nación AR": 2, "El Tiempo CO": 2,
    "La Tercera CL": 2, "Carbon Brief": 2, "Yale E360": 2,
    "El País Bienestar": 2, "El País Clima": 2, "El País España": 2,
    "Science Daily": 2, "El Mundo Salud": 2, "El Mundo Ciencia": 2,
    "MedlinePlus": 2,
    # Especialistas nivel 3
    "Wired": 3, "Wired AI": 3, "The Verge": 3, "The Verge AI": 3,
    "OpenAI": 3, "Techmeme": 3, "404 Media": 3,
    "CNET": 3, "Engadget": 3, "The Register": 3,
    "Business Insider": 3, "Fortune": 3,
    "Dawn": 3, "Arab News": 3, "Middle East Eye": 3,
    "Grist": 3, "El Diario": 3, "Público": 3, "El Periódico": 3,
    "Semana CO": 3, "Emol CL": 3, "BioBio CL": 3,
    "El Comercio PE": 3, "RPP PE": 3, "El Universo EC": 3,
    "El País UY": 3, "El Observador UY": 3, "El Nacional VE": 3,
    # Alertas/PR nivel 4
    "TechCrunch": 4, "Xataka": 4, "Genbeta": 4, "VentureBeat": 4,
    "CoinDesk": 4, "Cointelegraph": 4, "Decrypt": 4,
    "20 Minutos": 4, "ABC España": 4, "El Español": 4, "Cadena SER": 4,
    "Perfil AR": 4, "El Universal MX": 4, "Milenio MX": 4,
    "Proceso MX": 4, "El Financiero MX": 4,
}

TIPO_NIVEL = {
    1: "agencia o ciencia revisada",
    2: "prensa de referencia",
    3: "especialista",
    4: "alerta o PR",
}

_FACT_CHECKERS = ("maldita", "newtral", "full fact", "afp factual", "efe verifica")

# Temas predefinidos → query de búsqueda
CATEGORIAS = {
    "tecnologia": "tecnologia",
    "ia": "inteligencia artificial OR AI OR openai OR anthropic",
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
        ("https://www.nih.gov/news-events/news-releases/feed",                 "NIH"),
        ("https://www.cdc.gov/media/feeds/news.xml",                          "CDC"),
        ("https://www.statnews.com/feed/",                                    "STAT News"),
        ("https://phys.org/rss-feed.xml",                                     "Phys.org"),
        ("http://feeds.bbci.co.uk/news/health/rss.xml",                       "BBC Health"),
        ("https://medlineplus.gov/rss/healthnews.xml",                        "MedlinePlus"),
        ("https://www.elmundo.es/rss/salud.xml",                              "El Mundo Salud"),
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/bienestar", "El País Bienestar"),
        ("https://www.infobae.com/feeds/rss/salud/",                          "Infobae Salud"),
        (_gnews_site("reuters.com", "health OR medicine"),                    "Reuters Health"),
    ],
    "nutricion": [
        ("https://www.who.int/rss-feeds/news-english.xml",                    "OMS/WHO"),
        ("https://medlineplus.gov/rss/healthnews.xml",                        "MedlinePlus"),
        ("https://www.nih.gov/news-events/news-releases/feed",                 "NIH"),
        ("http://feeds.bbci.co.uk/news/health/rss.xml",                       "BBC Health"),
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/bienestar", "El País Bienestar"),
        ("https://www.elmundo.es/rss/salud.xml",                              "El Mundo Salud"),
    ],
    "ciencia": [
        ("https://www.nature.com/nature.rss",                                 "Nature"),
        ("https://www.science.org/rss/news_current.xml",                      "Science"),
        ("https://www.nasa.gov/rss/dyn/breaking_news.rss",                    "NASA"),
        ("https://www.sciencenews.org/feed",                                  "Science News"),
        ("https://phys.org/rss-feed.xml",                                     "Phys.org"),
        ("http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",      "BBC Science"),
        (_gnews_site("reuters.com", "science OR research"),                   "Reuters Science"),
        ("https://www.newscientist.com/subject/technology/feed/",             "New Scientist"),
        ("https://www.scientificamerican.com/platform/morgue/rss/",           "Scientific American"),
        ("https://www.elmundo.es/rss/ciencia.xml",                            "El Mundo Ciencia"),
        ("https://www.sciencedaily.com/rss/all.xml",                          "Science Daily"),
    ],
    "tecnologia": [
        ("http://feeds.bbci.co.uk/news/technology/rss.xml",                   "BBC Tech"),
        (_gnews_site("reuters.com", "technology OR AI OR chip"),              "Reuters Tech"),
        (_gnews_site("apnews.com", "technology OR AI"),                       "AP Tech"),
        ("https://www.technologyreview.com/feed/",                            "MIT Tech Review"),
        ("https://arstechnica.com/ai/feed/",                                  "Ars Technica AI"),
        ("https://spectrum.ieee.org/feeds/feed.rss",                          "IEEE Spectrum"),
        ("https://feeds.bloomberg.com/technology/news.rss",                   "Bloomberg Tech"),
        ("https://www.ft.com/technology?format=rss",                          "FT Tech"),
        ("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",       "NYT Tech"),
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada", "El País Tech"),
        ("https://www.wired.com/feed/rss",                                    "Wired"),
        ("https://www.theverge.com/rss/index.xml",                            "The Verge"),
        ("https://venturebeat.com/feed/",                                     "VentureBeat"),
        ("https://www.cnet.com/rss/news/",                                    "CNET"),
        ("https://www.engadget.com/rss.xml",                                  "Engadget"),
        ("https://www.theregister.com/headlines.atom",                        "The Register"),
        ("https://techcrunch.com/feed/",                                      "TechCrunch"),
        ("https://feeds.weblogssl.com/xataka",                                "Xataka"),
    ],
    "ia": [
        ("https://www.technologyreview.com/topic/artificial-intelligence/feed", "MIT Tech Review AI"),
        ("https://arstechnica.com/ai/feed/",                                  "Ars Technica AI"),
        ("https://spectrum.ieee.org/feeds/feed.rss",                          "IEEE Spectrum"),
        ("https://www.nature.com/nature.rss",                                 "Nature"),
        ("https://www.science.org/rss/news_current.xml",                      "Science"),
        ("https://www.ft.com/artificial-intelligence?format=rss",             "FT AI"),
        ("https://www.theguardian.com/technology/artificialintelligenceai/rss", "Guardian AI"),
        ("https://www.wired.com/feed/tag/ai/latest/rss",                      "Wired AI"),
        ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge AI"),
        ("https://feeds.bloomberg.com/technology/news.rss",                   "Bloomberg Tech"),
        ("http://feeds.bbci.co.uk/news/technology/rss.xml",                   "BBC Tech"),
        (_gnews_site("reuters.com", "artificial intelligence OR AI OR OpenAI OR Anthropic"), "Reuters AI"),
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada", "El País Tech"),
        ("https://maldita.es/malditatecnologia/feed",                         "Maldita Tecnología"),
        ("https://openai.com/news/rss.xml",                                   "OpenAI"),
        ("https://www.techmeme.com/feed.xml",                                 "Techmeme"),
        ("https://venturebeat.com/feed/",                                     "VentureBeat"),
        ("https://techcrunch.com/feed/",                                      "TechCrunch"),
    ],
    "economia": [
        (_gnews_site("reuters.com", "business OR economy OR markets"),         "Reuters Business"),
        ("http://feeds.bbci.co.uk/news/business/rss.xml",                     "BBC Business"),
        ("https://feeds.bloomberg.com/markets/news.rss",                      "Bloomberg Markets"),
        ("https://www.ft.com/economics?format=rss",                           "FT Tech"),
        ("https://www.cnbc.com/id/100003114/device/rss/rss.html",             "CNBC"),
        ("https://feeds.businessinsider.com/custom/all",                      "Business Insider"),
        ("https://fortune.com/feed/fortune-feeds/?id=3230629",                "Fortune"),
        ("https://www.expansion.com/rss/economia.xml",                        "Expansión"),
        ("https://cincodias.elpais.com/rss/",                                 "Cinco Días"),
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
        (_gnews_site("reuters.com", "sports OR football OR tennis"),           "Reuters Sport"),
        ("https://www.marca.com/rss/portada.xml",                             "Marca"),
    ],
    "mundo": [
        ("http://feeds.bbci.co.uk/news/world/rss.xml",                        "BBC World"),
        ("https://www.aljazeera.com/xml/rss/all.xml",                         "Al Jazeera"),
        (_gnews_site("reuters.com", "world OR international", hl="es", gl="ES"), "Reuters World"),
        ("https://www.france24.com/es/rss",                                   "France 24 ES"),
        ("https://rss.dw.com/rdf/rss-en-es",                                  "DW Español"),
        (_gnews_site("apnews.com", "world"),                                  "AP World"),
        ("https://www3.nhk.or.jp/nhkworld/en/news/feeds/",                   "NHK World"),
        ("https://www.scmp.com/rss/91/feed",                                  "SCMP"),
        ("https://news.un.org/feed/subscribe/es/news/all/rss.xml",            "ONU Noticias"),
    ],
    "politica": [
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/espana", "El País España"),
        ("https://www.elmundo.es/rss/espana.xml",                             "El Mundo España"),
        ("https://rss.politico.com/politics-news.xml",                        "Politico"),
        ("https://www.theatlantic.com/feed/all/",                             "The Atlantic"),
        ("http://feeds.bbci.co.uk/news/world/europe/rss.xml",                 "BBC Europa"),
        (_gnews_site("reuters.com", "politics OR government OR election"),     "Reuters"),
    ],
    "entretenimiento": [
        ("https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/cultura", "El País Cultura"),
        ("https://www.elmundo.es/rss/cultura.xml",                            "El Mundo Cultura"),
        ("http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",       "BBC Entertainment"),
    ],
    "medioambiente": [
        ("http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",      "BBC Medio Ambiente"),
        ("https://www.carbonbrief.org/feed/",                                 "Carbon Brief"),
        ("https://e360.yale.edu/feed",                                        "Yale E360"),
        ("https://grist.org/feed/",                                           "Grist"),
        (_gnews_site("reuters.com", "climate OR environment"),                "Reuters Environment"),
        ("https://www.nasa.gov/rss/dyn/breaking_news.rss",                    "NASA"),
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
    "ia":             ["inteligencia artificial", "artificial intelligence", "chatgpt",
                       "openai", "anthropic", "deepmind", "machine learning",
                       "aprendizaje automático", "llm", "gpt", "claude", "gemini",
                       "grok", "hugging face", "midjourney"],
    "medioambiente":  ["clima", "cambio climático", "medio ambiente", "sostenible",
                       "emisiones", "co2", "ecología", "ecologia", "biodiversidad",
                       "renovable", "energía verde", "contaminación"],
    "tecnologia":     ["tecnología", "tecnologia", "tech", "robot", "software",
                       "hardware", "app", "startup", "google", "apple",
                       "microsoft", "meta", "nvidia", "semiconductor", "chip"],
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


def _dominio_de(url: str) -> str:
    try:
        d = urllib.parse.urlparse(url or "").netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


def _lookup_dominio(mapa: dict, dominio: str, default=None):
    if not dominio:
        return default
    if dominio in mapa:
        return mapa[dominio]
    for d, val in mapa.items():
        if dominio == d or dominio.endswith("." + d):
            return val
    return default


def _org_de_nombre(nombre: str) -> str:
    return re.sub(
        r"\s+(AI|Tech|World|Health|Science|Business|Sport|Markets|ES|Español|Environment)$",
        "",
        nombre or "",
    ).strip() or (nombre or "desconocida")


def _nivel_y_org(fuente: str, url: str, nombre_feed: str | None = None) -> tuple[int, str]:
    dominio = _dominio_de(url)
    nivel = _lookup_dominio(NIVEL_DOMINIO, dominio)
    org = _lookup_dominio(_ORG_DOMINIO, dominio)
    nivel_feed = NIVEL_FEED.get(nombre_feed or "") or NIVEL_FEED.get(fuente or "")
    if nivel is None:
        nivel = nivel_feed if nivel_feed is not None else 3
    elif nivel_feed is not None:
        nivel = min(int(nivel), int(nivel_feed))
    if org is None:
        org = _org_de_nombre(nombre_feed or fuente or dominio)
    return int(nivel), org


def _item_desde_entry(entry, nombre_fallback: str, categoria: str | None = None,
                      verificada: bool | None = None) -> dict:
    fecha = entry.get("published", "") or entry.get("updated", "")
    link = entry.get("link", "")
    fuente = nombre_fallback
    fuente_url = link
    source = getattr(entry, "source", None)
    if source is not None:
        if getattr(source, "title", None):
            fuente = source.title
        if getattr(source, "href", None):
            fuente_url = source.href
    nivel, org = _nivel_y_org(fuente, fuente_url or link, nombre_feed=nombre_fallback)
    if verificada is None:
        verificada = True
    item = {
        "titulo": entry.get("title", ""),
        "link": link,
        "fuente": fuente,
        "fecha": fecha,
        "resumen": entry.get("summary", ""),
        "recencia": calcular_recencia(fecha),
        "fuente_verificada": verificada,
        "nivel_fuente": nivel,
        "org_fuente": org,
        "confirmada": False,
        "fuentes_confirmacion": [org],
        "fuentes_detalle": [{
            "org": org, "fuente": fuente, "url": link,
            "nivel": nivel, "rol": "origen",
        }],
        "n_fuentes": 1,
    }
    if categoria:
        item["categoria_detectada"] = categoria
    return documentar_procedencia(item)


def _match_palabra(texto: str, p: str) -> bool:
    if len(p) <= 3:
        return re.search(rf"(^|[^a-z0-9áéíóúñ]){re.escape(p)}([^a-z0-9áéíóúñ]|$)", texto) is not None
    return p in texto


def detectar_categoria(tema: str) -> str | None:
    """Detecta la categoría temática de un texto libre. Devuelve None si no hay match claro."""
    tema_lower = tema.lower()
    puntuaciones: dict[str, int] = {}
    for cat, palabras in _PALABRAS_CATEGORIA.items():
        score = sum(1 for p in palabras if _match_palabra(tema_lower, p))
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
                resultado.append(_item_desde_entry(entry, nombre, categoria=categoria))
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
    dominio = _dominio_de(link)
    if not dominio:
        return False
    return any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_CONFIABLES)


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
                resultado.append(_item_desde_entry(entry, nombre))
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
        fuente_url = ""
        if hasattr(entry, "source") and hasattr(entry.source, "title"):
            fuente = entry.source.title
        if hasattr(entry, "source") and hasattr(entry.source, "href"):
            fuente_url = entry.source.href

        link = entry.link
        # entry.link es siempre un redirect de news.google.com; el dominio
        # real del medio viene en entry.source.href.
        verificada = _es_dominio_confiable(fuente_url or link)

        if solo_confiables and not verificada:
            continue

        item = _item_desde_entry(entry, fuente or "Google News", verificada=verificada)
        item["link"] = link
        noticias.append(item)

        if len(noticias) >= max_resultados:
            break

    return noticias


_STOP_TITULO = {
    "the", "and", "for", "with", "from", "that", "this", "after", "over",
    "says", "said", "about", "into", "have", "will", "been", "were",
    "sobre", "para", "como", "desde", "entre", "hasta", "cuando",
    "una", "unos", "unas", "del", "las", "los", "por", "con", "que",
    "after", "their", "they", "what", "when", "more", "than",
}


def _tokens_titulo(titulo: str) -> set[str]:
    t = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode()
    t = t.lower()
    t = re.sub(r"\s*[-—|:]\s*[^|-]{0,40}$", "", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return {w for w in t.split() if len(w) > 3 and w not in _STOP_TITULO}


def _sim_titulo(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _es_fact_checker(org: str) -> bool:
    o = (org or "").lower()
    return any(fc in o for fc in _FACT_CHECKERS)


def documentar_procedencia(item: dict) -> dict:
    """Rellena origen, verificadores y un texto de procedencia listo para citar."""
    origen = item.get("org_fuente") or item.get("fuente") or "desconocida"
    nivel = int(item.get("nivel_fuente") or 3)
    tipo = TIPO_NIVEL.get(nivel, "medio")
    orgs = [o for o in (item.get("fuentes_confirmacion") or [origen]) if o]
    if origen not in orgs:
        orgs = [origen] + orgs
    verificadores = [o for o in orgs if o != origen]
    fact_checkers = [o for o in orgs if _es_fact_checker(o)]

    if fact_checkers:
        estado = "fact_check"
    elif len(orgs) >= 2:
        estado = "contrastada"
    elif nivel <= 2:
        estado = "redaccion_propia"
    else:
        estado = "sin_contrastar"

    partes = [f"Sale de {origen} ({tipo})."]
    if fact_checkers:
        partes.append(f"Verificada por {', '.join(fact_checkers)}.")
    otros = [v for v in verificadores if v not in fact_checkers]
    if otros:
        partes.append(f"Contrastada por {', '.join(otros)}.")
    elif estado == "redaccion_propia":
        partes.append(
            "La redacción aplica verificación interna; no hay segunda redacción independiente en este barrido."
        )
    elif estado == "sin_contrastar":
        partes.append("Sin contrastar en otro medio independiente.")

    item["origen"] = origen
    item["origen_tipo"] = tipo
    item["verificadores"] = verificadores
    item["fact_checkers"] = fact_checkers
    item["estado_verificacion"] = estado
    item["documentacion"] = " ".join(partes)
    return item


def _detalle_de(it: dict, rol: str) -> dict:
    org = it.get("org_fuente") or it.get("fuente") or ""
    return {
        "org": org,
        "fuente": it.get("fuente") or org,
        "url": it.get("link") or "",
        "nivel": it.get("nivel_fuente", 3),
        "rol": rol,
    }


def confirmar_historias(items: list, umbral: float = 0.42, colapsar: bool = True) -> list:
    """Agrupa la misma historia en medios distintos. confirmada = 2+ orgs independientes.

    Si colapsar=True, deja un ítem por cluster (mejor nivel, luego más reciente)
    y lista las demás redacciones en fuentes_confirmacion.
    """
    if not items:
        return items

    tokens = [_tokens_titulo(it.get("titulo", "")) for it in items]
    usado = [False] * len(items)
    clusters: list[list[int]] = []

    for i in range(len(items)):
        if usado[i]:
            continue
        cluster = [i]
        usado[i] = True
        for j in range(i + 1, len(items)):
            if usado[j]:
                continue
            if _sim_titulo(tokens[i], tokens[j]) >= umbral:
                cluster.append(j)
                usado[j] = True
        clusters.append(cluster)

    resultado = []
    for cluster in clusters:
        orgs = []
        for i in cluster:
            org = items[i].get("org_fuente") or items[i].get("fuente") or ""
            if org and org not in orgs:
                orgs.append(org)
        confirmada = len(orgs) >= 2

        def _rank(i: int):
            it = items[i]
            horas = (it.get("recencia") or {}).get("horas")
            return (it.get("nivel_fuente", 5), horas if horas is not None else 9999.0)

        mejor = min(cluster, key=_rank)
        origen_org = items[mejor].get("org_fuente") or items[mejor].get("fuente") or ""
        detalle, vistos = [], set()
        for i in cluster:
            org = items[i].get("org_fuente") or items[i].get("fuente") or ""
            if not org or org in vistos:
                continue
            vistos.add(org)
            if org == origen_org:
                rol = "origen"
            elif _es_fact_checker(org):
                rol = "fact_check"
            else:
                rol = "contraste"
            detalle.append(_detalle_de(items[i], rol))

        if colapsar:
            elegido = dict(items[mejor])
            elegido["confirmada"] = confirmada
            elegido["fuentes_confirmacion"] = orgs
            elegido["fuentes_detalle"] = detalle
            elegido["n_fuentes"] = len(orgs)
            resultado.append(documentar_procedencia(elegido))
        else:
            for i in cluster:
                items[i]["confirmada"] = confirmada
                items[i]["fuentes_confirmacion"] = orgs
                items[i]["fuentes_detalle"] = detalle
                items[i]["n_fuentes"] = len(orgs)
                documentar_procedencia(items[i])
            resultado.extend(items[i] for i in cluster)

    return resultado


def _score_relevancia(item: dict) -> float:
    """Puntuación de relevancia: prioriza noticias cubiertas por varias fuentes de calidad."""
    n = item.get("n_fuentes", 1)
    nivel = item.get("nivel_fuente", 3)
    horas = (item.get("recencia") or {}).get("horas") or 9999.0

    # Multi-fuente: cada fuente adicional suma 60 pts (hasta 4 extra)
    fuentes_pts = min(n - 1, 4) * 60
    # Calidad: nivel 1 → 40, nivel 2 → 20, nivel 3 → 0, nivel 4 → −10
    calidad_pts = max(-10, (3 - nivel) * 20)
    # Recencia (decae por tramos)
    if horas < 1:
        rec_pts = 20
    elif horas < 6:
        rec_pts = 16
    elif horas < 24:
        rec_pts = 10
    elif horas < 72:
        rec_pts = 4
    elif horas < 168:
        rec_pts = 1
    else:
        rec_pts = 0

    return fuentes_pts + calidad_pts + rec_pts


def buscar_variadas(temas=None, por_tema: int = 3, pais: str = "ES") -> list:
    """
    Junta noticias de varias fuentes:
    1. Feeds RSS directos de fuentes verificadas (prioridad)
    2. Google News filtrado por tema y dominio confiable

    Resultado ordenado por relevancia: noticias cubiertas por varias fuentes
    de alta calidad van primero; dentro del mismo score, las más recientes.
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

    # Combinar y agrupar historias duplicadas
    todos = directas + google_news
    agrupados = confirmar_historias(todos, umbral=0.42, colapsar=True)

    # Calcular score y ordenar (mayor score primero)
    for item in agrupados:
        item["score_noticia"] = round(_score_relevancia(item), 1)

    agrupados.sort(key=lambda it: -it["score_noticia"])
    return agrupados


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
