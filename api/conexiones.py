"""
api/conexiones.py
Gestor de la conexion de Telegram de cursos.

No lee ni escribe _tokens/telegram.json (noticias / Bieninforma2).
No llama a la API de Telegram. No envia videos.
"""
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

router = APIRouter()

# Archivo nuevo, separado del token de noticias.
CURSOS_PATH = Path(__file__).resolve().parent.parent / "_tokens" / "telegram-cursos.json"

_VACIO = {
    "nombre_canal": "RiverSec",
    "nombre_bot": "RiverSec Bot",
    "bot_token": "",
    "chat_id": "",
}


def _leer() -> dict:
    data = dict(_VACIO)
    if not CURSOS_PATH.exists():
        return data
    try:
        raw = json.loads(CURSOS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return data
    if not isinstance(raw, dict):
        return data
    for clave in _VACIO:
        valor = raw.get(clave, data[clave])
        data[clave] = valor if isinstance(valor, str) else data[clave]
    return data


def _publico(data: dict) -> dict:
    """Nunca devuelve el token. Solo si hay uno guardado."""
    return {
        "nombre_canal": data.get("nombre_canal") or "",
        "nombre_bot": data.get("nombre_bot") or "",
        "chat_id": data.get("chat_id") or "",
        "bot_token_configurado": bool(data.get("bot_token")),
    }


def _guardar(data: dict) -> None:
    CURSOS_PATH.parent.mkdir(exist_ok=True)
    CURSOS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


class GuardarCursosReq(BaseModel):
    nombre_canal: str = ""
    nombre_bot: str = ""
    bot_token: str = ""
    chat_id: str = ""


@router.get("/api/conexiones/telegram-cursos")
def obtener_telegram_cursos():
    return _publico(_leer())


@router.put("/api/conexiones/telegram-cursos")
def guardar_telegram_cursos(req: GuardarCursosReq):
    """Escribe solo _tokens/telegram-cursos.json.
    Un token vacio conserva el que ya hubiera, sin imprimirlo."""
    actual = _leer()
    nombre_canal = req.nombre_canal.strip()
    nombre_bot = req.nombre_bot.strip()
    if nombre_canal:
        actual["nombre_canal"] = nombre_canal
    if nombre_bot:
        actual["nombre_bot"] = nombre_bot
    actual["chat_id"] = req.chat_id.strip()
    token = req.bot_token.strip()
    if token:
        actual["bot_token"] = token
    _guardar(actual)
    return {"ok": True, **_publico(actual)}

# YouTube de cursos. Solo este archivo. No es el token de noticias.
YT_CURSOS_PATH = Path(__file__).resolve().parent.parent / "_tokens" / "youtube-cursos.json"
YT_OAUTH_REDIRECT = "http://127.0.0.1:8000/api/conexiones/youtube-cursos/callback"
YT_OAUTH_SCOPE = (
    "https://www.googleapis.com/auth/youtube.upload "
    "https://www.googleapis.com/auth/youtube"
)
YT_PANEL_OK = "http://127.0.0.1:3000/conexiones?youtube=ok"

_YT_CLAVES = (
    "nombre",
    "handle",
    "canal_id",
    "client_id",
    "client_secret",
    "refresh_token",
)

_YT_VACIO = {
    "nombre": "RayverSec",
    "handle": "@RAYVERSEC",
    "canal_id": "UCbEnilZIVXwp9lNAv91j69g",
    "client_id": "",
    "client_secret": "",
    "refresh_token": "",
}

# States de OAuth de este proceso. No se escriben en disco.
_YT_OAUTH_STATES = set()


def _yt_html(mensaje: str, status: int = 200) -> HTMLResponse:
    pagina = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        "<title>YouTube de cursos</title></head><body><p>"
        + mensaje
        + "</p></body></html>"
    )
    return HTMLResponse(pagina, status_code=status)


def _yt_texto(origen: dict, clave: str) -> str:
    valor = origen.get(clave)
    if isinstance(valor, str):
        return valor
    return ""


