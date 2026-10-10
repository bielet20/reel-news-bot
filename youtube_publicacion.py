"""
youtube_publicacion.py
Publicación diferida de vídeos de YouTube.

Flujo:
  1. youtube_uploader.subir_video() sube SIEMPRE en privado y llama a
     registrar_subida(), que apunta el vídeo en _config/youtube_publicacion.json.
  2. Un hilo publicador (arrancado por api/youtube_publicacion_api.py al iniciar
     el backend) revisa cada ~5 min las entradas cuya next_check_at ya pasó
     (subida + 2h30m):
       - videos.list(status,processingDetails)
       - procesado      -> videos.update(status) a "public" conservando el resto
                           de campos de status  -> estado "publicado"
       - procesando     -> reprograma +30 min (nunca publica a ciegas)
       - fallido/rechazado/borrado/no encontrado -> estado "error" (sigue privado)
       - 3 errores seguidos de API/red, o >24 h procesando -> estado "bloqueado"
  El estado vive en disco, así que sobrevive a reinicios/recargas del backend.

DESDE 10/2026: la publicación es MANUAL por defecto (botón "Publicar" de la web,
publicar_manual()). El publicador automático solo funciona con YT_AUTOPUBLICAR=1.

Ver docs/youtube_publicacion_diferida.md
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CORE_DIR = Path(__file__).parent
STATE_FILE = CORE_DIR / "_config" / "youtube_publicacion.json"
LOG_FILE = CORE_DIR / "_config" / "youtube_publicacion.log"

ESPERA_INICIAL = timedelta(hours=2, minutes=30)
REINTENTO_PROCESANDO = timedelta(minutes=30)
REINTENTO_ERROR = timedelta(minutes=15)
EDAD_MAXIMA = timedelta(hours=24)
MAX_ERRORES = 3
INTERVALO_BUCLE_S = 300  # 5 min

# Campos de status que se conservan al pasar a público (para no resetearlos)
_CAMPOS_STATUS_CONSERVAR = (
    "embeddable",
    "license",
    "publicStatsViewable",
    "selfDeclaredMadeForKids",
    "containsSyntheticMedia",
)

_lock = threading.RLock()


def autopublicar_activo() -> bool:
    """Publicador automático 2h30m: DESACTIVADO salvo YT_AUTOPUBLICAR=1/true/si."""
    return os.environ.get("YT_AUTOPUBLICAR", "0").strip().lower() in ("1", "true", "si", "sí", "yes")
_HISTORIAL_MAX = 50


# ── utilidades ────────────────────────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def log(nivel: str, msg: str):
    """Escribe en stdout (docker logs, convención del proyecto) y en
    _config/youtube_publicacion.log. Nunca se registran tokens ni respuestas
    completas de la API."""
    linea = f"[YT-Publicacion][{nivel}] {msg}"
    print(linea, flush=True)
    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{_iso(_ahora())} {linea}\n")
    except Exception:
        pass


def _cargar() -> list[dict]:
    if not STATE_FILE.exists():
        return []
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        # No sobrescribimos un fichero corrupto: se guarda copia y se avisa.
        log("ERROR", f"No se pudo leer {STATE_FILE.name}: {e}")
        raise


def _guardar(items: list[dict]):
    STATE_FILE.parent.mkdir(exist_ok=True)
    tmp = STATE_FILE.with_name(STATE_FILE.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def _hist(entry: dict, evento: str, detalle: str = ""):
    h = entry.setdefault("history", [])
    h.append({"at": _iso(_ahora()), "evento": evento, "detalle": detalle[:300]})
    del h[:-_HISTORIAL_MAX]


def _alerta(entry: dict, msg: str):
    """Alerta: queda en el log a nivel ERROR y en el propio registro
    (campo 'alerta'), visible en GET /api/youtube/publicacion.
    No se envía a Telegram/WhatsApp porque esos canales son de distribución
    pública del bot."""
    entry["alerta"] = msg[:300]
    log("ERROR", f"ALERTA video={entry.get('video_id')} historia={entry.get('story_id')}: {msg}")


# ── API pública ───────────────────────────────────────────────────────────────

def registrar_subida(video_id: str, titulo: str = "", story_id: str = "",
                     video_path: str = "") -> dict:
    """Registra un vídeo recién subido en privado para publicarlo más tarde."""
    ahora = _ahora()
    entry = {
        "video_id": video_id,
        "story_id": story_id,
        "titulo": (titulo or "")[:200],
        "video_path": video_path,
        "uploaded_at": _iso(ahora),
        "next_check_at": _iso(ahora + ESPERA_INICIAL),
        "attempts": 0,
        "error_count": 0,
        "state": "pendiente",
        "published_at": None,
        "alerta": None,
        "history": [],
    }
    _hist(entry, "subida privada", "")
    with _lock:
        items = _cargar()
        items = [i for i in items if i.get("video_id") != video_id]
        items.append(entry)
        _guardar(items)
    if autopublicar_activo():
        log("INFO", f"subida privada video={video_id} historia={story_id} "
                    f"comprobación automática programada {entry['next_check_at']} (UTC)")
    else:
        log("INFO", f"subida privada video={video_id} historia={story_id} "
                    "pendiente de publicar con el botón Publicar")
    return entry


def listar() -> list[dict]:
    with _lock:
        return _cargar()


def obtener(video_id: str) -> dict | None:
    with _lock:
        return next((e for e in _cargar() if e.get("video_id") == video_id), None)


def reintentar(video_id: str) -> dict | None:
    """Vuelve a poner en 'pendiente' un vídeo bloqueado/en error, para
    comprobarlo ya (en el siguiente ciclo del publicador)."""
    with _lock:
        items = _cargar()
        for e in items:
            if e.get("video_id") == video_id:
                e["state"] = "pendiente"
                e["error_count"] = 0
                e["alerta"] = None
                e["next_check_at"] = _iso(_ahora())
                # se reinicia el reloj de las 24 h para no re-bloquear al instante
                e["retry_from"] = _iso(_ahora())
                _hist(e, "reintento manual", "")
                _guardar(items)
                log("INFO", f"reintento manual video={video_id} historia={e.get('story_id')}")
                return e
    return None


# ── Lógica de comprobación (testeable con un cliente falso) ───────────────────

def _motivo_error_api(exc: Exception) -> str:
    try:
        from youtube_uploader import _yt_error_message
        return _yt_error_message(exc)[:200]
    except Exception:
        return f"{type(exc).__name__}: {str(exc)[:200]}"


def procesar_entrada(service, entry: dict, ahora: datetime | None = None) -> str:
    """Comprueba un vídeo y aplica la transición. Devuelve el nuevo estado.
    Modifica 'entry' en sitio. No hace nada si no le toca todavía."""
    ahora = ahora or _ahora()
    if entry.get("state") != "pendiente":
        return entry.get("state")
    nca = _parse(entry.get("next_check_at"))
    if nca and nca > ahora:
        return "pendiente"

    vid = entry["video_id"]
    sid = entry.get("story_id", "")
    entry["attempts"] = entry.get("attempts", 0) + 1

    # 1) videos.list
    try:
        resp = service.videos().list(part="status,processingDetails", id=vid).execute()
    except Exception as exc:
        return _registrar_error(entry, ahora, f"videos.list falló: {_motivo_error_api(exc)}")

    items = (resp or {}).get("items") or []
    if not items:
        entry["state"] = "error"
        _hist(entry, "error", "vídeo no encontrado en YouTube")
        _alerta(entry, "Vídeo no encontrado (¿borrado?). No se publica.")
        return "error"

    status = items[0].get("status") or {}
    proc = items[0].get("processingDetails") or {}
    upload_status = status.get("uploadStatus")
    proc_status = proc.get("processingStatus")
    privacidad = status.get("privacyStatus")

    detalle = f"uploadStatus={upload_status} processingStatus={proc_status} privacy={privacidad}"
    _hist(entry, "comprobación de estado", detalle)
    log("INFO", f"comprobación de estado video={vid} historia={sid}: {detalle}")

    if upload_status in ("failed", "rejected", "deleted") or proc_status in ("failed", "terminated"):
        motivo = status.get("failureReason") or status.get("rejectionReason") or ""
        entry["state"] = "error"
        _hist(entry, "error", f"{detalle} {motivo}".strip())
        _alerta(entry, f"YouTube no pudo procesar el vídeo ({detalle} {motivo}). Se queda privado.")
        return "error"

    if privacidad == "public":
        entry["state"] = "publicado"
        entry["published_at"] = entry.get("published_at") or _iso(ahora)
        _hist(entry, "publicado", "ya estaba público (cambio manual)")
        log("INFO", f"publicado video={vid} historia={sid} (ya era público)")
        return "publicado"
    if privacidad != "private":
        entry["state"] = "bloqueado"
        _hist(entry, "bloqueado", f"privacidad cambiada a mano a '{privacidad}'")
        _alerta(entry, f"La privacidad se cambió a mano a '{privacidad}'; no se toca.")
        return "bloqueado"

    procesado = upload_status == "processed" and proc_status in (None, "succeeded")
    if not procesado:
        base = _parse(entry.get("retry_from")) or _parse(entry.get("uploaded_at")) or ahora
        if ahora - base >= EDAD_MAXIMA:
            entry["state"] = "bloqueado"
            _hist(entry, "bloqueado", f"sigue sin procesar tras 24 h ({detalle})")
            _alerta(entry, f"Sigue sin procesar tras 24 h ({detalle}). Se queda privado.")
            return "bloqueado"
        entry["error_count"] = 0  # ciclo completo sin errores
        entry["next_check_at"] = _iso(ahora + REINTENTO_PROCESANDO)
        _hist(entry, "reprogramado", f"aún procesando; siguiente {entry['next_check_at']}")
        log("INFO", f"reprogramado video={vid} historia={sid}: aún procesando, "
                    f"siguiente comprobación {entry['next_check_at']} (UTC)")
        return "pendiente"

    # 2) videos.update -> public, conservando el resto de campos de status
    nuevo_status = {k: status[k] for k in _CAMPOS_STATUS_CONSERVAR if k in status}
    nuevo_status["privacyStatus"] = "public"
    try:
        service.videos().update(part="status", body={"id": vid, "status": nuevo_status}).execute()
    except Exception as exc:
        return _registrar_error(entry, ahora, f"videos.update falló: {_motivo_error_api(exc)}")

    entry["state"] = "publicado"
    entry["published_at"] = _iso(ahora)
    entry["error_count"] = 0
    entry["alerta"] = None
    _hist(entry, "publicado", "")
    log("INFO", f"publicado video={vid} historia={sid} https://www.youtube.com/watch?v={vid}")
    return "publicado"


def _registrar_error(entry: dict, ahora: datetime, msg: str) -> str:
    entry["error_count"] = entry.get("error_count", 0) + 1
    _hist(entry, "error", msg)
    if entry["error_count"] >= MAX_ERRORES:
        entry["state"] = "bloqueado"
        _hist(entry, "bloqueado", f"{MAX_ERRORES} errores seguidos")
        _alerta(entry, f"{MAX_ERRORES} errores seguidos; se para y se queda privado. "
                       f"Último: {msg}. Si es de permisos, reconecta YouTube en /canales.")
        return "bloqueado"
    entry["next_check_at"] = _iso(ahora + REINTENTO_ERROR * entry["error_count"])
    log("WARNING", f"error video={entry.get('video_id')} historia={entry.get('story_id')} "
                   f"({entry['error_count']}/{MAX_ERRORES}): {msg}; reintento {entry['next_check_at']} (UTC)")
    return "pendiente"


def ciclo(service_factory=None, ahora: datetime | None = None) -> int:
    """Un ciclo del publicador. Devuelve cuántas entradas se procesaron."""
    if not autopublicar_activo():
        return 0
    ahora = ahora or _ahora()
    with _lock:
        items = _cargar()
    toca = [e for e in items if e.get("state") == "pendiente"
            and (_parse(e.get("next_check_at")) or ahora) <= ahora]
    if not toca:
        return 0

    if service_factory is None:
        from youtube_uploader import _get_service as service_factory
    try:
        service = service_factory()
    except Exception as exc:
        # Sin credenciales/servicio: cuenta como error para cada vídeo pendiente
        msg = f"no se pudo crear el cliente de YouTube: {_motivo_error_api(exc)}"
        with _lock:
            items = _cargar()
            for e in items:
                if e in toca or any(e.get("video_id") == t.get("video_id") for t in toca):
                    _registrar_error(e, ahora, msg)
            _guardar(items)
        return len(toca)

    n = 0
    for t in toca:
        # Trabajamos sobre una copia y la fusionamos con lo que haya en disco
        e = dict(t)
        try:
            procesar_entrada(service, e, ahora)
        except Exception as exc:  # nunca debe matar el bucle
            _registrar_error(e, ahora, f"excepción inesperada: {type(exc).__name__}: {exc}")
        with _lock:
            items = _cargar()
            for idx, cur in enumerate(items):
                if cur.get("video_id") == e["video_id"]:
                    items[idx] = e
            _guardar(items)
        n += 1
    return n


# ── Publicación manual (botón "Publicar" de la web) ─────────────────────────

def _es_error_permisos(exc: Exception) -> bool:
    resp = getattr(exc, "resp", None)
    st = getattr(resp, "status", None)
    texto = str(getattr(exc, "content", b"") or b"") + str(exc)
    if any(r in texto for r in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded",
                                "uploadLimitExceeded")):
        return False
    return st in (401, 403) or any(r in texto for r in (
        "insufficientPermissions", "forbidden", "authorizationRequired",
        "invalidCredentials", "ACCESS_TOKEN_SCOPE_INSUFFICIENT", "insufficient"))


def _actualizar_entrada(video_id: str, cambios: dict, evento: str, detalle: str = ""):
    """Aplica cambios a la entrada del vídeo (la crea si no estaba registrada)."""
    with _lock:
        items = _cargar()
        e = next((i for i in items if i.get("video_id") == video_id), None)
        if e is None:
            e = {"video_id": video_id, "story_id": "", "titulo": "", "video_path": "",
                 "uploaded_at": None, "next_check_at": None, "attempts": 0,
                 "error_count": 0, "state": "pendiente", "published_at": None,
                 "alerta": None, "history": []}
            items.append(e)
        e.update(cambios)
        _hist(e, evento, detalle)
        _guardar(items)
        return e


def publicar_manual(video_id: str, service_factory=None) -> tuple[int, dict]:
    """Publica un vídeo a petición de Biel. Devuelve (código HTTP, cuerpo).
    Solo pasa a público si YouTube ya lo ha procesado; si no, no toca nada."""
    sid = (obtener(video_id) or {}).get("story_id", "")

    def fallo(code: int, msg: str, evento: str = "error publicación manual"):
        log("WARNING" if code == 409 else "ERROR",
            f"publicación manual NO hecha video={video_id} historia={sid}: {msg}")
        try:
            _actualizar_entrada(video_id, {}, evento, msg)
        except Exception:
            pass
        return code, {"ok": False, "video_id": video_id, "estado": "privado", "detail": msg}

    if service_factory is None:
        from youtube_uploader import _get_service as service_factory
    try:
        service = service_factory()
    except Exception as exc:
        return fallo(503, f"No se pudo conectar con YouTube: {_motivo_error_api(exc)}. "
                          "Revisa la cuenta en /canales.")

    try:
        resp = service.videos().list(part="status,processingDetails", id=video_id).execute()
    except Exception as exc:
        if _es_error_permisos(exc):
            return fallo(403, "YouTube ha denegado el permiso. Reconecta la cuenta en /canales "
                              f"(hace falta el permiso 'youtube'). Detalle: {_motivo_error_api(exc)}")
        return fallo(502, f"Error consultando YouTube: {_motivo_error_api(exc)}")

    items = (resp or {}).get("items") or []
    if not items:
        return fallo(404, "El vídeo no existe en YouTube (¿se borró?). No se publica.")

    status = items[0].get("status") or {}
    proc = items[0].get("processingDetails") or {}
    upload_status = status.get("uploadStatus")
    proc_status = proc.get("processingStatus")
    privacidad = status.get("privacyStatus")
    detalle = f"uploadStatus={upload_status} processingStatus={proc_status} privacy={privacidad}"
    log("INFO", f"comprobación de estado (manual) video={video_id} historia={sid}: {detalle}")

    if privacidad == "public":
        e = _actualizar_entrada(video_id, {"state": "publicado", "alerta": None,
                                           "published_at": _iso(_ahora())},
                                "publicado", "ya estaba público")
        log("INFO", f"publicado manualmente video={video_id} historia={sid} (ya era público)")
        return 200, {"ok": True, "video_id": video_id, "estado": "publico",
                     "published_at": e.get("published_at"),
                     "detail": "El vídeo ya era público."}

    if upload_status in ("failed", "rejected", "deleted") or proc_status in ("failed", "terminated"):
        motivo = status.get("failureReason") or status.get("rejectionReason") or ""
        msg = f"YouTube no pudo procesar el vídeo ({detalle} {motivo}).".replace(" )", ")")
        try:
            _actualizar_entrada(video_id, {"state": "error", "alerta": msg}, "error", msg)
        except Exception:
            pass
        log("ERROR", f"publicación manual NO hecha video={video_id} historia={sid}: {msg}")
        return 422, {"ok": False, "video_id": video_id, "estado": "error",
                     "detail": msg + " Se queda privado."}

    if not (upload_status == "processed" and proc_status in (None, "succeeded")):
        return fallo(409, "YouTube todavía está procesando el vídeo, prueba en unos minutos.",
                     "comprobación de estado")

    nuevo_status = {k: status[k] for k in _CAMPOS_STATUS_CONSERVAR if k in status}
    nuevo_status["privacyStatus"] = "public"
    try:
        service.videos().update(part="status", body={"id": video_id, "status": nuevo_status}).execute()
    except Exception as exc:
        if _es_error_permisos(exc):
            return fallo(403, "YouTube no deja cambiar la privacidad: falta el permiso 'youtube'. "
                              "Reconecta la cuenta en /canales. El vídeo sigue privado. "
                              f"Detalle: {_motivo_error_api(exc)}")
        return fallo(502, f"Error publicando en YouTube: {_motivo_error_api(exc)}. Sigue privado.")

    e = _actualizar_entrada(video_id, {"state": "publicado", "alerta": None, "error_count": 0,
                                       "published_at": _iso(_ahora())}, "publicado", "manual")
    log("INFO", f"publicado manualmente video={video_id} historia={sid} "
                f"https://www.youtube.com/watch?v={video_id}")
    return 200, {"ok": True, "video_id": video_id, "estado": "publico",
                 "published_at": e.get("published_at"), "detail": "Vídeo publicado."}


# ── Hilo publicador ───────────────────────────────────────────────────────────

_hilo: threading.Thread | None = None
_hilo_lock = threading.Lock()


def _bucle():
    log("INFO", f"publicador iniciado (cada {INTERVALO_BUCLE_S // 60} min, "
                f"estado en {STATE_FILE.name})")
    time.sleep(20)  # deja arrancar el backend
    while True:
        if not autopublicar_activo():
            log("INFO", "YT_AUTOPUBLICAR desactivado: el publicador automático se detiene")
            return
        try:
            ciclo()
        except Exception as exc:
            log("ERROR", f"fallo en el ciclo del publicador: {type(exc).__name__}: {exc}")
        time.sleep(INTERVALO_BUCLE_S)


def iniciar_publicador():
    """Arranca el hilo publicador una sola vez por proceso."""
    global _hilo
    if not autopublicar_activo():
        log("INFO", "publicador automático DESACTIVADO (YT_AUTOPUBLICAR=0); "
                    "los vídeos se publican con el botón Publicar de la web")
        return
    with _hilo_lock:
        if _hilo and _hilo.is_alive():
            return
        _hilo = threading.Thread(target=_bucle, daemon=True, name="youtube-publicador")
        _hilo.start()
