"""
thumbnail_maker.py
Miniaturas llamativas y relacionadas con cada reel:

  <slug>_cover.jpg      1080×1920  portada vertical (Reels / Shorts / TikTok)
  <slug>_thumbnail.jpg  1280×720   miniatura de YouTube (mismo nombre de siempre)

Todo en local (sin IA de pago ni servicios externos):
1. El LLM local de LM Studio lee el titular y el guion y devuelve el texto de portada (pocas palabras,
   fiel a la noticia), qué palabras resaltar, una etiqueta de tema y un prompt
   de imagen en inglés con el sujeto concreto de la historia.
   Si LM Studio no responde se usa el titular tal cual.
2. Fondo, por orden: Flux en el ComfyUI local (calidad alta) → la primera imagen
   limpia usada en el reel / og:image del artículo → fotograma del reel → degradado.
   Si ComfyUI está apagado se puede arrancar vía Centro de Control con
   MINIATURAS_ARRANCAR_COMFY=1 (por defecto no: ComfyUI retiene VRAM).
3. Composición con Pillow: color y contraste realzados, degradado solo donde va
   el texto, titular en Montserrat ExtraBold con contorno, palabras clave en
   amarillo, etiqueta de tema y marca del canal. En vertical el texto queda fuera
   de las zonas que tapan los botones de TikTok / Reels / Shorts.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ASSETS = Path(__file__).parent / "assets" / "fonts"
FONT_TITULO = ASSETS / "Montserrat-ExtraBold.ttf"
FONT_ETIQUETA = ASSETS / "Montserrat-Bold.ttf"

AMARILLO = (255, 214, 10)
BLANCO = (255, 255, 255)
ROJO = (229, 57, 53)
NEGRO = (0, 0, 0)

V_W, V_H = 1080, 1920
H_W, H_H = 1280, 720


def _marca() -> str:
    return os.environ.get("CANAL_NOMBRE", "BIENINFORMA2").upper()


def _log(msg: str) -> None:
    print(f"   [miniatura] {msg}")


# ── 1. Concepto (LLM) ─────────────────────────────────────────────────────────

_SYSTEM = (
    "Eres director de arte de un canal de noticias en vertical (TikTok, Reels, Shorts). "
    "Diseñas portadas que hacen parar el scroll sin mentir. Respondes SOLO con JSON."
)

_PROMPT = """Noticia del reel:
TITULAR: {titulo}
GUION: {guion}

