"""
main.py
Orquestador del sistema: busca noticias -> extrae el articulo -> genera el guion
del reel -> genera el audio narrado -> genera el video vertical final (<=60s).

Uso basico:
    python3 main.py --tema tecnologia
    python3 main.py --tema "elecciones en argentina" --cantidad 3
    python3 main.py --variado          # mezcla varios temas (tecnologia, mundo, ciencia, etc.)
    python3 main.py --url https://ejemplo.com/articulo-1 --url https://ejemplo.com/articulo-2
                                        # genera un reel por cada link pasado directamente
    python3 main.py --archivo mi_articulo.txt
                                        # si el sitio bloquea la descarga automatica (bot
                                        # protection, login, JS), pega el articulo en un
                                        # .txt (ver formato en README) y usa esta opcion

    # --- NUEVAS FUNCIONES ---
    python3 main.py --youtube https://youtu.be/VIDEO_ID
                                        # recorta el tramo mas informativo del video real
                                        # (segun su transcripcion), lo reencuadra a vertical
                                        # y quema subtitulos sincronizados (no requiere API key)
    python3 main.py --youtube URL1 --youtube URL2
                                        # varios videos de YouTube en una sola corrida
    python3 main.py --youtube URL --modo-youtube narrado
                                        # (opcional) en vez de recortar el video real, genera
                                        # una narracion sintetica nueva sobre fondo generico
                                        # a partir de la transcripcion (comportamiento anterior)
    python3 main.py --trending-yt [--pais AR] [--cantidad 3]
                                        # busca los videos en tendencia en YouTube y genera
                                        # reels a partir de sus transcripciones
    python3 main.py --trending [--pais AR] [--cantidad 3]
                                        # busca temas en tendencia (Google Trends) y genera
                                        # reels con noticias sobre esos temas

Requisitos (ver requirements.txt): feedparser, requests, beautifulsoup4, gTTS,
moviepy==1.0.3, pillow, numpy, youtube-transcript-api. Necesita ffmpeg instalado.
"""

import argparse
import os
import re
import sys
import traceback

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from news_fetcher import buscar_noticias, buscar_variadas, CATEGORIAS
from article_extractor import extraer_texto, extraer_articulo
from summarizer import generar_guion_reel, generar_guion_reel_claude
from tts import generar_audio, duracion_audio
from video_builder import construir_video
from youtube_extractor import extraer_youtube
from trending_finder import buscar_trending_youtube, buscar_trending_noticias
from video_clipper import generar_reel_desde_clip, generar_multiples_reels_desde_clip
from video_extractor import transcribir_video_local
from music_analyzer import EXTS_VIDEO as _EXTS_VIDEO, EXTS_AUDIO as _EXTS_AUDIO
from image_pipeline import preparar_imagenes
from avatar_generator import generar_avatar, estado as avatar_estado

CARPETA_SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _slug(texto: str, max_len: int = 60) -> str:
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9áéíóúñ\s-]", "", texto)
    texto = re.sub(r"\s+", "-", texto.strip())
    return texto[:max_len] or "reel"


def _guardar_atribucion(slug: str, carpeta: str, noticia: dict,
                         atribucion: dict = None) -> dict:
    """
    Guarda los datos de atribución del artículo original junto al reel:
      - {slug}_fuente.json  → metadatos completos en JSON
      - {slug}_caption.txt  → texto listo para copiar como descripción del post
    Devuelve el dict de atribución guardado.
    """
    import json as _json
    from datetime import datetime, timezone

    at = atribucion or {}
    fuente_completa = {
        "titulo_original": noticia.get("titulo", ""),
        "fuente": noticia.get("fuente", ""),
        "url_original": noticia.get("link", ""),
        "autor": at.get("autor", ""),
        "fecha_publicacion": at.get("fecha_publicacion", ""),
        "descripcion": at.get("descripcion", "") or noticia.get("resumen", ""),
        "seccion": at.get("seccion", ""),
        "url_autor": at.get("url_autor", ""),
        "extraido_en": datetime.now(timezone.utc).isoformat(),
    }

    ruta_fuente = os.path.join(carpeta, f"{slug}_fuente.json")
    with open(ruta_fuente, "w", encoding="utf-8") as f:
        _json.dump(fuente_completa, f, ensure_ascii=False, indent=2)

    # Caption para YouTube — descripción lista para pegar en YouTube Studio
    titulo    = noticia.get("titulo", "")
    fuente    = fuente_completa.get("fuente", "")
    autor     = fuente_completa.get("autor", "")
    fecha_pub = fuente_completa.get("fecha_publicacion", "")[:10]
    seccion   = fuente_completa.get("seccion", "")
    url_orig  = fuente_completa.get("url_original", "")
    descripcion_art = fuente_completa.get("descripcion", "")

    # Hashtag de la fuente (sin espacios ni caracteres especiales)
    import re as _re
    fuente_tag = _re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚñÑ]", "", fuente) if fuente else ""

    lineas = [titulo, ""]

    if descripcion_art:
        lineas += [descripcion_art, ""]

    lineas.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lineas.append("📰 FUENTE ORIGINAL")
    if fuente:    lineas.append(f"Medio:     {fuente}")
    if autor:     lineas.append(f"Autor:     {autor}")
    if fecha_pub: lineas.append(f"Publicado: {fecha_pub}")
    if seccion:   lineas.append(f"Sección:   {seccion}")
    if url_orig:  lineas.append(f"🔗 {url_orig}")
    lineas.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    lineas += [
        "",
        "⚠️ Este vídeo es un resumen informativo. Los derechos del contenido",
        "original pertenecen al medio citado arriba.",
        "",
        "─────────────────────────────────",
        "🔔 SUSCRÍBETE para no perderte ninguna noticia verificada",
        "👍 Dale like si te ha resultado útil",
        "─────────────────────────────────",
        "",
        "#Noticias #UltimaHora #NoticiasVerificadas"
        + (f" #{fuente_tag}" if fuente_tag else ""),
    ]

    ruta_caption = os.path.join(carpeta, f"{slug}_caption.txt")
    with open(ruta_caption, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))

    print(f"   Atribución guardada: {ruta_fuente}")
    return fuente_completa


