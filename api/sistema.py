"""
api/sistema.py
Estado del sistema: qué piezas funcionan y cuáles hay que arrancar.

- Al arrancar el backend (`preparar_arranque`, llamado desde api/server.py):
  crea las carpetas de datos, comprueba las librerías de Python y, si falta
  alguna de requirements.txt (p. ej. el contenedor se recreó sin reconstruir
  la imagen), la instala en segundo plano. El informe queda en el log y en
  GET /api/sistema/estado.
- GET /api/sistema/estado → cada componente con ok / detalle / cómo arreglarlo
  y, por sección de la web, qué necesita. La web lo usa para avisar en cada
  página («Necesitas arrancar ComfyUI…») con un botón cuando se puede arrancar
  desde aquí (IA del Mac → despertar; ComfyUI → Centro de Control).

Las comprobaciones de red van en paralelo con timeouts cortos y se cachean
unos segundos para que varias pestañas abiertas no martilleen los servicios.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from fastapi import APIRouter

CORE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CORE_DIR))

router = APIRouter(prefix="/api/sistema", tags=["sistema"])

# ─── Qué necesita cada sección de la web ────────────────────────────────────
# obligatorio: sin eso la sección no funciona · opcional: solo algunas opciones
SECCIONES = {
    "generar": {"nombre": "Generar", "obligatorio": ["llm", "ffmpeg", "internet"],
                "opcional": {"comfyui": "Vídeo IA en movimiento y Portada IA"}},
    "gestor": {"nombre": "Gestor", "obligatorio": ["llm", "ffmpeg", "internet"],
               "opcional": {"comfyui": "Vídeo IA y Portada IA en la cola"}},
    "montaje": {"nombre": "Montaje", "obligatorio": ["comfyui", "llm", "ffmpeg", "whisper"],
                "opcional": {"control_center": "Arrancar ComfyUI / LM Studio con un botón"}},
    "fuentes": {"nombre": "Fuentes", "obligatorio": ["internet"], "opcional": {}},
    "canales": {"nombre": "Canales", "obligatorio": ["internet"], "opcional": {}},
    "tiktok": {"nombre": "TikTok", "obligatorio": ["internet"], "opcional": {}},
    "biblioteca": {"nombre": "Biblioteca", "obligatorio": ["disco"], "opcional": {}},
    "musica": {"nombre": "Música", "obligatorio": ["ffmpeg", "disco"], "opcional": {}},
    "cursos": {"nombre": "Cursos", "obligatorio": ["llm", "ffmpeg", "chromium", "frontend", "libs_documentos", "internet"],
               "opcional": {}},  # sus imágenes IA van por Pollinations, no por ComfyUI
    "ajustes": {"nombre": "Settings", "obligatorio": [], "opcional": {}},
}

# Módulo de Python → paquete de pip (para autoinstalar lo que falte)
LIBRERIAS = {
    "fastapi": "fastapi", "edge_tts": "edge-tts", "moviepy": "moviepy==1.0.3", "PIL": "pillow",
    "feedparser": "feedparser", "bs4": "beautifulsoup4", "yt_dlp": "yt-dlp", "librosa": "librosa",
    "faster_whisper": "faster-whisper", "playwright": "playwright", "pymupdf": "pymupdf",
    "docx": "python-docx", "pptx": "python-pptx", "googleapiclient": "google-api-python-client",
    "qrcode": "qrcode[pil]", "mutagen": "mutagen",
}
LIBS_DOCUMENTOS = ["pymupdf", "docx", "pptx"]
CARPETAS = ["output", "_library", "_music", "_templates", "_uploads", "_tokens", "_config", "_cursos"]

_arranque = {"hecho": False, "instalando": [], "instaladas": [], "errores": [], "carpetas_creadas": [],
             "inicio": None, "fin": None}
_cache = {"t": 0.0, "datos": None}
_cache_lock = threading.Lock()
TTL_CACHE = 8.0


def _falta(modulo: str) -> bool:
    try:
        return importlib.util.find_spec(modulo) is None
    except (ImportError, ValueError):
        return True


def _instalar_en_segundo_plano(paquetes: list[str]) -> None:
    def _run():
        _arranque["instalando"] = list(paquetes)
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", *paquetes],
                               capture_output=True, text=True, timeout=1800)
            if r.returncode == 0:
                _arranque["instaladas"] = list(paquetes)
                importlib.invalidate_caches()
                print(f"[arranque] Librerías instaladas: {', '.join(paquetes)}", flush=True)
            else:
                _arranque["errores"].append(f"pip install {' '.join(paquetes)}: {r.stderr.strip()[-400:]}")
                print(f"[arranque] ERROR instalando {paquetes}: {r.stderr[-400:]}", flush=True)
        except Exception as e:  # noqa: BLE001
            _arranque["errores"].append(f"pip install: {e}")
        finally:
            _arranque["instalando"] = []
            _cache["t"] = 0
    threading.Thread(target=_run, daemon=True, name="autoinstalar-libs").start()


def preparar_arranque() -> None:
    """Se ejecuta una vez al arrancar el backend."""
    _arranque["inicio"] = time.strftime("%Y-%m-%d %H:%M:%S")
    for c in CARPETAS:
        d = CORE_DIR / c
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            _arranque["carpetas_creadas"].append(c)
    faltan = [pip for mod, pip in LIBRERIAS.items() if _falta(mod)]
    if faltan and os.environ.get("AUTO_INSTALAR_LIBS", "1") != "0":
        print(f"[arranque] Faltan librerías, instalando en segundo plano: {', '.join(faltan)}", flush=True)
        _instalar_en_segundo_plano(faltan)
    _arranque["hecho"] = True
    _arranque["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def _informe():  # informe en el log, sin retrasar el arranque
        datos = estado(forzar=True)
        malos = [c for c in datos["componentes"] if not c["ok"]]
        print("[arranque] Estado del sistema: " + ("todo listo" if not malos else
              "; ".join(f"{c['nombre']}: {c['detalle']}" for c in malos)), flush=True)
    threading.Thread(target=_informe, daemon=True).start()


# ─── Comprobaciones ─────────────────────────────────────────────────────────

def _c(id_, nombre, ok, detalle, arreglo="", accion=None, grave=True):
    return {"id": id_, "nombre": nombre, "ok": bool(ok), "detalle": detalle, "arreglo": arreglo,
            "accion": accion, "grave": grave}


def _chk_llm():
    from llm_local import (
        GROK_BRIDGE_URL, LLM_BASE_URL, grok_responde, llm_studio_responde, usar_grok,
    )
    if usar_grok():
        if grok_responde(timeout=4):
            return _c("llm", "Grok", True, f"conectado en {GROK_BRIDGE_URL}", "")
        if llm_studio_responde(timeout=4):
            return _c(
                "llm", "LM Studio (Grok caído)", True,
                f"el puente no responde; se usa {LLM_BASE_URL}",
                "Para volver a Grok, ejecuta scripts\\Iniciar-Grok.bat en el PC.",
            )
        return _c(
            "llm", "Grok", False, f"no responde en {GROK_BRIDGE_URL}",
            "Ejecuta scripts\\Iniciar-Grok.bat en el PC. Si prefieres el Mac, pulsa «Despertar».",
            accion="despertar_llm",
        )
    ok = llm_studio_responde(timeout=4)
    return _c("llm", "IA del Mac (LM Studio)", ok,
              f"responde en {LLM_BASE_URL}" if ok else f"no responde en {LLM_BASE_URL}",
              "Enciende el Mac y abre LM Studio con el servidor activo, o pulsa «Despertar».",
              accion="despertar_llm")


def _chk_comfy():
    from comfy_video_builder import comfy_disponible, COMFY_URL
    ok = comfy_disponible(timeout=3)
    return _c("comfyui", "ComfyUI (GPU del PC)", ok,
              f"responde en {COMFY_URL}" if ok else f"no responde en {COMFY_URL}",
              "Arráncalo con el botón (Centro de Control) o abre E:\\AI-Studio\\ComfyUI.",
              accion="arrancar_comfyui")


def _chk_cc():
    from comfy_video_builder import control_center_disponible, CONTROL_CENTER_URL
    ok = control_center_disponible(timeout=2)
    return _c("control_center", "Centro de Control (AI Studio)", ok,
              f"responde en {CONTROL_CENTER_URL}" if ok else f"no responde en {CONTROL_CENTER_URL}",
              "Ábrelo con E:\\AI-Studio\\Centro-Control.bat (permite arrancar ComfyUI desde aquí).", grave=False)


def _chk_internet():
    try:
        ok = requests.head("https://www.google.com", timeout=4).status_code < 500
    except requests.RequestException:
        ok = False
    return _c("internet", "Internet", ok, "conectado" if ok else "sin conexión",
              "Comprueba la red del PC: la voz (edge-tts), las noticias y la publicación la necesitan.")


def _chk_frontend():
    url = os.environ.get("CURSOS_FRONTEND_URL", "http://frontend:3000").rstrip("/")
    try:
        ok = requests.get(url + "/cursos", timeout=8).status_code < 500
    except requests.RequestException:
        ok = False
    return _c("frontend", "Web vista desde el backend", ok,
              f"{url} accesible" if ok else f"{url} no responde",
              "El render de cursos fotografía las diapositivas en la web: levanta todo con `docker compose up -d`.")


def _chk_local():
    """Comprobaciones sin red (rápidas)."""
    out = []
    ff = shutil.which("ffmpeg") and shutil.which("ffprobe")
    out.append(_c("ffmpeg", "ffmpeg", ff, "instalado" if ff else "no encontrado",
                  "Viene en la imagen del backend: reconstruye con `docker compose build backend`."))
    pw_dir = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache" / "ms-playwright"))
    chromium = pw_dir.exists() and any(pw_dir.glob("chromium*"))
    out.append(_c("chromium", "Chromium (Playwright)", chromium and not _falta("playwright"),
                  "instalado" if chromium else "no instalado",
                  "Ejecuta `playwright install chromium` en el backend (o reconstruye la imagen)."))
    faltan_docs = [m for m in LIBS_DOCUMENTOS if _falta(m)]
    instalando = bool(_arranque["instalando"])
    out.append(_c("libs_documentos", "Lectores de PDF / Word / PowerPoint", not faltan_docs,
                  "instalados" if not faltan_docs else
                  ("instalándose…" if instalando else f"faltan: {', '.join(faltan_docs)}"),
                  "Se instalan solos al arrancar; si no, `pip install pymupdf python-docx python-pptx`."))
    whisper = not _falta("faster_whisper")
    out.append(_c("whisper", "Sincronía de letra (faster-whisper)", whisper,
                  "instalado" if whisper else "no instalado", "Se instala solo al arrancar el backend."))
    faltan = [pip for mod, pip in LIBRERIAS.items() if _falta(mod)]
    out.append(_c("librerias", "Librerías de Python", not faltan,
                  "completas" if not faltan else ("instalándose: " if instalando else "faltan: ") + ", ".join(faltan),
                  "Se instalan solas al arrancar; si persiste: `docker compose build backend`."))
    libre = shutil.disk_usage(CORE_DIR).free / 1e9
    out.append(_c("disco", "Espacio en disco", libre > 5, f"{libre:.0f} GB libres",
                  "Libera espacio: Gestor → Almacenamiento → Limpiar.", grave=libre < 2))
    no_escribibles = [c for c in CARPETAS if not os.access(CORE_DIR / c, os.W_OK)]
    out.append(_c("carpetas", "Carpetas de datos", not no_escribibles,
                  "todas accesibles" if not no_escribibles else f"sin permiso: {', '.join(no_escribibles)}",
                  "Revisa los volúmenes de docker-compose.yml."))
    return out


def estado(forzar: bool = False) -> dict:
    with _cache_lock:
        if not forzar and _cache["datos"] and time.time() - _cache["t"] < TTL_CACHE:
            return _cache["datos"]
    comps = _chk_local()
    with ThreadPoolExecutor(max_workers=5) as ex:
        futuros = [ex.submit(f) for f in (_chk_llm, _chk_comfy, _chk_cc, _chk_internet, _chk_frontend)]
        for f in futuros:
            try:
                comps.append(f.result(timeout=12))
            except Exception as e:  # noqa: BLE001
                comps.append(_c("error", "Comprobación", False, str(e)))
    por_id = {c["id"]: c for c in comps}
    secciones = {}
    for sid, s in SECCIONES.items():
        faltan = [por_id[i] for i in s["obligatorio"] if i in por_id and not por_id[i]["ok"]]
        opc = [dict(por_id[i], para=para) for i, para in s["opcional"].items()
               if i in por_id and not por_id[i]["ok"]]
        secciones[sid] = {"nombre": s["nombre"], "ok": not faltan,
                          "faltan": [c["id"] for c in faltan], "opcionales": [c["id"] for c in opc],
                          "opcionales_para": {c["id"]: c["para"] for c in opc}}
    datos = {"componentes": comps, "secciones": secciones, "arranque": _arranque,
             "comprobado": time.strftime("%H:%M:%S")}
    with _cache_lock:
        _cache.update(t=time.time(), datos=datos)
    return datos


@router.get("/estado")
def ver_estado(forzar: bool = False):
    return estado(forzar=forzar)


@router.post("/arrancar/{servicio}")
def arrancar(servicio: str):
    """Arranca lo que se puede arrancar desde la web: la IA del Mac (despertar
    por SSH vía Centro de Control) o ComfyUI (Centro de Control del PC)."""
    if servicio == "llm":
        from llm_local import asegurar_llm, LLMNoDisponible
        try:
            asegurar_llm()
            _cache["t"] = 0
            return {"ok": True, "msg": "IA del Mac lista"}
        except LLMNoDisponible as e:
            return {"ok": False, "msg": str(e)}
    if servicio == "comfyui":
        from comfy_video_builder import control_center_disponible, arrancar_via_control_center
        if not control_center_disponible():
            return {"ok": False, "msg": "El Centro de Control (:8090) no responde. Ábrelo con E:\\AI-Studio\\Centro-Control.bat"}
        res = arrancar_via_control_center(["comfyui"]).get("comfyui", {})
        _cache["t"] = 0
        return {"ok": bool(res.get("ok")), "msg": res.get("msg", "")}
    return {"ok": False, "msg": f"«{servicio}» no se puede arrancar desde la web"}
