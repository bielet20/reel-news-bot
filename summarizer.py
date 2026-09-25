"""
summarizer.py
Resumen extractivo para articulos de noticias y transcripciones de video,
+ guion estructurado para reel de <=60 segundos.

Ritmo de habla promedio en espanol ~2.5 palabras/seg -> 60s ~= 150 palabras.
Apuntamos a 120-135 palabras de guion.
"""

import os

from llm_local import nube_permitida
import re

STOPWORDS_ES = set("""
a al algo algunas algunos ante antes como con contra cual cuando de del desde
donde durante e el ella ellas ellos en entre era erais eramos eran eres es esa
esas ese eso esos esta estaba estabais estabamos estaban estar este esto estos
fue fuimos fueron fui ha habia habeis habia han has hasta hay la las le les lo
los mas me mi mientras muy nada ni no nos nosotros o os otra otras otro otros
para pero poco por porque que quien quienes se sera seran sereis sido siendo
sin sobre sois somos son soy su sus tambien tanto te tendra tenia tenido tiene
tienen todo todos tras tu tus un una uno unos y ya sus les fue son
""".split())

# Palabras que en videos informativos suelen preceder a datos clave
PALABRAS_CLAVE_VIDEO = set("""
importante clave secreto truco consejo recomiendo recomienda mejor peor nunca
siempre resultado estudio investigacion segun dato porcentaje veces mayor menor
primero segundo tercero principal basico fundamental descubrieron demostraron
comprobaron hallaron encontraron aumenta reduce mejora evita previene causa
efecto beneficio riesgo peligro solucion problema respuesta pregunta conclusion
""".split())

ORACION_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
PALABRA_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)
MULETILLAS_RE = re.compile(
    r"\b(eh|ah|um|uh|pues|bueno|entonces|o sea|verdad|sabes|ves|claro|oye|"
    r"mira|exacto|exactamente|perfecto|genial|interesante|basicamente|"
    r"literalmente|simplemente|obviamente|evidentemente)\b",
    re.IGNORECASE,
)


def _normalizar(palabra: str) -> str:
    return palabra.lower()


# ---------------------------------------------------------------------------
# Resumen para ARTICULOS (texto periodístico con puntuacion normal)
# ---------------------------------------------------------------------------

def _dividir_oraciones(texto: str):
    texto = texto.replace("\n", " ")
    oraciones = ORACION_SPLIT_RE.split(texto.strip())
    return [o.strip() for o in oraciones if len(o.strip()) > 20]


def resumen_extractivo(texto: str, n_oraciones: int = 3):
    """Devuelve las n_oraciones mas relevantes del texto usando frecuencia de palabras."""
    oraciones = _dividir_oraciones(texto)
    if not oraciones:
        return []
    if len(oraciones) <= n_oraciones:
        return oraciones

    frecuencias = {}
    for oracion in oraciones:
        for palabra in PALABRA_RE.findall(oracion):
            palabra = _normalizar(palabra)
            if palabra in STOPWORDS_ES or len(palabra) < 3:
                continue
            frecuencias[palabra] = frecuencias.get(palabra, 0) + 1

    if not frecuencias:
        return oraciones[:n_oraciones]

    max_frec = max(frecuencias.values())
    for palabra in frecuencias:
        frecuencias[palabra] /= max_frec

    scores = []
    for idx, oracion in enumerate(oraciones):
        palabras = [_normalizar(p) for p in PALABRA_RE.findall(oracion)]
        score = sum(frecuencias.get(p, 0) for p in palabras) / max(len(palabras), 1)
        posicion_bonus = 1.15 if idx < 2 else 1.0
        scores.append((idx, score * posicion_bonus, oracion))

    top = sorted(scores, key=lambda x: x[1], reverse=True)[:n_oraciones]
    return [t[2] for t in sorted(top, key=lambda x: x[0])]


# ---------------------------------------------------------------------------
# Resumen para TRANSCRIPCIONES DE VIDEO (sin puntuacion, lenguaje hablado)
# ---------------------------------------------------------------------------