def procesar_noticia(noticia: dict, tema: str, carpeta_salida: str = CARPETA_SALIDA,
                      duracion_maxima: int = 60, texto_articulo: str = None,
                      tipo: str = "articulo", imagenes: list = None,
                      generar_imagenes_ai: bool = False,
                      servicio_ai: str = "pollinations",
                      atribucion: dict = None,
                      ruta_avatar_img: str = None,
                      servicio_avatar: str = "auto",
                      servicio_voz: str = "auto",
                      voz: str = None,
                      marca: str = None,
                      mostrar_titulo: bool = False,
                      mostrar_subtitulos: bool = True,
                      musica_fondo: str = None,
                      volumen_musica: float = 0.3,
                      volumen_voz: float = 1.0,
                      texto_personalizado: str = None) -> str:
    """
    Toma una noticia (dict con titulo/link/fuente/resumen) y genera el reel
    completo. Devuelve la ruta del mp4 generado.

    Si ya se tiene el texto completo del articulo (por ejemplo, porque vino de
    procesar_url()), se puede pasar en texto_articulo para no descargarlo dos
    veces.

    tipo: "video" para transcripciones de YouTube, "articulo" para noticias.
    """
    print(f"\n=== Procesando: {noticia['titulo']} ===")

    link = noticia.get("link", "")
    tiene_link_valido = bool(link and link.startswith("http"))

    if texto_articulo is None:
        if tiene_link_valido:
            print("-> Descargando articulo completo...")
            texto_articulo = extraer_texto(link)
        if not texto_articulo or len(texto_articulo.split()) < 30:
            print("   (no se pudo extraer suficiente texto, usando el resumen del RSS)")
            texto_articulo = noticia.get("resumen", "") or noticia["titulo"]
    elif len(texto_articulo.split()) < 50 and tiene_link_valido:
        # Texto pegado muy corto (ej: resumen RSS de Descubrir) → intentar artículo completo
        print("-> Texto muy corto, intentando descargar el artículo completo...")
        texto_completo = extraer_texto(link)
        if len(texto_completo.split()) > len(texto_articulo.split()):
            texto_articulo = texto_completo
            print(f"   Artículo descargado: {len(texto_articulo.split())} palabras")

    print("-> Generando guion del reel...")
    guion = generar_guion_reel_claude(noticia["titulo"], texto_articulo,
                                       noticia.get("fuente", ""), tipo=tipo)
    print(f"   Guion ({guion['palabras']} palabras, ~{guion['duracion_estimada_seg']}s):")
    print(f"   {guion['guion']}")

    os.makedirs(carpeta_salida, exist_ok=True)
    slug = _slug(noticia["titulo"])
    ruta_audio = os.path.join(carpeta_salida, f"{slug}_audio.mp3")
    ruta_video = os.path.join(carpeta_salida, f"{slug}_reel.mp4")
    ruta_guion = os.path.join(carpeta_salida, f"{slug}_guion.txt")

    with open(ruta_guion, "w", encoding="utf-8") as f:
        f.write(f"Titulo: {noticia['titulo']}\n")
        f.write(f"Fuente: {noticia.get('fuente', '')}\n")
        f.write(f"Link: {noticia['link']}\n\n")
        f.write(guion["guion"])

    print("-> Generando audio narrado...")
    ruta_audio = generar_audio(guion["guion"], ruta_audio, servicio=servicio_voz, voz=voz)
    dur = duracion_audio(ruta_audio)
    print(f"   Audio generado: {ruta_audio} ({dur:.1f}s)")

    # Pipeline de imágenes
    import tempfile
    carpeta_imgs = tempfile.mkdtemp(prefix="_imgs_")
    url_art = noticia.get("link") if not (noticia.get("link") or "").startswith("/") else None
    imgs_fondo = preparar_imagenes(
        titulo=noticia["titulo"],
        url_articulo=url_art,
        texto_articulo=texto_articulo or "",
        rutas_usuario=imagenes or [],
        generar_ai=generar_imagenes_ai,
        n_ai=3,
        servicio_ai=servicio_ai,
        carpeta_tmp=carpeta_imgs,
    )

    # Avatar hablando (lip sync)
    ruta_avatar_video = None
    if ruta_avatar_img and os.path.isfile(ruta_avatar_img):
        ruta_avatar_video = os.path.join(carpeta_imgs, "avatar_talking.mp4")
        print("-> Generando avatar hablando (lip sync)...")
        ruta_avatar_video = generar_avatar(
            ruta_imagen=ruta_avatar_img,
            ruta_audio=ruta_audio,
            ruta_salida=ruta_avatar_video,
            servicio=servicio_avatar,
        )
        if ruta_avatar_video:
            print(f"   Avatar generado: {ruta_avatar_video}")
        else:
            print("   [WARN] No se pudo generar avatar, continuando sin él.")

    print("-> Generando video vertical...")
    construir_video(guion, ruta_audio, ruta_video, tema=tema, duracion_maxima=duracion_maxima,
                    imagenes=imgs_fondo if imgs_fondo else None,
                    ruta_avatar=ruta_avatar_video,
                    marca=marca,
                    mostrar_titulo=mostrar_titulo,
                    mostrar_subtitulos=mostrar_subtitulos,
                    musica_fondo=musica_fondo,
                    volumen_musica=volumen_musica,
                    volumen_voz=volumen_voz,
                    texto_personalizado=texto_personalizado)
    print(f"   Video generado: {ruta_video}")

    # Guardar atribución de la fuente original
    _guardar_atribucion(slug, carpeta_salida, noticia, atribucion)

    # Limpiar imágenes temporales
    import shutil
    try:
        shutil.rmtree(carpeta_imgs, ignore_errors=True)
    except Exception:
        pass

    return ruta_video


