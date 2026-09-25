"""
api/prefs.py
Preferencias de generación de reels (persiste en _config/generation_prefs.json).
"""
import json
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

CORE_DIR = Path(__file__).parent.parent
PREFS_FILE = CORE_DIR / "_config" / "generation_prefs.json"

DEFAULTS = {
    "servicio_voz":       "edge-tts",
    "voz":                "es-ES-AlvaroNeural",
    "tipo_contenido":     "noticia",
    "duracion_maxima":    60,
    "mostrar_subtitulos": True,
    "mostrar_titulo":     True,
    "marca":              "",
    "generar_imagenes_ai": False,
    "servicio_ai":        "pollinations",
    "musica_fondo":       None,
    "volumen_musica":     0.3,
    "volumen_voz":        1.0,
}


def load_prefs() -> dict:
    try:
        if PREFS_FILE.exists():
            saved = json.loads(PREFS_FILE.read_text("utf-8"))
            return {**DEFAULTS, **saved}
    except Exception:
        pass
    return dict(DEFAULTS)


def save_prefs(prefs: dict):
    PREFS_FILE.parent.mkdir(exist_ok=True)
    PREFS_FILE.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), "utf-8")


class GenerationPrefs(BaseModel):
    servicio_voz:       str   = "edge-tts"
    voz:                str   = "es-ES-AlvaroNeural"
    tipo_contenido:     str   = "noticia"
    duracion_maxima:    int   = 60
    mostrar_subtitulos: bool  = True
    mostrar_titulo:     bool  = True
    marca:              str   = ""
    generar_imagenes_ai: bool = False
    servicio_ai:        str   = "pollinations"
    musica_fondo:       Optional[str] = None
    volumen_musica:     float = 0.3
    volumen_voz:        float = 1.0


@router.get("/api/prefs/generation")
def get_prefs():
    return load_prefs()


@router.put("/api/prefs/generation")
def update_prefs(body: GenerationPrefs):
    prefs = body.model_dump()
    save_prefs(prefs)
    return prefs
