"""
api/gestor.py
Gestor de generación y publicación automatizada de reels.
"""
import email.utils
import os
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests as http
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from api.jobs_store import jobs as _server_jobs, jobs_lock as _server_jobs_lock, create_job as _create_job

router = APIRouter()

CORE_DIR = Path(__file__).parent.parent
CONFIG_DIR = CORE_DIR / "_config"
CONFIG_DIR.mkdir(exist_ok=True)

QUEUE_FILE = CONFIG_DIR / "gestor_queue.json"
SCHEDULED_FILE = CONFIG_DIR / "gestor_scheduled.json"
OUTPUT_DIR = CORE_DIR / "output"

_lock = threading.Lock()


# ── Persistence ────────────────────────────────────────────────────────────────

def _load(path: Path) -> list:
    try:
        return json.loads(path.read_text("utf-8")) if path.exists() else []
    except Exception:
        return []


def _save(path: Path, data: list):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


# ── Fecha / recencia helpers ───────────────────────────────────────────────────

def _recalcular_recencia(fecha_str: str) -> dict:
    """Recalcula recencia en tiempo real a partir de la fecha original del artículo."""
    if not fecha_str:
        return {"horas": None, "label": ""}
    dt = None
    try:
        dt = email.utils.parsedate_to_datetime(fecha_str)
    except Exception:
        # ISO 8601 — probar formatos de mayor a menor precisión
        s = fecha_str.rstrip("Z")
        for fmt, length in (
            ("%Y-%m-%dT%H:%M:%S.%f", 26),
            ("%Y-%m-%dT%H:%M:%S",    19),
            ("%Y-%m-%d %H:%M:%S",    19),
            ("%Y-%m-%d",             10),
        ):
            try:
                dt = datetime.strptime(s[:length], fmt)
                dt = dt.replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue
    if dt is None:
        return {"horas": None, "label": ""}
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ahora = datetime.now(timezone.utc)
    delta = ahora - dt
    horas = max(0.0, delta.total_seconds() / 3600)
    if horas < 1:
        label = f"Hace {max(1, int(delta.total_seconds() / 60))}min"
    elif horas < 24:
        label = f"Hace {int(horas)}h"
    elif horas < 48:
        label = "Ayer"
    elif horas < 24 * 7:
        label = f"Hace {int(horas / 24)}d"
    elif horas < 24 * 30:
        label = f"Hace {int(horas / (24 * 7))}sem"
    else:
        m = int(horas / (24 * 30))
        label = f"Hace {m}mes" if m == 1 else f"Hace {m}meses"
    return {"horas": round(horas, 1), "label": label}


def _enriquecer_noticia(item: dict) -> dict:
    """Para items tipo 'noticia', expone fecha_noticia, recencia_label, recencia_horas y fuente_noticia."""
    if item.get("tipo") != "noticia":
        return item
    try:
        noticia = json.loads(item.get("contenido", "{}"))
    except Exception:
        return item

    fecha_str = noticia.get("fecha", "")
    rec = _recalcular_recencia(fecha_str)

    # Fallback 1: usar el dict recencia que ya guardó el curator
    if not rec["label"]:
        stored = noticia.get("recencia", {})
        if isinstance(stored, dict) and stored.get("label"):
            rec = {"horas": stored.get("horas"), "label": stored["label"]}

    # Fallback 2: usar la fecha de creación del item en la cola
    if not rec["label"] and item.get("creado"):
        rec = _recalcular_recencia(item["creado"])

    return {
        **item,
        "fecha_noticia":    fecha_str,
        "recencia_label":   rec["label"],
        "recencia_horas":   rec["horas"],
        "fuente_noticia":   noticia.get("origen") or noticia.get("fuente", ""),
        "score_noticia":    noticia.get("score"),
        "veracidad_label":  noticia.get("veracidad_label", ""),
        "veracidad_color":  noticia.get("veracidad_color", ""),
        "veracidad_score":  noticia.get("veracidad_score"),
        "veracidad_evidencia": noticia.get("veracidad_evidencia", ""),
    }


# ── Models ─────────────────────────────────────────────────────────────────────

class QueueItemRequest(BaseModel):
    tipo: str           # "url" | "texto" | "noticia"
    contenido: str      # URL, texto libre, o JSON serializado de la noticia
    titulo: str = ""
    auto_publish: bool = False
    publish_platforms: list[str] = []
    tipo_contenido: str = "noticia"
    tiktok_privacy: str = "SELF_ONLY"
    hilo_id: Optional[str] = None
    score_noticia: Optional[float] = None
    retry_count: int = 0
    score_noticia: Optional[float] = None


class GenerateOverrides(BaseModel):
    """Parámetros opcionales que sobreescriben las prefs globales para esta generación."""
    musica_fondo: Optional[str] = None       # "" = sin música, "file.mp3" = usar este, None = usar prefs
    mostrar_titulo: Optional[bool] = None    # None = usar prefs
    mostrar_subtitulos: Optional[bool] = None
    largo: bool = False                      # True = video largo 7-10 min (4 actos)
    video_ia: Optional[bool] = None          # None = según viralidad (VIDEO_IA_UMBRAL)
    portada_ia: Optional[bool] = None


class YoutubeUrlRequest(BaseModel):
    youtube_url: str = ""


class DistributeRequest(BaseModel):
    platforms: list[str]   # ["telegram", "x", "whatsapp"]
    texto: str = ""
    textos: dict = {}      # por plataforma: {"telegram": "...", "x": "..."}


class ScheduleRequest(BaseModel):
    output_file: str
    titulo: str
    descripcion: str = ""
    tiktok_caption: str = ""
    instagram_caption: str = ""
    x_caption: str = ""
    platforms: list[str]
    tipo_contenido: str = "noticia"
    tiktok_privacy: str = "SELF_ONLY"
    publish_at: Optional[str] = None   # ISO datetime; None = publicar ahora
    queue_item_id: str = ""            # ID del item de origen en gestor_queue
    auto_distribute: bool = False      # distribuir a Telegram/X/WA tras subir a YouTube
    distribute_platforms: list[str] = []
    distribute_textos: dict = {}
    force: bool = False               # forzar re-subida aunque ya esté confirmada


