"""
api/accounts.py
Gestión OAuth de cuentas: YouTube, TikTok, Instagram.
"""
import os
import sys
import secrets
import urllib.parse
import requests as http
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from accounts_manager import save_token, load_token, delete_token, get_account_info

router = APIRouter()

FRONTEND = "http://localhost:3000"
BACKEND_CB = "http://localhost:8000"

# CSRF state store (in-memory, sufficient for single-instance dev server)
_oauth_state: dict[str, str] = {}


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/api/accounts/status")
def accounts_status():
    """Estado de conexión de las tres plataformas."""
    # YouTube: prefer _tokens file, fall back to .env
    yt_token = load_token("youtube")
    if yt_token:
        youtube = {"connected": True, "canal": yt_token.get("canal", "Canal conectado")}
    else:
        has_env = bool(
            os.environ.get("YOUTUBE_CLIENT_ID") and
            os.environ.get("YOUTUBE_CLIENT_SECRET") and
            os.environ.get("YOUTUBE_REFRESH_TOKEN")
        )
        if has_env:
            try:
                from youtube_uploader import verificar_credenciales
                yt = verificar_credenciales()
                youtube = yt
            except Exception:
                youtube = {"connected": False}
        else:
            youtube = {"connected": False}

    return {
        "youtube":   youtube,
        "tiktok":    get_account_info("tiktok"),
        "instagram": get_account_info("instagram"),
    }


# ── YouTube OAuth ────────────────────────────────────────────────────────────

YT_SCOPES = " ".join([
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
])


@router.get("/api/accounts/youtube/connect")
def youtube_connect():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail={
            "error": "missing_credentials",
            "message": "Añade YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET al archivo .env",
        })

    state = secrets.token_urlsafe(16)
    _oauth_state[state] = "youtube"

    params = {
        "client_id": client_id,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/youtube/callback",
        "response_type": "code",
        "scope": YT_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return {"auth_url": "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)}


@router.get("/api/accounts/youtube/callback")
def youtube_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse(f"{FRONTEND}/canales?error=youtube_{error}")
    if not code or not state or _oauth_state.get(state) != "youtube":
        return RedirectResponse(f"{FRONTEND}/canales?error=youtube_state_invalid")
    _oauth_state.pop(state, None)

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")

    resp = http.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/youtube/callback",
        "grant_type": "authorization_code",
    })

    if not resp.ok:
        return RedirectResponse(f"{FRONTEND}/canales?error=youtube_token_failed")

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return RedirectResponse(f"{FRONTEND}/canales?error=youtube_no_refresh")

    # Get channel info
    canal = "Canal conectado"
    channel_id = None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        service = build("youtube", "v3", credentials=creds)
        ch = service.channels().list(part="snippet", mine=True).execute()
        if ch.get("items"):
            canal = ch["items"][0]["snippet"]["title"]
            channel_id = ch["items"][0]["id"]
    except Exception:
        pass

    save_token("youtube", {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "canal": canal,
        "channel_id": channel_id,
    })
    return RedirectResponse(f"{FRONTEND}/canales?youtube=ok")


# ── TikTok OAuth ─────────────────────────────────────────────────────────────

TIKTOK_SCOPES = "user.info.basic,video.publish,video.upload"


@router.get("/api/accounts/tiktok/connect")
def tiktok_connect():
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    if not client_key:
        raise HTTPException(status_code=400, detail={
            "error": "missing_credentials",
            "message": "Añade TIKTOK_CLIENT_KEY y TIKTOK_CLIENT_SECRET al archivo .env",
        })

    state = secrets.token_urlsafe(16)
    _oauth_state[state] = "tiktok"

    params = {
        "client_key": client_key,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/tiktok/callback",
        "response_type": "code",
        "scope": TIKTOK_SCOPES,
        "state": state,
    }
    return {"auth_url": "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params)}


@router.get("/api/accounts/tiktok/callback")
def tiktok_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse(f"{FRONTEND}/canales?error=tiktok_{error}")
    if not code or not state or _oauth_state.get(state) != "tiktok":
        return RedirectResponse(f"{FRONTEND}/canales?error=tiktok_state_invalid")
    _oauth_state.pop(state, None)

    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")

    resp = http.post("https://open.tiktok.com/v2/oauth/token/", data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": f"{BACKEND_CB}/api/accounts/tiktok/callback",
    })

    if not resp.ok:
        return RedirectResponse(f"{FRONTEND}/canales?error=tiktok_token_failed")

    data = resp.json().get("data", {})
    if data.get("error_code", 0) != 0:
        return RedirectResponse(f"{FRONTEND}/canales?error=tiktok_auth_denied")

    access_token = data.get("access_token", "")
    now = datetime.now()

    # Get user display name
    display_name = "Usuario TikTok"
    avatar_url = None
    try:
        user_resp = http.get(
            "https://open.tiktok.com/v2/user/info/",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "open_id,display_name,avatar_url"},
        )
        if user_resp.ok:
            u = user_resp.json().get("data", {}).get("user", {})
            display_name = u.get("display_name", display_name)
            avatar_url = u.get("avatar_url")
    except Exception:
        pass

    save_token("tiktok", {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token", ""),
        "open_id": data.get("open_id", ""),
        "expires_at": (now + timedelta(seconds=data.get("expires_in", 86400))).isoformat(),
        "refresh_expires_at": (now + timedelta(seconds=data.get("refresh_expires_in", 31536000))).isoformat(),
        "display_name": display_name,
        "avatar_url": avatar_url,
        "client_key": client_key,
        "client_secret": client_secret,
    })
    return RedirectResponse(f"{FRONTEND}/canales?tiktok=ok")


