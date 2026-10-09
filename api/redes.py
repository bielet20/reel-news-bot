"""
api/redes.py
API del Centro de Redes (ver centro_redes.py). La usan la web (/redes) y las
demás aplicaciones (AI Studio, cursos…) para publicar en los canales.

  GET    /api/redes                       cuentas con estado + canales
  POST   /api/redes/cuentas               cuenta nueva (sin conectar)
  DELETE /api/redes/cuentas/{id}          quitar del Centro (el token se conserva)
  GET    /api/redes/cuentas/{id}/conectar URL de Google para autorizar el canal
  PUT    /api/redes/canales/{id}          crear/editar canal y sus cuentas
  POST   /api/redes/publicar              subir (archivo o ruta) → trabajo
  GET    /api/redes/trabajos/{id}         estado del trabajo
  GET    /api/redes/publicaciones         historial
"""
import os
import secrets
import shutil
import sys
import threading
import urllib.parse
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests as http
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
import centro_redes as cr  # noqa: E402

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent
SUBIDAS = BASE_DIR / "_uploads" / "redes"
FRONTEND = "http://localhost:3000"
# `ruta` solo puede apuntar a vídeos de estas carpetas (nunca a .env, _tokens…)
RUTAS_VIDEO = ("output", "_uploads")
EXT_VIDEO = (".mp4", ".mov", ".m4v", ".webm", ".mkv")

_trabajos: dict[str, dict] = {}
_tlock = threading.Lock()


def _error(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/redes")
def redes_estado(comprobar: bool = False):
    return cr.resumen(comprobar)


class CuentaNueva(BaseModel):
    plataforma: str
    nombre: str
    channel_id: str = ""


@router.post("/api/redes/cuentas")
def redes_crear_cuenta(req: CuentaNueva):
    try:
        return cr.crear_cuenta(req.plataforma, req.nombre, req.channel_id)
    except cr.RedesError as e:
        _error(e)


@router.delete("/api/redes/cuentas/{cuenta_id}")
def redes_borrar_cuenta(cuenta_id: str):
    try:
        cr.borrar_cuenta(cuenta_id)
    except cr.RedesError as e:
        _error(e)
    return {"ok": True}


@router.post("/api/redes/cuentas/{cuenta_id}/desconectar")
def redes_desconectar(cuenta_id: str):
    """Borra la autorización guardada (la cuenta sigue en el Centro, sin conectar)."""
    try:
        c = cr.cuenta(cuenta_id)
        p = cr.token_path(c)
    except cr.RedesError as e:
        _error(e)
    if c.get("origen") == "sistema_reels" or c.get("token") == "youtube.json":
        # youtube.json es el de los reels automáticos: se gestiona en Canales
        raise HTTPException(status_code=400, detail="Esta cuenta se gestiona en Canales.")
    if p and p.exists():
        p.unlink()
    if c["plataforma"] == "youtube":
        import youtube_uploader as yt
        yt.invalidate_service_cache(p)
    cr.olvidar_estado(cuenta_id)
    return {"ok": True}


def _volver_seguro(volver: str) -> str:
    """Solo se vuelve a páginas de esta máquina (web, AI Studio…)."""
    if volver:
        u = urllib.parse.urlparse(volver)
        if u.scheme in ("http", "https") and u.hostname in ("localhost", "127.0.0.1"):
            return volver
    return f"{FRONTEND}/redes"


def _con_query(url: str, **params) -> str:
    sep = "&" if "?" in url else "?"
    frag = ""
    if "#" in url:
        url, frag = url.split("#", 1)
        frag = "#" + frag
    return url + sep + urllib.parse.urlencode(params) + frag


@router.get("/api/redes/cuentas/{cuenta_id}/conectar")
def redes_conectar(cuenta_id: str, volver: str = "", ir: bool = False):
    """Devuelve la URL de Google (o redirige si ir=1) para autorizar el canal.
    Usa la misma app y el mismo redirect que Canales: no hay que tocar Google Cloud."""
    from api.accounts import BACKEND_CB, YT_SCOPES, _oauth_state
    try:
        c = cr.cuenta(cuenta_id)
    except cr.RedesError as e:
        _error(e)
    if c["plataforma"] != "youtube":
        raise HTTPException(status_code=400, detail="Desde el Centro solo se conecta YouTube por ahora.")
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    if not client_id or not os.environ.get("YOUTUBE_CLIENT_SECRET"):
        raise HTTPException(status_code=400, detail="Faltan YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET en el .env.")
    state = secrets.token_urlsafe(16)
    _oauth_state[state] = {"cuenta": cuenta_id, "volver": _volver_seguro(volver)}
    params = {
        "client_id": client_id,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/youtube/callback",
        "response_type": "code",
        "scope": YT_SCOPES,
        "access_type": "offline",
        # select_account: que Google pregunte qué canal (cuentas de marca)
        "prompt": "consent select_account",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)
    if ir:
        return RedirectResponse(url)
    return {"auth_url": url}


def completar_youtube(destino: dict, code: Optional[str], error: Optional[str]):
    """Final del OAuth de una cuenta del Centro (lo llama /api/accounts/youtube/callback)."""
    from api.accounts import BACKEND_CB
    volver = destino["volver"]
    cuenta_id = destino["cuenta"]
    if error or not code:
        return RedirectResponse(_con_query(volver, error=f"youtube_{error or 'sin_codigo'}", cuenta=cuenta_id))
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    resp = http.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": f"{BACKEND_CB}/api/accounts/youtube/callback",
        "grant_type": "authorization_code",
    }, timeout=30)
    if not resp.ok:
        return RedirectResponse(_con_query(volver, error="youtube_token_failed", cuenta=cuenta_id))
    t = resp.json()
    if not t.get("refresh_token"):
        return RedirectResponse(_con_query(volver, error="youtube_no_refresh", cuenta=cuenta_id))
    tokens = {
        "refresh_token": t["refresh_token"],
        "access_token": t.get("access_token"),
        "expires_at": (datetime.now() + timedelta(seconds=t.get("expires_in", 3600) - 60)).isoformat(),
        "client_id": client_id,
        "client_secret": client_secret,
    }
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials(token=t.get("access_token"), refresh_token=t["refresh_token"],
                            client_id=client_id, client_secret=client_secret,
                            token_uri="https://oauth2.googleapis.com/token")
        ch = build("youtube", "v3", credentials=creds).channels().list(part="snippet", mine=True).execute()
        item = (ch.get("items") or [None])[0]
        if not item:
            return RedirectResponse(_con_query(volver, error="youtube_sin_canal", cuenta=cuenta_id))
        real = {"channel_id": item["id"], "titulo": item["snippet"]["title"],
                "custom_url": item["snippet"].get("customUrl", "")}
        cr.guardar_token_youtube(cuenta_id, tokens, real)
    except cr.RedesError:
        return RedirectResponse(_con_query(volver, error="youtube_wrong_channel",
                                           canal=real["titulo"], cuenta=cuenta_id))
    except Exception as e:  # noqa: BLE001
        print(f"[redes] OAuth {cuenta_id}: {e}")
        return RedirectResponse(_con_query(volver, error="youtube_fallo", cuenta=cuenta_id))
    return RedirectResponse(_con_query(volver, youtube="ok", cuenta=cuenta_id))


