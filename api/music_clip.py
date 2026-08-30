"""
api/music_clip.py
Endpoints para la sección de Montaje: subida de audio y generación de clips.
"""
import json
import os
import re
import sys
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

CORE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = CORE_DIR / "output"
UPLOADS_DIR = CORE_DIR / "_uploads"
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

_jobs: dict = {}
_lock = threading.Lock()

# Estado del último "Arrancar herramientas" disparado desde la web (lo pinta el
# front vía /api/music-clip/estado -> campo `arranque`).
_arranque: dict = {"activo": False, "mensaje": "", "resultados": {}}

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".aiff", ".aif"}

# WAV/FLAC de alta calidad (24 bit / 96 kHz) rondan los 80–170 MB en 3–5 min,
# así que el límite es holgado. Configurable con MONTAJE_MAX_UPLOAD_MB.
MAX_UPLOAD_BYTES = int(os.getenv("MONTAJE_MAX_UPLOAD_MB", "300")) * 1024 * 1024


# ── Upload de audio ───────────────────────────────────────────────────────────

@router.post("/api/music-clip/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """Sube un archivo de audio. Devuelve la ruta interna para usarla en /generate.
    Se escribe a disco en trozos para no cargar 100+ MB en memoria."""
    ext = Path(file.filename or "audio.mp3").suffix.lower()
    if ext not in AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: {ext}. Usa mp3, wav, flac, aac, m4a, aiff.",
        )

    nombre = f"lyric_{uuid.uuid4().hex[:10]}{ext}"
    ruta = UPLOADS_DIR / nombre
    escrito = 0
    with open(ruta, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            escrito += len(chunk)
            if escrito > MAX_UPLOAD_BYTES:
                f.close()
                ruta.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"El archivo supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            f.write(chunk)

    return {"path": str(ruta), "filename": nombre, "size": escrito}


# ── Generación de clips ───────────────────────────────────────────────────────

class MusicClipRequest(BaseModel):
    audio_path: str           # ruta devuelta por upload-audio
    letra: str                # texto de la letra
    artista: str = ""
    titulo: str = ""
    estilo: str = "cinematico"   # clave de ESTILOS
    mostrar_letra: bool = True
    mostrar_cabecera: bool = True
    modo_fondo: str = "video"      # compat: "video" | "imagen"
    provider: str = "wan22"        # "wan22" | "ltx" | "fal" | "imagen"
    voz_femenina: bool = False     # compat: fuerza protagonista femenina + lip-sync
    voz: str = "auto"              # "auto" (detecta) | "hombre" | "mujer" | "mixta"
    pista_voz_path: Optional[str] = None  # a cappella opcional para el lip-sync
    aspect: str = "16:9"           # "16:9" (horizontal, default) | "9:16" (reel)
    letra_lrc: Optional[str] = None  # letra en formato .lrc (tiempos exactos)
    idioma: str = "es"               # idioma de la letra (para Whisper)


def _slug_de(req: MusicClipRequest) -> str:
    return re.sub(r"[^\w]", "_", (req.titulo or req.artista or "clip").lower())[:24]


def _req_path(slug: str) -> Path:
    return OUTPUT_DIR / f"{slug}_montaje_req.json"


def _plan_path(slug: str) -> Path:
    return OUTPUT_DIR / f"{slug}_montaje_plan.json"


def _arrancar_job(req: MusicClipRequest, audio_path: Path, reanudar: bool) -> str:
    job_id = uuid.uuid4().hex[:8]
    slug = _slug_de(req)
    with _lock:
        _jobs[job_id] = {
            "id": job_id, "slug": slug, "status": "running", "cancel": False,
            "progress": {"actual": 0, "total": 0,
                         "label": "Reanudando…" if reanudar else "Iniciando…"},
            "output_files": [], "error": None,
            "created_at": datetime.now().isoformat(), "completed_at": None,
        }
    # Sidecar con la petición, para poder reanudar tras un corte del backend.
    try:
        _req_path(slug).write_text(
            json.dumps({"request": req.model_dump(), "job_id": job_id,
                        "updated_at": datetime.now().isoformat()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass
    threading.Thread(target=_run, args=(job_id, req, audio_path, reanudar), daemon=True).start()
    return job_id


@router.post("/api/music-clip/generate")
def generate_music_clip(req: MusicClipRequest):
    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de audio no encontrado.")
    if not req.letra.strip():
        raise HTTPException(status_code=400, detail="La letra no puede estar vacía.")
    return {"job_id": _arrancar_job(req, audio_path, reanudar=False)}


@router.post("/api/music-clip/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado.")
        job["cancel"] = True
        job["progress"]["label"] = "Cancelando… (termina el paso en curso)"
    return {"ok": True}


@router.get("/api/music-clip/reanudables")
def listar_reanudables():
    """Montajes que quedaron a medias (backend o ComfyUI se cortó) y se pueden
    continuar. Lee los sidecars de plan/petición del disco."""
    out = []
    for plan_f in OUTPUT_DIR.glob("*_montaje_plan.json"):
        try:
            plan = json.loads(plan_f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if plan.get("status") not in ("generando", "cancelado"):
            continue
        slug = plan_f.name[: -len("_montaje_plan.json")]
        if not _req_path(slug).exists():
            continue
        activo = any(j.get("slug") == slug and j.get("status") == "running"
                     for j in _jobs.values())
        out.append({
            "slug": slug, "titulo": plan.get("titulo") or slug,
            "hechas": plan.get("secciones_hechas", 0),
            "total": plan.get("total_secciones", 0),
            "status": plan.get("status"), "actualizado": plan.get("actualizado"),
            "en_curso": activo,
        })
    out.sort(key=lambda x: x.get("actualizado") or "", reverse=True)
    return out


@router.post("/api/music-clip/reanudar/{slug}")
def reanudar_montaje(slug: str):
    req_f = _req_path(slug)
    if not req_f.exists():
        raise HTTPException(status_code=404, detail="No hay un montaje que reanudar con ese nombre.")
    if any(j.get("slug") == slug and j.get("status") == "running" for j in _jobs.values()):
        raise HTTPException(status_code=409, detail="Ese montaje ya se está generando.")
    try:
        data = json.loads(req_f.read_text(encoding="utf-8"))
        req = MusicClipRequest(**data["request"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Sidecar de petición ilegible: {e}")
    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="El audio original ya no está en disco.")
    return {"job_id": _arrancar_job(req, audio_path, reanudar=True)}


def _run(job_id: str, req: MusicClipRequest, audio_path: Path, reanudar: bool = False):
    sys.path.insert(0, str(CORE_DIR))

    def progreso(idx: int, total: int, label: str):
        with _lock:
            _jobs[job_id]["progress"] = {
                "actual": idx + 1,
                "total": total,
                "label": f"Generando clip {idx + 1}/{total}: {label}…",
            }

    def _cancelado() -> bool:
        with _lock:
            j = _jobs.get(job_id)
            return bool(j and j.get("cancel"))

    try:
        from lyric_video_builder import generar_clips

        slug = _slug_de(req)
        base = str(OUTPUT_DIR / slug)

        pista_voz = None
        if req.pista_voz_path:
            p = Path(req.pista_voz_path)
            if p.exists():
                pista_voz = str(p)

        # Si el usuario marcó "voz femenina" a mano y no eligió otra cosa en el
        # selector, esa marca manda sobre la autodetección.
        voz_sel = req.voz
        if voz_sel == "auto" and req.voz_femenina:
            voz_sel = "mujer"

        info: dict = {}
        rutas = generar_clips(
            ruta_audio=str(audio_path),
            letra=req.letra,
            artista=req.artista,
            titulo=req.titulo,
            estilo=req.estilo,
            ruta_salida_base=base,
            mostrar_letra=req.mostrar_letra,
            mostrar_cabecera=req.mostrar_cabecera,
            cb_progreso=progreso,
            modo_fondo=req.modo_fondo,
            provider=req.provider,
            voz_femenina=req.voz_femenina,
            voz=voz_sel,
            pista_voz=pista_voz,
            aspect=req.aspect,
            letra_lrc=req.letra_lrc,
            idioma=req.idioma,
            info_out=info,
            should_cancel=_cancelado,
            reanudar=reanudar,
        )

        nombres = [Path(r).name for r in rutas]
        with _lock:
            cancelado = bool(info.get("cancelado"))
            _jobs[job_id]["status"] = "cancelled" if cancelado else "completed"
            _jobs[job_id]["output_files"] = nombres
            _jobs[job_id]["sync_letra"] = info.get("sync_letra", "uniforme")
            _jobs[job_id]["voces"] = info.get("voces")
            _jobs[job_id]["completed_at"] = datetime.now().isoformat()

    except Exception as e:
        import traceback
        with _lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
            _jobs[job_id]["completed_at"] = datetime.now().isoformat()
        print(f"[MusicClip] Error: {traceback.format_exc()}")


# Importar re aquí para poder usarlo en _run
import re


@router.get("/api/music-clip/activo")
def hay_job_activo():
    """True si algún job del Montaje está corriendo. Lo usa el guardián de
    suspensión del host (scripts/mantener_despierto.ps1)."""
    with _lock:
        activo = any(j.get("status") == "running" for j in _jobs.values())
    return {"activo": activo}


@router.get("/api/music-clip/jobs/{job_id}")
def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return job


@router.get("/api/music-clip/estilos")
def list_estilos():
    from lyric_video_builder import ESTILOS
    return [{"id": k, "label": k.capitalize()} for k in ESTILOS]


@router.get("/api/music-clip/proveedores")
def list_proveedores():
    """Generadores de vídeo disponibles ahora mismo (para el selector del
    Montaje): consulta ComfyUI, qué modelos hay y si FAL_KEY está puesta."""
    try:
        from comfy_video_builder import providers_disponibles
        return providers_disponibles()
    except Exception as e:  # noqa: BLE001
        return [{"id": "imagen", "label": "Imagen fija (Pollinations)",
                 "disponible": True, "nota": f"(sin ComfyUI: {e})"}]


@router.get("/api/music-clip/estado")
def estado_herramientas():
    """Pre-chequeo del Montaje: ComfyUI arriba, LM Studio arriba, modelos,
    y la lista de problemas a resolver antes de generar vídeo."""
    try:
        from comfy_video_builder import verificar_herramientas
        d = verificar_herramientas()
        d["arranque"] = _arranque
        return d
    except Exception as e:  # noqa: BLE001
        return {"comfy": False, "lm_studio": False, "providers": [],
                "problemas": [f"No se pudo comprobar el estado: {e}"],
                "control_center": False, "arranque": _arranque}


@router.post("/api/music-clip/arrancar-herramientas")
def arrancar_herramientas(servicios: Optional[str] = Form("comfyui,lmstudio")):
    """Pide al Centro de Control del host (AI Studio, :8090) que encienda
    ComfyUI y/o LM Studio. Devuelve al instante; el arranque real corre en
    segundo plano y su progreso se lee en /estado (campo `arranque`)."""
    from comfy_video_builder import control_center_disponible, arrancar_via_control_center

    keys = [s.strip() for s in (servicios or "").split(",") if s.strip() in ("comfyui", "lmstudio")]
    if not keys:
        raise HTTPException(status_code=400, detail="Nada que arrancar.")
    if not control_center_disponible():
        raise HTTPException(
            status_code=503,
            detail="El Centro de Control (:8090) no responde. Ábrelo con "
                   "E:\\AI-Studio\\Centro-Control.bat")
    if _arranque["activo"]:
        return {"ok": True, "ya_en_marcha": True, "arranque": _arranque}

    nombres = {"comfyui": "ComfyUI", "lmstudio": "LM Studio"}
    _arranque.update(activo=True, resultados={},
                     mensaje="Arrancando " + " y ".join(nombres[k] for k in keys) + "…")

    def _run():
        try:
            res = arrancar_via_control_center(keys)
            fallos = [k for k, v in res.items() if not v.get("ok")]
            _arranque.update(
                resultados=res,
                mensaje=("Todo arrancado." if not fallos
                         else "Con avisos: " + "; ".join(res[k]["msg"] for k in fallos)))
        except Exception as e:  # noqa: BLE001
            _arranque.update(mensaje=f"Error al arrancar: {e}")
        finally:
            _arranque["activo"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "arranque": _arranque}


@router.get("/api/music-clip/audio-preview")
def audio_preview(path: str):
    """Sirve el archivo de audio subido para previsualización en el player."""
    from fastapi.responses import FileResponse
    p = Path(path)
    # Seguridad: solo servir archivos dentro de _uploads
    if not p.is_file() or UPLOADS_DIR not in p.parents:
        raise HTTPException(status_code=404, detail="Audio no encontrado.")
    suffix = p.suffix.lower()
    mime_map = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
        ".aac": "audio/aac", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
    }
    return FileResponse(str(p), media_type=mime_map.get(suffix, "audio/mpeg"))