# ── Instagram OAuth ───────────────────────────────────────────────────────────

IG_SCOPES = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement"


@router.get("/api/accounts/instagram/connect")
def instagram_connect():
    app_id = os.environ.get("INSTAGRAM_APP_ID")
    if not app_id:
        raise HTTPException(status_code=400, detail={
            "error": "missing_credentials",
            "message": "Añade INSTAGRAM_APP_ID e INSTAGRAM_APP_SECRET al archivo .env",
        })

    state = secrets.token_urlsafe(16)
    _oauth_state[state] = "instagram"

    params = {
        "client_id": app_id,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/instagram/callback",
        "response_type": "code",
        "scope": IG_SCOPES,
        "state": state,
    }
    return {"auth_url": "https://www.facebook.com/v22.0/dialog/oauth?" + urllib.parse.urlencode(params)}


@router.get("/api/accounts/instagram/callback")
def instagram_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse(f"{FRONTEND}/canales?error=instagram_{error}")
    if not code or not state or _oauth_state.get(state) != "instagram":
        return RedirectResponse(f"{FRONTEND}/canales?error=instagram_state_invalid")
    _oauth_state.pop(state, None)

    app_id = os.environ.get("INSTAGRAM_APP_ID")
    app_secret = os.environ.get("INSTAGRAM_APP_SECRET")
    cb_url = f"{BACKEND_CB}/api/accounts/instagram/callback"

    # Exchange code for short-lived user access token
    token_resp = http.get("https://graph.facebook.com/v22.0/oauth/access_token", params={
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": cb_url,
        "code": code,
    })

    if not token_resp.ok:
        return RedirectResponse(f"{FRONTEND}/canales?error=instagram_token_failed")

    short_token = token_resp.json().get("access_token")
    if not short_token:
        return RedirectResponse(f"{FRONTEND}/canales?error=instagram_no_token")

    # Exchange for long-lived token (~60 days)
    long_resp = http.get("https://graph.facebook.com/v22.0/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })

    access_token = short_token
    expires_in = 5184000  # 60 days default
    if long_resp.ok:
        ld = long_resp.json()
        access_token = ld.get("access_token", short_token)
        expires_in = ld.get("expires_in", 5184000)

    # Get Instagram Business Account linked to user's pages
    ig_user_id = None
    username = "usuario"

    try:
        pages_resp = http.get("https://graph.facebook.com/v22.0/me/accounts", params={
            "access_token": access_token,
        })
        if pages_resp.ok:
            pages = pages_resp.json().get("data", [])
            for page in pages:
                page_id = page.get("id")
                page_token = page.get("access_token", access_token)
                ig_resp = http.get(f"https://graph.facebook.com/v22.0/{page_id}", params={
                    "fields": "instagram_business_account",
                    "access_token": page_token,
                })
                if ig_resp.ok:
                    ig_data = ig_resp.json().get("instagram_business_account")
                    if ig_data:
                        ig_user_id = ig_data.get("id")
                        # Get username
                        me_resp = http.get(f"https://graph.facebook.com/v22.0/{ig_user_id}", params={
                            "fields": "username",
                            "access_token": page_token,
                        })
                        if me_resp.ok:
                            username = me_resp.json().get("username", username)
                        # Use page access token for publishing
                        access_token = page_token
                        break
    except Exception:
        pass

    if not ig_user_id:
        return RedirectResponse(f"{FRONTEND}/canales?error=instagram_no_business_account")

    now = datetime.now()
    save_token("instagram", {
        "access_token": access_token,
        "ig_user_id": str(ig_user_id),
        "username": username,
        "expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
        "app_id": app_id,
        "app_secret": app_secret,
    })
    return RedirectResponse(f"{FRONTEND}/canales?instagram=ok")


# ── Disconnect ────────────────────────────────────────────────────────────────

@router.delete("/api/accounts/{platform}")
def disconnect(platform: str):
    if platform not in ("youtube", "tiktok", "instagram"):
        raise HTTPException(status_code=400, detail="Plataforma desconocida")
    delete_token(platform)
    return {"ok": True}
