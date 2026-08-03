"""
FastAPI backend para Reel News Bot.
Expone endpoints para lanzar jobs de generación de video y consultar su estado.
"""
import os
import re
import sys
import uuid
import tempfile
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

UPLOADS_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "_uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

API_DIR = Path(__file__).parent
CORE_DIR = API_DIR.parent
OUTPUT_DIR = CORE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Reel News Bot API")

from api.hotspots import router as hotspots_router
from api.library import router as library_router, LIBRARY_DIR
from api.templates import router as templates_router
from api.music import router as music_router, MUSIC_DIR
app.include_router(hotspots_router)
app.include_router(library_router)
app.include_router(templates_router)
app.include_router(music_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")
app.mount("/library-files", StaticFiles(directory=str(LIBRARY_DIR)), name="library")
app.mount("/music-files", StaticFiles(directory=str(MUSIC_DIR)), name="music")

jobs: dict = {}
jobs_lock = threading.Lock()


class GenerateRequest(BaseModel):
    mode: str  # url | texto | youtube | musica | tema
    url: Optional[str] = None
    texto: Optional[str] = None
    titulo: Optional[str] = None
    fuente: Optional[str] = None
    modo_youtube: str = "clip"
    cantidad_shorts: int = 1
    cookies_browser: Optional[str] = None
    artista: Optional[str] = None
    tema: Optional[str] = None
    duracion_maxima: int = 60
    # Imágenes de fondo
    imagenes_subidas: list = []
    generar_imagenes_ai: bool = False
    servicio_ai: str = "pollinations"
    # Avatar lip sync
    avatar_imagen: Optional[str] = None
    avatar_servicio: str = "auto"
    # Voz TTS
    servicio_voz: str = "auto"
    voz: Optional[str] = None
    # Marca/watermark en el video (None = sin marca)
    marca: Optional[str] = None
    mostrar_titulo: bool = True
    # Música de fondo
    musica_fondo: Optional[str] = None   # filename en _music/
    volumen_musica: float = 0.3
    volumen_voz: float = 1.0
    # Texto libre visible en el video (nombre canción, fuente, subtítulo…)
    texto_personalizado: Optional[str] = None


def _build_cli_args(req: GenerateRequest, texto_tmp: Optional[str] = None) -> list:
    args = ["--duracion-maxima", str(req.duracion_maxima)]
    if req.mode == "url":
        args += ["--url", req.url]
    elif req.mode == "texto":
        args += ["--archivo", texto_tmp]
    elif req.mode == "youtube":
        args += ["--youtube", req.url,
                 "--modo-youtube", req.modo_youtube,
                 "--cantidad-shorts", str(req.cantidad_shorts)]
        if req.cookies_browser:
            args += ["--cookies-browser", req.cookies_browser]
    elif req.mode == "musica":
        args += ["--musica", req.url]
        if req.artista:
            args += ["--artista", req.artista]
        if req.cookies_browser:
            args += ["--cookies-browser", req.cookies_browser]
    elif req.mode == "tema":
        args += ["--tema", req.tema]

    # Imágenes
    for ruta in req.imagenes_subidas:
        args += ["--imagen", ruta]
    if req.generar_imagenes_ai:
        args += ["--generar-imagenes-ai", "--servicio-ai", req.servicio_ai]

    if req.avatar_imagen:
        args += ["--avatar", req.avatar_imagen, "--avatar-servicio", req.avatar_servicio]

    args += ["--servicio-voz", req.servicio_voz]
    if req.voz:
        args += ["--voz", req.voz]
    if req.marca:
        args += ["--marca", req.marca]
    if not req.mostrar_titulo:
        args += ["--sin-titulo"]
    if req.musica_fondo:
        music_path = CORE_DIR / "_music" / req.musica_fondo
        if music_path.exists():
            args += ["--musica-fondo", str(music_path)]
    args += ["--volumen-musica", str(req.volumen_musica)]
    args += ["--volumen-voz", str(req.volumen_voz)]
    if req.texto_personalizado and req.texto_personalizado.strip():
        args += ["--texto-personalizado", req.texto_personalizado.strip()]

    return args


def _run_job(job_id: str, req: GenerateRequest):
    texto_tmp = None
    log_path = CORE_DIR / f"_job_{job_id}.log"

    try:
        if req.mode == "texto":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False,
                dir=str(CORE_DIR), encoding="utf-8"
            ) as f:
                texto_tmp = f.name
                f.write(f"TITULO: {req.titulo or 'Sin título'}\n")
                if req.fuente:
                    f.write(f"FUENTE: {req.fuente}\n")
                f.write(f"\n{req.texto}")

        cli_args = _build_cli_args(req, texto_tmp)
        cmd = [sys.executable, str(CORE_DIR / "main.py")] + cli_args

        with jobs_lock:
            jobs[job_id]["status"] = "running"
            jobs[job_id]["log_file"] = str(log_path)
            jobs[job_id]["started_at"] = datetime.now().isoformat()

        with open(log_path, "w", encoding="utf-8") as lf:
            proc = subprocess.Popen(
                cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(CORE_DIR)
            )

        returncode = proc.wait()
        log_content = log_path.read_text(encoding="utf-8", errors="replace")

        output_files = re.findall(r"Video generado: (.+\.mp4)", log_content, re.UNICODE)

        has_output = bool(output_files)
        # Only fail if process crashed OR there were errors AND no video at all
        critical_error = (
            "raise " in log_content or
            "Error\n" in log_content or
            ("Traceback" in log_content and not has_output)
        )
        if returncode != 0 or (critical_error and not has_output):
            final_status = "failed"
        else:
            final_status = "completed"

        with jobs_lock:
            jobs[job_id]["logs"] = log_content
            jobs[job_id]["output_files"] = [Path(p).name for p in output_files]
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
            jobs[job_id]["status"] = final_status
            jobs[job_id]["log_file"] = None

    except Exception as e:
        import traceback
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["logs"] = traceback.format_exc()
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
            jobs[job_id]["log_file"] = None
    finally:
        if texto_tmp:
            try:
                os.unlink(texto_tmp)
            except Exception:
                pass
        try:
            log_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/api/generate")
