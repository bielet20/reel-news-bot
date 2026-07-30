"""
trending_finder.py
Encuentra contenido viral/en tendencia sin necesitar API keys:
  - buscar_trending_youtube(): YouTube search por temas trending, ordenado por visualizaciones
  - buscar_trending_noticias(): Google Trends -> Google News RSS
"""

import json
import re
import urllib.parse

import feedparser
import requests

_HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

# Cookie que bypasea la pantalla de consentimiento de cookies de Google/YouTube
_SOCS_COOKIE = {
    "SOCS": "CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMwODI5LjA3X3AwGgJlbiAD"
}

# URL de busqueda de YouTube con orden por visualizaciones (sp = sort by view count)
_YT_SEARCH_URL = "https://www.youtube.com/results"
_YT_SP_VIEW_COUNT = "CAMSAhAB"


# ---------------------------------------------------------------------------
# Helpers para parsear la data embebida en paginas de YouTube
# ---------------------------------------------------------------------------

def _parsear_ytInitialData(html: str) -> dict:
    """
    YouTube embebe los datos en 'var ytInitialData = {...};' en el HTML inicial.
    Funciona sin JavaScript, solo con requests.
    """
    m = re.search(
        r'var ytInitialData\s*=\s*(\{.+?\});\s*(?:var |window\.|</script>)',
        html, re.DOTALL,
    )
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _buscar_en_data(obj, clave: str, resultados: list = None) -> list:
    """Recorre recursivamente el JSON de YouTube buscando dicts con 'clave'."""
    if resultados is None:
        resultados = []
    if isinstance(obj, dict):
        if clave in obj:
            resultados.append(obj[clave])
        else:
            for v in obj.values():
                _buscar_en_data(v, clave, resultados)
    elif isinstance(obj, list):
        for item in obj:
            _buscar_en_data(item, clave, resultados)
    return resultados


def _texto_desde_yt(obj) -> str:
    """Extrae texto de los formatos 'simpleText' o 'runs' de YouTube."""
    if not obj:
        return ""
    if isinstance(obj, dict):
        if "simpleText" in obj:
            return obj["simpleText"]
        if "runs" in obj:
            return "".join(r.get("text", "") for r in obj["runs"])
    return ""


def _buscar_videos_en_youtube(query: str, max_resultados: int = 5) -> list:
    """
    Busca en YouTube ordenando por visualizaciones y devuelve los primeros
    resultados como lista de dicts con titulo/canal/url/views/hace_cuanto.
    """
    params = {
        "search_query": query,
        "sp": _YT_SP_VIEW_COUNT,
    }
    url = f"{_YT_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    try:
        resp = requests.get(
            url, headers=_HEADERS_BROWSER, cookies=_SOCS_COOKIE, timeout=20
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] Error buscando en YouTube '{query}': {e}")
        return []

    data = _parsear_ytInitialData(resp.text)
    if not data:
        return []

    renderers = _buscar_en_data(data, "videoRenderer")
    videos = []
    for r in renderers[:max_resultados]:
        video_id = r.get("videoId", "")
        if not video_id:
            continue
        titulo = _texto_desde_yt(r.get("title", {}))
        canal = _texto_desde_yt(r.get("ownerText", r.get("shortBylineText", {})))
        views = _texto_desde_yt(r.get("viewCountText", {}))
        hace = _texto_desde_yt(r.get("publishedTimeText", {}))
        desc = _texto_desde_yt(r.get("descriptionSnippet", {}))

        if not titulo or not video_id:
            continue

        yt_url = f"https://www.youtube.com/watch?v={video_id}"
        videos.append({
            "titulo": titulo,
            "canal": canal,
            "url": yt_url,
            "video_id": video_id,
            "visualizaciones": views,
            "hace_cuanto": hace,
            "fuente": canal or "YouTube",
            "link": yt_url,
            "resumen": desc or (f"{canal} · {views}" if canal else views),
            "fecha": hace,
            "tema": "youtube_trending",
        })
    return videos


# ---------------------------------------------------------------------------
# API publica: tendencias de YouTube
# ---------------------------------------------------------------------------

