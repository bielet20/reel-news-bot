"""
tts.py
Convierte el guion en audio narrado.

Motores disponibles (por prioridad):
  1. ElevenLabs (si ELEVENLABS_API_KEY esta en .env) — voces premium, multilingue.
  2. edge-tts (voces neuronales de Microsoft Edge, gratis, sin API key).
  3. gTTS (Google Text-to-Speech, gratis).
  4. pyttsx3 (motor offline del sistema).
"""

import asyncio
import os

from moviepy.editor import AudioFileClip

VOZ_DEFAULT_EDGE = "es-ES-AlvaroNeural"
VOZ_DEFAULT_ELEVENLABS = "pNInz6obpgDQGcFmaJgB"  # Adam — voz masculina clara

VOCES_EDGE_ES = [
    {"id": "es-ES-AlvaroNeural",    "name": "Álvaro (España, hombre)"},
    {"id": "es-ES-ElviraNeural",    "name": "Elvira (España, mujer)"},
    {"id": "es-MX-JorgeNeural",     "name": "Jorge (México, hombre)"},
    {"id": "es-MX-DaliaNeural",     "name": "Dalia (México, mujer)"},
    {"id": "es-AR-TomasNeural",     "name": "Tomás (Argentina, hombre)"},
    {"id": "es-AR-ElenaNeural",     "name": "Elena (Argentina, mujer)"},
    {"id": "es-CO-GonzaloNeural",   "name": "Gonzalo (Colombia, hombre)"},
    {"id": "es-CO-SalomeNeural",    "name": "Salomé (Colombia, mujer)"},
    {"id": "es-US-AlonsoNeural",    "name": "Alonso (EE.UU., hombre)"},
    {"id": "es-US-PalomaNeural",    "name": "Paloma (EE.UU., mujer)"},
]


def _generar_audio_edge_tts(texto: str, ruta_salida: str, voz: str) -> str:
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(texto, voz)
        await communicate.save(ruta_salida)

    asyncio.run(_run())
    if not os.path.isfile(ruta_salida) or os.path.getsize(ruta_salida) == 0:
        raise RuntimeError("edge-tts genero un archivo vacio o no genero archivo")
    return ruta_salida


def _generar_audio_elevenlabs(texto: str, ruta_salida: str, voice_id: str,
                               model_id: str = "eleven_multilingual_v2") -> str:
    from elevenlabs.client import ElevenLabs

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Falta ELEVENLABS_API_KEY en las variables de entorno")

    client = ElevenLabs(api_key=api_key)
    audio_gen = client.text_to_speech.convert(
        voice_id=voice_id,
        text=texto,
        model_id=model_id,
        output_format="mp3_44100_128",
    )
    with open(ruta_salida, "wb") as f:
        for chunk in audio_gen:
            if chunk:
                f.write(chunk)

    if not os.path.isfile(ruta_salida) or os.path.getsize(ruta_salida) == 0:
        raise RuntimeError("ElevenLabs genero un archivo vacio")
    return ruta_salida


def estado_tts() -> dict:
    """Devuelve que servicios TTS estan disponibles."""
    elevenlabs_key = bool(os.environ.get("ELEVENLABS_API_KEY"))
    edge_ok = False
    try:
        import edge_tts  # noqa: F401
        edge_ok = True
    except ImportError:
        pass
    return {"edge_tts": edge_ok, "elevenlabs": elevenlabs_key}


def listar_voces_elevenlabs() -> list:
    """Devuelve las voces disponibles en ElevenLabs (requiere API key)."""
    from elevenlabs.client import ElevenLabs

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return []
    client = ElevenLabs(api_key=api_key)
    resp = client.voices.get_all()
    return [
        {"id": v.voice_id, "name": v.name, "labels": dict(v.labels) if v.labels else {}}
        for v in resp.voices
    ]


def generar_audio(texto: str, ruta_salida: str, idioma: str = "es", lento: bool = False,
                   voz: str = None, servicio: str = "auto") -> str:
    """
    Genera audio narrado. Devuelve la ruta del archivo.

    servicio: "auto" | "elevenlabs" | "edge-tts"
      - "auto": usa ElevenLabs si hay API key, si no edge-tts.
      - "elevenlabs": fuerza ElevenLabs (falla si no hay key).
      - "edge-tts": fuerza edge-tts.
    voz: voice_id de ElevenLabs o nombre de voz de edge-tts.
    """
    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY")
    usar_elevenlabs = servicio == "elevenlabs" or (servicio == "auto" and elevenlabs_key)

    if usar_elevenlabs:
        voice_id = voz or os.environ.get("ELEVENLABS_VOICE_ID", VOZ_DEFAULT_ELEVENLABS)
        try:
            print(f"   -> Usando ElevenLabs (voice_id: {voice_id})...")
            return _generar_audio_elevenlabs(texto, ruta_salida, voice_id)
        except ImportError:
            print("[tts] elevenlabs SDK no instalado (pip install elevenlabs), usando edge-tts...")
        except Exception as e:
            print(f"[tts] ElevenLabs fallo ({e}), usando edge-tts...")

    voz_edge = (voz if servicio != "elevenlabs" else None) or os.environ.get("TTS_VOICE", VOZ_DEFAULT_EDGE)
    try:
        print(f"   -> Usando edge-tts (voz: {voz_edge})...")
        return _generar_audio_edge_tts(texto, ruta_salida, voz_edge)
    except ImportError:
        print("[tts] Falta instalar edge-tts (pip install edge-tts), probando gTTS...")
    except Exception as e:
        print(f"[tts] edge-tts fallo ({e}), probando gTTS...")

    try:
        from gtts import gTTS
        tts = gTTS(text=texto, lang=idioma, slow=lento)
        tts.save(ruta_salida)
        return ruta_salida
    except Exception as e:
        print(f"[tts] gTTS fallo ({e}), probando motor offline pyttsx3...")

    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.save_to_file(texto, ruta_salida.replace(".mp3", ".wav"))
        engine.runAndWait()
        return ruta_salida.replace(".mp3", ".wav")
    except Exception as e:
        raise RuntimeError(
            "No se pudo generar audio con ningún motor TTS. "
            "Revisa tu conexion a internet o instala pyttsx3 + un motor de voz local."
        ) from e


def duracion_audio(ruta_audio: str) -> float:
    """Devuelve la duracion real del audio en segundos."""
    clip = AudioFileClip(ruta_audio)
    dur = clip.duration
    clip.close()
    return dur


if __name__ == "__main__":
    ruta = generar_audio("Esta es una prueba del sistema de texto a voz.", "/tmp/prueba_tts.mp3")
    print("Generado en:", ruta)
    print("Duracion:", duracion_audio(ruta), "segundos")