def procesar_url(url: str, tema: str = "default", carpeta_salida: str = CARPETA_SALIDA,
                  duracion_maxima: int = 60, imagenes: list = None,
                  generar_imagenes_ai: bool = False, servicio_ai: str = "pollinations",
                  ruta_avatar_img: str = None, servicio_avatar: str = "auto",
                  servicio_voz: str = "auto", voz: str = None,
                  marca: str = None, mostrar_titulo: bool = False,
                  mostrar_subtitulos: bool = True,
                  musica_fondo: str = None, volumen_musica: float = 0.3,
                  volumen_voz: float = 1.0, texto_personalizado: str = None) -> str:
    """
    Version de procesar_noticia() para cuando el usuario pega un link de
    articulo directamente (no viene de una busqueda por RSS). Descarga la
    pagina, extrae titulo/fuente/texto, y corre el mismo pipeline.
    """
    print(f"\n=== Procesando link: {url} ===")
    print("-> Descargando y leyendo el articulo...")
    try:
        articulo = extraer_articulo(url)
    except Exception as e:
        raise RuntimeError(
            f"No se pudo descargar {url} ({e}). Algunos sitios bloquean las "
            "peticiones automaticas (proteccion anti-bots, login, contenido "
            "cargado con JavaScript). Alternativa: copia el titulo y el texto "
            "del articulo a un .txt (ver formato en el README) y usa "
            "'--archivo tu_archivo.txt' en vez de '--url'."
        ) from e

    if len(articulo["texto"].split()) < 30:
        raise ValueError(
            f"No se pudo extraer suficiente texto de {url}. "
            "Puede que el sitio bloquee la descarga automatica o que el "
            "contenido se cargue con JavaScript. Alternativa: copia el titulo "
            "y el texto del articulo a un .txt (ver formato en el README) y "
            "usa '--archivo tu_archivo.txt' en vez de '--url'."
        )

    noticia = {
        "titulo": articulo["titulo"],
        "link": articulo["link"],
        "fuente": articulo["fuente"],
        "resumen": "",
    }
    atribucion = {
        "autor": articulo.get("autor", ""),
        "fecha_publicacion": articulo.get("fecha_publicacion", ""),
        "descripcion": articulo.get("descripcion", ""),
        "seccion": articulo.get("seccion", ""),
        "url_autor": articulo.get("url_autor", ""),
    }
    if any(atribucion.values()):
        print(f"   Autor: {atribucion['autor'] or '(no detectado)'}  "
              f"Fecha: {atribucion['fecha_publicacion'][:10] if atribucion['fecha_publicacion'] else '(no detectada)'}")
    print(f"   Titulo detectado: {noticia['titulo']}  (fuente: {noticia['fuente']})")
    return procesar_noticia(noticia, tema, carpeta_salida=carpeta_salida,
                             duracion_maxima=duracion_maxima,
                             texto_articulo=articulo["texto"],
                             imagenes=imagenes,
                             generar_imagenes_ai=generar_imagenes_ai,
                             servicio_ai=servicio_ai,
                             atribucion=atribucion,
                             ruta_avatar_img=ruta_avatar_img,
                             servicio_avatar=servicio_avatar,
                             servicio_voz=servicio_voz,
                             voz=voz,
                             marca=marca,
                             mostrar_titulo=mostrar_titulo,
                             mostrar_subtitulos=mostrar_subtitulos,
                             musica_fondo=musica_fondo,
                             volumen_musica=volumen_musica,
                             volumen_voz=volumen_voz,
                             texto_personalizado=texto_personalizado)


