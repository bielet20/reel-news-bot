"""
comfy_video_builder.py
Genera el FONDO de cada sección del Montaje como un vídeo IA relacionado con la
letra, usando el ComfyUI local del usuario (E:\\AI-Studio, RTX 5070 Ti).

Pipeline por sección:
  1. Un LLM (LM Studio local -> Claude -> Gemini) lee la letra completa y
     escribe un guion visual: un `style_prefix` de dirección de arte coherente
     + una escena por sección (image_prompt para Flux + motion_prompt para Wan).
  2. ComfyUI: Flux genera un frame fijo -> Wan2.2 I2V (LoRA Lightning, 4 pasos)
     lo anima ~4s -> se encadenan hasta MAX_REAL_SEGMENTS renders y el resto de
     la duración de la sección se cubre estirando a cámara lenta (nunca congela).
  3. (opcional, "voz femenina") El clip se pasa por LatentSync con el audio de
     esa sección para que la persona en pantalla mueva los labios con la letra.

Todo el intercambio con ComfyUI es HTTP; el backend corre en Docker y llega al
host por `host.docker.internal`. Si ComfyUI no responde o algo falla, la función
lanza una excepción y el que llama (lyric_video_builder) cae a la imagen fija.

Port adaptado de E:\\AI-Studio\\tools\\EstudioIA\\videoclip.py (que el contenedor
no puede importar: no ve la unidad E:). El ComfyUI del usuario NO tiene
VideoHelperSuite, así que se usan los nodos de vídeo nativos del core
(LoadVideo / GetVideoComponents / CreateVideo / SaveVideo), igual que videoclip.py.
"""
import json
import math
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import requests

# ── Config (todo override por variable de entorno) ────────────────────────────

COMFY_URL = os.getenv("COMFY_URL", "http://host.docker.internal:8188").rstrip("/")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://host.docker.internal:1234/v1").rstrip("/")
LLM_MODEL = os.getenv("LMSTUDIO_MODEL", "qwen/qwen3-8b")

# Centro de Control de AI Studio (E:\\AI-Studio\\tools\\ControlCenter, puerto 8090):
# panel del host que sabe arrancar/parar ComfyUI y LM Studio. Si responde, el
# Montaje puede ofrecer un botón "Arrancar" en vez de pedir abrir un .bat a mano.
CONTROL_CENTER_URL = os.getenv(
    "CONTROL_CENTER_URL", "http://host.docker.internal:8090").rstrip("/")

FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_BIN", "ffprobe")

# ── Text-to-video (Wan2.2-T2V + LoRA Lightning T2V, 4 pasos) ──────────────────
# Los modelos T2V no venían con la instalación (solo los I2V); se descargan a
# models/unet y models/loras/Wan2.2-Lightning-T2V (ver scripts/descargar_wan_t2v.sh).
WAN22_T2V_HIGH_UNET = os.getenv("COMFY_WAN_T2V_HIGH", "Wan2.2-T2V-A14B-HighNoise-Q3_K_S.gguf")
WAN22_T2V_LOW_UNET = os.getenv("COMFY_WAN_T2V_LOW", "Wan2.2-T2V-A14B-LowNoise-Q3_K_S.gguf")
WAN22_T2V_LORA_HIGH = os.getenv("COMFY_WAN_T2V_LORA_HIGH", "Wan2.2-Lightning-T2V\\high_noise_model.safetensors")
WAN22_T2V_LORA_LOW = os.getenv("COMFY_WAN_T2V_LORA_LOW", "Wan2.2-Lightning-T2V\\low_noise_model.safetensors")

