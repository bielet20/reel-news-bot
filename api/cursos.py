"""
api/cursos.py
Zona «Cursos y formaciones»: documentación → temario → lecciones (escenas de
diapositiva + narración) → editor → render de vídeo.

Las tareas largas (temario, generar lecciones, importar PowerPoint, render)
van a una cola con UN solo hilo: una cosa a la vez, para no competir por el
LM Studio del Mac ni por la CPU del render. El progreso se lee por polling en
GET /api/cursos/tareas/{id}.
"""

import json
import queue
import shutil
import sys
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import course_store as cs  # noqa: E402

router = APIRouter(prefix="/api/cursos", tags=["cursos"])

EXTS_VIDEO = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
EXTS_IMAGEN = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# ─── Cola de tareas ──────────────────────────────────────────────────────────

_tareas: dict[str, dict] = {}
_tareas_lock = threading.RLock()
_cola: "queue.Queue[tuple[str, callable]]" = queue.Queue()


def _worker():
    while True:
        tid, fn = _cola.get()
        t = _tareas[tid]
        t["estado"] = "en_curso"

        def log(msg, _t=t):
            _t["log"].append(str(msg))
            del _t["log"][:-300]
        estado = "completada"
        try:
            t["resultado"] = fn(log)
        except Exception as e:  # noqa: BLE001
            estado = "error"
            t["error"] = str(e)
            log(f"ERROR: {e}")
            traceback.print_exc()
        finally:
            # cierre + al_terminar (que puede encolar la siguiente fase) bajo el
            # lock: el editor nunca ve un instante «sin tareas» entre una fase y otra
            with _tareas_lock:
                t["estado"] = estado
                t["fin"] = cs.ahora()
                if t.get("al_terminar"):
                    try:
                        t["al_terminar"](t)
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
            _cola.task_done()


threading.Thread(target=_worker, daemon=True, name="cursos-worker").start()


def _limpiar_estados_huerfanos():
    """La cola vive en memoria: si el backend se reinicia, las lecciones que
    estaban «en cola» o «generando» ya no las termina nadie."""
    def fn(curso):
        for m in curso["modulos"]:
            for l in m["lecciones"]:
                if l.get("estado") in ("en_cola", "generando"):
                    l["estado"] = "lista" if l.get("escenas") else "pendiente"
    for c in cs.listar():
        try:
            cs.modificar(c["id"], fn)
        except Exception:  # noqa: BLE001
            pass


_limpiar_estados_huerfanos()


def _encolar(curso_id: str, tipo: str, etiqueta: str, fn, objetivo: str = "", al_terminar=None) -> dict:
    tid = uuid.uuid4().hex[:10]
    tarea = {"id": tid, "curso_id": curso_id, "tipo": tipo, "etiqueta": etiqueta, "objetivo": objetivo,
             "estado": "en_cola", "log": [], "error": "", "resultado": None, "creada": cs.ahora(),
             "al_terminar": al_terminar}
    with _tareas_lock:
        _tareas[tid] = tarea
    _cola.put((tid, fn))
    return _publica(tarea)


def _lanzar_aparte(curso_id: str, tipo: str, etiqueta: str, fn) -> dict:
    """Como _encolar, pero en un hilo propio: subir a YouTube es red, no CPU ni
    LM Studio, y no debe parar la cola de render. Sale igual en las tareas."""
    tid = uuid.uuid4().hex[:10]
    tarea = {"id": tid, "curso_id": curso_id, "tipo": tipo, "etiqueta": etiqueta, "objetivo": "",
             "estado": "en_curso", "log": [], "error": "", "resultado": None, "creada": cs.ahora()}
    with _tareas_lock:
        _tareas[tid] = tarea

    def run():
        def log(msg):
            tarea["log"].append(str(msg))
            del tarea["log"][:-300]
        estado = "completada"
        try:
            tarea["resultado"] = fn(log)
        except Exception as e:  # noqa: BLE001
            estado = "error"
            tarea["error"] = str(e)
            log(f"ERROR: {e}")
            traceback.print_exc()
        with _tareas_lock:
            tarea["estado"] = estado
            tarea["fin"] = cs.ahora()

    threading.Thread(target=run, daemon=True, name=f"cursos-{tipo}").start()
    return _publica(tarea)


def _publica(t: dict) -> dict:
    return {k: v for k, v in t.items() if k not in ("al_terminar", "resultado")}


