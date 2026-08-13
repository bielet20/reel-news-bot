"""
instagram_uploader.py
Sube Reels a Instagram via Meta Graph API.
Usa Resumable Upload — no requiere URL pública del video.

Credenciales requeridas en .env:
  INSTAGRAM_APP_ID
  INSTAGRAM_APP_SECRET

El access token se obtiene via OAuth en /canales.
"""
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta

from accounts_manager import load_token, save_token

GRAPH_API = "https://graph.facebook.com/v22.0"


def _get_token() -> dict:
    token = load_token("instagram")
    if not token:
        raise RuntimeError("Instagram no conectado. Ve a Canales para vincular tu cuenta.")

    expires_at = token.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if exp < datetime.now():
                raise RuntimeError("Token de Instagram expirado. Reconecta la cuenta en Canales.")
            # Refresh proactively if less than 7 days remain
            if exp < datetime.now() + timedelta(days=7):
                token = _refresh_long_lived_token(token)
        except RuntimeError:
            raise
        except Exception:
            pass

    return token


def _refresh_long_lived_token(token: dict) -> dict:
    resp = requests.get("https://graph.instagram.com/refresh_access_token", params={
        "grant_type": "ig_refresh_token",
        "access_token": token["access_token"],
    })
    if resp.ok:
        data = resp.json()
        token["access_token"] = data.get("access_token", token["access_token"])
        expires_in = data.get("expires_in", 5184000)
        token["expires_at"] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
        save_token("instagram", token)
    return token


def subir_video(video_path: str, caption: str = "") -> dict:
    """
    Sube un Reel a Instagram.

    Args:
        video_path: Ruta al archivo MP4.
        caption:    Texto del post.

    Returns:
        {"ok": True, "media_id": str, "url": str}
    """
    token_data = _get_token()
    access_token = token_data["access_token"]
    ig_user_id = token_data["ig_user_id"]

    file_path = Path(video_path)
    file_size = file_path.stat().st_size

    # Step 1: Create media container (resumable)
    container_resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media",
        params={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": (caption or "")[:2200],
            "share_to_feed": "true",
            "access_token": access_token,
        },
    )

    if not container_resp.ok:
        raise RuntimeError(f"Error creando contenedor Instagram: {container_resp.text}")

    container_data = container_resp.json()
    container_id = container_data.get("id")
    upload_uri = container_data.get("uri")

    if not container_id or not upload_uri:
        raise RuntimeError(f"Respuesta inesperada de Instagram: {container_data}")

    # Step 2: Upload video
    with open(file_path, "rb") as f:
        video_bytes = f.read()

    upload_resp = requests.post(
        upload_uri,
        headers={
            "Authorization": f"OAuth {access_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "video/mp4",
        },
        data=video_bytes,
    )

    if not upload_resp.ok:
        raise RuntimeError(f"Error subiendo video a Instagram: {upload_resp.text}")

    # Step 3: Poll until processing is done
    print("[Instagram] Video subido, esperando procesamiento...")
    for attempt in range(24):  # max 2 minutes
        time.sleep(5)
        status_resp = requests.get(
            f"{GRAPH_API}/{container_id}",
            params={"fields": "status_code,status", "access_token": access_token},
        )
        if not status_resp.ok:
            continue

        status_code = status_resp.json().get("status_code")
        print(f"[Instagram] Estado: {status_code} ({(attempt+1)*5}s)")

        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(
                f"Instagram rechazó el video: {status_resp.json().get('status')}"
            )

    # Step 4: Publish
    publish_resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media_publish",
        params={"creation_id": container_id, "access_token": access_token},
    )

    if not publish_resp.ok:
        raise RuntimeError(f"Error publicando Reel: {publish_resp.text}")

    media_id = publish_resp.json().get("id", "")
    print(f"[Instagram] Reel publicado: media_id={media_id}")

    return {"ok": True, "media_id": media_id}


def verificar_credenciales() -> dict:
    token = load_token("instagram")
    if not token:
        return {"ok": False, "motivo": "No conectado"}

    expires_at = token.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                return {"ok": False, "motivo": "Token expirado. Reconecta la cuenta."}
        except Exception:
            pass

    return {"ok": True, "username": token.get("username", "usuario")}
