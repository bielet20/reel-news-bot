"""
lyric_video_builder.py
Genera clips de videoclip vertical (1080x1920) a partir de audio + letra.
Un clip independiente por sección (Verso, Estribillo, Puente…).

Pipeline por sección:
  1. Calcula su duración proporcional al nº de líneas.
  2. Genera una imagen AI con Pollinations (gratis, sin API key).
  3. Aplica efecto Ken Burns sobre la imagen.
  4. Superpone letra y etiqueta de sección.
  5. Exporta como MP4 con el segmento de audio correspondiente.
"""

import hashlib
import os
import re
import tempfile
import urllib.parse
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, vfx

from video_builder import ALTO, ANCHO, FONT_BOLD, FONT_REGULAR, _frame_texto

# ── Constantes ────────────────────────────────────────────────────────────────

CACHE_DIR = Path(__file__).parent / "_img_cache"
CACHE_DIR.mkdir(exist_ok=True)

ESTILOS: dict[str, str] = {
    "cinematico":  "cinematic film still, dramatic lighting, moody atmosphere, dark tones",
    "abstracto":   "abstract art, colorful geometric shapes, fluid art, dreamy surreal",
    "urbano":      "urban street art, neon city lights, graffiti aesthetic, night photography",
    "naturaleza":  "natural landscape, golden hour, ethereal fog, soft light, vast scenery",
    "minimalista": "minimalist design, clean lines, subtle muted colors, elegant simplicity",
    "romantico":   "romantic atmosphere, soft bokeh, warm pink tones, intimate, candlelight",
}

_SECCION_LABELS_AUTO = [
    "Intro", "Verso 1", "Pre-Estribillo", "Estribillo",
    "Verso 2", "Pre-Estribillo", "Estribillo",
    "Puente", "Estribillo", "Outro",
]

_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "con", "y",
    "que", "se", "no", "a", "su", "sus", "por", "es", "al", "lo", "le",
    "me", "te", "mi", "tu", "yo", "tú", "pero", "o", "ni", "si", "ya",
    "me", "te", "nos", "os", "les", "era", "ser", "hay", "más", "tan",
    "sin", "sobre", "como", "cuando", "donde", "eres", "tiene", "hace",
}


# ── Parseo de letra ───────────────────────────────────────────────────────────

def parsear_secciones(letra: str) -> list[dict]:
    """
    Convierte la letra en una lista de secciones.

    Formato con etiquetas (recomendado):
        [Verso 1]
        línea 1
        línea 2

        [Estribillo]
        línea 3

    Formato sin etiquetas: divide por párrafos (líneas en blanco).

    Returns:
        [{"label": str, "lineas": [str]}, ...]
    """
    tiene_etiquetas = bool(re.search(r"^\[.+?\]", letra, re.MULTILINE))

    if tiene_etiquetas:
        bloques = re.split(r"\n(?=\[)", letra.strip())
        secciones = []
        for bloque in bloques:
            lines = bloque.strip().splitlines()
            if not lines:
                continue
            primera = lines[0].strip()
            label = re.sub(r"[\[\]]", "", primera) if primera.startswith("[") else "Sección"
            lineas = [l.strip() for l in lines[1:] if l.strip()]
            if lineas:
                secciones.append({"label": label, "lineas": lineas})
    else:
        parrafos = re.split(r"\n\s*\n", letra.strip())
        secciones = []
        for i, parrafo in enumerate(parrafos):
            lineas = [l.strip() for l in parrafo.splitlines() if l.strip()]
            if lineas:
                label = _SECCION_LABELS_AUTO[i] if i < len(_SECCION_LABELS_AUTO) else f"Sección {i + 1}"
                secciones.append({"label": label, "lineas": lineas})

    return secciones


# ── Generación de imágenes ────────────────────────────────────────────────────

def _palabras_clave(texto: str) -> str:
    palabras = re.sub(r"[^\w\s]", " ", texto.lower()).split()
    clave = [p for p in palabras if len(p) > 3 and p not in _STOPWORDS]
    return " ".join(clave[:6]) or "music abstract"


