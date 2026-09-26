"""
llm_local.py
Modelo de lenguaje LOCAL (LM Studio del host) para todo el proyecto, y el
interruptor de IA en la nube.

La app produce en local: guiones, selección de noticias, títulos y miniaturas
usan LM Studio. Claude / Gemini / Groq solo se usan si IA_NUBE=1 en el .env
(desactivado por defecto: son de pago o servicios externos).

Config:
  LLM_BASE_URL    (def. http://host.docker.internal:1234/v1 — desde Docker;
                   "localhost" dentro del contenedor es el propio contenedor)
  LMSTUDIO_MODEL  (def. qwen/qwen3-8b)
  IA_NUBE=1       permite Claude/Gemini/Groq como reserva
"""
import os
import re

import requests

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://host.docker.internal:1234/v1").rstrip("/")
LLM_MODEL = os.getenv("LMSTUDIO_MODEL", "qwen/qwen3-8b")


def nube_permitida() -> bool:
    return os.environ.get("IA_NUBE", "0").strip().lower() in ("1", "true", "si", "sí", "yes")


def _sin_razonamiento(texto: str) -> str:
    """Qwen3 y similares devuelven <think>…</think> antes de la respuesta."""
    texto = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    return texto.strip()


def completar(prompt: str, max_tokens: int = 2500, temperature: float = 0.7,
              system: str | None = None, timeout: float = 300) -> str:
    """Respuesta de LM Studio. Lanza RuntimeError si no responde o viene vacía.

    Se añade /no_think (interruptor de Qwen3): sin él, el modelo gasta los
    tokens razonando y a veces devuelve el contenido vacío."""
    mensajes = []
    if system:
        mensajes.append({"role": "system", "content": system})
    mensajes.append({"role": "user", "content": f"{prompt}\n/no_think"})
    try:
        r = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            json={"model": LLM_MODEL, "messages": mensajes,
                  "max_tokens": max_tokens, "temperature": temperature},
            timeout=timeout,
        )
        r.raise_for_status()
        texto = _sin_razonamiento(r.json()["choices"][0]["message"]["content"])
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"LM Studio no disponible en {LLM_BASE_URL}: {e}") from e
    if not texto:
        raise RuntimeError("LM Studio devolvió una respuesta vacía")
    return texto


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
