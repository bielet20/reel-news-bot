"""
api/publish.py
Publicación de videos generados a YouTube, TikTok e Instagram.
"""
import os
import sys
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

CORE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = CORE_DIR / "output"

_jobs: dict = {}
_lock = threading.Lock()


class PublishRequest(BaseModel):
    filename: str
    titulo: str = ""
    descripcion: str = ""
    tiktok_caption: str = ""
    instagram_caption: str = ""
    x_caption: str = ""
    platforms: list[str]          # ["youtube", "tiktok", "instagram", "telegram", "whatsapp", "x"]
    tipo_contenido: str = "noticia"  # youtube: noticia | curiosidad
    tiktok_privacy: str = "SELF_ONLY"


@router.post("/api/publish")
def publish_video(req: PublishRequest):
    file_path = OUTPUT_DIR / req.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de video no encontrado")
    if not req.platforms:
        raise HTTPException(status_code=400, detail="Selecciona al menos una plataforma")

    job_id = uuid.uuid4().hex[:8]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "filename": req.filename,
            "platforms": req.platforms,
            "status": "running",
            "results": {p: {"status": "pending"} for p in req.platforms},
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        }

    threading.Thread(target=_do_publish, args=(job_id, req, file_path), daemon=True).start()
    return {"job_id": job_id}


def _do_publish(job_id: str, req: PublishRequest, file_path: Path):
    sys.path.insert(0, str(CORE_DIR))
    results = {}
    youtube_url = ""

    # YouTube primero para que su URL llegue al texto del canal de WA
    ordered = ["youtube"] + [p for p in req.platforms if p != "youtube"]

    for platform in ordered:
        if platform not in req.platforms:
            continue
        with _lock:
            _jobs[job_id]["results"][platform] = {"status": "uploading"}

        try:
            if platform == "youtube":
                r = _upload_youtube(req, file_path)
                youtube_url = r.get("url", "")
            elif platform == "tiktok":
                r = _upload_tiktok(req, file_path)
            elif platform == "instagram":
                r = _upload_instagram(req, file_path)
            elif platform == "telegram":
                r = _upload_telegram(req, file_path)
            elif platform == "whatsapp":
                r = _upload_whatsapp(req, file_path)
            elif platform == "x":
                r = _upload_x(req, file_path)
            elif platform == "facebook":
                r = _upload_facebook(req, file_path)
            elif platform == "whatsapp_canal":
                r = _upload_whatsapp_canal(req, file_path, youtube_url=youtube_url)
            else:
                r = {"status": "error", "error": "Plataforma desconocida"}
        except Exception as e:
            r = {"status": "error", "error": str(e)}

        results[platform] = r
        with _lock:
            _jobs[job_id]["results"][platform] = r

    all_failed = all(r.get("status") == "error" for r in results.values())
    with _lock:
        _jobs[job_id]["status"] = "failed" if all_failed else "completed"
        _jobs[job_id]["completed_at"] = datetime.now().isoformat()


def _upload_youtube(req: PublishRequest, file_path: Path) -> dict:
    from accounts_manager import load_token
    from youtube_uploader import subir_video

    token = load_token("youtube")
    old_env: dict[str, Optional[str]] = {}

    if token:
        for key, val in {
            "YOUTUBE_CLIENT_ID": token.get("client_id", ""),
            "YOUTUBE_CLIENT_SECRET": token.get("client_secret", ""),
            "YOUTUBE_REFRESH_TOKEN": token.get("refresh_token", ""),
        }.items():
            old_env[key] = os.environ.get(key)
            if val:
                os.environ[key] = val

    try:
        slug = file_path.stem.replace("_reel", "")
        thumb = OUTPUT_DIR / f"{slug}_thumbnail.jpg"
        resultado = subir_video(
            video_path=str(file_path),
            titulo=req.titulo or file_path.stem,
            tipo=req.tipo_contenido,
            thumbnail_path=str(thumb) if thumb.exists() else None,
        )
        return {"status": "ok", "url": resultado["url"], "video_id": resultado["video_id"]}
    except Exception as e:
        from youtube_uploader import _yt_error_message
        raise RuntimeError(_yt_error_message(e)) from e
    finally:
        if token:
            for key, val in old_env.items():
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val


def _upload_tiktok(req: PublishRequest, file_path: Path) -> dict:
    from tiktok_uploader import subir_video
    caption = req.tiktok_caption or req.descripcion or req.titulo or file_path.stem
    result = subir_video(
        str(file_path),
        titulo=caption,
        privacy=req.tiktok_privacy,
    )
    return {"status": "ok", "publish_id": result.get("publish_id")}


def _upload_instagram(req: PublishRequest, file_path: Path) -> dict:
    from instagram_uploader import subir_video
    caption = req.instagram_caption or req.descripcion or req.titulo or file_path.stem
    result = subir_video(str(file_path), caption=caption)
    return {"status": "ok", "media_id": result.get("media_id"), "url": result.get("url", "")}


