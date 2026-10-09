"""
course_publicar.py
Subir un curso ya renderizado a YouTube (petición 2026-10-07): eligiendo qué
lecciones (o todas, o el vídeo del curso completo con capítulos) y con qué
privacidad: pública, oculta o privada.

Sube por el Centro de Redes (centro_redes.publicar), al canal de cursos
(RayverSec por defecto), sin tocar el token de Bieninforma2. Cada lección va
a una lista de reproducción con el nombre del curso.

Lo subido se apunta en _cursos/<id>/publicaciones.json y NO en curso.json: el
editor guarda los módulos enteros y pisaría lo que escribiera aquí.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import course_store as cs

CANAL_CURSOS = "rayversec"
PRIVACIDADES = ("public", "unlisted", "private")
NOMBRE_PRIVACIDAD = {"public": "público", "unlisted": "oculto", "private": "privado"}
COMPLETO = "completo"  # clave del vídeo del curso entero en publicaciones.json


def _ruta_publicaciones(curso_id: str) -> Path:
    return cs.dir_curso(curso_id) / "publicaciones.json"


def publicaciones(curso_id: str) -> dict:
    """{leccion_id | "completo": {url, video_id, privacidad, fecha, canal}}"""
    ruta = _ruta_publicaciones(curso_id)
    if not ruta.exists():
        return {}
    with cs._lock:
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _apuntar(curso_id: str, clave: str, dato: dict) -> None:
    ruta = _ruta_publicaciones(curso_id)
    with cs._lock:
        todo = publicaciones(curso_id)
        todo[clave] = dato
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(todo, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(ruta)


def lecciones_en_orden(curso: dict) -> list:
    """[(numero, modulo, leccion)] en el orden del temario."""
    out, n = [], 0
    for m in curso.get("modulos") or []:
        for l in m.get("lecciones") or []:
            n += 1
            out.append((n, m, l))
    return out


def estado(curso_id: str) -> dict:
    """Qué se puede subir y qué está ya subido, para el panel del editor."""
    curso = cs.cargar(curso_id)
    base = cs.dir_curso(curso_id)
    pubs = publicaciones(curso_id)
    lecciones = []
    for n, m, l in lecciones_en_orden(curso):
        render = l.get("render") or {}
        lista = bool(render.get("archivo")) and (base / render["archivo"]).is_file()
        lecciones.append({
            "id": l["id"], "numero": n, "titulo": l.get("titulo", ""), "modulo": m.get("titulo", ""),
            "duracion": render.get("duracion") if lista else None,
            "renderizada": lista, "publicada": pubs.get(l["id"]),
        })
    render = curso.get("render") or {}
    completo = bool(render.get("archivo")) and (base / render["archivo"]).is_file()
    return {
        "lecciones": lecciones,
        "completo": {"renderizado": completo, "duracion": render.get("duracion") if completo else None,
                     "publicado": pubs.get(COMPLETO)},
        "todas_renderizadas": bool(lecciones) and all(x["renderizada"] for x in lecciones),
        "canal": CANAL_CURSOS,
    }


def _pie(canal_id: str) -> str:
    import centro_redes as cr
    return ((cr.canal(canal_id).get("youtube") or {}).get("pie") or "").strip()


def titulo_leccion(curso: dict, numero: int, leccion: dict) -> str:
    titulo = f"{curso['titulo']} | {numero}. {leccion.get('titulo', '')}"
    if len(titulo) > 100:  # límite de YouTube: se recorta el nombre del curso, no la lección
        resto = f" | {numero}. {leccion.get('titulo', '')}"
        titulo = (curso["titulo"][:max(10, 99 - len(resto))].rstrip() + "…" + resto)[:100]
    return titulo


def descripcion_leccion(curso: dict, numero: int, total: int, leccion: dict, pie: str) -> str:
    partes = [leccion.get("titulo", ""), f"Lección {numero} de {total} del curso «{curso['titulo']}»."]
    if (curso.get("descripcion") or "").strip():
        partes.append(curso["descripcion"].strip())
    objetivos = [o for o in leccion.get("objetivos") or [] if str(o).strip()]
    if objetivos:
        partes.append("En esta lección:\n" + "\n".join(f"• {o}" for o in objetivos))
    if pie:
        partes.append(pie)
    return "\n\n".join(partes)


def descripcion_completo(curso: dict, capitulos: str, pie: str) -> str:
    partes = [curso["titulo"]]
    if (curso.get("descripcion") or "").strip():
        partes.append(curso["descripcion"].strip())
    if capitulos.strip():
        partes.append("Capítulos:\n" + capitulos.strip())
    if pie:
        partes.append(pie)
    return "\n\n".join(partes)


def _miniatura(curso_id: str, leccion: dict, carpeta: str) -> str | None:
    """JPG 1280×720 de la primera diapositiva ya capturada (el PNG a 1920 puede
    pasar de los 2 MB que admite YouTube)."""
    escenas = leccion.get("escenas") or []
    if not escenas:
        return None
    png = cs.dir_curso(curso_id) / "render" / "slides" / f"{escenas[0]['id']}.png"
    if not png.is_file():
        return None
    try:
        from PIL import Image
        destino = Path(carpeta) / f"{leccion['id']}.jpg"
        Image.open(png).convert("RGB").resize((1280, 720)).save(destino, "JPEG", quality=90)
        return str(destino)
    except Exception:
        return None


def publicar(curso_id: str, leccion_ids: list[str], completo: bool = False,
             privacidad: str = "public", canal_id: str = CANAL_CURSOS,
             resubir: bool = False, log=print) -> dict:
    """Sube las lecciones elegidas (en el orden del temario) y/o el curso completo.

    Las ya subidas se saltan salvo resubir=True. Un fallo en una lección no para
    las demás. Devuelve {"subidas": [...], "fallos": [...], "saltadas": [...]}.
    """
    import centro_redes as cr
    if privacidad not in PRIVACIDADES:
        raise ValueError("Privacidad no válida: public, unlisted o private.")
    curso = cs.cargar(curso_id)
    base = cs.dir_curso(curso_id)
    pubs = publicaciones(curso_id)
    pie = _pie(canal_id)
    orden = lecciones_en_orden(curso)
    total = len(orden)
    elegidas = [(n, l) for n, _, l in orden if l["id"] in set(leccion_ids)]
    desconocidas = set(leccion_ids) - {l["id"] for _, l in elegidas}
    if desconocidas:
        raise ValueError(f"Lecciones que no son de este curso: {', '.join(sorted(desconocidas))}")

    trabajos = []  # (clave, ruta, titulo, descripcion, leccion|None)
    saltadas = []
    for n, l in elegidas:
        if pubs.get(l["id"]) and not resubir:
            saltadas.append({"id": l["id"], "titulo": l.get("titulo", ""), "motivo": "ya subida"})
            continue
        archivo = (l.get("render") or {}).get("archivo")
        if not archivo or not (base / archivo).is_file():
            saltadas.append({"id": l["id"], "titulo": l.get("titulo", ""), "motivo": "sin renderizar"})
            continue
        trabajos.append((l["id"], base / archivo, titulo_leccion(curso, n, l),
                         descripcion_leccion(curso, n, total, l, pie), l))
    if completo:
        render = curso.get("render") or {}
        if pubs.get(COMPLETO) and not resubir:
            saltadas.append({"id": COMPLETO, "titulo": "Curso completo", "motivo": "ya subido"})
        elif not render.get("archivo") or not (base / render["archivo"]).is_file():
            saltadas.append({"id": COMPLETO, "titulo": "Curso completo", "motivo": "sin renderizar"})
        else:
            cap = base / render["capitulos"] if render.get("capitulos") else None
            capitulos = cap.read_text(encoding="utf-8") if cap and cap.is_file() else ""
            trabajos.append((COMPLETO, base / render["archivo"], curso["titulo"][:100],
                             descripcion_completo(curso, capitulos, pie), None))

    subidas, fallos = [], []
    with tempfile.TemporaryDirectory(prefix="_curso_pub_") as tmp:
        for i, (clave, video, titulo, desc, leccion) in enumerate(trabajos, 1):
            log(f"Subiendo {i}/{len(trabajos)}: {titulo}")
            mini = _miniatura(curso_id, leccion, tmp) if leccion else None
            try:
                res = cr.publicar(canal_id, video, titulo, descripcion=desc, redes=["youtube"],
                                  privacidad=privacidad, miniatura=mini, origen="cursos",
                                  playlist=curso["titulo"] if leccion else None)
                yt = res.get("youtube") or {}
            except Exception as e:  # noqa: BLE001
                yt = {"ok": False, "error": str(e)}
            if yt.get("ok"):
                dato = {"url": yt.get("url", ""), "video_id": yt.get("video_id", ""),
                        "privacidad": privacidad, "fecha": cs.ahora(), "canal": canal_id,
                        "titulo": titulo}
                _apuntar(curso_id, clave, dato)
                subidas.append({"id": clave, **dato})
                log(f"   ✓ {yt.get('url', '')}")
            else:
                fallos.append({"id": clave, "titulo": titulo, "error": yt.get("error", "desconocido")})
                log(f"   ✗ {yt.get('error', 'desconocido')}")
    for s in saltadas:
        log(f"Saltada: {s['titulo']} ({s['motivo']})")
    return {"subidas": subidas, "fallos": fallos, "saltadas": saltadas}
