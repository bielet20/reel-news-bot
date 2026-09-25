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
        buscar_tema_especializado, detectar_categoria, confirmar_historias,
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

        vistos = set()
        unicos = []
        for item in pool:
            key = item["titulo"][:50].lower().strip()
            if key not in vistos:
                vistos.add(key)
                unicos.append(item)

        return confirmar_historias(unicos)[:n]
    except Exception as e:
        print(f"[curator] Error buscando noticias: {e}")
        return []


def _curar_con_ia(noticias, n, tema=None):
    """Evalúa noticias con Claude y devuelve las top-n rankeadas."""
    from llm_local import completar, nube_permitida
    client = None
    if nube_permitida() and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        except ImportError:
            client = None

    lista_txt = "\n\n".join(
        f"{i+1}. TÍTULO: {item['titulo']}\n"
        f"   FUENTE: {item.get('fuente', '—')}"
        f"{' ✓VERIFICADA' if item.get('fuente_verificada') else ''}"
        f"{' ✓CONFIRMADA ' + str(item.get('n_fuentes', 1)) + ' medios' if item.get('confirmada') else ' (1 medio)'}\n"
        f"   NIVEL: {item.get('nivel_fuente', 3)} (1=agencia/ciencia, 2=prensa, 3=especialista, 4=alerta/PR)\n"
        f"   MEDIOS: {', '.join(item.get('fuentes_confirmacion') or [item.get('fuente', '—')])}\n"
        f"   PROCEDENCIA: {item.get('documentacion', '')}\n"
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

    prompt = f"""Eres experto en contenido viral para YouTube Shorts en español. Tu referencia es MrBeast: títulos cortos, cifras exactas, preguntas directas al espectador.
Analiza estas {len(noticias)} noticias y selecciona las {n} con MAYOR potencial viral.
{filtro_tema}
{lista_txt}

Criterios de puntuación (0-10):
- 9-10: Marca conocida (NASA, Apple, Tesla, SpaceX, Google, OpenAI...) + cifra impactante + primicia. O hecho que genere debate masivo.
- 7-8: Tema con comunidad activa (IA, espacio, crypto, salud) + dato sorprendente
- 5-6: Útil para audiencia específica pero sin gancho masivo
- <5: No seleccionar

REGLAS DE PUNTUACIÓN:
- +2 pts si la noticia tiene una cifra grande concreta ($1B+, millones de personas, récord mundial)
- +2 pts si involucra 2+ marcas o instituciones conocidas (NASA+SpaceX, Apple+Google...)
- +2 pts si es primicia (<2h) o muy reciente (<6h)
- +2 pts si está CONFIRMADA por 2+ medios independientes
- -2 pts si es política genérica sin cifras ni marcas conocidas
- NIVEL 4 sin confirmar: no seleccionar
- No seleccionar noticias de hace más de 48h salvo impacto extraordinario{(chr(10) + f'- CRÍTICO: Si la noticia no es sobre «{tema}», NO la incluyas aunque sea interesante') if tema else ''}

TÍTULO DEL REEL (titulo_reel):
IDIOMA OBLIGATORIO: el título DEBE estar en ESPAÑOL. Si la noticia es en inglés, tradúcela y adáptala.
Sigue UNA de estas fórmulas MrBeast en español:
1. "¿Sabías que [Marca] acaba de [acción] por [cifra]?" — máx 60 chars
2. "[Marca] acaba de [acción sorprendente] y nadie lo esperaba" — máx 60 chars
3. "¿[Pregunta que pone al espectador en la noticia]?" — máx 60 chars
4. "[Cifra] [unidad] de [cosa]: lo que [Marca] acaba de hacer"
NUNCA empieces con "La", "El", "Los", "Un" ni con el titular plano. NUNCA en inglés.

Devuelve SOLO este JSON (sin texto adicional, sin markdown):
{{
  "seleccionadas": [
    {{
      "indice": <número 1-{len(noticias)}>,
      "titulo_reel": "<título viral máx 60 chars siguiendo fórmulas MrBeast>",
      "score": <número 1-10 con un decimal>,
      "categoria": "<tecnologia|ia|economia|mundo|politica|ciencia|salud|deportes|entretenimiento|cripto>",
      "gancho": "<por qué captará atención en 1 frase breve>",
      "audiencia": "<perfil de audiencia en 1 frase muy corta>"
    }}
  ]
}}

Ordena por score descendente."""

    try:
        if client is not None:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = ("".join(b.text for b in resp.content if getattr(b, "type", "") == "text")).strip()
        else:
            raw = completar(prompt, max_tokens=3000, temperature=0.4)
        # Strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        # el modelo local a veces añade texto alrededor del JSON
        ini, fin = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[ini:fin + 1] if ini != -1 and fin > ini else raw)
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
                    **_campos_procedencia(orig),
                    **_calcular_veracidad(orig),
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
    score = 8.5 - pos * 0.4
    if noticia.get("confirmada"):
        score += 1.5
    nivel = noticia.get("nivel_fuente", 3)
    score += {1: 1.0, 2: 0.5, 3: 0.0, 4: -1.0}.get(nivel, 0)
    if nivel >= 4 and not noticia.get("confirmada"):
        score = min(score, 4.5)
    return {
        "titulo": noticia["titulo"],
        "titulo_original": noticia["titulo"],
        "fuente": noticia.get("fuente", ""),
        "link": _resolver_url(noticia.get("link", "")),
        "resumen": noticia.get("resumen", ""),
        "score": round(max(4.0, min(10.0, score)), 1),
        "categoria": "general",
        "gancho": "",
        "audiencia": "",
        "fecha": noticia.get("fecha", ""),
        "recencia": noticia.get("recencia", {}),
        **_campos_procedencia(noticia),
        "nivel_fuente": nivel,
    }


