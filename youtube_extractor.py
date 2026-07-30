"""
youtube_extractor.py
Extrae titulo, canal y transcripcion de un video de YouTube.
No requiere API key: usa youtube-transcript-api para los subtitulos y
scraping de la pagina para los metadatos.
"""

import re

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_IDIOMAS_DEFAULT = ["es", "es-419", "es-ES", "es-MX", "es-AR", "en", "en-US"]


def _video_id_desde_url(url: str) -> str:
    patrones = [
        r'[?&]v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/(?:shorts|embed)/([a-zA-Z0-9_-]{11})',
    ]
    for patron in patrones:
        m = re.search(patron, url)
        if m:
            return m.group(1)
    raise ValueError(
        f"No se pudo extraer el ID del video de: {url}\n"
        "Formatos soportados: youtube.com/watch?v=..., youtu.be/..., "
        "youtube.com/shorts/..."
    )


def _metadata_desde_pagina(watch_url: str) -> dict:
    try:
        resp = requests.get(watch_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception:
        return {"titulo": "", "canal": ""}

    soup = BeautifulSoup(resp.text, "html.parser")

    titulo = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        titulo = og_title["content"].strip()
    if not titulo:
        tag = soup.find("title")
        if tag:
            titulo = tag.get_text(strip=True).split(" - YouTube")[0].strip()

    canal = ""
    m = re.search(r'"ownerChannelName"\s*:\s*"([^"]+)"', resp.text)
    if m:
        canal = m.group(1)
    if not canal:
        m = re.search(r'"author"\s*:\s*"([^"]+)"', resp.text)
        if m:
            canal = m.group(1)

    return {"titulo": titulo, "canal": canal}


def _transcript_a_texto(fetched) -> str:
    """
    Convierte un FetchedTranscript (nuevo API) o lista de dicts (API vieja)
    en un string de texto continuo, descartando marcadores de musica/ruido.
    """
    partes = []
    # Nuevo API: FetchedTranscript con atributo .snippets
    snippets = getattr(fetched, "snippets", None)
    if snippets is not None:
        for snippet in snippets:
            texto = getattr(snippet, "text", "").strip()
            if texto and not re.match(r"^\[.+\]$", texto):
                partes.append(texto)
    else:
        # Compatibilidad con lista de dicts (API anterior)
        for item in fetched:
            texto = (item.get("text", "") if isinstance(item, dict) else "").strip()
            if texto and not re.match(r"^\[.+\]$", texto):
                partes.append(texto)
    return " ".join(partes)


def _transcript_a_segmentos(fetched) -> list:
    """
    Convierte un FetchedTranscript (o lista de dicts equivalente) en una lista
    de segmentos con marca de tiempo real: [{"start": float, "duration": float,
    "text": str}, ...]. Descarta marcadores de musica/ruido (p.ej. "[Musica]").
    Se usa para detectar el mejor tramo del video (highlight) y para quemar
    subtitulos sincronizados con el video original.
    """
    segmentos = []
    snippets = getattr(fetched, "snippets", None)
    if snippets is not None:
        iterable = (
            {
                "start": getattr(s, "start", 0.0),
                "duration": getattr(s, "duration", 0.0),
                "text": getattr(s, "text", ""),
            }
            for s in snippets
        )
    else:
        iterable = (
            {
                "start": item.get("start", 0.0),
                "duration": item.get("duration", 0.0),
                "text": item.get("text", ""),
            }
            for item in fetched
            if isinstance(item, dict)
        )

    for item in iterable:
        texto = (item["text"] or "").strip()
        if not texto or re.match(r"^\[.+\]$", texto):
            continue
        segmentos.append({
            "start": float(item["start"]),
            "duration": float(item["duration"] or 0.0),
            "text": texto,
        })
    return segmentos


def extraer_youtube(url: str, idiomas: list = None) -> dict:
    """
    Extrae titulo, canal y transcripcion de un video de YouTube.
    No requiere API key.

    Devuelve dict con: titulo, canal, url, video_id, texto (transcripcion completa)

    Lanza ValueError si el video no tiene transcripciones disponibles.
    """
    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            NoTranscriptFound,
            TranscriptsDisabled,
        )
    except ImportError:
        raise ImportError(
            "Falta instalar youtube-transcript-api:\n"
            "  pip install youtube-transcript-api"
        )

    if idiomas is None:
        idiomas = _IDIOMAS_DEFAULT

    video_id = _video_id_desde_url(url)
    watch_url = f"https://www.youtube.com/watch?v={video_id}"

    print("   -> Obteniendo metadatos del video...")
    meta = _metadata_desde_pagina(watch_url)

    print("   -> Descargando transcripcion/subtitulos...")
    # La version >= 0.0.11 usa instancias; versiones anteriores usaban classmethods
    api = YouTubeTranscriptApi()

    try:
        fetched = api.fetch(video_id, languages=idiomas)
        texto = _transcript_a_texto(fetched)
    except TranscriptsDisabled:
        raise ValueError(
            f"Las transcripciones estan deshabilitadas para este video ({video_id}). "
            "El creador no permite que se extraigan subtitulos."
        )
    except NoTranscriptFound:
        # Intentar con cualquier idioma disponible (incluye auto-generados)
        try:
            lista = api.list(video_id)
            transcript_obj = None
            # Primero intentar español, luego cualquier idioma
            for lang_prioridad in (["es", "es-419", "es-ES"], None):
                try:
                    if lang_prioridad:
                        transcript_obj = lista.find_transcript(lang_prioridad)
                    else:
                        transcript_obj = next(iter(lista))
                    break
                except Exception:
                    continue
            if transcript_obj is None:
                raise ValueError("No hay transcripciones disponibles en ningun idioma.")
            fetched = transcript_obj.fetch()
            texto = _transcript_a_texto(fetched)
        except Exception as e:
            raise ValueError(
                f"No se encontraron transcripciones para el video ({video_id}). "
                "Algunos videos no tienen subtitulos disponibles. "
                "Alternativa: usa '--archivo' para pegar el contenido manualmente."
            ) from e

    if not texto or len(texto.split()) < 20:
        raise ValueError(
            f"La transcripcion del video ({video_id}) es demasiado corta o esta vacia. "
            "Puede que el video sea mayormente musical o no tenga dialogo suficiente."
        )

    segmentos = _transcript_a_segmentos(fetched)

    return {
        "titulo": meta["titulo"] or f"Video {video_id}",
        "canal": meta["canal"],
        "url": watch_url,
        "video_id": video_id,
        "texto": texto,
        # Segmentos con marca de tiempo real (start/duration/text), en el orden
        # del video. Se usan para: detectar el mejor tramo del video (highlight)
        # y para quemar subtitulos sincronizados con el video original.
        "segmentos": segmentos,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python youtube_extractor.py <url_del_video>")
        sys.exit(1)
    data = extraer_youtube(sys.argv[1])
    print("Titulo:", data["titulo"])
    print("Canal:", data["canal"])
    print("Video ID:", data["video_id"])
    print("Palabras en transcripcion:", len(data["texto"].split()))
    print("\nPrimeras 500 caracteres de la transcripcion:")
    print(data["texto"][:500])