def _limpiar_transcripcion(texto: str) -> str:
    """Elimina muletillas y artefactos del habla espontanea."""
    texto = MULETILLAS_RE.sub("", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _chunks_transcripcion(texto: str, n_palabras: int = 35) -> list:
    """Divide la transcripcion en bloques de ~n_palabras. Devuelve [(posicion, texto)]."""
    palabras = texto.split()
    chunks = []
    for i in range(0, len(palabras), n_palabras):
        chunk = " ".join(palabras[i: i + n_palabras])
        if len(chunk.split()) >= 8:
            chunks.append((i, chunk))
    return chunks


def _score_chunk_video(chunk: str, frecuencias: dict) -> float:
    """Puntua un chunk por frecuencia de palabras + palabras clave + numeros."""
    palabras = [_normalizar(p) for p in PALABRA_RE.findall(chunk)]
    if not palabras:
        return 0.0

    score_frec = sum(frecuencias.get(p, 0) for p in palabras) / len(palabras)

    # Bonus por palabras indicadoras de datos importantes
    bonus_clave = sum(0.25 for p in palabras if p in PALABRAS_CLAVE_VIDEO)

    # Bonus por presencia de numeros/estadisticas (muy informativos)
    bonus_num = len(re.findall(r"\d+", chunk)) * 0.15

    return score_frec + bonus_clave + bonus_num


def resumen_transcripcion_video(texto: str, n_puntos: int = 3) -> list:
    """
    Extrae los n_puntos mas informativos de una transcripcion de video,
    seleccionando uno de cada tercio para cubrir toda la exposicion.

    Devuelve lista de strings (fragmentos del video con los puntos clave).
    """
    texto_limpio = _limpiar_transcripcion(texto)
    chunks = _chunks_transcripcion(texto_limpio)

    if not chunks:
        return [texto[:400]]
    if len(chunks) <= n_puntos:
        return [c for _, c in chunks]

    # Calcular frecuencias globales
    frecuencias = {}
    for _, chunk in chunks:
        for palabra in PALABRA_RE.findall(chunk):
            p = _normalizar(palabra)
            if p not in STOPWORDS_ES and len(p) >= 3:
                frecuencias[p] = frecuencias.get(p, 0) + 1

    if frecuencias:
        max_frec = max(frecuencias.values())
        for p in frecuencias:
            frecuencias[p] /= max_frec

    # Puntuar todos los chunks
    scores = [(pos, _score_chunk_video(chunk, frecuencias), chunk)
              for pos, chunk in chunks]

    # Dividir en n_puntos segmentos y elegir el mejor de cada uno
    n_total = len(scores)
    seg_size = max(1, n_total // n_puntos)
    seleccionados = []

    for i in range(n_puntos):
        inicio = i * seg_size
        fin = inicio + seg_size if i < n_puntos - 1 else n_total
        segmento = scores[inicio:fin]
        if segmento:
            mejor = max(segmento, key=lambda x: x[1])
            seleccionados.append(mejor)

    # Ordenar por posicion para mantener coherencia narrativa
    seleccionados.sort(key=lambda x: x[0])
    return [c for _, _, c in seleccionados]


def _hook_desde_video(titulo: str, puntos: list) -> str:
    """
    Genera un hook para videos: intenta usar el subtitulo del titulo
    (lo que va despues de ':') o busca un dato con numero en los puntos.
    """
    # Buscar un dato con numero en los puntos extraidos
    for punto in puntos:
        nums = re.findall(r"\d[\d,.]*\s*(?:%|por ciento|veces|kilos?|kg|años?|dias?|semanas?)?",
                          punto, re.IGNORECASE)
        if nums:
            # Tomar el primer fragmento de ~10 palabras que contenga el numero
            palabras = punto.split()
            for idx, p in enumerate(palabras):
                if re.search(r"\d", p):
                    inicio = max(0, idx - 3)
                    fin = min(len(palabras), idx + 7)
                    dato = " ".join(palabras[inicio:fin]).strip(".,;:")
                    return f"¿Sabías que {dato}?"

    # Fallback: usar el subtitulo del titulo (despues de ":")
    partes = titulo.split(":", 1)
    subtitulo = partes[1].strip() if len(partes) > 1 else titulo
    subtitulo = subtitulo.split(" - ")[0].strip()
    if len(subtitulo) > 80:
        subtitulo = _recortar_a_palabras(subtitulo, 12)
    return f"¿{subtitulo}?"


# ---------------------------------------------------------------------------
# Helpers comunes
# ---------------------------------------------------------------------------

def _recortar_a_palabras(texto: str, max_palabras: int) -> str:
    palabras = texto.split()
    if len(palabras) <= max_palabras:
        return texto
    return " ".join(palabras[:max_palabras]).rstrip(",.;:") + "..."


def _construir_resultado(titulo: str, fuente: str, hook: str,
                          puntos: list, cierre: str, max_palabras: int) -> dict:
    guion_texto = " ".join([hook] + puntos + [cierre])
    guion_texto = _recortar_a_palabras(guion_texto, max_palabras)
    n_palabras = len(guion_texto.split())
    return {
        "titulo": titulo,
        "fuente": fuente,
        "hook": hook,
        "puntos": puntos,
        "cierre": cierre,
        "guion": guion_texto,
        "palabras": n_palabras,
        "duracion_estimada_seg": round(n_palabras / 2.5, 1),
    }


# ---------------------------------------------------------------------------
# API publica: generacion de guion
# ---------------------------------------------------------------------------

def _es_texto_en_espanol(texto: str) -> bool:
    """Heurística rápida: detecta si el texto tiene suficientes palabras españolas."""
    palabras_es = set("que el la de los las en por para con una del sus más")
    palabras = set(texto.lower().split()[:60])
    return len(palabras & palabras_es) >= 3


def generar_guion_reel(titulo: str, texto_completo: str, fuente: str = "",
                        max_palabras_total: int = 135,
                        tipo: str = "articulo") -> dict:
    """
    Genera el guion del reel sin IA, usando resumen extractivo.
    Si el texto está en otro idioma, usa solo el título para evitar
    que el fallback produzca contenido en inglés.
    """
    # Si el texto no parece español, no usar extractivo (producirá inglés)
    texto_es_espanol = _es_texto_en_espanol(texto_completo)
    fuente_texto = texto_completo if (texto_es_espanol and len(texto_completo.split()) > 30) else titulo
    cierre = "Sígueme para más contenido explicado en 60 segundos."

    if tipo == "video":
        puntos = resumen_transcripcion_video(fuente_texto, n_puntos=3)
        hook = _hook_desde_video(titulo, puntos)
    else:
        puntos = resumen_extractivo(fuente_texto, n_oraciones=3)
        if not puntos or not texto_es_espanol:
            # Construir puntos en español desde el título
            puntos = [f"Esta noticia de {fuente} tiene un alto impacto informativo." if fuente else titulo]
        titulo_hook = titulo.split(":")[0].split(" - ")[0].strip()
        if len(titulo_hook) > 70:
            titulo_hook = _recortar_a_palabras(titulo_hook, 10)
        hook = f"¿Sabías esto sobre {titulo_hook}?"

    return _construir_resultado(titulo, fuente, hook, puntos, cierre, max_palabras_total)


def _llamar_ollama(prompt: str, model: str = "llama3.2") -> str:
    """Llama a un modelo local via Ollama. Sin API, sin coste, sin internet."""
    import json
    import urllib.request
    url = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/") + "/api/generate"
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 600, "temperature": 0.7},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["response"].strip()


def _llamar_lmstudio(prompt: str, model: str) -> str:
    """Llama a un modelo cargado en LM Studio via su API compatible con OpenAI.
    Sin API, sin coste, sin internet. Requiere el servidor local de LM Studio
    corriendo (Developer > Start Server, o `lms server start`)."""
    # llm_local usa LLM_BASE_URL (host.docker.internal desde Docker): con
    # "localhost" el contenedor no llegaba a LM Studio y todo acababa en Claude.
    from llm_local import completar
    return completar(prompt, max_tokens=2500)


def _llamar_gemini(prompt: str, api_key: str) -> str:
    """Llama a Gemini 2.0 Flash via HTTP. Gratis hasta 1500 peticiones/dia."""
    import json
    import urllib.request
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')}:generateContent"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 600, "temperature": 0.7},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json",
                                           "x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _llamar_groq(prompt: str, api_key: str) -> str:
    """Llama a Llama 3.3 70B via Groq. Gratis hasta 14400 req/dia."""
    import json
    import urllib.request
    url = "https://api.groq.com/openai/v1/chat/completions"
    body = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def _llamar_claude(prompt: str, api_key: str) -> str:
    """Llama a Claude via SDK. Modelo configurable con CLAUDE_MODEL (default: claude-sonnet-4-6)."""
    import anthropic
    modelo = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=modelo,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return ("".join(b.text for b in response.content if getattr(b, "type", "") == "text")).strip()


def generar_guion_reel_claude(titulo: str, texto_completo: str, fuente: str = "",
                               max_palabras_total: int = 135,
                               tipo: str = "articulo",
                               documentacion: str = "") -> dict:
    """
    Genera el guion usando IA. Orden de prioridad:
      1. Ollama (local, sin API, sin coste, sin internet)
      2. LM Studio (local, sin API, sin coste, sin internet; usa el modelo
         cargado en el servidor local, LMSTUDIO_MODEL o "qwen/qwen3-8b")
      3. Claude (ANTHROPIC_API_KEY) — de pago
      4. Gemini 2.0 Flash (GEMINI_API_KEY) — gratis hasta 1500 req/dia
      5. Groq Llama 3.3 70B (GROQ_API_KEY) — gratis hasta 14400 req/dia
      6. Resumen extractivo — siempre disponible, sin IA

    tipo: "video" para transcripciones de YouTube, "articulo" para noticias.
    """
    palabras_texto = len(texto_completo.split())
    palabras_titulo = len(titulo.split())

    # Rechazar solo si no hay absolutamente nada con lo que trabajar
    if palabras_texto < 5 and palabras_titulo < 3:
        raise ValueError(
            f"Contenido insuficiente para generar un reel "
            f"({palabras_texto} palabras). "
            f"Proporciona al menos el texto del artículo o una descripción detallada."
        )

    # Con poco texto usa el título como fuente principal; Claude puede expandirlo
    fuente_texto = texto_completo if palabras_texto >= 20 else titulo

    limite_chars = 40000 if tipo == "video" else 4000
    extracto = fuente_texto[:limite_chars]

    if tipo == "video":
        prompt = _prompt_video(titulo, fuente, extracto, max_palabras_total)
    else:
        prompt = _prompt_articulo(titulo, fuente, extracto, max_palabras_total,
                                  documentacion=documentacion)

    def _validar_guion(texto: str) -> str:
        """Lanza ValueError si la IA indicó que el contenido es insuficiente."""
        if "CONTENIDO_INSUFICIENTE" in texto.upper():
            raise ValueError(
                "El contenido proporcionado es insuficiente para generar un reel. "
                "Añade más texto descriptivo sobre el tema."
            )
        return texto

    # --- Intentar Ollama (local, sin coste) ---
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    try:
        print(f"   -> Usando Ollama ({ollama_model}, local)...")
        guion_texto = _validar_guion(_llamar_ollama(prompt, ollama_model))
        guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
        n = len(guion_texto.split())
        return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                "cierre": "", "guion": guion_texto, "palabras": n,
                "duracion_estimada_seg": round(n / 2.5, 1)}
    except ValueError as e:
        print(f"[WARN] Ollama: contenido insuficiente, probando siguiente proveedor...")
    except Exception as e:
        print(f"[WARN] Ollama no disponible: {e}")

    # --- Intentar LM Studio (local, sin coste) ---
    lmstudio_model = os.environ.get("LMSTUDIO_MODEL", "qwen/qwen3-8b")
    try:
        print(f"   -> Usando LM Studio ({lmstudio_model}, local)...")
        guion_texto = _validar_guion(_llamar_lmstudio(prompt, lmstudio_model))
        guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
        n = len(guion_texto.split())
        return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                "cierre": "", "guion": guion_texto, "palabras": n,
                "duracion_estimada_seg": round(n / 2.5, 1)}
    except ValueError as e:
        print(f"[WARN] LM Studio: contenido insuficiente, probando siguiente proveedor...")
    except Exception as e:
        print(f"[WARN] LM Studio no disponible: {e}")

    # --- Intentar Claude ---
    claude_key = os.environ.get("ANTHROPIC_API_KEY") if nube_permitida() else None
    if claude_key:
        try:
            import anthropic  # noqa: F401
            print(f"   -> Usando Claude ({os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')})...")
            guion_texto = _validar_guion(_llamar_claude(prompt, claude_key))
            guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
            n = len(guion_texto.split())
            return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                    "cierre": "", "guion": guion_texto, "palabras": n,
                    "duracion_estimada_seg": round(n / 2.5, 1)}
        except ValueError as e:
            print(f"[WARN] Claude: contenido insuficiente, probando siguiente proveedor...")
        except ImportError:
            print("[WARN] Paquete 'anthropic' no instalado.")
        except Exception as e:
            print(f"[WARN] Claude API: {e}")

    # --- Intentar Gemini (gratis) ---
    gemini_key = os.environ.get("GEMINI_API_KEY") if nube_permitida() else None
    if gemini_key:
        try:
            print("   -> Usando Gemini 2.0 Flash (gratuito)...")
            guion_texto = _validar_guion(_llamar_gemini(prompt, gemini_key))
            guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
            n = len(guion_texto.split())
            return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                    "cierre": "", "guion": guion_texto, "palabras": n,
                    "duracion_estimada_seg": round(n / 2.5, 1)}
        except ValueError as e:
            print(f"[WARN] Gemini: contenido insuficiente, probando siguiente proveedor...")
        except Exception as e:
            print(f"[WARN] Gemini API: {e}")

    # --- Intentar Groq (gratis) ---
    groq_key = os.environ.get("GROQ_API_KEY") if nube_permitida() else None
    if groq_key:
        try:
            print("   -> Usando Groq Llama 3.3 70B (gratuito)...")
            guion_texto = _validar_guion(_llamar_groq(prompt, groq_key))
            guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
            n = len(guion_texto.split())
            return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                    "cierre": "", "guion": guion_texto, "palabras": n,
                    "duracion_estimada_seg": round(n / 2.5, 1)}
        except ValueError as e:
            print(f"[WARN] Groq: contenido insuficiente, usando fallback extractivo...")
        except Exception as e:
            print(f"[WARN] Groq API: {e}")

    # --- Fallback extractivo ---
    return generar_guion_reel(titulo, texto_completo, fuente, max_palabras_total, tipo)