def procesar_youtube(url: str, carpeta_salida: str = CARPETA_SALIDA,
                     duracion_maxima: int = 60, modo: str = "clip",
                     cantidad_shorts: int = 1,
                     cookies_browser: str = None,
                     auto_segmento: bool = True,
                     mostrar_subtitulos: bool = True) -> list:
    """
    Genera uno o varios reels a partir de un video de YouTube.

    modo:
      "clip"    (default) -> descarga el video real, detecta el/los tramos mas
                 informativos, los recorta y reencuadra a vertical con
                 subtitulos sincronizados. Si falla, cae a modo "narrado".
      "narrado" -> genera un video sintetico narrado con TTS sobre fondo
                 generico, a partir de la transcripcion.

    cantidad_shorts: cuantos shorts generar del mismo video (default: 1).
                     Con >1 detecta tramos no solapados y genera un .mp4 por cada uno.

    Devuelve lista de rutas de videos generados.
    """
    print(f"\n=== Procesando video de YouTube: {url} ===")
    try:
        datos = extraer_youtube(url)
    except Exception as e:
        raise RuntimeError(
            f"No se pudo procesar el video de YouTube: {e}"
        ) from e

    if len(datos["texto"].split()) < 30:
        raise ValueError(
            "La transcripcion del video es demasiado corta para generar un reel. "
            "Asegurate de que el video tenga subtitulos habilitados."
        )

    fuente = datos["canal"] or "YouTube"
    print(f"   Titulo: {datos['titulo']}  (canal: {fuente})")

    if modo == "clip":
        try:
            os.makedirs(carpeta_salida, exist_ok=True)
            slug = _slug(datos["titulo"])

            if cantidad_shorts > 1:
                resultados = generar_multiples_reels_desde_clip(
                    datos, carpeta_salida, slug,
                    n=cantidad_shorts, duracion_maxima=duracion_maxima,
                    cookies_browser=cookies_browser,
                    auto_segmento=auto_segmento,
                    mostrar_subtitulos=mostrar_subtitulos,
                )
            else:
                r = generar_reel_desde_clip(
                    datos, carpeta_salida, slug, duracion_maxima=duracion_maxima,
                    cookies_browser=cookies_browser,
                    auto_segmento=auto_segmento,
                    mostrar_subtitulos=mostrar_subtitulos,
                )
                resultados = [r]

            rutas = []
            for i, resultado in enumerate(resultados, 1):
                sufijo = f"_short{i}" if len(resultados) > 1 else ""
                ruta_info = os.path.join(carpeta_salida, f"{slug}{sufijo}_info.txt")
                with open(ruta_info, "w", encoding="utf-8") as f:
                    f.write(f"Titulo: {resultado['titulo']}\n")
                    f.write(f"Canal: {fuente}\n")
                    f.write(f"Link: {datos['url']}\n")
                    f.write(f"Tramo recortado: {resultado['inicio']:.0f}s - "
                            f"{resultado['fin']:.0f}s ({resultado['duracion']:.0f}s)\n\n")
                    f.write(resultado["texto_segmento"])
                print(f"   Video generado: {resultado['ruta_video']}")
                rutas.append(resultado["ruta_video"])
            return rutas
        except Exception as e:
            print(f"[WARN] Modo 'clip' fallo ({e}). Intentando modo musica (deteccion de coro)...")
            try:
                ruta = procesar_musica(
                    url,
                    carpeta_salida=carpeta_salida,
                    duracion_maxima=duracion_maxima,
                    cookies_browser=cookies_browser,
                )
                return [ruta]
            except Exception as e2:
                print(f"[WARN] Modo musica tambien fallo ({e2}). Usando modo narrado como ultimo recurso...")

    noticia = {
        "titulo": datos["titulo"],
        "link": datos["url"],
        "fuente": fuente,
        "resumen": "",
    }
    ruta = procesar_noticia(
        noticia, tema="youtube", carpeta_salida=carpeta_salida,
        duracion_maxima=duracion_maxima, texto_articulo=datos["texto"],
        tipo="video",
    )
    return [ruta]


def procesar_video_local(ruta: str, carpeta_salida: str = CARPETA_SALIDA,
                          duracion_maxima: int = 60, cantidad_shorts: int = 1,
                          modelo_whisper: str = "base",
                          idioma_whisper: str = "es") -> list:
    """
    Genera uno o varios reels a partir de un archivo de video local.
    Usa Whisper para transcribir el audio con marcas de tiempo.

    Devuelve lista de rutas de videos generados.
    """
    print(f"\n=== Procesando video local: {ruta} ===")
    datos = transcribir_video_local(ruta, modelo=modelo_whisper, idioma=idioma_whisper)

    if len(datos["texto"].split()) < 30:
        raise ValueError(
            "La transcripcion es demasiado corta. Verifica que el video tenga "
            "audio con voz y que ffmpeg este instalado."
        )

    os.makedirs(carpeta_salida, exist_ok=True)
    slug = _slug(datos["titulo"])

    if cantidad_shorts > 1:
        resultados = generar_multiples_reels_desde_clip(
            datos, carpeta_salida, slug,
            n=cantidad_shorts, duracion_maxima=duracion_maxima,
            ruta_video_local=ruta,
        )
    else:
        r = generar_reel_desde_clip(
            datos, carpeta_salida, slug,
            duracion_maxima=duracion_maxima,
            ruta_video_local=ruta,
        )
        resultados = [r]

    rutas = []
    for i, resultado in enumerate(resultados, 1):
        sufijo = f"_short{i}" if len(resultados) > 1 else ""
        ruta_info = os.path.join(carpeta_salida, f"{slug}{sufijo}_info.txt")
        with open(ruta_info, "w", encoding="utf-8") as f:
            f.write(f"Titulo: {resultado['titulo']}\n")
            f.write(f"Fuente: local\n")
            f.write(f"Archivo: {ruta}\n")
            f.write(f"Tramo recortado: {resultado['inicio']:.0f}s - "
                    f"{resultado['fin']:.0f}s ({resultado['duracion']:.0f}s)\n\n")
            f.write(resultado["texto_segmento"])
        print(f"   Video generado: {resultado['ruta_video']}")
        rutas.append(resultado["ruta_video"])
    return rutas


