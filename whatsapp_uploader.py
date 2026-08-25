"""
whatsapp_uploader.py
Cliente HTTP para el sidecar Node.js (wa_service) que gestiona WhatsApp Web.
"""
import requests

WA_SERVICE_URL = "http://localhost:3001"


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


def get_qr() -> str:
    """Obtiene el QR de vinculación como string base64.

    Returns:
        string base64 "data:image/png;base64,..."
    """
    resp = requests.get(f"{WA_SERVICE_URL}/qr", timeout=10)
    resp.raise_for_status()
    return resp.json().get("qr", "")


def get_status() -> dict:
    """Obtiene el estado de conexión del sidecar WhatsApp.

    Returns:
        {"connected": bool, "ready": bool}
    """
    try:
        resp = requests.get(f"{WA_SERVICE_URL}/status", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"connected": False, "ready": False, "error": "Sidecar no disponible"}
