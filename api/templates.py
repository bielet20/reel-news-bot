"""
api/templates.py
Plantillas de hotspots reutilizables (solo posición/estilo, sin tiempos).
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

TEMPLATES_DIR = Path(__file__).parent.parent / "_templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
INDEX_FILE = TEMPLATES_DIR / "index.json"

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _load() -> list:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(items: list) -> None:
    INDEX_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class TemplateIn(BaseModel):
    name: str
    description: str = ""
    hotspots: List[Any]


@router.get("")
def list_templates():
    return _load()


@router.post("")
def create_template(body: TemplateIn):
    stripped = []
    for h in body.hotspots:
        s = {k: v for k, v in h.items() if k not in ("time_start", "time_end", "id")}
        stripped.append(s)
    item = {
        "id": uuid.uuid4().hex[:10],
        "name": body.name,
        "description": body.description,
        "hotspots": stripped,
        "created_at": datetime.utcnow().isoformat(),
    }
    items = _load()
    items.insert(0, item)
    _save(items)
    return item


@router.delete("/{template_id}")
def delete_template(template_id: str):
    items = _load()
    if not any(i["id"] == template_id for i in items):
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    _save([i for i in items if i["id"] != template_id])
    return {"ok": True}
