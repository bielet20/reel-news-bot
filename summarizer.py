"""
summarizer.py
Resumen extractivo para articulos de noticias y transcripciones de video,
+ guion estructurado para reel de <=60 segundos.

Ritmo de habla promedio en espanol ~2.5 palabras/seg -> 60s ~= 150 palabras.
Apuntamos a 120-135 palabras de guion.
"""

import os
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

def generar_guion_reel(titulo: str, texto_completo: str, fuente: str = "",
                        max_palabras_total: int = 135,
                        tipo: str = "articulo") -> dict:
    """
    Genera el guion del reel sin IA, usando resumen extractivo.

    tipo: "video" usa el resumidor especial para transcripciones habladas;
          "articulo" (default) usa el resumidor para texto periodistico.
    """
    fuente_texto = texto_completo if len(texto_completo.split()) > 30 else titulo
    cierre = "Sígueme para más contenido explicado en 60 segundos."

    if tipo == "video":
        puntos = resumen_transcripcion_video(fuente_texto, n_puntos=3)
        hook = _hook_desde_video(titulo, puntos)
    else:
        puntos = resumen_extractivo(fuente_texto, n_oraciones=3)
        if not puntos:
            puntos = [titulo]
        titulo_hook = titulo.split(":")[0].split(" - ")[0].strip()
        if len(titulo_hook) > 70:
            titulo_hook = _recortar_a_palabras(titulo_hook, 10)
        hook = f"¿Sabías esto sobre {titulo_hook}?"

    return _construir_resultado(titulo, fuente, hook, puntos, cierre, max_palabras_total)


def _llamar_ollama(prompt: str, model: str = "llama3.2") -> str:
    """Llama a un modelo local via Ollama. Sin API, sin coste, sin internet."""
    import json
    import urllib.request
    url = "http://localhost:11434/api/generate"
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


