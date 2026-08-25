"""
api/storage.py
Endpoints para gestionar los destinos de almacenamiento de videos generados.
"""
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from storage_manager import load_config, save_config

router = APIRouter()


class StorageConfig(BaseModel):
    destinations: list[dict]


@router.get("/api/storage/config")
def get_storage_config():
    return load_config()


@router.post("/api/storage/config")
def set_storage_config(cfg: StorageConfig):
    save_config(cfg.dict())
    return {"ok": True}
