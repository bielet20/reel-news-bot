"""
telegram_uploader.py
Sube videos a un canal/chat de Telegram usando la Bot API directamente.

Nota sobre Stories: la Bot API de Telegram no expone un endpoint oficial para
publicar Stories de bots. Las Stories sólo están disponibles para cuentas
personales a través de TDLib. Como alternativa, subir_story() envía el video
al chat configurado con protect_content=True, que evita el reenvío y el
guardado del contenido, siendo el comportamiento más cercano posible con la API
pública de bots.
"""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from accounts_manager import load_token

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _get_credentials() -> tuple[str, str]:
    token_data = load_token("telegram")
    if token_data:
        bot_token = token_data.get("bot_token", "")
        chat_id = token_data.get("chat_id", "")
    else:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID no configurado")
    return bot_token, chat_id


def subir_video(video_path: str, caption: str = "", chat_id: str = None) -> dict:
    """Envía un video a un chat/canal de Telegram.

    Args:
        video_path: ruta local al archivo .mp4
        caption: texto que acompaña al video (opcional)
        chat_id: ID del chat destino; si None usa el valor configurado

    Returns:
        {"ok": True, "message_id": int}
    """
    bot_token, default_chat_id = _get_credentials()
    target = chat_id or default_chat_id

    url = _BASE.format(token=bot_token, method="sendVideo")
    with open(video_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": target, "caption": caption, "supports_streaming": "true"},
            files={"video": (Path(video_path).name, f, "video/mp4")},
            timeout=300,
        )

    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data.get('description', data)}")

    message_id = data["result"]["message_id"]
    return {"ok": True, "message_id": message_id}


def subir_story(video_path: str) -> dict:
    """Publica un video como contenido protegido en el canal configurado.

    La Bot API no tiene endpoint de Stories para bots. Este método sube el
    video con protect_content=True, que impide reenviarlo o guardarlo,
    aproximándose al comportamiento de una Story privada.

    Returns:
        {"ok": True, "message_id": int}
    """
    bot_token, chat_id = _get_credentials()

    url = _BASE.format(token=bot_token, method="sendVideo")
    with open(video_path, "rb") as f:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "supports_streaming": "true",
                "protect_content": "true",
            },
            files={"video": (Path(video_path).name, f, "video/mp4")},
            timeout=300,
        )

    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data.get('description', data)}")

    message_id = data["result"]["message_id"]
    return {"ok": True, "message_id": message_id}
