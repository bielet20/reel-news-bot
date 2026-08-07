"""
news_curator.py
Busca noticias de fuentes verificadas y las evalúa con IA para proponer
las de mayor potencial viral como reels. Prioriza primicias y recencia.
"""

import json
import os


def buscar_y_curar(tema=None, pais="ES", variado=True, n_buscar=30, n_retornar=8):
    """
    Busca noticias de fuentes confiables y devuelve las mejores ordenadas por score.

    Retorna lista de dicts:
      titulo, titulo_original, fuente, link, resumen,
      score (0-10), categoria, gancho, audiencia,
      fecha, recencia, fuente_verificada
    """
    candidatos = _recopilar(tema, pais, variado, n_buscar)
    if not candidatos:
        return []
    return _curar_con_ia(candidatos, n_retornar, tema)


def _recopilar(tema, pais, variado, n):
    """Obtiene noticias de fuentes verificadas, priorizando feeds directos."""
    from news_fetcher import (
        buscar_noticias, buscar_variadas, buscar_fuentes_directas,
        buscar_tema_especializado, detectar_categoria,
    )

    try:
        if variado or not tema:
            # Empieza con feeds directos de fuentes verificadas
            pool = buscar_variadas(por_tema=3, pais=pais)
        else:
            # Para tema específico: fuentes especializadas tienen prioridad máxima
            categoria = detectar_categoria(tema)
            if categoria:
                pool = buscar_tema_especializado(tema, max_por_fuente=7)
            else:
                pool = buscar_fuentes_directas(pais=pais, max_por_fuente=5)
            # Complementar con Google News filtrado por dominio confiable
            pool += buscar_noticias(tema, pais=pais, max_resultados=n, solo_confiables=True)

        # Complementar con trending si hay poco
        if len(pool) < 8:
            try:
                from trending_finder import buscar_trending_noticias
                trending = buscar_trending_noticias(pais=pais, max_resultados=10)
                pool += [t for t in trending if t.get("fuente_verificada", False)]
            except Exception:
                pass

        # Deduplicar por título
        vistos = set()
        unicos = []
        for item in pool:
            key = item["titulo"][:50].lower().strip()
            if key not in vistos:
                vistos.add(key)
                unicos.append(item)

        return unicos[:n]
    except Exception as e:
        print(f"[curator] Error buscando noticias: {e}")
        return []


def _curar_con_ia(noticias, n, tema=None):
    """Evalúa noticias con Claude y devuelve las top-n rankeadas."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    except ImportError:
        return [_fallback_item(noticias[i], i) for i in range(min(n, len(noticias)))]

    lista_txt = "\n\n".join(
        f"{i+1}. TÍTULO: {item['titulo']}\n"
        f"   FUENTE: {item.get('fuente', '—')}"
        f"{' ✓VERIFICADA' if item.get('fuente_verificada') else ''}\n"
        f"   RECENCIA: {item.get('recencia', {}).get('label', 'desconocida')}\n"
        f"   RESUMEN: {(item.get('resumen') or '')[:200]}"
        for i, item in enumerate(noticias)
    )

    filtro_tema = (
        f"\nFILTRO DE RELEVANCIA OBLIGATORIO: el usuario busca '{tema}'.\n"
        f"DESCARTA cualquier noticia que NO esté directamente relacionada con '{tema}'.\n"
        f"Solo selecciona noticias donde '{tema}' sea el tema central o muy relevante.\n"
        if tema else ""
    )

    prompt = f"""Eres experto en contenido viral para redes sociales (TikTok, Instagram Reels, YouTube Shorts).
Analiza estas {len(noticias)} noticias de fuentes verificadas y selecciona las {n} con MAYOR potencial viral.
{filtro_tema}
{lista_txt}

Criterios de puntuación (0-10):
- 9-10: Impacto masivo, sorprendente, urgente, emotivo O primicia reciente (<2h)
- 7-8: Interesante, relevante, genera opinión
- 5-6: Útil o curioso para una audiencia específica
- <5: No seleccionar (nunca incluir)

REGLAS:
- Primicias (<2h, <1h) reciben +2 puntos sobre su valor editorial base
- Noticias recientes (<6h) reciben +1 punto
- No selecciones noticias de hace más de 48h salvo impacto extraordinario
- Prioriza variedad de sub-temas dentro de la categoría buscada{(chr(10) + f'- CRÍTICO: Si la noticia no es sobre «{tema}», NO la incluyas aunque sea interesante') if tema else ''}

Devuelve SOLO este JSON (sin texto adicional, sin markdown):
{{
  "seleccionadas": [
    {{
      "indice": <número 1-{len(noticias)}>,
      "titulo_reel": "<título impactante para el reel, máx 80 chars>",
      "score": <número 1-10 con un decimal>,
      "categoria": "<tecnologia|economia|mundo|politica|ciencia|salud|deportes|entretenimiento|cripto>",
      "gancho": "<por qué captará atención en 1 frase breve>",
      "audiencia": "<perfil de audiencia en 1 frase muy corta>"
    }}
  ]
}}

Ordena por score descendente."""

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
                    "fecha": orig.get("fecha", ""),
                    "recencia": orig.get("recencia", {}),
                    "fuente_verificada": orig.get("fuente_verificada", False),
                })
        return sorted(resultado, key=lambda x: x["score"], reverse=True)

    except Exception as e:
        print(f"[curator] Error IA ({e}), usando fallback")
        pool = noticias
        if tema:
            # Filtro básico por palabras del tema cuando la IA falla
            palabras = tema.lower().split()
            relevantes = [
                it for it in pool
                if any(p in (it.get("titulo", "") + it.get("resumen", "")).lower() for p in palabras)
            ]
            pool = relevantes or pool
        return [_fallback_item(pool[i], i) for i in range(min(n, len(pool)))]


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
        "fecha": noticia.get("fecha", ""),
        "recencia": noticia.get("recencia", {}),
        "fuente_verificada": noticia.get("fuente_verificada", False),
    }
