"""
video_clipper.py
Genera un reel a partir de un RECORTE REAL de un video de YouTube (no de una
narracion sintetica sobre fondo generico).

Pipeline:
  1. descargar_video()          -> baja el video original con yt-dlp
  2. detectar_mejor_segmento()  -> usa la transcripcion con marcas de tiempo
                                    para encontrar el tramo mas informativo
                                    (~duracion_objetivo segundos)
  3. generar_reel_desde_clip()  -> recorta ese tramo, lo reencuadra a vertical
                                    9:16 (video original centrado sobre un
                                    fondo desenfocado del mismo video, sin
                                    deformar ni recortar contenido), quema
                                    subtitulos sincronizados con el audio/
                                    video real, y exporta el mp4 final.

No requiere ninguna API key: yt-dlp descarga el video publico y
youtube_transcript_api ya provee las marcas de tiempo (ver youtube_extractor.py).
"""

import os
import re
import tempfile
import time

import cv2
import numpy as np
from moviepy.editor import (
    VideoFileClip, ImageClip, CompositeVideoClip, vfx,
)

from summarizer import (
    PALABRA_RE, PALABRAS_CLAVE_VIDEO, _normalizar, _limpiar_transcripcion,
)
from video_builder import (
    ANCHO, ALTO, FONT_BOLD, FONT_REGULAR, _frame_texto, _partir_si_es_larga,
)

ANCHO_V, ALTO_V = ANCHO, ALTO  # 1080x1920


# ---------------------------------------------------------------------------
# 1. Descarga del video original (yt-dlp, sin API key)
# ---------------------------------------------------------------------------

def descargar_video(url: str, carpeta_tmp: str = None,
                     cookies_browser: str = None) -> str:
    """
    Descarga el video de YouTube (calidad <=1080p, mp4) a una carpeta temporal
    y devuelve la ruta local. Lanza RuntimeError si falla.

    cookies_browser: nombre del navegador del que leer las cookies para
                     autenticar la descarga (bypass de restricciones de
                     edad/region). Valores: "chrome", "safari", "firefox",
                     "edge", "chromium", "brave", "opera", "vivaldi".
                     Si es None, descarga sin autenticar.
    """
    try:
        import yt_dlp
    except ImportError:
        raise ImportError(
            "Falta instalar yt-dlp:\n  pip install yt-dlp"
        )

    carpeta_tmp = carpeta_tmp or tempfile.gettempdir()
    os.makedirs(carpeta_tmp, exist_ok=True)
    salida = os.path.join(carpeta_tmp, f"_ytsrc_{int(time.time() * 1000)}.%(ext)s")

    opciones = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": salida,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 2,
    }

    if cookies_browser:
        # Permite descargar videos con restriccion de edad/region usando
        # la sesion activa del navegador del usuario.
        opciones["cookiesfrombrowser"] = (cookies_browser,)

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
            ruta = ydl.prepare_filename(info)
            base, _ = os.path.splitext(ruta)
            candidato_mp4 = base + ".mp4"
            if os.path.isfile(candidato_mp4):
                return candidato_mp4
            if os.path.isfile(ruta):
                return ruta
            raise RuntimeError("yt-dlp no genero el archivo esperado.")
    except Exception as e:
        sugerencia = (
            f" Podes reintentar con --cookies-browser chrome (o safari/firefox) "
            "para usar tu sesion del navegador."
        ) if not cookies_browser else ""
        raise RuntimeError(
            f"No se pudo descargar el video de YouTube ({e}). Puede estar "
            f"restringido por edad/region, ser privado, o YouTube bloqueo la "
            f"descarga automatica.{sugerencia}"
        ) from e


# ---------------------------------------------------------------------------
# 2. Deteccion del mejor tramo (highlight) usando la transcripcion con tiempos
# ---------------------------------------------------------------------------

def _limpiar_segmentos(segmentos: list) -> list:
    """Copia los segmentos limpiando muletillas del texto (solo para scoring
    y para lo que se muestra en pantalla, no afecta los tiempos)."""
    limpios = []
    for seg in segmentos:
        texto = _limpiar_transcripcion(seg["text"])
        if texto:
            limpios.append({**seg, "text": texto})
    return limpios