def _yt_normalizar_cuenta_servicio(sa):
    """Solo los campos de la cuenta de servicio. None si no vale."""
    if not isinstance(sa, dict):
        return None
    if sa.get("type") != "service_account":
        return None
    project_id = _yt_texto(sa, "project_id").strip()
    private_key = _yt_texto(sa, "private_key")
    client_email = _yt_texto(sa, "client_email").strip()
    if not project_id or not private_key.strip() or not client_email:
        return None
    if "BEGIN PRIVATE KEY" not in private_key and "BEGIN RSA PRIVATE KEY" not in private_key:
        return None
    limpio = {
        "type": "service_account",
        "project_id": project_id,
    }
    private_key_id = _yt_texto(sa, "private_key_id").strip()
    if private_key_id:
        limpio["private_key_id"] = private_key_id
    limpio["private_key"] = private_key
    limpio["client_email"] = client_email
    client_id = _yt_texto(sa, "client_id").strip()
    if client_id:
        limpio["client_id"] = client_id
    token_uri = _yt_texto(sa, "token_uri").strip()
    if token_uri:
        limpio["token_uri"] = token_uri
    return limpio


def _yt_validar_cuenta_servicio(payload) -> dict:
    """Mensajes cortos, sin repetir el secreto."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="El JSON no es un objeto.")
    if payload.get("type") != "service_account":
        raise HTTPException(
            status_code=400,
            detail="El campo type debe ser service_account.",
        )
    for clave in ("project_id", "private_key", "client_email"):
        valor = payload.get(clave)
        if not isinstance(valor, str) or not valor.strip():
            raise HTTPException(status_code=400, detail="Falta " + clave + ".")
    normalizada = _yt_normalizar_cuenta_servicio(payload)
    if normalizada is None:
        raise HTTPException(
            status_code=400,
            detail="private_key no tiene formato de clave privada.",
        )
    return normalizada


def _yt_leer() -> dict:
    data = dict(_YT_VACIO)
    data["service_account"] = None
    if not YT_CURSOS_PATH.exists():
        return data
    try:
        raw = json.loads(YT_CURSOS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return data
    if not isinstance(raw, dict):
        return data
    for clave in _YT_CLAVES:
        valor = raw.get(clave, data[clave])
        data[clave] = valor if isinstance(valor, str) else data[clave]
    sa = raw.get("service_account")
    if isinstance(sa, dict):
        data["service_account"] = sa
    return data


def _yt_publico(data: dict) -> dict:
    def _configurado(clave: str) -> bool:
        valor = data.get(clave) or ""
        return bool(valor.strip()) if isinstance(valor, str) else False

    publico = {
        "nombre": data.get("nombre") or "RayverSec",
        "handle": data.get("handle") or "@RAYVERSEC",
        "canal_id": data.get("canal_id") or "UCbEnilZIVXwp9lNAv91j69g",
        "client_id_configurado": _configurado("client_id"),
        "client_secret_configurado": _configurado("client_secret"),
        "refresh_configurado": _configurado("refresh_token"),
    }
    cuenta = _yt_normalizar_cuenta_servicio(data.get("service_account"))
    publico["service_account_configurado"] = cuenta is not None
    if cuenta is not None:
        publico["project_id"] = cuenta["project_id"]
        publico["client_email"] = cuenta["client_email"]
    return publico


def _yt_guardar(data: dict) -> None:
    limpio = {}
    for clave in _YT_CLAVES:
        valor = data.get(clave, _YT_VACIO[clave])
        limpio[clave] = valor if isinstance(valor, str) else _YT_VACIO[clave]
    cuenta = _yt_normalizar_cuenta_servicio(data.get("service_account"))
    if cuenta is not None:
        limpio["service_account"] = cuenta
    YT_CURSOS_PATH.parent.mkdir(exist_ok=True)
    YT_CURSOS_PATH.write_text(
        json.dumps(limpio, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _yt_escribir_cuenta_servicio(cuenta: dict) -> None:
    """Añade service_account sin vaciar el OAuth ni otras claves ya guardadas."""
    if YT_CURSOS_PATH.exists():
        try:
            raw = json.loads(YT_CURSOS_PATH.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="No se pudo leer el archivo de la conexión.",
            )
        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=400,
                detail="El archivo de la conexión no es un objeto.",
            )
    else:
        raw = dict(_YT_VACIO)
    for clave, valor in _YT_VACIO.items():
        raw.setdefault(clave, valor)
    raw["service_account"] = cuenta
    YT_CURSOS_PATH.parent.mkdir(exist_ok=True)
    YT_CURSOS_PATH.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


class GuardarYouTubeCursosReq(BaseModel):
    nombre: str = ""
    handle: str = ""
    canal_id: str = ""
    client_id: str = ""
    client_secret: str = ""


@router.get("/api/conexiones/youtube-cursos")
def obtener_youtube_cursos():
    return _yt_publico(_yt_leer())


@router.put("/api/conexiones/youtube-cursos")
def guardar_youtube_cursos(req: GuardarYouTubeCursosReq):
    # Un id o un secreto vacio conserva el ya guardado.
    # El secreto no se trata como refresh_token.
    actual = _yt_leer()
    nombre = req.nombre.strip()
    handle = req.handle.strip()
    canal_id = req.canal_id.strip()
    if nombre:
        actual["nombre"] = nombre
    if handle:
        if not handle.startswith("@"):
            handle = "@" + handle
        actual["handle"] = handle
    if canal_id:
        actual["canal_id"] = canal_id
    client_id = req.client_id.strip()
    client_secret = req.client_secret.strip()
    if client_id:
        actual["client_id"] = client_id
    if client_secret:
        actual["client_secret"] = client_secret
    _yt_guardar(actual)
    return {"ok": True, **_yt_publico(actual)}



@router.post("/api/conexiones/youtube-cursos/json")
async def guardar_youtube_cursos_json(request: Request):
    """Guarda la cuenta de servicio. No pisa client_id, client_secret ni refresh_token."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="El archivo no es un JSON válido.")
    cuenta = _yt_validar_cuenta_servicio(payload)
    _yt_escribir_cuenta_servicio(cuenta)
    return {"ok": True, **_yt_publico(_yt_leer())}