def _llamar_gemini(prompt: str, api_key: str) -> str:
    """Llama a Gemini 2.0 Flash via HTTP. Gratis hasta 1500 peticiones/dia."""
    import json
    import urllib.request
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 600, "temperature": 0.7},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json"})
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
    """Llama a Claude via SDK. Modelo configurable con CLAUDE_MODEL (default: claude-sonnet-5)."""
    import anthropic
    modelo = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=modelo,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def generar_guion_reel_claude(titulo: str, texto_completo: str, fuente: str = "",
                               max_palabras_total: int = 135,
                               tipo: str = "articulo") -> dict:
    """
    Genera el guion usando IA. Orden de prioridad:
      1. Ollama (local, sin API, sin coste, sin internet)
      2. Claude (ANTHROPIC_API_KEY) — de pago
      3. Gemini 2.0 Flash (GEMINI_API_KEY) — gratis hasta 1500 req/dia
      4. Groq Llama 3.3 70B (GROQ_API_KEY) — gratis hasta 14400 req/dia
      5. Resumen extractivo — siempre disponible, sin IA

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
        prompt = _prompt_articulo(titulo, fuente, extracto, max_palabras_total)

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
    except ValueError:
        raise
    except Exception as e:
        print(f"[WARN] Ollama no disponible: {e}")

    # --- Intentar Claude ---
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if claude_key:
        try:
            import anthropic  # noqa: F401
            print(f"   -> Usando Claude ({os.environ.get('CLAUDE_MODEL', 'claude-sonnet-5')})...")
            guion_texto = _validar_guion(_llamar_claude(prompt, claude_key))
            guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
            n = len(guion_texto.split())
            return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                    "cierre": "", "guion": guion_texto, "palabras": n,
                    "duracion_estimada_seg": round(n / 2.5, 1)}
        except ValueError:
            raise
        except ImportError:
            print("[WARN] Paquete 'anthropic' no instalado.")
        except Exception as e:
            print(f"[WARN] Claude API: {e}")

    # --- Intentar Gemini (gratis) ---
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            print("   -> Usando Gemini 2.0 Flash (gratuito)...")
            guion_texto = _validar_guion(_llamar_gemini(prompt, gemini_key))
            guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
            n = len(guion_texto.split())
            return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                    "cierre": "", "guion": guion_texto, "palabras": n,
                    "duracion_estimada_seg": round(n / 2.5, 1)}
        except ValueError:
            raise
        except Exception as e:
            print(f"[WARN] Gemini API: {e}")

    # --- Intentar Groq (gratis) ---
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            print("   -> Usando Groq Llama 3.3 70B (gratuito)...")
            guion_texto = _validar_guion(_llamar_groq(prompt, groq_key))
            guion_texto = _recortar_a_palabras(guion_texto, max_palabras_total)
            n = len(guion_texto.split())
            return {"titulo": titulo, "fuente": fuente, "hook": "", "puntos": [],
                    "cierre": "", "guion": guion_texto, "palabras": n,
                    "duracion_estimada_seg": round(n / 2.5, 1)}
        except ValueError:
            raise
        except Exception as e:
            print(f"[WARN] Groq API: {e}")

    # --- Fallback extractivo ---
    return generar_guion_reel(titulo, texto_completo, fuente, max_palabras_total, tipo)


def _prompt_video(titulo: str, fuente: str, transcripcion: str, max_palabras: int) -> str:
    return (
        f"Eres un guionista de contenido viral para redes sociales.\n\n"
        f"A continuacion tienes la transcripcion completa de un video de YouTube "
        f"titulado \"{titulo}\" del canal \"{fuente}\".\n\n"
        f"TRANSCRIPCION:\n{transcripcion}\n\n"
        f"Tu tarea:\n"
        f"1. Entende de que trata el video: cual es el tema principal y que puntos "
        f"importantes se mencionan realmente en el video.\n"
        f"2. Escribe un guion en espanol para un reel de 60 segundos (maximo "
        f"{max_palabras} palabras) que resuma fielmente el contenido del video.\n\n"
        f"Estructura del guion (todo en un parrafo continuo, sin etiquetas):\n"
        f"- HOOK: dato o pregunta impactante basada en algo que se dice en el video\n"
        f"- PUNTOS CLAVE: 2-3 ideas centrales que se explican en el video\n"
        f"- CIERRE: llamada a la accion breve\n\n"
        f"IMPORTANTE: los puntos clave deben reflejar lo que realmente se habla en "
        f"el video, no suposiciones generales sobre el tema.\n"
        f"Tono: dinamico, conversacional. "
        f"Devuelve SOLO el texto del guion, sin encabezados ni explicaciones."
    )


def _prompt_articulo(titulo: str, fuente: str, texto: str, max_palabras: int) -> str:
    return (
        f"Eres un guionista de contenido viral para redes sociales. "
        f"Crea un guion en espanol para un reel vertical de 60 segundos "
        f"(maximo {max_palabras} palabras en total) sobre esta noticia:\n\n"
        f"Titulo: {titulo}\n"
        f"Fuente: {fuente}\n"
        f"Contenido: {texto}\n\n"
        f"Estructura obligatoria (todo en un parrafo continuo, sin etiquetas):\n"
        f"1. HOOK: pregunta o dato impactante que enganche en los primeros 3 segundos\n"
        f"2. PUNTOS CLAVE: 2-3 datos mas importantes de la noticia\n"
        f"3. CIERRE: llamada a la accion breve\n\n"
        f"IMPORTANTE: usa UNICAMENTE informacion presente en el texto proporcionado. "
        f"NO inventes datos, hechos, cifras ni detalles que no aparezcan en el contenido. "
        f"Si el contenido es insuficiente para generar un guion util, responde exactamente: CONTENIDO_INSUFICIENTE\n\n"
        f"Tono: dinamico, conversacional, directo. "
        f"Devuelve SOLO el texto del guion, sin ningun encabezado ni explicacion."
    )


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