def _prompt_video(titulo: str, fuente: str, transcripcion: str, max_palabras: int) -> str:
    return (
        f"Eres un guionista experto en retención visual para YouTube Shorts y Reels.\n\n"
        f"Transcripción del video \"{titulo}\" (canal: \"{fuente}\"):\n"
        f"TRANSCRIPCION:\n{transcripcion}\n\n"
        f"IDIOMA OBLIGATORIO: TODO en español. Si la transcripción es en inglés, TRADUCE COMPLETAMENTE.\n\n"
        f"Escribe el guion en español para un reel de 60 segundos (máximo {max_palabras} palabras).\n\n"
        f"REGLAS DE RETENCIÓN VISUAL — aplica todas:\n"
        f"1. RITMO: frases de máximo 8-10 palabras. Punto final. Cada frase es una pantalla.\n"
        f"   MAL: 'OpenAI ha anunciado un nuevo modelo que supera a todos los anteriores en todas las métricas'\n"
        f"   BIEN: 'OpenAI acaba de lanzar su mejor modelo. Supera todo lo anterior. Por mucho.'\n"
        f"2. HOOK (primeras 3 segundos): dato más sorprendente del video + loop abierto.\n"
        f"   Formato: '[Cifra/hecho impactante]. [Nombre conocido] acaba de [acción]. Y lo que sigue lo cambia todo.'\n"
        f"   O: '¿Sabías que [marca/institución] acaba de [acción sorprendente]? Esto es lo que nadie te está contando.'\n"
        f"3. DESARROLLO (3 revelaciones en escalada):\n"
        f"   — Primero: el hecho básico con cifra exacta\n"
        f"   — Segundo: la consecuencia o implicación (más impactante)\n"
        f"   — Tercero: el dato que nadie esperaba / el giro (el más impactante)\n"
        f"   Entre revelaciones usa exactamente UNA de estas transiciones:\n"
        f"   'Pero esto no es todo.' / 'Y aquí viene lo importante:' / 'Lo que nadie esperaba:' / 'Ahora viene lo mejor:'\n"
        f"4. CIERRE: pregunta polarizante que OBLIGUE a opinar. No genérica.\n"
        f"   MAL: '¿Qué te parece? Deja tu comentario.'\n"
        f"   BIEN: '¿Crees que [marca] está haciendo lo correcto o nos está manipulando? Dilo en los comentarios.'\n\n"
        f"IMPORTANTE: usa SOLO datos del video. No inventes cifras ni hechos.\n"
        f"Devuelve SOLO el texto del guion en español, sin etiquetas ni explicaciones."
    )