def procesar_musica(fuente: str, carpeta_salida: str = CARPETA_SALIDA,
                     duracion_maxima: int = 60, ruta_letra: str = None,
                     artista: str = None, cookies_browser: str = None,
                     mostrar_nombre: bool = False) -> str:
    """
    Genera un reel musical a partir de:
      - URL de YouTube (video musical)
      - Video local (.mp4, .mov, ...)
      - Audio local (.mp3, .wav, .flac, ...)

    Detecta el coro/hook automaticamente con librosa.
    Si se pasa ruta_letra (.txt), muestra la letra sincronizada.
    Devuelve la ruta del .mp4 generado.
    """
    from music_analyzer import detectar_coro
    from music_video_builder import (
        construir_reel_musical_desde_video,
        construir_reel_musical_desde_audio,
        parsear_letra,
    )

    print(f"\n=== Procesando musica: {fuente} ===")

    lineas_letra = []
    if ruta_letra:
        if not os.path.isfile(ruta_letra):
            raise FileNotFoundError(f"No se encontro el archivo de letra: {ruta_letra}")
        lineas_letra = parsear_letra(ruta_letra)
        print(f"   -> {len(lineas_letra)} lineas de letra cargadas desde {ruta_letra}")

    es_youtube = bool(re.search(r"youtu(\.be|be\.com)/", fuente))
    ext = os.path.splitext(fuente)[1].lower()
    es_video_local = not es_youtube and ext in _EXTS_VIDEO
    es_audio_local = not es_youtube and ext in _EXTS_AUDIO

    if not es_youtube and not es_video_local and not es_audio_local:
        raise ValueError(
            f"Fuente no reconocida: '{fuente}'. Debe ser una URL de YouTube, "
            "un video local (.mp4, .mov, ...) o un audio (.mp3, .wav, .flac, ...)."
        )

    titulo = ""
    artista_display = artista or ""
    ruta_media = None
    limpiar_media = False

    if es_youtube:
        from youtube_extractor import _video_id_desde_url, _metadata_desde_pagina
        from video_clipper import descargar_video
        import tempfile

        video_id = _video_id_desde_url(fuente)
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        print("   -> Obteniendo metadatos...")
        meta = _metadata_desde_pagina(watch_url)
        titulo = meta.get("titulo", "") or f"Video {video_id}"
        artista_display = artista or meta.get("canal", "")

        print("   -> Descargando video (yt-dlp)...")
        ruta_media = descargar_video(fuente, carpeta_tmp=tempfile.gettempdir(),
                                     cookies_browser=cookies_browser)
        limpiar_media = True
        es_video_local = True

    elif es_video_local:
        titulo = os.path.splitext(os.path.basename(fuente))[0]
        ruta_media = fuente

    else:
        titulo = os.path.splitext(os.path.basename(fuente))[0]
        ruta_media = fuente

    try:
        highlight = detectar_coro(
            ruta_media,
            duracion_objetivo=min(45, duracion_maxima),
            duracion_min=min(20, duracion_maxima),
            duracion_max=duracion_maxima,
        )
    except Exception:
        if limpiar_media and ruta_media and os.path.isfile(ruta_media):
            try:
                os.remove(ruta_media)
            except Exception:
                pass
        raise

    print(f"   -> Coro/hook detectado: {highlight['inicio']:.1f}s - "
          f"{highlight['fin']:.1f}s ({highlight['duracion']:.1f}s)")

    os.makedirs(carpeta_salida, exist_ok=True)
    slug = _slug(titulo)
    ruta_salida = os.path.join(carpeta_salida, f"{slug}_music_reel.mp4")

    try:
        titulo_mostrar = titulo if mostrar_nombre else ""
        artista_mostrar = artista_display if mostrar_nombre else ""
        if es_video_local:
            construir_reel_musical_desde_video(
                ruta_media, highlight["inicio"], highlight["fin"],
                titulo_mostrar, artista_mostrar, lineas_letra, ruta_salida,
                mostrar_cabecera=mostrar_nombre,
            )
        else:
            construir_reel_musical_desde_audio(
                ruta_media, highlight["inicio"], highlight["fin"],
                titulo_mostrar, artista_mostrar, lineas_letra, ruta_salida,
                mostrar_cabecera=mostrar_nombre,
            )
    finally:
        if limpiar_media and ruta_media and os.path.isfile(ruta_media):
            try:
                os.remove(ruta_media)
            except Exception:
                pass

    print(f"   Video generado: {ruta_salida}")
    return ruta_salida


def leer_articulo_desde_archivo(ruta: str) -> dict:
    """
    Lee un articulo pegado manualmente en un .txt con este formato:

        TITULO: El titulo de la noticia
        FUENTE: Nombre del sitio (opcional)
        LINK: https://... (opcional)

        Aca va el cuerpo completo del articulo, tantos parrafos como quieras.

    Util cuando un sitio bloquea la descarga automatica (proteccion anti-bots,
    login, contenido cargado con JavaScript): copias el articulo a mano y se
    lo pasas a este archivo en vez de usar --url.
    """
    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read()

    titulo, fuente, link = "", "", ""
    lineas = contenido.splitlines()
    idx_cuerpo = 0
    for i, linea in enumerate(lineas):
        if linea.upper().startswith("TITULO:"):
            titulo = linea.split(":", 1)[1].strip()
        elif linea.upper().startswith("FUENTE:"):
            fuente = linea.split(":", 1)[1].strip()
        elif linea.upper().startswith("LINK:"):
            link = linea.split(":", 1)[1].strip()
        elif linea.strip() == "" and titulo:
            idx_cuerpo = i + 1
            break

    texto = "\n".join(lineas[idx_cuerpo:]).strip()

    if not titulo:
        raise ValueError(
            f"El archivo {ruta} no tiene una linea 'TITULO: ...' al principio. "
            "Revisa el formato esperado en el README."
        )
    if len(texto.split()) < 3:
        raise ValueError(
            f"El archivo {ruta} no tiene suficiente texto de articulo despues "
            "del encabezado (TITULO/FUENTE/LINK + linea en blanco)."
        )

    return {"titulo": titulo, "fuente": fuente, "link": link or ruta, "texto": texto}


