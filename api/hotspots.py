"""
api/hotspots.py
Router FastAPI para CRUD de hotspots de video.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import hotspot_manager as hm

router = APIRouter(prefix="/api/hotspots", tags=["hotspots"])

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _assert_video(filename: str):
    if not (OUTPUT_DIR / filename).exists():
        raise HTTPException(status_code=404, detail=f"Video no encontrado: {filename}")


class Region(BaseModel):
    x: float
    y: float
    width: float
    height: float


class HotspotIn(BaseModel):
    type: str = "text"          # "text" | "qr" | "image"
    time_start: float
    time_end: float
    region: Region
    destination: str = ""
    label: str = ""
    hold_ms: Optional[int] = None
    font_size: Optional[int] = None
    library_id: Optional[str] = None
    library_filename: Optional[str] = None


class ConfigIn(BaseModel):
    hold_ms_default: int = 800


@router.get("/render-preview")
def render_preview(
    type: str = Query("text"),
    label: str = Query(""),
    destination: str = Query(""),
    font_size: int = Query(0),
    pw: int = Query(200),
    ph: int = Query(100),
):
    """Renderiza un overlay con PIL y devuelve PNG — mismo código que burn."""
    import io
    pw = max(10, min(pw, 1920))
    ph = max(10, min(ph, 1920))
    if type == "qr" and destination:
        img = hm._render_qr_overlay(destination, 0, 0, pw, ph)
    else:
        img = hm._render_text_overlay(destination, label, 0, 0, pw, ph, font_size)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/{filename}")
def get_hotspots(filename: str):
    _assert_video(filename)
    return hm.get_hotspots(filename)


@router.post("/{filename}")
def create_hotspot(filename: str, body: HotspotIn):
    _assert_video(filename)
    hotspot = {
        "type": body.type,
        "time_start": body.time_start,
        "time_end": body.time_end,
        "region": body.region.model_dump(),
        "destination": body.destination,
        "label": body.label,
        "hold_ms": body.hold_ms,
        "font_size": body.font_size,
        "library_id": body.library_id,
        "library_filename": body.library_filename,
    }
    return hm.add_hotspot(filename, hotspot)


@router.put("/{filename}/config")
def update_config(filename: str, body: ConfigIn):
    _assert_video(filename)
    return hm.update_config(filename, body.hold_ms_default)


@router.put("/{filename}/{hotspot_id}")
def update_hotspot(filename: str, hotspot_id: str, body: HotspotIn):
    _assert_video(filename)
    updates = {
        "type": body.type,
        "time_start": body.time_start,
        "time_end": body.time_end,
        "region": body.region.model_dump(),
        "destination": body.destination,
        "label": body.label,
        "hold_ms": body.hold_ms,
        "font_size": body.font_size,
        "library_id": body.library_id,
        "library_filename": body.library_filename,
    }
    result = hm.update_hotspot(filename, hotspot_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Hotspot no encontrado")
    return result


@router.delete("/{filename}/{hotspot_id}")
def delete_hotspot(filename: str, hotspot_id: str):
    _assert_video(filename)
    if not hm.delete_hotspot(filename, hotspot_id):
        raise HTTPException(status_code=404, detail="Hotspot no encontrado")
    return {"ok": True}


@router.post("/{filename}/burn")
async def burn_video(filename: str):
    _assert_video(filename)
    from fastapi.concurrency import run_in_threadpool
    try:
        output = await run_in_threadpool(hm.burn_hotspots, filename)
        return {"output_filename": output}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
