"""
course_store.py
Almacenamiento de la zona «Cursos»: un directorio por curso en _cursos/<id>/
con curso.json (estructura completa), docs/, assets/, audio/ y render/.

Estructura de curso.json
------------------------
curso:    id, titulo, descripcion, publico, tema{fondo,texto,acento,fuente},
          voz{servicio,voz}, musica, volumen_musica, subtitulos, documentos[],
          modulos[]
modulo:   id, titulo, lecciones[]
leccion:  id, titulo, objetivos[], resumen, estado, error, escenas[], render{}
escena:   id, tipo ("diapositiva" | "video"), layout, contenido{...}, narracion,
          notas, duracion (None = la marca el audio), transicion, fuente,
          audio{archivo,hash,duracion}, video{archivo,inicio,fin}
"""

import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

CURSOS_DIR = Path(__file__).parent / "_cursos"
CURSOS_DIR.mkdir(exist_ok=True)

LAYOUTS = ["portada", "vinetas", "imagen_texto", "imagen_completa", "codigo",
           "cita", "comparacion", "pasos", "resumen", "cuestionario"]

TEMA_DEFECTO = {"fondo": "#0f172a", "texto": "#f8fafc", "acento": "#8b5cf6", "fuente": "Inter"}
VOZ_DEFECTO = {"servicio": "edge-tts", "voz": "es-ES-AlvaroNeural"}

_lock = threading.RLock()


def nuevo_id() -> str:
    return uuid.uuid4().hex[:10]


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dir_curso(curso_id: str) -> Path:
    if not curso_id or "/" in curso_id or "\\" in curso_id or ".." in curso_id:
        raise ValueError("id de curso no válido")
    return CURSOS_DIR / curso_id


def subdir(curso_id: str, nombre: str) -> Path:
    d = dir_curso(curso_id) / nombre
    d.mkdir(parents=True, exist_ok=True)
    return d


def escena_vacia(layout: str = "vinetas", **contenido) -> dict:
    return {
        "id": nuevo_id(), "tipo": "diapositiva", "layout": layout,
        "contenido": {"titulo": "", **contenido}, "narracion": "", "notas": "",
        "duracion": None, "transicion": "fundido", "fuente": "",
        "audio": None, "video": None,
    }


def crear_curso(titulo: str, descripcion: str = "", publico: str = "") -> dict:
    curso = {
        "id": nuevo_id(), "titulo": titulo.strip() or "Curso sin título",
        "descripcion": descripcion, "publico": publico,
        "creado": ahora(), "actualizado": ahora(),
        "tema": dict(TEMA_DEFECTO), "voz": dict(VOZ_DEFECTO),
        "musica": None, "volumen_musica": 0.12, "subtitulos": True,
        "duracion_leccion_min": 5,
        "documentos": [], "modulos": [],
    }
    guardar(curso)
    return curso


def cargar(curso_id: str) -> dict:
    ruta = dir_curso(curso_id) / "curso.json"
    if not ruta.exists():
        raise FileNotFoundError(curso_id)
    with _lock:
        return json.loads(ruta.read_text(encoding="utf-8"))


def guardar(curso: dict) -> None:
    d = dir_curso(curso["id"])
    d.mkdir(parents=True, exist_ok=True)
    curso["actualizado"] = ahora()
    tmp = d / "curso.json.tmp"
    with _lock:
        tmp.write_text(json.dumps(curso, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(d / "curso.json")


def modificar(curso_id: str, fn):
    """Carga, aplica fn(curso) y guarda de forma atómica respecto a otros hilos."""
    with _lock:
        curso = cargar(curso_id)
        resultado = fn(curso)
        guardar(curso)
        return resultado


def listar() -> list[dict]:
    salida = []
    for ruta in CURSOS_DIR.glob("*/curso.json"):
        try:
            c = json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            continue
        lecciones = [l for m in c.get("modulos", []) for l in m.get("lecciones", [])]
        salida.append({
            "id": c["id"], "titulo": c["titulo"], "descripcion": c.get("descripcion", ""),
            "actualizado": c.get("actualizado", ""), "n_modulos": len(c.get("modulos", [])),
            "n_lecciones": len(lecciones),
            "n_renderizadas": sum(1 for l in lecciones if (l.get("render") or {}).get("archivo")),
            "n_documentos": len(c.get("documentos", [])),
        })
    return sorted(salida, key=lambda x: x["actualizado"], reverse=True)


def borrar(curso_id: str) -> None:
    d = dir_curso(curso_id)
    if d.exists():
        shutil.rmtree(d)
    try:
        import course_canales
        course_canales.quitar_vinculos_curso(curso_id)
    except Exception:
        pass


def buscar_leccion(curso: dict, leccion_id: str) -> tuple[dict, dict]:
    for m in curso.get("modulos", []):
        for l in m.get("lecciones", []):
            if l["id"] == leccion_id:
                return m, l
    raise KeyError(f"lección {leccion_id} no encontrada")


def buscar_escena(curso: dict, escena_id: str) -> tuple[dict, dict]:
    for m in curso.get("modulos", []):
        for l in m.get("lecciones", []):
            for e in l.get("escenas", []):
                if e["id"] == escena_id:
                    return l, e
    raise KeyError(f"escena {escena_id} no encontrada")


def texto_documentos(curso_id: str) -> list[dict]:
    """Documentos ya leídos (docs/<id>.json) con su texto y secciones."""
    salida = []
    for ruta in sorted(subdir(curso_id, "docs").glob("*.json")):
        try:
            salida.append(json.loads(ruta.read_text(encoding="utf-8")))
        except Exception:
            continue
    return salida
