"""
instagram_uploader.py
Sube Reels a Instagram via Meta Graph API (2026).

Flujo:
  1. POST /{ig_user_id}/media  → container_id + upload_uri  (resumable)
  2. POST <upload_uri>          → subida chunked del MP4
  3. GET  /{container_id}       → polling status_code hasta FINISHED
  4. POST /{ig_user_id}/media_publish → media_id
  5. GET  /{media_id}           → permalink

Credenciales (en orden):
  1. _tokens/instagram.json (conexión OAuth desde /canales).
  2. El token de PÁGINA de Facebook (FB_PAGE_ID + FB_PAGE_ACCESS_TOKEN, ver
     facebook_uploader): la cuenta profesional de Instagram vinculada a esa
     página se publica con ese mismo token, que no caduca.
"""
import os
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta

from accounts_manager import load_token, save_token

GRAPH_API  = f"https://graph.facebook.com/{os.environ.get('FB_GRAPH_VERSION', 'v23.0')}"
CHUNK_SIZE = 10 * 1024 * 1024   # 10 MB por chunk
POLL_MAX   = 40                  # ~4 minutos máximo
POLL_BASE  = 4                   # segundos base (duplica cada intento fallido)


# ── Token ─────────────────────────────────────────────────────────────────────

def _token_desde_pagina() -> dict | None:
    """Cuenta de Instagram vinculada a la página de Facebook, con el token de la página."""
    try:
        from facebook_uploader import _get_credentials
        page_id, page_token = _get_credentials()
    except Exception:
        return None
    resp = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"fields": "instagram_business_account{id,username}", "access_token": page_token},
        timeout=20,
    )
    ig = resp.json().get("instagram_business_account") if resp.ok else None
    if not ig or not ig.get("id"):
        return None
    return {"access_token": page_token, "ig_user_id": ig["id"], "username": ig.get("username", "")}


def _get_token() -> dict:
    token = load_token("instagram")
    if not token:
        token = _token_desde_pagina()
        if token:
            return token
        raise RuntimeError(
            "Instagram no conectado. Vincula la cuenta profesional de Instagram a la "
            "página de Facebook (o conéctala en Canales)."
        )
    expires_at = token.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if exp < datetime.now():
                raise RuntimeError("Token de Instagram expirado. Reconecta la cuenta en Canales.")
            if exp < datetime.now() + timedelta(days=7):
                token = _refresh_token(token)
        except RuntimeError:
            raise
        except Exception:
            pass
    return token


def _refresh_token(token: dict) -> dict:
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


# ── Paso 1: contenedor ────────────────────────────────────────────────────────

def _crear_contenedor(ig_user_id: str, access_token: str, caption: str, file_size: int,
                      cover_url: str | None = None) -> tuple[str, str]:
    """Devuelve (container_id, upload_uri)."""
    params = {
        "media_type":   "REELS",
        "upload_type":  "resumable",
        "caption":      caption[:2200],
        "share_to_feed": "true",
        "access_token": access_token,
    }
    if cover_url:
        params["cover_url"] = cover_url
    resp = requests.post(f"{GRAPH_API}/{ig_user_id}/media", params=params)
    if not resp.ok:
        raise RuntimeError(f"Error creando contenedor: {resp.status_code} {resp.text}")
    data = resp.json()
    container_id = data.get("id")
    upload_uri   = data.get("uri")
    if not container_id or not upload_uri:
        raise RuntimeError(f"Respuesta inesperada al crear contenedor: {data}")
    return container_id, upload_uri


# ── Paso 2: subida chunked ────────────────────────────────────────────────────

def _subir_chunks(upload_uri: str, access_token: str, file_path: Path) -> None:
    file_size = file_path.stat().st_size
    offset    = 0

    with open(file_path, "rb") as f:
        while offset < file_size:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            for attempt in range(3):
                resp = requests.post(
                    upload_uri,
                    headers={
                        "Authorization": f"OAuth {access_token}",
                        "offset":        str(offset),
                        "file_size":     str(file_size),
                        "Content-Type":  "video/mp4",
                    },
                    data=chunk,
                    timeout=120,
                )
                if resp.ok:
                    break
                if attempt == 2:
                    raise RuntimeError(f"Error subiendo chunk en offset {offset}: {resp.status_code} {resp.text}")
                time.sleep(2 ** attempt)

            offset += len(chunk)
            pct = int(offset / file_size * 100)
            print(f"[Instagram] Upload {pct}% ({offset}/{file_size} bytes)")