# ── Helpers ────────────────────────────────────────────────────────────────────

def _titulo_desde_guion(output_file: str) -> str | None:
    """Lee la línea 'Titulo:' del sidecar _guion.txt o _info.txt en español."""
    if not output_file:
        return None
    slug = re.sub(r'(_short\d+)?_reel\.mp4$', '', output_file)
    if not slug or slug == output_file:
        return None
    for suffix in ("_guion.txt", "_info.txt"):
        path = OUTPUT_DIR / f"{slug}{suffix}"
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("Titulo:"):
                        titulo = line[len("Titulo:"):].strip()
                        if titulo:
                            return titulo
            except Exception:
                pass
    return None


def _start_job(item: dict, items: list, overrides: dict = None) -> bool:
    """Crea un job de generación directamente en memoria. Devuelve True si se pudo lanzar."""
    payload = _build_generate_payload(item, overrides=overrides)

    # Enriquecer con contexto del hilo temático si aplica
    hilo_id = item.get("hilo_id")
    if hilo_id:
        try:
            from api.threads import _load as _load_threads
            hilos = _load_threads()
            hilo = next((h for h in hilos if h["id"] == hilo_id), None)
            if hilo:
                episodios_prev = [e for e in hilo.get("episodios", []) if e.get("youtube_url")]
                if episodios_prev:
                    ep_txt = "; ".join(
                        f"Ep.{e['numero']}: {e['titulo']} ({e['youtube_url']})"
                        for e in episodios_prev[-3:]  # últimos 3
                    )
                    hilo_ctx = (
                        f"\n\nCONTEXTO DE SERIE: Este video es el episodio {len(hilo['episodios']) + 1} "
                        f"de la serie '{hilo['nombre']}'. "
                        f"Videos anteriores: {ep_txt}. "
                        f"Menciona brevemente la serie al inicio y enlaza con lo anterior."
                    )
                    existing_doc = payload.get("procedencia", "") or ""
                    payload["procedencia"] = existing_doc + hilo_ctx
        except Exception as e:
            print(f"[threads] Error al cargar contexto de hilo: {e}")

    try:
        job_id = _create_job(payload)
        item["estado"] = "generating"
        item["job_id"] = job_id
        item["error"] = None
        return True
    except Exception as e:
        item["estado"] = "failed"
        item["error"] = str(e)
        return False


def _advance_queue(items: list) -> bool:
    """Si no hay nada generando, arranca el primer item 'queued'. Devuelve True si hubo cambio."""
    generating = any(i.get("estado") == "generating" for i in items)
    if generating:
        return False
    for item in reversed(items):
        # Solo "queued" = explícitamente encolado por el usuario. Los "pending" esperan selección manual.
        if item.get("estado") == "queued":
            _start_job(item, items)
            return True
    return False


def _sync_statuses(items: list) -> bool:
    """Actualiza estado de items 'generating' leyendo jobs en memoria. Devuelve True si hubo cambios."""
    dirty = False
    for item in items:
        if item.get("estado") != "generating" or not item.get("job_id"):
            continue
        try:
            with _server_jobs_lock:
                job = _server_jobs.get(item["job_id"])
            if job is None:
                item["estado"] = "failed"
                item["error"] = "Job perdido tras reinicio — reintenta"
                dirty = True
                continue
            if job["status"] == "completed":
                files = job.get("output_files", [])
                item["estado"] = "ready"
                item["output_file"] = files[0] if files else None
                dirty = True
                titulo_es = _titulo_desde_guion(item["output_file"])
                if titulo_es:
                    item["titulo"] = titulo_es
                item["titulo_synced"] = True
                if item.get("auto_publish") and item.get("publish_platforms"):
                    import api.autopublisher as _autopub
                    _autopub.enqueue(
                        item_id=item["id"],
                        score=float(item.get("score_noticia") or 7.0),
                        output_file=item.get("output_file", ""),
                        titulo=item.get("titulo", ""),
                        platforms=item["publish_platforms"],
                        tipo_contenido=item.get("tipo_contenido", "noticia"),
                        tiktok_privacy=item.get("tiktok_privacy", "SELF_ONLY"),
                        categoria=item.get("categoria", ""),
                    )
            elif job["status"] == "failed":
                score = float(item.get("score_noticia") or 0)
                retries = int(item.get("retry_count") or 0)
                if score >= 7.0 and retries < 3:
                    # Alta viralidad: reintentar automáticamente
                    item["estado"] = "queued"
                    item["job_id"] = None
                    item["retry_count"] = retries + 1
                    item["error"] = f"[Auto-reintento {retries+1}/3] {job.get('error') or 'Error al generar'}"
                else:
                    item["estado"] = "failed"
                    item["error"] = job.get("error") or "Error al generar video"
                dirty = True
        except Exception:
            pass

    if dirty:
        _advance_queue(items)

    return dirty