# ── Image-to-video (Wan2.2-I2V + LoRA Lightning I2V) — para encadenar segmentos ─
WAN22_HIGH_NOISE_UNET = os.getenv("COMFY_WAN_HIGH", "Wan2.2-I2V-A14B-HighNoise-Q3_K_S.gguf")
WAN22_LOW_NOISE_UNET = os.getenv("COMFY_WAN_LOW", "Wan2.2-I2V-A14B-LowNoise-Q3_K_S.gguf")
WAN22_LORA_HIGH_NOISE = os.getenv("COMFY_WAN_LORA_HIGH", "Wan2.2-Lightning\\high_noise_model.safetensors")
WAN22_LORA_LOW_NOISE = os.getenv("COMFY_WAN_LORA_LOW", "Wan2.2-Lightning\\low_noise_model.safetensors")
WAN_CLIP = os.getenv("COMFY_WAN_CLIP", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
WAN_VAE = os.getenv("COMFY_WAN_VAE", "wan_2.1_vae.safetensors")
WAN_CLIP_VISION = os.getenv("COMFY_WAN_CLIP_VISION", "clip_vision_h.safetensors")

# ── Fotograma inicial (Flux) ─────────────────────────────────────────────────
# El primer segmento de cada sección arranca de una imagen fija generada con
# Flux y se anima con Wan2.2-I2V (igual que EstudioIA/videoclip.py, que es el
# pipeline probado). El texto->vídeo puro de Wan2.2 (WanImageToVideo sin
# start_image) salía NEGRO con estos GGUF Q3, así que ya no se usa.
FLUX_CHECKPOINT = os.getenv("COMFY_FLUX_CKPT", "flux1-dev-fp8.safetensors")
FLUX_STEPS = int(os.getenv("COMFY_FLUX_STEPS", "25"))
FLUX_GUIDANCE = float(os.getenv("COMFY_FLUX_GUIDANCE", "3.5"))

# Resolución nativa de Wan 480p. Horizontal 16:9 por defecto (832x480); el
# builder pasa width/height según el formato elegido y luego reescala al canvas.
VIDEO_W = int(os.getenv("COMFY_VIDEO_W", "832"))
VIDEO_H = int(os.getenv("COMFY_VIDEO_H", "480"))
VIDEO_FPS = int(os.getenv("COMFY_VIDEO_FPS", "16"))
VIDEO_FRAMES = int(os.getenv("COMFY_VIDEO_FRAMES", "65"))  # ~4s por render
WAN_LIGHTNING_STEPS = 4
WAN_LIGHTNING_SPLIT = 2
WAN_LIGHTNING_SHIFT = 5.0
WAN_LIGHTNING_CFG = 1.0
# Cuántos renders reales de ~4s se encadenan para cubrir una sección larga
# (cada uno arranca del último frame del anterior). Sin cámara lenta: es vídeo
# de verdad de principio a fin. Tope de seguridad para no dispararse en secciones
# de 30s+.
MAX_REAL_SEGMENTS_PER_SCENE = int(os.getenv("COMFY_MAX_REAL_SEGMENTS", "8"))

LATENTSYNC_STEPS = int(os.getenv("COMFY_LATENTSYNC_STEPS", "20"))
LATENTSYNC_LIPS_EXPRESSION = float(os.getenv("COMFY_LATENTSYNC_LIPS", "1.5"))

# ── LTX-Video 2B (local, rápido) ─────────────────────────────────────────────
# Modelo GGUF ya instalado; faltan text encoder (t5xxl) y VAE — ver
# scripts/descargar_ltx.sh.
LTX_UNET = os.getenv("COMFY_LTX_UNET", "ltx-video-2b-v0.9-Q6_K.gguf")
LTX_VAE = os.getenv("COMFY_LTX_VAE", "LTX-Video-VAE-BF16.safetensors")
LTX_T5 = os.getenv("COMFY_LTX_T5", "t5xxl_fp8_e4m3fn.safetensors")
LTX_STEPS = int(os.getenv("COMFY_LTX_STEPS", "30"))
LTX_CFG = float(os.getenv("COMFY_LTX_CFG", "3.0"))
LTX_FPS = int(os.getenv("COMFY_LTX_FPS", "24"))
# LTX genera clips largos de una vez (hasta ~8n+1 frames); cubre secciones
# largas con pocas llamadas.
LTX_MAX_FRAMES = int(os.getenv("COMFY_LTX_MAX_FRAMES", "185"))  # ~7.7s @24fps

# ── fal.ai (API externa, de pago) ────────────────────────────────────────────
FAL_KEY = os.getenv("FAL_KEY", "")
FAL_MODEL = os.getenv("FAL_MODEL", "fal-ai/minimax/hailuo-02/standard/text-to-video")

WAN_NEGATIVE = (
    "低画质,模糊,静止,字幕,水印,变形,画面抖动,过曝,欠曝,"
    "low quality, blurry, static, subtitles, watermark, distorted, "
    "deformed, extra limbs, worst quality, jpeg artifacts"
)

LTX_NEGATIVE = (
    "low quality, worst quality, deformed, distorted, disfigured, "
    "motion smear, motion artifacts, blurry, static, watermark, text"
)


# ── Disponibilidad ───────────────────────────────────────────────────────────

def comfy_disponible(timeout: float = 4.0) -> bool:
    """True si el ComfyUI local responde. Se usa para decidir rápido si merece
    la pena intentar el camino de vídeo IA o ir directo al fallback de imagen."""
    try:
        r = requests.get(f"{COMFY_URL}/system_stats", timeout=timeout)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def control_center_disponible(timeout: float = 3.0) -> bool:
    """True si el Centro de Control del host (AI Studio, :8090) responde. Si lo
    hace, el Montaje puede arrancar ComfyUI/LM Studio con un botón."""
    try:
        r = requests.get(f"{CONTROL_CENTER_URL}/api/status", timeout=timeout)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def liberar_lm_studio_vram() -> bool:
    """Pide al Centro de Control que descargue el modelo de LM Studio (libera
    ~5 GB de VRAM). Se llama tras escribir el guion visual: el resto del montaje
    solo necesita ComfyUI, y LM Studio ocupando VRAM es la causa nº1 de que
    ComfyUI se quede sin memoria a mitad y todo caiga a imagen fija. El servidor
    de LM Studio sigue en pie y recarga solo en la siguiente petición."""
    if not control_center_disponible():
        return False
    try:
        r = requests.post(f"{CONTROL_CENTER_URL}/api/service/lmstudio/unload", timeout=30)
        return bool(r.ok and r.json().get("ok"))
    except (requests.exceptions.RequestException, ValueError):
        return False


def arrancar_via_control_center(servicios: list[str], timeout: float = 180.0) -> dict:
    """Pide al Centro de Control que encienda los servicios indicados
    ('comfyui', 'lmstudio'). Bloqueante: el panel no responde hasta que el
    servicio pasa su chequeo de salud o agota su propio timeout."""
    resultados = {}
    for key in servicios:
        try:
            r = requests.post(f"{CONTROL_CENTER_URL}/api/service/{key}/start",
                              timeout=timeout)
            data = r.json()
            resultados[key] = {"ok": bool(data.get("ok")), "msg": data.get("msg", "")}
        except requests.exceptions.RequestException as e:
            resultados[key] = {"ok": False, "msg": f"sin respuesta del Centro de Control: {e}"}
    return resultados


_OI_CACHE: dict = {}


def _oi_opciones(node: str, param: str, timeout: float = 8.0) -> list[str]:
    """Valores válidos que ComfyUI acepta para un parámetro de un nodo (leídos de
    /object_info, la fuente autoritativa — el endpoint /models/<carpeta> usa
    nombres de carpeta que cambian entre versiones)."""
    key = (node, param)
    if key in _OI_CACHE:
        return _OI_CACHE[key]
    try:
        oi = requests.get(f"{COMFY_URL}/object_info/{node}", timeout=timeout).json()
        it = oi[node]["input"]
        for grp in ("required", "optional"):
            if param in it.get(grp, {}):
                v = it[grp][param][0]
                res = [str(x) for x in v] if isinstance(v, list) else []
                _OI_CACHE[key] = res
                return res
    except Exception:  # noqa: BLE001
        pass
    _OI_CACHE[key] = []
    return []


def _base(nombre: str) -> str:
    return nombre.replace("\\", "/").split("/")[-1]


def _tiene(nombre: str, lista: list[str]) -> bool:
    b = _base(nombre)
    return any(_base(x) == b for x in lista)


def verificar_herramientas() -> dict:
    """Estado detallado de lo que hace falta para generar vídeo, para el
    pre-chequeo del Montaje. {comfy, lm_studio, providers:[...], problemas:[...]}"""
    _OI_CACHE.clear()
    comfy = comfy_disponible()
    lm = False
    try:
        lm = requests.get(f"{LLM_BASE_URL}/models", timeout=4).status_code == 200
    except Exception:  # noqa: BLE001
        lm = False

    unet = _oi_opciones("UnetLoaderGGUF", "unet_name") if comfy else []
    vae = _oi_opciones("VAELoader", "vae_name") if comfy else []
    clip = _oi_opciones("CLIPLoader", "clip_name") if comfy else []
    lora = _oi_opciones("LoraLoaderModelOnly", "lora_name") if comfy else []
    ckpt = _oi_opciones("CheckpointLoaderSimple", "ckpt_name") if comfy else []

    # El pipeline es Flux (fotograma) -> Wan2.2-I2V (animación). No se usa T2V.
    wan_falta = [m for m in (WAN22_HIGH_NOISE_UNET, WAN22_LOW_NOISE_UNET) if not _tiene(m, unet)] \
        + [m for m in (WAN22_LORA_HIGH_NOISE, WAN22_LORA_LOW_NOISE) if not _tiene(m, lora)] \
        + ([WAN_CLIP] if not _tiene(WAN_CLIP, clip) else []) \
        + ([WAN_VAE] if not _tiene(WAN_VAE, vae) else []) \
        + ([FLUX_CHECKPOINT] if not _tiene(FLUX_CHECKPOINT, ckpt) else [])
    ltx_falta = ([LTX_UNET] if not _tiene(LTX_UNET, unet) else []) \
        + ([LTX_VAE] if not _tiene(LTX_VAE, vae) else []) \
        + ([LTX_T5] if not _tiene(LTX_T5, clip) else [])

    wan_ok = comfy and not wan_falta
    ltx_ok = comfy and not ltx_falta

    providers = [
        {"id": "wan22", "label": "Wan 2.2 (Flux + I2V, local)", "disponible": bool(wan_ok),
         "nota": "Local, gratis. Mejor calidad open. Cada sección tarda minutos."
                 if wan_ok else ("Arranca ComfyUI (E:\\AI-Studio → Iniciar-ComfyUI.bat)"
                                 if not comfy else f"Faltan modelos: {', '.join(_base(m) for m in wan_falta)}")},
        {"id": "ltx", "label": "LTX-Video 2B (local, rápido)", "disponible": bool(ltx_ok),
         "nota": "Local, gratis. Rápido, algo menos coherente que Wan."
                 if ltx_ok else ("Arranca ComfyUI" if not comfy else
                                 f"Faltan: {', '.join(_base(m) for m in ltx_falta)} — scripts/descargar_ltx.sh")},
        {"id": "fal", "label": "API externa (fal.ai)", "disponible": bool(FAL_KEY),
         "nota": f"De pago (~$2–3/videoclip). Modelo: {FAL_MODEL}."
                 if FAL_KEY else "Pon FAL_KEY en .env (cuenta en fal.ai) para activarlo."},
        {"id": "imagen", "label": "Imagen fija (Pollinations)", "disponible": True,
         "nota": "Sin ComfyUI ni coste. Imagen IA por sección con Ken Burns (no es vídeo real)."},
    ]

    problemas = []
    if not comfy:
        problemas.append("ComfyUI no responde en " + COMFY_URL + " — arráncalo con E:\\AI-Studio\\Iniciar-ComfyUI.bat")
    if not lm:
        problemas.append("LM Studio no responde en " + LLM_BASE_URL + " (se usará Claude/Gemini para el guion si hay API key)")
    if comfy and wan_falta:
        problemas.append("Wan 2.2 (Flux+I2V): faltan " + ", ".join(_base(m) for m in wan_falta))

    return {"comfy": comfy, "lm_studio": lm, "providers": providers,
            "problemas": problemas, "control_center": control_center_disponible()}


def providers_disponibles() -> list[dict]:
    return verificar_herramientas()["providers"]


# ── Planificador de escenas (LLM) ────────────────────────────────────────────

def strip_think(text: str) -> str:
    """Los modelos 'thinking' (qwen3, deepseek-r1) meten un bloque
    <think>...</think> antes de la respuesta; lo quitamos."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


def _json_lenient(raw: str) -> dict:
    """json.loads con reparación de los errores típicos de un LLM:
    comas colgando, comillas simples, claves sin comillas, salida cortada."""
    blob = extract_json(raw)
    intentos = [blob]

    # comas colgando antes de } o ]
    intentos.append(re.sub(r",(\s*[}\]])", r"\1", blob))
    # comillas simples -> dobles (solo si no hay dobles, para no romper apóstrofos)
    if '"' not in blob and "'" in blob:
        intentos.append(re.sub(r"'", '"', blob))
    # claves sin comillas:  { foo:  ->  { "foo":
    intentos.append(re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', blob))
    # salida cortada: reequilibrar llaves/corchetes que falten al final
    abiertas = blob.count("{") - blob.count("}")
    cerradas = blob.count("[") - blob.count("]")
    if abiertas > 0 or cerradas > 0:
        recorte = re.sub(r",\s*$", "", blob.rstrip())
        intentos.append(recorte + "]" * max(0, cerradas) + "}" * max(0, abiertas))

    ultimo_err = None
    for cand in intentos:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError) as e:
            ultimo_err = e
    raise ultimo_err or ValueError("JSON ilegible")


def count_lines_per_section(lyrics: str) -> list[int]:
    """Cuenta líneas cantadas (no vacías, no etiquetas) por cada aparición de
    sección, en orden, para repartir la duración proporcionalmente."""
    counts: list[int] = []
    current = 0
    started = False
    for line in lyrics.split("\n"):
        line = line.strip()
        if re.fullmatch(r"\[[^\]]+\]", line):
            if started:
                counts.append(current)
            current = 0
            started = True
        elif line:
            current += 1
    if started:
        counts.append(current)
    return counts


def _llm_completion(system_prompt: str, user_prompt: str, max_tokens: int = 6000,
                    temperature: float = 0.8, json_mode: bool = False) -> str:
    """Escalera de LLM para planificar escenas. A diferencia de los helpers de
    summarizer.py (max_tokens=600, pensados para un guion corto) aquí hace falta
    espacio para un JSON con una escena por sección."""
    errores = []

    # 1) LM Studio local (gratis, sin internet) via host.docker.internal
    try:
        cuerpo = {
            "model": LLM_MODEL,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            cuerpo["response_format"] = {"type": "json_object"}
        r = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=cuerpo,
            timeout=300,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        if content and content.strip():
            return content
        errores.append("LM Studio: respuesta vacía")
    except Exception as e:  # noqa: BLE001
        errores.append(f"LM Studio: {e}")

    # 2) Claude (ANTHROPIC_API_KEY)
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if claude_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=claude_key)
            resp = client.messages.create(
                model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return resp.content[0].text
        except Exception as e:  # noqa: BLE001
            errores.append(f"Claude: {e}")

    # 3) Gemini (GEMINI_API_KEY, gratis)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={gemini_key}",
                json={
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.8},
                },
                timeout=120,
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:  # noqa: BLE001
            errores.append(f"Gemini: {e}")

    raise RuntimeError(
        "No hay ningún LLM disponible para planificar las escenas del videoclip "
        f"({'; '.join(errores)}). Arranca LM Studio o configura ANTHROPIC_API_KEY / GEMINI_API_KEY."
    )


_SYSTEM_PLAN = (
    "Eres un director de videoclips de IA. Te dan la letra de una canción (con "
    "secciones marcadas por etiquetas [Verso 1] [Estribillo] [Puente]... o "
    "separadas por líneas en blanco) y su estilo. Escribe el guion visual para "
    "un modelo de generación de vídeo local (Wan2.2), que solo entiende inglés y "
    "necesita descripciones concretas y cinematográficas (sujeto, entorno, "
    "iluminación, movimiento de cámara).\n"
    "El vídeo es HORIZONTAL 16:9: cada image_prompt compone en apaisado — "
    "planos cinematográficos, profundidad, el sujeto puede no estar centrado.\n"
    "Responde SIEMPRE con JSON válido, sin markdown ni texto fuera del JSON, con "
    "exactamente esta forma:\n"
    '{"style_prefix": "...", "scenes": [{"section": "verso", "image_prompt": "...", '
    '"motion_prompt": "..."}, ...]}\n'
    "Reglas:\n"
    "- \"style_prefix\": frase corta EN INGLÉS con la dirección de arte que se "
    "repite en TODAS las escenas para que el vídeo se vea coherente de principio "
    "a fin (paleta, época, técnica: p.ej. 'cinematic anamorphic film look, warm "
    "golden-hour palette, 35mm grain').\n"
    "- \"scenes\": una entrada por CADA sección de la letra, en el mismo orden. "
    "Si el estribillo se repite, hay una escena por repetición (pueden variar el "
    "encuadre manteniendo el estilo).\n"
    "- \"image_prompt\": la escena en inglés (sujeto, acción, entorno, luz, "
    "composición). Debe reflejar el CONTENIDO y la EMOCIÓN concretos de las "
    "líneas de esa sección, no ideas genéricas. Nada de texto ni letras en pantalla.\n"
    "- \"motion_prompt\": el movimiento y la cámara de esos segundos (p.ej. 'slow "
    "dolly-in, hair moves in the wind, dust drifts, handheld camera'), en inglés. "
    "Siempre debe haber movimiento visible — nunca una escena estática.\n"
    "- No incluyas nada fuera del JSON."
)

_SYSTEM_PLAN_MUJER = (
    "\n- IMPORTANTE: la voz que canta es una MUJER. En TODAS las escenas que "
    "tengan líneas cantadas aparece SIEMPRE LA MISMA mujer (fija su aspecto en "
    "el style_prefix: edad aproximada, color y largo de pelo, rasgos, vestuario) "
    "en primer plano o plano medio, CARA CLARAMENTE VISIBLE Y DE FRENTE, bien "
    "iluminada, mirando a cámara o casi — es la protagonista que canta la letra."
)

_SYSTEM_PLAN_HOMBRE = (
    "\n- IMPORTANTE: la voz que canta es un HOMBRE. En TODAS las escenas con "
    "líneas cantadas aparece SIEMPRE EL MISMO hombre (fija su aspecto en el "
    "style_prefix: edad, pelo, barba, rasgos, vestuario) en primer plano o plano "
    "medio, CARA CLARAMENTE VISIBLE Y DE FRENTE, bien iluminado, mirando a cámara "
    "o casi — es el protagonista que canta la letra."
)

_SYSTEM_PLAN_MIXTA = (
    "\n- IMPORTANTE: cantan un HOMBRE y una MUJER (dúo). Fija el aspecto de "
    "AMBOS en el style_prefix. En cada escena con líneas cantadas aparece la "
    "persona cuya voz lleva esa parte (si no está claro, los dos juntos), en "
    "primer plano o plano medio, CARA VISIBLE Y DE FRENTE, bien iluminada."
)


def plan_escenas(letra: str, artista: str, titulo: str, estilo_base: str,
                 voz_femenina: bool, dur_total: float,
                 voz_tipo: str = "") -> tuple[str, list[dict]]:
    """Devuelve (style_prefix, [ {section, image_prompt, motion_prompt,
    target_duration} ]). target_duration reparte dur_total proporcional al nº de
    líneas de cada sección (igual que lyric_video_builder).

    `voz_tipo` ∈ {"hombre","mujer","mixta",...} manda si viene; si no, se usa el
    bool `voz_femenina` de siempre."""
    if voz_tipo == "mixta":
        extra = _SYSTEM_PLAN_MIXTA
    elif voz_tipo == "hombre":
        extra = _SYSTEM_PLAN_HOMBRE
    elif voz_tipo == "mujer" or voz_femenina:
        extra = _SYSTEM_PLAN_MUJER
    else:
        extra = ""
    system = _SYSTEM_PLAN + extra
    user = (
        f"Canción: {titulo or '(sin título)'}\n"
        f"Artista: {artista or '(sin artista)'}\n"
        f"Estilo visual deseado: {estilo_base or 'cinemático'}\n"
        f"Duración total del audio: {dur_total:.0f} segundos\n\n"
        f"Letra:\n{letra}"
    )
    raw = strip_think(_llm_completion(system, user, temperature=0.35, json_mode=True)).strip()
    if not raw:
        raise RuntimeError("El LLM devolvió una respuesta vacía al planificar las escenas.")
    try:
        data = _json_lenient(raw)
    except (json.JSONDecodeError, ValueError) as e1:
        # Segundo intento: que el propio LLM arregle su JSON.
        print(f"[LyricVideo] guion: JSON inválido ({e1}); pido corrección al LLM…")
        reparado = strip_think(_llm_completion(
            "Devuelve ÚNICAMENTE el JSON corregido y válido, sin explicaciones, "
            "sin ```. Debe tener las claves style_prefix (string) y scenes (lista "
            "de objetos con section, image_prompt, motion_prompt).",
            f"Corrige este JSON:\n\n{raw}",
            temperature=0.0, json_mode=True,
        )).strip()
        try:
            data = _json_lenient(reparado)
        except (json.JSONDecodeError, ValueError) as e2:
            raise RuntimeError(
                f"El LLM no devolvió un guion en JSON válido ni tras pedir corrección "
                f"({e2}). Primeras líneas de lo que devolvió:\n{raw[:400]}"
            ) from e2

    # El modelo a veces devuelve la lista de escenas pelada, o bajo otra clave.
    if isinstance(data, list):
        data = {"scenes": data}
    style_prefix = (data.get("style_prefix") or data.get("style") or "").strip()
    scenes = (data.get("scenes") or data.get("escenas")
              or data.get("shots") or data.get("sections") or [])
    if not isinstance(scenes, list) or not scenes:
        raise RuntimeError("El LLM no devolvió ninguna escena.")

    section_lines = count_lines_per_section(letra)
    weights = [max(section_lines[i] if i < len(section_lines) else 1, 1) for i in range(len(scenes))]
    total_w = sum(weights) or 1
    for sc, w in zip(scenes, weights):
        sc["target_duration"] = max(2.0, dur_total * w / total_w)
        sc.setdefault("section", "")
        sc.setdefault("image_prompt", "")
        sc.setdefault("motion_prompt", "slow subtle camera move")
    return style_prefix, scenes


# ── Cliente ComfyUI ──────────────────────────────────────────────────────────

def comfy_upload_file(path: Path, content_type: str) -> str:
    """/upload/image de ComfyUI escribe el fichero tal cual en input/, sin mirar
    el tipo — sirve igual para subir vídeo o audio y que LoadVideo/LoadAudio los
    lean luego."""
    with open(path, "rb") as f:
        r = requests.post(
            f"{COMFY_URL}/upload/image",
            files={"image": (path.name, f, content_type)},
            data={"overwrite": "true"},
            timeout=300,
        )
    r.raise_for_status()
    return r.json()["name"]


def comfy_upload_image(path: Path) -> str:
    return comfy_upload_file(path, "image/png")


def comfy_queue(workflow: dict) -> str:
    client_id = uuid.uuid4().hex
    r = requests.post(
        f"{COMFY_URL}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI rechazó el workflow: {r.text[:800]}")
    return r.json()["prompt_id"]


def _prompt_en_cola(prompt_id: str) -> bool:
    """True si el prompt está corriendo o en espera en la cola de ComfyUI."""
    try:
        q = requests.get(f"{COMFY_URL}/queue", timeout=15).json()
        for grp in ("queue_running", "queue_pending"):
            for item in q.get(grp, []):
                # item = [num, prompt_id, prompt, extra, outputs]
                if len(item) > 1 and item[1] == prompt_id:
                    return True
    except requests.exceptions.RequestException:
        return True  # ante la duda, no lo demos por perdido
    return False


class MontajeCancelado(Exception):
    """El usuario paró la generación desde la app."""


def comfy_interrumpir() -> None:
    try:
        requests.post(f"{COMFY_URL}/interrupt", timeout=10)
    except requests.exceptions.RequestException:
        pass


def comfy_wait(prompt_id: str, timeout: float = 1800.0, poll_every: float = 2.0,
               should_cancel=None) -> dict:
    deadline = time.time() + timeout
    visto = False          # ¿lo hemos visto alguna vez en historia o cola?
    perdido = 0            # sondeos seguidos sin rastro (crash / reinicio)
    caido = 0              # sondeos seguidos sin poder contactar con ComfyUI
    while time.time() < deadline:
        if should_cancel and should_cancel():
            comfy_interrumpir()
            raise MontajeCancelado()
        try:
            r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=30)
            r.raise_for_status()
            data = r.json()
            caido = 0
        except requests.exceptions.RequestException:
            # ComfyUI puede tardar unos segundos mientras carga un checkpoint
            # grande; toleramos cortes breves. Pero si lleva ~90s sin responder
            # es que crasheó y no vuelve solo -> cortamos y caemos al fallback.
            caido += 1
            if caido >= 30:
                raise RuntimeError(
                    f"ComfyUI lleva ~{caido * poll_every:.0f}s sin responder "
                    f"(¿crasheó?); se abandona el prompt {prompt_id}."
                )
            time.sleep(poll_every)
            continue
        if prompt_id in data:
            entry = data[prompt_id]
            status = entry.get("status", {})
            if status.get("completed") is False and status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI falló generando: {json.dumps(status)[:800]}")
            if entry.get("outputs"):
                return entry["outputs"]
            visto = True
            perdido = 0
        elif _prompt_en_cola(prompt_id):
            visto = True
            perdido = 0
        else:
            # ni en historia ni en cola: o aún no ha entrado, o ComfyUI se
            # reinició y lo perdió. Si ya lo habíamos visto, cortamos rápido
            # para caer al fallback en vez de colgar hasta el timeout.
            perdido += 1
            if visto and perdido >= 8:
                raise RuntimeError(
                    f"ComfyUI perdió el prompt {prompt_id} (¿se reinició o crasheó?)."
                )
            if not visto and perdido >= 30:
                raise RuntimeError(
                    f"ComfyUI nunca encoló el prompt {prompt_id}."
                )
        time.sleep(poll_every)
    raise TimeoutError(f"ComfyUI no terminó el prompt {prompt_id} en {timeout:.0f}s")


def comfy_download(filename: str, subfolder: str, folder_type: str, dest: Path) -> None:
    r = requests.get(
        f"{COMFY_URL}/view",
        params={"filename": filename, "subfolder": subfolder, "type": folder_type},
        timeout=120,
    )
    r.raise_for_status()
    dest.write_bytes(r.content)


def _first_output(outputs: dict, node_id: str) -> dict:
    """SaveVideo/SaveImage exponen su resultado bajo la clave "images" aunque
    sea un vídeo (PreviewVideo.as_dict)."""
    node = outputs[node_id]
    items = node.get("images") or node.get("gifs") or node.get("videos") or []
    if not items:
        raise RuntimeError(f"El nodo {node_id} de ComfyUI no devolvió ningún fichero: {json.dumps(node)[:400]}")
    return items[0]


# ── Workflows ────────────────────────────────────────────────────────────────

def _wan_moe_sampler_nodes(high_unet: str, low_unet: str, lora_high: str, lora_low: str,
                            seed: int, latent_ref: list) -> dict:
    """Nodos comunes del sampler MoE Wan2.2 + LoRA Lightning (4 pasos, split 2/2,
    shift=5, cfg=1, euler/simple). `latent_ref` es [node, slot] del latente
    inicial (de WanImageToVideo, sirva o no de start_image). Devuelve el dict de
    nodos "10".."17"; el latente final decodificado sale de "17"."""
    return {
        "10": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": high_unet}},
        "11": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["10", 0], "lora_name": lora_high, "strength_model": 1.0}},
        "12": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["11", 0], "shift": WAN_LIGHTNING_SHIFT}},
        "13": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["12", 0], "positive": ["9", 0], "negative": ["9", 1],
            "latent_image": latent_ref, "add_noise": "enable", "noise_seed": seed,
            "steps": WAN_LIGHTNING_STEPS, "cfg": WAN_LIGHTNING_CFG, "sampler_name": "euler",
            "scheduler": "simple", "start_at_step": 0, "end_at_step": WAN_LIGHTNING_SPLIT,
            "return_with_leftover_noise": "enable",
        }},
        "14": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": low_unet}},
        "15": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["14", 0], "lora_name": lora_low, "strength_model": 1.0}},
        "16": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["15", 0], "shift": WAN_LIGHTNING_SHIFT}},
        "17": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["16", 0], "positive": ["9", 0], "negative": ["9", 1],
            "latent_image": ["13", 0], "add_noise": "disable", "noise_seed": seed,
            "steps": WAN_LIGHTNING_STEPS, "cfg": WAN_LIGHTNING_CFG, "sampler_name": "euler",
            "scheduler": "simple", "start_at_step": WAN_LIGHTNING_SPLIT,
            "end_at_step": WAN_LIGHTNING_STEPS, "return_with_leftover_noise": "disable",
        }},
    }


def build_flux_workflow(prompt: str, seed: int, width: int, height: int) -> dict:
    """Flux (dev fp8) genera el fotograma inicial de una sección. Port directo
    del workflow probado en EstudioIA/videoclip.py."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": FLUX_CHECKPOINT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "4": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": FLUX_GUIDANCE}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["3", 0],
            "latent_image": ["5", 0], "seed": seed, "steps": FLUX_STEPS,
            "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "reel_frame"}},
    }


