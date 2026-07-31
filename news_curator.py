"""
news_curator.py
Busca noticias de actualidad y las evalúa con IA para proponer
las de mayor potencial viral como reels.
"""

import json
import os


def buscar_y_curar(tema=None, pais="ES", variado=True, n_buscar=25, n_retornar=8):
    """
    Busca noticias y devuelve las más virales ordenadas por score.

    Retorna lista de dicts:
      titulo, titulo_original, fuente, link, resumen,
      score (0-10), categoria, gancho, audiencia
    """
    candidatos = _recopilar(tema, pais, variado, n_buscar)
    if not candidatos:
        return []
    return _curar_con_ia(candidatos, n_retornar)


def _recopilar(tema, pais, variado, n):
    """Obtiene noticias de varias fuentes."""
    from news_fetcher import buscar_noticias, buscar_variadas, CATEGORIAS

    try:
        if variado or not tema:
            pool = buscar_variadas(por_tema=4)
        else:
            query = CATEGORIAS.get(tema.lower(), tema)
            pool = buscar_noticias(query, pais=pais, max_resultados=n)

        # Si hay poco, complementar con trending
        if len(pool) < 6:
            try:
                from trending_finder import buscar_trending_noticias
                pool += buscar_trending_noticias(pais=pais, max_resultados=10)
            except Exception:
                pass

        # Deduplicar por título
        vistos = set()
        unicos = []
        for item in pool:
            key = item["titulo"][:50].lower()
            if key not in vistos:
                vistos.add(key)
                unicos.append(item)

        return unicos[:n]
    except Exception as e:
        print(f"[curator] Error buscando noticias: {e}")
        return []


def _curar_con_ia(noticias, n):
    """Evalúa noticias con Claude y devuelve las top-n rankeadas."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    except ImportError:
        return [_fallback_item(noticias[i], i) for i in range(min(n, len(noticias)))]

    lista_txt = "\n\n".join(
        f"{i+1}. TÍTULO: {item['titulo']}\n"
        f"   FUENTE: {item.get('fuente', '—')}\n"
        f"   RESUMEN: {(item.get('resumen') or '')[:250]}"
        for i, item in enumerate(noticias)
    )

    prompt = f"""Eres experto en contenido viral para redes sociales (TikTok, Instagram Reels, YouTube Shorts).
Analiza estas {len(noticias)} noticias de actualidad y selecciona las {n} con MAYOR potencial viral para un short de 30-60 segundos.

{lista_txt}

Devuelve SOLO este JSON (sin texto adicional, sin markdown):
{{
  "seleccionadas": [
    {{
      "indice": <número 1-{len(noticias)}>,
      "titulo_reel": "<título impactante/curioso para el reel, máx 80 chars>",
      "score": <número 1-10 con un decimal>,
      "categoria": "<tecnologia|economia|mundo|politica|ciencia|salud|deportes|entretenimiento|cripto>",
      "gancho": "<por qué captará atención en 1 frase breve>",
      "audiencia": "<perfil de audiencia en 1 frase muy corta>"
    }}
  ]
}}

Criterios de selección y puntuación:
- 9-10: Impacto masivo, sorprendente, urgente o muy emotivo
- 7-8: Interesante, relevante, genera opinión
- 5-6: Útil o curioso para una audiencia específica
- <5: No seleccionar
Prioriza variedad de categorías. Ordena por score descendente."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        seleccionadas = data.get("seleccionadas", [])

        resultado = []
        for item in seleccionadas:
            idx = item["indice"] - 1
            if 0 <= idx < len(noticias):
                orig = noticias[idx]
                link_real = _resolver_url(orig.get("link", ""))
                resultado.append({
                    "titulo": item.get("titulo_reel", orig["titulo"]),
                    "titulo_original": orig["titulo"],
                    "fuente": orig.get("fuente", ""),
                    "link": link_real,
                    "resumen": orig.get("resumen", ""),
                    "score": round(float(item.get("score", 7.0)), 1),
                    "categoria": item.get("categoria", "general"),
                    "gancho": item.get("gancho", ""),
                    "audiencia": item.get("audiencia", ""),
                })
        return sorted(resultado, key=lambda x: x["score"], reverse=True)

    except Exception as e:
        print(f"[curator] Error IA ({e}), usando fallback")
        return [_fallback_item(noticias[i], i) for i in range(min(n, len(noticias)))]


def _resolver_url(url: str) -> str:
    """Sigue el redirect de Google News RSS para obtener la URL real del artículo."""
    if "news.google.com" not in url:
        return url
    import requests
    try:
        resp = requests.get(
            url, allow_redirects=True, timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ReelBot/1.0)"},
        )
        final = resp.url
        # Si aún apunta a google, intentar extraer de la respuesta
        if "google.com" in final and "news.google.com" not in final:
            return final
        if "google.com" not in final:
            return final
        return url
    except Exception:
        return url


def _fallback_item(noticia, pos):
    return {
        "titulo": noticia["titulo"],
        "titulo_original": noticia["titulo"],
        "fuente": noticia.get("fuente", ""),
        "link": _resolver_url(noticia.get("link", "")),
        "resumen": noticia.get("resumen", ""),
        "score": round(max(4.0, 8.5 - pos * 0.4), 1),
        "categoria": "general",
        "gancho": "",
        "audiencia": "",
    }
