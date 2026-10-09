"""
course_ingest.py
Lee la documentación que se sube a un curso (zona «Cursos» de la web) y la
deja como texto plano + imágenes, lista para que course_builder genere el
temario y las lecciones.

Formatos: PDF (pymupdf), Word .docx (python-docx), PowerPoint .pptx
(python-pptx: además del texto devuelve cada diapositiva con título, viñetas,
imágenes y notas, para importarlas como escenas), Markdown/texto y URLs
(article_extractor.extraer_texto).

Cada documento devuelve:
    {"titulo", "tipo", "texto", "secciones": [{"titulo", "texto"}],
     "imagenes": [rutas], "diapositivas": [...] (solo pptx)}
"""

import hashlib
import os
import re
from pathlib import Path

EXTS_TEXTO = {".md", ".markdown", ".txt", ".rst"}
EXTS_SOPORTADAS = {".pdf", ".docx", ".pptx"} | EXTS_TEXTO
_MIN_LADO_IMAGEN = 200  # descarta iconos y viñetas decorativas


def _guardar_imagen(datos: bytes, ext: str, carpeta: Path) -> str | None:
    """Guarda la imagen con nombre por hash (sin duplicados). None si es diminuta."""
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(datos)) as im:
            if min(im.size) < _MIN_LADO_IMAGEN:
                return None
    except Exception:
        return None
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = hashlib.sha1(datos).hexdigest()[:16] + "." + (ext or "png").lstrip(".").lower()
    ruta = carpeta / nombre
    if not ruta.exists():
        ruta.write_bytes(datos)
    return str(ruta)


def _secciones_markdown(texto: str) -> list[dict]:
    """Parte un texto en secciones por encabezados Markdown (#, ##, ###)."""
    secciones, actual = [], {"titulo": "", "texto": []}
    for linea in texto.splitlines():
        m = re.match(r"^\s{0,3}#{1,3}\s+(.+)", linea)
        if m:
            if actual["texto"] or actual["titulo"]:
                secciones.append(actual)
            actual = {"titulo": m.group(1).strip(), "texto": []}
        else:
            actual["texto"].append(linea)
    secciones.append(actual)
    return [{"titulo": s["titulo"], "texto": "\n".join(s["texto"]).strip()}
            for s in secciones if s["titulo"] or "".join(s["texto"]).strip()]


def leer_pdf(ruta: str, carpeta_imgs: Path) -> dict:
    import pymupdf
    doc = pymupdf.open(ruta)
    paginas, imagenes = [], []
    for pagina in doc:
        paginas.append(pagina.get_text("text"))
        for img in pagina.get_images(full=True):
            try:
                info = doc.extract_image(img[0])
                r = _guardar_imagen(info["image"], info.get("ext", "png"), carpeta_imgs)
                if r and r not in imagenes:
                    imagenes.append(r)
            except Exception:
                continue
    # Secciones: el índice (TOC) del PDF si lo tiene; si no, una por página
    toc = doc.get_toc()
    secciones = []
    if toc:
        for i, (_, titulo, pag) in enumerate(toc):
            fin = toc[i + 1][2] if i + 1 < len(toc) else len(paginas) + 1
            texto = "\n".join(paginas[max(0, pag - 1):max(pag, fin - 1)])
            secciones.append({"titulo": titulo.strip(), "texto": texto.strip()})
    else:
        secciones = [{"titulo": f"Página {i + 1}", "texto": t.strip()}
                     for i, t in enumerate(paginas) if t.strip()]
    titulo = (doc.metadata or {}).get("title") or Path(ruta).stem
    return {"titulo": titulo, "tipo": "pdf", "texto": "\n\n".join(paginas).strip(),
            "secciones": secciones, "imagenes": imagenes}


