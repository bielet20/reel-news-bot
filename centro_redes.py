"""
centro_redes.py
Centro de Redes: un solo sitio para las cuentas de redes sociales y los
canales (marcas) que las usan. Todas las aplicaciones publican por aquí.

  Cuenta  = una conexión concreta a una red (p. ej. el YouTube RAYVERMUSIC).
            Sus secretos siguen en _tokens/<fichero>.json; aquí solo se apunta
            a ese fichero, nunca se copian.
  Canal   = una marca (Bieninforma2, RAYVER, RayverSec…). Dice qué cuenta usa
            en cada red y cómo se publica en ella (categoría, pie, tags…).

Registro:       _config/redes.json
Publicaciones:  _config/redes_publicaciones.json (últimas 500)

Fase 1: publicar desde el Centro solo en YouTube. El resto de redes se ven
aquí con su estado, pero se siguen publicando por el sistema de reels.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
TOKENS_DIR = BASE_DIR / "_tokens"
REGISTRO = BASE_DIR / "_config" / "redes.json"
PUBLICACIONES = BASE_DIR / "_config" / "redes_publicaciones.json"
MAX_PUBLICACIONES = 500

PLATAFORMAS = ("youtube", "facebook", "instagram", "tiktok", "x",
               "telegram", "whatsapp_canal")
# Redes en las que el Centro ya sabe publicar.
PUBLICABLES = ("youtube",)

_lock = threading.RLock()

# Lo que había antes del Centro: tokens existentes y canales conocidos.
_SEMILLA = {
    "version": 1,
    "cuentas": [
        {"id": "youtube-bieninforma2", "plataforma": "youtube", "nombre": "Bieninforma2",
         "token": "youtube.json", "channel_id": "UCMNhs1ppgt0SDp-br2J70Ow"},
        {"id": "youtube-rayver", "plataforma": "youtube", "nombre": "RAYVERMUSIC",
         "token": "youtube_rayver.json", "channel_id": "UC1ayyOq-jLYWuT_apjAQ9MA"},
        {"id": "youtube-rayversec", "plataforma": "youtube", "nombre": "RayverSec",
         "token": "youtube-cursos.json", "channel_id": "UCbEnilZIVXwp9lNAv91j69g",
         "handle": "@RAYVERSEC"},
        {"id": "telegram-bieninforma2", "plataforma": "telegram", "nombre": "@Bieninforma2",
         "token": "telegram.json"},
        {"id": "telegram-rayversec", "plataforma": "telegram", "nombre": "RiverSec (cursos)",
         "token": "telegram-cursos.json"},
        {"id": "facebook-bieninforma2", "plataforma": "facebook", "nombre": "Página Bieninforma2",
         "origen": "sistema_reels"},
        {"id": "instagram-bieninforma2", "plataforma": "instagram", "nombre": "Instagram Bieninforma2",
         "origen": "sistema_reels"},
        {"id": "tiktok-bieninforma2", "plataforma": "tiktok", "nombre": "TikTok Bieninforma2",
         "origen": "sistema_reels"},
        {"id": "x-bieninforma2", "plataforma": "x", "nombre": "X Bieninforma2",
         "origen": "sistema_reels"},
        {"id": "whatsapp-bieninforma2", "plataforma": "whatsapp_canal", "nombre": "Canal WhatsApp bieninforma2",
         "token": "whatsapp_canal.json", "origen": "sistema_reels"},
    ],
    "canales": [
        {"id": "bieninforma2", "nombre": "Bieninforma2", "tema": "Noticias de ciencia y tecnología",
         "cuentas": {"youtube": "youtube-bieninforma2", "facebook": "facebook-bieninforma2",
                     "instagram": "instagram-bieninforma2", "tiktok": "tiktok-bieninforma2",
                     "x": "x-bieninforma2", "telegram": "telegram-bieninforma2",
                     "whatsapp_canal": "whatsapp-bieninforma2"},
         "youtube": {"tipo": "noticia", "categoria": "25", "playlist": ""}},
        {"id": "rayver", "nombre": "RAYVER", "tema": "Música original",
         "cuentas": {"youtube": "youtube-rayver"},
         "web": "https://rayvermusic.com",
         "youtube": {"tipo": "musica", "categoria": "10", "playlist": None,
                     "pie": "RAYVER — música original.\nhttps://rayvermusic.com\n\n#RAYVER #RayverMusic",
                     "tags": ["RAYVER", "RayverMusic", "música"]}},
        {"id": "rayversec", "nombre": "RayverSec", "tema": "Cursos y formaciones",
         "cuentas": {"youtube": "youtube-rayversec", "telegram": "telegram-rayversec"},
         "youtube": {"tipo": "curso", "categoria": "27", "playlist": None,
                     "pie": "RayverSec — cursos y formaciones.\n\n#RayverSec #Cursos",
                     "tags": ["RayverSec", "curso", "formación"]}},
    ],
}


class RedesError(Exception):
    """Error con mensaje para el usuario (dato que falta, canal mal elegido…)."""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _escribir(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def slug(texto: str) -> str:
    s = (texto or "").strip().lower()
    for a, b in zip("áéíóúüñ", "aeiouun"):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:40]


# ── Registro ──────────────────────────────────────────────────────────────────

def cargar() -> dict:
    """Registro completo. La primera vez lo crea con lo que ya existía."""
    with _lock:
        if not REGISTRO.exists():
            data = json.loads(json.dumps(_SEMILLA))
            for c in data["cuentas"] + data["canales"]:
                c["creado"] = _ahora()
            _escribir(REGISTRO, data)
            return data
        data = json.loads(REGISTRO.read_text(encoding="utf-8"))
        data.setdefault("cuentas", [])
        data.setdefault("canales", [])
        return data


def guardar(data: dict) -> None:
    with _lock:
        _escribir(REGISTRO, data)


def cuenta(cuenta_id: str) -> dict:
    for c in cargar()["cuentas"]:
        if c["id"] == cuenta_id:
            return c
    raise RedesError(f"No existe la cuenta «{cuenta_id}».")


def canal(canal_id: str) -> dict:
    for c in cargar()["canales"]:
        if c["id"] == canal_id:
            return c
    raise RedesError(f"No existe el canal «{canal_id}».")


def token_path(c: dict) -> Path | None:
    nombre = c.get("token")
    if not nombre:
        return None
    p = (TOKENS_DIR / nombre).resolve()
    if p.parent != TOKENS_DIR.resolve():
        raise RedesError("Fichero de token no válido.")
    return p


def crear_cuenta(plataforma: str, nombre: str, channel_id: str = "") -> dict:
    """Cuenta nueva sin conectar. Para YouTube se conecta luego con Google."""
    if plataforma not in PLATAFORMAS:
        raise RedesError(f"Red no soportada: {plataforma}.")
    nombre = (nombre or "").strip()
    if not nombre:
        raise RedesError("Pon un nombre a la cuenta.")
    with _lock:
        data = cargar()
        base = f"{plataforma}-{slug(nombre) or 'cuenta'}"
        cid, n = base, 2
        ids = {c["id"] for c in data["cuentas"]}
        while cid in ids:
            cid, n = f"{base}-{n}", n + 1
        nueva = {"id": cid, "plataforma": plataforma, "nombre": nombre,
                 "token": f"{cid}.json", "creado": _ahora()}
        if channel_id.strip():
            nueva["channel_id"] = channel_id.strip()
        data["cuentas"].append(nueva)
        guardar(data)
        return nueva


def borrar_cuenta(cuenta_id: str) -> None:
    """Quita la cuenta del Centro (y de los canales). El token se conserva."""
    with _lock:
        data = cargar()
        if not any(c["id"] == cuenta_id for c in data["cuentas"]):
            raise RedesError(f"No existe la cuenta «{cuenta_id}».")
        data["cuentas"] = [c for c in data["cuentas"] if c["id"] != cuenta_id]
        for ch in data["canales"]:
            ch["cuentas"] = {k: v for k, v in ch.get("cuentas", {}).items() if v != cuenta_id}
        guardar(data)


def guardar_canal(canal_id: str, nombre: str = "", tema: str = "",
                  cuentas: dict | None = None, youtube: dict | None = None,
                  web: str | None = None) -> dict:
    """Crea o actualiza un canal. `cuentas` = {red: cuenta_id}; "" la quita."""
    with _lock:
        data = cargar()
        ids_cuentas = {c["id"]: c for c in data["cuentas"]}
        canal_id = slug(canal_id or nombre)
        if not canal_id:
            raise RedesError("Pon un nombre al canal.")
        ch = next((c for c in data["canales"] if c["id"] == canal_id), None)
        if ch is None:
            ch = {"id": canal_id, "nombre": nombre.strip() or canal_id, "tema": "",
                  "cuentas": {}, "youtube": {"tipo": "general", "categoria": "22",
                                             "playlist": None}, "creado": _ahora()}
            data["canales"].append(ch)
        if nombre.strip():
            ch["nombre"] = nombre.strip()
        if tema:
            ch["tema"] = tema.strip()
        if web is not None:
            ch["web"] = web.strip()
        for red, cid in (cuentas or {}).items():
            if red not in PLATAFORMAS:
                raise RedesError(f"Red no soportada: {red}.")
            if not cid:
                ch["cuentas"].pop(red, None)
                continue
            if cid not in ids_cuentas:
                raise RedesError(f"No existe la cuenta «{cid}».")
            if ids_cuentas[cid]["plataforma"] != red:
                raise RedesError(f"La cuenta «{cid}» no es de {red}.")
            ch["cuentas"][red] = cid
        if youtube:
            ch.setdefault("youtube", {}).update(youtube)
        ch["actualizado"] = _ahora()
        guardar(data)
        return ch


# ── Estado de las cuentas ────────────────────────────────────────────────────

_cache_estado: dict[str, tuple[float, dict]] = {}
CACHE_ESTADO_S = 600


def estado_cuenta(c: dict, comprobar: bool = False) -> dict:
    """Estado sin secretos. Con comprobar=True pregunta a la red de verdad."""
    out = {"conectada": False, "motivo": ""}
    if c.get("origen") == "sistema_reels" and c["plataforma"] != "youtube":
        out.update(_estado_sistema_reels(c["plataforma"]))
        out["gestion"] = "Se conecta en Canales (sistema de reels)."
        return out
    p = token_path(c)
    if c["plataforma"] == "youtube":
        if not p or not p.exists():
            out["motivo"] = "sin conectar"
            return out
        clave = c["id"]
        hit = _cache_estado.get(clave)
        if not comprobar and hit and time.time() - hit[0] < CACHE_ESTADO_S:
            return dict(hit[1])
        try:
            import youtube_uploader as yt
            real = yt.canal_del_token(p)
            out.update(canal=real["titulo"], custom_url=real["custom_url"],
                       channel_id_real=real["channel_id"])
            esperado = c.get("channel_id")
            if esperado and real["channel_id"] != esperado:
                out["motivo"] = f"el token es de «{real['titulo']}», no de este canal"
            else:
                out["conectada"] = True
        except Exception as e:
            out["motivo"] = motivo_error(e)
        _cache_estado[clave] = (time.time(), dict(out))
        return out
    if c["plataforma"] == "telegram":
        try:
            d = json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else {}
        except Exception:
            d = {}
        out["conectada"] = bool(d.get("bot_token") and d.get("chat_id"))
        out["destino"] = d.get("chat_id", "")
        if not out["conectada"]:
            out["motivo"] = "falta el bot o el chat"
        return out
    out["conectada"] = bool(p and p.exists())
    if not out["conectada"]:
        out["motivo"] = "sin conectar"
    return out


def motivo_error(e: Exception) -> str:
    """Mensaje legible. invalid_grant = Google revocó o caducó la autorización
    (pasa a los 7 días si la app de Google Cloud está en modo «Prueba»)."""
    if "invalid_grant" in str(e):
        return "autorización caducada o revocada por Google: pulsa Conectar"
    try:
        import youtube_uploader as yt
        return yt._yt_error_message(e)
    except Exception:
        return str(e)


def _estado_sistema_reels(plataforma: str) -> dict:
    try:
        from api.accounts import accounts_status
        st = accounts_status().get(plataforma) or {}
        return {"conectada": bool(st.get("connected")),
                "motivo": "" if st.get("connected") else "sin conectar"}
    except Exception as e:
        return {"conectada": False, "motivo": f"no se pudo comprobar: {e}"}


def olvidar_estado(cuenta_id: str | None = None) -> None:
    if cuenta_id:
        _cache_estado.pop(cuenta_id, None)
    else:
        _cache_estado.clear()


def resumen(comprobar: bool = False) -> dict:
    """Todo el Centro para la interfaz: cuentas con estado y canales."""
    data = cargar()
    cuentas = []
    for c in data["cuentas"]:
        item = {k: v for k, v in c.items() if k != "token"}
        item["estado"] = estado_cuenta(c, comprobar)
        item["publicable"] = c["plataforma"] in PUBLICABLES
        cuentas.append(item)
    return {"cuentas": cuentas, "canales": data["canales"],
            "plataformas": list(PLATAFORMAS), "publicables": list(PUBLICABLES)}


# ── Conectar YouTube (OAuth) ─────────────────────────────────────────────────

def guardar_token_youtube(cuenta_id: str, tokens: dict, real: dict) -> dict:
    """Guarda la autorización de Google en el token de la cuenta.
    Si la cuenta ya tiene canal fijado y Google devolvió otro, NO guarda."""
    with _lock:
        data = cargar()
        c = next((x for x in data["cuentas"] if x["id"] == cuenta_id), None)
        if c is None or c["plataforma"] != "youtube":
            raise RedesError("Cuenta de YouTube no encontrada.")
        if c.get("channel_id") and c["channel_id"] != real["channel_id"]:
            raise RedesError(f"Elegiste «{real['titulo']}», que no es el canal de esta cuenta.")
        p = token_path(c)
        previo = {}
        if p.exists():
            try:
                previo = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                previo = {}
        previo.update(tokens)
        previo.update(canal=real["titulo"], channel_id=real["channel_id"])
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(previo, indent=2, ensure_ascii=False), encoding="utf-8")
        c["channel_id"] = real["channel_id"]
        if real.get("custom_url"):
            c["handle"] = real["custom_url"]
        c["conectada_el"] = _ahora()
        guardar(data)
    import youtube_uploader as yt
    yt.invalidate_service_cache(p)
    olvidar_estado(cuenta_id)
    return c


# ── Publicar ─────────────────────────────────────────────────────────────────

def _publicar_youtube(ch: dict, c: dict, video: Path, titulo: str, descripcion: str,
                      privacidad: str, miniatura: str | None) -> dict:
    import youtube_uploader as yt
    cfg = ch.get("youtube") or {}
    tipo = cfg.get("tipo", "general")
    if not descripcion and cfg.get("pie"):
        descripcion = f"{titulo}\n\n{cfg['pie']}"
    if not descripcion and tipo not in ("noticia", "curiosidad"):
        descripcion = titulo
    try:
        return yt.subir_video(
            video_path=str(video),
            titulo=titulo,
            tipo=tipo if tipo in ("noticia", "curiosidad") else "curiosidad",
            thumbnail_path=miniatura or None,
            token_file=token_path(c),
            categoria_id=cfg.get("categoria"),
            descripcion_override=descripcion or None,
            exigir_channel_id=c.get("channel_id"),
            playlist=cfg.get("playlist", None),
            # sin tags propios: los de noticias solo para noticias/curiosidades
            tags=cfg["tags"] if "tags" in cfg else (None if tipo in ("noticia", "curiosidad") else []),
            privacidad=privacidad,
        )
    except RedesError:
        raise
    except Exception as e:
        raise RedesError(motivo_error(e)) from e


def publicar(canal_id: str, video: str | Path, titulo: str, descripcion: str = "",
             redes: list[str] | None = None, privacidad: str = "public",
             miniatura: str | None = None, origen: str = "") -> dict:
    """Publica un vídeo en las redes de un canal.

    redes=None → todas las redes del canal que el Centro sabe publicar.
    Devuelve {red: {"ok": bool, "url"?, "video_id"?, "error"?}}. Cada intento
    queda en el historial de publicaciones.
    """
    ch = canal(canal_id)
    video = Path(video)
    if not video.is_file():
        raise RedesError(f"No encuentro el vídeo: {video.name}")
    titulo = (titulo or video.stem).strip()
    if privacidad not in ("public", "unlisted", "private"):
        raise RedesError("Privacidad no válida (public, unlisted o private).")
    disponibles = ch.get("cuentas", {})
    if redes is None:
        redes = [r for r in disponibles if r in PUBLICABLES]
    if not redes:
        raise RedesError(f"El canal «{ch['nombre']}» no tiene ninguna red en la que el Centro sepa publicar.")

    resultados: dict[str, dict] = {}
    for red in redes:
        if red not in disponibles:
            resultados[red] = {"ok": False, "error": f"El canal no tiene cuenta de {red}."}
            continue
        if red not in PUBLICABLES:
            resultados[red] = {"ok": False, "error": f"Publicar en {red} desde el Centro aún no está disponible."}
            continue
        c = cuenta(disponibles[red])
        try:
            r = _publicar_youtube(ch, c, video, titulo, descripcion, privacidad, miniatura)
            resultados[red] = {"ok": True, "cuenta": c["id"], **r}
        except RedesError as e:
            resultados[red] = {"ok": False, "cuenta": c["id"], "error": str(e)}
        except Exception as e:  # noqa: BLE001 — el error real va al historial
            resultados[red] = {"ok": False, "cuenta": c["id"], "error": str(e)}

    registrar_publicacion({
        "fecha": _ahora(), "canal": canal_id, "titulo": titulo, "video": video.name,
        "origen": origen, "privacidad": privacidad, "resultados": resultados,
    })
    return resultados


def registrar_publicacion(item: dict) -> None:
    with _lock:
        lista = publicaciones()
        lista.insert(0, item)
        _escribir(PUBLICACIONES, lista[:MAX_PUBLICACIONES])


def publicaciones(canal_id: str | None = None) -> list:
    with _lock:
        if not PUBLICACIONES.exists():
            return []
        try:
            lista = json.loads(PUBLICACIONES.read_text(encoding="utf-8"))
        except Exception:
            return []
    if canal_id:
        lista = [p for p in lista if p.get("canal") == canal_id]
    return lista