def build_wan_i2v_workflow(image_filename: str, image_prompt: str, motion_prompt: str,
                            seed: int, width: int, height: int, length: int) -> dict:
    """Wan2.2 I2V MoE + LoRA Lightning (4 pasos). Se usa para ENCADENAR segmentos:
    arranca del último frame del segmento anterior para continuar el movimiento
    sin corte. Receta oficial lightx2v/Wan2.2-Lightning (shift=5, cfg=1, euler/simple)."""
    positive_text = f"{image_prompt}. {motion_prompt}".strip()
    wf = {
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": WAN_CLIP, "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": WAN_VAE}},
        "4": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": WAN_CLIP_VISION}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive_text, "clip": ["2", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": WAN_NEGATIVE, "clip": ["2", 0]}},
        "8": {"class_type": "CLIPVisionEncode",
              "inputs": {"clip_vision": ["4", 0], "image": ["5", 0], "crop": "none"}},
        "9": {"class_type": "WanImageToVideo", "inputs": {
            "positive": ["6", 0], "negative": ["7", 0], "vae": ["3", 0],
            "clip_vision_output": ["8", 0], "start_image": ["5", 0],
            "width": width, "height": height, "length": length, "batch_size": 1,
        }},
        "19b": {"class_type": "VAEDecode", "inputs": {"samples": ["17", 0], "vae": ["3", 0]}},
        "18": {"class_type": "CreateVideo", "inputs": {"images": ["19b", 0], "fps": VIDEO_FPS}},
        "20": {"class_type": "SaveVideo", "inputs": {
            "video": ["18", 0], "filename_prefix": "reel_i2v", "format": "auto", "codec": "auto"}},
    }
    wf.update(_wan_moe_sampler_nodes(
        WAN22_HIGH_NOISE_UNET, WAN22_LOW_NOISE_UNET, WAN22_LORA_HIGH_NOISE, WAN22_LORA_LOW_NOISE,
        seed, ["9", 2],
    ))
    return wf