def _prompt_articulo(titulo: str, fuente: str, texto: str, max_palabras: int,
                     documentacion: str = "") -> str:
    atribucion = (
        f"Procedencia verificada: {documentacion}\n"
        f"Cita la fuente real una vez (ej: 'Segun {fuente or 'el medio'}'). "
        f"Si hay medios que contrastan, mencionalos UNA vez. NO inventes fuentes.\n"
        if documentacion else
        f"Cita la fuente si se conoce: {fuente or 'no indicada'}. No inventes medios.\n"
    )
    return (
        f"Eres un guionista experto en retención visual para YouTube Shorts y Reels.\n"
        f"Canal de noticias en ESPAÑOL para audiencia hispanohablante.\n\n"
        f"Noticia: {titulo}\n"
        f"Fuente: {fuente}\n"
        f"{atribucion}"
        f"Contenido: {texto}\n\n"
        f"IDIOMA OBLIGATORIO: TODO en español. Si el contenido es en inglés, TRADUCE COMPLETAMENTE.\n\n"
        f"Escribe el guion en español para un reel de 60 segundos (máximo {max_palabras} palabras).\n\n"
        f"REGLAS DE RETENCIÓN VISUAL — aplica TODAS:\n"
        f"1. RITMO: frases de máximo 8-10 palabras. Punto final. Cada frase es una pantalla.\n"
        f"   MAL: 'La empresa ha anunciado un acuerdo histórico que cambiará la industria para siempre'\n"
        f"   BIEN: 'Acuerdo histórico. La industria no volverá a ser la misma. Nunca.'\n"
        f"2. HOOK (primeras 3 segundos — retención crítica): dato más sorprendente + loop abierto.\n"
        f"   Formato A: '[Cifra impactante]. [Nombre conocido] acaba de [acción]. Y nadie lo vio venir.'\n"
        f"   Formato B: '¿Sabías que [marca/institución] acaba de [acción]? Lo que sigue te va a sorprender.'\n"
        f"   Formato C: '[Acción inesperada]. [Nombre conocido] lo acaba de confirmar. Esto lo cambia todo.'\n"
        f"   NUNCA empieces con 'En', 'La', 'El', 'Un' ni con el titular plano.\n"
        f"3. DESARROLLO (3 revelaciones en escalada — cada una más impactante):\n"
        f"   — Revelación 1: el hecho central con cifra exacta si existe\n"
        f"   — Transición obligatoria: 'Pero esto no es todo.' o 'Y aquí viene lo importante:' o 'Lo que nadie esperaba:'\n"
        f"   — Revelación 2: la consecuencia real o el dato que sorprende\n"
        f"   — Transición obligatoria: 'Pero espera.' o 'Ahora viene lo mejor:' o 'Y esto es lo que más impacta:'\n"
        f"   — Revelación 3: el dato más impactante / el giro / la consecuencia que nadie dice\n"
        f"4. CIERRE polarizante (genera debate, NO CTA genérica):\n"
        f"   Formato: '¿Crees que [acción de la noticia] es [postura A] o [postura B contraria]? Dilo abajo.'\n"
        f"   MAL: '¿Qué piensas? Deja tu comentario.'\n"
        f"   BIEN: '¿Crees que [marca] está protegiendo a los usuarios o solo a sus beneficios? Dilo abajo.'\n\n"
        f"REGLA CRÍTICA: usa SOLO información presente en el texto. Si el contenido es insuficiente, responde: CONTENIDO_INSUFICIENTE\n"
        f"Devuelve SOLO el texto del guion en español, sin etiquetas ni explicaciones."
    )


