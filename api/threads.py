"""
api/threads.py
Hilos temáticos: agrupa noticias relacionadas para crear series de videos vinculadas.
Cada hilo es un tema continuo (ej: "Crisis de Ceuta") con varios episodios ordenados.
"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

CONFIG_DIR = Path(__file__).parent.parent / "_config"
CONFIG_DIR.mkdir(exist_ok=True)
THREADS_FILE = CONFIG_DIR / "threads.json"

_lock = threading.Lock()


def _load() -> list:
    try:
        return json.loads(THREADS_FILE.read_text("utf-8")) if THREADS_FILE.exists() else []
    except Exception:
        return []


def _save(data: list):
    THREADS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


class ThreadCreate(BaseModel):
    nombre: str       # "Crisis de Ceuta", "IA en 2026"
    descripcion: str = ""
    tema: str = ""    # keyword para búsqueda automática


class ThreadUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tema: Optional[str] = None


class EpisodioAdd(BaseModel):
    item_id: str
    titulo: str
    youtube_url: str = ""


@router.get("/api/threads")
def list_threads():
    with _lock:
        return _load()


@router.post("/api/threads")
def create_thread(req: ThreadCreate):
    hilo = {
        "id": uuid.uuid4().hex[:8],
        "nombre": req.nombre,
        "descripcion": req.descripcion,
        "tema": req.tema,
        "episodios": [],
        "creado": datetime.now().isoformat(),
        "actualizado": datetime.now().isoformat(),
    }
    with _lock:
        data = _load()
        data.insert(0, hilo)
        _save(data)
    return hilo


@router.patch("/api/threads/{hilo_id}")
def update_thread(hilo_id: str, req: ThreadUpdate):
    with _lock:
        data = _load()
        hilo = next((h for h in data if h["id"] == hilo_id), None)
        if not hilo:
            raise HTTPException(404, "Hilo no encontrado")
        if req.nombre is not None:
            hilo["nombre"] = req.nombre
        if req.descripcion is not None:
            hilo["descripcion"] = req.descripcion
        if req.tema is not None:
            hilo["tema"] = req.tema
        hilo["actualizado"] = datetime.now().isoformat()
        _save(data)
    return hilo


@router.delete("/api/threads/{hilo_id}")
def delete_thread(hilo_id: str):
    with _lock:
        data = _load()
        data = [h for h in data if h["id"] != hilo_id]
        _save(data)
    return {"ok": True}


@router.post("/api/threads/{hilo_id}/episodios")
def add_episodio(hilo_id: str, req: EpisodioAdd):
    with _lock:
        data = _load()
        hilo = next((h for h in data if h["id"] == hilo_id), None)
        if not hilo:
            raise HTTPException(404, "Hilo no encontrado")
        # Evitar duplicados por item_id
        if any(e["item_id"] == req.item_id for e in hilo["episodios"]):
            return hilo
        hilo["episodios"].append({
            "item_id": req.item_id,
            "titulo": req.titulo,
            "youtube_url": req.youtube_url,
            "fecha": datetime.now().isoformat(),
            "numero": len(hilo["episodios"]) + 1,
        })
        hilo["actualizado"] = datetime.now().isoformat()
        _save(data)
    return hilo


@router.delete("/api/threads/{hilo_id}/episodios/{item_id}")
def remove_episodio(hilo_id: str, item_id: str):
    with _lock:
        data = _load()
        hilo = next((h for h in data if h["id"] == hilo_id), None)
        if not hilo:
            raise HTTPException(404, "Hilo no encontrado")
        hilo["episodios"] = [e for e in hilo["episodios"] if e["item_id"] != item_id]
        # Renumerar
        for i, ep in enumerate(hilo["episodios"]):
            ep["numero"] = i + 1
        hilo["actualizado"] = datetime.now().isoformat()
        _save(data)
    return hilo


@router.get("/api/threads/{hilo_id}/contexto")
def get_contexto(hilo_id: str):
    """Devuelve el contexto del hilo para pasar al generador de guion."""
    with _lock:
        data = _load()
        hilo = next((h for h in data if h["id"] == hilo_id), None)
    if not hilo:
        raise HTTPException(404, "Hilo no encontrado")
    episodios = hilo.get("episodios", [])
    prev = [e for e in episodios if e.get("youtube_url")]
    return {
        "nombre": hilo["nombre"],
        "tema": hilo.get("tema", ""),
        "episodios_totales": len(episodios),
        "episodio_siguiente": len(episodios) + 1,
        "episodios_publicados": [
            {"numero": e["numero"], "titulo": e["titulo"], "youtube_url": e["youtube_url"]}
            for e in prev
        ],
    }
