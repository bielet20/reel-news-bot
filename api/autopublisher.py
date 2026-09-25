"""
api/autopublisher.py
Cola de publicación automática con prioridad por score de viralidad.

- Prioridad: mayor score primero (heapq con -score)
- Límite: máx 10 publicaciones en ventana de 24h rolling
- Intervalo mínimo entre publicaciones: 30 minutos
- Captions optimizadas desde /api/publish/caption antes de publicar
- Estado persistido en _config/autopub_state.json
"""

import heapq
import json
import threading
import time
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

STATE_FILE = CONFIG_DIR / "autopub_state.json"

_lock        = threading.Lock()
_queue: list = []       # heapq: (-score, timestamp_added, item_dict)
_publishing  = False    # flag para evitar publicaciones simultáneas

STATE_DEFAULTS = {
    "enabled":      False,
    "daily_limit":  10,
    "paused":       False,
    "last_publish_at": None,
    "published_24h": [],
}


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text("utf-8"))
            return {**STATE_DEFAULTS, **data}
    except Exception:
        pass
    return dict(STATE_DEFAULTS)


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _count_24h(published: list) -> int:
    """Cuenta publicaciones en las últimas 24h (rolling window)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    return sum(1 for p in published if p.get("timestamp", "") >= cutoff)


def _prune_24h(published: list) -> list:
    """Elimina entradas de más de 24h de la lista."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    return [p for p in published if p.get("timestamp", "") >= cutoff]