def _build_generate_payload(item: dict, overrides: dict = None) -> dict:
    from api.prefs import load_prefs
    p = load_prefs()
    ov = overrides or {}

    tipo = item["tipo"]
    contenido = item["contenido"]
    titulo = item.get("titulo", "")

    # Normalizar: la UI guarda "edge", el CLI espera "edge-tts"
    servicio_voz = p["servicio_voz"]
    if servicio_voz == "edge":
        servicio_voz = "edge-tts"

    # musica_fondo: "" en overrides = sin música; None en overrides = usar prefs
    if "musica_fondo" in ov:
        musica_fondo = ov["musica_fondo"] or None
    else:
        musica_fondo = p["musica_fondo"]

    base = {
        "servicio_voz":       servicio_voz,
        "voz":                p["voz"] or None,
        "tipo_contenido":     p["tipo_contenido"],
        "duracion_maxima":    p["duracion_maxima"],
        "mostrar_subtitulos": ov["mostrar_subtitulos"] if "mostrar_subtitulos" in ov else p["mostrar_subtitulos"],
        "mostrar_titulo":     ov["mostrar_titulo"] if "mostrar_titulo" in ov else p["mostrar_titulo"],
        "marca":              p["marca"] or None,
        "generar_imagenes_ai": p["generar_imagenes_ai"],
        "servicio_ai":        p["servicio_ai"],
        "musica_fondo":       musica_fondo,
        "volumen_musica":     p["volumen_musica"],
        "volumen_voz":        p["volumen_voz"],
        "largo":              ov.get("largo", False),
    }

    # Solo las noticias más virales (score ≥ VIDEO_IA_UMBRAL, def. 7.5) salen con
    # vídeo IA en movimiento + portada IA (~15-20 min); el resto, en modo rápido,
    # y se pueden pasar a vídeo IA después desde la lista de vídeos.
    try:
        umbral = float(os.environ.get("VIDEO_IA_UMBRAL", "7.5"))
    except ValueError:
        umbral = 7.5
    score = float(item.get("score_noticia") or 0)
    premium = score >= umbral and not base["largo"]
    base["video_ia"] = ov.get("video_ia", premium)
    base["portada_ia"] = ov.get("portada_ia", premium)

    def _is_youtube(url: str) -> bool:
        return "youtube.com/watch" in url or "youtu.be/" in url

    if tipo == "url":
        if _is_youtube(contenido):
            return {**base, "mode": "youtube", "url": contenido, "titulo": titulo,
                    "modo_youtube": "clip", "cantidad_shorts": 1}
        return {**base, "mode": "url", "url": contenido, "titulo": titulo}
    if tipo == "texto":
        return {**base, "mode": "texto", "texto": contenido, "titulo": titulo}
    if tipo == "noticia":
        try:
            noticia = json.loads(contenido)
        except Exception:
            noticia = {}
        link = noticia.get("link", "")
        tit = noticia.get("titulo", titulo)
        fuente = noticia.get("fuente", "")
        resumen = noticia.get("resumen", "")
        gancho = noticia.get("gancho", "")
        # Texto combinado: resumen + gancho si los hay
        texto_fallback = " ".join(filter(None, [resumen, gancho])) or tit
        if link:
            if _is_youtube(link):
                return {**base, "mode": "youtube", "url": link, "titulo": tit,
                        "modo_youtube": "clip", "cantidad_shorts": 1}
            # Links de Google News RSS no son scrapeables — usar texto almacenado
            if "news.google.com" in link:
                return {**base, "mode": "texto", "texto": texto_fallback, "titulo": tit, "fuente": fuente}
            return {**base, "mode": "url", "url": link, "titulo": tit, "fuente": fuente}
        return {**base, "mode": "texto", "texto": texto_fallback, "titulo": tit, "fuente": fuente}
    return {**base, "mode": "url", "url": contenido}


# ── Queue endpoints ────────────────────────────────────────────────────────────

@router.get("/api/gestor/items")
def list_items():
    with _lock:
        items = _load(QUEUE_FILE)
    dirty = _sync_statuses(items)
    # Sincronizar títulos en español para items "ready" aún no actualizados
    for item in items:
        if item.get("estado") == "ready" and item.get("output_file") and not item.get("titulo_synced"):
            titulo_es = _titulo_desde_guion(item["output_file"])
            if titulo_es:
                item["titulo"] = titulo_es
            item["titulo_synced"] = True
            dirty = True
    # Intentar avanzar aunque nada haya cambiado (rescata items pending sin job tras reinicios)
    advanced = _advance_queue(items)
    if dirty or advanced:
        with _lock:
            _save(QUEUE_FILE, items)
    return [_enriquecer_noticia(i) for i in items]


@router.post("/api/gestor/items")
def add_item(req: QueueItemRequest):
    item = {
        "id": uuid.uuid4().hex[:8],
        "tipo": req.tipo,
        "contenido": req.contenido,
        "titulo": req.titulo,
        "estado": "pending",
        "job_id": None,
        "output_file": None,
        "youtube_url": None,
        "creado": datetime.now().isoformat(),
        "error": None,
        "auto_publish": req.auto_publish,
        "publish_platforms": req.publish_platforms,
        "tipo_contenido": req.tipo_contenido,
        "tiktok_privacy": req.tiktok_privacy,
        "hilo_id": req.hilo_id,
        "score_noticia": req.score_noticia,
        "retry_count": req.retry_count,
    }
    with _lock:
        items = _load(QUEUE_FILE)
        items.insert(0, item)
        _save(QUEUE_FILE, items)
    return item


def _output_files_for(output_file: str) -> list[Path]:
    """Devuelve todos los archivos sidecar de un output_file."""
    if not output_file:
        return []
    slug = re.sub(r'(_short\d+)?_reel\.mp4$', '', output_file)
    if not slug or slug == output_file:
        return []
    suffixes = ["_reel.mp4", "_audio.mp3", "_guion.txt", "_fuente.json",
                "_caption.txt", "_thumbnail.jpg", "_cover.jpg", "_miniatura.json", "_info.txt"]
    paths = []
    for s in suffixes:
        p = OUTPUT_DIR / f"{slug}{s}"
        if p.exists():
            paths.append(p)
    return paths


def _delete_output_files(output_file: str) -> int:
    """Borra todos los sidecars de un output_file. Devuelve bytes liberados."""
    freed = 0
    for p in _output_files_for(output_file):
        try:
            freed += p.stat().st_size
            p.unlink()
        except Exception:
            pass
    return freed


class ImportOutputRequest(BaseModel):
    filename: str
    titulo: str = ""


