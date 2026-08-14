#!/usr/bin/env python3
"""
voice_lab.py — Laboratorio de Voces para Reel News Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Explora, compara y configura la voz para el bot.

Uso:
  python voice_lab.py --list-el          # Lista voces ElevenLabs disponibles
  python voice_lab.py --list-edge        # Lista voces edge-tts (gratis)
  python voice_lab.py --sample VOICE_ID  # Genera muestra de una voz ElevenLabs
  python voice_lab.py --compare          # Genera la misma frase con varias voces
  python voice_lab.py --set-voice        # Guarda la voz elegida como predeterminada
  python voice_lab.py --settings         # Ajusta parámetros de voz (stability, etc.)
  python voice_lab.py --test-local       # Prueba XTTS v2 local (requiere GPU)
"""

import argparse
import os
import json
import subprocess
from pathlib import Path

SAMPLE_TEXT = (
    "El DJ Rayver presentó su nuevo set de música electrónica, "
    "combinando techno y trance ante miles de seguidores en el festival. "
    "El evento, transmitido en streaming, batió récords con más de cincuenta mil conexiones."
)

SETTINGS_PATH = Path(__file__).parent / "voice_settings.json"
SAMPLES_DIR = Path(__file__).parent / "_voice_samples"

# Voces ElevenLabs recomendadas para noticias en español
SUGGESTED_EL_VOICES = [
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam",        "style": "narración, claro"},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni",      "style": "cálido, presentador"},
    {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold",      "style": "profundo, dramático"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh",        "style": "joven, dinámico"},
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel",      "style": "profesional, mujer"},
    {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi",        "style": "enérgica, joven"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella",       "style": "cálida, reportera"},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli",        "style": "clara, presentadora"},
]


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {
        "service": "auto",
        "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
        "edge_voice": "es-ES-AlvaroNeural",
        "elevenlabs_settings": {
            "stability": 0.5,           # 0.0–1.0 (0=más variado, 1=más estable/monotono)
            "similarity_boost": 0.75,   # 0.0–1.0 (0=menos parecido a la voz, 1=máximo)
            "style": 0.0,               # 0.0–1.0 (estilo/emoción, consume más créditos)
            "use_speaker_boost": True,  # Mejora la claridad
            "speed": 1.0,               # 0.7–1.3 (velocidad de habla)
        },
        "model": "eleven_multilingual_v2",
    }