def _conteo_texto_exacto(segmentos: list) -> dict:
    """Cuenta cuantas veces se repite (casi) textualmente cada segmento. Sirve
    para detectar boilerplate (intro/outro/CTA repetido) que no deberia
    considerarse un highlight aunque use palabras 'importantes'."""
    conteo = {}
    for seg in segmentos:
        clave = seg["text"].strip().lower()
        conteo[clave] = conteo.get(clave, 0) + 1
    return conteo


def _score_highlight_segmento(texto: str, conteo_duplicados: dict) -> float:
    """
    Puntua un segmento de transcripcion por que tan probable es que sea parte
    de un 'momento destacado' del video: prioriza datos concretos (numeros,
    porcentajes) y palabras que indican informacion relevante, y penaliza el
    texto que se repite identico muchas veces en el video (tipicamente intros,
    outros o llamados a la accion repetidos, no highlights).

    A diferencia del resumen extractivo (summarizer.py), aca NO se usa
    frecuencia de palabras a nivel de todo el video: en un highlight buscamos
    el momento mas denso en informacion puntual, no el tema mas repetido.
    """
    palabras = [_normalizar(p) for p in PALABRA_RE.findall(texto)]
    if not palabras:
        return 0.0

    bonus_clave = sum(0.35 for p in palabras if p in PALABRAS_CLAVE_VIDEO)
    bonus_num = len(re.findall(r"\d+", texto)) * 0.4
    base_contenido = min(len(palabras) / 12.0, 1.0) * 0.15

    duplicados = conteo_duplicados.get(texto.strip().lower(), 1)
    penalizacion = 1.0 / duplicados  # texto repetido identico = probable boilerplate

    return (base_contenido + bonus_clave + bonus_num) * penalizacion


def detectar_mejor_segmento(segmentos: list, duracion_objetivo: int = 45,
                             duracion_min: int = 20, duracion_max: int = 59) -> dict:
    """
    Encuentra la ventana de tiempo [inicio, fin] (duracion <= duracion_max,
    >= duracion_min) con mayor densidad de contenido informativo, usando la
    transcripcion real del video (frecuencia de palabras + palabras clave +
    numeros/datos, igual criterio que summarizer._score_chunk_video).

    Devuelve dict: {inicio, fin, duracion, segmentos, texto}
        - segmentos: sublista de los segmentos originales dentro de la ventana
          (con sus tiempos reales, sin modificar), para quemar subtitulos.
    """
    segmentos = [s for s in segmentos if s["text"].strip()]
    if not segmentos:
        raise ValueError("La transcripcion no tiene segmentos utilizables.")

    segmentos_limpios = _limpiar_segmentos(segmentos)
    if not segmentos_limpios:
        segmentos_limpios = segmentos

    conteo_duplicados = _conteo_texto_exacto(segmentos_limpios)
    scores = [_score_highlight_segmento(s["text"], conteo_duplicados) for s in segmentos_limpios]

    duracion_total = segmentos[-1]["start"] + segmentos[-1]["duration"] - segmentos[0]["start"]
    if duracion_total <= duracion_max:
        # El video entero ya entra en el limite: no hace falta recortar.
        i, j = 0, len(segmentos) - 1
    else:
        n = len(segmentos)
        mejor = None
        mejor_score = -1.0
        j = 0
        acumulado = 0.0
        for i in range(n):
            if j < i:
                j = i
                acumulado = 0.0
            while j < n and (segmentos[j]["start"] + segmentos[j]["duration"]
                              - segmentos[i]["start"]) <= duracion_max:
                acumulado += scores[j]
                j += 1
            if j > i:
                dur_ventana = (segmentos[j - 1]["start"] + segmentos[j - 1]["duration"]
                                - segmentos[i]["start"])
                if dur_ventana >= duracion_min and acumulado > mejor_score:
                    mejor_score = acumulado
                    mejor = (i, j - 1)
            acumulado -= scores[i]

        if mejor is None:
            # Transcripcion muy corta o dispersa: usar desde el principio.
            i, j = 0, min(len(segmentos) - 1, max(0, n - 1))
        else:
            i, j = mejor

    inicio = segmentos[i]["start"]
    fin = segmentos[j]["start"] + segmentos[j]["duration"]
    # Red de seguridad: cualquiera sea el camino tomado arriba (incluido el
    # caso extremo de un unico segmento mas largo que duracion_max), la
    # ventana final nunca debe superar el limite pedido.
    if fin - inicio > duracion_max:
        fin = inicio + duracion_max
    ventana = segmentos[i:j + 1]

    return {
        "inicio": inicio,
        "fin": fin,
        "duracion": fin - inicio,
        "segmentos": ventana,
        "texto": " ".join(s["text"] for s in ventana),
    }


