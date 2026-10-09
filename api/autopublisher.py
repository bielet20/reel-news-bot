"""
api/autopublisher.py
Cola de publicación automática con prioridad por score de viralidad.

- Prioridad: mayor score primero (heapq con -score)
- Límite: máx N publicaciones por DÍA NATURAL (hora de España, ver horario.py);
  a medianoche el contador vuelve a 0 (antes era una ventana móvil de 24 h)
- Franja horaria (hora de España): solo publica entre hora_inicio y hora_fin
  (def. 8-23) y REPARTE las publicaciones del día: intervalo = minutos que
  quedan de franja / publicaciones que faltan para el límite (mínimo 30 min)
- Captions optimizadas desde /api/publish/caption antes de publicar
- Estado y cola persistidos en _config/autopub_state.json (la cola sobrevive
  a los reinicios del backend)
- Al acabar cada subida confirma qué se publicó y dónde (campana del Gestor +
  Telegram si está configurado)
"""

import heapq
import json
import os
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
    "queue": [],
    "hora_inicio":  8,     # franja de publicación, hora local (ver horario.py)
    "hora_fin":     23,
    "repartir":     True,  # repartir las del día a lo largo de la franja
}

INTERVALO_MIN = 30  # minutos mínimos entre publicaciones


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


def _persist_queue():
    """Guarda la cola en disco. Llamar con _lock tomado."""
    state = _load_state()
    state["queue"] = [e for _, _, e in sorted(_queue)]
    _save_state(state)


def _restore_queue():
    with _lock:
        for e in _load_state().get("queue") or []:
            heapq.heappush(_queue, (-float(e.get("score") or 0), e.get("added_at", ""), e))
    if _queue:
        print(f"[autopublisher] {len(_queue)} reel(s) recuperados de la cola guardada")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _count_24h(published: list) -> int:
    """Cuenta las publicaciones de HOY (día natural en hora local). El nombre
    se mantiene por compatibilidad; ya no es una ventana móvil de 24 h."""
    from horario import es_hoy
    return sum(1 for p in published if es_hoy(p.get("timestamp", "")))


