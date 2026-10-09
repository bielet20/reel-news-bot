"""
course_builder.py
Genera el contenido de un curso a partir de su documentación:
  1. proponer_temario()  → módulos + lecciones + objetivos (JSON)
  2. generar_leccion()   → escenas (diapositiva con layout + narración)
  3. importar_pptx()     → un PowerPoint existente se convierte en escenas tal
                           cual (título, viñetas, imagen, notas → narración)

La IA es el LM Studio local (llm_local.completar) con la misma cadena de
respaldo que el guion largo (summarizer._completar_largo: Claude / Gemini /
Groq solo con IA_NUBE=1). Regla: usar SOLO lo que dice la documentación.
"""

import json
import re
from pathlib import Path

import course_store as cs

PALABRAS_POR_SEG = 2.3  # ritmo real de la voz (ver summarizer.PALABRAS_POR_SEG)
_MAX_CHARS_CONTEXTO = 14000


def _llm(prompt: str, max_tokens: int = 4000) -> str:
    from llm_local import asegurar_llm, LLMNoDisponible, nube_permitida
    try:
        asegurar_llm()
    except LLMNoDisponible:
        if not nube_permitida():
            raise
    from summarizer import _completar_largo
    return _completar_largo(prompt, max_tokens=max_tokens)


def _extraer_json(texto: str):
    """Saca el primer objeto JSON de la respuesta (el modelo a veces añade
    ```json ... ``` o una frase antes)."""
    texto = re.sub(r"```(?:json)?", "", texto)
    ini = texto.find("{")
    fin = texto.rfind("}")
    if ini < 0 or fin <= ini:
        raise ValueError("la IA no devolvió JSON")
    bloque = texto[ini:fin + 1]
    try:
        return json.loads(bloque)
    except json.JSONDecodeError:
        # comas finales y comillas tipográficas, los fallos más comunes
        limpio = re.sub(r",\s*([}\]])", r"\1", bloque).replace("“", '"').replace("”", '"')
        return json.loads(limpio)


def _llm_json(prompt: str, max_tokens: int = 4000) -> dict:
    ultimo = None
    for intento in range(2):
        texto = _llm(prompt if intento == 0 else
                     prompt + "\n\nIMPORTANTE: tu respuesta anterior no era JSON válido. "
                              "Devuelve SOLO el objeto JSON, sin texto alrededor.",
                     max_tokens=max_tokens)
        try:
            return _extraer_json(texto)
        except (ValueError, json.JSONDecodeError) as e:
            ultimo = e
    raise RuntimeError(f"La IA no devolvió un JSON válido: {ultimo}")


# ─── Contexto de la documentación ────────────────────────────────────────────

def _secciones(curso_id: str) -> list[dict]:
    out = []
    for doc in cs.texto_documentos(curso_id):
        for s in doc.get("secciones") or [{"titulo": doc.get("titulo", ""), "texto": doc.get("texto", "")}]:
            if s.get("texto", "").strip():
                out.append({"doc": doc.get("titulo", ""), "titulo": s.get("titulo", ""), "texto": s["texto"]})
    return out