def _cargar(curso_id: str) -> dict:
    try:
        return cs.cargar(curso_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Curso no encontrado")


# ─── Cursos ──────────────────────────────────────────────────────────────────

class NuevoCurso(BaseModel):
    titulo: str
    descripcion: str = ""
    publico: str = ""


class AjustesCurso(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    publico: str | None = None
    tema: dict | None = None
    voz: dict | None = None
    musica: str | None = None
    volumen_musica: float | None = None
    subtitulos: bool | None = None
    duracion_leccion_min: float | None = None


@router.get("")
def listar_cursos():
    return cs.listar()


@router.post("")
def crear_curso(req: NuevoCurso):
    return cs.crear_curso(req.titulo, req.descripcion, req.publico)


@router.get("/tareas/{tarea_id}")
def ver_tarea(tarea_id: str):
    t = _tareas.get(tarea_id)
    if not t:
        raise HTTPException(404, "Tarea no encontrada")
    return _publica(t)



class NuevoCanal(BaseModel):
    channel_id: str
    handle: str
    nombre: str


class UrlPublicada(BaseModel):
    url: str


@router.get("/canales")
def listar_canales_yt():
    import course_canales as cc
    return cc.listar_canales()


@router.post("/canales")
def crear_canal_yt(req: NuevoCanal):
    import course_canales as cc
    try:
        return cc.agregar_canal(req.channel_id, req.handle, req.nombre)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{curso_id}/canales")
def canales_de_curso(curso_id: str):
    _cargar(curso_id)
    import course_canales as cc
    canales = {c["channel_id"]: c for c in cc.listar_canales()}
    return [{**v, "canal": canales.get(v["channel_id"])} for v in cc.listar_vinculos(curso_id=curso_id)]


@router.put("/{curso_id}/canales/{channel_id}")
def vincular_canal(curso_id: str, channel_id: str):
    import course_canales as cc
    try:
        return cc.vincular(curso_id, channel_id)
    except FileNotFoundError:
        raise HTTPException(404, "Curso no encontrado")
    except KeyError:
        raise HTTPException(404, "Canal no registrado")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{curso_id}/canales/{channel_id}")
def desvincular_canal(curso_id: str, channel_id: str):
    _cargar(curso_id)
    import course_canales as cc
    try:
        cc.desvincular(curso_id, channel_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.put("/{curso_id}/canales/{channel_id}/url")
def fijar_url_canal(curso_id: str, channel_id: str, req: UrlPublicada):
    """Solo guarda el enlace cuando ya existe. No sube el video."""
    import course_canales as cc
    try:
        return cc.guardar_url_publicada(curso_id, channel_id, req.url)
    except KeyError:
        raise HTTPException(404, "Vinculo no encontrado")
    except ValueError as e:
        raise HTTPException(400, str(e))


class PublicarCurso(BaseModel):
    lecciones: list[str] = []
    completo: bool = False
    privacidad: str = "public"   # public | unlisted (oculto) | private
    resubir: bool = False


@router.get("/{curso_id}/publicacion")
def estado_publicacion(curso_id: str):
    """Lecciones renderizadas y lo ya subido a YouTube, para elegir qué subir."""
    _cargar(curso_id)
    import course_publicar as cp
    return cp.estado(curso_id)


@router.post("/{curso_id}/publicar")
def publicar_curso(curso_id: str, req: PublicarCurso):
    """Sube a YouTube (canal de cursos) las lecciones elegidas y/o el curso entero."""
    _cargar(curso_id)
    import course_publicar as cp
    if req.privacidad not in cp.PRIVACIDADES:
        raise HTTPException(400, "Privacidad no válida (public, unlisted o private).")
    if not req.lecciones and not req.completo:
        raise HTTPException(400, "Elige al menos una lección o el curso completo.")
    with _tareas_lock:
        if any(t["curso_id"] == curso_id and t["tipo"] == "publicar" and t["estado"] == "en_curso"
               for t in _tareas.values()):
            raise HTTPException(409, "Ya hay una subida de este curso en marcha.")
    n = len(req.lecciones) + (1 if req.completo else 0)
    etiqueta = f"Subir a YouTube ({n} vídeo{'s' if n != 1 else ''}, {cp.NOMBRE_PRIVACIDAD[req.privacidad]})"

    def fn(log):
        r = cp.publicar(curso_id, req.lecciones, completo=req.completo, privacidad=req.privacidad,
                        resubir=req.resubir, log=log)
        if r["fallos"] and not r["subidas"]:
            raise RuntimeError("No se subió ningún vídeo: " + r["fallos"][0]["error"])
        if r["fallos"]:
            log(f"Subidos {len(r['subidas'])}; fallaron {len(r['fallos'])} (puedes reintentarlos)")
        return r
    return _lanzar_aparte(curso_id, "publicar", etiqueta, fn)


@router.get("/{curso_id}")
def ver_curso(curso_id: str):
    return _cargar(curso_id)


@router.put("/{curso_id}")
def ajustar_curso(curso_id: str, req: AjustesCurso):
    _cargar(curso_id)
    cambios = {k: v for k, v in req.model_dump().items() if v is not None}
    if "musica" in cambios and cambios["musica"] == "":
        cambios["musica"] = None
    if "duracion_leccion_min" in cambios:
        cambios["duracion_leccion_min"] = max(1.0, min(30.0, cambios["duracion_leccion_min"]))
    cs.modificar(curso_id, lambda c: c.update(cambios))
    return cs.cargar(curso_id)


@router.delete("/{curso_id}")
def borrar_curso(curso_id: str):
    _cargar(curso_id)
    cs.borrar(curso_id)
    return {"ok": True}


@router.get("/{curso_id}/tareas")
def tareas_curso(curso_id: str):
    """Tareas activas del curso + las que fallaron en los últimos 10 minutos
    (para que un error de render o de IA no pase desapercibido)."""
    from datetime import datetime, timedelta
    limite = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    with _tareas_lock:
            return [_publica(t) for t in _tareas.values()
                if t["curso_id"] == curso_id and (t["estado"] in ("en_cola", "en_curso")
                                                  or (t["estado"] == "error" and t.get("fin", "") >= limite))]


# ─── Documentación ───────────────────────────────────────────────────────────

def _guardar_doc(curso_id: str, info: dict, nombre: str) -> dict:
    """Guarda el texto extraído (docs/<id>.json) y lo registra en el curso."""
    base = cs.dir_curso(curso_id)
    doc_id = cs.nuevo_id()
    rel = lambda r: str(Path(r).relative_to(base)).replace("\\", "/")  # noqa: E731
    info["imagenes"] = [rel(r) for r in info.get("imagenes", [])]
    for d in info.get("diapositivas") or []:
        d["imagenes"] = [rel(r) for r in d.get("imagenes", [])]
    info["id"] = doc_id
    (cs.subdir(curso_id, "docs") / f"{doc_id}.json").write_text(
        json.dumps(info, ensure_ascii=False), encoding="utf-8")
    ficha = {"id": doc_id, "nombre": nombre, "tipo": info["tipo"], "titulo": info["titulo"],
             "palabras": len(info.get("texto", "").split()), "n_imagenes": len(info["imagenes"]),
             "n_diapositivas": len(info.get("diapositivas") or []), "url": info.get("url", "")}
    cs.modificar(curso_id, lambda c: c["documentos"].append(ficha))
    return ficha


@router.post("/{curso_id}/documentos")
async def subir_documentos(curso_id: str, archivos: list[UploadFile] = File(...), auto: bool = Form(True)):
    """Sube documentos. Con auto=True (por defecto) y un curso aún sin temario,
    lanza el curso completo solo: temario → lecciones (con imágenes) → vídeos."""
    from course_ingest import leer_documento, EXTS_SOPORTADAS
    _cargar(curso_id)
    originales = cs.subdir(curso_id, "docs/originales")
    fichas, errores = [], []
    for up in archivos:
        nombre = Path(up.filename or "documento").name
        ext = Path(nombre).suffix.lower()
        if ext not in EXTS_SOPORTADAS:
            errores.append(f"{nombre}: formato no soportado")
            continue
        ruta = originales / f"{cs.nuevo_id()}{ext}"
        ruta.write_bytes(await up.read())
        try:
            info = await run_in_threadpool(leer_documento, str(ruta), cs.subdir(curso_id, "assets"))
            if not info.get("titulo") or info["titulo"] == ruta.stem:
                info["titulo"] = Path(nombre).stem  # sin título en los metadatos: el nombre original
            if len(info.get("texto", "").split()) < 5 and not info.get("imagenes"):
                errores.append(f"{nombre}: no se encontró texto (¿PDF escaneado?)")
                continue
            ficha = _guardar_doc(curso_id, info, nombre)
            ficha["archivo"] = str(ruta.relative_to(cs.dir_curso(curso_id))).replace("\\", "/")
            fichas.append(ficha)
        except Exception as e:  # noqa: BLE001
            errores.append(f"{nombre}: {e}")
    tarea = None
    if auto and fichas and not cs.cargar(curso_id)["modulos"]:
        tarea = _encolar_automatico(curso_id)
    return {"documentos": fichas, "errores": errores, "tarea": tarea}


class UrlDoc(BaseModel):
    url: str
    auto: bool = True


@router.post("/{curso_id}/documentos/url")
async def subir_url(curso_id: str, req: UrlDoc):
    from course_ingest import leer_url
    _cargar(curso_id)
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL no válida")
    try:
        info = await run_in_threadpool(leer_url, req.url)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, str(e))
    ficha = _guardar_doc(curso_id, info, req.url)
    if req.auto and not cs.cargar(curso_id)["modulos"]:
        ficha["tarea"] = _encolar_automatico(curso_id)
    return ficha


@router.delete("/{curso_id}/documentos/{doc_id}")
def borrar_documento(curso_id: str, doc_id: str):
    _cargar(curso_id)
    (cs.subdir(curso_id, "docs") / f"{doc_id}.json").unlink(missing_ok=True)
    cs.modificar(curso_id, lambda c: c.update(documentos=[d for d in c["documentos"] if d["id"] != doc_id]))
    return {"ok": True}


@router.post("/{curso_id}/documentos/{doc_id}/importar")
def importar_presentacion(curso_id: str, doc_id: str):
    """Un .pptx subido → módulo con sus diapositivas tal cual (notas = narración)."""
    from course_builder import importar_pptx
    _cargar(curso_id)
    ruta = cs.subdir(curso_id, "docs") / f"{doc_id}.json"
    if not ruta.exists():
        raise HTTPException(404, "Documento no encontrado")
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    if doc.get("tipo") != "pptx":
        raise HTTPException(400, "Solo se pueden importar presentaciones PowerPoint")
    return _encolar(curso_id, "importar", f"Importar «{doc['titulo']}»",
                    lambda log: bool(importar_pptx(curso_id, doc, log=log)))


# ─── Generación con IA ───────────────────────────────────────────────────────

class PeticionTemario(BaseModel):
    n_modulos: int = 0


@router.post("/{curso_id}/temario")
def generar_temario(curso_id: str, req: PeticionTemario):
    from course_builder import proponer_temario
    _cargar(curso_id)
    return _encolar(curso_id, "temario", "Proponer temario",
                    lambda log: bool(proponer_temario(curso_id, req.n_modulos, log=log)))


def _marcar_leccion(curso_id: str, leccion_id: str, estado: str, error: str = ""):
    def fn(c):
        _, l = cs.buscar_leccion(c, leccion_id)
        l["estado"] = estado
        l["error"] = error
    try:
        cs.modificar(curso_id, fn)
    except KeyError:
        pass


def _encolar_leccion(curso_id: str, leccion: dict, renderizar: bool = False) -> dict:
    from course_builder import generar_leccion
    _marcar_leccion(curso_id, leccion["id"], "en_cola")

    def trabajo(log, lid=leccion["id"]):
        _marcar_leccion(curso_id, lid, "generando")
        generar_leccion(curso_id, lid, log=log)
        if renderizar:  # modo automático: el vídeo de la lección sale en cuanto está escrita
            from course_render import render_leccion
            log("-> Lección escrita; renderizando su vídeo...")
            render_leccion(curso_id, lid, log=log)
        return True

    def al_terminar(t, lid=leccion["id"]):
        if t["estado"] == "error":
            _marcar_leccion(curso_id, lid, "error", t["error"])
    etiqueta = f"{'Generar y renderizar' if renderizar else 'Generar'} «{leccion['titulo']}»"
    return _encolar(curso_id, "leccion", etiqueta, trabajo, objetivo=leccion["id"], al_terminar=al_terminar)


def _encolar_automatico(curso_id: str, n_modulos: int = 0) -> dict:
    """Curso completo sin tocar nada: temario (si no hay) → cada lección
    pendiente se escribe con la IA (imágenes de la documentación o generadas)
    y se renderiza → al final se unen en un solo vídeo con capítulos.
    Todo va encadenado en la cola, así el editor ve avanzar cada paso."""
    from course_builder import proponer_temario

    def seguir(t=None):
        if t is not None and t["estado"] == "error":
            return  # el temario falló: el aviso rojo del editor lo muestra
        curso = cs.cargar(curso_id)
        for m in curso["modulos"]:
            for l in m["lecciones"]:
                if l.get("estado") in ("en_cola", "generando"):
                    continue
                if not l.get("escenas"):
                    _encolar_leccion(curso_id, l, renderizar=True)
        from course_render import render_curso
        _encolar(curso_id, "render_curso", "Montar el curso completo",
                 lambda log: render_curso(curso_id, log=log))

    if cs.cargar(curso_id)["modulos"]:
        seguir()
        return {"ok": True}
    return _encolar(curso_id, "temario", "Proponer temario (automático)",
                    lambda log: bool(proponer_temario(curso_id, n_modulos, log=log)), al_terminar=seguir)


@router.post("/{curso_id}/automatico")
def generar_automatico(curso_id: str, req: PeticionTemario | None = None):
    """Botón «Generar todo»: lo que falte del curso, hasta el vídeo final."""
    _cargar(curso_id)
    return _encolar_automatico(curso_id, req.n_modulos if req else 0)


@router.post("/{curso_id}/lecciones/{leccion_id}/generar")
def generar_una_leccion(curso_id: str, leccion_id: str):
    curso = _cargar(curso_id)
    try:
        _, l = cs.buscar_leccion(curso, leccion_id)
    except KeyError:
        raise HTTPException(404, "Lección no encontrada")
    return _encolar_leccion(curso_id, l)


@router.post("/{curso_id}/generar-pendientes")
def generar_pendientes(curso_id: str):
    curso = _cargar(curso_id)
    pendientes = [l for m in curso["modulos"] for l in m["lecciones"]
                  if not l.get("escenas") and l.get("estado") not in ("en_cola", "generando")]
    return [_encolar_leccion(curso_id, l) for l in pendientes]


# ─── Edición ─────────────────────────────────────────────────────────────────

class Estructura(BaseModel):
    modulos: list
    rev_modulos: int | None = None


@router.put("/{curso_id}/estructura")
def guardar_estructura(curso_id: str, req: Estructura):
    """Guarda módulos/lecciones/escenas tal como los deja el editor. Los campos
    que solo escribe el servidor (audio, render, estado) se conservan del
    servidor por id, para no pisar lo que haya hecho una tarea mientras tanto."""
    def aplicar(c):
        lec_srv = {l["id"]: l for m in c["modulos"] for l in m["lecciones"]}
        esc_srv = {e["id"]: e for l in lec_srv.values() for e in l.get("escenas", [])}
        for m in req.modulos:
            m.setdefault("id", cs.nuevo_id())
            for l in m.setdefault("lecciones", []):
                l.setdefault("id", cs.nuevo_id())
                srv = lec_srv.get(l["id"], {})
                # el editor tenía la lección vacía pero una tarea ya la ha generado:
                # manda el servidor (si no, el autoguardado borraría la lección)
                # (si el editor la tenía "lista" y vacía, es que el usuario borró las escenas)
                if not l.get("escenas") and srv.get("escenas") and l.get("estado") != "lista":
                    l["escenas"] = srv["escenas"]
                for campo in ("render", "estado", "error"):
                    if campo in srv:
                        l[campo] = srv[campo]
                l.setdefault("estado", "lista" if l.get("escenas") else "pendiente")
                for e in l.setdefault("escenas", []):
                    e.setdefault("id", cs.nuevo_id())
                    previa = esc_srv.get(e["id"])
                    # el audio solo vale si la narración no ha cambiado
                    e["audio"] = previa.get("audio") if previa and previa.get("narracion") == e.get("narracion") else None
        c["modulos"] = req.modulos
    actual = _cargar(curso_id)
    # el servidor rehízo el temario (IA / importar) después de que el editor lo
    # cargara: lo que manda el editor es viejo y borraría el temario nuevo
    if req.rev_modulos is not None and req.rev_modulos < actual.get("rev_modulos", 0):
        raise HTTPException(409, "El temario ha cambiado en el servidor; recarga el curso")
    cs.modificar(curso_id, aplicar)
    return cs.cargar(curso_id)


@router.post("/{curso_id}/escenas/{escena_id}/narrar")
async def narrar(curso_id: str, escena_id: str, forzar: bool = False):
    from course_render import narrar_escena
    _cargar(curso_id)
    try:
        audio = await run_in_threadpool(narrar_escena, curso_id, escena_id, forzar)
    except KeyError:
        raise HTTPException(404, "Escena no encontrada")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"No se pudo generar la voz: {e}")
    return {"audio": audio}


@router.post("/{curso_id}/narrar-leccion/{leccion_id}")
def narrar_leccion(curso_id: str, leccion_id: str):
    """Voz de todas las escenas de la lección (para la vista previa)."""
    from course_render import narrar_escena
    curso = _cargar(curso_id)
    _, l = cs.buscar_leccion(curso, leccion_id)
    ids = [e["id"] for e in l.get("escenas", [])]

    def trabajo(log):
        for i, eid in enumerate(ids, 1):
            narrar_escena(curso_id, eid, log=log)
            log(f"   voz {i}/{len(ids)}")
        return True
    return _encolar(curso_id, "voz", f"Voz de «{l['titulo']}»", trabajo, objetivo=leccion_id)


@router.post("/{curso_id}/assets")
async def subir_asset(curso_id: str, archivo: UploadFile = File(...)):
    """Imagen para una diapositiva o grabación de pantalla para la línea de tiempo."""
    _cargar(curso_id)
    ext = Path(archivo.filename or "").suffix.lower()
    if ext in EXTS_IMAGEN:
        carpeta = cs.subdir(curso_id, "assets")
    elif ext in EXTS_VIDEO:
        carpeta = cs.subdir(curso_id, "assets/videos")
    else:
        raise HTTPException(400, "Sube una imagen (png/jpg/webp) o un vídeo (mp4/mov/webm)")
    ruta = carpeta / f"{cs.nuevo_id()}{ext}"
    with open(ruta, "wb") as f:
        shutil.copyfileobj(archivo.file, f)
    rel = str(ruta.relative_to(cs.dir_curso(curso_id))).replace("\\", "/")
    salida = {"ruta": rel, "tipo": "video" if ext in EXTS_VIDEO else "imagen"}
    if ext in EXTS_VIDEO:
        from course_render import _duracion
        salida["duracion"] = round(await run_in_threadpool(_duracion, str(ruta)), 2)
    return salida


class PeticionImagenIA(BaseModel):
    prompt: str


@router.post("/{curso_id}/imagen-ia")
async def imagen_ia(curso_id: str, req: PeticionImagenIA):
    from image_pipeline import generar_imagen_ai
    _cargar(curso_id)
    ruta = cs.subdir(curso_id, "assets") / f"ia_{cs.nuevo_id()}.jpg"
    hecho = await run_in_threadpool(
        generar_imagen_ai, f"{req.prompt}, clean educational illustration, 16:9", str(ruta))
    if not hecho:
        raise HTTPException(502, "No se pudo generar la imagen")
    return {"ruta": str(Path(hecho).relative_to(cs.dir_curso(curso_id))).replace("\\", "/")}


# ─── Render ──────────────────────────────────────────────────────────────────

@router.post("/{curso_id}/lecciones/{leccion_id}/render")
def renderizar_leccion(curso_id: str, leccion_id: str):
    from course_render import render_leccion
    curso = _cargar(curso_id)
    _, l = cs.buscar_leccion(curso, leccion_id)
    return _encolar(curso_id, "render", f"Renderizar «{l['titulo']}»",
                    lambda log: render_leccion(curso_id, leccion_id, log=log), objetivo=leccion_id)


@router.post("/{curso_id}/render")
def renderizar_curso(curso_id: str):
    from course_render import render_curso
    _cargar(curso_id)
    return _encolar(curso_id, "render_curso", "Renderizar el curso completo",
                    lambda log: render_curso(curso_id, log=log))


# ─── Archivos ────────────────────────────────────────────────────────────────

@router.get("/{curso_id}/archivo/{ruta:path}")
def servir_archivo(curso_id: str, ruta: str):
    base = cs.dir_curso(curso_id).resolve()
    destino = (base / ruta).resolve()
    if base not in destino.parents or not destino.is_file():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(str(destino))