# ---------------------------------------------------------------------------
# 3. Reencuadre vertical (video horizontal centrado sobre fondo desenfocado)
# ---------------------------------------------------------------------------

def _blur_frame(frame: np.ndarray, fuerza: int = 61) -> np.ndarray:
    """Desenfoca un frame (numpy array HxWx3) con OpenCV (rapido, por frame)."""
    fuerza = fuerza if fuerza % 2 == 1 else fuerza + 1
    borroso = cv2.GaussianBlur(frame, (fuerza, fuerza), 0)
    # oscurecer un poco para que los subtitulos/texto resalten encima
    return (borroso.astype(np.float32) * 0.55).astype(np.uint8)


def _construir_fondo_desenfocado(clip: VideoFileClip):
    """Escala el clip para cubrir 1080x1920 (recortando sobrante) y lo desenfoca,
    para usar de fondo detras del video original centrado (sin barras negras)."""
    escala = max(ANCHO_V / clip.w, ALTO_V / clip.h)
    fondo = clip.fx(vfx.resize, escala)
    x_centro, y_centro = fondo.w / 2, fondo.h / 2
    fondo = vfx.crop(
        fondo, width=ANCHO_V, height=ALTO_V, x_center=x_centro, y_center=y_centro
    )
    fondo = fondo.fl_image(_blur_frame)
    return fondo


def _construir_primer_plano(clip: VideoFileClip):
    """Escala el clip original a lo ancho del reel (1080px), manteniendo su
    proporcion original (sin deformar ni recortar el contenido real)."""
    frente = clip.fx(vfx.resize, width=ANCHO_V)
    if frente.h > ALTO_V:
        frente = clip.fx(vfx.resize, height=ALTO_V)
    return frente.set_position("center")


# ---------------------------------------------------------------------------
# Subtitulos sincronizados con el video real
# ---------------------------------------------------------------------------

def _agrupar_segmentos_para_subtitulos(segmentos: list, palabras_por_grupo: int = 10) -> list:
    """
    Agrupa segmentos de transcripcion (que suelen ser muy cortos, 2-4
    palabras) en bloques de ~palabras_por_grupo palabras para que cada
    subtitulo en pantalla sea legible, conservando el tiempo real de inicio/fin.
    """
    grupos = []
    actual_textos = []
    actual_inicio = None
    actual_fin = None
    n_palabras = 0

    for seg in segmentos:
        texto = seg["text"].strip()
        if not texto:
            continue
        if actual_inicio is None:
            actual_inicio = seg["start"]
        actual_textos.append(texto)
        actual_fin = seg["start"] + seg["duration"]
        n_palabras += len(texto.split())

        termina_en_punto = bool(re.search(r"[.!?]$", texto))
        if n_palabras >= palabras_por_grupo or termina_en_punto:
            grupos.append({
                "inicio": actual_inicio,
                "fin": actual_fin,
                "texto": " ".join(actual_textos).strip(),
            })
            actual_textos, actual_inicio, actual_fin, n_palabras = [], None, None, 0

    if actual_textos:
        grupos.append({
            "inicio": actual_inicio,
            "fin": actual_fin,
            "texto": " ".join(actual_textos).strip(),
        })
    return grupos