@router.get("/api/conexiones/youtube-cursos/autorizar")
def autorizar_youtube_cursos():
    data = _yt_leer()
    client_id = data.get("client_id") or ""
    client_secret = data.get("client_secret") or ""
    if (
        not isinstance(client_id, str)
        or not client_id.strip()
        or not isinstance(client_secret, str)
        or not client_secret.strip()
    ):
        return _yt_html(
            "Faltan el ID de cliente y el secreto. "
            "Guárdalos en la tarjeta de YouTube de cursos y vuelve a pulsar Autorizar con Google."
        )
    state = secrets.token_urlsafe(32)
    _YT_OAUTH_STATES.add(state)
    query = urllib.parse.urlencode(
        {
            "client_id": client_id.strip(),
            "redirect_uri": YT_OAUTH_REDIRECT,
            "response_type": "code",
            "scope": YT_OAUTH_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        },
        quote_via=urllib.parse.quote,
    )
    destino = "https://accounts.google.com/o/oauth2/v2/auth?" + query
    return RedirectResponse(destino, status_code=302)


@router.get("/api/conexiones/youtube-cursos/callback")
def callback_youtube_cursos(code: str = "", state: str = "", error: str = ""):
    if not state or state not in _YT_OAUTH_STATES:
        return _yt_html(
            "La autorización no es válida. Vuelve a pulsar Autorizar con Google.",
            status=400,
        )
    _YT_OAUTH_STATES.discard(state)
    if error or not code:
        return _yt_html(
            "Google no ha completado la autorización. No se ha guardado nada.",
            status=400,
        )
    data = _yt_leer()
    client_id = data.get("client_id") if isinstance(data.get("client_id"), str) else ""
    client_secret = data.get("client_secret") if isinstance(data.get("client_secret"), str) else ""
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    if not client_id or not client_secret:
        return _yt_html(
            "Faltan el ID de cliente y el secreto. No se ha guardado la autorización.",
            status=400,
        )
    formulario = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": YT_OAUTH_REDIRECT,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    peticion = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=formulario,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            crudo = respuesta.read().decode("utf-8")
    except urllib.error.HTTPError:
        return _yt_html(
            "Google ha rechazado el canje de la autorización. No se ha guardado nada.",
            status=400,
        )
    except Exception:
        return _yt_html(
            "No se pudo hablar con Google para guardar la autorización.",
            status=502,
        )
    try:
        payload = json.loads(crudo)
    except Exception:
        return _yt_html(
            "Google no ha devuelto una respuesta válida. No se ha guardado nada.",
            status=502,
        )
    refresh = payload.get("refresh_token") if isinstance(payload, dict) else None
    if not isinstance(refresh, str) or not refresh.strip():
        return _yt_html(
            "Google no ha devuelto la autorización permanente. "
            "No se ha guardado nada. Vuelve a pulsar Autorizar con Google y acepta el acceso.",
            status=400,
        )
    data["refresh_token"] = refresh.strip()
    _yt_guardar(data)
    return RedirectResponse(YT_PANEL_OK, status_code=302)