def _upload_telegram(req: PublishRequest, file_path: Path) -> dict:
    from telegram_uploader import subir_video
    caption = req.descripcion or req.titulo or file_path.stem
    result = subir_video(str(file_path), caption=caption)
    return {"status": "ok", "message_id": result.get("message_id")}


def _upload_whatsapp(req: PublishRequest, file_path: Path) -> dict:
    from whatsapp_uploader import subir_status
    caption = req.descripcion or req.titulo or file_path.stem
    result = subir_status(str(file_path), caption=caption)
    return {"status": "ok", **result}


def _upload_x(req: PublishRequest, file_path: Path) -> dict:
    from x_uploader import subir_video
    texto = req.x_caption or req.descripcion or req.titulo or file_path.stem
    try:
        result = subir_video(str(file_path), texto=texto)
        return {"status": "ok", "url": result.get("url"), "tweet_id": result.get("tweet_id")}
    except Exception as e:
        from x_uploader import _x_error_message
        raise RuntimeError(_x_error_message(e)) from e


def _upload_facebook(req: PublishRequest, file_path: Path) -> dict:
    from facebook_uploader import subir_video
    titulo = req.titulo or file_path.stem
    descripcion = req.descripcion or ""
    result = subir_video(str(file_path), titulo=titulo, descripcion=descripcion)
    return {"status": "ok", "url": result.get("url"), "video_id": result.get("video_id")}


def _upload_whatsapp_canal(req: PublishRequest, file_path: Path, youtube_url: str = "") -> dict:
    from whatsapp_uploader import subir_canal
    from accounts_manager import load_token
    token = load_token("whatsapp_canal") or {}
    channel_jid = token.get("channel_jid") or None
    partes = [req.titulo or req.descripcion or file_path.stem]
    if req.descripcion and req.descripcion != req.titulo:
        partes.append(req.descripcion)
    if youtube_url:
        partes.append(f"▶️ {youtube_url}")
    caption = "\n\n".join(filter(None, partes))
    result = subir_canal(str(file_path), caption=caption, channel_jid=channel_jid)
    return {"status": "ok", **result}


@router.get("/api/publish/caption")
def get_caption(filename: str):
    """Genera captions optimizados para cada plataforma a partir del guion del reel."""
    slug = filename.replace("_reel.mp4", "")
    guion_path  = OUTPUT_DIR / f"{slug}_guion.txt"
    fuente_path = OUTPUT_DIR / f"{slug}_fuente.json"

    guion  = guion_path.read_text("utf-8").strip()  if guion_path.exists()  else ""
    fuente: dict = {}
    if fuente_path.exists():
        import json as _json
        try:
            fuente = _json.loads(fuente_path.read_text("utf-8"))
        except Exception:
            pass

    # Extraer título y cuerpo del guion
    lines = [l.strip() for l in guion.splitlines() if l.strip()]
    titulo = ""
    cuerpo = ""
    for line in lines:
        if line.startswith("Titulo:"):
            titulo = line.replace("Titulo:", "").strip()
        elif not line.startswith(("Fuente:", "Link:")):
            cuerpo += line + " "
    cuerpo = cuerpo.strip()
    if not titulo:
        titulo = slug.replace("-", " ").title()

    # Primera frase del guion como hook
    hook = cuerpo.split(".")[0].strip() if cuerpo else titulo

    # Detectar categoría para hashtags
    texto_lower = (titulo + " " + cuerpo).lower()
    hashtags = _hashtags_para(texto_lower)

    medio = fuente.get("origen") or fuente.get("fuente", "")
    url   = fuente.get("url_original", "")
    documentacion = fuente.get("documentacion", "")
    verificadores = fuente.get("verificadores") or []

    # ── TikTok: corto, gancho fuerte, max ~150 chars título + hashtags ──
    tiktok_titulo = (hook[:147] + "…") if len(hook) > 150 else hook
    tiktok_caption = (
        f"{tiktok_titulo}\n\n"
        f"{'📰 ' + medio + ' | ' if medio else ''}"
        f"Sígueme para más noticias en 60 segundos ⚡\n\n"
        f"{' '.join(hashtags[:10])}"
    ).strip()

    # ── Instagram: más largo, emojis, todos los hashtags ──
    ig_caption = (
        f"🔥 {titulo.upper()}\n\n"
        f"{cuerpo[:400]}{'…' if len(cuerpo) > 400 else ''}\n\n"
        f"{'📰 Fuente: ' + medio + chr(10) if medio else ''}"
        f"{'✅ ' + documentacion + chr(10) if documentacion else ''}"
        f"{'🔎 Contrastada por: ' + ', '.join(verificadores) + chr(10) if verificadores else ''}"
        f"{'🔗 ' + url + chr(10) if url else ''}"
        f"\n¿Qué opinas? 👇 Cuéntame en los comentarios\n"
        f"🔔 Sígueme para noticias verificadas cada día\n\n"
        f"{' '.join(hashtags)}"
    ).strip()

    # ── X (Twitter): máx 280 chars — hook + fuente + 5 hashtags ──
    x_hashtags = " ".join(hashtags[:5])
    x_source   = f"\n📰 {medio}" if medio else ""
    x_base     = f"{x_source}\n{x_hashtags}".strip()
    max_hook   = 280 - len(x_base) - 2
    x_hook     = (hook[:max_hook - 1] + "…") if len(hook) > max_hook else hook
    x_caption  = f"{x_hook}{x_source}\n{x_hashtags}".strip()

    # ── Descripción YouTube: leer _caption.txt si existe ──
    slug_cap = filename.replace("_reel.mp4", "")
    caption_txt_path = OUTPUT_DIR / f"{slug_cap}_caption.txt"
    descripcion_youtube = ""
    if caption_txt_path.exists():
        try:
            descripcion_youtube = caption_txt_path.read_text("utf-8").strip()
        except Exception:
            pass
    if not descripcion_youtube:
        # Fallback: construir desde los datos disponibles
        descripcion_youtube = (
            f"{hook}\n\n"
            f"{'📰 Fuente: ' + medio + chr(10) if medio else ''}"
            f"{'🔗 ' + url + chr(10) if url else ''}"
            f"\n🔔 Suscríbete para no perderte ninguna noticia verificada\n\n"
            f"{' '.join(hashtags[:8])}"
        ).strip()

    return {
        "tiktok":             tiktok_caption,
        "instagram":          ig_caption,
        "x":                  x_caption,
        "titulo":             titulo,
        "hook":               hook,
        "descripcion_youtube": descripcion_youtube,
    }


