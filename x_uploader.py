"""
x_uploader.py
Sube videos a X (Twitter) usando OAuth 1.0a + API v1.1 media upload + v2 tweets.

Requiere en .env (o _tokens/x.json):
  X_API_KEY           → Consumer Key
  X_API_SECRET        → Consumer Secret
  X_ACCESS_TOKEN      → Access Token
  X_ACCESS_SECRET     → Access Token Secret

Obtén las 4 claves en: https://developer.twitter.com/en/portal/
"""

import os
import time
import math
import json as _json
from pathlib import Path

UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_URL  = "https://api.twitter.com/2/tweets"

_X_ERROR_MESSAGES = {
    "32":  "Credenciales de X no válidas. Reconecta la cuenta en /canales.",
    "64":  "Tu cuenta de X ha sido suspendida.",
    "88":  "Límite de peticiones alcanzado. Espera unos minutos.",
    "89":  "Token de X expirado. Reconecta la cuenta en /canales.",
    "135": "El timestamp de la petición no es válido. Revisa la fecha del sistema.",
    "161": "Límite de follows alcanzado.",
    "179": "No tienes permiso para ver este estado.",
    "185": "Has alcanzado el límite de tweets por día.",
    "187": "Tweet duplicado. Espera unos minutos antes de reintentarlo.",
    "226": "Tweet marcado como spam automático.",
    "261": "Tu app está suspendida. Revisa developer.twitter.com.",
    "326": "Tu cuenta está temporalmente bloqueada.",
    "453": "Se requiere acceso a la API de X. Revisa tu plan en developer.twitter.com.",
}


def _x_error_message(exc: Exception) -> str:
    raw = str(exc)
    try:
        data = _json.loads(getattr(exc, "response", None) and exc.response.text or "{}")
        errors = data.get("errors") or data.get("detail", "")
        if isinstance(errors, list) and errors:
            code = str(errors[0].get("code", ""))
            if code in _X_ERROR_MESSAGES:
                return _X_ERROR_MESSAGES[code]
            msg = errors[0].get("message") or errors[0].get("title", "")
            if msg:
                return msg
    except Exception:
        pass
    for code, msg in _X_ERROR_MESSAGES.items():
        if f'"code":{code}' in raw or f'"code": {code}' in raw:
            return msg
    return raw


def _get_auth():
    from requests_oauthlib import OAuth1

    from accounts_manager import load_token
    tok = load_token("x")
    if tok:
        api_key    = tok.get("api_key", "")
        api_secret = tok.get("api_secret", "")
        at         = tok.get("access_token", "")
        at_secret  = tok.get("access_secret", "")
    else:
        api_key    = os.environ.get("X_API_KEY", "")
        api_secret = os.environ.get("X_API_SECRET", "")
        at         = os.environ.get("X_ACCESS_TOKEN", "")
        at_secret  = os.environ.get("X_ACCESS_SECRET", "")

    if not all([api_key, api_secret, at, at_secret]):
        raise RuntimeError(
            "Faltan credenciales de X. Configura X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN y X_ACCESS_SECRET en el .env o conéctalas desde /canales."
        )
    return OAuth1(api_key, api_secret, at, at_secret)


def _media_upload_chunked(video_path: str, auth) -> str:
    """Sube un video a X en chunks y devuelve el media_id."""
    import requests

    file_size = Path(video_path).stat().st_size
    chunk_size = 5 * 1024 * 1024  # 5 MB

    # INIT
    r = requests.post(UPLOAD_URL, auth=auth, data={
        "command": "INIT",
        "total_bytes": file_size,
        "media_type": "video/mp4",
        "media_category": "tweet_video",
    })
    r.raise_for_status()
    media_id = r.json()["media_id_string"]

    # APPEND
    with open(video_path, "rb") as f:
        segment = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            r2 = requests.post(UPLOAD_URL, auth=auth, data={
                "command": "APPEND",
                "media_id": media_id,
                "segment_index": segment,
            }, files={"media": chunk})
            r2.raise_for_status()
            segment += 1

    # FINALIZE
    r3 = requests.post(UPLOAD_URL, auth=auth, data={
        "command": "FINALIZE",
        "media_id": media_id,
    })
    r3.raise_for_status()
    info = r3.json()

    # Polling if processing_info present
    state = (info.get("processing_info") or {}).get("state", "succeeded")
    while state not in ("succeeded", "failed"):
        wait = (info.get("processing_info") or {}).get("check_after_secs", 5)
        print(f"[X] Procesando video… ({state}, espera {wait}s)")
        time.sleep(wait)
        r4 = requests.get(UPLOAD_URL, auth=auth, params={
            "command": "STATUS",
            "media_id": media_id,
        })
        r4.raise_for_status()
        info = r4.json()
        state = (info.get("processing_info") or {}).get("state", "succeeded")

    if state == "failed":
        err = (info.get("processing_info") or {}).get("error", {})
        raise RuntimeError(f"X rechazó el video: {err.get('message', 'error desconocido')}")

    return media_id


def subir_video(video_path: str, texto: str = "") -> dict:
    """
    Sube un vídeo a X y publica el tweet.

    Args:
        video_path: Ruta absoluta al archivo MP4 (máx. ~512 MB, 2:20 min).
        texto:      Texto del tweet (máx. 280 chars).

    Returns:
        {"tweet_id": str, "url": str}
    """
    import requests

    auth = _get_auth()

    print(f"[X] Subiendo video '{Path(video_path).name}'…")
    media_id = _media_upload_chunked(video_path, auth)
    print(f"[X] Media subida: {media_id}")

    tweet_body: dict = {"media": {"media_ids": [media_id]}}
    if texto:
        tweet_body["text"] = texto[:280]

    r = requests.post(TWEET_URL, auth=auth, json=tweet_body)
    if not r.ok:
        try:
            err_data = r.json()
        except Exception:
            err_data = {}
        raise RuntimeError(_x_error_message(type("E", (), {"response": r})()))

    data = r.json().get("data", {})
    tweet_id = data.get("id", "")
    url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "https://x.com"
    print(f"[X] Tweet publicado: {url}")
    return {"tweet_id": tweet_id, "url": url}


def publicar_tweet(texto: str) -> dict:
    """Publica un tweet de texto (sin media)."""
    import requests
    auth = _get_auth()
    r = requests.post(TWEET_URL, auth=auth, json={"text": texto[:280]})
    if not r.ok:
        try:
            err_data = r.json()
        except Exception:
            err_data = {}
        raise RuntimeError(_x_error_message(type("E", (), {"response": r})()))
    data = r.json().get("data", {})
    tweet_id = data.get("id", "")
    url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "https://x.com"
    return {"tweet_id": tweet_id, "url": url}


def verificar_credenciales() -> dict:
    try:
        import requests
        auth = _get_auth()
        r = requests.get("https://api.twitter.com/2/users/me", auth=auth)
        if r.ok:
            u = r.json().get("data", {})
            return {"ok": True, "username": u.get("username", "usuario")}
        return {"ok": False, "motivo": r.text}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}
