"""
llm_local.py
Modelo de lenguaje LOCAL (LM Studio del host) para todo el proyecto, y el
interruptor de IA en la nube.

La app produce el texto en Grok cuando LLM_PROVEEDOR=grok: un puente en el PC
(scripts/grok_puente.py) llama a grok.exe con la sesión ya iniciada. Si ese
puente no responde, se usa LM Studio. Claude / Gemini / Groq solo entran si
IA_NUBE=1 en el .env (desactivado por defecto).

Config:
  LLM_PROVEEDOR   grok | lmstudio (def. lmstudio)
  GROK_BRIDGE_URL (def. http://host.docker.internal:12434/v1)
  GROK_PUENTE_TOKEN  secreto compartido con el puente
  XAI_MODEL       (def. grok-4.7)
  LLM_BASE_URL    LM Studio (def. http://host.docker.internal:1234/v1)
  LMSTUDIO_MODEL  (def. qwen/qwen3-8b)
  IA_NUBE=1       permite Claude/Gemini/Groq como reserva
"""
import os
import re

import requests

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://host.docker.internal:1234/v1").rstrip("/")
LLM_MODEL = os.getenv("LMSTUDIO_MODEL", "qwen/qwen3-8b")
GROK_BRIDGE_URL = os.getenv("GROK_BRIDGE_URL", "http://host.docker.internal:12434/v1").rstrip("/")
GROK_MODEL = os.getenv("XAI_MODEL", "grok-4.7")


def usar_grok() -> bool:
    return os.environ.get("LLM_PROVEEDOR", "").strip().lower() in ("grok", "xai")


def _cabeceras_puente() -> dict:
    token = os.environ.get("GROK_PUENTE_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def nube_permitida() -> bool:
    return os.environ.get("IA_NUBE", "0").strip().lower() in ("1", "true", "si", "sí", "yes")


def _sin_razonamiento(texto: str) -> str:
    """Qwen3 y similares devuelven <think>…</think> antes de la respuesta."""
    texto = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    return texto.strip()


def _post_chat(base_url: str, model: str, mensajes: list, max_tokens: int,
               temperature: float, timeout: float, headers: dict | None = None) -> str:
    r = requests.post(
        f"{base_url}/chat/completions",
        json={"model": model, "messages": mensajes,
              "max_tokens": max_tokens, "temperature": temperature},
        headers=headers or {},
        timeout=timeout,
    )
    r.raise_for_status()
    texto = _sin_razonamiento(r.json()["choices"][0]["message"]["content"])
    if not texto:
        raise RuntimeError("respuesta vacía")
    return texto


def completar_grok(prompt: str, max_tokens: int = 2500, temperature: float = 0.7,
                   system: str | None = None, timeout: float = 300) -> str:
    """Una respuesta de Grok a través del puente local. No llama a LM Studio."""
    if not usar_grok():
        raise RuntimeError("LLM_PROVEEDOR no es grok")
    mensajes = []
    if system:
        mensajes.append({"role": "system", "content": system})
    mensajes.append({"role": "user", "content": prompt})
    try:
        return _post_chat(GROK_BRIDGE_URL, GROK_MODEL, mensajes, max_tokens,
                          temperature, timeout, _cabeceras_puente())
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Grok no disponible en {GROK_BRIDGE_URL}: {e}") from e


def completar(prompt: str, max_tokens: int = 2500, temperature: float = 0.7,
              system: str | None = None, timeout: float = 300) -> str:
    """Respuesta de Grok si está configurado, y si no de LM Studio.

    A LM Studio se le añade /no_think (interruptor de Qwen3): sin él, el modelo
    gasta los tokens razonando y a veces devuelve el contenido vacío. Grok no
    usa esa marca."""
    errores = []
    if usar_grok():
        try:
            return completar_grok(prompt, max_tokens, temperature, system, timeout)
        except Exception as e:  # noqa: BLE001
            errores.append(str(e))
    mensajes = []
    if system:
        mensajes.append({"role": "system", "content": system})
    mensajes.append({"role": "user", "content": f"{prompt}\n/no_think"})
    try:
        return _post_chat(LLM_BASE_URL, LLM_MODEL, mensajes, max_tokens,
                          temperature, timeout)
    except Exception as e:  # noqa: BLE001
        errores.append(f"LM Studio no disponible en {LLM_BASE_URL}: {e}")
    raise RuntimeError("; ".join(errores))


class LLMNoDisponible(RuntimeError):
    """El LM Studio del Mac no responde ni tras intentar despertarlo."""


CONTROL_CENTER_URL = os.getenv("CONTROL_CENTER_URL", "http://host.docker.internal:8090").rstrip("/")


def llm_studio_responde(timeout: float = 5) -> bool:
    try:
        return requests.get(f"{LLM_BASE_URL}/models", timeout=timeout).ok
    except Exception:  # noqa: BLE001
        return False


def grok_responde(timeout: float = 4) -> bool:
    if not usar_grok():
        return False
    try:
        return requests.get(f"{GROK_BRIDGE_URL}/models", headers=_cabeceras_puente(),
                            timeout=timeout).ok
    except Exception:  # noqa: BLE001
        return False


def llm_responde(timeout: float = 5) -> bool:
    if grok_responde(timeout):
        return True
    return llm_studio_responde(timeout)


def asegurar_llm(log=print) -> None:
    """Antes de escribir un guion: Grok (si está configurado) o, si no responde,
    el LM Studio del Mac. Si el Mac tampoco responde, pide al Centro de Control
    que lo despierte. Si sigue sin haber IA, lanza LLMNoDisponible: mejor avisar
    que hacer un reel flojo con la plantilla de emergencia."""
    if llm_responde():
        return
    if usar_grok():
        log(f"   [llm] Grok no responde en {GROK_BRIDGE_URL}.")
    log(f"   [llm] LM Studio no responde en {LLM_BASE_URL}; intentando despertar el Mac...")
    msg = ""
    try:
        r = requests.post(f"{CONTROL_CENTER_URL}/api/mac/despertar", timeout=260)
        msg = (r.json() or {}).get("msg", "")
    except Exception as e:  # noqa: BLE001
        msg = f"Centro de Control no disponible ({e})"
    log(f"   [llm] {msg}")
    if llm_responde(timeout=10):
        return
    extra = ""
    if usar_grok():
        extra = (f"Tampoco responde el puente de Grok ({GROK_BRIDGE_URL}). "
                 "Arranca scripts\\Iniciar-Grok.bat en el PC. ")
    raise LLMNoDisponible(
        extra + "El LM Studio del Mac no responde y no se ha podido despertar "
        f"({msg or 'sin detalle'}). Comprueba que el Mac está encendido y "
        "conectado a Tailscale y vuelve a intentarlo. No se ha hecho el reel "
        "para no publicar un guion de baja calidad.")


def liberar_gpu_para_video() -> bool:
    """Descarga el modelo de LM Studio antes de generar imagen o vídeo en ComfyUI.

    Con el LLM cargado (~5 GB) ComfyUI se queda sin VRAM y tiene que mover
    modelos a disco: una imagen de Flux schnell pasó de segundos a 5 min.
    Lo pide al Centro de Control del AI Studio; LM Studio sigue en marcha y
    recarga el modelo solo en la siguiente petición de texto."""
    try:
        from comfy_video_builder import liberar_lm_studio_vram
        ok = liberar_lm_studio_vram()
    except Exception:  # noqa: BLE001
        ok = False
    print(f"   [gpu] LM Studio {'descargado' if ok else 'no se pudo descargar (¿Centro de Control apagado?)'} "
          "antes de usar ComfyUI")
    return ok
