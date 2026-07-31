"""
api/library.py
Biblioteca de imágenes y QR reutilizables.
"""
import io
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

LIBRARY_DIR = Path(__file__).parent.parent / "_library"
LIBRARY_DIR.mkdir(exist_ok=True)
INDEX_FILE = LIBRARY_DIR / "index.json"

router = APIRouter(prefix="/api/library", tags=["library"])

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


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
def list_library():
    return _load_index()


@router.post("/upload")
async def upload_image(file: UploadFile = File(...), name: str = Form("")):
    ext = Path(file.filename or "image.png").suffix.lower() or ".png"
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Formato no permitido: {ext}")
    content = await file.read()
    item_id = uuid.uuid4().hex[:10]
    filename = f"{item_id}{ext}"
    (LIBRARY_DIR / filename).write_bytes(content)
    item = {
        "id": item_id,
        "name": name or Path(file.filename or "imagen").stem,
        "type": "image",
        "filename": filename,
        "created_at": datetime.utcnow().isoformat(),
    }
    items = _load_index()
    items.insert(0, item)
    _save_index(items)
    return item


class QRSaveBody(BaseModel):
    destination: str
    name: str = ""


@router.post("/qr")
def save_qr(body: QRSaveBody):
    import hotspot_manager as hm
    size = 400
    img = hm._render_qr_overlay(body.destination, 0, 0, size, size)
    item_id = uuid.uuid4().hex[:10]
    filename = f"{item_id}.png"
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    (LIBRARY_DIR / filename).write_bytes(buf.getvalue())
    item = {
        "id": item_id,
        "name": body.name or body.destination[:50],
        "type": "qr",
        "filename": filename,
        "destination": body.destination,
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
        raise HTTPException(status_code=404, detail="Item no encontrado")
    path = LIBRARY_DIR / item["filename"]
    if path.exists():
        path.unlink()
    _save_index([i for i in items if i["id"] != item_id])
    return {"ok": True}
