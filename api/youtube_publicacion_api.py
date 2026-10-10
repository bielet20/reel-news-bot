"""
Endpoints de la publicación de vídeos de YouTube (subidos siempre en privado).
Ver youtube_publicacion.py y docs/youtube_publicacion.md
"""
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

CORE_DIR = Path(__file__).parent.parent
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import youtube_publicacion as _yp  # noqa: E402

router = APIRouter()

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def _validar(video_id: str):
    if not _VIDEO_ID_RE.match(video_id or ""):
        raise HTTPException(400, "ID de vídeo de YouTube no válido")


def _vista(e: dict) -> dict:
    """Resumen para la web: 'publico' | 'privado' | 'error'."""
    st = e.get("state")
    estado = "publico" if st == "publicado" else ("error" if st in ("error", "bloqueado") else "privado")
    return {**e, "estado": estado}


@router.get("/api/youtube/publicacion")
def listar_publicacion(estado: str = ""):
    """Vídeos registrados (filtrable por state: pendiente/publicado/error/bloqueado)."""
    items = _yp.listar()
    if estado:
        items = [i for i in items if i.get("state") == estado]
    return {"autopublicar": _yp.autopublicar_activo(), "items": [_vista(i) for i in items]}


@router.get("/api/youtube/publicacion/{video_id}")
def estado_publicacion(video_id: str):
    """Estado de un vídeo según el registro local (no consulta a YouTube).
    404 = vídeo no registrado (p. ej. subido antes de este cambio, ya público)."""
    _validar(video_id)
    e = _yp.obtener(video_id)
    if not e:
        raise HTTPException(404, "Vídeo no registrado")
    return _vista(e)


@router.post("/api/youtube/publicacion/{video_id}/publicar")
def publicar(video_id: str):
    """Botón 'Publicar': pasa el vídeo a público solo si YouTube ya lo procesó.
    409 si aún se está procesando; 403 si faltan permisos; 404/422 si falló."""
    _validar(video_id)
    code, body = _yp.publicar_manual(video_id)
    return JSONResponse(status_code=code, content=body)


@router.post("/api/youtube/publicacion/{video_id}/reintentar")
def reintentar_publicacion(video_id: str):
    """Solo con el publicador automático (YT_AUTOPUBLICAR=1): vuelve a poner en
    'pendiente' un vídeo bloqueado/en error."""
    _validar(video_id)
    e = _yp.reintentar(video_id)
    if not e:
        raise HTTPException(404, "Vídeo no registrado en la cola de publicación")
    return _vista(e)


# Publicador automático: solo arranca si YT_AUTOPUBLICAR=1 (por defecto, no).
_yp.iniciar_publicador()
