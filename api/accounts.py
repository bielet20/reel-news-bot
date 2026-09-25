"""
api/accounts.py
Gestión OAuth de cuentas: YouTube, TikTok, Instagram, Telegram, WhatsApp.
"""
import base64
import hashlib
import os
import sys
import secrets
import urllib.parse
import requests as http
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from accounts_manager import save_token, load_token, delete_token, get_account_info

router = APIRouter()

FRONTEND = "http://localhost:3000"
BACKEND_CB = "http://localhost:8000"

# CSRF state store (in-memory, sufficient for single-instance dev server)
_oauth_state: dict[str, str] = {}
# PKCE code_verifier store (keyed by OAuth state, only used for TikTok)
_pkce_verifiers: dict[str, str] = {}


def _pkce_verifier() -> str:
    """Genera un code_verifier aleatorio para PKCE (RFC 7636, 43-128 chars URL-safe)."""
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    """Calcula code_challenge = BASE64URL(SHA256(verifier)) sin padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


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

    # WhatsApp: consulta el sidecar Node.js
    try:
        from whatsapp_uploader import get_status as wa_get_status
        wa_status = wa_get_status()
        whatsapp = {
            "connected": wa_status.get("connected", False),
            "ready": wa_status.get("ready", False),
        }
    except Exception:
        whatsapp = {"connected": False, "ready": False}

    # X (Twitter)
    x_token = load_token("x")
    if x_token:
        x_status = {"connected": True, "username": x_token.get("username", "usuario")}
    else:
        has_x_env = bool(
            os.environ.get("X_API_KEY") and os.environ.get("X_API_SECRET") and
            os.environ.get("X_ACCESS_TOKEN") and os.environ.get("X_ACCESS_SECRET")
        )
        if has_x_env:
            try:
                from x_uploader import verificar_credenciales as x_verify
                x_status = x_verify()
            except Exception:
                x_status = {"connected": False}
        else:
            x_status = {"connected": False}

    # TikTok: cookies-based connection takes priority over OAuth token
    tiktok = _tiktok_status()

    # Facebook Page
    fb_token = load_token("facebook")
    if fb_token and fb_token.get("page_id") and fb_token.get("page_access_token"):
        facebook = {"connected": True, "page_name": fb_token.get("page_name", "Página conectada"), "page_id": fb_token.get("page_id", "")}
    else:
        fb_env = bool(os.environ.get("FB_PAGE_ID") and os.environ.get("FB_PAGE_ACCESS_TOKEN"))
        if fb_env:
            try:
                from facebook_uploader import verificar_credenciales as fb_verify
                facebook = fb_verify()
            except Exception:
                facebook = {"connected": False}
        else:
            facebook = {"connected": False}

    # WhatsApp Canal
    wa_canal_token = load_token("whatsapp_canal")
    if wa_canal_token and wa_canal_token.get("channel_jid"):
        wa_canal = {"connected": True, "channel_jid": wa_canal_token["channel_jid"], "channel_name": wa_canal_token.get("channel_name", "")}
    else:
        wa_canal_jid = os.environ.get("WA_CHANNEL_JID", "")
        wa_canal = {"connected": bool(wa_canal_jid), "channel_jid": wa_canal_jid}

    # Instagram: token OAuth propio o la cuenta vinculada a la página de Facebook
    instagram = get_account_info("instagram")
    if not instagram.get("connected") and facebook.get("connected"):
        try:
            from instagram_uploader import verificar_credenciales as ig_verify
            ig = ig_verify()
            if ig.get("ok"):
                instagram = {"connected": True, "username": ig.get("username", "usuario")}
        except Exception:
            pass

    return {
        "youtube":        youtube,
        "tiktok":         tiktok,
        "instagram":      instagram,
        "telegram":       get_account_info("telegram"),
        "whatsapp":       whatsapp,
        "x":              x_status,
        "facebook":       facebook,
        "whatsapp_canal": wa_canal,
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

    expires_in = tokens.get("expires_in", 3600)
    save_token("youtube", {
        "refresh_token": refresh_token,
        "access_token": tokens.get("access_token"),
        "expires_at": (datetime.now() + timedelta(seconds=expires_in - 60)).isoformat(),
        "client_id": client_id,
        "client_secret": client_secret,
        "canal": canal,
        "channel_id": channel_id,
    })
    from youtube_uploader import invalidate_service_cache
    invalidate_service_cache()
    return RedirectResponse(f"{FRONTEND}/canales?youtube=ok")


def _tiktok_status() -> dict:
    """TikTok connection status: cookies file > OAuth token."""
    cookies_path = Path(__file__).parent.parent / "_config" / "tiktok_cookies.json"
    if cookies_path.exists():
        try:
            import json as _json
            cookies = _json.loads(cookies_path.read_text("utf-8"))
            if cookies:
                return {"connected": True, "display_name": "TikTok (browser)", "method": "cookies"}
        except Exception:
            pass
    return get_account_info("tiktok")


# ── TikTok OAuth ─────────────────────────────────────────────────────────────

TIKTOK_SCOPES = "user.info.basic,video.publish,video.upload"
# video.publish = publicación directa (requiere acceso producción)
# video.upload  = sube como borrador (disponible en sandbox)


@router.get("/api/accounts/tiktok/connect-browser")
def tiktok_connect_browser():
    """Estado de conexión via cookies (método sin OAuth)."""
    cookies_path = Path(__file__).parent.parent / "_config" / "tiktok_cookies.json"
    if cookies_path.exists():
        try:
            import json as _json
            cookies = _json.loads(cookies_path.read_text("utf-8"))
            if cookies:
                return {"connected": True, "message": "Cookies de TikTok encontradas. Ya puedes publicar."}
        except Exception:
            pass
    return {
        "connected": False,
        "message": (
            "Para conectar TikTok sin OAuth, ejecuta en el host (fuera de Docker): "
            "python3 scripts/tiktok_login.py"
        ),
    }


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

    verifier = _pkce_verifier()
    _pkce_verifiers[state] = verifier

    params = {
        "client_key": client_key,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/tiktok/callback",
        "response_type": "code",
        "scope": TIKTOK_SCOPES,
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    return {"auth_url": "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params)}


@router.get("/api/accounts/tiktok/callback")
def tiktok_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse(f"{FRONTEND}/canales?error=tiktok_{error}")
    if not code or not state or _oauth_state.get(state) != "tiktok":
        return RedirectResponse(f"{FRONTEND}/canales?error=tiktok_state_invalid")
    _oauth_state.pop(state, None)
    code_verifier = _pkce_verifiers.pop(state, "")

    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")

    token_data: dict = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": f"{BACKEND_CB}/api/accounts/tiktok/callback",
    }
    if code_verifier:
        token_data["code_verifier"] = code_verifier

    resp = http.post("https://open.tiktok.com/v2/oauth/token/", data=token_data)

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


# ── Telegram ─────────────────────────────────────────────────────────────────

class TelegramConnectRequest(BaseModel):
    bot_token: str
    chat_id: str


@router.post("/api/accounts/telegram/connect")
def telegram_connect(req: TelegramConnectRequest):
    """Guarda el bot token y chat_id de Telegram."""
    if not req.bot_token or not req.chat_id:
        raise HTTPException(status_code=400, detail={
            "error": "missing_credentials",
            "message": "bot_token y chat_id son requeridos",
        })

    # Verificar que el token es válido consultando getMe
    try:
        test = http.get(
            f"https://api.telegram.org/bot{req.bot_token}/getMe",
            timeout=10,
        )
        data = test.json()
        if not data.get("ok"):
            raise HTTPException(status_code=400, detail={
                "error": "invalid_token",
                "message": f"Token inválido: {data.get('description', 'error desconocido')}",
            })
        bot_username = data["result"].get("username", "bot")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "error": "connection_error",
            "message": f"No se pudo verificar el token: {e}",
        })

    save_token("telegram", {
        "bot_token": req.bot_token,
        "chat_id": req.chat_id,
        "bot_username": bot_username,
    })
    return {"ok": True, "bot_username": bot_username}


@router.delete("/api/accounts/telegram/disconnect")
def telegram_disconnect():
    delete_token("telegram")
    return {"ok": True}


# ── WhatsApp ──────────────────────────────────────────────────────────────────

@router.get("/api/accounts/whatsapp/status")
def whatsapp_status():
    """Estado de conexión del sidecar WhatsApp."""
    try:
        from whatsapp_uploader import get_status as wa_get_status
        return wa_get_status()
    except Exception as e:
        return {"connected": False, "ready": False, "error": str(e)}


@router.get("/api/accounts/whatsapp/qr")
def whatsapp_qr():
    """Devuelve el QR de vinculación como base64."""
    try:
        from whatsapp_uploader import get_qr
        qr = get_qr()
        return {"qr": qr}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── X (Twitter) ───────────────────────────────────────────────────────────────

class XConnectRequest(BaseModel):
    api_key: str
    api_secret: str
    access_token: str
    access_secret: str


@router.post("/api/accounts/x/connect")
def x_connect(req: XConnectRequest):
    """Guarda las credenciales OAuth 1.0a de X."""
    if not all([req.api_key, req.api_secret, req.access_token, req.access_secret]):
        raise HTTPException(status_code=400, detail={
            "error": "missing_credentials",
            "message": "Las 4 credenciales son obligatorias",
        })

    # Verificar antes de guardar
    import os as _os
    _os.environ["X_API_KEY"]       = req.api_key
    _os.environ["X_API_SECRET"]    = req.api_secret
    _os.environ["X_ACCESS_TOKEN"]  = req.access_token
    _os.environ["X_ACCESS_SECRET"] = req.access_secret
    try:
        from x_uploader import verificar_credenciales
        result = verificar_credenciales()
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail={
                "error": "invalid_credentials",
                "message": result.get("motivo", "Credenciales inválidas"),
            })
        username = result.get("username", "usuario")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "error": "connection_error",
            "message": str(e),
        })

    save_token("x", {
        "api_key":      req.api_key,
        "api_secret":   req.api_secret,
        "access_token": req.access_token,
        "access_secret": req.access_secret,
        "username":     username,
    })
    return {"ok": True, "username": username}


@router.delete("/api/accounts/x/disconnect")
def x_disconnect():
    delete_token("x")
    return {"ok": True}


# ── Facebook Page ─────────────────────────────────────────────────────────────

FB_PAGE_SCOPES = "pages_manage_posts,pages_show_list,pages_read_engagement,pages_manage_engagement"


@router.get("/api/accounts/facebook/oauth-connect")
def facebook_oauth_connect():
    app_id = os.environ.get("FB_APP_ID")
    app_secret = os.environ.get("FB_APP_SECRET")
    if not app_id or not app_secret:
        raise HTTPException(status_code=400, detail={
            "error": "missing_credentials",
            "message": "Añade FB_APP_ID y FB_APP_SECRET al archivo .env",
        })
    state = secrets.token_urlsafe(16)
    _oauth_state[state] = "facebook"
    params = {
        "client_id": app_id,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/facebook/callback",
        "response_type": "code",
        "scope": FB_PAGE_SCOPES,
        "state": state,
    }
    return {"auth_url": "https://www.facebook.com/v22.0/dialog/oauth?" + urllib.parse.urlencode(params)}


@router.get("/api/accounts/facebook/callback")
def facebook_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse(f"{FRONTEND}/canales?error=facebook_{error}")
    if not code or not state or _oauth_state.get(state) != "facebook":
        return RedirectResponse(f"{FRONTEND}/canales?error=facebook_state_invalid")
    _oauth_state.pop(state, None)

    app_id = os.environ.get("FB_APP_ID")
    app_secret = os.environ.get("FB_APP_SECRET")
    cb_url = f"{BACKEND_CB}/api/accounts/facebook/callback"

    # Exchange code for short-lived user access token
    token_resp = http.get("https://graph.facebook.com/v22.0/oauth/access_token", params={
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": cb_url,
        "code": code,
    })
    if not token_resp.ok:
        return RedirectResponse(f"{FRONTEND}/canales?error=facebook_token_failed")
    short_token = token_resp.json().get("access_token")
    if not short_token:
        return RedirectResponse(f"{FRONTEND}/canales?error=facebook_no_token")

    # Exchange for long-lived token (~60 days)
    long_resp = http.get("https://graph.facebook.com/v22.0/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })
    long_token = short_token
    if long_resp.ok:
        long_token = long_resp.json().get("access_token", short_token)

    # Get Page Access Token for all managed pages
    pages_resp = http.get("https://graph.facebook.com/v22.0/me/accounts", params={
        "access_token": long_token,
        "fields": "id,name,access_token",
    })
    if not pages_resp.ok:
        return RedirectResponse(f"{FRONTEND}/canales?error=facebook_pages_failed")

    pages = pages_resp.json().get("data", [])
    if not pages:
        return RedirectResponse(f"{FRONTEND}/canales?error=facebook_no_pages")

    # Use the first page, or match by env FB_PAGE_ID if set
    preferred_page_id = os.environ.get("FB_PAGE_ID", "")
    page = next((p for p in pages if p["id"] == preferred_page_id), pages[0])

    page_id = page["id"]
    page_access_token = page["access_token"]
    page_name = page.get("name", "Página Facebook")

    save_token("facebook", {
        "page_id": page_id,
        "page_access_token": page_access_token,
        "page_name": page_name,
    })
    return RedirectResponse(f"{FRONTEND}/canales?facebook=ok")


class FacebookConnectRequest(BaseModel):
    page_id: str
    page_access_token: str


@router.post("/api/accounts/facebook/connect")
def facebook_connect(req: FacebookConnectRequest):
    """Guarda las credenciales de la Página de Facebook y las verifica."""
    if not req.page_id or not req.page_access_token:
        raise HTTPException(status_code=400, detail={"error": "missing_credentials", "message": "Page ID y Access Token son obligatorios"})

    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent.parent))
        import os as _os
        _os.environ["FB_PAGE_ID"] = req.page_id
        _os.environ["FB_PAGE_ACCESS_TOKEN"] = req.page_access_token
        from facebook_uploader import verificar_credenciales as fb_verify
        result = fb_verify()
        if not result.get("connected"):
            raise HTTPException(status_code=400, detail={"error": "invalid_credentials", "message": result.get("error", "Token inválido")})
        page_name = result.get("page_name", "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "connection_error", "message": str(e)})

    save_token("facebook", {
        "page_id": req.page_id,
        "page_access_token": req.page_access_token,
        "page_name": page_name,
    })
    return {"ok": True, "page_name": page_name}


# ── WhatsApp Canal ─────────────────────────────────────────────────────────────

class WaCanelConnectRequest(BaseModel):
    channel_jid: str
    channel_name: str = ""


@router.post("/api/accounts/whatsapp-canal/connect")
def whatsapp_canal_connect(req: WaCanelConnectRequest):
    """Guarda el JID del canal de WhatsApp."""
    if not req.channel_jid or not req.channel_jid.endswith("@newsletter"):
        raise HTTPException(status_code=400, detail={"error": "invalid_jid", "message": "El JID debe terminar en @newsletter"})
    save_token("whatsapp_canal", {"channel_jid": req.channel_jid, "channel_name": req.channel_name})
    return {"ok": True}


@router.get("/api/accounts/whatsapp-canal/channels")
def whatsapp_canal_list():
    """Lista los canales de WhatsApp del usuario conectado (requiere sidecar activo)."""
    try:
        from whatsapp_uploader import get_channels
        return get_channels()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


class WaFindByUrlRequest(BaseModel):
    url: str


@router.post("/api/accounts/whatsapp-canal/find-by-url")
def whatsapp_canal_find_by_url(req: WaFindByUrlRequest):
    """Busca un canal por su URL de invitación (whatsapp.com/channel/...)."""
    try:
        from whatsapp_uploader import find_channel_by_url
        return find_channel_by_url(req.url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── Disconnect ────────────────────────────────────────────────────────────────

@router.delete("/api/accounts/{platform}")
def disconnect(platform: str):
    if platform not in ("youtube", "tiktok", "instagram", "telegram", "facebook", "whatsapp_canal"):
        raise HTTPException(status_code=400, detail="Plataforma desconocida")
    delete_token(platform)
    if platform == "tiktok":
        cookies_path = Path(__file__).parent.parent / "_config" / "tiktok_cookies.json"
        cookies_path.unlink(missing_ok=True)
    return {"ok": True}