def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    labels = {
        "url": f"URL: {req.url}",
        "texto": f"Artículo: {req.titulo}",
        "youtube": f"YouTube: {req.url}",
        "musica": f"Música: {req.url}",
        "tema": f"Tema: {req.tema}",
    }
    job_id = uuid.uuid4().hex[:8]

    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "label": labels.get(req.mode, req.mode),
            "mode": req.mode,
            "logs": "",
            "log_file": None,
            "output_files": [],
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
        }

    thread = threading.Thread(target=_run_job, args=(job_id, req), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.get("/api/jobs")
def list_jobs():
    with jobs_lock:
        snapshot = list(jobs.values())
    return sorted(snapshot, key=lambda j: j["created_at"], reverse=True)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = dict(job)
    log_file = job.get("log_file")
    if log_file and job["status"] == "running":
        try:
            result["logs"] = Path(log_file).read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return result


@app.get("/api/output")
def list_output():
    files = []
    for f in sorted(OUTPUT_DIR.glob("*_reel.mp4"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        files.append({
            "filename": f.name,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return files


@app.get("/api/videos/{filename}")
def get_video(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(file_path), media_type="video/mp4")


@app.post("/api/upload")
async def upload_images(files: list[UploadFile] = File(...)):
    """Sube imágenes para usar como fondo. Devuelve lista de rutas locales."""
    rutas = []
    for f in files:
        if not f.content_type or not f.content_type.startswith("image/"):
            continue
        ext = Path(f.filename or "img").suffix or ".jpg"
        nombre = UPLOADS_DIR / f"{uuid.uuid4().hex[:8]}{ext}"
        content = await f.read()
        with open(nombre, "wb") as out:
            out.write(content)
        rutas.append(str(nombre))
    return {"rutas": rutas}


@app.get("/api/avatar/status")
def avatar_status():
    """Devuelve si SadTalker y D-ID están disponibles."""
    sys.path.insert(0, str(CORE_DIR))
    try:
        from avatar_generator import estado
        return estado()
    except Exception:
        return {"sadtalker": False, "did": False}


class DiscoverRequest(BaseModel):
    tema: Optional[str] = None
    pais: str = "ES"
    variado: bool = True
    n_retornar: int = 8


@app.post("/api/news/discover")
async def news_discover(req: DiscoverRequest):
    """Busca noticias y devuelve propuestas de reels rankeadas por potencial viral."""
    from fastapi.concurrency import run_in_threadpool

    sys.path.insert(0, str(CORE_DIR))

    def _buscar():
        from news_curator import buscar_y_curar
        return buscar_y_curar(
            tema=req.tema or None,
            pais=req.pais,
            variado=req.variado,
            n_retornar=req.n_retornar,
        )

    try:
        resultados = await run_in_threadpool(_buscar)
        return {"noticias": resultados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PreviewTtsRequest(BaseModel):
    servicio: str = "auto"
    voz: Optional[str] = None
    texto: str = "Hola, esta es una prueba de voz para el reel. ¿Qué te parece cómo suena?"


@app.post("/api/tts/preview")
async def tts_preview(req: PreviewTtsRequest):
    """Genera y devuelve un audio de prueba con la voz seleccionada."""
    import io
    import tempfile
    from fastapi.responses import StreamingResponse
    from fastapi.concurrency import run_in_threadpool

    sys.path.insert(0, str(CORE_DIR))

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = tmp.name
    tmp.close()

    def _generar():
        from tts import generar_audio
        return generar_audio(req.texto, tmp_path, servicio=req.servicio, voz=req.voz)

    try:
        ruta = await run_in_threadpool(_generar)
        with open(ruta, "rb") as f:
            audio_bytes = f.read()
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.get("/api/tts/status")
def tts_status():
    """Devuelve qué motores TTS están disponibles."""
    sys.path.insert(0, str(CORE_DIR))
    try:
        from tts import estado_tts
        return estado_tts()
    except Exception:
        return {"edge_tts": False, "elevenlabs": False}


VOCES_ELEVENLABS_FALLBACK = [
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (hombre, inglés/multilingüe)"},
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel (mujer, inglés/multilingüe)"},
    {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi (mujer, expresiva)"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella (mujer, suave)"},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni (hombre, articulado)"},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli (mujer, joven)"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh (hombre, profundo)"},
    {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold (hombre, robusto)"},
    {"id": "pqHfZKP75CvOlQylNhV4", "name": "Bill (hombre, maduro)"},
    {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam (hombre, periodista)"},
]


@app.get("/api/tts/voices")
def tts_voices(servicio: str = "edge-tts"):
    """Devuelve las voces disponibles para el servicio indicado."""
    sys.path.insert(0, str(CORE_DIR))
    if servicio == "elevenlabs":
        try:
            from tts import listar_voces_elevenlabs
            voces = listar_voces_elevenlabs()
            if voces:
                return {"voices": voces}
            return {"voices": VOCES_ELEVENLABS_FALLBACK, "fallback": True}
        except Exception:
            return {"voices": VOCES_ELEVENLABS_FALLBACK, "fallback": True}
    else:
        from tts import VOCES_EDGE_ES
        return {"voices": VOCES_EDGE_ES}


@app.post("/api/preview-image")
async def preview_image(prompt: str, seed: int = 42):
    """Previsualiza una imagen generada con IA (Pollinations.ai)."""
    import urllib.parse
    prompt_enc = urllib.parse.quote(f"{prompt}, cinematic, dark background, vertical portrait")
    url = f"https://image.pollinations.ai/prompt/{prompt_enc}?width=540&height=960&seed={seed}&nologo=true&model=flux"
    return {"url": url}