def _minutes_since_last(last_publish_at: Optional[str]) -> float:
    if not last_publish_at:
        return 9999.0
    try:
        dt = datetime.fromisoformat(last_publish_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return 9999.0


# ── Public API ─────────────────────────────────────────────────────────────────

def enqueue(item_id: str, score: float, output_file: str, titulo: str,
            platforms: list, tipo_contenido: str = "noticia",
            tiktok_privacy: str = "SELF_ONLY", categoria: str = ""):
    """Añade un item a la cola de publicación automática."""
    # Skip if all requested platforms already have confirmed uploads
    try:
        import json
        from pathlib import Path as _Path
        queue_file = _Path(__file__).parent.parent / "_config" / "gestor_queue.json"
        if queue_file.exists():
            queue_items = json.loads(queue_file.read_text("utf-8"))
            src = next((i for i in queue_items if i["id"] == item_id), None)
            if src:
                uploads = src.get("uploads", {})
                already = [p for p in platforms if p in uploads]
                if already:
                    print(f"[autopublisher] Omitido (ya subido a {already}): {titulo[:50]}")
                    return
    except Exception:
        pass

    entry = {
        "item_id":        item_id,
        "score":          score,
        "output_file":    output_file,
        "titulo":         titulo,
        "platforms":      platforms,
        "tipo_contenido": tipo_contenido,
        "tiktok_privacy": tiktok_privacy,
        "categoria":      categoria,
        "added_at":       datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        # Evitar duplicados
        for _, _, existing in _queue:
            if existing["item_id"] == item_id:
                return
        heapq.heappush(_queue, (-score, entry["added_at"], entry))
    print(f"[autopublisher] Encolado: {titulo[:50]} (score={score})")


def get_status() -> dict:
    with _lock:
        state = _load_state()
        queue_snapshot = [e for _, _, e in sorted(_queue)]
    count = _count_24h(state.get("published_24h", []))
    minutes_wait = max(0, 30 - _minutes_since_last(state.get("last_publish_at")))
    return {
        "enabled":       state["enabled"],
        "paused":        state["paused"],
        "daily_limit":   state["daily_limit"],
        "published_today": count,
        "queue_size":    len(queue_snapshot),
        "queue":         queue_snapshot[:5],   # top-5 preview
        "last_publish_at": state.get("last_publish_at"),
        "minutes_until_next": round(minutes_wait, 1) if queue_snapshot and count < state["daily_limit"] else None,
        "publishing":    _publishing,
    }


# ── Core publish logic ─────────────────────────────────────────────────────────

def _fetch_captions(output_file: str) -> dict:
    try:
        r = http.get(
            f"http://localhost:8000/api/publish/caption",
            params={"filename": output_file},
            timeout=10,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


def _publish_item(entry: dict):
    global _publishing
    item_id      = entry["item_id"]
    output_file  = entry["output_file"]
    titulo       = entry["titulo"]
    platforms    = entry["platforms"]
    tipo         = entry["tipo_contenido"]
    tiktok_priv  = entry["tiktok_privacy"]
    score        = entry["score"]

    try:
        # Obtener captions optimizadas desde el guion generado
        caps = _fetch_captions(output_file)
        titulo_yt   = caps.get("hook") or caps.get("titulo") or titulo
        desc_yt     = caps.get("descripcion_youtube") or caps.get("descripcion") or titulo
        tg_cap      = caps.get("telegram") or desc_yt
        ig_cap      = caps.get("instagram") or titulo_yt
        tiktok_cap  = caps.get("tiktok") or titulo_yt
        x_cap       = caps.get("x") or titulo_yt

        resp = http.post("http://localhost:8000/api/publish", json={
            "filename":           output_file,
            "titulo":             titulo_yt,
            "descripcion":        desc_yt,
            "tiktok_caption":     tiktok_cap,
            "instagram_caption":  ig_cap,
            "x_caption":          x_cap,
            "platforms":          platforms,
            "tipo_contenido":     tipo,
            "tiktok_privacy":     tiktok_priv,
        }, timeout=15)
        resp.raise_for_status()
        pub_job_id = resp.json()["job_id"]

        # Poll hasta completar (máx 15 min)
        job_results = {}
        not_found_streak = 0
        for _ in range(450):
            time.sleep(2)
            try:
                r = http.get(f"http://localhost:8000/api/publish/{pub_job_id}", timeout=5)
                if r.ok:
                    not_found_streak = 0
                    job = r.json()
                    if job["status"] != "running":
                        job_results = job.get("results", {})
                        break
                elif r.status_code == 404:
                    not_found_streak += 1
                    if not_found_streak >= 3:
                        raise RuntimeError(f"Publish job {pub_job_id} no encontrado")
            except RuntimeError:
                raise
            except Exception:
                pass

        # Registrar resultado
        ok_platforms = [p for p, r in job_results.items() if r.get("status") == "ok"]
        yt_url = (job_results.get("youtube") or {}).get("url", "")

        with _lock:
            state = _load_state()
            state["published_24h"] = _prune_24h(state.get("published_24h", []))
            state["published_24h"].insert(0, {
                "item_id":   item_id,
                "titulo":    titulo,
                "score":     score,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platforms": ok_platforms,
                "yt_url":    yt_url,
            })
            state["last_publish_at"] = datetime.now(timezone.utc).isoformat()
            _save_state(state)

        # Confirmación Telegram (canal propio)
        try:
            from telegram_uploader import enviar_mensaje as tg_msg
            lines = [f"[Auto {score:.1f}⭐] {titulo}"]
            if ok_platforms:
                lines.append(f"Publicado en: {', '.join(ok_platforms)}")
            if yt_url:
                lines.append(yt_url)
            tg_msg("\n".join(lines))
        except Exception as e:
            print(f"[autopublisher] Telegram: {e}")

        # Distribuir a grupos de Telegram y Reddit
        if yt_url:
            try:
                import sys
                from pathlib import Path as _Path
                sys.path.insert(0, str(_Path(__file__).parent.parent))
                from distribuidor import distribuir as _dist
                _dist(titulo=titulo, yt_url=yt_url, categoria=entry.get("categoria", ""))
            except Exception as e:
                print(f"[autopublisher] Distribuidor: {e}")

        print(f"[autopublisher] Publicado: {titulo[:50]} → {ok_platforms}")

    except Exception as e:
        print(f"[autopublisher] Error publicando {item_id}: {e}")
    finally:
        _publishing = False


# ── Background loop ────────────────────────────────────────────────────────────

def _publisher_loop():
    global _publishing
    time.sleep(30)   # espera inicial
    while True:
        time.sleep(60)
        try:
            with _lock:
                state = _load_state()

            if not state.get("enabled") or state.get("paused"):
                continue

            if _publishing:
                continue

            count = _count_24h(state.get("published_24h", []))
            if count >= state.get("daily_limit", 10):
                continue

            minutes_since = _minutes_since_last(state.get("last_publish_at"))
            if minutes_since < 30:
                continue

            with _lock:
                if not _queue:
                    continue
                _, _, entry = heapq.heappop(_queue)

            _publishing = True
            threading.Thread(
                target=_publish_item,
                args=(entry,),
                daemon=True,
                name=f"autopub-{entry['item_id']}",
            ).start()

        except Exception as e:
            print(f"[autopublisher] loop error: {e}")


threading.Thread(target=_publisher_loop, daemon=True, name="autopublisher").start()


# ── API endpoints ──────────────────────────────────────────────────────────────

class AutoPubConfig(BaseModel):
    enabled:     Optional[bool]  = None
    paused:      Optional[bool]  = None
    daily_limit: Optional[int]   = None


@router.get("/api/autopublisher/status")
def autopub_status():
    return get_status()


@router.post("/api/autopublisher/config")
def autopub_config(body: AutoPubConfig):
    with _lock:
        state = _load_state()
        if body.enabled is not None:
            state["enabled"] = body.enabled
        if body.paused is not None:
            state["paused"] = body.paused
        if body.daily_limit is not None:
            state["daily_limit"] = max(1, min(50, body.daily_limit))
        _save_state(state)
    return get_status()


@router.delete("/api/autopublisher/queue/{item_id}")
def autopub_dequeue(item_id: str):
    with _lock:
        global _queue
        _queue = [(s, t, e) for s, t, e in _queue if e["item_id"] != item_id]
        heapq.heapify(_queue)
    return {"ok": True, "queue_size": len(_queue)}