def build_ltx_t2v_workflow(prompt: str, seed: int, width: int, height: int, length: int) -> dict:
    """LTX-Video 2B texto->vídeo (variante GGUF del template ltxv_text_to_video):
    UnetLoaderGGUF + VAELoader + CLIPLoader(ltxv) -> LTXVConditioning ->
    LTXVScheduler -> SamplerCustom. LTX genera el clip entero de una pasada."""
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": LTX_UNET}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": LTX_VAE}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": LTX_T5, "type": "ltxv"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": LTX_NEGATIVE, "clip": ["3", 0]}},
        "6": {"class_type": "EmptyLTXVLatentVideo",
              "inputs": {"width": width, "height": height, "length": length, "batch_size": 1}},
        "7": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["4", 0], "negative": ["5", 0], "frame_rate": float(LTX_FPS)}},
        "8": {"class_type": "LTXVScheduler", "inputs": {
            "steps": LTX_STEPS, "max_shift": 2.05, "base_shift": 0.95,
            "stretch": True, "terminal": 0.1, "latent": ["6", 0]}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "SamplerCustom", "inputs": {
            "model": ["1", 0], "add_noise": True, "noise_seed": seed, "cfg": LTX_CFG,
            "positive": ["7", 0], "negative": ["7", 1],
            "sampler": ["9", 0], "sigmas": ["8", 0], "latent_image": ["6", 0]}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["2", 0]}},
        "12": {"class_type": "CreateVideo", "inputs": {"images": ["11", 0], "fps": LTX_FPS}},
        "13": {"class_type": "SaveVideo", "inputs": {
            "video": ["12", 0], "filename_prefix": "reel_ltx", "format": "auto", "codec": "auto"}},
    }


