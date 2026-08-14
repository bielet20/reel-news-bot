"""
pronunciation_manager.py
━━━━━━━━━━━━━━━━━━━━━━━
Sistema de corrección de pronunciación para TTS.

Dos mecanismos:
  1. Sustitución de texto: reemplaza palabras antes de enviárselas al TTS.
     → Funciona con TODOS los motores (edge-tts, ElevenLabs, XTTS).
  2. Diccionario ElevenLabs (IPA): sube reglas de fonemas directamente a ElevenLabs.
     → Solo ElevenLabs, máxima precisión.

El diccionario se guarda en pronunciation_dict.json.

Uso como CLI:
  python pronunciation_manager.py --list
  python pronunciation_manager.py --add "ChatGPT" "chat-yi-pi-ti"
  python pronunciation_manager.py --add "DJ" "di-yei" --phoneme
  python pronunciation_manager.py --remove "ChatGPT"
  python pronunciation_manager.py --test "El DJ presentó el set con ayuda del ChatGPT"
  python pronunciation_manager.py --sync-elevenlabs   # Sube el dict a ElevenLabs
"""

import json
import os
import re
import argparse
from pathlib import Path

DICT_PATH = Path(__file__).parent / "pronunciation_dict.json"

# ── Diccionario por defecto — palabras que suelen pronunciarse mal ─────────
DEFAULT_DICT = {
    # Siglas / acrónimos
    "AI": {"replacement": "inteligencia artificial", "type": "text"},
    "IA": {"replacement": "inteligencia artificial", "type": "text"},
    "DJ": {"replacement": "di-yei", "type": "text"},
    "CEO": {"replacement": "si-i-ou", "type": "text"},
    "ChatGPT": {"replacement": "chat-yi-pi-ti", "type": "text"},
    "GPT": {"replacement": "yi-pi-ti", "type": "text"},
    "NFT": {"replacement": "ene-efe-ti", "type": "text"},
    "ONG": {"replacement": "o-ene-gue", "type": "text"},
    "UE": {"replacement": "Unión Europea", "type": "text"},
    "EE.UU.": {"replacement": "Estados Unidos", "type": "text"},
    "EEUU": {"replacement": "Estados Unidos", "type": "text"},
    "EUA": {"replacement": "Estados Unidos", "type": "text"},
    "BTC": {"replacement": "bitcoin", "type": "text"},
    "ETH": {"replacement": "ethereum", "type": "text"},
    "USD": {"replacement": "dólares", "type": "text"},
    "EUR": {"replacement": "euros", "type": "text"},

    # Nombres / marcas
    "Elon": {"replacement": "Ílon", "type": "text"},
    "YouTube": {"replacement": "iu-tub", "type": "text"},
    "iPhone": {"replacement": "ai-fon", "type": "text"},
    "Apple": {"replacement": "épol", "type": "text"},
    "Google": {"replacement": "gugol", "type": "text"},
    "Netflix": {"replacement": "nétflix", "type": "text"},
    "Twitch": {"replacement": "tuich", "type": "text"},
    "WhatsApp": {"replacement": "watsap", "type": "text"},
    "TikTok": {"replacement": "tik-tok", "type": "text"},
    "Spotify": {"replacement": "espotifai", "type": "text"},
    "SoundCloud": {"replacement": "saund-claud", "type": "text"},

    # Términos técnicos / noticias
    "hacker": {"replacement": "háker", "type": "text"},
    "hackers": {"replacement": "hákers", "type": "text"},
    "software": {"replacement": "sóftuer", "type": "text"},
    "hardware": {"replacement": "járduer", "type": "text"},
    "streaming": {"replacement": "estreaming", "type": "text"},
    "bitcoin": {"replacement": "bítcoin", "type": "text"},
    "blockchain": {"replacement": "blok-chein", "type": "text"},
    "startup": {"replacement": "estártap", "type": "text"},
    "startups": {"replacement": "estártaps", "type": "text"},
    "online": {"replacement": "on-lain", "type": "text"},
    "offline": {"replacement": "óflain", "type": "text"},
    "selfie": {"replacement": "sélfi", "type": "text"},
    "influencer": {"replacement": "influénser", "type": "text"},
    "influencers": {"replacement": "influénsers", "type": "text"},
    "live": {"replacement": "laiv", "type": "text"},

    # Abreviaturas comunes en noticias
    "etc.": {"replacement": "etcétera", "type": "text"},
    "aprox.": {"replacement": "aproximadamente", "type": "text"},
    "dpto.": {"replacement": "departamento", "type": "text"},
    "nº": {"replacement": "número", "type": "text"},
    "Nº": {"replacement": "número", "type": "text"},
    "km": {"replacement": "kilómetros", "type": "text"},
    "km²": {"replacement": "kilómetros cuadrados", "type": "text"},
    "m²": {"replacement": "metros cuadrados", "type": "text"},
    "kg": {"replacement": "kilogramos", "type": "text"},
}


def load_dict() -> dict:
    if DICT_PATH.exists():
        with open(DICT_PATH, encoding="utf-8") as f:
            return json.load(f)
    # Primera vez: guardar el diccionario por defecto
    save_dict(DEFAULT_DICT)
    return DEFAULT_DICT.copy()


