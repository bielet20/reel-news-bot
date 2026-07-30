"""
tts.py
Convierte el guion en audio narrado.

Motor principal: edge-tts (voces neuronales de Microsoft Edge, gratis, sin
API key, requiere internet). Mucho mas natural que gTTS.
Fallback 1: gTTS (Google Text-to-Speech, gratis, requiere internet).
Fallback 2: pyttsx3 (motor offline del sistema operativo, sin internet)
para que el pipeline no se caiga si no hay conexion en ese momento.
"""

import asyncio
import os

from moviepy.editor import AudioFileClip

# Voz neuronal en espanol por defecto (se puede sobreescribir con la variable
# de entorno TTS_VOICE). Lista de voces disponibles: 'edge-tts --list-voices'.
VOZ_DEFAULT = "es-ES-AlvaroNeural"


def _generar_audio_edge_tts(texto: str, ruta_salida: str, voz: str) -> str:
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(texto, voz)
        await communicate.save(ruta_salida)

    asyncio.run(_run())
    if not os.path.isfile(ruta_salida) or os.path.getsize(ruta_salida) == 0:
        raise RuntimeError("edge-tts genero un archivo vacio o no genero archivo")
    return ruta_salida


def generar_audio(texto: str, ruta_salida: str, idioma: str = "es", lento: bool = False,
                   voz: str = None) -> str:
    """
    Genera un archivo de audio con el texto narrado. Devuelve la ruta del archivo.

    Orden de prioridad:
      1. edge-tts (voces neuronales, gratis, sin API key) — voz configurable
         con el parametro 'voz' o la variable de entorno TTS_VOICE.
      2. gTTS (motor anterior, gratis, requiere internet).
      3. pyttsx3 (motor offline del sistema, sin internet).
    """
    voz = voz or os.environ.get("TTS_VOICE", VOZ_DEFAULT)
    try:
        print(f"   -> Usando edge-tts (voz: {voz})...")
        return _generar_audio_edge_tts(texto, ruta_salida, voz)
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
            "No se pudo generar audio con edge-tts, gTTS ni pyttsx3. "
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