def _prompt_largo(titulo: str, fuente: str, texto: str, max_palabras: int,
                  documentacion: str = "") -> str:
    """Prompt para generar un guion de 7-10 minutos estructurado en 4 actos."""
    atribucion = (
        f"Procedencia verificada: {documentacion}\n"
        f"Cita la fuente real al menos una vez: \"{fuente or 'la fuente'}\". No inventes medios.\n"
        if documentacion else
        f"Cita la fuente si se conoce: {fuente or 'no indicada'}. No inventes.\n"
    )
    return (
        f"Eres un guionista de documentales informativos virales para YouTube. "
        f"Tu referencia son canales como Veritasium, Kurzgesagt y Vox: retienen al espectador "
        f"durante 8-10 minutos porque cada minuto tiene una nueva revelacion que engancha.\n\n"
        f"Escribe un guion en ESPANOL DE ESPANA para un video informativo de 7-10 minutos "
        f"(entre {max_palabras - 100} y {max_palabras} palabras) sobre esta noticia:\n\n"
        f"Titulo: {titulo}\n"
        f"Fuente: {fuente}\n"
        f"{atribucion}"
        f"Contenido: {texto}\n\n"
        f"IDIOMA OBLIGATORIO: todo en español. Traduce completamente si el texto es en inglés.\n\n"
        f"REGLAS DE RITMO Y RETENCIÓN (aplica en todos los actos):\n"
        f"- Frases de máximo 10 palabras. Punto final. Cada frase es una pantalla.\n"
        f"- Nunca párrafos de más de 3 líneas seguidas — corta y continúa.\n"
        f"- Usa transiciones de retención entre revelaciones:\n"
        f"  'Pero esto no es todo.' / 'Y aquí viene lo importante:' / 'Pero espera.' / 'Lo que nadie dice:'\n\n"
        f"ESTRUCTURA OBLIGATORIA EN 4 ACTOS (usa exactamente estas marcas de sección):\n\n"
        f"[ACTO 1 - EL GANCHO] (aprox. 150 palabras)\n"
        f"Empieza con la cifra o hecho MÁS sorprendente. Sin preámbulo.\n"
        f"Ej: 'Novecientos cuarenta y seis millones. Eso acaba de pagar la NASA. Y nadie lo esperaba.'\n"
        f"Presenta la pregunta central del video. Termina con loop abierto:\n"
        f"'Pero lo que muy poca gente sabe es que detrás de esto hay algo mucho más grande.'\n\n"
        f"[ACTO 2 - EL CONTEXTO] (aprox. 300 palabras)\n"
        f"Historia de fondo: quién, qué, cuándo, cómo llegamos hasta aquí.\n"
        f"3 puntos. Cada punto termina con frase que engancha al siguiente.\n"
        f"Transiciones: 'pero eso no es lo más importante...' / 'y aquí viene lo que nadie esperaba...'\n\n"
        f"[ACTO 3 - EL IMPACTO] (aprox. 350 palabras)\n"
        f"Qué significa esto realmente. Consecuencias concretas. Quiénes ganan, quiénes pierden.\n"
        f"Al menos 3 revelaciones en escalada (cada dato más impactante que el anterior).\n"
        f"Incluye UNA comparación de magnitud (ej: 'equivale a construir 5.000 hospitales').\n\n"
        f"[ACTO 4 - EL DEBATE] (aprox. 150 palabras)\n"
        f"DOS perspectivas reales (a favor y crítica). No tomes partido.\n"
        f"Cierra con la pregunta más polarizante posible.\n"
        f"Ej: '¿Crees que los viajes espaciales deben depender de empresas privadas o del Estado? Dilo abajo.'\n\n"
        f"REGLAS:\n"
        f"- Usa SOLO información del texto. No inventes datos ni cifras\n"
        f"- Si el contenido es insuficiente responde exactamente: CONTENIDO_INSUFICIENTE\n"
        f"- Devuelve SOLO el guion con las marcas de sección, sin explicaciones adicionales"
    )


