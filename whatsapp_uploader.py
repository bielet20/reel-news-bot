"""
whatsapp_uploader.py
Cliente HTTP para el sidecar Node.js (wa_service) que gestiona WhatsApp Web.
"""
import os
import requests

WA_SERVICE_URL = os.environ.get("WA_SERVICE_URL", "http://whatsapp:3001")


def subir_status(video_path: str, caption: str = "") -> dict:
    """Envía un video como WhatsApp Status a través del sidecar.

    Args:
        video_path: ruta local al archivo de video
        caption: texto del estado (opcional)

    Returns:
        dict con la respuesta del sidecar
    """
    resp = requests.post(
        f"{WA_SERVICE_URL}/send-status",
        json={"video_path": video_path, "caption": caption},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def enviar_mensaje(texto: str, chat_id: str = None) -> dict:
    """Envía un mensaje de texto a través del sidecar WhatsApp.

    chat_id: número en formato internacional sin + (ej: 34612345678@c.us)
             o ID de grupo (XXXXX@g.us). Si None, usa WA_DEFAULT_CHAT_ID.
    """
    payload: dict = {"texto": texto}
    if chat_id:
        payload["chat_id"] = chat_id
    resp = requests.post(f"{WA_SERVICE_URL}/send-message", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_qr() -> str:
    """Obtiene el QR de vinculación como string base64.

    Returns:
        string base64 "data:image/png;base64,..."
    """
    resp = requests.get(f"{WA_SERVICE_URL}/qr", timeout=10)
    resp.raise_for_status()
    return resp.json().get("qr", "")


def get_status() -> dict:
    """Obtiene el estado de conexión del sidecar WhatsApp."""
    try:
        resp = requests.get(f"{WA_SERVICE_URL}/status", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"connected": False, "ready": False, "error": "Sidecar no disponible"}


def get_channels() -> list:
    """Lista los canales de WhatsApp (newsletters) del usuario conectado."""
    resp = requests.get(f"{WA_SERVICE_URL}/channels", timeout=10)
    resp.raise_for_status()
    return resp.json()


def find_channel_by_url(url: str) -> list:
    """Busca un canal de WhatsApp por su URL de invitación.

    Returns lista de canales con {jid, name, invite_link, exact},
    donde exact=True indica coincidencia con el código de la URL.
    """
    resp = requests.post(f"{WA_SERVICE_URL}/find-channel", json={"url": url}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def subir_canal(video_path: str, caption: str = "", channel_jid: str = None) -> dict:
    """Envía un vídeo al canal de WhatsApp configurado.

    Args:
        video_path: ruta local al archivo .mp4
        caption: texto que acompaña al vídeo (opcional)
        channel_jid: JID del canal (XXXXXXXXXX@newsletter); si None usa WA_CHANNEL_JID

    Returns:
        {"ok": True, "channel_jid": str}
    """
    payload: dict = {"video_path": video_path, "caption": caption}
    if channel_jid:
        payload["channel_jid"] = channel_jid
    resp = requests.post(f"{WA_SERVICE_URL}/send-channel", json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()