def leer_docx(ruta: str, carpeta_imgs: Path) -> dict:
    import docx
    d = docx.Document(ruta)
    lineas = []
    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        estilo = (p.style.name or "").lower() if p.style is not None else ""
        if estilo.startswith("heading") or estilo.startswith("título") or estilo == "title":
            nivel = re.findall(r"\d", estilo)
            lineas.append("#" * min(3, int(nivel[0]) if nivel else 1) + " " + t)
        elif "list" in estilo or "lista" in estilo:
            lineas.append(f"- {t}")
        else:
            lineas.append(t)
    for tabla in d.tables:
        for fila in tabla.rows:
            lineas.append(" | ".join(c.text.strip() for c in fila.cells))
    imagenes = []
    for rel in d.part.rels.values():
        if "image" in rel.reltype:
            try:
                ext = os.path.splitext(rel.target_ref)[1]
                r = _guardar_imagen(rel.target_part.blob, ext, carpeta_imgs)
                if r and r not in imagenes:
                    imagenes.append(r)
            except Exception:
                continue
    texto = "\n".join(lineas)
    titulo = d.core_properties.title or Path(ruta).stem
    return {"titulo": titulo, "tipo": "docx", "texto": texto,
            "secciones": _secciones_markdown(texto), "imagenes": imagenes}


def leer_pptx(ruta: str, carpeta_imgs: Path) -> dict:
    """Además del texto, devuelve cada diapositiva para importarla como escena:
    título, viñetas, imagen principal y notas del orador (→ narración)."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    prs = Presentation(ruta)
    diapositivas, imagenes, partes = [], [], []
    for n, slide in enumerate(prs.slides, 1):
        titulo, viñetas, imgs = "", [], []
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            titulo = slide.shapes.title.text_frame.text.strip()
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    r = _guardar_imagen(shape.image.blob, shape.image.ext, carpeta_imgs)
                    if r:
                        imgs.append(r)
                        if r not in imagenes:
                            imagenes.append(r)
                except Exception:
                    pass
            elif shape.has_text_frame and shape != slide.shapes.title:
                for p in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in p.runs).strip()
                    if t:
                        viñetas.append(t)
        notas = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notas = slide.notes_slide.notes_text_frame.text.strip()
        diapositivas.append({"numero": n, "titulo": titulo, "vinetas": viñetas,
                             "imagenes": imgs, "notas": notas})
        partes.append("\n".join(filter(None, [f"# {titulo}" if titulo else f"# Diapositiva {n}",
                                              *[f"- {v}" for v in viñetas],
                                              f"Notas: {notas}" if notas else ""])))
    texto = "\n\n".join(partes)
    titulo = prs.core_properties.title or Path(ruta).stem
    return {"titulo": titulo, "tipo": "pptx", "texto": texto,
            "secciones": _secciones_markdown(texto), "imagenes": imagenes,
            "diapositivas": diapositivas}


def leer_texto(ruta: str) -> dict:
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\s{0,3}#\s+(.+)", texto, re.M)
    return {"titulo": m.group(1).strip() if m else Path(ruta).stem, "tipo": "texto",
            "texto": texto.strip(), "secciones": _secciones_markdown(texto), "imagenes": []}


def leer_url(url: str) -> dict:
    from article_extractor import extraer_articulo
    art = extraer_articulo(url)
    texto = art.get("texto", "")
    if len(texto.split()) < 30:
        raise ValueError(f"No se pudo leer contenido suficiente de {url}")
    return {"titulo": art.get("titulo") or url, "tipo": "url", "texto": texto,
            "secciones": [{"titulo": art.get("titulo") or url, "texto": texto}],
            "imagenes": [], "url": url}


def leer_documento(ruta: str, carpeta_imgs: Path) -> dict:
    ext = Path(ruta).suffix.lower()
    if ext == ".pdf":
        return leer_pdf(ruta, carpeta_imgs)
    if ext == ".docx":
        return leer_docx(ruta, carpeta_imgs)
    if ext == ".pptx":
        return leer_pptx(ruta, carpeta_imgs)
    if ext in EXTS_TEXTO:
        return leer_texto(ruta)
    raise ValueError(f"Formato no soportado: {ext}. Usa PDF, Word (.docx), PowerPoint (.pptx), Markdown o texto.")