def _clips_subtitulos_sincronizados(segmentos_ventana: list, offset: float, duracion_clip: float):
    grupos = _agrupar_segmentos_para_subtitulos(segmentos_ventana)
    clips = []
    for grupo in grupos:
        inicio_rel = max(0.0, grupo["inicio"] - offset)
        fin_rel = min(duracion_clip, grupo["fin"] - offset)
        dur_rel = fin_rel - inicio_rel
        if dur_rel <= 0.05:
            continue
        partes = _partir_si_es_larga(grupo["texto"])
        dur_parte = dur_rel / max(1, len(partes))
        for idx, parte in enumerate(partes):
            img = _frame_texto(parte, FONT_BOLD, 58, y_centro=int(ALTO_V * 0.82), max_ancho=940)
            clip_img = (
                ImageClip(np.array(img))
                .set_start(inicio_rel + idx * dur_parte)
                .set_duration(dur_parte)
                .crossfadein(min(0.15, dur_parte / 4))
            )
            clips.append(clip_img)
    return clips


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def _escribir_reel_desde_segmento(clip_original, highlight: dict,
                                   datos: dict, ruta_video: str,
                                   duracion_maxima: int, preset: str,
                                   fps: int,
                                   mostrar_subtitulos: bool = True) -> dict:
    """
    Genera y escribe un reel vertical a partir de un VideoFileClip ya abierto
    y un highlight detectado. No cierra clip_original (el llamador lo gestiona).

    Devuelve dict: {ruta_video, inicio, fin, duracion, texto_segmento, titulo}
    """
    fin_real = min(highlight["fin"], clip_original.duration)
    inicio_real = min(highlight["inicio"], max(0, fin_real - 1))
    fin_real = min(fin_real, inicio_real + duracion_maxima)

    subclip = clip_original.subclip(inicio_real, fin_real)
    duracion_clip = subclip.duration

    print("   -> Reencuadrando a vertical 9:16 (fondo desenfocado + video centrado)...")
    fondo = _construir_fondo_desenfocado(subclip).set_duration(duracion_clip)
    frente = _construir_primer_plano(subclip).set_duration(duracion_clip)

    titulo_img = _frame_texto(
        datos["titulo"], FONT_BOLD, 50, y_centro=110, max_ancho=980, max_lineas=2
    )
    titulo_clip = ImageClip(np.array(titulo_img)).set_duration(duracion_clip)

    if mostrar_subtitulos:
        print("   -> Generando subtitulos sincronizados con el video real...")
        clips_subs = _clips_subtitulos_sincronizados(
            highlight["segmentos"], offset=inicio_real, duracion_clip=duracion_clip
        )
    else:
        clips_subs = []

    video_final = None
    try:
        video_final = CompositeVideoClip(
            [fondo, frente, titulo_clip] + clips_subs,
            size=(ANCHO_V, ALTO_V),
        ).set_audio(subclip.audio).set_duration(duracion_clip)

        os.makedirs(os.path.dirname(ruta_video) or ".", exist_ok=True)
        slug_tmp = re.sub(r"[^a-z0-9]", "_", os.path.basename(ruta_video))[:30]
        temp_audio = os.path.join(
            tempfile.gettempdir(), f"_tmp_audio_{os.getpid()}_{slug_tmp}.m4a"
        )
        video_final.write_videofile(
            ruta_video, fps=fps, codec="libx264", audio_codec="aac",
            preset=preset, threads=4, logger=None,
            temp_audiofile=temp_audio, remove_temp=True,
        )
    finally:
        # Cerrar solo video_final; subclip es una vista de clip_original y lo
        # gestiona el llamador — cerrarlo aquí libera el lector de audio compartido
        # y rompe los shorts siguientes con 'NoneType has no attribute stdout'.
        if video_final is not None:
            try:
                video_final.close()
            except Exception:
                pass

    return {
        "ruta_video": ruta_video,
        "inicio": highlight["inicio"],
        "fin": highlight["fin"],
        "duracion": highlight["duracion"],
        "texto_segmento": highlight["texto"],
        "titulo": datos["titulo"],
    }


