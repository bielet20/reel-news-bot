"""
api/scanner.py
Scanner automático de noticias virales.
Corre en background, detecta nuevas noticias con alto potencial viral,
las encola en el gestor y emite notificaciones.
"""
import json
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

CORE_DIR = Path(__file__).parent.parent
CONFIG_DIR = CORE_DIR / "_config"
CONFIG_DIR.mkdir(exist_ok=True)

CONFIG_FILE = CONFIG_DIR / "scanner_config.json"
STATE_FILE  = CONFIG_DIR / "scanner_state.json"
NOTIF_FILE  = CONFIG_DIR / "scanner_notifications.json"

_lock = threading.Lock()

# ── Defaults ───────────────────────────────────────────────────────────────────

CONFIG_DEFAULTS = {
    "enabled":           False,
    "interval_min":      30,
    "score_min":         7.0,
    "auto_generate":     False,
    "auto_publish":      False,
    "publish_platforms": ["youtube"],
    "pais":              "ES",
    "n_noticias":        5,
    # Reglas para generar/publicar SOLA una noticia (además de score_min):
    "fiabilidad_min":    70,     # índice de fiabilidad 0-100 (fiabilidad.py)
    "min_medios":        2,      # medios independientes que la publican
    "excluir_nivel4":    True,   # nunca si el origen es alerta/PR
}

STATE_DEFAULTS = {
    "last_run":   None,
    "next_run":   None,
    "running":    False,
    "last_error": None,
    "seen_links": [],
}


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_json(path: Path, defaults: dict) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text("utf-8"))
            return {**defaults, **data}
    except Exception:
        pass
    return dict(defaults)


def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _load_notifs() -> list:
    try:
        if NOTIF_FILE.exists():
            return json.loads(NOTIF_FILE.read_text("utf-8"))
    except Exception:
        pass
    return []


def _save_notifs(notifs: list):
    NOTIF_FILE.write_text(json.dumps(notifs, ensure_ascii=False, indent=2), "utf-8")


# ── Models ─────────────────────────────────────────────────────────────────────

class ScannerConfig(BaseModel):
    enabled:           bool        = False
    interval_min:      int         = 30
    score_min:         float       = 7.0
    auto_generate:     bool        = True
    auto_publish:      bool        = False
    publish_platforms: list[str]   = ["youtube"]
    pais:              str         = "ES"
    n_noticias:        int         = 5
    fiabilidad_min:    int         = 70
    min_medios:        int         = 2
    excluir_nivel4:    bool        = True


# ── API endpoints ──────────────────────────────────────────────────────────────

@router.get("/api/scanner/status")
def scanner_status():
    with _lock:
        config = _load_json(CONFIG_FILE, CONFIG_DEFAULTS)
        state  = _load_json(STATE_FILE,  STATE_DEFAULTS)
        notifs = _load_notifs()
    unread = sum(1 for n in notifs if not n.get("leido"))
    return {
        "config":       config,
        "last_run":     state["last_run"],
        "next_run":     state["next_run"],
        "running":      state["running"],
        "last_error":   state["last_error"],
        "unread":       unread,
    }


@router.put("/api/scanner/config")
def update_config(body: ScannerConfig):
    cfg = body.model_dump()
    with _lock:
        _save_json(CONFIG_FILE, cfg)
        state = _load_json(STATE_FILE, STATE_DEFAULTS)
        # Recalculate next_run based on new interval if scanner is enabled
        if cfg["enabled"] and not state.get("running"):
            next_dt = datetime.now(timezone.utc) + timedelta(minutes=cfg["interval_min"])
            state["next_run"] = next_dt.isoformat()
            _save_json(STATE_FILE, state)
    return cfg


