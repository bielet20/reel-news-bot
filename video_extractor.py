"""
video_extractor.py
Transcribes local video files (mp4, mov, avi, mkv...) using OpenAI Whisper
and returns a dict compatible with youtube_extractor.extraer_youtube(), so
local videos can feed directly into the video_clipper.py pipeline.

Install: pip install openai-whisper
(requires ffmpeg installed on the system)

Whisper model sizes vs. speed (CPU):
  tiny    ~39M  — muy rapido, calidad basica
  base    ~74M  — rapido, buena calidad (recomendado para empezar)
  small   ~244M — equilibrado
  medium  ~769M — buena calidad
  large   ~1.5G — mejor calidad, muy lento en CPU
"""

import os

MODELOS_DISPONIBLES = ["tiny", "base", "small", "medium", "large"]
EXTENSIONES_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".ts"}


def _validar_ruta(ruta: str) -> None:
    if not os.path.isfile(ruta):
        raise FileNotFoundError(f"No se encontro el archivo: {ruta}")
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in EXTENSIONES_VIDEO:
        raise ValueError(
            f"Extension no soportada: '{ext}'. "
            f"Extensiones validas: {', '.join(sorted(EXTENSIONES_VIDEO))}"
        )


def transcribir_video_local(ruta: str, modelo: str = "base",
                             idioma: str = "es") -> dict:
    """
    Transcribes a local video file using OpenAI Whisper.

    Args:
        ruta:   Ruta al archivo de video (mp4, mov, avi, mkv, ...).
        modelo: Tamano del modelo Whisper: tiny, base (default), small,
                medium, large. Mas grande = mejor calidad, mas lento.
        idioma: Codigo de idioma ISO 639-1 (default: "es"). Usa "auto"
                para deteccion automatica.

    Returns:
        Dict compatible con youtube_extractor.extraer_youtube():
        {titulo, canal, url, texto, segmentos}
        donde segmentos = [{text, start, duration}, ...]
    """
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "Para transcribir videos locales necesitas openai-whisper:\n"
            "  pip install openai-whisper\n"
            "Tambien requiere ffmpeg instalado (brew install ffmpeg en Mac)."
        )

    _validar_ruta(ruta)

    if modelo not in MODELOS_DISPONIBLES:
        raise ValueError(
            f"Modelo '{modelo}' no valido. Opciones: {MODELOS_DISPONIBLES}"
        )

    print(f"   -> Cargando modelo Whisper '{modelo}'...")
    model = whisper.load_model(modelo)

    print("   -> Transcribiendo video (puede tardar varios minutos)...")
    opciones = {"verbose": False}
    if idioma and idioma != "auto":
        opciones["language"] = idioma

    result = model.transcribe(ruta, **opciones)

    segmentos = []
    for seg in result.get("segments", []):
        texto = (seg.get("text") or "").strip()
        if texto:
            segmentos.append({
                "text": texto,
                "start": float(seg["start"]),
                "duration": float(seg["end"]) - float(seg["start"]),
            })

    texto_completo = " ".join(s["text"] for s in segmentos)
    if not texto_completo.strip():
        raise ValueError(
            "Whisper no pudo extraer texto del video. Verifica que el video "
            "tenga audio con voz (no solo musica) y que ffmpeg este instalado."
        )

    titulo = os.path.splitext(os.path.basename(ruta))[0]

    idioma_detectado = result.get("language", idioma)
    print(f"   -> Transcripcion lista: {len(texto_completo.split())} palabras "
          f"(idioma detectado: {idioma_detectado})")

    return {
        "titulo": titulo,
        "canal": "Local",
        "url": ruta,
        "texto": texto_completo,
        "segmentos": segmentos,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python video_extractor.py <ruta_video> [modelo] [idioma]")
        print("     modelo: tiny | base | small | medium | large  (default: base)")
        print("     idioma: es | en | auto | ...                  (default: es)")
        sys.exit(1)

    ruta_arg = sys.argv[1]
    modelo_arg = sys.argv[2] if len(sys.argv) > 2 else "base"
    idioma_arg = sys.argv[3] if len(sys.argv) > 3 else "es"

    datos = transcribir_video_local(ruta_arg, modelo=modelo_arg, idioma=idioma_arg)
    print("\nTitulo:", datos["titulo"])
    print("Segmentos con timestamp:", len(datos["segmentos"]))
    print("Palabras totales:", len(datos["texto"].split()))
    print("\nPrimeros 500 caracteres:")
    print(datos["texto"][:500])