def save_dict(d: dict):
    DICT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def apply_corrections(text: str, pronunciation_dict: dict = None) -> str:
    """
    Aplica el diccionario de pronunciación al texto antes de enviarlo al TTS.
    Respeta mayúsculas/minúsculas y límites de palabra.
    """
    if pronunciation_dict is None:
        pronunciation_dict = load_dict()

    for word, entry in pronunciation_dict.items():
        if entry.get("type") == "text":
            replacement = entry["replacement"]
            # Reemplazar con límites de palabra (case-insensitive)
            pattern = r'\b' + re.escape(word) + r'\b'
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def add_correction(word: str, replacement: str, phoneme: bool = False,
                   ipa: str = None, notes: str = ""):
    """Añade o actualiza una corrección en el diccionario."""
    d = load_dict()
    entry = {
        "replacement": replacement,
        "type": "phoneme_ipa" if phoneme else "text",
        "notes": notes,
    }
    if ipa:
        entry["ipa"] = ipa
    d[word] = entry
    save_dict(d)
    print(f"✓ '{word}' → '{replacement}' añadido al diccionario")


def remove_correction(word: str):
    d = load_dict()
    if word in d:
        del d[word]
        save_dict(d)
        print(f"✓ '{word}' eliminado del diccionario")
    else:
        print(f"'{word}' no está en el diccionario")


def test_correction(text: str) -> str:
    d = load_dict()
    corrected = apply_corrections(text, d)
    print(f"\nOriginal:   {text}")
    print(f"Corregido:  {corrected}\n")
    return corrected


def list_corrections():
    d = load_dict()
    print(f"\n{'='*60}")
    print(f"  Diccionario de pronunciación ({len(d)} entradas)")
    print(f"{'='*60}")
    for word, entry in sorted(d.items()):
        tipo = "📝" if entry.get("type") == "text" else "🔤"
        note = f"  # {entry['notes']}" if entry.get("notes") else ""
        print(f"  {tipo} {word:<20} → {entry['replacement']}{note}")
    print()


# ── Integración ElevenLabs Pronunciation Dictionary ───────────────────────

def sync_elevenlabs(dict_id: str = None) -> str:
    """
    Sube el diccionario de pronunciación a ElevenLabs.
    Si dict_id es None, crea uno nuevo. Devuelve el dict_id.

    El diccionario en ElevenLabs usa formato PLS (Pronunciation Lexicon Specification).
    """
    from elevenlabs.client import ElevenLabs

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Falta ELEVENLABS_API_KEY")

    d = load_dict()
    pls_entries = []

    for word, entry in d.items():
        if entry.get("ipa"):
            # Entrada con IPA específica — máxima precisión
            pls_entries.append(
                f'    <lexeme>\n'
                f'      <grapheme>{word}</grapheme>\n'
                f'      <phoneme alphabet="ipa">{entry["ipa"]}</phoneme>\n'
                f'    </lexeme>'
            )

    if not pls_entries:
        print("[ElevenLabs] Sin entradas IPA para sincronizar. Añade entradas con --phoneme y --ipa.")
        return dict_id or ""

    pls_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<lexicon version="1.0" xmlns="http://www.w3.org/2005/01/pronunciation-lexicon" '
        'alphabet="ipa" xml:lang="es">\n'
        + "\n".join(pls_entries)
        + "\n</lexicon>"
    )

    client = ElevenLabs(api_key=api_key)

    if dict_id:
        # Actualizar existente
        client.pronunciation_dictionary.add_rules_from_the_pronunciation_dictionary(
            pronunciation_dictionary_id=dict_id,
            rules=[{"type": "phoneme", "string_to_replace": w,
                    "phoneme": e["ipa"], "alphabet": "ipa"}
                   for w, e in d.items() if e.get("ipa")]
        )
        print(f"[ElevenLabs] Diccionario actualizado: {dict_id}")
    else:
        # Crear nuevo
        resp = client.pronunciation_dictionary.create_from_file(
            file=pls_content.encode("utf-8"),
            name="Rayver News Bot",
        )
        dict_id = resp.id
        print(f"[ElevenLabs] Diccionario creado: {dict_id}")
        print(f"  → Guarda este ID en .env: ELEVENLABS_PRONUNCIATION_DICT_ID={dict_id}")

    return dict_id


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gestión de pronunciación TTS")
    parser.add_argument("--list", "-l", action="store_true", help="Listar todas las correcciones")
    parser.add_argument("--add", "-a", nargs=2, metavar=("PALABRA", "SUSTITUCIÓN"),
                        help="Añadir o actualizar una corrección")
    parser.add_argument("--remove", "-r", metavar="PALABRA", help="Eliminar una corrección")
    parser.add_argument("--test", "-t", metavar="TEXTO", help="Probar el diccionario en un texto")
    parser.add_argument("--phoneme", action="store_true",
                        help="Con --add: marcar como entrada fonética (para ElevenLabs)")
    parser.add_argument("--ipa", metavar="FONEMAS_IPA",
                        help="Con --add: fonemas IPA exactos (ej: 'ˈbet.koin')")
    parser.add_argument("--notes", default="", help="Con --add: nota/comentario")
    parser.add_argument("--sync-elevenlabs", action="store_true",
                        help="Sincronizar entradas IPA con ElevenLabs Pronunciation Dictionary")
    parser.add_argument("--dict-id", default=None,
                        help="Con --sync-elevenlabs: ID de diccionario existente a actualizar")

    args = parser.parse_args()

    if args.list:
        list_corrections()
    elif args.add:
        add_correction(args.add[0], args.add[1], phoneme=args.phoneme,
                       ipa=args.ipa, notes=args.notes)
    elif args.remove:
        remove_correction(args.remove)
    elif args.test:
        test_correction(args.test)
    elif args.sync_elevenlabs:
        sync_elevenlabs(args.dict_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
