"""
api/yt_scanner.py
Scanner diario de YouTube: detecta vídeos virales por nicho con yt-dlp,
los puntúa por potencial viral y los encola para generar shorts.

No usa YouTube Data API — corre con yt-dlp (ya instalado) directamente.
"""
import json
import math
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests as http
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

CORE_DIR   = Path(__file__).parent.parent
CONFIG_DIR = CORE_DIR / "_config"
CONFIG_DIR.mkdir(exist_ok=True)

YT_CONFIG_FILE = CONFIG_DIR / "yt_scanner_config.json"
YT_STATE_FILE  = CONFIG_DIR / "yt_scanner_state.json"
YT_NOTIF_FILE  = CONFIG_DIR / "yt_scanner_notifications.json"

_lock = threading.Lock()

# ── Nichos con sus queries de búsqueda ─────────────────────────────────────────

NICHOS: dict[str, dict] = {
    "ia": {
        "nombre": "IA & LLMs",
        "emoji":  "🤖",
        "color":  "#818cf8",
        "queries": [
            "inteligencia artificial noticias hoy",
            "openai news latest",
            "chatgpt new update",
            "deepmind announcement",
            "AI agents breakthrough",
        ],
    },
    "crypto": {
        "nombre": "Crypto & Bitcoin",
        "emoji":  "₿",
        "color":  "#f59e0b",
        "queries": [
            "bitcoin price today crash",
            "crypto news today altcoins",
            "ethereum update news",
            "crypto bull run 2025",
            "btc all time high",
        ],
    },
    "finanzas": {
        "nombre": "Finanzas & Bolsa",
        "emoji":  "📈",
        "color":  "#34d399",
        "queries": [
            "stock market crash today",
            "federal reserve interest rates news",
            "economia noticias hoy",
            "wall street news today",
            "bolsa de valores noticias",
        ],
    },
    "tecnologia": {
        "nombre": "Tecnología",
        "emoji":  "💻",
        "color":  "#60a5fa",
        "queries": [
            "tech news today apple google",
            "tesla news latest",
            "noticias tecnologia hoy",
            "smartphone launch 2025",
            "startup funding tech",
        ],
    },
    "noticias": {
        "nombre": "Noticias Generales",
        "emoji":  "📰",
        "color":  "#f87171",
        "queries": [
            "noticias del mundo hoy",
            "breaking news today world",
            "ultimas noticias españa",
            "geopolitica noticias hoy",
            "world news viral today",
        ],
    },
}

# ── Config / State defaults ────────────────────────────────────────────────────

CONFIG_DEFAULTS: dict = {
    "enabled":           False,
    "interval_hours":    24,
    "score_min":         6.5,
    "min_views":         50_000,
    "max_age_days":      3,
    "n_por_nicho":       3,
    "auto_generate":     False,
    "auto_publish":      False,
    "publish_platforms": ["youtube"],
    "nichos_activos":    ["ia", "crypto", "finanzas", "tecnologia"],
}

STATE_DEFAULTS: dict = {
    "last_run":   None,
    "next_run":   None,
    "running":    False,
    "last_error": None,
    "seen_ids":   [],
}


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_json(path: Path, defaults: dict) -> dict:
    try:
        if path.exists():
            return {**defaults, **json.loads(path.read_text("utf-8"))}
    except Exception:
        pass
    return dict(defaults)


def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _load_notifs() -> list:
    try:
        if YT_NOTIF_FILE.exists():
            return json.loads(YT_NOTIF_FILE.read_text("utf-8"))
    except Exception:
        pass
    return []


def _save_notifs(notifs: list):
    YT_NOTIF_FILE.write_text(json.dumps(notifs, ensure_ascii=False, indent=2), "utf-8")


# ── Models ─────────────────────────────────────────────────────────────────────

class YtScannerConfig(BaseModel):
    enabled:        bool      = False
    interval_hours: int       = 24
    score_min:      float     = 6.5
    min_views:      int       = 50_000
    max_age_days:   int       = 3
    n_por_nicho:    int       = 3
    auto_generate:  bool      = True
    nichos_activos: list[str] = ["ia", "crypto", "finanzas", "tecnologia"]