def buscar_trending_youtube(pais: str = "AR", max_resultados: int = 10) -> list:
    """
    Encuentra videos de YouTube con muchas visualizaciones sobre los temas en
    tendencia del dia en el pais indicado.

    Flujo: Google Trends (topics del dia) -> YouTube search (sort: view count).
    No requiere ningun API key.

    pais: codigo ISO 3166-1 alpha-2 (AR, US, ES, MX, CO, ...)

    Devuelve lista de dicts con:
        titulo, canal, url, video_id, visualizaciones, hace_cuanto,
        fuente, link, resumen, tema  (compatibles con el pipeline de noticias)
    """
    print(f"   -> Buscando tendencias de YouTube ({pais})...")

    temas = buscar_temas_trending(pais)
    if not temas:
        # Fallback: buscar por terminos generales en espanol
        temas = ["noticias", "viral", "tecnologia", "deportes"]
    else:
        temas = temas[:5]

    print(f"   Temas para buscar en YouTube: {', '.join(temas[:3])}...")

    todos = []
    por_tema = max(1, max_resultados // len(temas) + 1)
    for tema in temas:
        videos = _buscar_videos_en_youtube(tema, max_resultados=por_tema)
        # Evitar duplicados por video_id
        ids_vistos = {v["video_id"] for v in todos}
        for v in videos:
            if v["video_id"] not in ids_vistos:
                todos.append(v)
                ids_vistos.add(v["video_id"])
        if len(todos) >= max_resultados:
            break

    result = todos[:max_resultados]
    if result:
        print(f"   Encontrados {len(result)} videos trending.")
    else:
        print("[WARN] No se encontraron videos trending.")
    return result


# ---------------------------------------------------------------------------
# API publica: tendencias de Google Trends
# ---------------------------------------------------------------------------

def buscar_temas_trending(pais: str = "AR") -> list:
    """
    Obtiene los temas en tendencia hoy via Google Trends RSS.
    pais: codigo ISO 3166-1 alpha-2 (AR, US, ES, MX, CO, ...)
    Devuelve lista de strings con los temas mas buscados (puede estar vacia).
    """
    # Nuevo endpoint de Google Trends (el viejo /daily/rss fue deprecado)
    url = f"https://trends.google.com/trending/rss?geo={pais}"
    try:
        resp = requests.get(url, headers=_HEADERS_BROWSER, timeout=15)
        if resp.status_code != 200:
            return []
        # feedparser puede parsear directamente el texto del RSS
        feed = feedparser.parse(resp.text)
        temas = [e.title for e in feed.entries if e.get("title")]
        return temas
    except Exception:
        return []


def buscar_trending_noticias(pais: str = "AR", max_resultados: int = 10,
                              max_por_tema: int = 2) -> list:
    """
    Combina Google Trends + Google News RSS para encontrar noticias sobre los
    temas mas buscados del dia en el pais indicado.

    pais: codigo ISO 3166-1 alpha-2 (AR, US, ES, MX, CO, ...)

    Devuelve lista de dicts compatibles con el pipeline de noticias:
        titulo, link, fuente, fecha, resumen, tema, tema_tendencia
    """
    from news_fetcher import buscar_noticias, buscar_variadas

    print(f"   -> Obteniendo temas en tendencia de Google Trends ({pais})...")
    temas = buscar_temas_trending(pais)

    if not temas:
        print("[WARN] No se pudieron obtener temas de Google Trends. "
              "Usando categorias generales como respaldo.")
        return buscar_variadas(por_tema=max_por_tema)

    top_temas = temas[:min(6, len(temas))]
    print(f"   Temas trending: {', '.join(top_temas[:5])}")

    todas = []
    for tema in top_temas:
        noticias = buscar_noticias(tema, max_resultados=max_por_tema)
        for n in noticias:
            n["tema"] = "trending"
            n["tema_tendencia"] = tema
        todas.extend(noticias)
        if len(todas) >= max_resultados:
            break

    return todas[:max_resultados]


if __name__ == "__main__":
    print("=== Google Trends AR ===")
    temas = buscar_temas_trending("AR")
    for t in temas[:8]:
        print(" -", t)

    print("\n=== YouTube Trending AR (top 5) ===")
    videos = buscar_trending_youtube(pais="AR", max_resultados=5)
    for v in videos:
        print(f"  [{v['visualizaciones']}] {v['titulo'][:55]} — {v['canal']} ({v['hace_cuanto']})")

    print("\n=== Noticias Trending AR (top 5) ===")
    noticias = buscar_trending_noticias(pais="AR", max_resultados=5)
    for n in noticias:
        print(f"  [{n.get('tema_tendencia', '')}] {n['titulo'][:60]}")