def generar_guion_largo(titulo: str, texto_completo: str, fuente: str = "",
                        duracion_min: int = 8,
                        documentacion: str = "") -> dict:
    """
    Genera un guion de video largo (7-10 min) estructurado en 4 actos.
    Ritmo: ~2.5 palabras/seg -> 8 min = ~1200 palabras.
    Usa Claude Sonnet por defecto (mejor calidad para contenido largo).
    """
    palabras_texto = len(texto_completo.split())
    if palabras_texto < 30 and len(titulo.split()) < 5:
        raise ValueError(f"Contenido insuficiente para guion largo ({palabras_texto} palabras).")

    max_palabras = int(duracion_min * 60 * 2.5)  # palabras objetivo segun duracion
    extracto = texto_completo[:8000]

    prompt = _prompt_largo(titulo, fuente, extracto, max_palabras, documentacion)

    def _parse_guion(texto: str) -> dict:
        """Extrae los 4 actos del guion y calcula metricas."""
        if "CONTENIDO_INSUFICIENTE" in texto.upper():
            raise ValueError("Contenido insuficiente para guion largo.")
        actos = {}
        marcas = ["[ACTO 1 - EL GANCHO]", "[ACTO 2 - EL CONTEXTO]",
                  "[ACTO 3 - EL IMPACTO]", "[ACTO 4 - EL DEBATE]"]
        partes = texto
        for marca in marcas:
            partes = partes.replace(marca, f"\n|||{marca}\n")
        bloques = [b.strip() for b in partes.split("|||") if b.strip()]
        guion_limpio = texto
        for marca in marcas:
            guion_limpio = guion_limpio.replace(marca, "").strip()
        guion_limpio = "\n\n".join(b.strip() for b in guion_limpio.split("\n\n") if b.strip())
        n = len(guion_limpio.split())
        return {
            "titulo": titulo,
            "fuente": fuente,
            "guion": guion_limpio,
            "guion_con_marcas": texto,
            "palabras": n,
            "duracion_estimada_min": round(n / (2.5 * 60), 1),
            "duracion_estimada_seg": round(n / 2.5),
            "tipo": "largo",
        }

    # 0. LM Studio local (sin coste)
    try:
        from llm_local import completar
        print("   -> Guion largo con LM Studio (local)...")
        return _parse_guion(completar(prompt, max_tokens=6000))
    except ValueError:
        raise
    except Exception as e:
        print(f"   [WARN] LM Studio largo: {e}")

    # 1. Claude (solo con IA_NUBE=1)
    claude_key = os.environ.get("ANTHROPIC_API_KEY") if nube_permitida() else None
    if claude_key:
        try:
            import anthropic
            modelo = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
            client = anthropic.Anthropic(api_key=claude_key)
            print(f"   -> Generando guion largo con Claude ({modelo})...")
            resp = client.messages.create(
                model=modelo,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
            return _parse_guion(("".join(b.text for b in resp.content if getattr(b, "type", "") == "text")).strip())
        except Exception as e:
            print(f"   [WARN] Claude largo: {e}")

    # 2. Gemini fallback
    gemini_key = os.environ.get("GEMINI_API_KEY") if nube_permitida() else None
    if gemini_key:
        try:
            import requests as _req
            r = _req.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')}:generateContent",
                headers={"x-goog-api-key": gemini_key},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"maxOutputTokens": 3000}},
                timeout=60,
            )
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return _parse_guion(texto)
        except Exception as e:
            print(f"   [WARN] Gemini largo: {e}")

    # 3. Groq fallback
    groq_key = os.environ.get("GROQ_API_KEY") if nube_permitida() else None
    if groq_key:
        try:
            import requests as _req
            r = _req.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={"model": "llama-3.3-70b-versatile", "max_tokens": 3000,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60,
            )
            texto = r.json()["choices"][0]["message"]["content"].strip()
            return _parse_guion(texto)
        except Exception as e:
            print(f"   [WARN] Groq largo: {e}")

    raise RuntimeError("No hay proveedor de IA disponible para generar guion largo.")


if __name__ == "__main__":
    texto_prueba = (
        "Un nuevo estudio revela que el consumo de energia de los centros de datos "
        "de inteligencia artificial se duplicara para 2027. Las empresas tecnologicas "
        "estan invirtiendo miles de millones en nuevos chips y en infraestructura de "
        "energia renovable para sostener el crecimiento. Expertos advierten que la red "
        "electrica de varios paises podria verse afectada si no se planifica con anticipacion. "
        "Sin embargo, algunas companias ya estan firmando acuerdos directos con plantas "
        "de energia nuclear y solar para asegurar su suministro."
    )
    guion = generar_guion_reel("El costo energetico de la IA se dispara", texto_prueba, "Reuters")
    for k, v in guion.items():
        print(f"{k}: {v}")