@router.post("/api/scanner/run")
def manual_run():
    """Lanza un escaneo manual inmediato."""
    with _lock:
        state = _load_json(STATE_FILE, STATE_DEFAULTS)
        if state.get("running"):
            return {"ok": False, "msg": "Ya hay un escaneo en curso"}
    threading.Thread(target=_scan_once, daemon=True).start()
    return {"ok": True, "msg": "Escaneo iniciado"}


@router.get("/api/scanner/notifications")
def get_notifications():
    with _lock:
        return _load_notifs()


@router.post("/api/scanner/notifications/read-all")
def mark_all_read():
    with _lock:
        notifs = _load_notifs()
        for n in notifs:
            n["leido"] = True
        _save_notifs(notifs)
    return {"ok": True}


@router.delete("/api/scanner/notifications")
def clear_notifications():
    with _lock:
        _save_notifs([])
    return {"ok": True}


# ── Core scanner logic ─────────────────────────────────────────────────────────

def _scan_once():
    with _lock:
        state = _load_json(STATE_FILE, STATE_DEFAULTS)
        config = _load_json(CONFIG_FILE, CONFIG_DEFAULTS)
        state["running"] = True
        state["last_error"] = None
        _save_json(STATE_FILE, state)

    found = 0
    try:
        import sys
        sys.path.insert(0, str(CORE_DIR))
        from news_curator import buscar_y_curar

        noticias = buscar_y_curar(
            tema=None,
            pais=config["pais"],
            variado=True,
            n_retornar=config["n_noticias"] * 3,  # pedir más para filtrar mejor
        )

        with _lock:
            state = _load_json(STATE_FILE, STATE_DEFAULTS)
            seen = set(state.get("seen_links") or [])
            notifs = _load_notifs()

        # Fiabilidad + reglas automáticas para cada noticia analizada
        from fiabilidad import apta_auto
        for n in noticias:
            n["apta_auto"], n["motivos_no_apta"] = apta_auto(n, config)
        _guardar_analisis(noticias, config)

        # Avisos: las virales nuevas. Se generan/publican SOLAS solo las que
        # además cumplen fiabilidad, medios y origen (apta_auto)
        nuevas = [
            n for n in noticias
            if float(n.get("score", 0)) >= config["score_min"]
            and n.get("link") not in seen
        ][:config["n_noticias"]]

        for noticia in nuevas:
            link = noticia.get("link", "")
            item_id = None

            if config["auto_generate"] and noticia.get("apta_auto"):
                item_id = _enqueue_noticia(noticia, config)

            notif = {
                "id":      uuid.uuid4().hex[:8],
                "tipo":    "viral_found",
                "titulo":  noticia.get("titulo", ""),
                "fuente":  noticia.get("origen") or noticia.get("fuente", ""),
                "score":   noticia.get("score", 0),
                "link":    link,
                "gancho":  noticia.get("gancho", ""),
                "documentacion": noticia.get("documentacion", ""),
                "verificadores": noticia.get("verificadores") or [],
                "estado_verificacion": noticia.get("estado_verificacion", ""),
                "item_id": item_id,
                "leido":   False,
                "creado":  datetime.now().isoformat(),
                "auto_generado": bool(item_id),
                "fiabilidad": noticia.get("fiabilidad"),
                "fiabilidad_label": noticia.get("fiabilidad_label"),
                "n_medios": noticia.get("n_medios"),
                "apta_auto": noticia.get("apta_auto"),
                "motivos_no_apta": noticia.get("motivos_no_apta") or [],
            }
            notifs.insert(0, notif)
            seen.add(link)
            found += 1

        # Mantener máx 500 links vistos, 100 notificaciones
        seen_list = list(seen)[-500:]
        notifs = notifs[:100]

        with _lock:
            state = _load_json(STATE_FILE, STATE_DEFAULTS)
            state["seen_links"] = seen_list
            _save_json(STATE_FILE, state)
            _save_notifs(notifs)

    except Exception as e:
        with _lock:
            state = _load_json(STATE_FILE, STATE_DEFAULTS)
            state["last_error"] = str(e)
            _save_json(STATE_FILE, state)

    finally:
        now = datetime.now(timezone.utc)
        with _lock:
            state = _load_json(STATE_FILE, STATE_DEFAULTS)
            config = _load_json(CONFIG_FILE, CONFIG_DEFAULTS)
            state["running"] = False
            state["last_run"] = now.isoformat()
            next_dt = now + timedelta(minutes=config["interval_min"])
            state["next_run"] = next_dt.isoformat()
            _save_json(STATE_FILE, state)

    return found