def detectar_mejores_segmentos(segmentos: list, n: int = 3,
                                duracion_objetivo: int = 45,
                                duracion_min: int = 20,
                                duracion_max: int = 59) -> list:
    """
    Encuentra los N mejores tramos NO solapados de la transcripcion.
    Devuelve lista de highlights ordenados por tiempo de inicio.

    Util para generar multiples shorts de un video largo.
    """
    if n <= 1:
        return [detectar_mejor_segmento(
            segmentos, duracion_objetivo, duracion_min, duracion_max
        )]

    resultados = []
    bloqueados = []  # [(inicio, fin), ...]

    for _ in range(n):
        disponibles = [
            s for s in segmentos
            if not any(
                s["start"] < fin and (s["start"] + s.get("duration", 0)) > inicio
                for inicio, fin in bloqueados
            )
        ]
        if not disponibles:
            break
        try:
            h = detectar_mejor_segmento(
                disponibles, duracion_objetivo, duracion_min, duracion_max
            )
        except ValueError:
            break
        resultados.append(h)
        bloqueados.append((h["inicio"], h["fin"]))

    resultados.sort(key=lambda x: x["inicio"])
    return resultados


def generar_reel_desde_clip(datos_youtube: dict, carpeta_salida: str, slug: str,
                             duracion_maxima: int = 59, carpeta_tmp: str = None,
                             ruta_video_local: str = None,
                             cookies_browser: str = None,
                             preset: str = "medium", fps: int = 30,
                             auto_segmento: bool = True,
                             mostrar_subtitulos: bool = True) -> dict:
    """
    Genera el reel recortando el video (YouTube o archivo local).

    datos_youtube:    dict de youtube_extractor o video_extractor
                      (debe incluir "segmentos" con marcas de tiempo).
    ruta_video_local: si se pasa, usa ese archivo en vez de descargar de YouTube.
    auto_segmento:    True -> detecta el tramo mas informativo automaticamente.
                      False -> usa el inicio del video (primeros duracion_maxima segundos).
    Devuelve dict:    {ruta_video, inicio, fin, duracion, texto_segmento, titulo}
    """
    segmentos = datos_youtube.get("segmentos") or []

    if auto_segmento:
        if not segmentos:
            raise ValueError(
                "No hay segmentos con marca de tiempo disponibles para este video "
                "(la transcripcion no trae timestamps)."
            )
        highlight = detectar_mejor_segmento(
            segmentos, duracion_objetivo=min(45, duracion_maxima),
            duracion_min=min(20, duracion_maxima), duracion_max=duracion_maxima,
        )
        print(f"   -> Mejor tramo detectado: {highlight['inicio']:.0f}s - "
              f"{highlight['fin']:.0f}s ({highlight['duracion']:.0f}s)")
    else:
        segs_ventana = [s for s in segmentos if s.get("start", 0) < duracion_maxima]
        highlight = {
            "inicio": 0.0,
            "fin": float(duracion_maxima),
            "duracion": float(duracion_maxima),
            "segmentos": segs_ventana,
            "texto": " ".join(s["text"] for s in segs_ventana),
        }
        print(f"   -> Sin recorte automático: usando inicio del video (hasta {duracion_maxima}s)")

    limpiar_origen = False
    if ruta_video_local:
        ruta_origen = ruta_video_local
    else:
        print("   -> Descargando video original (yt-dlp)...")
        ruta_origen = descargar_video(datos_youtube["url"], carpeta_tmp=carpeta_tmp,
                                      cookies_browser=cookies_browser)
        limpiar_origen = True

    ruta_video = os.path.join(carpeta_salida, f"{slug}_reel.mp4")
    clip_original = None
    try:
        clip_original = VideoFileClip(ruta_origen)
        resultado = _escribir_reel_desde_segmento(
            clip_original, highlight, datos_youtube, ruta_video,
            duracion_maxima, preset, fps, mostrar_subtitulos=mostrar_subtitulos,
        )
    finally:
        try:
            if clip_original is not None:
                clip_original.close()
        except Exception:
            pass
        if limpiar_origen:
            try:
                if os.path.isfile(ruta_origen):
                    os.remove(ruta_origen)
            except Exception:
                pass

    return resultado


