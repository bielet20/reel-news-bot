"""
facebook_uploader.py
Sube vídeos y publica texto en una Página de Facebook via Graph API v19.
"""
import os
import requests as http
from pathlib import Path

_GRAPH = "https://graph.facebook.com/v19.0"
_GRAPH_VIDEO = "https://graph-video.facebook.com/v19.0"


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


def subir_video(video_path: str, titulo: str = "", descripcion: str = "") -> dict:
    """Sube un vídeo a una Página de Facebook. Devuelve {"ok": True, "video_id": ..., "url": ...}."""
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