# ── API endpoints ──────────────────────────────────────────────────────────────

@router.get("/api/yt-scanner/status")
def yt_scanner_status():
    with _lock:
        config = _load_json(YT_CONFIG_FILE, CONFIG_DEFAULTS)
        state  = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
        notifs = _load_notifs()
    unread = sum(1 for n in notifs if not n.get("leido"))
    return {
        "config":     config,
        "nichos":     {k: {"nombre": v["nombre"], "emoji": v["emoji"], "color": v["color"]} for k, v in NICHOS.items()},
        "last_run":   state["last_run"],
        "next_run":   state["next_run"],
        "running":    state["running"],
        "last_error": state["last_error"],
        "unread":     unread,
    }


@router.put("/api/yt-scanner/config")
def update_config(body: YtScannerConfig):
    cfg = body.model_dump()
    with _lock:
        _save_json(YT_CONFIG_FILE, cfg)
        state = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
        if cfg["enabled"] and not state.get("running"):
            next_dt = datetime.now(timezone.utc) + timedelta(hours=cfg["interval_hours"])
            state["next_run"] = next_dt.isoformat()
            _save_json(YT_STATE_FILE, state)
    return cfg


@router.post("/api/yt-scanner/run")
def manual_run():
    with _lock:
        state = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
        if state.get("running"):
            return {"ok": False, "msg": "Ya hay un escaneo en curso"}
    threading.Thread(target=_scan_once, daemon=True).start()
    return {"ok": True, "msg": "Escaneo iniciado"}


@router.get("/api/yt-scanner/notifications")
def get_notifications():
    with _lock:
        return _load_notifs()


@router.post("/api/yt-scanner/notifications/read-all")
def mark_all_read():
    with _lock:
        notifs = _load_notifs()
        for n in notifs:
            n["leido"] = True
        _save_notifs(notifs)
    return {"ok": True}


@router.delete("/api/yt-scanner/notifications")
def clear_notifications():
    with _lock:
        _save_notifs([])
    return {"ok": True}


# ── yt-dlp search ──────────────────────────────────────────────────────────────