def procesar_archivo(ruta: str, tema: str = "default", carpeta_salida: str = CARPETA_SALIDA,
                      duracion_maxima: int = 60, imagenes: list = None,
                      generar_imagenes_ai: bool = False, servicio_ai: str = "pollinations",
                      ruta_avatar_img: str = None, servicio_avatar: str = "auto",
                      servicio_voz: str = "auto", voz: str = None,
                      marca: str = None, mostrar_titulo: bool = False,
                      mostrar_subtitulos: bool = True,
                      musica_fondo: str = None, volumen_musica: float = 0.3,
                      volumen_voz: float = 1.0, texto_personalizado: str = None) -> str:
    """Genera el reel a partir de un articulo pegado manualmente en un .txt."""
    print(f"\n=== Procesando archivo: {ruta} ===")
    articulo = leer_articulo_desde_archivo(ruta)
    print(f"   Titulo: {articulo['titulo']}  (fuente: {articulo['fuente'] or '-'})")

    noticia = {
        "titulo": articulo["titulo"],
        "link": articulo["link"],
        "fuente": articulo["fuente"],
        "resumen": "",
    }
    return procesar_noticia(noticia, tema, carpeta_salida=carpeta_salida,
                             duracion_maxima=duracion_maxima,
                             texto_articulo=articulo["texto"],
                             imagenes=imagenes,
                             generar_imagenes_ai=generar_imagenes_ai,
                             servicio_ai=servicio_ai,
                             ruta_avatar_img=ruta_avatar_img,
                             servicio_avatar=servicio_avatar,
                             servicio_voz=servicio_voz,
                             voz=voz,
                             marca=marca,
                             mostrar_titulo=mostrar_titulo,
                             mostrar_subtitulos=mostrar_subtitulos,
                             musica_fondo=musica_fondo,
                             volumen_musica=volumen_musica,
                             volumen_voz=volumen_voz,
                             texto_personalizado=texto_personalizado)


