"""
accounts_manager.py
Gestiona tokens OAuth para YouTube, TikTok e Instagram.
Los tokens se guardan en _tokens/{platform}.json.
"""
import json
from datetime import datetime
from pathlib import Path

TOKENS_DIR = Path(__file__).parent / "_tokens"
TOKENS_DIR.mkdir(exist_ok=True)


def _token_path(platform: str) -> Path:
    return TOKENS_DIR / f"{platform}.json"


def save_token(platform: str, data: dict) -> None:
    _token_path(platform).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_token(platform: str) -> dict | None:
    p = _token_path(platform)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_token(platform: str) -> None:
    p = _token_path(platform)
    if p.exists():
        p.unlink()


def is_connected(platform: str) -> bool:
    token = load_token(platform)
    if not token:
        return False
    expires_at = token.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                return False
        except Exception:
            pass
    return True


def get_account_info(platform: str) -> dict:
    token = load_token(platform)
    if not token:
        return {"connected": False}

    connected = is_connected(platform)

    if platform == "youtube":
        return {
            "connected": connected,
            "canal": token.get("canal", "Canal conectado"),
            "channel_id": token.get("channel_id"),
        }
    elif platform == "tiktok":
        return {
            "connected": connected,
            "display_name": token.get("display_name", "Usuario TikTok"),
            "avatar_url": token.get("avatar_url"),
        }
    elif platform == "instagram":
        return {
            "connected": connected,
            "username": token.get("username", "usuario"),
        }
    return {"connected": False}
