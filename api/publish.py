"""
api/publish.py
Publicación de videos generados a YouTube, TikTok e Instagram.
"""
import os
import sys
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

CORE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = CORE_DIR / "output"

_jobs: dict = {}
_lock = threading.Lock()


class PublishRequest(BaseModel):
    filename: str
    titulo: str = ""
    descripcion: str = ""
    platforms: list[str]          # ["youtube", "tiktok", "instagram", "telegram", "whatsapp"]
    tipo_contenido: str = "noticia"  # youtube: noticia | curiosidad
    tiktok_privacy: str = "SELF_ONLY"


@router.post("/api/publish")
def publish_video(req: PublishRequest):
    file_path = OUTPUT_DIR / req.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de video no encontrado")
    if not req.platforms:
        raise HTTPException(status_code=400, detail="Selecciona al menos una plataforma")

    job_id = uuid.uuid4().hex[:8]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "filename": req.filename,
            "platforms": req.platforms,
            "status": "running",
            "results": {p: {"status": "pending"} for p in req.platforms},
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        }

    threading.Thread(target=_do_publish, args=(job_id, req, file_path), daemon=True).start()
    return {"job_id": job_id}


def _do_publish(job_id: str, req: PublishRequest, file_path: Path):
    sys.path.insert(0, str(CORE_DIR))
    results = {}

    for platform in req.platforms:
        with _lock:
            _jobs[job_id]["results"][platform] = {"status": "uploading"}

        try:
            if platform == "youtube":
                r = _upload_youtube(req, file_path)
            elif platform == "tiktok":
                r = _upload_tiktok(req, file_path)
            elif platform == "instagram":
                r = _upload_instagram(req, file_path)
            elif platform == "telegram":
                r = _upload_telegram(req, file_path)
            elif platform == "whatsapp":
                r = _upload_whatsapp(req, file_path)
            else:
                r = {"status": "error", "error": "Plataforma desconocida"}
        except Exception as e:
            r = {"status": "error", "error": str(e)}

        results[platform] = r
        with _lock:
            _jobs[job_id]["results"][platform] = r

    all_failed = all(r.get("status") == "error" for r in results.values())
    with _lock:
        _jobs[job_id]["status"] = "failed" if all_failed else "completed"
        _jobs[job_id]["completed_at"] = datetime.now().isoformat()


def _upload_youtube(req: PublishRequest, file_path: Path) -> dict:
    from accounts_manager import load_token
    from youtube_uploader import subir_video

    token = load_token("youtube")
    old_env: dict[str, Optional[str]] = {}

    if token:
        for key, val in {
            "YOUTUBE_CLIENT_ID": token.get("client_id", ""),
            "YOUTUBE_CLIENT_SECRET": token.get("client_secret", ""),
            "YOUTUBE_REFRESH_TOKEN": token.get("refresh_token", ""),
        }.items():
            old_env[key] = os.environ.get(key)
            if val:
                os.environ[key] = val

    try:
        resultado = subir_video(
            video_path=str(file_path),
            titulo=req.titulo or file_path.stem,
            tipo=req.tipo_contenido,
        )
        return {"status": "ok", "url": resultado["url"], "video_id": resultado["video_id"]}
    finally:
        if token:
            for key, val in old_env.items():
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val


def _upload_tiktok(req: PublishRequest, file_path: Path) -> dict:
    from tiktok_uploader import subir_video
    result = subir_video(
        str(file_path),
        titulo=req.titulo or file_path.stem,
        privacy=req.tiktok_privacy,
    )
    return {"status": "ok", "publish_id": result.get("publish_id")}


def _upload_instagram(req: PublishRequest, file_path: Path) -> dict:
    from instagram_uploader import subir_video
    caption = req.descripcion or req.titulo or file_path.stem
    result = subir_video(str(file_path), caption=caption)
    return {"status": "ok", "media_id": result.get("media_id")}


def _upload_telegram(req: PublishRequest, file_path: Path) -> dict:
    from telegram_uploader import subir_video
    caption = req.descripcion or req.titulo or file_path.stem
    result = subir_video(str(file_path), caption=caption)
    return {"status": "ok", "message_id": result.get("message_id")}


def _upload_whatsapp(req: PublishRequest, file_path: Path) -> dict:
    from whatsapp_uploader import subir_status
    caption = req.descripcion or req.titulo or file_path.stem
    result = subir_status(str(file_path), caption=caption)
    return {"status": "ok", **result}


@router.get("/api/publish/{job_id}")
def get_publish_status(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de publicación no encontrado")
    return job