Devuelve este JSON:
{{
  "texto": "texto de portada en español, 3 a 7 palabras, MAYÚSCULAS, impactante y FIEL a la noticia; usa SOLO palabras que aparezcan tal cual en el titular o el guion (sin inventar ni cambiar la forma verbal); puede llevar una cifra clave completa (nunca cortada)",
  "destacar": ["1 a 3 palabras exactas de 'texto' que se pintarán en amarillo (la idea clave)"],
  "etiqueta": "UNA de estas: IA, TECNOLOGÍA, CIENCIA, ESPACIO, ECONOMÍA, POLÍTICA, SALUD, DEPORTES, MUNDO, ESPAÑA, CULTURA, MOTOR, CLIMA, SUCESOS, ÚLTIMA HORA",
  "prompt_imagen": "English prompt for a photorealistic, dramatic, vibrant image of the CONCRETE subject of this story (people, objects, place), cinematic lighting, shallow depth of field, high detail. Absolutely no text, letters, signs, screens with words, logos or watermarks."
}}"""


def _norm(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", t)


def _palabras_inventadas(texto: str, fuente: str) -> list[str]:
    """Palabras de la portada (4+ letras) que no están en el titular ni en el guion:
    el LLM local a veces se inventa una forma verbal o comete una errata."""
    vocab = set(_norm(fuente).split())
    raices = {v[:5] for v in vocab if len(v) >= 5}

    def conocida(p: str) -> bool:
        # misma palabra, o misma raíz (recorre ~ recorridas); una errata como
        # "depiso" no comparte raíz con "despide" y se descarta
        return p in vocab or (len(p) >= 5 and p[:5] in raices)

    return [p for p in _norm(texto).split() if len(p) >= 4 and not p.isdigit() and not conocida(p)]


# Temas permitidos, bien escritos: el LLM local elige y aquí se pone la ortografía
# (llegó a devolver "TECNOLÓGIA").
ETIQUETAS = ["IA", "TECNOLOGÍA", "CIENCIA", "ESPACIO", "ECONOMÍA", "POLÍTICA", "SALUD",
             "DEPORTES", "MUNDO", "ESPAÑA", "CULTURA", "MOTOR", "CLIMA", "SUCESOS",
             "ÚLTIMA HORA", "NOTICIA"]
_ALIAS = {"inteligencia artificial": "IA", "ai": "IA", "tecnologico": "TECNOLOGÍA",
          "tech": "TECNOLOGÍA", "astronomia": "ESPACIO", "internacional": "MUNDO",
          "finanzas": "ECONOMÍA", "empleo": "ECONOMÍA", "coches": "MOTOR"}


def _etiqueta(raw: str) -> str:
    n = _norm(raw).strip()
    for e in ETIQUETAS:
        if _norm(e).strip() == n:
            return e
    if n in _ALIAS:
        return _ALIAS[n]
    # errata leve (tecnologia ~ tecnologia con tilde mal puesta ya se cubre arriba)
    for e in ETIQUETAS:
        en = _norm(e).strip()
        if len(n) >= 4 and (en.startswith(n[:5]) or n.startswith(en[:5])):
            return e
    return "NOTICIA"


def _texto_desde_titular(titulo: str) -> tuple[str, list[str]]:
    """Portada de reserva: hasta 7 palabras del titular, sin cortar ninguna."""
    primera = re.split(r"(?<=[^\d])[.!?](?=\s|$)", titulo.strip())[0]
    palabras = primera.upper().split()[:7]
    texto = " ".join(palabras).rstrip(".,;:")
    cifras = [p for p in palabras if re.search(r"\d", p)]
    return texto, (cifras or palabras[-1:])[:2]


def _concepto(titulo: str, guion: str) -> dict:
    texto_res, destacar_res = _texto_desde_titular(titulo)
    fallback = {
        "texto": texto_res,
        "destacar": destacar_res,
        "etiqueta": "NOTICIA",
        "prompt_imagen": f"{titulo}, photojournalism, dramatic cinematic lighting, vibrant, no text",
    }
    fuente = f"{titulo} {guion}"
    data, texto, valido = {}, "", False
    for _ in range(2):
        try:
            from comfy_video_builder import _json_lenient
            from llm_local import completar  # siempre local (LM Studio)
            raw = completar(_PROMPT.format(titulo=titulo, guion=(guion or "")[:1500]),
                            max_tokens=2000, temperature=0.7, system=_SYSTEM)
            data = _json_lenient(raw)
        except Exception as e:  # noqa: BLE001
            _log(f"LM Studio no disponible ({e}); uso el titular")
            return fallback
        texto = re.sub(r"\s+", " ", str(data.get("texto") or "")).strip().upper()
        malas = _palabras_inventadas(texto, fuente)
        if 2 <= len(texto.split()) <= 9 and not malas:
            valido = True
            break
        _log(f"texto descartado ({texto!r}; no están en la noticia: {malas})")

    if valido:
        destacar = data.get("destacar") or []
        if isinstance(destacar, str):
            destacar = [destacar]
        # Como mucho 3 palabras en amarillo, y solo las que están en el texto
        en_texto = set(texto.split())
        destacar = [w for d in destacar if isinstance(d, str) for w in d.upper().split() if w in en_texto][:3]
    else:
        # El texto del modelo no vale, pero su etiqueta y su imagen sí
        texto, destacar = texto_res, destacar_res
    return {
        "texto": texto,
        "destacar": destacar,
        "etiqueta": _etiqueta(str(data.get("etiqueta") or "")),
        "prompt_imagen": str(data.get("prompt_imagen") or fallback["prompt_imagen"]),
    }


# ── 2. Fondo ──────────────────────────────────────────────────────────────────

def _flux(prompt: str, w: int, h: int, dest: Path) -> Path | None:
    try:
        import comfy_video_builder as cvb
    except Exception:
        return None
    if not cvb.comfy_disponible():
        if os.environ.get("MINIATURAS_ARRANCAR_COMFY") == "1" and cvb.control_center_disponible():
            _log("ComfyUI apagado: lo arranco vía Centro de Control")
            cvb.arrancar_via_control_center(["comfyui"])
        if not cvb.comfy_disponible():
            return None
    try:
        _log(f"Flux {w}×{h}")
        return cvb.generar_frame_flux(
            f"{prompt}, no text, no letters, no watermark", random.randint(1, 2**31 - 1), dest, w, h,
        )
    except Exception as e:  # noqa: BLE001
        _log(f"Flux falló: {e}")
        return None


def _fondos(concepto: dict, imagenes: list[str], url_articulo: str | None,
            tmp: Path) -> tuple[Image.Image | None, Image.Image | None, str]:
    """(fondo vertical, fondo horizontal, origen)."""
    p = concepto["prompt_imagen"] + ", vibrant saturated colors, high contrast, striking, epic"
    v = _flux(p + ", vertical composition, main subject large in the lower half of the frame, "
              "clean dark negative space in the upper third", 768, 1344, tmp / "v.png")
    if v:
        h = _flux(p + ", main subject on the right side, darker empty space on the left", 1344, 768, tmp / "h.png")
        return Image.open(v), Image.open(h) if h else Image.open(v), "flux"

    candidatas = [i for i in (imagenes or []) if i and os.path.isfile(i)]
    if not candidatas and url_articulo and "news.google.com" not in url_articulo:
        try:
            from image_pipeline import extraer_og_image
            og = extraer_og_image(url_articulo, str(tmp / "og.jpg"))
            if og:
                candidatas.append(og)
        except Exception:
            pass
    if candidatas:
        im = Image.open(candidatas[0])
        return im, im, "imagen del reel"

    return None, None, "degradado"


# ── 3. Composición ────────────────────────────────────────────────────────────

def _cubrir(im: Image.Image, w: int, h: int) -> Image.Image:
    im = im.convert("RGB")
    esc = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * esc) + 1, int(im.height * esc) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _realzar(im: Image.Image) -> Image.Image:
    im = ImageEnhance.Color(im).enhance(1.25)
    im = ImageEnhance.Contrast(im).enhance(1.12)
    return im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))


def _degradado_base(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(40 + 60 * t), int(12 + 10 * t), int(80 + 60 * (1 - t))))
    return im


def _sombra_vertical(w: int, h: int, y0: int, y1: int, alpha: int) -> Image.Image:
    """Capa negra que se funde hacia arriba y abajo entre y0 e y1."""
    capa = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(capa)
    centro, medio = (y0 + y1) / 2, max(1, (y1 - y0) / 2)
    for y in range(max(0, y0), min(h, y1)):
        a = alpha * (1 - (abs(y - centro) / medio) ** 2)
        d.line([(0, y), (w, y)], fill=int(max(0, a)))
    negro = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    negro.putalpha(capa)
    return negro


def _sombra_superior(w: int, h: int, hasta: int, alpha: int) -> Image.Image:
    """Negro arriba que se desvanece hacia abajo hasta `hasta`."""
    capa = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(capa)
    for y in range(min(h, hasta)):
        d.line([(0, y), (w, y)], fill=int(alpha * (1 - y / hasta) ** 0.8))
    negro = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    negro.putalpha(capa)
    return negro


def _sombra_izquierda(w: int, h: int, hasta: int, alpha: int) -> Image.Image:
    capa = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(capa)
    for x in range(hasta):
        d.line([(x, 0), (x, h)], fill=int(alpha * (1 - x / hasta) ** 1.3))
    negro = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    negro.putalpha(capa)
    return negro


def _partir(palabras: list[str], font: ImageFont.FreeTypeFont, ancho: int) -> list[list[str]]:
    lineas, actual = [], []
    for p in palabras:
        prueba = actual + [p]
        if actual and font.getlength(" ".join(prueba)) > ancho:
            lineas.append(actual)
            actual = [p]
        else:
            actual = prueba
    if actual:
        lineas.append(actual)
    return lineas


def _ajustar(texto: str, ancho: int, max_lineas: int, tam_max: int, tam_min: int):
    palabras = texto.split()
    for tam in range(tam_max, tam_min - 1, -4):
        font = ImageFont.truetype(str(FONT_TITULO), tam)
        lineas = _partir(palabras, font, ancho)
        if len(lineas) <= max_lineas and all(font.getlength(" ".join(ln)) <= ancho for ln in lineas):
            return font, lineas
    font = ImageFont.truetype(str(FONT_TITULO), tam_min)
    return font, _partir(palabras, font, ancho)[:max_lineas]


def _es_destacada(palabra: str, destacar: list[str]) -> bool:
    limpia = re.sub(r"[^\wÁÉÍÓÚÜÑ%€$]", "", palabra.upper())
    return any(limpia == re.sub(r"[^\wÁÉÍÓÚÜÑ%€$]", "", d) for dd in destacar for d in dd.split())


def _pintar_titular(draw: ImageDraw.ImageDraw, lineas: list[list[str]], font, x_ancla: int,
                    y: int, destacar: list[str], centrado: bool) -> int:
    alto = int(font.size * 1.08)
    trazo = max(4, font.size // 14)
    esp = font.getlength(" ")
    for ln in lineas:
        total = font.getlength(" ".join(ln))
        x = x_ancla - total / 2 if centrado else x_ancla
        for p in ln:
            color = AMARILLO if _es_destacada(p, destacar) else BLANCO
            draw.text((x + trazo, y + trazo * 1.5), p, font=font, fill=(0, 0, 0))
            draw.text((x, y), p, font=font, fill=color, stroke_width=trazo, stroke_fill=NEGRO)
            x += font.getlength(p) + esp
        y += alto
    return y


def _pastilla(draw: ImageDraw.ImageDraw, texto: str, x: int, y: int, tam: int,
              fondo: tuple, centrado: bool = False, punto: bool = False) -> tuple[int, int]:
    font = ImageFont.truetype(str(FONT_ETIQUETA), tam)
    tw = font.getlength(texto)
    pad_x, pad_y = int(tam * 0.7), int(tam * 0.35)
    r = int(tam * 0.22) if punto else 0
    extra = 2 * r + int(tam * 0.4) if punto else 0
    w, h = int(tw + 2 * pad_x + extra), int(tam + 2 * pad_y)
    if centrado:
        x = int(x - w / 2)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=fondo)
    if punto:
        cx, cy = x + pad_x + r, y + h // 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLANCO)
    draw.text((x + pad_x + extra, y + pad_y + tam * 0.05), texto, font=font, fill=BLANCO)
    return w, h


def _vertical(fondo: Image.Image | None, c: dict) -> Image.Image:
    base = _realzar(_cubrir(fondo, V_W, V_H)) if fondo else _degradado_base(V_W, V_H)
    font, lineas = _ajustar(c["texto"], 940, 4, 150, 84)
    alto_txt = len(lineas) * int(font.size * 1.08)
    # Zona segura: arriba ~260 px de interfaz, abajo ~520 px (texto y botones).
    # El titular va en el tercio superior; el protagonista de la imagen, debajo.
    y_tit = 400
    img = Image.alpha_composite(base.convert("RGBA"),
                                _sombra_superior(V_W, V_H, y_tit + alto_txt + 320, 200))
    d = ImageDraw.Draw(img)
    _pastilla(d, c["etiqueta"], V_W // 2, y_tit - 110, 40, ROJO, centrado=True, punto=True)
    y_fin = _pintar_titular(d, lineas, font, V_W // 2, y_tit, c["destacar"], centrado=True)
    _pastilla(d, _marca(), V_W // 2, y_fin + 30, 34, (20, 20, 20), centrado=True)
    return img.convert("RGB")


def _horizontal(fondo: Image.Image | None, c: dict) -> Image.Image:
    base = _realzar(_cubrir(fondo, H_W, H_H)) if fondo else _degradado_base(H_W, H_H)
    img = Image.alpha_composite(base.convert("RGBA"), _sombra_izquierda(H_W, H_H, 860, 190))
    d = ImageDraw.Draw(img)
    font, lineas = _ajustar(c["texto"], 700, 4, 118, 64)
    alto_txt = len(lineas) * int(font.size * 1.08)
    y = (H_H - alto_txt) // 2 + 10
    _pastilla(d, c["etiqueta"], 56, y - 78, 30, ROJO, punto=True)
    _pintar_titular(d, lineas, font, 56, y, c["destacar"], centrado=False)
    _pastilla(d, _marca(), 56, H_H - 78, 26, (20, 20, 20))
    return img.convert("RGB")


# ── API ───────────────────────────────────────────────────────────────────────

def generar_miniaturas(slug: str, carpeta_salida: str, titulo: str, guion: str = "",
                       imagenes: list[str] | None = None, url_articulo: str | None = None) -> dict:
    """Genera <slug>_cover.jpg (9:16) y <slug>_thumbnail.jpg (16:9).
    Devuelve {"cover", "thumbnail", "fondo", "texto"}."""
    carpeta = Path(carpeta_salida)
    tmp = Path(tempfile.mkdtemp(prefix="_thumb_"))
    try:
        c = _concepto(titulo, guion)
        _log(f"texto: {c['texto']} | destacar: {c['destacar']} | etiqueta: {c['etiqueta']}")
        # El texto ya está: fuera el modelo de LM Studio para que Flux tenga toda la GPU
        from llm_local import liberar_gpu_para_video
        liberar_gpu_para_video()
        fondo_v, fondo_h, origen = _fondos(c, imagenes or [], url_articulo, tmp)
        _log(f"fondo: {origen}")
        cover = carpeta / f"{slug}_cover.jpg"
        thumb = carpeta / f"{slug}_thumbnail.jpg"
        _vertical(fondo_v, c).save(cover, "JPEG", quality=92)
        _horizontal(fondo_h, c).save(thumb, "JPEG", quality=92)
        (carpeta / f"{slug}_miniatura.json").write_text(
            json.dumps({**c, "fondo": origen}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"cover": str(cover), "thumbnail": str(thumb), "fondo": origen, "texto": c["texto"]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def generar_para_reel(video_filename: str, carpeta_salida: str) -> dict:
    """Miniaturas de un reel ya generado, a partir de sus ficheros acompañantes
    (guion, fuente). Sin imágenes del reel a mano: Flux o un fotograma del vídeo."""
    carpeta = Path(carpeta_salida)
    stem = Path(video_filename).stem
    slug = re.sub(r"_(reel|largo|music_reel)$", "", stem)
    titulo, guion = slug.replace("-", " "), ""
    for g in (carpeta / f"{slug}_guion_reel.txt", carpeta / f"{slug}_guion_largo.txt"):
        if g.exists():
            txt = g.read_text(encoding="utf-8")
            cab, _, cuerpo = txt.partition("\n\n")
            guion = cuerpo.strip()
            m = re.search(r"^Titulo:\s*(.+)$", cab, re.M)
            if m:
                titulo = m.group(1).strip()
            break
    fuente = carpeta / f"{slug}_fuente.json"
    url = None
    if fuente.exists():
        try:
            meta = json.loads(fuente.read_text(encoding="utf-8"))
            titulo = meta.get("titulo_original") or titulo
            url = meta.get("url_original")
        except Exception:
            pass

    imagenes = []
    video = carpeta / video_filename
    if video.exists():
        # Fotograma representativo del tramo central (evita intro y cierre)
        import subprocess
        frame = carpeta / f".{slug}_frame.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "8", "-i", str(video),
                        "-vf", "thumbnail=90", "-frames:v", "1", str(frame)], check=False)
        if frame.exists():
            imagenes.append(str(frame))
    try:
        return generar_miniaturas(slug, carpeta_salida, titulo, guion, imagenes,
                                  url_articulo=None if url and "youtube.com" in url else url)
    finally:
        for i in imagenes:
            Path(i).unlink(missing_ok=True)


def portadas_de(video_path: str) -> dict:
    """Portada vertical y miniatura 16:9 que acompañan a un vídeo de output/
    ({slug}_cover.jpg / {slug}_thumbnail.jpg). Valores None si no existen."""
    p = Path(video_path)
    slug = re.sub(r"(_short\d+)?_(music_)?(reel|largo)$", "", p.stem)
    out = {}
    for clave, sufijo in (("cover", "_cover.jpg"), ("thumbnail", "_thumbnail.jpg")):
        f = p.parent / f"{slug}{sufijo}"
        out[clave] = str(f) if f.is_file() else None
    return out
