"""
local_reel_builder.py
Genera un reel vertical (1080x1920) a partir de un audio local (el tramo
[inicio, fin] ya recortado, p.ej. el coro detectado por music_analyzer) y una
lista de clips visuales propios (imagenes y/o videos) usados como fondo en
slideshow.

Reutiliza los mismos helpers visuales que el resto de la app para mantener
un estilo consistente:
  - video_clipper._construir_fondo_desenfocado / _construir_primer_plano
    para los clips de video (fondo desenfocado a pantalla completa + el
    video original centrado encima, sin barras negras).
  - video_builder._crear_fondo_clip_desde_imagenes para las imagenes
    (slideshow con efecto Ken Burns).
  - El mismo estilo de cabecera titulo/artista que music_video_builder.
"""

import os
import re
import tempfile

import numpy as np
from moviepy.editor import (
    AudioFileClip, ImageClip, VideoFileClip, CompositeVideoClip,
    concatenate_videoclips, vfx,
)

from video_builder import ANCHO, ALTO, FONT_BOLD, FONT_REGULAR, _frame_texto
from video_builder import _crear_fondo_clip_desde_imagenes
from video_clipper import _construir_fondo_desenfocado, _construir_primer_plano
from music_analyzer import EXTS_VIDEO

EXTS_IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


# ---------------------------------------------------------------------------
# Cabecera (mismo estilo que music_video_builder._clips_cabecera)
# ---------------------------------------------------------------------------

def _clips_cabecera(titulo: str, artista: str, duracion: float) -> list:
    clips = []
    if titulo:
        img = _frame_texto(titulo, FONT_BOLD, 52, y_centro=130,
                            max_ancho=940, max_lineas=2)
        clips.append(ImageClip(np.array(img)).set_duration(duracion))
    if artista:
        y = 260 if titulo else 130
        img = _frame_texto(artista, FONT_REGULAR, 38, y_centro=y,
                            max_ancho=940, max_lineas=1,
                            color_texto=(210, 160, 255, 220), con_fondo=False)
        clips.append(ImageClip(np.array(img)).set_duration(duracion))
    return clips


# ---------------------------------------------------------------------------
# Fondo: slideshow de imagenes y/o videos propios
# ---------------------------------------------------------------------------

def _fondo_desde_clip_de_video(ruta_video: str, duracion: float):
    """Recorta/alarga (loop) un video propio a `duracion` y lo monta con el
    mismo fondo desenfocado + primer plano centrado que usa el resto de la
    app para clips de video reales."""
    clip = VideoFileClip(ruta_video)
    if clip.duration < duracion:
        clip = clip.fx(vfx.loop, duration=duracion)
    clip = clip.subclip(0, min(duracion, clip.duration))

    fondo = _construir_fondo_desenfocado(clip).set_duration(clip.duration)
    frente = _construir_primer_plano(clip).set_duration(clip.duration)
    compuesto = (
        CompositeVideoClip([fondo, frente], size=(ANCHO, ALTO))
        .set_duration(clip.duration)
    )
    return compuesto, clip


def _construir_fondo_slideshow(rutas_clips: list, duracion_total: float):
    """
    Reparte `rutas_clips` (imagenes y/o videos, en el orden recibido) a lo
    largo de duracion_total. Si son todo imagenes usa el slideshow Ken Burns
    existente; si hay videos, cada uno se reparte en tramos iguales con el
    estilo fondo-desenfocado + primer-plano.

    Devuelve (clip_de_fondo, lista_de_clips_originales_a_cerrar).
    """
    imagenes = [r for r in rutas_clips if os.path.splitext(r)[1].lower() in EXTS_IMG]
    videos = [r for r in rutas_clips if os.path.splitext(r)[1].lower() in EXTS_VIDEO]

    if videos and not imagenes:
        dur_por_clip = duracion_total / len(videos)
        partes, originales = [], []
        for ruta in videos:
            try:
                compuesto, original = _fondo_desde_clip_de_video(ruta, dur_por_clip)
                partes.append(compuesto)
                originales.append(original)
            except Exception as e:
                print(f"[WARN] No se pudo cargar el video {ruta}: {e}")
        if not partes:
            raise ValueError("Ninguno de los clips de video pudo procesarse.")
        return concatenate_videoclips(partes, method="compose"), originales

    if imagenes and not videos:
        fondo = _crear_fondo_clip_desde_imagenes(imagenes, duracion_total)
        if fondo is None:
            raise ValueError("Ninguna de las imagenes pudo cargarse.")
        return fondo, []

    # Mezcla de imagenes y videos: reparte la duracion equitativamente entre
    # todos los clips, respetando el orden en que se pasaron.
    dur_por_clip = duracion_total / len(rutas_clips)
    partes, originales = [], []
    for ruta in rutas_clips:
        ext = os.path.splitext(ruta)[1].lower()
        try:
            if ext in EXTS_VIDEO:
                compuesto, original = _fondo_desde_clip_de_video(ruta, dur_por_clip)
                partes.append(compuesto)
                originales.append(original)
            else:
                parte = _crear_fondo_clip_desde_imagenes([ruta], dur_por_clip)
                if parte is not None:
                    partes.append(parte)
        except Exception as e:
            print(f"[WARN] No se pudo cargar el clip {ruta}: {e}")
    if not partes:
        raise ValueError("Ninguno de los clips visuales pudo procesarse.")
    return concatenate_videoclips(partes, method="compose"), originales


# ---------------------------------------------------------------------------
# Constructor publico
# ---------------------------------------------------------------------------

def construir_reel_video_local(ruta_audio: str, rutas_clips: list, inicio: float,
                                fin: float, titulo: str, artista: str,
                                ruta_salida: str, mostrar_cabecera: bool = True,
                                preset: str = "medium", fps: int = 30) -> str:
    """
    Genera un reel vertical (1080x1920) a partir de:
      - ruta_audio: audio local, recortado al tramo [inicio, fin]
      - rutas_clips: imagenes y/o videos propios usados como fondo/slideshow
      - titulo / artista: cabecera opcional superpuesta arriba

    Escribe el resultado en ruta_salida y devuelve esa misma ruta.
    """
    audio_orig = audio_clip = fondo = video_final = None
    originales = []
    try:
        audio_orig = AudioFileClip(ruta_audio)
        fin_real = min(fin, audio_orig.duration)
        ini_real = max(0.0, min(inicio, fin_real - 1))
        audio_clip = audio_orig.subclip(ini_real, fin_real)
        dur = audio_clip.duration

        fondo, originales = _construir_fondo_slideshow(rutas_clips, dur)
        fondo = fondo.set_duration(dur)

        capas = [fondo]
        if mostrar_cabecera:
            capas += _clips_cabecera(titulo, artista, dur)

        video_final = (
            CompositeVideoClip(capas, size=(ANCHO, ALTO))
            .set_audio(audio_clip)
            .set_duration(dur)
        )
        _escribir_video(video_final, ruta_salida, preset, fps)
    finally:
        for c in (video_final, fondo, audio_clip, audio_orig, *originales):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass
    return ruta_salida


def _escribir_video(video_final, ruta_salida: str, preset: str, fps: int):
    os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)
    slug_tmp = re.sub(r"[^a-z0-9]", "_", os.path.basename(ruta_salida))[:30]
    temp_audio = os.path.join(tempfile.gettempdir(), f"_tmp_local_{os.getpid()}_{slug_tmp}.m4a")
    video_final.write_videofile(
        ruta_salida, fps=fps, codec="libx264", audio_codec="aac",
        preset=preset, threads=4, logger=None,
        temp_audiofile=temp_audio, remove_temp=True,
    )