def _calcular_veracidad(item: dict) -> dict:
    """Calcula score de veracidad (0-100) y etiqueta a partir de metadatos de fuentes."""
    nivel = item.get("nivel_fuente", 3)
    confirmada = item.get("confirmada", False)
    n_fuentes = item.get("n_fuentes", 1)
    fuente_verificada = item.get("fuente_verificada", False)

    score = 40  # base

    if nivel == 1:    # agencia/ciencia
        score += 35
    elif nivel == 2:  # prensa
        score += 20
    elif nivel == 4:  # alerta/PR sin confirmar
        score -= 20

    if confirmada:
        score += 20
    if n_fuentes >= 3:
        score += 15
    elif n_fuentes == 2:
        score += 8
    if fuente_verificada:
        score += 8

    score = max(0, min(100, score))

    if score >= 75:
        label, color = "Verificada", "#4ade80"
    elif score >= 45:
        label, color = "En investigación", "#fbbf24"
    else:
        label, color = "Sin confirmar", "#f87171"

    fuentes_list = item.get("fuentes_confirmacion") or ([item.get("fuente")] if item.get("fuente") else [])
    evidencia = ", ".join(filter(None, fuentes_list[:4]))

    return {
        "veracidad_score": score,
        "veracidad_label": label,
        "veracidad_color": color,
        "veracidad_evidencia": evidencia,
    }


def _campos_procedencia(orig: dict) -> dict:
    return {
        "fuente_verificada": orig.get("fuente_verificada", False),
        "confirmada": orig.get("confirmada", False),
        "n_fuentes": orig.get("n_fuentes", 1),
        "fuentes_confirmacion": orig.get("fuentes_confirmacion", []),
        "fuentes_detalle": orig.get("fuentes_detalle", []),
        "nivel_fuente": orig.get("nivel_fuente", 3),
        "origen": orig.get("origen") or orig.get("org_fuente") or orig.get("fuente", ""),
        "origen_tipo": orig.get("origen_tipo", ""),
        "verificadores": orig.get("verificadores", []),
        "fact_checkers": orig.get("fact_checkers", []),
        "estado_verificacion": orig.get("estado_verificacion", ""),
        "documentacion": orig.get("documentacion", ""),
        **_calcular_veracidad(orig),
    }