# ── Paso 3: polling ───────────────────────────────────────────────────────────

def _esperar_procesamiento(container_id: str, access_token: str) -> None:
    """Bloquea hasta que el contenedor esté FINISHED o lanza RuntimeError."""
    delay = POLL_BASE
    for attempt in range(POLL_MAX):
        time.sleep(delay)
        resp = requests.get(
            f"{GRAPH_API}/{container_id}",
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=30,
        )
        if not resp.ok:
            delay = min(delay * 2, 30)
            continue

        data        = resp.json()
        status_code = data.get("status_code", "")
        print(f"[Instagram] Estado: {status_code} ({(attempt + 1) * delay}s)")

        if status_code == "FINISHED":
            return
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram rechazó el video: {data.get('status', 'error desconocido')}")
        if status_code == "EXPIRED":
            raise RuntimeError("Contenedor de Instagram expirado (>24h sin publicar). Reintenta.")

        # IN_PROGRESS: backoff suave, nunca supera 30s
        delay = min(delay + 2, 30)

    raise RuntimeError("Timeout esperando procesamiento de Instagram (>4 min).")


# ── Paso 4: publicar ──────────────────────────────────────────────────────────

def _publicar(ig_user_id: str, container_id: str, access_token: str) -> str:
    """Devuelve media_id."""
    resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media_publish",
        params={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Error publicando Reel: {resp.status_code} {resp.text}")
    media_id = resp.json().get("id", "")
    if not media_id:
        raise RuntimeError(f"Respuesta inesperada al publicar: {resp.json()}")
    return media_id


# ── Paso 5: permalink ─────────────────────────────────────────────────────────

def _obtener_permalink(media_id: str, access_token: str) -> str:
    resp = requests.get(
        f"{GRAPH_API}/{media_id}",
        params={"fields": "permalink", "access_token": access_token},
        timeout=15,
    )
    if resp.ok:
        return resp.json().get("permalink", "")
    return ""


# ── API pública ───────────────────────────────────────────────────────────────

def subir_video(video_path: str, caption: str = "") -> dict:
    """
    Sube un Reel a Instagram.

    Returns:
        {"ok": True, "media_id": str, "url": str}
    """
    token_data   = _get_token()
    access_token = token_data["access_token"]
    ig_user_id   = token_data["ig_user_id"]
    file_path    = Path(video_path)
    file_size    = file_path.stat().st_size

    print(f"[Instagram] Subiendo {file_path.name} ({file_size // 1024 // 1024} MB)...")

    # Portada: Instagram la pide por URL pública (cover_url). Se aloja un momento
    # como foto no publicada de la página de Facebook y se borra al terminar.
    cover_url, foto_id = None, None
    try:
        from thumbnail_maker import portadas_de
        cover = portadas_de(video_path)["cover"]
        if cover:
            from facebook_uploader import alojar_imagen_temporal
            foto_id, cover_url = alojar_imagen_temporal(cover)
            print("[Instagram] Portada preparada")
    except Exception as e:  # noqa: BLE001
        print(f"[Instagram][WARN] Sin portada personalizada: {e}")

    try:
        container_id, upload_uri = _crear_contenedor(ig_user_id, access_token, caption or "",
                                                     file_size, cover_url)
        print(f"[Instagram] Contenedor creado: {container_id}")

        _subir_chunks(upload_uri, access_token, file_path)
        print("[Instagram] Video subido, esperando procesamiento...")

        _esperar_procesamiento(container_id, access_token)
    finally:
        if foto_id:
            from facebook_uploader import borrar_foto
            borrar_foto(foto_id)

    media_id  = _publicar(ig_user_id, container_id, access_token)
    permalink = _obtener_permalink(media_id, access_token)
    print(f"[Instagram] Reel publicado: {permalink or media_id}")

    return {"ok": True, "media_id": media_id, "url": permalink}


def verificar_credenciales() -> dict:
    token = load_token("instagram")
    if not token:
        token = _token_desde_pagina()
        if token:
            return {"ok": True, "username": token.get("username") or "usuario", "via": "página de Facebook"}
        return {"ok": False, "motivo": "No conectado"}
    expires_at = token.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                return {"ok": False, "motivo": "Token expirado. Reconecta la cuenta."}
        except Exception:
            pass
    return {"ok": True, "username": token.get("username", "usuario")}