def build_latentsync_workflow(video_filename: str, audio_filename: str, seed: int) -> dict:
    """El ComfyUI del usuario no tiene VideoHelperSuite, así que se leen los
    frames del clip con los nodos de vídeo del core (LoadVideo +
    GetVideoComponents) en lugar de VHS_LoadVideo del workflow de ejemplo.
    LatentSyncNode: (images, audio) -> (images, audio) con los labios sincronizados."""
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": video_filename}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "LoadAudio", "inputs": {"audio": audio_filename}},
        "4": {"class_type": "VideoLengthAdjuster", "inputs": {
            "images": ["2", 0], "audio": ["3", 0],
            "mode": "loop_to_audio", "fps": float(VIDEO_FPS), "silent_padding_sec": 0.1,
        }},
        "5": {"class_type": "LatentSyncNode", "inputs": {
            "images": ["4", 0], "audio": ["4", 1], "seed": seed,
            "lips_expression": LATENTSYNC_LIPS_EXPRESSION, "inference_steps": LATENTSYNC_STEPS,
        }},
        "6": {"class_type": "CreateVideo", "inputs": {
            "images": ["5", 0], "fps": VIDEO_FPS, "audio": ["5", 1]}},
        "7": {"class_type": "SaveVideo", "inputs": {
            "video": ["6", 0], "filename_prefix": "reel_lipsync", "format": "auto", "codec": "auto"}},
    }


