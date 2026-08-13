"""
music_video_builder.py
Genera reels musicales verticales (1080x1920) para Instagram/TikTok/Shorts.

Dos modos segun la fuente:
  - Video (.mp4, YouTube descargado): recorta el segmento, lo reencuadra a
    9:16 con fondo desenfocado, superpone titulo/artista y letra (si hay).
  - Audio puro (.mp3, .wav, .flac): crea un fondo de degradado animado
    (estilo lyric video) con titulo/artista y letra sincronizada.
"""

import os
import re
import tempfile

import numpy as np
from PIL import Image
from moviepy.editor import (
    AudioFileClip, ImageClip, CompositeVideoClip, VideoFileClip, vfx,
)

from video_builder import (
    ANCHO, ALTO, FONT_BOLD, FONT_REGULAR, _frame_texto,
)
from video_clipper import _construir_fondo_desenfocado, _construir_primer_plano

# Paleta morada oscura, especifica para reels musicales
_PALETA_TOP = (5, 0, 20)
_PALETA_BOT = (75, 0, 90)


# ---------------------------------------------------------------------------
# Fondo degradado para modo audio-only
# ---------------------------------------------------------------------------

def _crear_fondo_musica() -> Image.Image:
    top = np.array(_PALETA_TOP, dtype=float)
    bot = np.array(_PALETA_BOT, dtype=float)
    filas = np.linspace(0, 1, ALTO)[:, None] * (bot - top) + top
    grad = np.tile(filas[:, None, :], (1, ANCHO, 1)).astype(float)

    ys, xs = np.mgrid[0:ALTO, 0:ANCHO]
    cx, cy = ANCHO / 2, ALTO / 2
    dist = np.sqrt(((xs - cx) / cx) ** 2 + ((ys - cy) / cy) ** 2)
    vineta = np.clip(1.0 - 0.45 * np.clip(dist - 0.3, 0, None), 0.45, 1.0)
    grad *= vineta[:, :, None]

    rng = np.random.default_rng(7)
    grad += rng.normal(0, 4.0, size=(ALTO, ANCHO, 1))
    return Image.fromarray(np.clip(grad, 0, 255).astype("uint8"), mode="RGB")


# ---------------------------------------------------------------------------
# Letra (lyrics)
# ---------------------------------------------------------------------------

def parsear_letra(ruta_txt: str) -> list:
    """Lee el .txt de letra y devuelve lista de lineas no vacias."""
    with open(ruta_txt, "r", encoding="utf-8") as f:
        lineas = [l.strip() for l in f]
    return [l for l in lineas if l]


def _paginas(lineas: list, por_pagina: int = 2) -> list:
    """Agrupa lineas en paginas de N lineas."""
    return [
        "\n".join(lineas[i: i + por_pagina])
        for i in range(0, len(lineas), por_pagina)
    ]


def _clips_letra(paginas: list, duracion_total: float) -> list:
    """
    Un ImageClip por pagina de letra, distribuidas uniformemente,
    con crossfade suave entre ellas.
    """
    if not paginas:
        return []
    dur = duracion_total / len(paginas)
    clips = []
    for i, pag in enumerate(paginas):
        img = _frame_texto(pag, FONT_BOLD, 72, y_centro=ALTO // 2,
                           max_ancho=960, max_lineas=4)
        fade = min(0.3, dur / 4)
        c = (
            ImageClip(np.array(img))
            .set_start(i * dur)
            .set_duration(dur)
            .crossfadein(fade)
            .crossfadeout(fade)
        )
        clips.append(c)
    return clips


# ---------------------------------------------------------------------------
# Titulo y artista
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
# Constructores publicos
# ---------------------------------------------------------------------------

def construir_reel_musical_desde_video(ruta_video: str, inicio: float, fin: float,
                                        titulo: str, artista: str,
                                        lineas_letra: list, ruta_salida: str,
                                        preset: str = "medium", fps: int = 30,
                                        mostrar_cabecera: bool = True) -> str:
    """
    Recorta [inicio, fin] del video, lo reencuadra a 9:16 con fondo
    desenfocado y superpone cabecera + letra.
    """
    clip_orig = subclip = video_final = None
    try:
        clip_orig = VideoFileClip(ruta_video)
        fin_real = min(fin, clip_orig.duration)
        ini_real = max(0.0, min(inicio, fin_real - 1))
        fin_real = min(fin_real, ini_real + (fin - inicio))

        subclip = clip_orig.subclip(ini_real, fin_real)
        dur = subclip.duration

        fondo = _construir_fondo_desenfocado(subclip).set_duration(dur)
        frente = _construir_primer_plano(subclip).set_duration(dur)

        capas = [fondo, frente]
        if mostrar_cabecera:
            capas += _clips_cabecera(titulo, artista, dur)
        if lineas_letra:
            capas += _clips_letra(_paginas(lineas_letra), dur)

        video_final = (
            CompositeVideoClip(capas, size=(ANCHO, ALTO))
            .set_audio(subclip.audio)
            .set_duration(dur)
        )
        _escribir_video(video_final, ruta_salida, preset, fps)
    finally:
        for c in (video_final, subclip, clip_orig):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass
    return ruta_salida


def construir_reel_musical_desde_audio(ruta_audio: str, inicio: float, fin: float,
                                        titulo: str, artista: str,
                                        lineas_letra: list, ruta_salida: str,
                                        preset: str = "medium", fps: int = 30,
                                        mostrar_cabecera: bool = True) -> str:
    """
    Crea un reel estilo lyric-video sobre fondo degradado animado,
    usando el audio directo (.mp3, .wav, etc.).
    """
    audio_orig = audio_clip = video_final = None
    try:
        audio_orig = AudioFileClip(ruta_audio)
        fin_real = min(fin, audio_orig.duration)
        audio_clip = audio_orig.subclip(max(0.0, inicio), fin_real)
        dur = audio_clip.duration

        fondo_img = _crear_fondo_musica()
        fondo = (
            ImageClip(np.array(fondo_img))
            .set_duration(dur)
            .fx(vfx.resize, lambda t: 1 + 0.04 * (t / max(dur, 0.01)))
            .set_position("center")
        )

        capas = [fondo]
        if mostrar_cabecera:
            capas += _clips_cabecera(titulo, artista, dur)

        if lineas_letra:
            capas += _clips_letra(_paginas(lineas_letra), dur)
        else:
            img = _frame_texto("~ ~ ~", FONT_BOLD, 110, y_centro=ALTO // 2,
                               max_ancho=800, con_fondo=False,
                               color_texto=(180, 100, 255, 180))
            capas.append(ImageClip(np.array(img)).set_duration(dur))

        video_final = (
            CompositeVideoClip(capas, size=(ANCHO, ALTO))
            .set_audio(audio_clip)
            .set_duration(dur)
        )
        _escribir_video(video_final, ruta_salida, preset, fps)
    finally:
        for c in (video_final, audio_clip, audio_orig):
            try:
                if c is not None:
                    c.close()
            except Exception:
                pass
    return ruta_salida


def _escribir_video(video_final, ruta_salida: str, preset: str, fps: int):
    os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)
    slug_tmp = re.sub(r"[^a-z0-9]", "_", os.path.basename(ruta_salida))[:30]
    temp_audio = os.path.join(tempfile.gettempdir(), f"_tmp_mus_{os.getpid()}_{slug_tmp}.m4a")
    video_final.write_videofile(
        ruta_salida, fps=fps, codec="libx264", audio_codec="aac",
        preset=preset, threads=4, logger=None,
        temp_audiofile=temp_audio, remove_temp=True,
    )