@router.get("/api/gestor/orphans")
def list_orphans():
    """Output files not linked to any queue item."""
    with _lock:
        items = _load(QUEUE_FILE)
    queued_outputs = {i.get("output_file") for i in items if i.get("output_file")}
    orphans = []
    for f in sorted(OUTPUT_DIR.glob("*_reel.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.name not in queued_outputs:
            titulo = _titulo_desde_guion(f.name) or f.name.replace("_music_reel.mp4", "").replace("_reel.mp4", "").replace("_", " ")
            orphans.append({
                "filename": f.name,
                "titulo": titulo,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return orphans


@router.post("/api/gestor/import-output")
def import_output(req: ImportOutputRequest):
    """Import a manually-generated output file into the gestor queue as a ready item."""
    output_path = OUTPUT_DIR / req.filename
    if not output_path.exists():
        raise HTTPException(404, "File not found")

    titulo = req.titulo.strip()
    if not titulo:
        titulo = _titulo_desde_guion(req.filename) or req.filename.replace("_music_reel.mp4", "").replace("_reel.mp4", "").replace("_", " ")

    with _lock:
        items = _load(QUEUE_FILE)
        if any(i.get("output_file") == req.filename for i in items):
            raise HTTPException(409, "Already in queue")

        item = {
            "id": uuid.uuid4().hex[:8],
            "tipo": "manual",
            "contenido": "",
            "titulo": titulo,
            "estado": "ready",
            "job_id": None,
            "output_file": req.filename,
            "youtube_url": None,
            "creado": datetime.now().isoformat(),
            "error": None,
            "auto_publish": False,
            "publish_platforms": [],
            "titulo_synced": True,
            "uploads": {},
        }
        items.insert(0, item)
        _save(QUEUE_FILE, items)
    return item


@router.post("/api/gestor/upload-video")
async def upload_video(file: UploadFile = File(...), titulo: str = Form("")):
    """Upload a manually-created video and add it to the queue as a ready item."""
    if not file.filename or not file.filename.lower().endswith(".mp4"):
        raise HTTPException(400, "Solo se aceptan archivos .mp4")

    safe_name = re.sub(r"[^\w\-.]", "_", Path(file.filename).stem).lower()
    if not safe_name.endswith("_reel"):
        safe_name += "_reel"
    dest = OUTPUT_DIR / f"{safe_name}.mp4"

    # Avoid collisions
    counter = 1
    while dest.exists():
        dest = OUTPUT_DIR / f"{safe_name}_{counter}.mp4"
        counter += 1

    content = await file.read()
    dest.write_bytes(content)

    titulo = titulo.strip() or safe_name.replace("_reel", "").replace("_", " ").title()

    with _lock:
        items = _load(QUEUE_FILE)
        item = {
            "id": uuid.uuid4().hex[:8],
            "tipo": "manual",
            "contenido": "",
            "titulo": titulo,
            "estado": "ready",
            "job_id": None,
            "output_file": dest.name,
            "youtube_url": None,
            "creado": datetime.now().isoformat(),
            "error": None,
            "auto_publish": False,
            "publish_platforms": [],
            "titulo_synced": True,
            "uploads": {},
        }
        items.insert(0, item)
        _save(QUEUE_FILE, items)
    return item


@router.delete("/api/gestor/items/{item_id}")
def delete_item(item_id: str, files: bool = False):
    freed = 0
    with _lock:
        items = _load(QUEUE_FILE)
        item = next((i for i in items if i["id"] == item_id), None)
        if files and item and item.get("output_file"):
            freed = _delete_output_files(item["output_file"])
            # Marcar que el archivo ya no existe
            item["output_file"] = None
        items = [i for i in items if i["id"] != item_id]
        _save(QUEUE_FILE, items)
    return {"ok": True, "freed_bytes": freed}


@router.post("/api/gestor/items/{item_id}/delete-files")
def delete_item_files(item_id: str):
    """Borra solo los archivos de output sin eliminar el item de la cola."""
    with _lock:
        items = _load(QUEUE_FILE)
        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            raise HTTPException(404, "Item no encontrado")
        freed = _delete_output_files(item.get("output_file", ""))
        item["output_file"] = None
        _save(QUEUE_FILE, items)
    return {"ok": True, "freed_bytes": freed}


@router.get("/api/storage/stats")
def storage_stats():
    """Estadísticas de disco del directorio output."""
    import shutil
    total_bytes = 0
    file_count = 0
    mp4_bytes = 0
    mp3_bytes = 0

    if OUTPUT_DIR.exists():
        for f in OUTPUT_DIR.iterdir():
            if f.is_file():
                sz = f.stat().st_size
                total_bytes += sz
                file_count += 1
                if f.suffix == ".mp4":
                    mp4_bytes += sz
                elif f.suffix == ".mp3":
                    mp3_bytes += sz

    disk = shutil.disk_usage(OUTPUT_DIR if OUTPUT_DIR.exists() else "/")

    # Cruzar con la cola para saber qué está subido y qué no
    with _lock:
        items = _load(QUEUE_FILE)

    uploaded_bytes = 0
    pending_bytes = 0
    for item in items:
        if not item.get("output_file"):
            continue
        item_bytes = sum(
            p.stat().st_size for p in _output_files_for(item["output_file"])
            if p.exists()
        )
        if item.get("uploads") and len(item["uploads"]) > 0:
            uploaded_bytes += item_bytes
        else:
            pending_bytes += item_bytes

    return {
        "total_bytes": total_bytes,
        "mp4_bytes": mp4_bytes,
        "mp3_bytes": mp3_bytes,
        "other_bytes": total_bytes - mp4_bytes - mp3_bytes,
        "file_count": file_count,
        "uploaded_bytes": uploaded_bytes,
        "pending_bytes": pending_bytes,
        "disk_total": disk.total,
        "disk_free": disk.free,
        "disk_used": disk.used,
    }


class CleanupRequest(BaseModel):
    mode: str           # "uploaded" | "older_than" | "all_files"
    older_than_days: int = 7
    dry_run: bool = False


@router.post("/api/storage/cleanup")
def storage_cleanup(req: CleanupRequest):
    """Limpieza bulk de archivos de output."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=req.older_than_days)

    with _lock:
        items = _load(QUEUE_FILE)
        freed = 0
        cleaned = 0

        for item in items:
            if not item.get("output_file"):
                continue
            should_clean = False

            if req.mode == "uploaded":
                # Solo borrar si tiene al menos una subida exitosa
                should_clean = bool(item.get("uploads"))
            elif req.mode == "older_than":
                # Borrar si fue creado hace más de N días y tiene subidas o está en ready
                try:
                    creado = datetime.fromisoformat(item["creado"].replace("Z", "+00:00"))
                    if creado.tzinfo is None:
                        creado = creado.replace(tzinfo=timezone.utc)
                    should_clean = creado < cutoff and item.get("estado") == "ready"
                except Exception:
                    pass
            elif req.mode == "all_files":
                should_clean = item.get("estado") == "ready"

            if should_clean:
                if not req.dry_run:
                    freed += _delete_output_files(item["output_file"])
                    item["output_file"] = None
                else:
                    freed += sum(
                        p.stat().st_size for p in _output_files_for(item["output_file"])
                        if p.exists()
                    )
                cleaned += 1

        if not req.dry_run:
            _save(QUEUE_FILE, items)

    # Huérfanos: archivos en output que no pertenecen a ningún item activo
    known_slugs = set()
    for item in items:
        if item.get("output_file"):
            slug = re.sub(r'(_short\d+)?_reel\.mp4$', '', item["output_file"])
            known_slugs.add(slug)

    orphan_bytes = 0
    orphan_count = 0
    if OUTPUT_DIR.exists():
        for f in OUTPUT_DIR.iterdir():
            if not f.is_file():
                continue
            # Calcular slug del archivo
            name = f.name
            for s in ["_reel.mp4", "_audio.mp3", "_guion.txt", "_fuente.json",
                      "_caption.txt", "_thumbnail.jpg", "_cover.jpg", "_miniatura.json", "_info.txt"]:
                if name.endswith(s):
                    slug = name[: -len(s)]
                    if slug not in known_slugs:
                        orphan_bytes += f.stat().st_size
                        orphan_count += 1
                        if not req.dry_run and req.mode == "all_files":
                            try:
                                f.unlink()
                            except Exception:
                                pass
                    break

    return {
        "cleaned_items": cleaned,
        "freed_bytes": freed + (orphan_bytes if not req.dry_run and req.mode == "all_files" else 0),
        "freed_display": freed,
        "orphan_bytes": orphan_bytes,
        "orphan_count": orphan_count,
        "dry_run": req.dry_run,
    }


@router.post("/api/gestor/items/{item_id}/generate")
def generate_item(item_id: str, overrides: Optional[GenerateOverrides] = None):
    ov = overrides.model_dump(exclude_none=True) if overrides else {}
    with _lock:
        items = _load(QUEUE_FILE)
        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            raise HTTPException(404, "Item no encontrado")
        if item["estado"] in ("generating", "queued"):
            raise HTTPException(400, "Ya está en cola o generando")

        already_generating = any(i.get("estado") == "generating" for i in items)

        if already_generating:
            item["estado"] = "queued"
            item["job_id"] = None
            item["error"] = None
            _save(QUEUE_FILE, items)
            return {"queued": True}

        _start_job(item, items, overrides=ov)
        _save(QUEUE_FILE, items)

    return {"job_id": item.get("job_id")}


class HiloAsignRequest(BaseModel):
    hilo_id: Optional[str] = None  # None = desasignar


@router.patch("/api/gestor/items/{item_id}/hilo")
def set_hilo(item_id: str, req: HiloAsignRequest):
    """Asigna o desasigna un hilo temático a un item de la cola."""
    with _lock:
        items = _load(QUEUE_FILE)
        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            raise HTTPException(404, "Item no encontrado")
        item["hilo_id"] = req.hilo_id
        _save(QUEUE_FILE, items)
    return {"ok": True, "hilo_id": req.hilo_id}


@router.patch("/api/gestor/items/{item_id}/youtube_url")
def set_youtube_url(item_id: str, req: YoutubeUrlRequest):
    hilo_id = None
    titulo_item = ""
    with _lock:
        items = _load(QUEUE_FILE)
        for i in items:
            if i["id"] == item_id:
                i["youtube_url"] = req.youtube_url or None
                hilo_id = i.get("hilo_id")
                titulo_item = i.get("titulo", "")
        _save(QUEUE_FILE, items)
    # Sincronizar URL de YouTube en el episodio del hilo
    if hilo_id and req.youtube_url:
        try:
            from api.threads import _load as _load_threads, _save as _save_threads
            with _lock:
                hilos = _load_threads()
                for h in hilos:
                    if h["id"] == hilo_id:
                        for ep in h.get("episodios", []):
                            if ep["item_id"] == item_id:
                                ep["youtube_url"] = req.youtube_url
                                ep["titulo"] = ep.get("titulo") or titulo_item
                        h["actualizado"] = datetime.now().isoformat()
                _save_threads(hilos)
        except Exception as e:
            print(f"[threads] Error sincronizando youtube_url en hilo: {e}")
    return {"ok": True}


@router.post("/api/gestor/items/{item_id}/distribute")
def distribute_item(item_id: str, req: DistributeRequest):
    """Distribuye el enlace de YouTube del item a las plataformas indicadas."""
    with _lock:
        items = _load(QUEUE_FILE)
        item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "Item no encontrado")

    youtube_url = item.get("youtube_url", "")
    fallback_texto = req.texto or f"{item.get('titulo', '')}\n\n▶️ {youtube_url}"

    results: dict = {}

    for platform in req.platforms:
        texto = req.textos.get(platform) or fallback_texto
        try:
            if platform == "telegram":
                from telegram_uploader import enviar_mensaje as tg_msg
                r = tg_msg(texto)
                results["telegram"] = {"ok": True, "message_id": r.get("message_id")}

            elif platform == "x":
                from x_uploader import publicar_tweet
                r = publicar_tweet(texto)
                results["x"] = {"ok": True, "url": r.get("url")}

            elif platform == "whatsapp":
                from whatsapp_uploader import enviar_mensaje as wa_msg
                r = wa_msg(texto)
                results["whatsapp"] = {"ok": True}

            else:
                results[platform] = {"ok": False, "error": "Plataforma no soportada para distribución de enlaces"}

        except Exception as e:
            results[platform] = {"ok": False, "error": str(e)}

    # Registrar historial en el item
    with _lock:
        items = _load(QUEUE_FILE)
        for i in items:
            if i["id"] == item_id:
                i.setdefault("distribute_log", []).insert(0, {
                    "ts": datetime.now().isoformat(),
                    "platforms": req.platforms,
                    "results": results,
                })
        _save(QUEUE_FILE, items)

    return {"results": results}


@router.post("/api/gestor/items/{item_id}/retry")
def retry_item(item_id: str, overrides: Optional[GenerateOverrides] = None):
    with _lock:
        items = _load(QUEUE_FILE)
        for i in items:
            if i["id"] == item_id:
                i["estado"] = "pending"
                i["job_id"] = None
                i["output_file"] = None
                i["error"] = None
        _save(QUEUE_FILE, items)
    return generate_item(item_id, overrides=overrides)


# ── Scheduled endpoints ────────────────────────────────────────────────────────

@router.get("/api/gestor/scheduled")
def list_scheduled():
    with _lock:
        return _load(SCHEDULED_FILE)


@router.post("/api/gestor/scheduled")
def create_scheduled(req: ScheduleRequest):
    # Guard: warn if already confirmed uploaded to any of these platforms
    if req.queue_item_id and not req.force:
        with _lock:
            queue_items = _load(QUEUE_FILE)
        src = next((i for i in queue_items if i["id"] == req.queue_item_id), None)
        if src:
            already = {p: src["uploads"][p] for p in req.platforms if p in src.get("uploads", {})}
            if already:
                raise HTTPException(409, {
                    "detail": "already_uploaded",
                    "platforms": already,
                    "titulo": src.get("titulo", ""),
                })

    item = {
        "id": uuid.uuid4().hex[:8],
        "output_file": req.output_file,
        "titulo": req.titulo,
        "descripcion": req.descripcion,
        "tiktok_caption": req.tiktok_caption,
        "instagram_caption": req.instagram_caption,
        "x_caption": req.x_caption,
        "platforms": req.platforms,
        "tipo_contenido": req.tipo_contenido,
        "tiktok_privacy": req.tiktok_privacy,
        "publish_at": req.publish_at,
        "estado": "scheduled" if req.publish_at else "pending_publish",
        "results": {},
        "creado": datetime.now().isoformat(),
        "publish_job_id": None,
        "error": None,
        "queue_item_id": req.queue_item_id,
        "auto_distribute": req.auto_distribute,
        "distribute_platforms": req.distribute_platforms,
        "distribute_textos": req.distribute_textos,
        "forced_reupload": req.force,
    }
    with _lock:
        items = _load(SCHEDULED_FILE)
        items.insert(0, item)
        _save(SCHEDULED_FILE, items)

    # Si publish_at es None o ya pasó → publicar de inmediato en background
    if not req.publish_at or _is_past(req.publish_at):
        threading.Thread(target=_publish_scheduled, args=(item["id"],), daemon=True).start()

    return item


@router.delete("/api/gestor/scheduled/{item_id}")
def cancel_scheduled(item_id: str):
    with _lock:
        items = _load(SCHEDULED_FILE)
        items = [i for i in items if i["id"] != item_id]
        _save(SCHEDULED_FILE, items)
    return {"ok": True}


# ── Background scheduler ───────────────────────────────────────────────────────

def _is_past(iso: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= dt
    except Exception:
        return False


def _send_telegram_confirmation(titulo: str, platforms: list, results: dict):
    try:
        from telegram_uploader import enviar_mensaje as tg_msg
        ok_p = [p for p, r in results.items() if r.get("status") == "ok"]
        fail_p = [p for p, r in results.items() if r.get("status") != "ok"]
        lines = [f"Reel publicado: {titulo}"]
        if ok_p:
            lines.append(f"Plataformas: {', '.join(ok_p)}")
        yt_url = (results.get("youtube") or {}).get("url", "")
        if yt_url:
            lines.append(yt_url)
        if fail_p:
            lines.append(f"Fallo en: {', '.join(fail_p)}")
        tg_msg("\n".join(lines))
    except Exception as e:
        print(f"[gestor] Telegram confirmation error: {e}")


def _auto_publish_item(item_id: str, output_file: str, titulo: str,
                       platforms: list, tipo_contenido: str, tiktok_privacy: str):
    """Publica automáticamente un item listo y envía confirmación Telegram."""
    if not output_file:
        return
    try:
        resp = http.post("http://localhost:8000/api/publish", json={
            "filename":           output_file,
            "titulo":             titulo,
            "descripcion":        titulo,
            "tiktok_caption":     titulo,
            "instagram_caption":  titulo,
            "x_caption":          titulo,
            "platforms":          platforms,
            "tipo_contenido":     tipo_contenido,
            "tiktok_privacy":     tiktok_privacy,
        }, timeout=15)
        resp.raise_for_status()
        pub_job_id = resp.json()["job_id"]

        with _lock:
            items = _load(QUEUE_FILE)
            for i in items:
                if i["id"] == item_id:
                    i["pub_job_id"] = pub_job_id
            _save(QUEUE_FILE, items)

        job_results = {}
        for _ in range(450):
            time.sleep(2)
            try:
                r = http.get(f"http://localhost:8000/api/publish/{pub_job_id}", timeout=5)
                if r.ok:
                    job = r.json()
                    if job["status"] != "running":
                        job_results = job.get("results", {})
                        break
            except Exception:
                pass

        with _lock:
            items = _load(QUEUE_FILE)
            for i in items:
                if i["id"] == item_id:
                    uploads = i.get("uploads", {})
                    yt_url = ""
                    for platform, result in job_results.items():
                        if result.get("status") == "ok":
                            url_val = result.get("url") or result.get("video_id") or True
                            prev = uploads.get(platform, {})
                            uploads[platform] = {
                                "url": url_val,
                                "at": datetime.now().isoformat(),
                                "reupload_count": (prev.get("reupload_count", 0) + 1) if prev else 0,
                            }
                            if platform == "youtube" and result.get("url"):
                                yt_url = result["url"]
                    i["uploads"] = uploads
                    if yt_url:
                        i["youtube_url"] = yt_url
            _save(QUEUE_FILE, items)

        _send_telegram_confirmation(titulo, platforms, job_results)

    except Exception as e:
        print(f"[gestor] Auto-publish error for {item_id}: {e}")


def _post_publish_actions(scheduled_item: dict, job_results: dict):
    """Acciones tras publicar: guarda URL de YouTube y registro de uploads en el item de cola."""
    yt_result = job_results.get("youtube", {})
    yt_url = yt_result.get("url", "")

    queue_item_id = scheduled_item.get("queue_item_id", "")
    if queue_item_id:
        try:
            with _lock:
                items = _load(QUEUE_FILE)
                for i in items:
                    if i["id"] == queue_item_id:
                        if yt_url:
                            i["youtube_url"] = yt_url
                        # Registrar qué plataformas se subieron con éxito
                        uploads = i.get("uploads", {})
                        for platform, result in job_results.items():
                            if result.get("status") == "ok":
                                prev = uploads.get(platform, {})
                                uploads[platform] = {
                                    "url": result.get("url") or result.get("video_id") or True,
                                    "at": datetime.now().isoformat(),
                                    "reupload_count": (prev.get("reupload_count", 0) + 1) if prev else 0,
                                }
                        i["uploads"] = uploads
                _save(QUEUE_FILE, items)
        except Exception as e:
            print(f"[gestor] No se pudo guardar youtube_url en item {queue_item_id}: {e}")

    # Auto-distribución a Telegram/X/WhatsApp
    if not scheduled_item.get("auto_distribute"):
        return
    platforms = scheduled_item.get("distribute_platforms") or []
    if not platforms:
        return

    textos: dict = dict(scheduled_item.get("distribute_textos") or {})
    titulo = scheduled_item.get("titulo", "")
    url_line = f"▶️ {yt_url}" if yt_url else ""

    for platform in platforms:
        texto = textos.get(platform) or f"{titulo}\n\n{url_line}".strip()
        if not texto.strip():
            continue
        # Añadir URL de YouTube si no está ya en el texto
        if yt_url and yt_url not in texto:
            texto = f"{texto}\n\n{url_line}".strip()
        try:
            if platform == "telegram":
                from telegram_uploader import enviar_mensaje as tg_msg
                tg_msg(texto)
                print(f"[gestor] Auto-distribuido a Telegram")
            elif platform == "x":
                from x_uploader import publicar_tweet
                publicar_tweet(texto)
                print(f"[gestor] Auto-distribuido a X")
            elif platform == "whatsapp":
                from whatsapp_uploader import enviar_mensaje as wa_msg
                wa_msg(texto)
                print(f"[gestor] Auto-distribuido a WhatsApp")
        except Exception as e:
            print(f"[gestor] Error distribuyendo a {platform}: {e}")

    # Distribuir a Telegram grupos y Reddit cuando hay URL de YouTube
    if yt_url:
        try:
            from distribuidor import distribuir as _dist
            _dist(
                titulo=scheduled_item.get("titulo", ""),
                yt_url=yt_url,
                categoria=scheduled_item.get("categoria", ""),
            )
        except Exception as e:
            print(f"[gestor] Distribuidor: {e}")


def _publish_scheduled(item_id: str):
    with _lock:
        items = _load(SCHEDULED_FILE)
        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            return
        if item["estado"] not in ("scheduled", "pending_publish"):
            return
        item["estado"] = "publishing"
        _save(SCHEDULED_FILE, items)

    try:
        resp = http.post("http://localhost:8000/api/publish", json={
            "filename": item["output_file"],
            "titulo": item["titulo"],
            "descripcion": item["descripcion"],
            "tiktok_caption": item.get("tiktok_caption", ""),
            "instagram_caption": item.get("instagram_caption", ""),
            "x_caption": item.get("x_caption", ""),
            "platforms": item["platforms"],
            "tipo_contenido": item["tipo_contenido"],
            "tiktok_privacy": item.get("tiktok_privacy", "SELF_ONLY"),
        }, timeout=15)
        resp.raise_for_status()
        pub_job_id = resp.json()["job_id"]

        with _lock:
            items = _load(SCHEDULED_FILE)
            for i in items:
                if i["id"] == item_id:
                    i["publish_job_id"] = pub_job_id
            _save(SCHEDULED_FILE, items)

        # Poll until done (max 15 min)
        not_found_streak = 0
        for _ in range(450):
            time.sleep(2)
            try:
                r = http.get(f"http://localhost:8000/api/publish/{pub_job_id}", timeout=5)
                if r.ok:
                    not_found_streak = 0
                    job = r.json()
                    if job["status"] != "running":
                        estado = "done" if job["status"] == "completed" else "failed"
                        job_results = job.get("results", {})
                        with _lock:
                            items = _load(SCHEDULED_FILE)
                            for i in items:
                                if i["id"] == item_id:
                                    i["estado"] = estado
                                    i["results"] = job_results
                            _save(SCHEDULED_FILE, items)
                        if estado == "done":
                            _post_publish_actions(item, job_results)
                        return
                elif r.status_code == 404:
                    not_found_streak += 1
                    if not_found_streak >= 3:
                        raise RuntimeError(f"Publish job {pub_job_id} no encontrado (reinicio del backend?)")
            except RuntimeError:
                raise
            except Exception:
                pass

    except Exception as e:
        with _lock:
            items = _load(SCHEDULED_FILE)
            for i in items:
                if i["id"] == item_id:
                    i["estado"] = "failed"
                    i["error"] = str(e)
            _save(SCHEDULED_FILE, items)


def _scheduler_loop():
    while True:
        time.sleep(30)
        try:
            with _lock:
                items = _load(SCHEDULED_FILE)
            for item in items:
                if item["estado"] == "scheduled" and item.get("publish_at") and _is_past(item["publish_at"]):
                    threading.Thread(target=_publish_scheduled, args=(item["id"],), daemon=True).start()
        except Exception:
            pass


# ── Archivo y limpieza automática ──────────────────────────────────────────────

ARCHIVE_FILE = CONFIG_DIR / "archivo_noticias.json"
CLEANUP_DAYS = 7


def _load_archive() -> list:
    try:
        if ARCHIVE_FILE.exists():
            return json.loads(ARCHIVE_FILE.read_text("utf-8"))
    except Exception:
        pass
    return []


def _save_archive(data: list):
    ARCHIVE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _leer_guion(output_file: str) -> str:
    if not output_file:
        return ""
    try:
        slug = re.sub(r'(_short\d+)?_reel\.mp4$', '', output_file)
        p = OUTPUT_DIR / f"{slug}_guion.txt"
        return p.read_text("utf-8").strip() if p.exists() else ""
    except Exception:
        return ""


def _archive_item(item: dict):
    """Guarda un item en el archivo antes de borrar sus archivos de disco."""
    guion = _leer_guion(item.get("output_file", ""))
    record = {
        "id":                item["id"],
        "titulo":            item.get("titulo", ""),
        "fuente":            item.get("fuente_noticia", ""),
        "contenido":         item.get("contenido", ""),
        "tipo":              item.get("tipo", "noticia"),
        "score_noticia":     item.get("score_noticia"),
        "guion":             guion,
        "uploads":           item.get("uploads", {}),
        "youtube_url":       item.get("youtube_url", ""),
        "publish_platforms": item.get("publish_platforms", []),
        "creado":            item.get("creado", ""),
        "archivado":         datetime.now(timezone.utc).isoformat(),
        "puede_regenerar":   bool(item.get("contenido")),
    }
    with _lock:
        archivo = _load_archive()
        archivo.insert(0, record)
        archivo = archivo[:500]
        _save_archive(archivo)


def _cleanup_uploaded_old(dry_run: bool = False) -> dict:
    """Borra archivos de items subidos con más de CLEANUP_DAYS días. Archiva antes de borrar."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CLEANUP_DAYS)).isoformat()
    freed = 0
    archived = 0

    with _lock:
        items = _load(QUEUE_FILE)
        for item in items:
            if not item.get("output_file"):
                continue
            if not item.get("uploads"):
                continue
            if item.get("creado", "9999") > cutoff:
                continue
            # Tiene archivos, está subido y lleva más de 7 días
            if not dry_run:
                _archive_item(item)
                freed += _delete_output_files(item["output_file"])
                item["output_file"] = None
                item["archivado"] = True
            archived += 1
        if not dry_run:
            _save(QUEUE_FILE, items)

    print(f"[cleanup] {archived} items archivados, {freed/1024/1024:.1f} MB liberados")
    return {"archived": archived, "freed_bytes": freed}


def _cleanup_loop():
    """Corre cada 6 horas para limpiar archivos subidos con más de 7 días."""
    time.sleep(300)  # espera 5 min al arranque
    while True:
        try:
            _cleanup_uploaded_old()
        except Exception as e:
            print(f"[cleanup] Error: {e}")
        time.sleep(6 * 3600)


threading.Thread(target=_cleanup_loop, daemon=True, name="cleanup-loop").start()


# ── Endpoints de archivo ────────────────────────────────────────────────────────

@router.get("/api/gestor/archive")
def list_archive(limit: int = 100):
    with _lock:
        archivo = _load_archive()
    return archivo[:limit]


@router.post("/api/gestor/archive/{record_id}/regenerate")
def regenerate_archived(record_id: str):
    """Vuelve a encolar un item archivado para regenerarlo."""
    with _lock:
        archivo = _load_archive()
    record = next((r for r in archivo if r["id"] == record_id), None)
    if not record:
        raise HTTPException(404, "Registro no encontrado en archivo")
    if not record.get("puede_regenerar") or not record.get("contenido"):
        raise HTTPException(400, "No hay contenido suficiente para regenerar")

    req = QueueItemRequest(
        tipo=record.get("tipo", "noticia"),
        contenido=record["contenido"],
        titulo=record.get("titulo", ""),
        auto_publish=bool(record.get("publish_platforms")),
        publish_platforms=record.get("publish_platforms", []),
        tipo_contenido="noticia",
        score_noticia=record.get("score_noticia"),
    )
    return add_item(req)


@router.post("/api/storage/cleanup-auto")
def manual_cleanup(dry_run: bool = False):
    """Ejecuta la limpieza automática manualmente."""
    result = _cleanup_uploaded_old(dry_run=dry_run)
    return {**result, "dry_run": dry_run}


threading.Thread(target=_scheduler_loop, daemon=True, name="gestor-scheduler").start()