def _imagen_seccion(texto: str, artista: str, estilo_key: str, seed: int) -> np.ndarray:
    """Descarga (o recupera del caché) la imagen AI para una sección."""
    estilo_desc = ESTILOS.get(estilo_key, ESTILOS["cinematico"])
    tema = _palabras_clave(texto)

    prompt_parts = [tema, "music video aesthetic", estilo_desc, "vertical 9:16 portrait", "no text no watermark"]
    if artista:
        prompt_parts.append(f"inspired by {artista}")
    prompt = ", ".join(prompt_parts)

    cache_key = hashlib.md5(f"{prompt}{seed}".encode()).hexdigest()[:14]
    cache_path = CACHE_DIR / f"lyric_{cache_key}.jpg"

    if not cache_path.exists():
        encoded = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1920&seed={seed}&nologo=true&model=flux"
        )
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            cache_path.write_bytes(r.content)
        except Exception as e:
            print(f"[LyricVideo] Error imagen AI: {e} — usando degradado")
            return _degradado_fallback()

    try:
        img = Image.open(cache_path).convert("RGB")
    except Exception:
        return _degradado_fallback()

    # Recortar a 1080×1920
    escala = max(ANCHO / img.width, ALTO / img.height)
    nw, nh = int(img.width * escala) + 1, int(img.height * escala) + 1
    img = img.resize((nw, nh), Image.LANCZOS)
    x0 = (img.width - ANCHO) // 2
    y0 = (img.height - ALTO) // 2
    img = img.crop((x0, y0, x0 + ANCHO, y0 + ALTO))

    # Oscurecer para que la letra sea legible
    overlay = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, overlay, 0.48)

    return np.array(img)


def _degradado_fallback() -> np.ndarray:
    top = np.array([5, 0, 20], dtype=float)
    bot = np.array([75, 0, 90], dtype=float)
    filas = np.linspace(0, 1, ALTO)[:, None] * (bot - top) + top
    grad = np.tile(filas[:, None, :], (1, ANCHO, 1)).astype(float)
    return np.clip(grad, 0, 255).astype("uint8")


# ── Capas de texto ────────────────────────────────────────────────────────────

def _clips_letra(lineas: list[str], dur: float) -> list:
    """Clips de letra: 2 líneas por pantalla, distribuidas uniformemente."""
    paginas = ["\n".join(lineas[i:i + 2]) for i in range(0, len(lineas), 2)]
    if not paginas:
        return []
    dur_pag = dur / len(paginas)
    clips = []
    for i, pag in enumerate(paginas):
        img = _frame_texto(pag, FONT_BOLD, 66, y_centro=int(ALTO * 0.73),
                           max_ancho=940, max_lineas=3)
        fade = min(0.25, dur_pag / 4)
        c = (
            ImageClip(np.array(img))
            .set_start(i * dur_pag)
            .set_duration(dur_pag)
            .crossfadein(fade)
            .crossfadeout(fade)
        )
        clips.append(c)
    return clips


def _clip_etiqueta(label: str, dur: float) -> ImageClip:
    img = _frame_texto(
        label.upper(), FONT_REGULAR, 28, y_centro=70,
        max_ancho=900, color_texto=(200, 160, 255, 170), con_fondo=False,
    )
    return ImageClip(np.array(img)).set_duration(min(3.0, dur)).crossfadein(0.3).crossfadeout(0.3)


def _clips_cabecera(titulo: str, artista: str, dur: float) -> list:
    clips = []
    if titulo:
        img = _frame_texto(titulo, FONT_BOLD, 52, y_centro=130, max_ancho=940, max_lineas=2)
        clips.append(ImageClip(np.array(img)).set_duration(dur))
    if artista:
        y = 260 if titulo else 130
        img = _frame_texto(artista, FONT_REGULAR, 38, y_centro=y, max_ancho=940, max_lineas=1,
                           color_texto=(210, 160, 255, 220), con_fondo=False)
        clips.append(ImageClip(np.array(img)).set_duration(dur))
    return clips


