"""
tts.py
Convierte el guion en audio narrado.

Motores disponibles (por prioridad):
  1. ElevenLabs (si ELEVENLABS_API_KEY esta en .env) — voces premium, multilingue.
  2. edge-tts (voces neuronales de Microsoft Edge, gratis, sin API key).
  3. XTTS v2 local (si TTS instalado + GPU) — gratis, sin internet.
  4. gTTS (Google Text-to-Speech, gratis).
  5. pyttsx3 (motor offline del sistema).

El texto pasa automáticamente por pronunciation_manager antes de enviarse al TTS.
La configuración de voz se carga de voice_settings.json si existe.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

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


def _load_voice_settings() -> dict:
    """Carga la configuración de voz desde voice_settings.json si existe."""
    settings_path = Path(__file__).parent / "voice_settings.json"
    if settings_path.exists():
        with open(settings_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _generar_audio_elevenlabs(texto: str, ruta_salida: str, voice_id: str,
                               model_id: str = None,
                               voice_settings: dict = None) -> str:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Falta ELEVENLABS_API_KEY en las variables de entorno")

    # Cargar configuración guardada (voice_lab.py --settings)
    saved = _load_voice_settings()
    el_cfg = {**saved.get("elevenlabs_settings", {}), **(voice_settings or {})}
    if not model_id:
        model_id = saved.get("model", "eleven_multilingual_v2")

    client = ElevenLabs(api_key=api_key)

    kwargs = dict(
        voice_id=voice_id,
        text=texto,
        model_id=model_id,
        output_format="mp3_44100_128",
    )

    # Aplicar VoiceSettings si hay configuración personalizada
    if el_cfg:
        kwargs["voice_settings"] = VoiceSettings(
            stability=float(el_cfg.get("stability", 0.5)),
            similarity_boost=float(el_cfg.get("similarity_boost", 0.75)),
            style=float(el_cfg.get("style", 0.0)),
            use_speaker_boost=bool(el_cfg.get("use_speaker_boost", True)),
            speed=float(el_cfg.get("speed", 1.0)),
        )

    # Aplicar diccionario de pronunciación ElevenLabs si está configurado
    dict_id = os.environ.get("ELEVENLABS_PRONUNCIATION_DICT_ID")
    if dict_id:
        kwargs["pronunciation_dictionary_locators"] = [
            {"pronunciation_dictionary_id": dict_id, "version_id": "latest"}
        ]

    audio_gen = client.text_to_speech.convert(**kwargs)
    with open(ruta_salida, "wb") as f:
        for chunk in audio_gen:
            if chunk:
                f.write(chunk)

    if not os.path.isfile(ruta_salida) or os.path.getsize(ruta_salida) == 0:
        raise RuntimeError("ElevenLabs genero un archivo vacio")
    return ruta_salida


def _generar_audio_xtts_local(texto: str, ruta_salida: str,
                               reference_wav: str = None, language: str = "es") -> str:
    """Motor XTTS v2 local (GPU). Gratis, sin internet. Requiere: pip install TTS"""
    try:
        from TTS.api import TTS
        import torch
    except ImportError:
        raise RuntimeError("Instala TTS para usar motor local: pip install TTS")

    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"

    # Cargar modelo (se cachea tras la primera descarga)
    tts_engine = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

    ref = reference_wav or str(Path(__file__).parent / "_voice_samples" / "reference_voice.wav")
    out_wav = ruta_salida.replace(".mp3", ".wav")

    if Path(ref).exists():
        tts_engine.tts_to_file(text=texto, speaker_wav=ref, language=language, file_path=out_wav)
    else:
        tts_engine.tts_to_file(text=texto, language=language, file_path=out_wav)

    # Convertir WAV → MP3
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-i", out_wav, "-b:a", "192k", ruta_salida],
                   check=True, capture_output=True)
    Path(out_wav).unlink(missing_ok=True)
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
                   voz: str = None, servicio: str = "auto",
                   apply_pronunciation: bool = True) -> str:
    """
    Genera audio narrado. Devuelve la ruta del archivo.

    servicio: "auto" | "elevenlabs" | "edge-tts" | "xtts"
      - "auto": usa ElevenLabs si hay API key, si no edge-tts.
      - "elevenlabs": fuerza ElevenLabs (falla si no hay key).
      - "edge-tts": fuerza edge-tts (gratis, Microsoft Azure).
      - "xtts": motor local XTTS v2 (requiere GPU + pip install TTS).
    voz: voice_id de ElevenLabs, nombre de voz edge-tts, o ruta WAV ref. para XTTS.
    apply_pronunciation: aplica correcciones del diccionario antes de generar (default True).
    """
    # Aplicar diccionario de pronunciación antes de generar
    if apply_pronunciation:
        try:
            from pronunciation_manager import apply_corrections
            texto_original = texto
            texto = apply_corrections(texto)
            if texto != texto_original:
                print(f"   -> Pronunciación corregida ({sum(1 for a,b in zip(texto_original.split(), texto.split()) if a!=b)} palabras ajustadas)")
        except ImportError:
            pass  # pronunciation_manager no disponible, continuar sin correcciones

    # Cargar voz predeterminada de voice_settings.json si no se especifica
    if not voz:
        saved = _load_voice_settings()
        if servicio in ("auto", "elevenlabs") and saved.get("elevenlabs_voice_id"):
            voz_el = saved["elevenlabs_voice_id"]
        else:
            voz_el = None
        if servicio in ("auto", "edge-tts") and saved.get("edge_voice"):
            voz_edge_saved = saved["edge_voice"]
        else:
            voz_edge_saved = None
        if servicio == "auto" and saved.get("service"):
            servicio = saved["service"]
    else:
        voz_el = voz if servicio not in ("edge-tts",) else None
        voz_edge_saved = voz if servicio == "edge-tts" else None

    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY")
    usar_elevenlabs = servicio == "elevenlabs" or (servicio == "auto" and elevenlabs_key)

    # Motor XTTS local (forzado)
    if servicio == "xtts":
        try:
            print("   -> Usando XTTS v2 local (GPU)...")
            return _generar_audio_xtts_local(texto, ruta_salida, reference_wav=voz, language=idioma)
        except Exception as e:
            print(f"[tts] XTTS fallo ({e}), usando edge-tts...")

    if usar_elevenlabs:
        voice_id = voz_el or os.environ.get("ELEVENLABS_VOICE_ID", VOZ_DEFAULT_ELEVENLABS)
        try:
            print(f"   -> Usando ElevenLabs (voice_id: {voice_id})...")
            return _generar_audio_elevenlabs(texto, ruta_salida, voice_id)
        except ImportError:
            print("[tts] elevenlabs SDK no instalado (pip install elevenlabs), usando edge-tts...")
        except Exception as e:
            print(f"[tts] ElevenLabs fallo ({e}), usando edge-tts...")

    voz_edge = voz_edge_saved or (voz if servicio not in ("elevenlabs", "xtts") else None) or os.environ.get("TTS_VOICE", VOZ_DEFAULT_EDGE)
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
    ruta = generar_audio("Esta es una prueba del sistema de texto a voz.",
                         os.path.join(tempfile.gettempdir(), "prueba_tts.mp3"))
    print("Generado en:", ruta)
    print("Duracion:", duracion_audio(ruta), "segundos")
