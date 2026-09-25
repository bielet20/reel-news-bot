"""
facebook_uploader.py
Sube vídeos (como Reel si cumple los requisitos) y publica texto en una Página
de Facebook via Graph API.

Credenciales: _tokens/facebook.json (Canales) o .env FB_PAGE_ID +
FB_PAGE_ACCESS_TOKEN (token de PÁGINA sacado de /me/accounts con un token de
usuario de larga duración: así no caduca).
"""
import json
import os
import subprocess
import time
import requests as http
from pathlib import Path

_VERSION = os.environ.get("FB_GRAPH_VERSION", "v23.0")
_GRAPH = f"https://graph.facebook.com/{_VERSION}"
_GRAPH_VIDEO = f"https://graph-video.facebook.com/{_VERSION}"
_RUPLOAD = f"https://rupload.facebook.com/video-upload/{_VERSION}"


def _get_credentials() -> tuple[str, str]:
    """Devuelve (page_id, page_access_token) desde token guardado o .env."""
    try:
        from accounts_manager import load_token
        token_data = load_token("facebook")
        if token_data:
            page_id = token_data.get("page_id", "")
            access_token = token_data.get("page_access_token", "")
            if page_id and access_token:
                return page_id, access_token
    except Exception:
        pass
    page_id = os.environ.get("FB_PAGE_ID", "")
    access_token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
    if not page_id or not access_token:
        raise RuntimeError("Facebook no configurado. Necesitas FB_PAGE_ID y FB_PAGE_ACCESS_TOKEN.")
    return page_id, access_token


def _check(resp: http.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(f"Facebook API: respuesta no JSON ({resp.status_code})")
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"Facebook API: {msg}")
    resp.raise_for_status()
    return data


def _es_reel(video_path: str) -> bool:
    """Reels de página: vertical (alto > ancho) y de 3 a 90 s."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration", "-of", "json", video_path],
            capture_output=True, text=True, timeout=30,
        ).stdout
        info = json.loads(out)
        w = int(info["streams"][0]["width"])
        h = int(info["streams"][0]["height"])
        dur = float(info["format"]["duration"])
    except Exception:
        return False
    return h > w and 3 <= dur <= 90


def subir_reel(video_path: str, descripcion: str = "") -> dict:
    """Publica un Reel en la Página (API video_reels: start → subida → finish)."""
    page_id, access_token = _get_credentials()

    start = _check(http.post(
        f"{_GRAPH}/{page_id}/video_reels",
        json={"upload_phase": "start", "access_token": access_token},
        timeout=30,
    ))
    video_id = start["video_id"]
    upload_url = start.get("upload_url") or f"{_RUPLOAD}/{video_id}"

    size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        up = _check(http.post(
            upload_url,
            headers={"Authorization": f"OAuth {access_token}", "offset": "0", "file_size": str(size)},
            data=f,
            timeout=600,
        ))
    if not up.get("success", True):
        raise RuntimeError(f"Facebook API: la subida del Reel falló: {up}")

    fin = _check(http.post(
        f"{_GRAPH}/{page_id}/video_reels",
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": descripcion,
            "access_token": access_token,
        },
        timeout=60,
    ))
    if not fin.get("success", True):
        raise RuntimeError(f"Facebook API: no se pudo publicar el Reel: {fin}")

    # Facebook procesa el Reel después; esperamos un poco para detectar errores.
    estado = {}
    for _ in range(20):
        estado = _check(http.get(
            f"{_GRAPH}/{video_id}",
            params={"fields": "status", "access_token": access_token},
            timeout=20,
        )).get("status", {})
        if estado.get("video_status") in ("ready", "error"):
            break
        time.sleep(6)
    if estado.get("video_status") == "error":
        raise RuntimeError(f"Facebook rechazó el Reel: {estado}")

    return {"ok": True, "video_id": video_id, "reel": True,
            "url": f"https://www.facebook.com/reel/{video_id}",
            "estado": estado.get("video_status", "processing")}


def subir_video(video_path: str, titulo: str = "", descripcion: str = "") -> dict:
    """Sube un vídeo a una Página de Facebook: como Reel si es vertical y de 3-90 s,
    si no como vídeo normal. Devuelve {"ok": True, "video_id": ..., "url": ...}."""
    if _es_reel(video_path):
        texto = "\n\n".join(t for t in (titulo, descripcion) if t)
        return subir_reel(video_path, descripcion=texto)

    page_id, access_token = _get_credentials()
    with open(video_path, "rb") as f:
        resp = http.post(
            f"{_GRAPH_VIDEO}/{page_id}/videos",
            data={
                "title": titulo or Path(video_path).stem,
                "description": descripcion,
                "access_token": access_token,
            },
            files={"source": (Path(video_path).name, f, "video/mp4")},
            timeout=600,
        )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Facebook API: {data['error'].get('message', str(data['error']))}")
    resp.raise_for_status()
    video_id = data.get("id", "")
    return {"ok": True, "video_id": video_id, "url": f"https://www.facebook.com/video/{video_id}"}


def publicar_texto(texto: str, link: str = "") -> dict:
    """Publica un post de texto en la página (con enlace opcional)."""
    page_id, access_token = _get_credentials()
    payload = {"message": texto, "access_token": access_token}
    if link:
        payload["link"] = link
    resp = http.post(f"{_GRAPH}/{page_id}/feed", data=payload, timeout=30)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Facebook API: {data['error'].get('message', str(data['error']))}")
    resp.raise_for_status()
    return {"ok": True, "post_id": data.get("id", "")}


def verificar_credenciales() -> dict:
    """Verifica que el token sea válido consultando la info de la página."""
    try:
        page_id, access_token = _get_credentials()
        resp = http.get(
            f"{_GRAPH}/{page_id}",
            params={"fields": "name,id", "access_token": access_token},
            timeout=10,
        )
        data = resp.json()
        if "error" in data:
            return {"connected": False, "error": data["error"].get("message", "Token inválido")}
        return {"connected": True, "page_name": data.get("name", ""), "page_id": data.get("id", "")}
    except RuntimeError as e:
        return {"connected": False, "error": str(e)}
    except Exception as e:
        return {"connected": False, "error": str(e)}