def save_settings(settings: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    print(f"✓ Configuración guardada en {SETTINGS_PATH}")


def list_elevenlabs_voices(filter_lang: str = None):
    """Lista las voces de ElevenLabs disponibles en tu cuenta."""
    try:
        from elevenlabs.client import ElevenLabs
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            print("[ElevenLabs] Falta ELEVENLABS_API_KEY en .env")
            return

        client = ElevenLabs(api_key=api_key)
        resp = client.voices.get_all()
        voices = resp.voices

        print(f"\n{'='*65}")
        print(f"  Voces ElevenLabs disponibles ({len(voices)} total)")
        print(f"{'='*65}")
        print(f"  {'ID':<28} {'Nombre':<20} {'Descripción'}")
        print(f"  {'-'*28} {'-'*20} {'-'*15}")

        for v in sorted(voices, key=lambda x: x.name):
            labels = dict(v.labels) if v.labels else {}
            desc = labels.get("description", labels.get("accent", labels.get("age", "")))
            print(f"  {v.voice_id:<28} {v.name:<20} {desc}")
        print()

    except ImportError:
        print("[ElevenLabs] Instala: pip install elevenlabs")
        print("\nVoces sugeridas para noticias en español:")
        for v in SUGGESTED_EL_VOICES:
            print(f"  {v['id']:<28} {v['name']:<12} ({v['style']})")


def list_edge_voices():
    """Lista voces edge-tts disponibles en español."""
    from tts import VOCES_EDGE_ES

    print(f"\n{'='*55}")
    print(f"  Voces edge-tts en español (gratis, sin API key)")
    print(f"{'='*55}")
    for v in VOCES_EDGE_ES:
        print(f"  {v['id']:<30} {v['name']}")
    print()


def generate_sample(voice_id: str, text: str = None, service: str = "elevenlabs",
                    settings: dict = None) -> Path:
    """Genera un audio de muestra con una voz específica."""
    SAMPLES_DIR.mkdir(exist_ok=True)
    text = text or SAMPLE_TEXT
    out = SAMPLES_DIR / f"sample_{voice_id[:15]}.mp3"

    print(f"\n[VoiceLab] Generando muestra con voz: {voice_id}")
    print(f"[VoiceLab] Texto: {text[:80]}...")

    from tts import generar_audio
    generar_audio(text, str(out), voz=voice_id, servicio=service)

    print(f"[VoiceLab] Guardado en: {out}")
    _play_audio(out)
    return out


def compare_voices(voice_ids: list[str] = None, text: str = None):
    """Genera la misma frase con varias voces para comparar."""
    SAMPLES_DIR.mkdir(exist_ok=True)
    text = text or SAMPLE_TEXT

    if not voice_ids:
        # Usa las voces sugeridas
        voice_ids = [v["id"] for v in SUGGESTED_EL_VOICES[:4]]

    print(f"\n[VoiceLab] Comparando {len(voice_ids)} voces...")
    print(f"[VoiceLab] Texto: {text[:80]}...\n")

    results = []
    for vid in voice_ids:
        out = SAMPLES_DIR / f"compare_{vid[:15]}.mp3"
        try:
            from tts import generar_audio
            generar_audio(text, str(out), voz=vid, servicio="elevenlabs")
            results.append((vid, out))
            name = next((v["name"] for v in SUGGESTED_EL_VOICES if v["id"] == vid), vid[:12])
            print(f"  ✓ {name} ({vid[:15]}...): {out.name}")
        except Exception as e:
            print(f"  ✗ {vid}: {e}")

    print(f"\n[VoiceLab] Muestras en {SAMPLES_DIR}/")
    print("[VoiceLab] Escúchalas y luego ejecuta:")
    print('  python voice_lab.py --set-voice VOICE_ID\n')


def interactive_settings():
    """Interfaz interactiva para ajustar parámetros de voz."""
    settings = load_settings()
    el = settings["elevenlabs_settings"]

    print("\n╔══════════════════════════════════════════╗")
    print("║    Voice Lab — Ajuste de parámetros      ║")
    print("╚══════════════════════════════════════════╝")
    print("\nConfiguración actual:")
    print(f"  Servicio:    {settings['service']}")
    print(f"  Voz EL:      {settings['elevenlabs_voice_id']}")
    print(f"  Modelo:      {settings['model']}")
    print(f"  Stability:   {el['stability']}  (0=variado, 1=monotono)")
    print(f"  Similarity:  {el['similarity_boost']}  (0=libre, 1=fiel a la voz)")
    print(f"  Style:       {el['style']}  (0=neutro, 1=expresivo)")
    print(f"  Speed:       {el['speed']}  (0.7=lento, 1.3=rápido)")
    print()

    print("Introduce los nuevos valores (Enter para mantener el actual):")

    def ask(prompt, current, type_=float, valid_range=None):
        val = input(f"  {prompt} [{current}]: ").strip()
        if not val:
            return current
        try:
            v = type_(val)
            if valid_range and not (valid_range[0] <= v <= valid_range[1]):
                print(f"  ⚠ Valor fuera de rango {valid_range}, usando {current}")
                return current
            return v
        except ValueError:
            return current

    el["stability"] = ask("Stability (0.0–1.0)", el["stability"], float, (0.0, 1.0))
    el["similarity_boost"] = ask("Similarity (0.0–1.0)", el["similarity_boost"], float, (0.0, 1.0))
    el["style"] = ask("Style (0.0–1.0)", el["style"], float, (0.0, 1.0))
    el["speed"] = ask("Speed (0.7–1.3)", el["speed"], float, (0.7, 1.3))

    model = input(f"  Modelo [{settings['model']}] (eleven_multilingual_v2 / eleven_turbo_v2_5): ").strip()
    if model in ("eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5"):
        settings["model"] = model

    settings["elevenlabs_settings"] = el
    save_settings(settings)

    print("\n¿Generar una muestra con la nueva configuración? [S/n]: ", end="")
    if input().strip().lower() != "n":
        generate_sample(settings["elevenlabs_voice_id"], settings=el)


def set_voice(voice_id: str, service: str = "elevenlabs"):
    settings = load_settings()
    if service == "elevenlabs":
        settings["elevenlabs_voice_id"] = voice_id
        settings["service"] = "elevenlabs"
    else:
        settings["edge_voice"] = voice_id
        settings["service"] = "edge-tts"
    save_settings(settings)
    print(f"✓ Voz predeterminada: {voice_id} ({service})")

    print("\n¿Generar una muestra de prueba? [S/n]: ", end="")
    if input().strip().lower() != "n":
        generate_sample(voice_id, service=service)


def test_local_xtts(text: str = None):
    """
    Prueba el motor XTTS v2 local (requiere GPU + pip install TTS).
    Ideal para iterar sin gastar créditos de ElevenLabs.
    """
    try:
        from TTS.api import TTS
    except ImportError:
        print("[XTTS] Instala: pip install TTS")
        print("  Nota: requiere GPU con CUDA y ~4 GB de VRAM mínimo.")
        return

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    text = text or SAMPLE_TEXT
    out = SAMPLES_DIR / "sample_xtts_local.wav"
    SAMPLES_DIR.mkdir(exist_ok=True)

    print(f"[XTTS] Cargando modelo en {device} (primera vez ~5 min de descarga)...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

    # Referencia: usa un sample de alta calidad como "semilla" de voz
    ref_audio = SAMPLES_DIR / "reference_voice.wav"
    if not ref_audio.exists():
        print(f"[XTTS] ⚠ No hay audio de referencia en {ref_audio}")
        print("  Para clonar una voz, guarda un WAV de 10-30 seg de audio limpio")
        print("  de la voz que quieres usar como base.\n")
        # Genera sin referencia usando una voz base de XTTS
        tts.tts_to_file(text=text, language="es", file_path=str(out))
    else:
        tts.tts_to_file(text=text, speaker_wav=str(ref_audio), language="es", file_path=str(out))

    print(f"[XTTS] Audio generado: {out}")
    _play_audio(out)


def _play_audio(path: Path):
    """Reproduce el audio si hay un player disponible."""
    import platform
    try:
        if platform.system() == "Darwin":
            subprocess.run(["afplay", str(path)], check=True)
        elif platform.system() == "Linux":
            for player in ["mpv", "ffplay", "aplay", "paplay"]:
                result = subprocess.run(["which", player], capture_output=True)
                if result.returncode == 0:
                    subprocess.run([player, str(path)], capture_output=True)
                    break
        elif platform.system() == "Windows":
            os.startfile(str(path))
    except Exception:
        print(f"  (abre manualmente: {path})")


def main():
    parser = argparse.ArgumentParser(description="Voice Lab — Laboratorio de Voces TTS")
    parser.add_argument("--list-el", action="store_true", help="Lista voces ElevenLabs")
    parser.add_argument("--list-edge", action="store_true", help="Lista voces edge-tts")
    parser.add_argument("--sample", metavar="VOICE_ID", help="Muestra de una voz EL")
    parser.add_argument("--sample-edge", metavar="VOICE_ID", help="Muestra de una voz edge-tts")
    parser.add_argument("--compare", nargs="*", metavar="VOICE_IDS",
                        help="Compara voces (sin args: usa voces sugeridas)")
    parser.add_argument("--set-voice", metavar="VOICE_ID", help="Guarda voz como predeterminada")
    parser.add_argument("--set-edge", metavar="VOICE_ID", help="Guarda voz edge-tts como predeterminada")
    parser.add_argument("--settings", action="store_true", help="Ajusta parámetros interactivamente")
    parser.add_argument("--show-settings", action="store_true", help="Muestra configuración actual")
    parser.add_argument("--test-local", action="store_true", help="Prueba XTTS v2 local (GPU)")
    parser.add_argument("--text", metavar="TEXTO", help="Texto personalizado para muestras")
    args = parser.parse_args()

    if args.list_el:
        list_elevenlabs_voices()
    elif args.list_edge:
        list_edge_voices()
    elif args.sample:
        generate_sample(args.sample, text=args.text)
    elif args.sample_edge:
        generate_sample(args.sample_edge, text=args.text, service="edge-tts")
    elif args.compare is not None:
        compare_voices(args.compare or None, text=args.text)
    elif args.set_voice:
        set_voice(args.set_voice, "elevenlabs")
    elif args.set_edge:
        set_voice(args.set_edge, "edge-tts")
    elif args.settings:
        interactive_settings()
    elif args.show_settings:
        s = load_settings()
        print(json.dumps(s, indent=2, ensure_ascii=False))
    elif args.test_local:
        test_local_xtts(text=args.text)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