# ── Generador principal ───────────────────────────────────────────────────────

def generar_clips(
    ruta_audio: str,
    letra: str,
    artista: str,
    titulo: str,
    estilo: str,
    ruta_salida_base: str,
    mostrar_letra: bool = True,
    mostrar_cabecera: bool = True,
    cb_progreso=None,
) -> list[str]:
    """
    Genera un clip MP4 por sección de la letra.

    Args:
        ruta_audio:       Ruta al archivo de audio (mp3, wav, flac).
        letra:            Texto completo de la letra.
        artista:          Nombre del artista.
        titulo:           Título de la canción.
        estilo:           Clave de ESTILOS.
        ruta_salida_base: Prefijo para los archivos de salida (sin extensión).
        mostrar_letra:    Superponer letra en el video.
        mostrar_cabecera: Mostrar título/artista en el primer clip.
        cb_progreso:      Callable(seccion_idx, total, label) para reportar avance.

    Returns:
        Lista de rutas a los MP4 generados.
    """
    secciones = parsear_secciones(letra)
    if not secciones:
        raise ValueError("No se encontraron secciones en la letra.")

    audio_full = AudioFileClip(ruta_audio)
    dur_total = audio_full.duration

    # Distribuir duración proporcionalmente al número de líneas
    total_lineas = sum(len(s["lineas"]) for s in secciones) or 1
    tiempos: list[tuple[float, float]] = []
    t = 0.0
    for sec in secciones:
        prop = len(sec["lineas"]) / total_lineas
        dur = max(4.0, dur_total * prop)
        fin = min(t + dur, dur_total)
        tiempos.append((t, fin))
        t = fin
        if t >= dur_total:
            break

    rutas = []

    for i, (sec, (t_ini, t_fin)) in enumerate(zip(secciones, tiempos)):
        if t_fin <= t_ini:
            continue

        if cb_progreso:
            cb_progreso(i, len(secciones), sec["label"])

        audio_clip = audio_full.subclip(t_ini, t_fin)
        dur = audio_clip.duration

        # Imagen AI
        img_arr = _imagen_seccion(
            "\n".join(sec["lineas"]), artista, estilo, seed=i * 19 + 7
        )

        # Ken Burns: zoom lento hacia adentro
        fondo = (
            ImageClip(img_arr)
            .set_duration(dur)
            .fx(vfx.resize, lambda t, d=dur: 1.0 + 0.06 * (t / max(d, 0.01)))
            .set_position("center")
        )

        capas: list = [fondo]

        # Etiqueta de sección (esquina superior)
        capas.append(_clip_etiqueta(sec["label"], dur))

        # Cabecera título/artista (solo primer clip)
        if mostrar_cabecera and i == 0:
            capas += _clips_cabecera(titulo, artista, dur)

        # Letra
        if mostrar_letra and sec["lineas"]:
            capas += _clips_letra(sec["lineas"], dur)

        video = (
            CompositeVideoClip(capas, size=(ANCHO, ALTO))
            .set_audio(audio_clip)
            .set_duration(dur)
        )

        slug = re.sub(r"[^\w]", "_", sec["label"].lower())[:18]
        ruta_out = f"{ruta_salida_base}_{i + 1:02d}_{slug}_reel.mp4"
        tmp_audio = os.path.join(tempfile.gettempdir(), f"_lyric_{os.getpid()}_{i}.m4a")

        video.write_videofile(
            ruta_out, fps=30, codec="libx264", audio_codec="aac",
            preset="medium", threads=4, logger=None,
            temp_audiofile=tmp_audio, remove_temp=True,
        )

        # Desacoplar audio antes de cerrar el video: audio_clip comparte el reader
        # de audio_full y cerrarlo aquí mataría el proceso ffmpeg para el resto.
        video.audio = None
        try:
            video.close()
        except Exception:
            pass

        print(f"[LyricVideo] {i + 1}/{len(secciones)} → {Path(ruta_out).name}")
        rutas.append(ruta_out)

    audio_full.close()
    return rutas