def _search_videos(query: str, n: int = 15) -> list[dict]:
    """Busca vídeos en YouTube con yt-dlp y devuelve lista de metadatos."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                f"ytsearch{n}:{query}",
                "--flat-playlist",
                "-J",
                "--no-warnings",
                "--ignore-errors",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0 and not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        return data.get("entries") or []
    except Exception:
        return []


def _parse_upload_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _score_video(video: dict, max_age_days: int) -> float:
    """
    Puntuación 0-10 basada en:
      - Vistas absolutas (peso 30%)
      - Velocidad de vistas (vistas/día, peso 40%)
      - Recencia (peso 20%)
      - Duración ideal para shorts de noticias (peso 10%)
    """
    views    = video.get("view_count") or 0
    uploaded = _parse_upload_date(video.get("upload_date"))
    duration = video.get("duration") or 0

    if views <= 0:
        return 0.0

    # Velocidad de vistas
    if uploaded:
        days_old = max(0.5, (datetime.now(timezone.utc) - uploaded).total_seconds() / 86400)
    else:
        days_old = max_age_days  # pesimista si no sabemos

    velocity = views / days_old  # vistas por día

    # Sub-scores (0-10 cada uno)
    views_score    = min(10, math.log10(max(views, 1)) * 1.43)      # 10M views = 10
    velocity_score = min(10, math.log10(max(velocity, 1)) * 2.0)    # 100K/día = 10
    recency_score  = max(0, 10 - days_old * (10 / max_age_days))    # lineal inverso
    duration_score = 10 if 60 <= duration <= 900 else (6 if duration > 0 else 3)

    # Pesos
    score = (
        views_score    * 0.30 +
        velocity_score * 0.40 +
        recency_score  * 0.20 +
        duration_score * 0.10
    )
    return round(min(10.0, score), 1)


def _fmt_views(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def _adaptar_titulos_es(videos: list[dict]) -> list[dict]:
    """Traduce y adapta los títulos de YouTube al español viral (MrBeast) en un solo batch."""
    import os, json as _json
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return videos

    lista = "\n".join(
        f'{i+1}. TÍTULO: {v["titulo"]} | CANAL: {v["canal"]} | VISTAS: {v["views_fmt"]}'
        for i, v in enumerate(videos)
    )
    prompt = (
        f"Adapta estos {len(videos)} títulos de YouTube al español viral para Shorts/Reels.\n"
        f"Canal de noticias hispanohablante. Audiencia: España y Latinoamérica.\n\n"
        f"{lista}\n\n"
        f"Para cada título genera uno nuevo en ESPAÑOL siguiendo EXACTAMENTE una de estas fórmulas:\n"
        f'1. "¿Sabías que [Marca] acaba de [acción] por [cifra]?" — máx 60 chars\n'
        f'2. "[Marca] acaba de [acción sorprendente] y nadie lo esperaba" — máx 60 chars\n'
        f'3. "¿[Pregunta que pone al espectador en la noticia]?" — máx 60 chars\n'
        f'4. "[Cifra] [unidad] de [cosa]: lo que [Marca] acaba de hacer"\n'
        f"NUNCA empieces con La/El/Los/Un. NUNCA en inglés. Máx 60 chars.\n\n"
        f"Devuelve SOLO este JSON (sin markdown):\n"
        f'{{"titulos": ["título 1 en español", "título 2 en español", ...]}}'
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = _json.loads(raw)
        titulos_es = data.get("titulos", [])
        for i, v in enumerate(videos):
            if i < len(titulos_es) and titulos_es[i].strip():
                v["titulo_original"] = v["titulo"]
                v["titulo"] = titulos_es[i].strip()
    except Exception as e:
        print(f"[yt-scanner] traducción títulos: {e}")

    return videos


# ── Core scan logic ────────────────────────────────────────────────────────────

def _scan_once():
    with _lock:
        state  = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
        config = _load_json(YT_CONFIG_FILE, CONFIG_DEFAULTS)
        state["running"]    = True
        state["last_error"] = None
        _save_json(YT_STATE_FILE, state)

    total_found = 0
    try:
        sys.path.insert(0, str(CORE_DIR))

        with _lock:
            state  = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
            seen   = set(state.get("seen_ids") or [])
            notifs = _load_notifs()

        score_min    = config["score_min"]
        min_views    = config["min_views"]
        max_age_days = config["max_age_days"]
        n_por_nicho  = config["n_por_nicho"]
        nichos_on    = set(config.get("nichos_activos") or NICHOS.keys())
        cutoff       = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        for nicho_id, nicho_info in NICHOS.items():
            if nicho_id not in nichos_on:
                continue

            candidates: list[dict] = []

            for query in nicho_info["queries"]:
                videos = _search_videos(query, n=12)
                for v in videos:
                    vid_id = v.get("id") or v.get("url", "").split("v=")[-1]
                    if not vid_id or vid_id in seen:
                        continue
                    views = v.get("view_count") or 0
                    if views < min_views:
                        continue
                    uploaded = _parse_upload_date(v.get("upload_date"))
                    if uploaded and uploaded < cutoff:
                        continue
                    score = _score_video(v, max_age_days)
                    if score < score_min:
                        continue
                    # evitar duplicados dentro de la misma búsqueda
                    if not any(c["id"] == vid_id for c in candidates):
                        candidates.append({
                            "id":          vid_id,
                            "titulo":      v.get("title") or v.get("fulltitle", ""),
                            "canal":       v.get("channel") or v.get("uploader", ""),
                            "views":       views,
                            "views_fmt":   _fmt_views(views),
                            "upload_date": v.get("upload_date", ""),
                            "duration":    v.get("duration") or 0,
                            "url":         f"https://www.youtube.com/watch?v={vid_id}",
                            "thumbnail":   f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                            "score":       score,
                            "nicho":       nicho_id,
                            "nicho_nombre": nicho_info["nombre"],
                            "nicho_emoji": nicho_info["emoji"],
                            "nicho_color": nicho_info["color"],
                        })

            # Ordenar por score y quedarse con los mejores
            top = sorted(candidates, key=lambda x: x["score"], reverse=True)[:n_por_nicho]

            # Traducir/adaptar títulos al español viral en un solo batch
            top = _adaptar_titulos_es(top)

            for video in top:
                item_id = None
                if config.get("auto_generate"):
                    item_id = _enqueue_video(video, config)

                notif = {
                    "id":           uuid.uuid4().hex[:8],
                    "tipo":         "yt_viral",
                    "titulo":       video["titulo"],
                    "titulo_original": video.get("titulo_original", video["titulo"]),
                    "canal":        video["canal"],
                    "views":        video["views"],
                    "views_fmt":    video["views_fmt"],
                    "score":        video["score"],
                    "url":          video["url"],
                    "thumbnail":    video["thumbnail"],
                    "nicho":        video["nicho"],
                    "nicho_nombre": video["nicho_nombre"],
                    "nicho_emoji":  video["nicho_emoji"],
                    "nicho_color":  video["nicho_color"],
                    "item_id":      item_id,
                    "leido":        False,
                    "creado":       datetime.now().isoformat(),
                    "auto_generado": bool(config.get("auto_generate")),
                }
                notifs.insert(0, notif)
                seen.add(video["id"])
                total_found += 1

        seen_list = list(seen)[-1000:]
        notifs    = notifs[:150]

        with _lock:
            state = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
            state["seen_ids"] = seen_list
            _save_json(YT_STATE_FILE, state)
            _save_notifs(notifs)

    except Exception as e:
        with _lock:
            state = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
            state["last_error"] = str(e)
            _save_json(YT_STATE_FILE, state)

    finally:
        now = datetime.now(timezone.utc)
        with _lock:
            state  = _load_json(YT_STATE_FILE, STATE_DEFAULTS)
            config = _load_json(YT_CONFIG_FILE, CONFIG_DEFAULTS)
            state["running"]  = False
            state["last_run"] = now.isoformat()
            next_dt           = now + timedelta(hours=config["interval_hours"])
            state["next_run"] = next_dt.isoformat()
            _save_json(YT_STATE_FILE, state)

    return total_found


def _enqueue_video(video: dict, config: dict = None) -> Optional[str]:
    """Encola el vídeo de YouTube para generar un short."""
    cfg = config or {}
    try:
        resp = http.post("http://localhost:8000/api/gestor/items", json={
            "tipo":              "url",
            "contenido":         video["url"],
            "titulo":            video["titulo"],
            "auto_publish":      cfg.get("auto_publish", False),
            "publish_platforms": cfg.get("publish_platforms", []),
            "score_noticia":     float(video.get("score", 7.0)),
        }, timeout=5)
        if not resp.ok:
            return None
        item_id = resp.json().get("id")
        http.post(f"http://localhost:8000/api/gestor/items/{item_id}/generate", timeout=5)
        return item_id
    except Exception:
        return None


# ── Background loop ────────────────────────────────────────────────────────────

def _yt_scanner_loop():
    time.sleep(20)   # espera inicial para no solapar con el arranque del servidor
    while True:
        try:
            with _lock:
                config = _load_json(YT_CONFIG_FILE, CONFIG_DEFAULTS)
                state  = _load_json(YT_STATE_FILE, STATE_DEFAULTS)

            if not config.get("enabled"):
                time.sleep(60)
                continue

            next_run_str = state.get("next_run")
            if next_run_str:
                try:
                    next_dt = datetime.fromisoformat(next_run_str.replace("Z", "+00:00"))
                    if next_dt.tzinfo is None:
                        next_dt = next_dt.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    if now < next_dt:
                        time.sleep(min(300, (next_dt - now).total_seconds()))
                        continue
                except Exception:
                    pass

            _scan_once()

        except Exception:
            time.sleep(300)


# Arranca el loop al importar el módulo
threading.Thread(target=_yt_scanner_loop, name="yt-scanner", daemon=True).start()
