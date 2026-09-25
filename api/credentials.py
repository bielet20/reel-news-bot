"""
api/credentials.py
CRUD de credenciales por plataforma (Client IDs, Secrets, Tokens).
Inyecta automáticamente en os.environ al arrancar para que los flujos OAuth las encuentren.
"""
import json
import os
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

from api.admin import verify_admin_password

router = APIRouter()

CONFIG_DIR = Path(__file__).parent.parent / "_config"
TOKENS_DIR = Path(__file__).parent.parent / "_tokens"
CREDS_FILE  = CONFIG_DIR / "credentials.json"

FIELDS: dict[str, list[dict]] = {
    "youtube": [
        {"key": "client_id",     "label": "Client ID",     "secret": False},
        {"key": "client_secret", "label": "Client Secret", "secret": True},
    ],
    "tiktok": [
        {"key": "client_key",    "label": "Client Key",    "secret": False},
        {"key": "client_secret", "label": "Client Secret", "secret": True},
        {"key": "service_url",     "label": "URL del servicio (api.bieninforma2.site)", "secret": False},
        {"key": "service_api_key", "label": "API Key del servicio (PUBLISH_API_KEY)",   "secret": True},
    ],
    "instagram": [
        {"key": "app_id",        "label": "App ID",        "secret": False},
        {"key": "app_secret",    "label": "App Secret",    "secret": True},
    ],
    "telegram": [
        {"key": "bot_token",     "label": "Bot Token",     "secret": True},
        {"key": "chat_id",       "label": "Chat ID",       "secret": False},
    ],
    "x": [
        {"key": "api_key",       "label": "API Key",       "secret": False},
        {"key": "api_secret",    "label": "API Secret",    "secret": True},
        {"key": "access_token",  "label": "Access Token",  "secret": False},
        {"key": "access_secret", "label": "Access Secret", "secret": True},
    ],
    "facebook": [
        {"key": "page_id",           "label": "Page ID",           "secret": False},
        {"key": "page_access_token", "label": "Page Access Token", "secret": True},
    ],
    "whatsapp_canal": [
        {"key": "channel_jid", "label": "Channel JID (@newsletter)", "secret": False},
    ],
}

# Plataformas cuyas credenciales viven en _tokens/{platform}.json (no en credentials.json)
_TOKEN_PLATFORMS = {"telegram", "x", "facebook", "whatsapp_canal"}

# Mapa de campos a variables de entorno para inyección en startup
ENV_MAP: dict[str, dict[str, str]] = {
    "youtube":   {"client_id": "YOUTUBE_CLIENT_ID", "client_secret": "YOUTUBE_CLIENT_SECRET"},
    "tiktok":    {"client_key": "TIKTOK_CLIENT_KEY", "client_secret": "TIKTOK_CLIENT_SECRET",
                  "service_url": "TIKTOK_API_URL", "service_api_key": "TIKTOK_API_KEY"},
    "instagram": {"app_id": "INSTAGRAM_APP_ID", "app_secret": "INSTAGRAM_APP_SECRET"},
}


def _load_creds() -> dict:
    if CREDS_FILE.exists():
        try:
            return json.loads(CREDS_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save_creds(data: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    CREDS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def _load_platform(platform: str) -> dict:
    if platform in _TOKEN_PLATFORMS:
        p = TOKENS_DIR / f"{platform}.json"
        if p.exists():
            try:
                return json.loads(p.read_text("utf-8"))
            except Exception:
                pass
        return {}
    return _load_creds().get(platform, {})


def _mask(v: str) -> str:
    if not v:
        return ""
    return "••••" + v[-4:] if len(v) > 4 else "••••"


def inject_to_env():
    """Inyecta credenciales guardadas en os.environ (ejecutado al importar el módulo)."""
    data = _load_creds()
    for platform, field_map in ENV_MAP.items():
        for field_key, env_key in field_map.items():
            val = data.get(platform, {}).get(field_key, "")
            if val and not os.environ.get(env_key):
                os.environ[env_key] = val


inject_to_env()


class SaveReq(BaseModel):
    credentials: dict


class RevealReq(BaseModel):
    password: str


@router.get("/api/credentials")
def list_credentials():
    result = {}
    for platform, fields in FIELDS.items():
        stored = _load_platform(platform)
        result[platform] = {
            f["key"]: {
                "label":     f["label"],
                "secret":    f["secret"],
                "has_value": bool(stored.get(f["key"], "")),
                "masked":    _mask(stored[f["key"]]) if f["secret"] and stored.get(f["key"]) else stored.get(f["key"], ""),
            }
            for f in fields
        }
    return result


@router.put("/api/credentials/{platform}")
def save_credentials(platform: str, req: SaveReq):
    if platform not in FIELDS:
        return {"ok": False, "error": "Plataforma desconocida"}

    creds = {k: v for k, v in req.credentials.items() if v}

    if platform in _TOKEN_PLATFORMS:
        TOKENS_DIR.mkdir(exist_ok=True)
        p = TOKENS_DIR / f"{platform}.json"
        existing: dict = {}
        if p.exists():
            try:
                existing = json.loads(p.read_text("utf-8"))
            except Exception:
                pass
        existing.update(creds)
        p.write_text(json.dumps(existing, indent=2, ensure_ascii=False), "utf-8")
    else:
        all_creds = _load_creds()
        existing = all_creds.get(platform, {})
        existing.update(creds)
        all_creds[platform] = existing
        _save_creds(all_creds)
        if platform in ENV_MAP:
            for field_key, env_key in ENV_MAP[platform].items():
                if existing.get(field_key):
                    os.environ[env_key] = existing[field_key]

    return {"ok": True}


@router.post("/api/credentials/{platform}/reveal")
def reveal_credentials(platform: str, req: RevealReq):
    if platform not in FIELDS:
        return {"ok": False, "error": "Plataforma desconocida"}
    if not verify_admin_password(req.password):
        return {"ok": False, "error": "Contraseña incorrecta"}
    stored = _load_platform(platform)
    return {
        "ok":          True,
        "credentials": {f["key"]: stored.get(f["key"], "") for f in FIELDS[platform]},
    }
