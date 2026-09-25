"""
youtube_uploader.py
Sube videos generados a YouTube automáticamente.

Credenciales (en orden de prioridad):
  1. _tokens/youtube.json  ← guardado por el OAuth web (/canales)
  2. Variables de entorno: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

Playlists gestionadas automáticamente:
  - "Últimas Noticias"   → tipo="noticia"
  - "Curiosidades"       → tipo="curiosidad"
"""

import json
import os
import time
from pathlib import Path


# Traducciones de errores de la YouTube Data API a mensajes legibles
_YT_ERROR_MESSAGES = {
    "uploadLimitExceeded":      "Límite de subidas alcanzado. Verifica tu canal en youtube.com/verify con un número de teléfono para aumentar el límite.",
    "quotaExceeded":            "Cuota diaria de la API agotada. Se resetea a medianoche (hora del Pacífico). Puedes solicitar más cuota en Google Cloud Console.",
    "forbidden":                "Sin permiso para subir a este canal. Reconecta la cuenta en /canales.",
    "authorizationRequired":    "Token de YouTube expirado. Reconecta la cuenta en /canales.",
    "invalidCredentials":       "Credenciales de YouTube no válidas. Reconecta la cuenta en /canales.",
    "dailyLimitExceeded":       "Límite diario de la API alcanzado. Se resetea a medianoche (hora del Pacífico).",
    "rateLimitExceeded":        "Demasiadas peticiones seguidas. Espera unos minutos y reintenta.",
    "videoNotFound":            "El archivo de vídeo no se encontró.",
    "invalidVideoMetadata":     "Los metadatos del vídeo no son válidos (título o descripción incorrectos).",
}


def _yt_error_message(exc: Exception) -> str:
    """Extrae un mensaje legible de un HttpError de la API de YouTube."""
    try:
        content = exc.content if hasattr(exc, "content") else b""
        data = json.loads(content)
        for err in data.get("error", {}).get("errors", []):
            reason = err.get("reason", "")
            if reason in _YT_ERROR_MESSAGES:
                return _YT_ERROR_MESSAGES[reason]
            msg = err.get("message", "")
            if msg:
                return msg
    except Exception:
        pass
    raw = str(exc)
    for reason, msg in _YT_ERROR_MESSAGES.items():
        if reason in raw:
            return msg
    return str(exc)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# YouTube category IDs
_CAT_NOTICIAS = "25"      # News & Politics
_CAT_EDUCACION = "27"     # Education (curiosidades)

# Cache de IDs de playlists para no llamar a la API repetidamente
_playlist_cache: dict[str, str] = {}

_TOKENS_FILE = Path(__file__).parent / "_tokens" / "youtube.json"

# Cache del servicio para no refrescar token en cada llamada
_service_cache: dict = {"service": None, "expires_at": 0}


def _load_credentials() -> tuple[str, str, str, str | None]:
    """Devuelve (client_id, client_secret, refresh_token, access_token|None).
    Prioriza _tokens/youtube.json (OAuth web) sobre las variables de entorno."""
    if _TOKENS_FILE.exists():
        try:
            data = json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))
            client_id     = data.get("client_id") or os.environ.get("YOUTUBE_CLIENT_ID")
            client_secret = data.get("client_secret") or os.environ.get("YOUTUBE_CLIENT_SECRET")
            refresh_token = data.get("refresh_token")
            access_token  = data.get("access_token")
            if client_id and client_secret and refresh_token:
                return client_id, client_secret, refresh_token, access_token
        except Exception:
            pass

    client_id     = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Faltan credenciales de YouTube. Conecta la cuenta en /canales o "
            "configura YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET y "
            "YOUTUBE_REFRESH_TOKEN en el .env."
        )
    return client_id, client_secret, refresh_token, None