_HASHTAG_MAP = {
    ("inteligencia artificial", "ia ", " ai ", "openai", "chatgpt", "llm", "machine learning", "deepmind", "anthropic", "gemini"): [
        "#InteligenciaArtificial", "#IA", "#AI", "#ChatGPT", "#TecnologiaIA",
        "#FuturoDigital", "#Innovacion", "#MachineLearning", "#AINews", "#Tech",
        "#Tecnologia", "#DigitalTransformation", "#Automatizacion",
    ],
    ("bitcoin", "crypto", "criptomoneda", "ethereum", "blockchain", "btc", "eth", "defi", "nft", "web3"): [
        "#Bitcoin", "#Crypto", "#Criptomonedas", "#BTC", "#Ethereum",
        "#Blockchain", "#DeFi", "#CryptoNews", "#Finanzas", "#Inversion",
        "#DineroDigital", "#MercadoCrypto", "#NFT",
    ],
    ("bolsa", "mercado", "economia", "inflacion", "fed ", "wall street", "acciones", "finanzas", "banco", "dolar"): [
        "#Economia", "#Finanzas", "#Bolsa", "#Mercados", "#Inversion",
        "#WallStreet", "#EducacionFinanciera", "#Dinero", "#Negocios",
        "#EconomiaGlobal", "#Fed", "#Macroeconomia",
    ],
    ("clima", "medioambiente", "inundacion", "sequia", "contaminacion", "carbono", "temperatura", "calentamiento"): [
        "#CambioClimatico", "#MedioAmbiente", "#ClimaExtremo",
        "#Sostenibilidad", "#Naturaleza", "#EcoConciencia",
        "#CalentamientoGlobal", "#Planeta", "#CrisisClimatica",
    ],
    ("salud", "cancer", "vacuna", "enfermedad", "medico", "hospital", "virus", "pandemia", "farmaco"): [
        "#Salud", "#Medicina", "#Bienestar", "#SaludMental",
        "#CienciaMedica", "#Noticias", "#Investigacion", "#Farmacia",
    ],
    ("guerra", "conflicto", "ejercito", "militar", "bomba", "ataque", "invasion", "misil", "otan"): [
        "#GeopoliticaGlobal", "#Conflicto", "#Noticias", "#Geopolitica",
        "#SeguridadInternacional", "#Diplomacia", "#NoticiasInternacionales",
    ],
    ("politica", "gobierno", "eleccion", "presidente", "congreso", "ley", "democracia", "partido"): [
        "#Politica", "#Gobierno", "#Democracia", "#Noticias",
        "#ActualidadPolitica", "#SocialdadCivil", "#EleccionesXX",
    ],
    ("espacio", "nasa", "cohete", "marte", "luna", "satelite", "astronomia", "planeta"): [
        "#Espacio", "#NASA", "#Astronomia", "#ExploraciónEspacial",
        "#Ciencia", "#Universo", "#FuturoCientifico", "#Cosmologia",
    ],
}

_HASHTAGS_BASE = [
    "#Noticias", "#UltimaHora", "#NoticiasVerificadas",
    "#InformaciónRapida", "#Shorts", "#ReelNews",
]


def _hashtags_para(texto: str) -> list[str]:
    for keywords, tags in _HASHTAG_MAP.items():
        if any(kw in texto for kw in keywords):
            return tags + _HASHTAGS_BASE[:3]
    return _HASHTAGS_BASE + ["#Informacion", "#Actualidad", "#Viral"]


@router.get("/api/publish/{job_id}")
def get_publish_status(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job de publicación no encontrado")
    return job