ANALISIS_FILE = Path(__file__).parent.parent / "_config" / "ultimo_analisis.json"


def _guardar_analisis(noticias: list, config: dict) -> None:
    """Último análisis completo (viralidad + fiabilidad + expansión) para la
    página de Fuentes, incluidas las que no pasan las reglas."""
    try:
        ANALISIS_FILE.write_text(json.dumps({
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "reglas": {k: config.get(k) for k in ("score_min", "fiabilidad_min", "min_medios", "excluir_nivel4")},
            "noticias": noticias,
        }, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as e:
        print(f"[scanner] no se pudo guardar el análisis: {e}")


def _enqueue_noticia(noticia: dict, config: dict) -> Optional[str]:
    """Añade la noticia a la cola del gestor. Devuelve el item_id si se creó."""
    try:
        resp = http.post("http://localhost:8000/api/gestor/items", json={
            "tipo":              "noticia",
            "contenido":         json.dumps(noticia, ensure_ascii=False),
            "titulo":            noticia.get("titulo", ""),
            "auto_publish":      config.get("auto_publish", False),
            "publish_platforms": config.get("publish_platforms", []),
            "score_noticia":     float(noticia.get("score", 7.0)),
        }, timeout=5)
        if not resp.ok:
            return None
        item_id = resp.json().get("id")

        # Lanzar generación inmediata
        http.post(f"http://localhost:8000/api/gestor/items/{item_id}/generate", timeout=5)
        return item_id
    except Exception:
        return None


# ── Background loop ────────────────────────────────────────────────────────────

def _scanner_loop():
    # Espera inicial para no arrancar en el mismo tick que el servidor
    time.sleep(15)
    while True:
        try:
            with _lock:
                config = _load_json(CONFIG_FILE, CONFIG_DEFAULTS)
                state  = _load_json(STATE_FILE,  STATE_DEFAULTS)

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
                        time.sleep(min(60, (next_dt - now).total_seconds()))
                        continue
                except Exception:
                    pass
            else:
                # Primera ejecución: esperar el intervalo completo
                interval = config.get("interval_min", 30)
                with _lock:
                    state = _load_json(STATE_FILE, STATE_DEFAULTS)
                    next_dt = datetime.now(timezone.utc) + timedelta(minutes=interval)
                    state["next_run"] = next_dt.isoformat()
                    _save_json(STATE_FILE, state)
                time.sleep(60)
                continue

            if not state.get("running"):
                _scan_once()
            else:
                # Otro escaneo en curso: esperar (antes volvía a mirar sin pausa,
                # en un bucle continuo leyendo el fichero de estado)
                time.sleep(60)

        except Exception:
            time.sleep(60)


def _limpiar_running_huerfano():
    """Al arrancar no hay ningún escaneo en marcha: si el backend se reinició
    a mitad de uno, "running" se quedaba en True y el escáner no volvía a
    ejecutarse nunca (pasó del 20 al 26-09-2026)."""
    with _lock:
        state = _load_json(STATE_FILE, STATE_DEFAULTS)
        if state.get("running"):
            state["running"] = False
            state["next_run"] = None
            _save_json(STATE_FILE, state)
            print("[scanner] estado 'running' huérfano limpiado al arrancar")


_limpiar_running_huerfano()
threading.Thread(target=_scanner_loop, daemon=True, name="viral-scanner").start()