# ── ffmpeg helpers (port de videoclip.py, sin el .exe de Windows) ─────────────

def _fraccion_negra(path: Path) -> float:
    """Fracción [0..1] del clip que es negro puro. Se usa para detectar
    renders fallidos de ComfyUI (que salen 100% negros y comprimen a ~13 KB)."""
    dur = probe_duration(path, default=0.0)
    if dur <= 0:
        return 1.0
    try:
        p = subprocess.run(
            [FFMPEG, "-i", str(path), "-vf", "blackdetect=d=0.1:pix_th=0.10",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        negro = sum(
            float(m) for m in re.findall(r"black_duration:(\d+\.?\d*)", p.stderr)
        )
        return min(1.0, negro / dur)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def probe_duration(path: Path, default: float = 0.0) -> float:
    try:
        p = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(p.stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return default


def extract_last_frame(video_path: Path, dest_png: Path) -> None:
    subprocess.run(
        [FFMPEG, "-y", "-sseof", "-0.2", "-i", str(video_path),
         "-update", "1", "-q:v", "2", str(dest_png)],
        capture_output=True, text=True, timeout=60,
    )


def concat_clips(clip_paths: list[Path], dest: Path) -> None:
    """Concatena varios mp4. Prueba primero sin recodificar (-c copy); si el
    resultado no es válido (los clips de ComfyUI podrían no compartir exactamente
    los mismos parámetros), recodifica."""
    concat_list = dest.parent / f"{dest.stem}_concat_list.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in clip_paths), encoding="utf-8"
    )
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(dest)],
        capture_output=True, text=True, timeout=600,
    )
    if not dest.exists() or dest.stat().st_size < 1024 or probe_duration(dest) < 0.1:
        subprocess.run(
            [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an",
             "-r", str(VIDEO_FPS), str(dest)],
            capture_output=True, text=True, timeout=900,
        )
    concat_list.unlink(missing_ok=True)


def _concat_silent(clip_paths: list[Path], silent: Path) -> None:
    """Concatena solo el vídeo (sin audio). Copia si puede; si no, recodifica."""
    concat_list = silent.parent / f"{silent.stem}_list.txt"
    concat_list.write_text(
        "\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in clip_paths), encoding="utf-8"
    )
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-an", "-c:v", "copy", str(silent)],
        capture_output=True, text=True, timeout=600,
    )
    if not silent.exists() or silent.stat().st_size < 1024 or probe_duration(silent) < 0.1:
        subprocess.run(
            [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(silent)],
            capture_output=True, text=True, timeout=900,
        )
    concat_list.unlink(missing_ok=True)