def _get_service():
    """Devuelve el cliente de YouTube, reutilizando el service si el token sigue vigente."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if _service_cache["service"] and time.time() < _service_cache["expires_at"]:
        return _service_cache["service"]

    client_id, client_secret, refresh_token, access_token = _load_credentials()

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )

    if not creds.valid:
        creds.refresh(Request())
        if _TOKENS_FILE.exists():
            try:
                data = json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))
                data["access_token"] = creds.token
                _TOKENS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

    service = build("youtube", "v3", credentials=creds)
    expiry = creds.expiry.timestamp() - 60 if creds.expiry else time.time() + 3540
    _service_cache.update({"service": service, "expires_at": expiry})
    return service


def invalidate_service_cache():
    """Limpia el cache del servicio (llamar tras reconectar la cuenta)."""
    _service_cache.update({"service": None, "expires_at": 0})


def _playlist_id(service, nombre: str, descripcion: str = "") -> str:
    """Devuelve el ID de una playlist por nombre, creándola si no existe."""
    if nombre in _playlist_cache:
        return _playlist_cache[nombre]

    req = service.playlists().list(part="snippet", mine=True, maxResults=50)
    while req:
        resp = req.execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"] == nombre:
                pid = item["id"]
                _playlist_cache[nombre] = pid
                return pid
        req = service.playlists().list_next(req, resp)

    resp = service.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": nombre, "description": descripcion},
            "status":  {"privacyStatus": "public"},
        }
    ).execute()
    pid = resp["id"]
    _playlist_cache[nombre] = pid
    print(f"[YouTube] Playlist '{nombre}' creada ({pid})")
    return pid


def _descripcion(titulo: str, tipo: str, attribution: dict | None) -> str:
    """Construye la descripción del video con datos de atribución."""
    lineas = []

    if tipo == "curiosidad":
        lineas.append("💡 ¿Lo sabías? Un dato curioso que no te puedes perder.")
    else:
        lineas.append("📰 Última hora — Noticia verificada de fuentes de referencia.")

    lineas.append("")

    if attribution:
        fuente   = attribution.get("fuente", "")
        autor    = attribution.get("autor", "")
        fecha    = (attribution.get("fecha_publicacion") or "")[:10]
        url_orig = attribution.get("url_original", "")

        if fuente:   lineas.append(f"📰 Fuente: {fuente}")
        if autor:    lineas.append(f"✍️ Autor: {autor}")
        if fecha:    lineas.append(f"📅 Publicado: {fecha}")
        documentacion = attribution.get("documentacion", "")
        verificadores = attribution.get("verificadores") or []
        fact_checkers = attribution.get("fact_checkers") or []
        if documentacion:
            lineas.append(f"✅ {documentacion}")
        if verificadores:
            lineas.append(f"🔎 Contrastada por: {', '.join(verificadores)}")
        if fact_checkers:
            lineas.append(f"🛡️ Fact-check: {', '.join(fact_checkers)}")
        if url_orig: lineas.append(f"🔗 Artículo completo: {url_orig}")
    else:
        lineas.append("Noticias verificadas: El País, Reuters, BBC Mundo y más.")

    lineas += [
        "",
        "───────────────────────────────",
        "Este vídeo es un resumen informativo. Los derechos del contenido",
        "original pertenecen al medio citado arriba.",
        "",
        "#Noticias #UltimaHora #NoticiasVerificadas" if tipo == "noticia"
        else "#Curiosidades #SabíasQue #DatosInteresantes",
        "🔔 Suscríbete y activa la campanita.",
    ]
    return "\n".join(lineas)


def subir_video(
    video_path: str,
    titulo: str,
    tipo: str = "noticia",
    attribution: dict | None = None,
    tags_extra: list[str] | None = None,
    thumbnail_path: str | None = None,
) -> dict:
    """
    Sube un video MP4 a YouTube y lo añade a la playlist correspondiente.

    Args:
        video_path: Ruta absoluta al archivo MP4.
        titulo:     Título del video (máx. 100 chars en YouTube).
        tipo:       "noticia" o "curiosidad".
        attribution: Dict con fuente, autor, fecha, url_original (opcional).
        tags_extra: Lista adicional de tags.

    Returns:
        {"video_id": str, "url": str, "playlist_id": str | None}

    Raises:
        RuntimeError si faltan credenciales o el upload falla.
    """
    from googleapiclient.http import MediaFileUpload

    service = _get_service()

    categoria    = _CAT_NOTICIAS if tipo == "noticia" else _CAT_EDUCACION
    descripcion  = _descripcion(titulo, tipo, attribution)
    tags_base    = (["noticias", "reelnews", "ultimahora", "informacion"]
                    if tipo == "noticia"
                    else ["curiosidades", "sabíasque", "datos", "aprende"])
    tags         = (tags_base + (tags_extra or []))[:500]

    body = {
        "snippet": {
            "title":                titulo[:100],
            "description":          descripcion[:5000],
            "tags":                 tags,
            "categoryId":           categoria,
            "defaultLanguage":      "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus":            "public",
            "selfDeclaredMadeForKids":  False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    print(f"[YouTube] Subiendo '{titulo[:60]}…' (tipo: {tipo})")

    request = service.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[YouTube] Progreso: {int(status.progress() * 100)}%")

    video_id  = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"[YouTube] ¡Publicado! {video_url}")

    # Subir miniatura personalizada
    if thumbnail_path and __import__("os").path.isfile(thumbnail_path):
        try:
            from googleapiclient.http import MediaFileUpload as _MFU
            service.thumbnails().set(
                videoId=video_id,
                media_body=_MFU(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            print(f"[YouTube] Miniatura subida: {thumbnail_path}")
        except Exception as e:
            print(f"[YouTube][WARN] No se pudo subir miniatura: {e}")

    # Añadir a la playlist
    playlist_nombre = "Últimas Noticias" if tipo == "noticia" else "Curiosidades"
    playlist_desc   = (
        "Las últimas noticias verificadas en menos de 60 segundos."
        if tipo == "noticia"
        else "Datos curiosos e interesantes que quizás no conocías."
    )
    playlist_id = None
    try:
        playlist_id = _playlist_id(service, playlist_nombre, playlist_desc)
        service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            }
        ).execute()
        print(f"[YouTube] Añadido a '{playlist_nombre}'")
    except Exception as e:
        print(f"[YouTube][WARN] No se pudo añadir a playlist: {e}")

    return {"video_id": video_id, "url": video_url, "playlist_id": playlist_id}


def verificar_credenciales() -> dict:
    """Comprueba si las credenciales están configuradas y son válidas."""
    try:
        _load_credentials()
    except RuntimeError as e:
        return {"ok": False, "motivo": str(e)}

    try:
        service = _get_service()
        resp    = service.channels().list(part="snippet", mine=True).execute()
        items   = resp.get("items", [])
        nombre  = items[0]["snippet"]["title"] if items else "Canal sin nombre"
        return {"ok": True, "canal": nombre}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}
