"""
api/music.py
Biblioteca de pistas de música de fondo para reels.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

MUSIC_DIR = Path(__file__).parent.parent / "_music"
MUSIC_DIR.mkdir(exist_ok=True)
INDEX_FILE = MUSIC_DIR / "index.json"

ALLOWED_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}

router = APIRouter(prefix="/api/music", tags=["music"])


def _load_index() -> list:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_index(items: list) -> None:
    INDEX_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@router.get("")
def list_music():
    return _load_index()


@router.post("/upload")
async def upload_music(file: UploadFile = File(...), name: str = Form("")):
    ext = Path(file.filename or "track.mp3").suffix.lower() or ".mp3"
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Formato no permitido: {ext}. Usa MP3, WAV, OGG, M4A, AAC o FLAC.")
    content = await file.read()
    item_id = uuid.uuid4().hex[:10]
    filename = f"{item_id}{ext}"
    (MUSIC_DIR / filename).write_bytes(content)

    # Intentar obtener duración
    duration_s = None
    try:
        import mutagen
        audio = mutagen.File(str(MUSIC_DIR / filename))
        if audio and audio.info:
            duration_s = round(audio.info.length, 1)
    except Exception:
        pass

    item = {
        "id": item_id,
        "name": name or Path(file.filename or "pista").stem,
        "filename": filename,
        "duration_s": duration_s,
        "created_at": datetime.utcnow().isoformat(),
    }
    items = _load_index()
    items.insert(0, item)
    _save_index(items)
    return item


@router.delete("/{item_id}")
def delete_item(item_id: str):
    items = _load_index()
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Pista no encontrada")
    path = MUSIC_DIR / item["filename"]
    if path.exists():
        path.unlink()
    _save_index([i for i in items if i["id"] != item_id])
    return {"ok": True}