def main():
    parser = argparse.ArgumentParser(
        description="Genera reels de noticias automaticamente (busqueda + guion + TTS + video)."
    )
    # --- Modos de entrada ---
    parser.add_argument("--tema", type=str, default=None,
                        help=f"Tema a buscar. Categorias predefinidas: {list(CATEGORIAS.keys())}, "
                             f"o cualquier texto libre.")
    parser.add_argument("--variado", action="store_true",
                        help="Mezcla varias categorias predefinidas en vez de un solo tema.")
    parser.add_argument("--url", action="append", default=None,
                        help="Link a un articulo especifico. Se puede repetir.")
    parser.add_argument("--archivo", action="append", default=None,
                        help="Ruta a un .txt con un articulo pegado a mano (ver README).")
    # --- Modo musica ---
    parser.add_argument("--musica", action="append", default=None, metavar="URL_O_RUTA",
                        help="URL de YouTube o ruta local (video .mp4 o audio .mp3/.wav/...) "
                             "para generar un reel musical. Detecta el coro/hook "
                             "automaticamente con librosa. Se puede repetir.")
    parser.add_argument("--letra", default=None, metavar="RUTA_TXT",
                        help="Archivo .txt con la letra de la cancion (una linea por verso). "
                             "Se muestra sincronizada en el reel. Se usa con --musica.")
    parser.add_argument("--artista", default=None,
                        help="Nombre del artista a mostrar en el reel musical.")
    parser.add_argument("--cookies-browser",
                        choices=["chrome", "safari", "firefox", "edge",
                                 "chromium", "brave", "opera", "vivaldi"],
                        default=None, metavar="NAVEGADOR",
                        help="Navegador del que leer las cookies para autenticar "
                             "la descarga de YouTube (bypass de restricciones de "
                             "edad/region). Valores: chrome, safari, firefox, edge, "
                             "brave... Se usa con --youtube y --musica.")
    # --- Nuevos modos ---
    parser.add_argument("--youtube", action="append", default=None, metavar="URL",
                        help="URL de un video de YouTube. Genera un reel recortando el "
                             "tramo mas informativo del video real (sin API key). "
                             "Se puede repetir.")
    parser.add_argument("--video", action="append", default=None, metavar="RUTA",
                        help="Ruta a un video local (mp4, mov, avi...). Transcribe con "
                             "Whisper y genera uno o varios shorts. Requiere: "
                             "pip install openai-whisper")
    parser.add_argument("--modo-youtube", choices=["clip", "narrado"], default="clip",
                        help="'clip' (default): recorta el video real y reencuadra a "
                             "vertical. 'narrado': genera un video sintetico narrado a "
                             "partir de la transcripcion (comportamiento anterior). Se "
                             "usa con --youtube y --trending-yt.")
    parser.add_argument("--cantidad-shorts", type=int, default=1, metavar="N",
                        help="Cuantos shorts generar por video (default: 1). Con N>1 "
                             "detecta N tramos no solapados y genera un .mp4 por cada uno. "
                             "Se usa con --youtube y --video.")
    parser.add_argument("--whisper-modelo", default="base",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Modelo Whisper para transcribir videos locales "
                             "(default: base). Mas grande = mejor calidad, mas lento.")
    parser.add_argument("--whisper-idioma", default="es",
                        help="Idioma para Whisper (default: es). Usa 'auto' para "
                             "deteccion automatica.")
    # --- Imágenes de fondo ---
    parser.add_argument("--imagen", action="append", default=None, metavar="RUTA",
                        help="Ruta a una imagen para usar como fondo del video. "
                             "Se puede repetir para hacer un slideshow.")
    parser.add_argument("--generar-imagenes-ai", action="store_true",
                        help="Genera imágenes de fondo con IA (Pollinations.ai, gratis).")
    parser.add_argument("--servicio-ai", default="pollinations",
                        choices=["pollinations", "pexels", "unsplash", "pixabay"],
                        help="Servicio para imágenes de fondo (default: pollinations). "
                             "pexels/unsplash/pixabay buscan fotos reales y requieren API key.")
    # --- Avatar hablando (lip sync) ---
    parser.add_argument("--avatar", default=None, metavar="RUTA_IMAGEN",
                        help="Ruta a una foto del avatar (cara) para animar con lip sync. "
                             "Requiere SadTalker instalado (bash setup_sadtalker.sh) o DID_API_KEY.")
    parser.add_argument("--avatar-servicio", default="auto",
                        choices=["auto", "sadtalker", "did"],
                        help="Servicio de lip sync: 'auto' (D-ID si hay key, si no SadTalker), "
                             "'sadtalker' (local), 'did' (cloud, requiere DID_API_KEY).")
    # --- Voz TTS ---
    parser.add_argument("--servicio-voz", default="auto",
                        choices=["auto", "elevenlabs", "edge-tts"],
                        help="Motor TTS: 'auto' (ElevenLabs si hay key, si no edge-tts), "
                             "'elevenlabs' (premium, requiere ELEVENLABS_API_KEY), 'edge-tts' (gratis).")
    parser.add_argument("--voz", default=None,
                        help="Nombre de voz para edge-tts (ej: es-ES-AlvaroNeural) o "
                             "voice_id de ElevenLabs.")
    parser.add_argument("--sin-titulo", action="store_true",
                        help="No muestra el título en el video (solo en el nombre del archivo)")
    parser.add_argument("--sin-subtitulos", action="store_true",
                        help="No muestra subtítulos karaoke en el video")
    parser.add_argument("--musica-fondo", default=None, metavar="RUTA",
                        help="Ruta a un archivo de música (MP3, WAV, etc.) para mezclar como "
                             "fondo del reel. El audio narrado suena encima de la música.")
    parser.add_argument("--volumen-musica", type=float, default=0.3, metavar="0.0-1.0",
                        help="Volumen de la música de fondo (0.0=silencio, 1.0=máximo). "
                             "Por defecto: 0.3")
    parser.add_argument("--volumen-voz", type=float, default=1.0, metavar="0.0-1.0",
                        help="Volumen de la voz narrada (0.0=silencio, 1.0=máximo). "
                             "Por defecto: 1.0")
    parser.add_argument("--marca", default=None, metavar="TEXTO",
                        help="Texto de marca/watermark en el video (ej: '@micanal'). "
                             "Si no se indica, no aparece ninguna marca.")
    parser.add_argument("--texto-personalizado", default=None, metavar="TEXTO",
                        help="Texto adicional que aparece en el video (ej: nombre de canción, "
                             "fuente, subtítulo libre). Solo se muestra si se indica.")
    parser.add_argument("--auto-segmento-youtube", action="store_true",
                        help="Activa la detección automática del mejor segmento en modo YouTube. "
                             "Por defecto desactivado (usa el inicio del video).")
    parser.add_argument("--mostrar-nombre-musica", action="store_true",
                        help="Muestra el nombre de la canción y el artista en el reel musical. "
                             "Por defecto desactivado.")
    parser.add_argument("--trending-yt", action="store_true",
                        help="Busca los videos en tendencia en YouTube y genera reels a "
                             "partir de sus transcripciones.")
    parser.add_argument("--trending", action="store_true",
                        help="Busca temas en tendencia via Google Trends y genera reels "
                             "con noticias sobre esos temas.")
    parser.add_argument("--pais", type=str, default="AR",
                        help="Pais para tendencias (codigo ISO: AR, US, ES, MX, CO ...). "
                             "Se usa con --trending y --trending-yt. Por defecto: AR.")
    # --- Opciones generales ---
    parser.add_argument("--cantidad", type=int, default=1,
                        help="Cuantos items procesar (una por reel). Por defecto: 1.")
    parser.add_argument("--duracion-maxima", type=int, default=60,
                        help="Duracion maxima del video en segundos. Por defecto: 60.")
    args = parser.parse_args()

    generados = []

    # ---- Modo: Musica ----
    if args.musica:
        for fuente in args.musica:
            try:
                ruta = procesar_musica(
                    fuente,
                    duracion_maxima=args.duracion_maxima,
                    ruta_letra=args.letra,
                    artista=args.artista,
                    cookies_browser=args.cookies_browser,
                    mostrar_nombre=args.mostrar_nombre_musica,
                )
                generados.append(ruta)
            except Exception:
                print(f"[ERROR] Fallo al procesar musica '{fuente}':")
                traceback.print_exc()

        print("\n=== Listo ===")
        for r in generados:
            print(" -", r)
        return

    # ---- Modo 1: URLs de articulos y/o archivos de texto ----
    if args.url or args.archivo:
        for link in (args.url or []):
            try:
                ruta = procesar_url(link, tema="default", duracion_maxima=args.duracion_maxima,
                                    imagenes=args.imagen,
                                    generar_imagenes_ai=args.generar_imagenes_ai,
                                    servicio_ai=args.servicio_ai,
                                    ruta_avatar_img=args.avatar,
                                    servicio_avatar=args.avatar_servicio,
                                    servicio_voz=args.servicio_voz,
                                    voz=args.voz,
                                    marca=args.marca,
                                    mostrar_titulo=not args.sin_titulo,
                                    mostrar_subtitulos=not args.sin_subtitulos,
                                    musica_fondo=args.musica_fondo,
                                    volumen_musica=args.volumen_musica,
                                    volumen_voz=args.volumen_voz,
                                    texto_personalizado=args.texto_personalizado)
                generados.append(ruta)
            except Exception:
                print(f"[ERROR] Fallo al procesar el link '{link}':")
                traceback.print_exc()

        for ruta_archivo in (args.archivo or []):
            try:
                ruta = procesar_archivo(ruta_archivo, tema="default",
                                        duracion_maxima=args.duracion_maxima,
                                        imagenes=args.imagen,
                                        generar_imagenes_ai=args.generar_imagenes_ai,
                                        servicio_ai=args.servicio_ai,
                                        ruta_avatar_img=args.avatar,
                                        servicio_avatar=args.avatar_servicio,
                                        servicio_voz=args.servicio_voz,
                                        voz=args.voz,
                                        marca=args.marca,
                                        mostrar_titulo=not args.sin_titulo,
                                        mostrar_subtitulos=not args.sin_subtitulos,
                                        musica_fondo=args.musica_fondo,
                                        volumen_musica=args.volumen_musica,
                                        volumen_voz=args.volumen_voz,
                                        texto_personalizado=args.texto_personalizado)
                generados.append(ruta)
            except Exception:
                print(f"[ERROR] Fallo al procesar el archivo '{ruta_archivo}':")
                traceback.print_exc()

        print("\n=== Listo ===")
        for r in generados:
            print(" -", r)
        return

    # ---- Modo 2: Videos de YouTube (URLs directas) ----
    if args.youtube:
        for yt_url in args.youtube:
            try:
                rutas = procesar_youtube(
                    yt_url, duracion_maxima=args.duracion_maxima,
                    modo=args.modo_youtube,
                    cantidad_shorts=args.cantidad_shorts,
                    cookies_browser=args.cookies_browser,
                    auto_segmento=args.auto_segmento_youtube,
                    mostrar_subtitulos=not args.sin_subtitulos,
                )
                generados.extend(rutas)
            except Exception:
                print(f"[ERROR] Fallo al procesar el video de YouTube '{yt_url}':")
                traceback.print_exc()

        print("\n=== Listo ===")
        for r in generados:
            print(" -", r)
        return

    # ---- Modo 3: Videos locales (con Whisper) ----
    if args.video:
        for ruta_video in args.video:
            try:
                rutas = procesar_video_local(
                    ruta_video,
                    duracion_maxima=args.duracion_maxima,
                    cantidad_shorts=args.cantidad_shorts,
                    modelo_whisper=args.whisper_modelo,
                    idioma_whisper=args.whisper_idioma,
                )
                generados.extend(rutas)
            except Exception:
                print(f"[ERROR] Fallo al procesar el video local '{ruta_video}':")
                traceback.print_exc()

        print("\n=== Listo ===")
        for r in generados:
            print(" -", r)
        return

    # ---- Modo 4: Videos en tendencia de YouTube ----
    if args.trending_yt:
        print(f"\n=== Buscando videos en tendencia de YouTube ({args.pais}) ===")
        videos = buscar_trending_youtube(pais=args.pais, max_resultados=args.cantidad * 3)
        if not videos:
            print("No se encontraron videos en tendencia. Revisa tu conexion a internet.")
            sys.exit(1)

        procesados = 0
        for video in videos:
            if procesados >= args.cantidad:
                break
            try:
                ruta = procesar_youtube(
                    video["url"], duracion_maxima=args.duracion_maxima,
                    modo=args.modo_youtube,
                )
                generados.append(ruta)
                procesados += 1
            except Exception:
                print(f"[WARN] No se pudo procesar '{video['titulo']}' (sin transcripcion o error), pasando al siguiente...")
                traceback.print_exc()
                continue

        if not generados:
            print("[ERROR] Ningun video trending tenia transcripcion disponible.")
            sys.exit(1)

        print("\n=== Listo ===")
        for r in generados:
            print(" -", r)
        return

    # ---- Modo 5: Noticias sobre temas en tendencia (Google Trends) ----
    if args.trending:
        print(f"\n=== Buscando noticias trending ({args.pais}) ===")
        pool = buscar_trending_noticias(pais=args.pais, max_resultados=max(args.cantidad, 5))
        if not pool:
            print("No se encontraron noticias trending. Revisa tu conexion a internet.")
            sys.exit(1)

        for noticia in pool[: args.cantidad]:
            tema_tendencia = noticia.get("tema_tendencia", "trending")
            try:
                ruta = procesar_noticia(noticia, "default", duracion_maxima=args.duracion_maxima)
                generados.append(ruta)
            except Exception:
                print(f"[ERROR] Fallo al procesar '{noticia['titulo']}':")
                traceback.print_exc()

        print("\n=== Listo ===")
        for r in generados:
            print(" -", r)
        return

    # ---- Modo 6 (default): Busqueda por tema o variado ----
    if not args.tema and not args.variado:
        args.variado = True  # por defecto: temas variados

    if args.variado:
        pool = buscar_variadas(por_tema=2)
        tema_por_noticia = {n["titulo"]: n.get("tema", "default") for n in pool}
    else:
        pool = buscar_noticias(args.tema, max_resultados=max(args.cantidad, 5))
        tema_key = args.tema.lower() if args.tema.lower() in CATEGORIAS else "default"
        tema_por_noticia = {n["titulo"]: tema_key for n in pool}

    if not pool:
        print("No se encontraron noticias. Revisa tu conexion a internet o el tema buscado.")
        sys.exit(1)

    for noticia in pool[: args.cantidad]:
        tema_video = tema_por_noticia.get(noticia["titulo"], "default")
        try:
            ruta = procesar_noticia(noticia, tema_video, duracion_maxima=args.duracion_maxima)
            generados.append(ruta)
        except Exception:
            print(f"[ERROR] Fallo al procesar '{noticia['titulo']}':")
            traceback.print_exc()

    print("\n=== Listo ===")
    for r in generados:
        print(" -", r)


if __name__ == "__main__":
    main()