def _indice_documentacion(curso_id: str) -> str:
    """Vista general para el temario: títulos de sección + el comienzo de cada una."""
    secciones = _secciones(curso_id)
    if not secciones:
        raise ValueError("El curso no tiene documentación. Sube al menos un documento o una URL.")
    presupuesto = max(300, _MAX_CHARS_CONTEXTO // max(1, len(secciones)))
    partes = []
    for s in secciones:
        cab = f"[{s['doc']}] {s['titulo']}".strip()
        partes.append(f"## {cab}\n{s['texto'][:presupuesto].strip()}")
    return "\n\n".join(partes)[:_MAX_CHARS_CONTEXTO]


_STOP = set("de la el los las un una y o en con para por del al que se es su sus como más lo "
            "a ante sobre tras entre este esta estos estas".split())


def _palabras(t: str) -> set:
    return {w for w in re.findall(r"[a-záéíóúüñ0-9]{3,}", t.lower()) if w not in _STOP}


def _contexto_leccion(curso_id: str, leccion: dict) -> str:
    """Las secciones de la documentación más relacionadas con la lección."""
    clave = _palabras(" ".join([leccion["titulo"], leccion.get("resumen", ""), *leccion.get("objetivos", [])]))
    secciones = _secciones(curso_id)
    puntuadas = sorted(secciones, key=lambda s: len(clave & _palabras(s["titulo"] * 3 + " " + s["texto"])),
                       reverse=True)
    partes, total = [], 0
    for s in puntuadas:
        bloque = f"## [{s['doc']}] {s['titulo']}\n{s['texto'].strip()}"
        if total + len(bloque) > _MAX_CHARS_CONTEXTO:
            bloque = bloque[:max(0, _MAX_CHARS_CONTEXTO - total)]
        if not bloque:
            break
        partes.append(bloque)
        total += len(bloque)
        if total >= _MAX_CHARS_CONTEXTO:
            break
    return "\n\n".join(partes)


# ─── 1. Temario ──────────────────────────────────────────────────────────────

def proponer_temario(curso_id: str, n_modulos: int = 0, log=print) -> dict:
    curso = cs.cargar(curso_id)
    indice = _indice_documentacion(curso_id)
    objetivo_mod = f"{n_modulos} módulos" if n_modulos else "entre 2 y 6 módulos según la extensión"
    prompt = (
        "Eres diseñador instruccional. Con la DOCUMENTACIÓN de abajo diseña el temario de un curso en vídeo "
        "en español.\n\n"
        f"Curso: {curso['titulo']}\n"
        f"Descripción: {curso.get('descripcion') or '(sin descripción)'}\n"
        f"Público: {curso.get('publico') or 'general'}\n\n"
        f"DOCUMENTACIÓN:\n{indice}\n\n"
        f"Crea {objetivo_mod}, cada uno con 2-6 lecciones de unos {curso.get('duracion_leccion_min', 5)} minutos. "
        "Orden pedagógico: de lo básico a lo avanzado. Cada lección = una idea enseñable.\n"
        "Usa SOLO lo que cubre la documentación; no añadas temas que no estén.\n\n"
        "Devuelve SOLO este JSON:\n"
        '{"titulo": "título del curso", "descripcion": "1-2 frases", "modulos": [\n'
        '  {"titulo": "...", "lecciones": [\n'
        '    {"titulo": "...", "resumen": "1 frase", "objetivos": ["El alumno sabrá...", "..."]}\n'
        "  ]}\n]}"
    )
    log("   -> Pidiendo el temario a la IA...")
    datos = _llm_json(prompt, max_tokens=3500)
    modulos = []
    for m in datos.get("modulos") or []:
        lecciones = [{
            "id": cs.nuevo_id(),
            "titulo": (str(l.get("titulo") or l.get("nombre") or "").strip()
                       or str(l.get("resumen") or "").strip()[:70]
                       or re.sub(r"^El alumno (sabrá|entenderá|aprenderá)\s*", "",
                                 str((l.get("objetivos") or ["Lección"])[0])).strip().rstrip(".").capitalize()),
            "resumen": str(l.get("resumen", "")).strip(),
            "objetivos": [str(o).strip() for o in (l.get("objetivos") or []) if str(o).strip()],
            "estado": "pendiente", "error": "", "escenas": [], "render": None,
        } for l in (m.get("lecciones") or []) if isinstance(l, dict)]
        if lecciones:
            modulos.append({"id": cs.nuevo_id(), "titulo": str(m.get("titulo", "")).strip() or "Módulo",
                            "lecciones": lecciones})
    if not modulos:
        raise RuntimeError("La IA no propuso ningún módulo")

    def aplicar(c):
        c["modulos"] = modulos
        c["rev_modulos"] = c.get("rev_modulos", 0) + 1  # invalida lo que tenga abierto el editor
        if datos.get("descripcion") and not c.get("descripcion"):
            c["descripcion"] = str(datos["descripcion"]).strip()
    cs.modificar(curso_id, aplicar)
    return cs.cargar(curso_id)


# ─── 2. Lección ──────────────────────────────────────────────────────────────

_GUIA_LAYOUTS = """Layouts disponibles y campos de "contenido" de cada uno:
- "portada": {"titulo", "subtitulo"}  → primera escena de la lección
- "vinetas": {"titulo", "vinetas": [3-5 frases cortas]}
- "imagen_texto": {"titulo", "vinetas": [2-4], "imagen_prompt": "visual description IN ENGLISH, no text"}
- "imagen_completa": {"titulo", "imagen_prompt": "visual description IN ENGLISH, no text"}
- "codigo": {"titulo", "lenguaje", "codigo": "código corto, máx 15 líneas"}  → solo si la documentación tiene código/comandos
- "cita": {"cita", "autor"}
- "comparacion": {"titulo", "columnas": [{"titulo", "vinetas": [...]}, {"titulo", "vinetas": [...]}]}
- "pasos": {"titulo", "pasos": ["Paso 1...", "Paso 2...", ...]}  → procedimientos e instrucciones
- "resumen": {"titulo", "vinetas": [3-5 ideas clave]}  → última o penúltima escena
- "cuestionario": {"pregunta", "opciones": ["A", "B", "C"], "correcta": 0}  → repaso final opcional"""


def _normalizar_escena(e: dict, imagenes_doc: list, usadas: set) -> dict:
    layout = e.get("layout") if e.get("layout") in cs.LAYOUTS else "vinetas"
    contenido = e.get("contenido") if isinstance(e.get("contenido"), dict) else {}
    esc = cs.escena_vacia(layout)
    esc["contenido"] = {k: v for k, v in contenido.items() if v not in (None, "", [])}
    esc["contenido"].setdefault("titulo", "")
    esc["narracion"] = str(e.get("narracion", "")).strip()
    esc["fuente"] = str(e.get("fuente", "")).strip()
    if layout in ("imagen_texto", "imagen_completa"):
        libre = next((i for i in imagenes_doc if i not in usadas), None)
        if libre:  # primero, imágenes reales de la documentación
            usadas.add(libre)
            esc["contenido"]["imagen"] = libre
    return esc


def generar_leccion(curso_id: str, leccion_id: str, log=print) -> dict:
    curso = cs.cargar(curso_id)
    modulo, leccion = cs.buscar_leccion(curso, leccion_id)
    minutos = float(curso.get("duracion_leccion_min", 5))
    palabras = int(minutos * 60 * PALABRAS_POR_SEG)
    n_escenas = max(4, min(16, round(minutos * 2)))
    contexto = _contexto_leccion(curso_id, leccion)
    objetivos = "\n".join(f"- {o}" for o in leccion.get("objetivos", [])) or "- (no indicados)"
    prompt = (
        "Eres guionista de cursos en vídeo (estilo tutorial claro y ameno, en español de España).\n\n"
        f"Curso: {curso['titulo']}  ·  Público: {curso.get('publico') or 'general'}\n"
        f"Módulo: {modulo['titulo']}\nLección: {leccion['titulo']}\n"
        f"Resumen: {leccion.get('resumen', '')}\nObjetivos:\n{objetivos}\n\n"
        f"DOCUMENTACIÓN (única fuente permitida):\n{contexto}\n\n"
        f"Escribe la lección como {n_escenas} escenas (diapositiva + narración), unas {palabras} palabras "
        f"de narración en total (~{minutos:g} min).\n\n{_GUIA_LAYOUTS}\n\n"
        "REGLAS:\n"
        "- Escena 1 = portada con el título de la lección; la narración presenta qué se va a aprender.\n"
        "  Sin saludos ('Buenos días', 'Hola a todos'): el vídeo se verá a cualquier hora y dentro de un curso.\n"
        "- La diapositiva resume (frases cortas, máx. 8 palabras por viñeta); la NARRACIÓN explica con detalle,\n"
        "  como un profesor: no leas la diapositiva literalmente.\n"
        "- Usa layouts variados. 'pasos' para instrucciones, 'codigo' solo si hay código en la documentación.\n"
        f"- Al menos {max(2, n_escenas // 3)} escenas deben ser 'imagen_texto' o 'imagen_completa' (la app genera\n"
        "  la imagen): 'imagen_prompt' en INGLÉS, describiendo una ilustración concreta, sin texto ni letras.\n"
        "- Última escena = 'resumen' con las ideas clave.\n"
        "- Usa SOLO información de la documentación. En 'fuente' indica la sección de donde sale cada escena.\n"
        "  Si falta información para un objetivo, dilo en la narración en vez de inventar.\n\n"
        "Devuelve SOLO este JSON:\n"
        '{"escenas": [{"layout": "portada", "contenido": {"titulo": "...", "subtitulo": "..."}, '
        '"narracion": "texto que dirá la voz", "fuente": "sección"}]}'
    )
    log(f"   -> Generando la lección «{leccion['titulo']}» ({n_escenas} escenas)...")
    datos = _llm_json(prompt, max_tokens=max(4000, int(palabras * 2.6) + 1500))
    crudas = [e for e in (datos.get("escenas") or []) if isinstance(e, dict)]
    if not crudas:
        raise RuntimeError("La IA no devolvió escenas para la lección")
    imagenes_doc = [i for d in cs.texto_documentos(curso_id) for i in d.get("imagenes", [])]
    usadas = {e.get("contenido", {}).get("imagen") for m in curso["modulos"] for l in m["lecciones"]
              for e in l.get("escenas", []) if l["id"] != leccion_id}
    escenas = [_normalizar_escena(e, imagenes_doc, usadas) for e in crudas]
    _asegurar_imagenes(escenas, curso["titulo"])
    _imagenes_ia(curso_id, escenas, log)

    def aplicar(c):
        _, l = cs.buscar_leccion(c, leccion_id)
        l["escenas"] = escenas
        l["estado"] = "lista"
        l["error"] = ""
        l["render"] = None
    cs.modificar(curso_id, aplicar)
    return cs.cargar(curso_id)


def _asegurar_imagenes(escenas: list, curso_titulo: str) -> None:
    """Si la IA se quedó corta de imágenes, pasa algunas escenas de viñetas
    cortas a imagen + texto (repartidas por la lección)."""
    minimo = max(2, len(escenas) // 4)
    con_img = [e for e in escenas if e["layout"] in ("imagen_texto", "imagen_completa")]
    candidatas = [e for e in escenas[1:-1] if e["layout"] == "vinetas"
                  and 1 <= len(e["contenido"].get("vinetas") or []) <= 4]
    faltan = minimo - len(con_img)
    if faltan <= 0 or not candidatas:
        return
    paso = max(1, len(candidatas) // faltan)
    for e in candidatas[::paso][:faltan]:
        e["layout"] = "imagen_texto"
        e["contenido"]["imagen_prompt"] = f"{e['contenido'].get('titulo', '')} (topic: {curso_titulo})".strip()


_ESTILO_IMG = ("clean modern educational illustration, flat vector style, soft gradients, "
               "dark navy background, purple accents, high detail, no text, no letters, no watermark")


def _comfy_ocupado() -> bool:
    """True si ComfyUI tiene trabajo (p. ej. un vídeo Wan de los reels)."""
    import requests
    import comfy_video_builder as cvb
    try:
        q = requests.get(f"{cvb.COMFY_URL}/queue", timeout=4).json()
        return bool(q.get("queue_running") or q.get("queue_pending"))
    except Exception:  # noqa: BLE001
        return False


def _flux_local(prompt: str, destino: Path, log=print, timeout: float = 900.0) -> Path | None:
    """FLUX en el ComfyUI del PC (GPU). 1344×768 ≈ 16:9. Si no termina a
    tiempo se quita de la cola para no gastar GPU en una imagen que ya nadie espera."""
    import random
    import requests
    import comfy_video_builder as cvb
    if not cvb.comfy_disponible():
        return None
    pid = None
    try:
        png = destino.with_suffix(".png")
        wf = cvb.build_flux_workflow(f"{prompt}. {_ESTILO_IMG}", random.randint(1, 2**31 - 1), 1344, 768)
        wf["8"]["inputs"]["filename_prefix"] = "curso_img"
        pid = cvb.comfy_queue(wf)
        out = cvb.comfy_wait(pid, timeout=timeout)
        info = cvb._first_output(out, "8")
        cvb.comfy_download(info["filename"], info.get("subfolder", ""), info["type"], png)
        from PIL import Image
        with Image.open(png) as im:
            im.convert("RGB").save(destino, quality=92)
        png.unlink(missing_ok=True)
        return destino
    except Exception as ex:  # noqa: BLE001
        log(f"   [WARN] FLUX local: {ex}")
        if pid:
            try:
                requests.post(f"{cvb.COMFY_URL}/queue", json={"delete": [pid]}, timeout=10)
            except requests.exceptions.RequestException:
                pass
        return None


def _pollinations_16x9(prompt: str, destino: Path, log=print) -> Path | None:
    """Respaldo en la nube (image_pipeline genera en vertical para reels; aquí 16:9)."""
    import random
    import urllib.parse
    import requests
    from PIL import Image
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(f"{prompt}, {_ESTILO_IMG}")
           + f"?width=1920&height=1080&seed={random.randint(1, 99999)}&nologo=true&model=flux")
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        destino.write_bytes(r.content)
        with Image.open(destino) as im:
            if im.width < 100:
                raise ValueError("imagen vacía")
        return destino
    except Exception as ex:  # noqa: BLE001
        log(f"   [WARN] Pollinations: {ex}")
        destino.unlink(missing_ok=True)
        return None


def generar_imagen_curso(prompt: str, destino: Path, log=print) -> Path | None:
    """Imagen 16:9 para una diapositiva. ComfyUI libre → FLUX local (GPU del PC);
    ocupado (los reels comparten la GPU) → Pollinations y, si falla, FLUX esperando turno."""
    if not _comfy_ocupado():
        return _flux_local(prompt, destino, log) or _pollinations_16x9(prompt, destino, log)
    return _pollinations_16x9(prompt, destino, log) or _flux_local(prompt, destino, log)


def _frases(texto: str, n: int = 3) -> list[str]:
    """Las primeras frases de la narración, recortadas a viñeta."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if len(f.split()) >= 4]
    return [(" ".join(f.split()[:12]) + ("…" if len(f.split()) > 12 else "")).rstrip(".") for f in frases[:n]]


def _imagenes_ia(curso_id: str, escenas: list, log=print) -> None:
    """Escenas con imagen_prompt y sin imagen de la documentación → imagen IA.
    Si no se puede, la escena pasa a viñetas con ideas de la narración
    (nunca una diapositiva vacía)."""
    carpeta = cs.subdir(curso_id, "assets")
    for e in escenas:
        c = e["contenido"]
        if e["layout"] not in ("imagen_texto", "imagen_completa") or c.get("imagen"):
            continue
        prompt = c.get("imagen_prompt") or c.get("titulo") or ""
        ruta = None
        if prompt:
            log(f"   -> Imagen IA: {prompt[:60]}")
            ruta = generar_imagen_curso(prompt, carpeta / f"ia_{e['id']}.jpg", log)
        if ruta:
            c["imagen"] = str(Path(ruta).relative_to(cs.dir_curso(curso_id))).replace("\\", "/")
        else:
            e["layout"] = "vinetas"
            if not c.get("vinetas"):
                c["vinetas"] = _frases(e.get("narracion", "")) or [c.get("titulo", "")]


# ─── 3. Importar un PowerPoint tal cual ──────────────────────────────────────

def importar_pptx(curso_id: str, doc: dict, log=print) -> dict:
    """Cada diapositiva del .pptx → una escena. Las notas del orador son la
    narración; si una diapositiva no tiene notas, la IA la escribe a partir
    del título y las viñetas. Se agrupan en lecciones de hasta 12."""
    diapos = doc.get("diapositivas") or []
    if not diapos:
        raise ValueError("El PowerPoint no tiene diapositivas")
    escenas = []
    for i, d in enumerate(diapos):
        if i == 0:
            esc = cs.escena_vacia("portada", titulo=d["titulo"] or doc["titulo"],
                                  subtitulo=(d["vinetas"] or [""])[0])
        elif d["imagenes"]:
            esc = cs.escena_vacia("imagen_texto", titulo=d["titulo"], vinetas=d["vinetas"][:5],
                                  imagen=d["imagenes"][0])
        else:
            esc = cs.escena_vacia("vinetas", titulo=d["titulo"], vinetas=d["vinetas"][:6])
        esc["narracion"] = d.get("notas", "")
        esc["fuente"] = f"{doc['titulo']} · diapositiva {d['numero']}"
        escenas.append(esc)

    sin_notas = [e for e in escenas if not e["narracion"].strip()]
    if sin_notas:
        log(f"   -> {len(sin_notas)} diapositivas sin notas: la IA escribe su narración...")
        for k in range(0, len(sin_notas), 8):
            lote = sin_notas[k:k + 8]
            listado = "\n".join(
                f'{j}. {e["contenido"].get("titulo", "")}: ' + "; ".join(e["contenido"].get("vinetas", []))
                for j, e in enumerate(lote))
            prompt = (
                f"Presentación: {doc['titulo']}\nTexto completo:\n{doc.get('texto', '')[:8000]}\n\n"
                "Escribe la narración (lo que dice el profesor, 40-90 palabras, español) para cada una de estas "
                f"diapositivas, explicando su contenido sin leerlo literalmente:\n{listado}\n\n"
                'Devuelve SOLO JSON: {"narraciones": ["...", "..."]} en el mismo orden.'
            )
            try:
                narr = _llm_json(prompt, max_tokens=3000).get("narraciones") or []
            except Exception as ex:  # noqa: BLE001
                log(f"   [WARN] narración IA: {ex}")
                narr = []
            for e, t in zip(lote, narr):
                e["narracion"] = str(t).strip()
            for e in lote:  # sin IA: al menos el título y las viñetas
                if not e["narracion"]:
                    e["narracion"] = ". ".join(filter(None, [e["contenido"].get("titulo", ""),
                                                            *e["contenido"].get("vinetas", [])]))

    lecciones = []
    for n, k in enumerate(range(0, len(escenas), 12), 1):
        trozo = escenas[k:k + 12]
        titulo = doc["titulo"] if len(escenas) <= 12 else f"{doc['titulo']} ({n})"
        lecciones.append({"id": cs.nuevo_id(), "titulo": titulo, "resumen": "", "objetivos": [],
                          "estado": "lista", "error": "", "escenas": trozo, "render": None})

    def aplicar(c):
        c["modulos"].append({"id": cs.nuevo_id(), "titulo": doc["titulo"], "lecciones": lecciones})
        c["rev_modulos"] = c.get("rev_modulos", 0) + 1
    cs.modificar(curso_id, aplicar)
    return cs.cargar(curso_id)
