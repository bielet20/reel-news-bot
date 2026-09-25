"""
api/distribucion.py
Endpoints para configurar la distribución automática a Telegram grupos y Reddit.
"""
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from distribuidor import load_config, save_config

router = APIRouter()


class TelegramGrupo(BaseModel):
    chat_id: str
    nombre: str = ""


class DistribucionConfig(BaseModel):
    telegram_grupos:         Optional[List[dict]] = None
    telegram_grupos_enabled: Optional[bool]       = None
    reddit_subreddits:       Optional[List[str]]  = None
    reddit_enabled:          Optional[bool]       = None
    delay_entre_posts:       Optional[int]        = None


@router.get("/api/distribucion/config")
def get_config():
    return load_config()


@router.post("/api/distribucion/config")
def update_config(req: DistribucionConfig):
    data = load_config()
    if req.telegram_grupos is not None:
        data["telegram_grupos"] = req.telegram_grupos
    if req.telegram_grupos_enabled is not None:
        data["telegram_grupos_enabled"] = req.telegram_grupos_enabled
    if req.reddit_subreddits is not None:
        data["reddit_subreddits"] = [s.lstrip("r/").strip() for s in req.reddit_subreddits if s.strip()]
    if req.reddit_enabled is not None:
        data["reddit_enabled"] = req.reddit_enabled
    if req.delay_entre_posts is not None:
        data["delay_entre_posts"] = max(5, req.delay_entre_posts)
    save_config(data)
    return data


@router.post("/api/distribucion/test/telegram")
def test_telegram(req: TelegramGrupo):
    """Envía mensaje de prueba a un grupo para verificar que el bot tiene acceso."""
    try:
        from telegram_uploader import enviar_mensaje
        enviar_mensaje(
            "✅ <b>Bot de noticias conectado</b>\nEste grupo recibirá los videos automáticamente al publicarse en YouTube.",
            chat_id=req.chat_id,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
