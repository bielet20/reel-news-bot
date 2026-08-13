"""
api/music_clip.py
Endpoints para la sección de Montaje: subida de audio y generación de clips.
"""
import os
import sys
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

CORE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = CORE_DIR / "output"
UPLOADS_DIR = CORE_DIR / "_uploads"
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

_jobs: dict = {}
_lock = threading.Lock()

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}


# ── Upload de audio ───────────────────────────────────────────────────────────

@router.post("/api/music-clip/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """Sube un archivo de audio. Devuelve la ruta interna para usarla en /generate."""
    ext = Path(file.filename or "audio.mp3").suffix.lower()
    if ext not in AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {ext}. Usa mp3, wav, flac, aac, m4a.")

    nombre = f"lyric_{uuid.uuid4().hex[:10]}{ext}"
    ruta = UPLOADS_DIR / nombre
    content = await file.read()

    if len(content) > 50 * 1024 * 1024:  # 50 MB max
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB.")

    ruta.write_bytes(content)
    return {"path": str(ruta), "filename": nombre, "size": len(content)}


# ── Generación de clips ───────────────────────────────────────────────────────

class MusicClipRequest(BaseModel):
    audio_path: str           # ruta devuelta por upload-audio
    letra: str                # texto de la letra
    artista: str = ""
    titulo: str = ""
    estilo: str = "cinematico"   # clave de ESTILOS
    mostrar_letra: bool = True
    mostrar_cabecera: bool = True


@router.post("/api/music-clip/generate")
def generate_music_clip(req: MusicClipRequest):
    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de audio no encontrado.")
    if not req.letra.strip():
        raise HTTPException(status_code=400, detail="La letra no puede estar vacía.")

    job_id = uuid.uuid4().hex[:8]

    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "progress": {"actual": 0, "total": 0, "label": "Iniciando…"},
            "output_files": [],
            "error": None,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        }

    threading.Thread(target=_run, args=(job_id, req, audio_path), daemon=True).start()
    return {"job_id": job_id}


def _run(job_id: str, req: MusicClipRequest, audio_path: Path):
    sys.path.insert(0, str(CORE_DIR))

    def progreso(idx: int, total: int, label: str):
        with _lock:
            _jobs[job_id]["progress"] = {
                "actual": idx + 1,
                "total": total,
                "label": f"Generando clip {idx + 1}/{total}: {label}…",
            }

    try:
        from lyric_video_builder import generar_clips

        slug = re.sub(r"[^\w]", "_", (req.titulo or req.artista or "clip").lower())[:24]
        base = str(OUTPUT_DIR / slug)

        rutas = generar_clips(
            ruta_audio=str(audio_path),
            letra=req.letra,
            artista=req.artista,
            titulo=req.titulo,
            estilo=req.estilo,
            ruta_salida_base=base,
            mostrar_letra=req.mostrar_letra,
            mostrar_cabecera=req.mostrar_cabecera,
            cb_progreso=progreso,
        )

        nombres = [Path(r).name for r in rutas]
        with _lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["output_files"] = nombres
            _jobs[job_id]["completed_at"] = datetime.now().isoformat()

    except Exception as e:
        import traceback
        with _lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
            _jobs[job_id]["completed_at"] = datetime.now().isoformat()
        print(f"[MusicClip] Error: {traceback.format_exc()}")


# Importar re aquí para poder usarlo en _run
import re


@router.get("/api/music-clip/jobs/{job_id}")
def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return job


@router.get("/api/music-clip/estilos")
def list_estilos():
    from lyric_video_builder import ESTILOS
    return [{"id": k, "label": k.capitalize()} for k in ESTILOS]


@router.get("/api/music-clip/audio-preview")
def audio_preview(path: str):
    """Sirve el archivo de audio subido para previsualización en el player."""
    from fastapi.responses import FileResponse
    p = Path(path)
    # Seguridad: solo servir archivos dentro de _uploads
    if not p.is_file() or UPLOADS_DIR not in p.parents:
        raise HTTPException(status_code=404, detail="Audio no encontrado.")
    suffix = p.suffix.lower()
    mime_map = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
        ".aac": "audio/aac", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
    }
    return FileResponse(str(p), media_type=mime_map.get(suffix, "audio/mpeg"))
