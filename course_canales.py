"""
course_canales.py
Canales de YouTube y vinculos curso-canal, muchos a muchos.

Un curso puede ir a varios canales y un canal puede tener varios cursos.
Cada vinculo guarda su propia URL publicada (vacia hasta que exista) y un
estado propio: pendiente, subido u omitido.

Persistencia, igual que los cursos: JSON en _cursos/.
  _cursos/canales.json
  _cursos/vinculos.json

No sube videos. Sin credenciales de YouTube, al terminar la generacion el
vinculo queda en "omitido": la subida es debida, pero no se finge que ocurrio.
"""

from __future__ import annotations

import json
import re

import course_store as cs

CANALES_PATH = cs.CURSOS_DIR / "canales.json"
VINCULOS_PATH = cs.CURSOS_DIR / "vinculos.json"

ESTADOS = ("pendiente", "subido", "omitido")
_CANAL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")

# Canal publico de la marca. No es el unico: se anaden los que se configuren.
CANAL_RAYVERSEC = {
    "channel_id": "UCbEnilZIVXwp9lNAv91j69g",
    "handle": "@RAYVERSEC",
    "nombre": "RayverSec",
}


def _atomic(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with cs._lock:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def _leer(path, clave: str) -> list:
    if not path.exists():
        return []
    with cs._lock:
        data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get(clave) or []
    if not isinstance(items, list):
        raise ValueError(path.name + " no es una lista")
    return items


def _norm_handle(handle: str) -> str:
    h = (handle or "").strip()
    if not h:
        raise ValueError("el handle del canal es obligatorio")
    if not h.startswith("@"):
        h = "@" + h
    if len(h) < 2 or any(c in h for c in "/\\ "):
        raise ValueError("handle no valido")
    return h


def _norm_channel_id(channel_id: str) -> str:
    cid = (channel_id or "").strip()
    if not _CANAL_ID.match(cid):
        raise ValueError("channel_id de YouTube no valido")
    return cid


def _norm_nombre(nombre: str) -> str:
    n = (nombre or "").strip()
    if not n:
        raise ValueError("el nombre del canal es obligatorio")
    return n


def _cargar_canales() -> list:
    """Crea el registro con RayverSec la primera vez. No pisa canales ya guardados."""
    if not CANALES_PATH.exists():
        ahora = cs.ahora()
        semilla = [dict(CANAL_RAYVERSEC, creado=ahora, actualizado=ahora)]
        _atomic(CANALES_PATH, {"canales": semilla})
        return semilla
    return _leer(CANALES_PATH, "canales")


def listar_canales() -> list:
    return _cargar_canales()


def agregar_canal(channel_id: str, handle: str, nombre: str) -> dict:
    cid = _norm_channel_id(channel_id)
    handle = _norm_handle(handle)
    nombre = _norm_nombre(nombre)
    with cs._lock:
        canales = _cargar_canales()
        ahora = cs.ahora()
        for c in canales:
            if c.get("channel_id") == cid:
                c["handle"] = handle
                c["nombre"] = nombre
                c["actualizado"] = ahora
                _atomic(CANALES_PATH, {"canales": canales})
                return dict(c)
        nuevo = {
            "channel_id": cid,
            "handle": handle,
            "nombre": nombre,
            "creado": ahora,
            "actualizado": ahora,
        }
        canales.append(nuevo)
        _atomic(CANALES_PATH, {"canales": canales})
        return dict(nuevo)


def buscar_canal(channel_id: str) -> dict:
    cid = _norm_channel_id(channel_id)
    for c in _cargar_canales():
        if c.get("channel_id") == cid:
            return c
    raise KeyError(cid)


def listar_vinculos(curso_id: str | None = None, channel_id: str | None = None) -> list:
    vins = _leer(VINCULOS_PATH, "vinculos")
    if curso_id:
        vins = [v for v in vins if v.get("curso_id") == curso_id]
    if channel_id:
        cid = _norm_channel_id(channel_id)
        vins = [v for v in vins if v.get("channel_id") == cid]
    return vins


def vincular(curso_id: str, channel_id: str) -> dict:
    """Une un curso ya existente con un canal ya registrado. Idempotente."""
    cs.cargar(curso_id)
    canal = buscar_canal(channel_id)
    cid = canal["channel_id"]
    with cs._lock:
        vins = _leer(VINCULOS_PATH, "vinculos")
        for v in vins:
            if v.get("curso_id") == curso_id and v.get("channel_id") == cid:
                return dict(v)
        nuevo = {
            "curso_id": curso_id,
            "channel_id": cid,
            "url_publicada": "",
            "estado": "pendiente",
            "motivo": "",
            "debida": False,
            "actualizado": cs.ahora(),
        }
        vins.append(nuevo)
        _atomic(VINCULOS_PATH, {"vinculos": vins})
        return dict(nuevo)


def desvincular(curso_id: str, channel_id: str) -> None:
    cid = _norm_channel_id(channel_id)
    with cs._lock:
        vins = _leer(VINCULOS_PATH, "vinculos")
        queda = [v for v in vins if not (v.get("curso_id") == curso_id and v.get("channel_id") == cid)]
        _atomic(VINCULOS_PATH, {"vinculos": queda})


def quitar_vinculos_curso(curso_id: str) -> None:
    with cs._lock:
        vins = _leer(VINCULOS_PATH, "vinculos")
        queda = [v for v in vins if v.get("curso_id") != curso_id]
        if len(queda) != len(vins):
            _atomic(VINCULOS_PATH, {"vinculos": queda})


def guardar_url_publicada(curso_id: str, channel_id: str, url: str) -> dict:
    """Guarda el enlace del curso en ESE canal cuando ya existe. No sube nada."""
    url = (url or "").strip()
    if not url.startswith("https://"):
        raise ValueError("la URL publicada tiene que ser https")
    cid = _norm_channel_id(channel_id)
    with cs._lock:
        vins = _leer(VINCULOS_PATH, "vinculos")
        for v in vins:
            if v.get("curso_id") == curso_id and v.get("channel_id") == cid:
                v["url_publicada"] = url
                v["estado"] = "subido"
                v["debida"] = False
                v["motivo"] = ""
                v["actualizado"] = cs.ahora()
                _atomic(VINCULOS_PATH, {"vinculos": vins})
                return dict(v)
    raise KeyError("sin vinculo")


def _credenciales_youtube() -> bool:
    """True solo si youtube_uploader puede cargar credenciales.
    No devuelve secretos y no llama a la API."""
    try:
        import youtube_uploader
        youtube_uploader._load_credentials()
    except Exception:
        return False
    return True


def registrar_subidas_al_terminar(curso_id: str) -> list:
    """El curso ya esta generado. Marca la subida como debida en TODOS los
    canales vinculados.

    Sin credenciales: estado omitido. Con credenciales: estado pendiente.
    En ningun caso estado subido ni URL inventada: este modulo no sube.
    Un vinculo que ya tiene URL publicada no se toca.
    """
    hay = _credenciales_youtube()
    with cs._lock:
        vins = _leer(VINCULOS_PATH, "vinculos")
        tocados = []
        ahora = cs.ahora()
        for v in vins:
            if v.get("curso_id") != curso_id:
                continue
            if v.get("estado") == "subido" and v.get("url_publicada"):
                tocados.append(dict(v))
                continue
            v["debida"] = True
            v["actualizado"] = ahora
            v["url_publicada"] = v.get("url_publicada") or ""
            if not hay:
                v["estado"] = "omitido"
                v["motivo"] = "sin credenciales de YouTube; subida no ejecutada"
            else:
                v["estado"] = "pendiente"
                v["motivo"] = "subida por canal no implementada; no se ha publicado"
            tocados.append(dict(v))
        if any(v.get("curso_id") == curso_id for v in vins):
            _atomic(VINCULOS_PATH, {"vinculos": vins})
        return tocados