def generar_multiples_reels_desde_clip(datos: dict, carpeta_salida: str,
                                        slug_base: str, n: int = 3,
                                        duracion_maxima: int = 59,
                                        carpeta_tmp: str = None,
                                        ruta_video_local: str = None,
                                        cookies_browser: str = None,
                                        preset: str = "medium",
                                        fps: int = 30,
                                        auto_segmento: bool = True,
                                        mostrar_subtitulos: bool = True) -> list:
    """
    Genera N shorts a partir de un video.

    datos:             dict con "titulo", "segmentos" y "url"
                       (formato de youtube_extractor o video_extractor).
    ruta_video_local:  Si se pasa, usa ese archivo local en vez de descargar
                       de YouTube (util para videos ya descargados o locales).
    auto_segmento:     True -> detecta N tramos no solapados automaticamente.
                       False -> divide en N segmentos consecutivos desde el inicio.

    Devuelve lista de dicts: [{ruta_video, inicio, fin, duracion, ...}, ...]
    """
    segmentos = datos.get("segmentos") or []

    if auto_segmento:
        if not segmentos:
            raise ValueError(
                "No hay segmentos con marca de tiempo. "
                "Asegurate de que la transcripcion incluya timestamps."
            )
        print(f"   -> Detectando los {n} mejores tramos no solapados...")
        highlights = detectar_mejores_segmentos(
            segmentos, n=n,
            duracion_objetivo=min(45, duracion_maxima),
            duracion_min=min(20, duracion_maxima),
            duracion_max=duracion_maxima,
        )
    else:
        print(f"   -> Sin recorte automático: dividiendo en {n} segmentos consecutivos...")
        highlights = []
        for i in range(n):
            inicio = i * float(duracion_maxima)
            fin = (i + 1) * float(duracion_maxima)
            segs_ventana = [s for s in segmentos
                            if s.get("start", 0) >= inicio and s.get("start", 0) < fin]
            highlights.append({
                "inicio": inicio,
                "fin": fin,
                "duracion": float(duracion_maxima),
                "segmentos": segs_ventana,
                "texto": " ".join(s["text"] for s in segs_ventana),
            })

    if not highlights:
        raise ValueError("No se pudieron detectar tramos validos en la transcripcion.")

    for i, h in enumerate(highlights, 1):
        print(f"   -> Short {i}: {h['inicio']:.0f}s - {h['fin']:.0f}s ({h['duracion']:.0f}s)")

    limpiar_origen = False
    if ruta_video_local:
        ruta_origen = ruta_video_local
        print(f"   -> Usando archivo local: {ruta_origen}")
    else:
        print("   -> Descargando video original (yt-dlp)...")
        ruta_origen = descargar_video(datos["url"], carpeta_tmp=carpeta_tmp,
                                      cookies_browser=cookies_browser)
        limpiar_origen = True

    resultados = []
    clip_original = None
    try:
        clip_original = VideoFileClip(ruta_origen)
        for i, highlight in enumerate(highlights, 1):
            suffix = f"_short{i}" if len(highlights) > 1 else "_reel"
            ruta_video = os.path.join(carpeta_salida, f"{slug_base}{suffix}.mp4")
            print(f"\n   [Short {i}/{len(highlights)}] Generando reel...")
            resultado = _escribir_reel_desde_segmento(
                clip_original, highlight, datos, ruta_video,
                duracion_maxima, preset, fps,
                mostrar_subtitulos=mostrar_subtitulos,
            )
            resultados.append(resultado)
            print(f"   -> Guardado: {ruta_video}")
    finally:
        try:
            if clip_original is not None:
                clip_original.close()
        except Exception:
            pass
        if limpiar_origen:
            try:
                if os.path.isfile(ruta_origen):
                    os.remove(ruta_origen)
            except Exception:
                pass

    return resultados


if __name__ == "__main__":
    import sys
    from youtube_extractor import extraer_youtube

    if len(sys.argv) < 2:
        print("Uso: python video_clipper.py <url_de_youtube>")
        sys.exit(1)

    datos = extraer_youtube(sys.argv[1])
    resultado = generar_reel_desde_clip(datos, "/tmp", "prueba_clip")
    print(resultado)
