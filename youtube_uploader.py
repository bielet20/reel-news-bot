"""
youtube_uploader.py
Sube videos generados a YouTube automáticamente.

Requiere credenciales OAuth 2.0 de la YouTube Data API v3.
Variables de entorno (.env):
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN   ← obtenido con scripts/youtube_auth.py

Playlists gestionadas automáticamente:
  - "Últimas Noticias"   → tipo="noticia"
  - "Curiosidades"       → tipo="curiosidad"
"""

import os
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# YouTube category IDs
_CAT_NOTICIAS = "25"      # News & Politics
_CAT_EDUCACION = "27"     # Education (curiosidades)

# Cache de IDs de playlists para no llamar a la API repetidamente
_playlist_cache: dict[str, str] = {}


def _get_service():
    """Construye el cliente de YouTube con credenciales OAuth desde .env"""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_id     = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Faltan credenciales de YouTube. Configura YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET y YOUTUBE_REFRESH_TOKEN en el .env. "
            "Ejecuta 'python scripts/youtube_auth.py' para obtener el refresh token."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


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
    if not all([
        os.environ.get("YOUTUBE_CLIENT_ID"),
        os.environ.get("YOUTUBE_CLIENT_SECRET"),
        os.environ.get("YOUTUBE_REFRESH_TOKEN"),
    ]):
        return {"ok": False, "motivo": "Faltan variables en .env"}

    try:
        service = _get_service()
        resp    = service.channels().list(part="snippet", mine=True).execute()
        items   = resp.get("items", [])
        nombre  = items[0]["snippet"]["title"] if items else "Canal sin nombre"
        return {"ok": True, "canal": nombre}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}