def _prune_24h(published: list) -> list:
    """Elimina entradas de más de 48 h (basta con conservar ayer y hoy)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
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


def _franja(state: dict) -> tuple[bool, float]:
    """(¿estamos dentro de la franja?, minutos que quedan de franja hoy)."""
    from horario import ahora_local
    ahora = ahora_local()
    ini, fin = int(state.get("hora_inicio", 8)), int(state.get("hora_fin", 23))
    minutos = ahora.hour * 60 + ahora.minute
    dentro = ini * 60 <= minutos < fin * 60
    return dentro, max(0.0, fin * 60 - minutos)


def _intervalo(state: dict, publicadas_hoy: int) -> float:
    """Minutos que deben pasar desde la última publicación."""
    if not state.get("repartir", True):
        return INTERVALO_MIN
    _, quedan_min = _franja(state)
    faltan = max(1, state.get("daily_limit", 10) - publicadas_hoy)
    return max(INTERVALO_MIN, quedan_min / faltan)


# ── Control de calidad antes de publicar ──────────────────────────────────────
# 2026-10-05: se publicaron solos reels de 11 s cuyo guion era solo el titular
# repetido. Pase lo que pase antes, el piloto automático no publica eso.
REEL_MIN_SEG = float(os.environ.get("AUTOPUB_REEL_MIN_SEG", "20"))
_FIRMA_PLANTILLA = "¿Sabías esto sobre "


def _duracion_video(ruta: Path) -> float:
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(ruta)], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return -1.0


def reel_publicable(output_file: str) -> tuple[bool, str]:
    """(True, "") si el reel se puede publicar solo; si no, (False, motivo)."""
    ruta = Path(__file__).parent.parent / "output" / output_file
    if not ruta.is_file():
        return False, "el vídeo no existe"
    guion = ruta.with_name(ruta.name.replace("_reel.mp4", "_guion_reel.txt"))
    if guion.is_file() and _FIRMA_PLANTILLA in guion.read_text("utf-8", errors="ignore"):
        return False, "el guion es la plantilla de emergencia (solo el titular, sin información)"
    dur = _duracion_video(ruta)
    if 0 <= dur < REEL_MIN_SEG:
        return False, f"dura {dur:.0f} s (mínimo {REEL_MIN_SEG:.0f} s): reel incompleto"
    return True, ""


def _rechazar(titulo: str, motivo: str):
    print(f"[autopublisher] NO se publica «{titulo[:60]}»: {motivo}")
    try:
        from api.scanner import registrar_aviso
        registrar_aviso("publicacion_fallida", titulo, error=f"No publicado: {motivo}")
    except Exception:
        pass


# ── Public API ─────────────────────────────────────────────────────────────────

def enqueue(item_id: str, score: float, output_file: str, titulo: str,
            platforms: list, tipo_contenido: str = "noticia",
            tiktok_privacy: str = "SELF_ONLY", categoria: str = ""):
    """Añade un item a la cola de publicación automática."""
    ok, motivo = reel_publicable(output_file)
    if not ok:
        _rechazar(titulo, motivo)
        return
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
        _persist_queue()
    print(f"[autopublisher] Encolado: {titulo[:50]} (score={score})")


def get_status() -> dict:
    with _lock:
        state = _load_state()
        queue_snapshot = [e for _, _, e in sorted(_queue)]
    count = _count_24h(state.get("published_24h", []))
    dentro, _ = _franja(state)
    intervalo = _intervalo(state, count)
    minutes_wait = max(0, intervalo - _minutes_since_last(state.get("last_publish_at")))
    return {
        "enabled":       state["enabled"],
        "paused":        state["paused"],
        "daily_limit":   state["daily_limit"],
        "published_today": count,
        "dia":           __import__("horario").dia_local(),
        "queue_size":    len(queue_snapshot),
        "queue":         queue_snapshot[:5],   # top-5 preview
        "last_publish_at": state.get("last_publish_at"),
        "minutes_until_next": round(minutes_wait, 1) if queue_snapshot and count < state["daily_limit"] else None,
        "publishing":    _publishing,
        "franja":        f"{int(state.get('hora_inicio', 8)):02d}:00-{int(state.get('hora_fin', 23)):02d}:00",
        "en_franja":     dentro,
        "repartir":      state.get("repartir", True),
        "intervalo_min": round(intervalo),
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

    # Lo que ya estaba en cola antes de este control también se revisa
    ok, motivo = reel_publicable(output_file)
    if not ok:
        _rechazar(titulo, motivo)
        _publishing = False  # si no, el piloto se queda bloqueado
        return

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

        # Registrar las subidas en el item del Gestor (no se vuelve a subir y
        # la web lo muestra como subido)
        try:
            from api.gestor import _post_publish_actions
            _post_publish_actions({"queue_item_id": item_id}, job_results)
        except Exception as e:
            print(f"[autopublisher] registrar subidas: {e}")

        _confirmar(titulo, score, platforms, job_results)

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
        _confirmar(titulo, score, platforms, {p: {"status": "error", "error": str(e)} for p in platforms})
    finally:
        _publishing = False


def _enlace(result: dict) -> str:
    url = result.get("url") or ""
    return url if isinstance(url, str) and url.startswith("http") else ""


def _confirmar(titulo: str, score: float, platforms: list, job_results: dict):
    """Confirma lo que se ha subido: aviso en la campana del Gestor y Telegram."""
    subidas = {p: _enlace(r) for p, r in job_results.items() if r.get("status") == "ok"}
    fallos = {p: str((job_results.get(p) or {}).get("error") or "sin respuesta")[:160]
              for p in platforms if p not in subidas}

    try:
        from api.scanner import registrar_aviso
        registrar_aviso(
            "publicado" if subidas else "publicacion_fallida", titulo,
            score=score, subidas=subidas, fallos=fallos,
            link=next((u for u in subidas.values() if u), ""),
        )
    except Exception as e:
        print(f"[autopublisher] aviso: {e}")

    # Telegram solo a un chat PRIVADO de avisos: TELEGRAM_CHAT_ID es el canal
    # público del medio y ahí no deben salir los fallos ni el informe
    chat_avisos = os.environ.get("TELEGRAM_AVISOS_CHAT_ID")
    if not chat_avisos:
        return
    try:
        from html import escape
        from telegram_uploader import enviar_mensaje as tg_msg
        if subidas and not fallos:
            cab = "✅ Reel publicado"
        elif subidas:
            cab = "⚠️ Reel publicado a medias"
        else:
            cab = "❌ No se pudo publicar"
        lines = [f"{cab} ({score:.1f}⭐)", f"<b>{escape(titulo)}</b>", ""]
        for p, url in subidas.items():
            lines.append(f"• {p}: {escape(url) if url else 'subido'}")
        for p, err in fallos.items():
            lines.append(f"• {p}: FALLÓ — {escape(err)}")
        tg_msg("\n".join(lines), chat_id=chat_avisos)
    except Exception as e:
        print(f"[autopublisher] Telegram: {e}")


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

            dentro, _ = _franja(state)
            if not dentro:  # fuera de la franja horaria: espera a mañana
                continue

            minutes_since = _minutes_since_last(state.get("last_publish_at"))
            if minutes_since < _intervalo(state, count):
                continue

            with _lock:
                if not _queue:
                    continue
                _, _, entry = heapq.heappop(_queue)
                _persist_queue()

            _publishing = True
            threading.Thread(
                target=_publish_item,
                args=(entry,),
                daemon=True,
                name=f"autopub-{entry['item_id']}",
            ).start()

        except Exception as e:
            print(f"[autopublisher] loop error: {e}")


_restore_queue()
threading.Thread(target=_publisher_loop, daemon=True, name="autopublisher").start()


# ── API endpoints ──────────────────────────────────────────────────────────────

class AutoPubConfig(BaseModel):
    enabled:     Optional[bool]  = None
    paused:      Optional[bool]  = None
    daily_limit: Optional[int]   = None
    hora_inicio: Optional[int]   = None
    hora_fin:    Optional[int]   = None
    repartir:    Optional[bool]  = None


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
        if body.hora_inicio is not None:
            state["hora_inicio"] = max(0, min(23, body.hora_inicio))
        if body.hora_fin is not None:
            state["hora_fin"] = max(1, min(24, body.hora_fin))
        if body.repartir is not None:
            state["repartir"] = body.repartir
        _save_state(state)
    return get_status()


@router.delete("/api/autopublisher/queue/{item_id}")
def autopub_dequeue(item_id: str):
    with _lock:
        global _queue
        _queue = [(s, t, e) for s, t, e in _queue if e["item_id"] != item_id]
        heapq.heapify(_queue)
        _persist_queue()
    return {"ok": True, "queue_size": len(_queue)}
