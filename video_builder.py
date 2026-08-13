"""
video_builder.py
Genera un video vertical (1080x1920, formato Reels/TikTok/Shorts) con:
  - fondo dinamico: foto real relacionada al tema (si hay PEXELS_API_KEY) o
    un degradado procedural con viñeta/glow/grano, con efecto de zoom lento
    (Ken Burns) para que no se sienta estatico
  - titulo arriba
  - subtitulos grandes sincronizados, en formato "karaoke" (van resaltando
    palabra por palabra en sincronia con el audio, estilo CapCut)
  - audio narrado
  - duracion total <= 60 segundos

No depende de ImageMagick: los textos se renderizan con PIL y se insertan
como ImageClip, lo cual es mas portable.
"""

import io
import os
import random
import tempfile
import textwrap

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    ImageClip, AudioFileClip, VideoFileClip,
    CompositeVideoClip, concatenate_videoclips, vfx
)

ANCHO, ALTO = 1080, 1920

_AQUI = os.path.dirname(os.path.abspath(__file__))

COLOR_TEXTO = (255, 255, 255, 255)
COLOR_ACTIVO = (255, 209, 0, 255)  # dorado: resalta la palabra que se esta narrando


def _resolver_fuente(nombre_local: str, candidatos_sistema: list) -> str:
    """
    Busca primero la fuente empaquetada en assets/fonts/ (funciona igual en
    cualquier sistema operativo), y si no esta, prueba rutas tipicas de
    fuentes del sistema (Linux/Mac/Windows) como respaldo.
    """
    ruta_local = os.path.join(_AQUI, "assets", "fonts", nombre_local)
    if os.path.isfile(ruta_local):
        return ruta_local
    for ruta in candidatos_sistema:
        if os.path.isfile(ruta):
            return ruta
    raise FileNotFoundError(
        f"No se encontro la fuente '{nombre_local}'. Asegurate de que la carpeta "
        f"'assets/fonts/' este junto a video_builder.py, o instala DejaVu Sans "
        f"en tu sistema."
    )


FONT_BOLD = _resolver_fuente(
    "DejaVuSans-Bold.ttf",
    [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/Library/Fonts/Arial Bold.ttf",  # Mac
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # Mac
        "C:\\Windows\\Fonts\\arialbd.ttf",  # Windows
    ],
)
FONT_REGULAR = _resolver_fuente(
    "DejaVuSans.ttf",
    [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "/Library/Fonts/Arial.ttf",  # Mac
        "/System/Library/Fonts/Supplemental/Arial.ttf",  # Mac
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows
    ],
)

# paletas de color (degradado) por tema
PALETAS = {
    "tecnologia": ((10, 15, 40), (60, 20, 120)),
    "negocios": ((10, 40, 30), (10, 90, 60)),
    "mundo": ((20, 20, 20), (70, 10, 10)),
    "ciencia": ((5, 30, 50), (10, 90, 130)),
    "salud": ((0, 40, 40), (0, 100, 90)),
    "deportes": ((40, 10, 10), (120, 30, 20)),
    "entretenimiento": ((50, 10, 50), (140, 30, 120)),
    "default": ((15, 15, 25), (50, 20, 90)),
}


def _crear_fondo_degradado(tema: str = "default") -> Image.Image:
    """Degradado procedural con viñeta suave y grano, para que el fondo se
    sienta menos plano que un simple degradado liso (sin depender de ninguna
    imagen externa)."""
    color_arriba, color_abajo = PALETAS.get(tema, PALETAS["default"])
    top = np.array(color_arriba, dtype=float)
    bottom = np.array(color_abajo, dtype=float)
    filas = np.linspace(0, 1, ALTO)[:, None] * (bottom - top) + top
    gradiente = np.tile(filas[:, None, :], (1, ANCHO, 1)).astype(float)

    # Viñeta radial sutil: oscurece un poco las esquinas para dar profundidad
    # y ayudar a que el texto centrado resalte mas.
    ys, xs = np.mgrid[0:ALTO, 0:ANCHO]
    cx, cy = ANCHO / 2, ALTO / 2
    dist = np.sqrt(((xs - cx) / cx) ** 2 + ((ys - cy) / cy) ** 2)
    vineta = np.clip(1.0 - 0.35 * np.clip(dist - 0.4, 0, None), 0.55, 1.0)
    gradiente *= vineta[:, :, None]

    # Grano fino, para textura (evita el aspecto "banda plana" del degradado).
    rng = np.random.default_rng(abs(hash(tema)) % (2**32))
    grano = rng.normal(0, 5.0, size=(ALTO, ANCHO, 1))
    gradiente += grano

    gradiente = np.clip(gradiente, 0, 255).astype("uint8")
    return Image.fromarray(gradiente, mode="RGB")