def _xfade_silent(clip_paths: list[Path], duraciones: list[float], silent: Path,
                  xfade: float) -> bool:
    """Encadena los clips con un crossfade de `xfade` s en cada corte, SIN
    descuadrar el audio: cada clip (menos el último) trae `xfade` s de cola de
    más, que es justo lo que consume la disolvencia, así que el clip k+1 sigue
    empezando en su instante real (suma de duraciones reales previas).
    Devuelve True si salió bien."""
    n = len(clip_paths)
    if n < 2 or len(duraciones) != n:
        return False
    labels = []
    parts = []
    for i in range(n):
        # cada clip menos el último lleva `xfade` s de cola (último frame clonado)
        # que es justo lo que consume la disolvencia siguiente
        cola = "" if i == n - 1 else f",tpad=stop_mode=clone:stop_duration={xfade:.3f}"
        parts.append(f"[{i}:v]fps=30,format=yuv420p,setsar=1{cola}[v{i}]")
        labels.append(f"v{i}")
    cur = labels[0]
    offset = 0.0
    for i in range(1, n):
        offset += duraciones[i - 1]
        out = "vx" if i == n - 1 else f"vc{i}"
        parts.append(
            f"[{cur}][{labels[i]}]xfade=transition=fade:"
            f"duration={xfade:.3f}:offset={offset:.3f}[{out}]"
        )
        cur = out
    filtro = ";".join(parts)
    inputs = []
    for p in clip_paths:
        inputs += ["-i", str(Path(p).resolve())]
    r = subprocess.run(
        [FFMPEG, "-y", *inputs, "-filter_complex", filtro, "-map", "[vx]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         str(silent)],
        capture_output=True, text=True, timeout=1800,
    )
    ok = silent.exists() and silent.stat().st_size > 1024 and probe_duration(silent) > 0.1
    if not ok:
        print(f"[comfy] xfade falló, se usa corte seco: {r.stderr[-500:]}")
    return ok


def ensamblar_videoclip_completo(clip_paths: list[Path], audio_path: Path, dest: Path,
                                  duraciones: list[float] | None = None,
                                  xfade: float = 0.0) -> None:
    """Une los clips de sección en un único videoclip SIN chasquidos en los
    cortes: monta solo el vídeo (empalmar tramos de audio AAC independientes
    mete un 'click' audible en cada corte por el encoder delay / priming) y
    encima pone la pista de audio original ENTERA, continua, sin ningún empalme.
    Si `duraciones` y `xfade>0`, los cortes llevan una disolvencia rápida."""
    work = dest.parent
    silent = work / f"{dest.stem}_silent.mp4"

    hecho = False
    if xfade > 0 and duraciones and len(duraciones) == len(clip_paths) >= 2:
        hecho = _xfade_silent(clip_paths, duraciones, silent, xfade)
    if not hecho:
        _concat_silent(clip_paths, silent)

    # Muxear la pista de audio original completa (una sola, continua).
    subprocess.run(
        [FFMPEG, "-y", "-i", str(silent), "-i", str(audio_path),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(dest)],
        capture_output=True, text=True, timeout=300,
    )
    silent.unlink(missing_ok=True)


def _fit_exact(src: Path, dest: Path, target: float) -> None:
    """Recorta si sobra; si falta una fracción de segundo, clona el último frame
    (tpad). NO hay cámara lenta: si acaba faltando mucho es que se llegó al tope
    de segmentos, y aun así preferimos un pelín de tpad a estirar todo el clip."""
    src_dur = probe_duration(src, default=target)
    if src_dur >= target - 0.05:
        cmd = [FFMPEG, "-y", "-i", str(src), "-t", f"{target:.3f}", "-an", "-c:v", "copy", str(dest)]
    else:
        pad = target - src_dur
        cmd = [FFMPEG, "-y", "-i", str(src), "-vf",
               f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
               "-t", f"{target:.3f}", "-an", "-r", str(VIDEO_FPS), str(dest)]
    subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not dest.exists() or dest.stat().st_size == 0:
        dest.write_bytes(src.read_bytes())


# ── API pública ──────────────────────────────────────────────────────────────

def generar_fondo_seccion(provider: str, style_prefix: str, scene: dict, dur: float,
                           seed: int, out_path: Path, width: int, height: int,
                           log_fn=lambda m: None, should_cancel=None) -> Path:
    """Genera el fondo (sin audio) de UNA sección como vídeo de la duración
    `dur`, con el generador `provider`:
      - "wan22": Wan2.2-T2V (seg 1) + Wan2.2-I2V encadenado (local, la mejor calidad).
      - "ltx":   LTX-Video 2B, clips largos de una sola pasada (local, rápido).
      - "fal":   API de fal.ai (de pago, requiere FAL_KEY).
    """
    if provider == "ltx":
        return _fondo_ltx(style_prefix, scene, dur, seed, out_path, width, height, log_fn)
    if provider == "fal":
        return _fondo_fal(style_prefix, scene, dur, seed, out_path, width, height, log_fn)
    return _fondo_wan22(style_prefix, scene, dur, seed, out_path, width, height, log_fn,
                        should_cancel=should_cancel)


def generar_frame_flux(prompt: str, seed: int, out_png: Path,
                        width: int, height: int, log_fn=lambda m: None,
                        should_cancel=None) -> Path:
    """Genera un fotograma fijo con Flux y lo descarga a `out_png`."""
    log_fn("flux frame")
    wf = build_flux_workflow(prompt, seed & 0x7FFFFFFF, width, height)
    out = comfy_wait(comfy_queue(wf), timeout=600.0, should_cancel=should_cancel)
    info = _first_output(out, "8")
    comfy_download(info["filename"], info.get("subfolder", ""), info["type"], out_png)
    return out_png


def _wan_i2v_segmento(image_path: Path, prompt: str, motion: str,
                       out_path: Path, width: int, height: int,
                       log_fn=lambda m: None, should_cancel=None) -> Path:
    """Un render de ~4s con Wan2.2-I2V desde `image_path`. Reintenta una vez con
    otra seed si el resultado sale negro (fallo puntual del sampler)."""
    for intento in (1, 2):
        uploaded = comfy_upload_image(image_path)
        wf = build_wan_i2v_workflow(uploaded, prompt, motion,
                                    uuid.uuid4().int & 0xFFFFFFFF,
                                    width, height, VIDEO_FRAMES)
        out = comfy_wait(comfy_queue(wf), timeout=2400.0, should_cancel=should_cancel)
        info = _first_output(out, "20")
        comfy_download(info["filename"], info.get("subfolder", ""), info["type"], out_path)
        if _fraccion_negra(out_path) < 0.6:
            return out_path
        log_fn(f"segmento negro, reintento {intento}")
    return out_path  # el guardián de _fondo_wan22 decide qué hacer


def _fondo_wan22(style_prefix: str, scene: dict, dur: float, seed: int,
                  out_path: Path, width: int, height: int,
                  log_fn=lambda m: None, should_cancel=None) -> Path:
    """Segmento 1: Flux genera el fotograma inicial y Wan2.2-I2V lo anima.
    Segmentos 2..N: Wan2.2-I2V desde el último frame, hasta cubrir `dur`.
    (El texto->vídeo puro de Wan2.2 con estos GGUF Q3 salía negro.)"""
    work = out_path.parent
    idx = out_path.stem
    prompt = f"{style_prefix}, {scene['image_prompt']}".strip(", ")
    motion = scene.get("motion_prompt") or "smooth cinematic camera movement"
    clip_seconds = VIDEO_FRAMES / VIDEO_FPS
    n_segments = min(MAX_REAL_SEGMENTS_PER_SCENE, max(1, math.ceil(dur / clip_seconds)))

    frame0 = work / f"{idx}_frame0.png"
    generar_frame_flux(prompt, seed, frame0, width, height, log_fn, should_cancel=should_cancel)

    segments: list[Path] = []
    current_frame = frame0
    for seg_num in range(1, n_segments + 1):
        log_fn(f"i2v {seg_num}/{n_segments}")
        seg_path = work / f"{idx}_seg{seg_num:02d}.mp4"
        _wan_i2v_segmento(current_frame, prompt, motion, seg_path, width, height, log_fn,
                          should_cancel=should_cancel)
        if _fraccion_negra(seg_path) >= 0.6:
            if seg_num == 1:
                raise RuntimeError("El primer segmento de Wan salió negro incluso tras reintento.")
            log_fn(f"segmento {seg_num} negro, se corta la sección aquí")
            break
        segments.append(seg_path)
        if seg_num < n_segments:
            nxt = work / f"{idx}_seg{seg_num:02d}_last.png"
            extract_last_frame(seg_path, nxt)
            current_frame = nxt

    if not segments:
        raise RuntimeError("Wan no produjo ningún segmento de vídeo utilizable.")

    raw = segments[0] if len(segments) == 1 else work / f"{idx}_raw.mp4"
    if len(segments) > 1:
        concat_clips(segments, raw)
    cobertura = probe_duration(raw, default=0.0)
    if cobertura < dur * 0.5 and cobertura < dur - 4.0:
        # Se cortó demasiado pronto: mejor imagen con Ken Burns (se mueve) que
        # 30s de fotograma congelado.
        raise RuntimeError(
            f"Wan solo cubrió {cobertura:.0f}s de {dur:.0f}s (segmentos negros)."
        )
    _fit_exact(raw, out_path, dur)
    return out_path


def _snap_ltx_frames(n: float) -> int:
    """LTX quiere longitud 8k+1."""
    n = max(9, min(LTX_MAX_FRAMES, int(round(n))))
    return n - ((n - 1) % 8)


def _fondo_ltx(style_prefix: str, scene: dict, dur: float, seed: int,
                out_path: Path, width: int, height: int,
                log_fn=lambda m: None) -> Path:
    """LTX-Video 2B: genera clips largos de una sola pasada (hasta ~7.7s) y los
    concatena hasta cubrir `dur`. Prompts largos y descriptivos (LTX pierde
    mucha calidad con prompts cortos)."""
    work = out_path.parent
    idx = out_path.stem
    # dims LTX: múltiplos de 32
    w = max(64, (width // 32) * 32)
    h = max(64, (height // 32) * 32)
    prompt = f"{style_prefix}. {scene['image_prompt']}. {scene.get('motion_prompt', '')}".strip(" .")
    clip_seconds = LTX_MAX_FRAMES / LTX_FPS
    n_clips = max(1, math.ceil(dur / clip_seconds))

    segments: list[Path] = []
    restante = dur
    for k in range(1, n_clips + 1):
        log_fn(f"LTX {k}/{n_clips}")
        frames = _snap_ltx_frames(min(restante, clip_seconds) * LTX_FPS + 1)
        wf = build_ltx_t2v_workflow(prompt, (seed + k) & 0xFFFFFFFF, w, h, frames)
        out = comfy_wait(comfy_queue(wf), timeout=1800.0)
        info = _first_output(out, "13")
        seg = work / f"{idx}_ltx{k:02d}.mp4"
        comfy_download(info["filename"], info.get("subfolder", ""), info["type"], seg)
        segments.append(seg)
        restante -= probe_duration(seg, default=clip_seconds)
        if restante <= 0.1:
            break

    if not segments:
        raise RuntimeError("LTX no produjo ningún clip.")
    raw = segments[0] if len(segments) == 1 else work / f"{idx}_raw.mp4"
    if len(segments) > 1:
        concat_clips(segments, raw)
    _fit_exact(raw, out_path, dur)
    return out_path


def _fondo_fal(style_prefix: str, scene: dict, dur: float, seed: int,
                out_path: Path, width: int, height: int,
                log_fn=lambda m: None) -> Path:
    """Genera el fondo con la API de fal.ai (modelo en FAL_MODEL, p.ej.
    MiniMax/Hailuo, Kling, Luma...). De pago. Requiere FAL_KEY.

    fal expone una cola síncrona en https://fal.run/<model>: POST con el prompt,
    devuelve JSON con la URL del vídeo. La duración por clip la fija el modelo
    (normalmente 5-6s), así que se piden varios y se concatenan."""
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY no configurada (pon tu clave de fal.ai en .env).")
    work = out_path.parent
    idx = out_path.stem
    prompt = f"{style_prefix}. {scene['image_prompt']}. {scene.get('motion_prompt', '')}".strip(" .")
    ratio = "16:9" if width >= height else "9:16"
    per_clip = 6.0
    n_clips = max(1, math.ceil(dur / per_clip))

    segments: list[Path] = []
    for k in range(1, n_clips + 1):
        log_fn(f"fal.ai {k}/{n_clips}")
        r = requests.post(
            f"https://fal.run/{FAL_MODEL}",
            headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
            json={"prompt": prompt, "aspect_ratio": ratio, "seed": (seed + k) & 0x7FFFFFFF},
            timeout=600,
        )
        r.raise_for_status()
        data = r.json()
        # fal devuelve {"video": {"url": ...}} o {"videos":[{"url":...}]}
        url = (data.get("video") or {}).get("url") or (data.get("videos") or [{}])[0].get("url")
        if not url:
            raise RuntimeError(f"Respuesta de fal.ai sin URL de vídeo: {str(data)[:300]}")
        seg = work / f"{idx}_fal{k:02d}.mp4"
        seg.write_bytes(requests.get(url, timeout=300).content)
        segments.append(seg)

    raw = segments[0] if len(segments) == 1 else work / f"{idx}_raw.mp4"
    if len(segments) > 1:
        concat_clips(segments, raw)
    _fit_exact(raw, out_path, dur)
    return out_path


def aplicar_lipsync(video_path: Path, audio_path: Path, out_path: Path,
                    log_fn=lambda m: None) -> Path:
    """Pasa el clip por LatentSync con `audio_path` para que la persona en
    pantalla mueva los labios con esa parte de la letra."""
    log_fn("LatentSync")
    vid_name = comfy_upload_file(video_path, "video/mp4")
    aud_name = comfy_upload_file(audio_path, "audio/wav")
    wf = build_latentsync_workflow(vid_name, aud_name, uuid.uuid4().int & 0xFFFFFFFF)
    out = comfy_wait(comfy_queue(wf), timeout=1800.0)
    info = _first_output(out, "7")
    comfy_download(info["filename"], info.get("subfolder", ""), info["type"], out_path)
    return out_path