class CanalReq(BaseModel):
    nombre: str = ""
    tema: str = ""
    web: Optional[str] = None
    cuentas: dict[str, str] = {}
    youtube: Optional[dict] = None


@router.put("/api/redes/canales/{canal_id}")
def redes_guardar_canal(canal_id: str, req: CanalReq):
    try:
        return cr.guardar_canal(canal_id, req.nombre, req.tema, req.cuentas, req.youtube, req.web)
    except cr.RedesError as e:
        _error(e)


@router.post("/api/redes/publicar")
def redes_publicar(
    canal: str = Form(...),
    titulo: str = Form(""),
    descripcion: str = Form(""),
    redes: str = Form(""),
    privacidad: str = Form("public"),
    origen: str = Form(""),
    ruta: str = Form(""),
    archivo: Optional[UploadFile] = File(None),
):
    """Sube un vídeo a las redes de un canal. Manda el fichero (`archivo`) o
    una `ruta` que el backend pueda leer (p. ej. output/xxx.mp4). Responde al
    momento con el id del trabajo; el resultado se lee en /api/redes/trabajos."""
    try:
        cr.canal(canal)
    except cr.RedesError as e:
        _error(e)
    temporal = None
    if archivo is not None and archivo.filename:
        SUBIDAS.mkdir(parents=True, exist_ok=True)
        nombre = Path(archivo.filename).name
        if Path(nombre).suffix.lower() not in EXT_VIDEO:
            raise HTTPException(status_code=400, detail="Eso no es un vídeo.")
        temporal = SUBIDAS / f"{uuid.uuid4().hex[:8]}_{nombre}"
        with open(temporal, "wb") as f:
            shutil.copyfileobj(archivo.file, f, length=1024 * 1024)
        video = temporal
    elif ruta:
        video = (BASE_DIR / ruta).resolve() if not Path(ruta).is_absolute() else Path(ruta).resolve()
        permitidas = [(BASE_DIR / d).resolve() for d in RUTAS_VIDEO]
        if not any(d in video.parents for d in permitidas) or video.suffix.lower() not in EXT_VIDEO:
            raise HTTPException(status_code=400, detail="Solo vídeos de output/ o _uploads/.")
        if not video.is_file():
            raise HTTPException(status_code=404, detail="No encuentro ese vídeo.")
    else:
        raise HTTPException(status_code=400, detail="Manda el archivo del vídeo o su ruta.")

    lista = [r.strip() for r in redes.split(",") if r.strip()] or None
    tid = uuid.uuid4().hex[:8]
    with _tlock:
        _trabajos[tid] = {"id": tid, "estado": "subiendo", "canal": canal, "titulo": titulo,
                          "resultados": {}, "error": None}

    def run():
        try:
            res = cr.publicar(canal, video, titulo, descripcion, lista, privacidad, origen=origen)
            fin = {"estado": "hecho" if all(r.get("ok") for r in res.values()) else "con_errores",
                   "resultados": res}
        except Exception as e:  # noqa: BLE001
            fin = {"estado": "fallido", "error": str(e)}
        finally:
            if temporal is not None:
                temporal.unlink(missing_ok=True)
        with _tlock:
            _trabajos[tid].update(fin)

    threading.Thread(target=run, daemon=True).start()
    return {"trabajo": tid}


@router.get("/api/redes/trabajos/{tid}")
def redes_trabajo(tid: str):
    with _tlock:
        t = _trabajos.get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado (¿se reinició el backend?).")
    return t


@router.get("/api/redes/publicaciones")
def redes_publicaciones(canal: str = "", limite: int = 100):
    return cr.publicaciones(canal or None)[:max(1, min(limite, 500))]