def _fondo_desde_pexels(tema: str, api_key: str) -> "Image.Image | None":
    """
    Busca una foto real relacionada al tema en Pexels (gratis, requiere
    PEXELS_API_KEY opcional) y la recorta/oscurece para usar de fondo.
    Devuelve None si falla o no hay resultados (el llamador cae al degradado
    procedural sin interrumpir la generacion del video).
    """
    consultas = {
        "tecnologia": "technology abstract dark",
        "negocios": "business city skyline dark",
        "mundo": "world map globe dark",
        "ciencia": "science laboratory abstract dark",
        "salud": "health wellness abstract dark",
        "deportes": "sports stadium lights dark",
        "entretenimiento": "cinema lights abstract dark",
        "default": "abstract gradient dark texture",
    }
    query = consultas.get(tema, consultas["default"])
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "orientation": "portrait", "per_page": 12},
            headers={"Authorization": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        fotos = resp.json().get("photos", [])
        if not fotos:
            return None
        foto = random.choice(fotos[: min(6, len(fotos))])
        url_img = foto["src"]["portrait"]

        img_resp = requests.get(url_img, timeout=15)
        img_resp.raise_for_status()
        img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")

        # Cubrir 1080x1920 completo, recortando el sobrante centrado.
        escala = max(ANCHO / img.width, ALTO / img.height)
        nuevo_tam = (int(img.width * escala) + 1, int(img.height * escala) + 1)
        img = img.resize(nuevo_tam, Image.LANCZOS)
        x0 = (img.width - ANCHO) // 2
        y0 = (img.height - ALTO) // 2
        img = img.crop((x0, y0, x0 + ANCHO, y0 + ALTO))

        # Oscurecer para que el texto/subtitulos resalten encima.
        overlay = Image.new("RGB", img.size, (0, 0, 0))
        img = Image.blend(img, overlay, 0.45)
        return img
    except Exception as e:
        print(f"[WARN] No se pudo obtener imagen de fondo de Pexels: {e}")
        return None


def _crear_fondo(tema: str = "default") -> Image.Image:
    """
    Elige el fondo del video: si hay PEXELS_API_KEY configurada, intenta usar
    una foto real relacionada al tema; si no hay clave o falla la busqueda,
    usa el degradado procedural (siempre disponible, sin API key).
    """
    api_key = os.environ.get("PEXELS_API_KEY")
    if api_key:
        img = _fondo_desde_pexels(tema, api_key)
        if img is not None:
            return img
    return _crear_fondo_degradado(tema)


def _envolver_texto(draw, texto, font, max_ancho):
    palabras = texto.split()
    lineas = []
    linea_actual = ""
    for palabra in palabras:
        prueba = (linea_actual + " " + palabra).strip()
        bbox = draw.textbbox((0, 0), prueba, font=font)
        if bbox[2] - bbox[0] <= max_ancho:
            linea_actual = prueba
        else:
            if linea_actual:
                lineas.append(linea_actual)
            linea_actual = palabra
    if linea_actual:
        lineas.append(linea_actual)
    return lineas


def _frame_texto(texto: str, font_path: str, tam_fuente: int, y_centro: int,
                  max_ancho: int = 900, color_texto=(255, 255, 255, 255),
                  con_fondo=True, max_lineas: int = 6, tam_fuente_min: int = 34) -> Image.Image:
    """Crea una imagen RGBA (tamano del video) con el texto centrado, envuelto y
    con una caja semi-transparente detras para legibilidad. Si el texto es largo,
    reduce el tamano de fuente automaticamente para que no ocupe mas de
    max_lineas lineas (evita que subtitulos largos se salgan de pantalla)."""
    img = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype(font_path, tam_fuente)
    lineas = _envolver_texto(draw, texto, font, max_ancho)
    while len(lineas) > max_lineas and tam_fuente > tam_fuente_min:
        tam_fuente -= 4
        font = ImageFont.truetype(font_path, tam_fuente)
        lineas = _envolver_texto(draw, texto, font, max_ancho)

    alturas_linea = tam_fuente + 14
    alto_total = alturas_linea * len(lineas)
    y = y_centro - alto_total // 2

    if con_fondo:
        pad_x, pad_y = 40, 30
        anchos = [draw.textbbox((0, 0), l, font=font)[2] for l in lineas]
        ancho_caja = max(anchos) + pad_x * 2
        draw.rounded_rectangle(
            [
                (ANCHO - ancho_caja) // 2,
                y - pad_y,
                (ANCHO + ancho_caja) // 2,
                y + alto_total + pad_y,
            ],
            radius=30,
            fill=(0, 0, 0, 150),
        )

    for linea in lineas:
        bbox = draw.textbbox((0, 0), linea, font=font)
        ancho_linea = bbox[2] - bbox[0]
        x = (ANCHO - ancho_linea) // 2
        draw.text((x, y), linea, font=font, fill=color_texto)
        y += alturas_linea

    return img


def _frame_texto_karaoke(palabras_chunk: list, idx_activo: int, font_path: str,
                          tam_fuente: int, y_centro: int, max_ancho: int = 900) -> Image.Image:
    """
    Como _frame_texto, pero para un grupo pequeño de palabras (chunk) donde
    una de ellas (idx_activo) se resalta en color distinto: es el frame que
    se muestra mientras se narra esa palabra especifica, creando el efecto
    de subtitulos "karaoke" palabra por palabra (estilo CapCut/reels virales).
    """
    img = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, tam_fuente)
    espacio = draw.textbbox((0, 0), "A A", font=font)[2] - draw.textbbox((0, 0), "AA", font=font)[2]

    # Envolver el chunk en lineas (normalmente entra en una sola linea corta).
    lineas, linea_actual, ancho_actual = [], [], 0
    for palabra in palabras_chunk:
        w = draw.textbbox((0, 0), palabra, font=font)[2]
        extra = (espacio if linea_actual else 0) + w
        if linea_actual and ancho_actual + extra > max_ancho:
            lineas.append(linea_actual)
            linea_actual, ancho_actual = [], 0
            extra = w
        linea_actual.append(palabra)
        ancho_actual += extra
    if linea_actual:
        lineas.append(linea_actual)

    alturas_linea = tam_fuente + 16
    alto_total = alturas_linea * len(lineas)
    y = y_centro - alto_total // 2

    def ancho_linea(linea):
        return sum(draw.textbbox((0, 0), p, font=font)[2] for p in linea) + espacio * (len(linea) - 1)

    pad_x, pad_y = 40, 30
    ancho_caja = max(ancho_linea(l) for l in lineas) + pad_x * 2
    draw.rounded_rectangle(
        [(ANCHO - ancho_caja) // 2, y - pad_y, (ANCHO + ancho_caja) // 2, y + alto_total + pad_y],
        radius=30, fill=(0, 0, 0, 150),
    )

    contador = 0
    for linea in lineas:
        x = (ANCHO - ancho_linea(linea)) // 2
        for palabra in linea:
            color = COLOR_ACTIVO if contador == idx_activo else COLOR_TEXTO
            draw.text((x, y), palabra, font=font, fill=color)
            x += draw.textbbox((0, 0), palabra, font=font)[2] + espacio
            contador += 1
        y += alturas_linea

    return img


def _duraciones_proporcionales(palabras: list, duracion_total: float) -> list:
    """Reparte duracion_total entre las palabras, dando un poco mas de tiempo
    a las palabras largas (estimacion simple, sin alineacion forzada de audio)."""
    pesos = [max(len(p), 3) for p in palabras]
    total_peso = sum(pesos) or 1
    return [duracion_total * (p / total_peso) for p in pesos]


def _clips_subtitulos_karaoke(frases: list, tiempos: list, font_path: str,
                               tam_fuente: int = 64, y_centro: int = None,
                               max_ancho: int = 880, palabras_por_chunk: int = 4):
    """
    Genera un ImageClip por CADA PALABRA de cada frase, resaltandola dentro de
    su chunk (grupo de ~palabras_por_chunk palabras) mientras se narra, para
    lograr el efecto de subtitulos animados palabra por palabra sincronizados
    con el audio.
    """
    if y_centro is None:
        y_centro = ALTO // 2
    clips = []
    for frase, (inicio_frase, dur_frase) in zip(frases, tiempos):
        palabras = frase.split()
        if not palabras:
            continue
        duraciones = _duraciones_proporcionales(palabras, dur_frase)
        tiempos_palabra = []
        t = inicio_frase
        for d in duraciones:
            tiempos_palabra.append(t)
            t += d

        chunks = [palabras[i:i + palabras_por_chunk] for i in range(0, len(palabras), palabras_por_chunk)]
        idx_global = 0
        for chunk in chunks:
            n = len(chunk)
            for local_idx in range(n):
                palabra_inicio = tiempos_palabra[idx_global + local_idx]
                palabra_dur = duraciones[idx_global + local_idx]
                img = _frame_texto_karaoke(chunk, local_idx, font_path, tam_fuente, y_centro, max_ancho)
                clip = (
                    ImageClip(np.array(img))
                    .set_start(palabra_inicio)
                    .set_duration(palabra_dur)
                )
                clips.append(clip)
            idx_global += n
    return clips


def _partir_si_es_larga(frase: str, max_palabras: int = 14):
    """Divide una frase larga en 2 mitades (por comas si es posible) para que
    cada subtitulo en pantalla se mantenga corto y legible."""
    palabras = frase.split()
    if len(palabras) <= max_palabras:
        return [frase]
    mitad = len(palabras) // 2
    # buscar una coma cerca de la mitad para cortar en un punto natural
    corte = mitad
    for i in range(max(mitad - 4, 1), min(mitad + 4, len(palabras) - 1)):
        if palabras[i].endswith(","):
            corte = i + 1
            break
    return [" ".join(palabras[:corte]), " ".join(palabras[corte:])]


def _dividir_en_frases(guion: dict):
    """Usa hook / puntos / cierre como 'frases' independientes para sincronizar,
    partiendo las que sean demasiado largas para que cada subtitulo quepa bien
    en pantalla. Si los campos estructurados están vacíos (IA devolvió solo
    guion["guion"]), parte el texto completo en oraciones."""
    frases_base = [guion.get("hook", "")] + list(guion.get("puntos", [])) + [guion.get("cierre", "")]
    frases = []
    for f in frases_base:
        if f.strip():
            frases.extend(_partir_si_es_larga(f))

    if not frases and guion.get("guion"):
        import re
        # Remove surrounding quotes (Claude sometimes wraps paragraphs in quotes)
        texto = re.sub(r'^["\']|["\']$', '', guion["guion"].strip())
        texto = re.sub(r'"\s*\n\s*"', ' ', texto)  # join "para1"\n"para2"
        oraciones = re.split(r'(?<=[.!?])\s+', texto)
        for o in oraciones:
            o = o.strip().strip('"').strip("'")
            if o:
                frases.extend(_partir_si_es_larga(o))

    return frases


def _clip_avatar(ruta_video: str, duracion_total: float,
                  tam: int = 380, y_pos: int = None) -> "CompositeVideoClip | None":
    """
    Carga el video del avatar (SadTalker/D-ID), lo recorta en círculo
    y lo posiciona en la parte inferior del frame.
    """
    if not ruta_video or not os.path.isfile(ruta_video):
        return None
    try:
        clip = VideoFileClip(ruta_video, audio=False)

        # Loopear si el avatar es más corto que el video
        if clip.duration < duracion_total:
            n = int(duracion_total / clip.duration) + 1
            clip = concatenate_videoclips([clip] * n).subclip(0, duracion_total)
        else:
            clip = clip.subclip(0, duracion_total)

        # Recortar al cuadrado y redimensionar
        w, h = clip.size
        lado = min(w, h)
        clip = clip.crop(x1=(w - lado) // 2, y1=(h - lado) // 2,
                         x2=(w + lado) // 2, y2=(h + lado) // 2)
        clip = clip.resize((tam, tam))

        # Máscara circular
        mascara = np.zeros((tam, tam), dtype=float)
        cy, cx = tam // 2, tam // 2
        r = tam // 2 - 4
        yy, xx = np.ogrid[:tam, :tam]
        mascara[(xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2] = 1.0
        mask_clip = ImageClip(mascara, ismask=True).set_duration(duracion_total)
        clip = clip.set_mask(mask_clip)

        # Borde blanco alrededor del círculo
        borde_tam = tam + 8
        borde_arr = np.zeros((borde_tam, borde_tam, 4), dtype=np.uint8)
        br = borde_tam // 2 - 1
        byy, bxx = np.ogrid[:borde_tam, :borde_tam]
        circulo = (bxx - borde_tam // 2) ** 2 + (byy - borde_tam // 2) ** 2 <= br ** 2
        borde_arr[circulo] = [255, 255, 255, 80]
        borde_clip = (ImageClip(borde_arr, ismask=False)
                      .set_duration(duracion_total)
                      .set_position(((ANCHO - borde_tam) // 2,
                                     (y_pos or (ALTO - tam - 100)) - 4)))

        x = (ANCHO - tam) // 2
        y = y_pos if y_pos is not None else ALTO - tam - 100
        clip = clip.set_position((x, y))

        return [borde_clip, clip]
    except Exception as e:
        print(f"[WARN] No se pudo cargar avatar: {e}")
        return None


def _crear_fondo_clip_desde_imagenes(rutas: list, duracion_total: float):
    """Slideshow con Ken Burns: cada imagen ocupa duracion_total/n segundos."""
    from moviepy.editor import concatenate_videoclips
    dur_por_img = duracion_total / len(rutas)
    clips = []
    for ruta in rutas:
        try:
            img = Image.open(ruta).convert("RGB")
            # Recortar/redimensionar al tamaño del video
            escala = max(ANCHO / img.width, ALTO / img.height)
            nuevo = (int(img.width * escala) + 1, int(img.height * escala) + 1)
            img = img.resize(nuevo, Image.LANCZOS)
            x0 = (img.width - ANCHO) // 2
            y0 = (img.height - ALTO) // 2
            img = img.crop((x0, y0, x0 + ANCHO, y0 + ALTO))
            clip = (
                ImageClip(np.array(img))
                .set_duration(dur_por_img)
                .fx(vfx.resize, lambda t, d=dur_por_img: 1 + 0.06 * (t / max(d, 0.01)))
                .set_position("center")
            )
            clips.append(clip)
        except Exception as e:
            print(f"[WARN] No se pudo cargar imagen {ruta}: {e}")
    if not clips:
        return None
    return concatenate_videoclips(clips, method="compose")


def construir_video(guion: dict, ruta_audio: str, ruta_salida: str,
                     tema: str = "default", duracion_maxima: int = 60,
                     preset: str = "medium", fps: int = 30,
                     imagenes: list = None,
                     ruta_avatar: str = None,
                     marca: str = None,
                     mostrar_titulo: bool = False,
                     mostrar_subtitulos: bool = True,
                     musica_fondo: str = None,
                     volumen_musica: float = 0.3,
                     volumen_voz: float = 1.0,
                     texto_personalizado: str = None) -> str:
    """
    Genera el mp4 final. guion viene de summarizer.generar_guion_reel().
    ruta_audio es el mp3/wav generado por tts.generar_audio().
    imagenes: lista de rutas de imágenes locales para usar como fondo (slideshow).
              Si es None o vacía, usa el fondo procedural/Pexels.
    """
    audio_clip = AudioFileClip(ruta_audio)
    duracion_audio = min(audio_clip.duration, duracion_maxima)
    if audio_clip.duration > duracion_maxima:
        audio_clip = audio_clip.subclip(0, duracion_maxima)

    # Mezcla con música de fondo si se proporcionó
    if musica_fondo and os.path.isfile(musica_fondo):
        try:
            import moviepy.audio.fx.all as afx
            from moviepy.editor import CompositeAudioClip
            music = AudioFileClip(musica_fondo)
            if music.duration < duracion_audio:
                music = afx.audio_loop(music, duration=duracion_audio)
            else:
                music = music.subclip(0, duracion_audio)
            voz = audio_clip.volumex(volumen_voz)
            musica = music.volumex(volumen_musica)
            audio_clip = CompositeAudioClip([voz, musica])
        except Exception as e:
            print(f"[WARN] No se pudo añadir música de fondo: {e}")

    frases = _dividir_en_frases(guion)
    palabras_por_frase = [max(len(f.split()), 1) for f in frases]
    total_palabras = sum(palabras_por_frase)

    # tiempo proporcional al numero de palabras de cada frase
    tiempos = []
    t = 0.0
    for n_palabras in palabras_por_frase:
        dur = duracion_audio * (n_palabras / total_palabras)
        tiempos.append((t, dur))
        t += dur

    # Fondo: imágenes proporcionadas → slideshow, si no → degradado/Pexels
    fondo_clip = None
    if imagenes:
        fondo_clip = _crear_fondo_clip_desde_imagenes(imagenes, duracion_audio)

    if fondo_clip is None:
        fondo_img = _crear_fondo(tema)
        fondo_clip = ImageClip(np.array(fondo_img)).set_duration(duracion_audio)
        fondo_clip = fondo_clip.fx(
            vfx.resize, lambda t: 1 + 0.06 * (t / max(duracion_audio, 0.01))
        ).set_position("center")

    # titulo fijo arriba
    titulo_img = _frame_texto(
        guion["titulo"], FONT_BOLD, 58, y_centro=220, max_ancho=940
    )
    titulo_clip = (
        ImageClip(np.array(titulo_img))
        .set_duration(duracion_audio)
        .set_start(0)
    )

    # Avatar hablando (opcional)
    avatar_clips = []
    y_subtitulos = ALTO // 2  # posición default de subtítulos (centro)
    TAM_AVATAR = 380

    if ruta_avatar:
        y_avatar = ALTO - TAM_AVATAR - 80  # zona inferior
        clips_resultado = _clip_avatar(ruta_avatar, duracion_audio, tam=TAM_AVATAR, y_pos=y_avatar)
        if clips_resultado:
            avatar_clips = clips_resultado
            # Subir subtítulos para que no se sobrepongan al avatar
            y_subtitulos = ALTO - TAM_AVATAR - 200

    # Subtitulos animados palabra por palabra (karaoke)
    clips_subtitulos = (
        _clips_subtitulos_karaoke(frases, tiempos, FONT_BOLD, y_centro=y_subtitulos)
        if mostrar_subtitulos else []
    )

    # Texto personalizado (nombre canción, fuente, subtítulo libre…)
    if texto_personalizado:
        y_texto_pers = ALTO - 180 if not ruta_avatar else y_avatar - 80
        texto_pers_img = _frame_texto(
            texto_personalizado, FONT_REGULAR, 42,
            y_centro=y_texto_pers, max_ancho=920,
            color_texto=(255, 255, 255, 220),
        )
        texto_pers_clips = [ImageClip(np.array(texto_pers_img)).set_duration(duracion_audio)]
    else:
        texto_pers_clips = []

    if marca:
        marca_img = _frame_texto(
            marca, FONT_REGULAR, 32,
            y_centro=ALTO - 40 if not ruta_avatar else y_avatar - 20,
            max_ancho=900, con_fondo=False,
            color_texto=(255, 255, 255, 130),
        )
        marca_clip = [ImageClip(np.array(marca_img)).set_duration(duracion_audio)]
    else:
        marca_clip = []

    capas = (
        [fondo_clip]
        + ([titulo_clip] if mostrar_titulo else [])
        + clips_subtitulos
        + avatar_clips
        + texto_pers_clips
        + marca_clip
    )
    video_final = CompositeVideoClip(capas, size=(ANCHO, ALTO)).set_audio(audio_clip)

    video_final = video_final.set_duration(duracion_audio)

    os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)
    # el archivo de audio temporal se escribe en /tmp: algunas carpetas de salida
    # montadas (p.ej. la carpeta de outputs de Cowork) no permiten borrar archivos,
    # y moviepy necesita poder borrar su temp de audio tras el mux final.
    temp_audio = os.path.join(
        tempfile.gettempdir(), f"_tmp_audio_{os.getpid()}_{os.path.basename(ruta_salida)}.m4a"
    )
    video_final.write_videofile(
        ruta_salida, fps=fps, codec="libx264", audio_codec="aac",
        preset=preset, threads=4, logger=None,
        temp_audiofile=temp_audio, remove_temp=True,
    )

    audio_clip.close()
    video_final.close()
    return ruta_salida


if __name__ == "__main__":
    from summarizer import generar_guion_reel
    from tts import generar_audio

    texto_prueba = (
        "Un nuevo estudio revela que el consumo de energia de los centros de datos "
        "de inteligencia artificial se duplicara para 2027. Las empresas tecnologicas "
        "estan invirtiendo miles de millones en nuevos chips y en infraestructura de "
        "energia renovable para sostener el crecimiento. Expertos advierten que la red "
        "electrica de varios paises podria verse afectada."
    )
    guion = generar_guion_reel("El costo energetico de la IA se dispara", texto_prueba, "Reuters")
    audio_path = generar_audio(guion["guion"], "/tmp/audio_prueba.mp3")
    construir_video(guion, audio_path, "/tmp/reel_prueba.mp4", tema="tecnologia")
    print("Video generado en /tmp/reel_prueba.mp4")
