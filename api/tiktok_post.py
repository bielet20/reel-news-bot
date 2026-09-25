"""
api/tiktok_post.py
Publicación en TikTok a través del servicio bieninforma2-tiktok-api
(https://api.bieninforma2.site), que es quien tiene el Redirect URI HTTPS,
el Client Secret y el token de la cuenta.

La página /tiktok de la web usa estas rutas. Siguen las normas de UX de la
Content Posting API (necesarias para la revisión de la app):
  - antes de publicar se muestra creator_info (nickname, privacidades permitidas,
    interacciones desactivadas, duración máxima);
  - la privacidad no tiene valor por defecto;
  - comentarios / dúo / stitch van desactivados salvo que el usuario los active;
  - se declara el contenido comercial si lo hay;
  - tras publicar se consulta el estado hasta que TikTok termina de procesar.

Config (.env o Canales → TikTok):
  TIKTOK_API_URL   (def. https://api.bieninforma2.site)
  TIKTOK_API_KEY   = PUBLISH_API_KEY del servicio en Coolify
"""
import os
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

OUTPUT_DIR = Path(__file__).parent.parent / "output"
FRONTEND = os.environ.get("FRONTEND_PUBLIC_URL", "http://localhost:3000")

PRIVACY_LEVELS = {"PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"}


def _service_url() -> str:
    return os.environ.get("TIKTOK_API_URL", "https://api.bieninforma2.site").rstrip("/")


def _headers() -> dict:
    key = os.environ.get("TIKTOK_API_KEY")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Falta TIKTOK_API_KEY (la PUBLISH_API_KEY del servicio en Coolify). "
                   "Añádela en Canales → TikTok o en el .env.",
        )
    return {"X-API-Key": key}


def _error(resp: requests.Response) -> str:
    try:
        return resp.json().get("error") or resp.text
    except Exception:
        return resp.text


@router.get("/api/tiktok/estado")
def estado():
    """Si la cuenta está conectada y, si lo está, su creator_info."""
    base = _service_url()
    connect_url = f"{base}/auth/tiktok/login?return={FRONTEND}/tiktok"
    try:
        salud = requests.get(f"{base}/", timeout=10).json()
    except Exception as e:
        return {"servicio": False, "conectado": False, "connect_url": connect_url,
                "error": f"No responde {base}: {e}"}

    out = {
        "servicio": True,
        "conectado": bool(salud.get("tiktokAuthorized")),
        "connect_url": connect_url,
        "api_key": bool(os.environ.get("TIKTOK_API_KEY")),
    }
    if out["conectado"] and out["api_key"]:
        r = requests.get(f"{base}/creator-info", headers=_headers(), timeout=20)
        if r.ok:
            out["creator"] = r.json().get("creatorInfo")
        else:
            out["error"] = _error(r)
    return out


class PublicarTikTok(BaseModel):
    filename: str
    titulo: str = ""
    privacy_level: str
    allow_comment: bool = False
    allow_duet: bool = False
    allow_stitch: bool = False
    brand_organic: bool = False   # "Tu marca"
    brand_content: bool = False   # "Contenido de marca" (colaboración pagada)


@router.post("/api/tiktok/publicar")
def publicar(req: PublicarTikTok):
    if req.privacy_level not in PRIVACY_LEVELS:
        raise HTTPException(status_code=400, detail="Elige la privacidad del vídeo.")
    if req.brand_content and req.privacy_level == "SELF_ONLY":
        raise HTTPException(status_code=400,
                            detail="El contenido de marca no puede publicarse como «Solo yo».")

    path = (OUTPUT_DIR / req.filename).resolve()
    if path.parent != OUTPUT_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Vídeo no encontrado")

    data = {
        "title": req.titulo[:2200],
        "privacyLevel": req.privacy_level,
        "allowComment": str(req.allow_comment).lower(),
        "allowDuet": str(req.allow_duet).lower(),
        "allowStitch": str(req.allow_stitch).lower(),
        "brandOrganicToggle": str(req.brand_organic).lower(),
        "brandContentToggle": str(req.brand_content).lower(),
    }
    with path.open("rb") as f:
        r = requests.post(
            f"{_service_url()}/publish",
            headers=_headers(),
            data=data,
            files={"video": (path.name, f, "video/mp4")},
            timeout=600,
        )
    if not r.ok:
        raise HTTPException(status_code=502, detail=_error(r))
    body = r.json()
    print(f"[TikTok] Publicado vía servicio: publish_id={body.get('publishId')}")
    return {"publish_id": body.get("publishId")}


@router.get("/api/tiktok/publicacion/{publish_id}")
def estado_publicacion(publish_id: str):
    r = requests.get(f"{_service_url()}/status/{publish_id}", headers=_headers(), timeout=20)
    if not r.ok:
        raise HTTPException(status_code=502, detail=_error(r))
    return r.json().get("status") or {}


@router.post("/api/tiktok/desconectar")
def desconectar():
    r = requests.post(f"{_service_url()}/auth/tiktok/disconnect", headers=_headers(), timeout=20)
    if not r.ok:
        raise HTTPException(status_code=502, detail=_error(r))
    return {"ok": True}
