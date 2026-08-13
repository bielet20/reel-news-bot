"""
tiktok_uploader.py
Sube videos a TikTok via Content Posting API v2.

Credenciales requeridas en .env:
  TIKTOK_CLIENT_KEY
  TIKTOK_CLIENT_SECRET

El access token se obtiene via OAuth en /canales.
"""
import os
import math
import requests
from pathlib import Path
from datetime import datetime, timedelta

from accounts_manager import load_token, save_token

CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB


def _get_valid_token() -> dict:
    token = load_token("tiktok")
    if not token:
        raise RuntimeError("TikTok no conectado. Ve a Canales para vincular tu cuenta.")

    expires_at = token.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                token = _refresh_token(token)
        except RuntimeError:
            raise
        except Exception:
            pass

    return token


def _refresh_token(token: dict) -> dict:
    client_key = token.get("client_key") or os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = token.get("client_secret") or os.environ.get("TIKTOK_CLIENT_SECRET")
    refresh_token = token.get("refresh_token")

    if not refresh_token:
        raise RuntimeError("No hay refresh token de TikTok. Reconecta la cuenta en Canales.")

    resp = requests.post("https://open.tiktok.com/v2/oauth/token/", data={
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })

    if not resp.ok:
        raise RuntimeError(f"Error al refrescar token TikTok: {resp.text}")

    data = resp.json().get("data", {})
    now = datetime.now()
    token.update({
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
        "expires_at": (now + timedelta(seconds=data.get("expires_in", 86400))).isoformat(),
        "refresh_expires_at": (now + timedelta(seconds=data.get("refresh_expires_in", 31536000))).isoformat(),
    })
    save_token("tiktok", token)
    return token


def subir_video(
    video_path: str,
    titulo: str = "",
    privacy: str = "SELF_ONLY",
) -> dict:
    """
    Sube un video a TikTok via File Upload.

    Args:
        video_path: Ruta al archivo MP4.
        titulo:     Descripción/caption del video.
        privacy:    SELF_ONLY | FOLLOWER_OF_CREATOR | MUTUAL_FOLLOW_FRIENDS | PUBLIC_TO_EVERYONE

    Returns:
        {"ok": True, "publish_id": str}
    """
    token_data = _get_valid_token()
    access_token = token_data["access_token"]

    file_path = Path(video_path)
    file_size = file_path.stat().st_size
    chunk_size = min(CHUNK_SIZE, file_size)
    total_chunks = math.ceil(file_size / chunk_size)

    # Step 1: Initialize upload
    init_resp = requests.post(
        "https://open.tiktok.com/v2/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": (titulo or "")[:150],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        },
    )

    if not init_resp.ok:
        raise RuntimeError(f"Error iniciando upload TikTok: {init_resp.text}")

    init_data = init_resp.json().get("data", {})
    if init_data.get("error_code", 0) != 0:
        raise RuntimeError(f"Error TikTok API: {init_data}")

    publish_id = init_data["publish_id"]
    upload_url = init_data["upload_url"]

    # Step 2: Upload chunks
    with open(file_path, "rb") as f:
        for idx in range(total_chunks):
            chunk = f.read(chunk_size)
            start = idx * chunk_size
            end = start + len(chunk) - 1

            chunk_resp = requests.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                },
                data=chunk,
            )

            if chunk_resp.status_code not in (200, 206):
                raise RuntimeError(
                    f"Error subiendo chunk {idx} a TikTok: {chunk_resp.status_code} {chunk_resp.text}"
                )

    print(f"[TikTok] Video publicado: publish_id={publish_id}")
    return {"ok": True, "publish_id": publish_id}


def verificar_credenciales() -> dict:
    token = load_token("tiktok")
    if not token:
        return {"ok": False, "motivo": "No conectado"}

    expires_at = token.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                return {"ok": False, "motivo": "Token expirado. Reconecta la cuenta."}
        except Exception:
            pass

    return {"ok": True, "display_name": token.get("display_name", "Usuario TikTok")}
