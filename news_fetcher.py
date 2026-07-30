"""
news_fetcher.py
Busca noticias recientes usando los feeds RSS de Google News (gratis, sin API key).
Funciona para cualquier tema/categoria en cualquier idioma soportado por Google News.
"""

import feedparser
import urllib.parse

# Categorias predefinidas -> query de Google News
CATEGORIAS = {
    "tecnologia": "tecnologia",
    "negocios": "negocios OR economia",
    "mundo": "mundo OR internacional",
    "ciencia": "ciencia",
    "salud": "salud",
    "deportes": "deportes",
    "entretenimiento": "entretenimiento OR cine OR musica",
}


def buscar_noticias(tema: str, idioma: str = "es-419", pais: str = "US", max_resultados: int = 10):
    """
    Busca noticias sobre un tema usando el feed RSS de Google News.

    tema: texto libre ("inteligencia artificial", "cambio climatico", ...)
          o una clave de CATEGORIAS ("tecnologia", "mundo", etc.)
    Devuelve una lista de dicts: {titulo, link, fuente, fecha, resumen}
    """
    query = CATEGORIAS.get(tema.lower(), tema)
    query_encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={query_encoded}&hl={idioma}&gl={pais}&ceid={pais}:{idioma}"

    feed = feedparser.parse(url)

    noticias = []
    for entry in feed.entries[:max_resultados]:
        fuente = ""
        if hasattr(entry, "source") and hasattr(entry.source, "title"):
            fuente = entry.source.title
        noticias.append({
            "titulo": entry.title,
            "link": entry.link,
            "fuente": fuente,
            "fecha": entry.get("published", ""),
            "resumen": entry.get("summary", ""),
        })
    return noticias


def buscar_variadas(temas=None, por_tema: int = 3):
    """
    Junta noticias de varios temas distintos para tener un pool 'variado'.
    """
    if temas is None:
        temas = list(CATEGORIAS.keys())
    resultado = []
    for tema in temas:
        items = buscar_noticias(tema, max_resultados=por_tema)
        for it in items:
            it["tema"] = tema
        resultado.extend(items)
    return resultado


if __name__ == "__main__":
    import json
    noticias = buscar_noticias("tecnologia", max_resultados=5)
    print(json.dumps(noticias, indent=2, ensure_ascii=False))
