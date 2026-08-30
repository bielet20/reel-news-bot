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
import json
import os
import re
import tempfile
import time
import urllib.parse
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip, vfx,
)

import comfy_video_builder

from video_builder import FONT_BOLD, FONT_REGULAR, _envolver_texto

# ── Formato / lienzo ─────────────────────────────────────────────────────────
# El Montaje es HORIZONTAL 16:9 por defecto (a diferencia del reel de noticias,
# que es 9:16). El formato se elige por sección/canción y decide tanto el lienzo
# final como la resolución que se le pide a ComfyUI.
FORMATOS = {
    "16:9": {"w": 1920, "h": 1080, "comfy_w": 832, "comfy_h": 480},
    "9:16": {"w": 1080, "h": 1920, "comfy_w": 480, "comfy_h": 832},
}

# Disolvencia rápida entre secciones en el videoclip completo. Cada sección se
# renderiza con esta cola de más (solo vídeo, el audio va aparte) que es justo
# lo que consume el crossfade, así el audio no se descuadra.
COLA_XFADE = float(os.getenv("MONTAJE_XFADE", "0.4"))


def _formato(aspect: str) -> dict:
    return FORMATOS.get(aspect, FORMATOS["16:9"])


def _frame_texto_wh(W: int, H: int, texto: str, font_path: str, tam_fuente: int,
                     y_centro: int, max_ancho: int = 900,
                     color_texto=(255, 255, 255, 255), con_fondo=True,
                     max_lineas: int = 6, tam_fuente_min: int = 34) -> Image.Image:
    """Como video_builder._frame_texto pero con lienzo (W, H) parametrizable
    (el del módulo es fijo 1080x1920)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
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
            [(W - ancho_caja) // 2, y - pad_y, (W + ancho_caja) // 2, y + alto_total + pad_y],
            radius=30, fill=(0, 0, 0, 150),
        )

    for linea in lineas:
        bbox = draw.textbbox((0, 0), linea, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), linea, font=font, fill=color_texto)
        y += alturas_linea

    return img


# Color de la línea que suena ahora (relleno karaoke). Naranja cálido por defecto.
KARAOKE_COLOR = (255, 200, 70, 255)
KARAOKE_DIM = (225, 225, 225, 160)


def _frame_karaoke(W: int, H: int, prev: str, cur: str, nxt: str,
                   tam: int, y_centro: int) -> Image.Image:
    """3 líneas apiladas: la anterior y la siguiente en gris tenue, la que se
    está cantando resaltada en color y un poco más grande. Estilo 'línea actual
    resaltada' (no relleno palabra a palabra)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    max_ancho = int(W * 0.88)

    f_dim = ImageFont.truetype(FONT_REGULAR, int(tam * 0.7))
    f_cur = ImageFont.truetype(FONT_BOLD, tam)

    filas: list[tuple[str, ImageFont.FreeTypeFont, tuple]] = []
    for txt in _envolver_texto(draw, prev, f_dim, max_ancho) if prev else []:
        filas.append((txt, f_dim, KARAOKE_DIM))
    cur_lineas = _envolver_texto(draw, cur, f_cur, max_ancho) if cur else []
    for txt in cur_lineas:
        filas.append((txt, f_cur, KARAOKE_COLOR))
    for txt in _envolver_texto(draw, nxt, f_dim, max_ancho) if nxt else []:
        filas.append((txt, f_dim, KARAOKE_DIM))
    if not filas:
        return img

    gap = int(tam * 0.35)
    alturas = [draw.textbbox((0, 0), t, font=fn)[3] + gap for t, fn, _ in filas]
    y = y_centro - sum(alturas) // 2

    # Caja de fondo semitransparente detrás de todo el bloque
    anchos = [draw.textbbox((0, 0), t, font=fn)[2] for t, fn, _ in filas]
    caja = max(anchos) + 80
    draw.rounded_rectangle(
        [(W - caja) // 2, y - 24, (W + caja) // 2, y + sum(alturas) + 8],
        radius=28, fill=(0, 0, 0, 165),
    )

    for (txt, fn, col), h in zip(filas, alturas):
        bb = draw.textbbox((0, 0), txt, font=fn)
        x = (W - (bb[2] - bb[0])) // 2
        # Sombra suave para legibilidad sobre el vídeo
        draw.text((x + 2, y + 2), txt, font=fn, fill=(0, 0, 0, 160))
        draw.text((x, y), txt, font=fn, fill=col)
        y += h

    return img

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


def _imagen_seccion(texto: str, artista: str, estilo_key: str, seed: int,
                     W: int, H: int) -> np.ndarray:
    """Descarga (o recupera del caché) la imagen AI para una sección. Fallback
    cuando ComfyUI no está disponible."""
    estilo_desc = ESTILOS.get(estilo_key, ESTILOS["cinematico"])
    tema = _palabras_clave(texto)

    orient = "horizontal 16:9 cinematic wide shot" if W >= H else "vertical 9:16 portrait"
    prompt_parts = [tema, "music video aesthetic", estilo_desc, orient, "no text no watermark"]
    if artista:
        prompt_parts.append(f"inspired by {artista}")
    prompt = ", ".join(prompt_parts)

    cache_key = hashlib.md5(f"{prompt}{seed}{W}x{H}".encode()).hexdigest()[:14]
    cache_path = CACHE_DIR / f"lyric_{cache_key}.jpg"

    if not cache_path.exists():
        encoded = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={W}&height={H}&seed={seed}&nologo=true&model=flux"
        )
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            cache_path.write_bytes(r.content)
        except Exception as e:
            print(f"[LyricVideo] Error imagen AI: {e} — usando degradado")
            return _degradado_fallback(W, H)

    try:
        img = Image.open(cache_path).convert("RGB")
    except Exception:
        return _degradado_fallback(W, H)

    escala = max(W / img.width, H / img.height)
    nw, nh = int(img.width * escala) + 1, int(img.height * escala) + 1
    img = img.resize((nw, nh), Image.LANCZOS)
    x0 = (img.width - W) // 2
    y0 = (img.height - H) // 2
    img = img.crop((x0, y0, x0 + W, y0 + H))

    overlay = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, overlay, 0.48)

    return np.array(img)


def _degradado_fallback(W: int, H: int) -> np.ndarray:
    top = np.array([5, 0, 20], dtype=float)
    bot = np.array([75, 0, 90], dtype=float)
    filas = np.linspace(0, 1, H)[:, None] * (bot - top) + top
    grad = np.tile(filas[:, None, :], (1, W, 1)).astype(float)
    return np.clip(grad, 0, 255).astype("uint8")


# ── Capas de texto ────────────────────────────────────────────────────────────

def _clips_letra(lineas: list[str], dur: float, W: int, H: int,
                 lineas_ts: list[dict] | None = None, t_offset: float = 0.0) -> list:
    """Superpone la letra.

    - Con `lineas_ts` (tiempos reales alineados con el audio): modo karaoke —
      UNA línea a la vez, que aparece exactamente cuando empieza a cantarse y se
      va cuando entra la siguiente. Es lo más ajustado a lo que suena.
    - Sin tiempos: 2 líneas por pantalla repartidas uniformemente en `dur`.
    """
    if not lineas:
        return []
    tam = 66 if W < H else 60
    clips = []

    if lineas_ts and len(lineas_ts) == len(lineas) and any(
        t and t.get("start") is not None for t in lineas_ts
    ):
        # ── Karaoke: una línea por vez ───────────────────────────────────────
        # Rellena los huecos (líneas sin tiempo) interpolando entre vecinas.
        starts: list[float] = []
        for j, t in enumerate(lineas_ts):
            s = None if not t else t.get("start")
            starts.append(None if s is None else max(0.0, s - t_offset))
        # interpola internos + extrapola extremos
        conoc = [j for j, s in enumerate(starts) if s is not None]
        if conoc:
            for a, b in zip(conoc, conoc[1:]):
                if b - a > 1:
                    for k in range(a + 1, b):
                        starts[k] = starts[a] + (starts[b] - starts[a]) * (k - a) / (b - a)
            for j in range(conoc[0] - 1, -1, -1):
                starts[j] = max(0.0, (starts[j + 1] or 0.0) - 2.0)
            paso = dur / max(len(lineas), 1)
            for j in range(conoc[-1] + 1, len(lineas)):
                starts[j] = min(dur - 0.1, (starts[j - 1] or 0.0) + paso)
        else:
            starts = [i * dur / len(lineas) for i in range(len(lineas))]

        for j, linea in enumerate(lineas):
            ini = min(max(0.0, starts[j]), max(0.0, dur - 0.3))
            fin = starts[j + 1] if j + 1 < len(lineas) else dur
            fin = min(max(fin, ini + 0.4), dur)
            if fin <= ini:
                continue
            img = _frame_karaoke(
                W, H,
                prev=lineas[j - 1] if j > 0 else "",
                cur=linea,
                nxt=lineas[j + 1] if j + 1 < len(lineas) else "",
                tam=tam, y_centro=int(H * 0.80),
            )
            fade = min(0.15, (fin - ini) / 6)
            clips.append(
                ImageClip(np.array(img)).set_start(ini).set_duration(fin - ini)
                .crossfadein(fade).crossfadeout(fade)
            )
        return clips

    # ── Fallback uniforme: 2 líneas por pantalla ─────────────────────────────
    n_pag = (len(lineas) + 1) // 2
    dur_pag = dur / n_pag
    for i in range(n_pag):
        pag = "\n".join(lineas[i * 2:i * 2 + 2])
        ini, fin = i * dur_pag, (i + 1) * dur_pag
        if fin <= ini:
            continue
        img = _frame_texto_wh(W, H, pag, FONT_BOLD, tam, y_centro=int(H * 0.82),
                              max_ancho=int(W * 0.85), max_lineas=3)
        fade = min(0.25, (fin - ini) / 4)
        clips.append(
            ImageClip(np.array(img)).set_start(ini).set_duration(fin - ini)
            .crossfadein(fade).crossfadeout(fade)
        )
    return clips


def _clip_etiqueta(label: str, dur: float, W: int, H: int) -> ImageClip:
    img = _frame_texto_wh(
        W, H, label.upper(), FONT_REGULAR, 28, y_centro=70,
        max_ancho=int(W * 0.85), color_texto=(200, 160, 255, 170), con_fondo=False,
    )
    return ImageClip(np.array(img)).set_duration(min(3.0, dur)).crossfadein(0.3).crossfadeout(0.3)


def _clips_cabecera(titulo: str, artista: str, dur: float, W: int, H: int) -> list:
    clips = []
    if titulo:
        img = _frame_texto_wh(W, H, titulo, FONT_BOLD, 52, y_centro=130,
                              max_ancho=int(W * 0.85), max_lineas=2)
        clips.append(ImageClip(np.array(img)).set_duration(dur))
    if artista:
        y = 260 if titulo else 130
        img = _frame_texto_wh(W, H, artista, FONT_REGULAR, 38, y_centro=y,
                              max_ancho=int(W * 0.85), max_lineas=1,
                              color_texto=(210, 160, 255, 220), con_fondo=False)
        clips.append(ImageClip(np.array(img)).set_duration(dur))
    return clips


# ── Estado del montaje (para pausar / reanudar tras un corte) ─────────────────

def _ruta_plan(ruta_salida_base: str) -> Path:
    return Path(f"{ruta_salida_base}_montaje_plan.json")


def _guardar_plan(ruta_salida_base: str, datos: dict) -> None:
    try:
        p = _ruta_plan(ruta_salida_base)
        datos["actualizado"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        p.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[LyricVideo] no se pudo guardar el plan del montaje: {e}")


def _cargar_plan(ruta_salida_base: str) -> dict | None:
    try:
        return json.loads(_ruta_plan(ruta_salida_base).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


MontajeCancelado = comfy_video_builder.MontajeCancelado


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
    modo_fondo: str = "video",
    voz_femenina: bool = False,
    voz: str = "auto",  # "auto" | "hombre" | "mujer" | "mixta"
    pista_voz: str | None = None,
    aspect: str = "16:9",
    provider: str = "wan22",
    letra_lrc: str | None = None,
    idioma: str = "es",
    info_out: dict | None = None,
    should_cancel=None,       # Callable() -> bool. Si devuelve True, se para limpio.
    reanudar: bool = False,   # Reusa el plan guardado y salta las secciones ya hechas.
) -> list[str]:
    """
    Genera un clip MP4 por sección de la letra + un videoclip completo.

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
        modo_fondo:       "video" -> fondo generado con ComfyUI (Flux + Wan i2v)
                          relacionado con la letra; "imagen" -> imagen fija AI
                          (Pollinations) con Ken Burns, el comportamiento antiguo.
                          Si "video" y ComfyUI no responde, cae a "imagen" por
                          sección sin abortar.
        voz_femenina:     Solo con modo_fondo="video": pasa cada sección cantada
                          por LatentSync para que la protagonista mueva los
                          labios con la letra.
        pista_voz:        Ruta opcional a una pista de voz a cappella; si se da,
                          es la que alimenta el lip-sync (mejor sincronía).
        aspect:           "16:9" (horizontal, default) o "9:16" (vertical/reel).

    Returns:
        Lista de rutas a los MP4: primero el videoclip completo, luego uno por
        sección.
    """
    secciones = parsear_secciones(letra)
    if not secciones:
        raise ValueError("No se encontraron secciones en la letra.")

    fmt = _formato(aspect)
    W, H = fmt["w"], fmt["h"]
    cw, ch = fmt["comfy_w"], fmt["comfy_h"]

    audio_full = AudioFileClip(ruta_audio)
    dur_total = audio_full.duration

    voz_full = None
    if pista_voz and os.path.exists(pista_voz):
        try:
            voz_full = AudioFileClip(pista_voz)
        except Exception as e:  # noqa: BLE001
            print(f"[LyricVideo] No se pudo abrir la pista de voz ({e}); se usará la mezcla para el lip-sync.")

    def _cancelado() -> bool:
        try:
            return bool(should_cancel and should_cancel())
        except Exception:  # noqa: BLE001
            return False

    # ── Reanudar: si hay plan guardado, se reutiliza y se saltan whisper / voz /
    #    guion (lo caro) y las secciones cuyo MP4 ya existe. ──────────────────
    _plan = _cargar_plan(ruta_salida_base) if reanudar else None
    if _plan:
        print(f"[LyricVideo] REANUDANDO: {_plan.get('secciones_hechas', 0)}/"
              f"{_plan.get('total_secciones', '?')} secciones ya hechas.")

    # ── Detectar el tipo de voz (hombre / mujer / mixta) ─────────────────────
    # Decide a quién se pone en pantalla y si se aplica lip-sync, sin que el
    # usuario lo marque a mano. `voz` != "auto" lo fija el usuario.
    deteccion_voz: dict | None = None
    voz_tipo = voz
    if _plan:
        voz_femenina = _plan.get("voz_femenina", voz_femenina)
        voz_tipo = _plan.get("voz_tipo", voz)
        deteccion_voz = _plan.get("voces")
    elif voz == "auto":
        try:
            import voice_detector
            if cb_progreso:
                cb_progreso(0, len(secciones), "Detectando el tipo de voz…")
            deteccion_voz = voice_detector.detectar_voces(ruta_audio, pista_voz)
            voz_tipo = deteccion_voz.get("tipo", "desconocida")
            print(f"[LyricVideo] voz detectada: {deteccion_voz}")
            if voz_tipo in ("mujer", "mixta"):
                voz_femenina = True
            elif voz_tipo == "hombre":
                voz_femenina = False
        except Exception as e:  # noqa: BLE001
            print(f"[LyricVideo] no se pudo detectar la voz ({e}); se usa voz_femenina={voz_femenina}.")
    else:
        voz_femenina = voz in ("mujer", "mixta")
    if info_out is not None:
        info_out["voces"] = deteccion_voz or {"tipo": voz_tipo, "fuente": "manual"}

    # ── Sincronizar la letra con el audio ────────────────────────────────────
    # lineas_ts_seccion[k] = [ {texto,start,end} | None ] por cada línea de la
    # sección k. Puede haber None sueltos (líneas que no se pudieron alinear):
    # el resto del pipeline los tolera e interpola. None global -> reparto
    # uniforme de siempre.
    lineas_ts_seccion: list[list[dict | None]] | None = None
    sync_modo = "uniforme"
    if _plan:
        lineas_ts_seccion = _plan.get("lineas_ts_seccion")
        sync_modo = _plan.get("sync_modo", "uniforme")
    else:
        try:
            import lyric_aligner
            if cb_progreso:
                cb_progreso(0, len(secciones), "Sincronizando letra con el audio…")
            tiene_acapella = bool(pista_voz and os.path.exists(pista_voz))
            audio_para_alinear = pista_voz if tiene_acapella else ruta_audio
            alineado = lyric_aligner.alinear_letra(
                audio_para_alinear, letra, idioma, letra_lrc, ya_es_voz=tiene_acapella)
            if alineado:
                it = iter(alineado)
                lineas_ts_seccion = []
                for sec in secciones:
                    grupo: list[dict | None] = [next(it, None) for _ in sec["lineas"]]
                    lineas_ts_seccion.append(grupo)
                timadas = sum(1 for g in lineas_ts_seccion for x in g if x)
                total_lin = sum(len(g) for g in lineas_ts_seccion) or 1
                if timadas < max(3, total_lin * 0.35):
                    # Demasiado poco casó como para fiarse; reparto uniforme.
                    print(f"[LyricVideo] alineación pobre ({timadas}/{total_lin}); reparto uniforme.")
                    lineas_ts_seccion = None
                else:
                    sync_modo = "lrc" if (letra_lrc and letra_lrc.strip()) else "whisper"
                    print(f"[LyricVideo] letra sincronizada ({sync_modo}, "
                          f"{timadas}/{total_lin} líneas con tiempo real).")
        except Exception as e:  # noqa: BLE001
            print(f"[LyricVideo] no se pudo sincronizar la letra ({e}); reparto uniforme.")
            lineas_ts_seccion = None
    if cb_progreso:
        cb_progreso(0, len(secciones), f"Sincronización de letra: {sync_modo}")
    if info_out is not None:
        info_out["sync_letra"] = sync_modo

    # ── Elegir generador de vídeo ────────────────────────────────────────────
    # `provider`: "wan22" | "ltx" | "fal" | "imagen".  (modo_fondo="imagen"
    # antiguo sigue funcionando.)
    if modo_fondo == "imagen":
        provider = "imagen"
    usar_video = provider != "imagen"
    style_prefix = ""
    escenas_plan: list[dict] = []
    if usar_video:
        # Pre-chequeo: si el generador elegido NO está listo, el job falla con un
        # mensaje claro (no se hace pasar por vídeo un montón de fotos en silencio).
        estado = comfy_video_builder.verificar_herramientas()
        prov_info = next((p for p in estado["providers"] if p["id"] == provider), None)
        if not prov_info or not prov_info["disponible"]:
            motivo = prov_info["nota"] if prov_info else f"generador desconocido: {provider}"
            raise RuntimeError(
                f"No se puede generar vídeo con '{provider}': {motivo}\n"
                f"Arregla eso y vuelve a intentarlo, o elige el generador «Imagen fija» "
                f"si quieres el montaje con imágenes."
            )
        if provider in ("wan22", "ltx") and not estado["lm_studio"] \
                and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY")):
            raise RuntimeError(
                "No hay ningún LLM para escribir el guion visual de la letra: "
                "arranca LM Studio (host, puerto 1234) o pon ANTHROPIC_API_KEY / GEMINI_API_KEY en .env."
            )
        if _plan and _plan.get("escenas_plan"):
            style_prefix = _plan.get("style_prefix", "")
            escenas_plan = _plan["escenas_plan"]
            print(f"[LyricVideo] guion reutilizado del plan ({len(escenas_plan)} escenas).")
        else:
            try:
                style_prefix, escenas_plan = comfy_video_builder.plan_escenas(
                    letra, artista, titulo, estilo, voz_femenina, dur_total,
                    voz_tipo=voz_tipo,
                )
                print(f"[LyricVideo] Generador '{provider}' · guion: {style_prefix!r} "
                      f"({len(escenas_plan)} escenas)")
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"No se pudo escribir el guion visual de la letra: {e}") from e

        # El guion ya está escrito; a partir de aquí solo se usa ComfyUI. Liberar
        # la VRAM de LM Studio evita que ComfyUI se quede sin memoria a mitad
        # (desactivable con MONTAJE_NO_LIBERAR_LM=1).
        if provider in ("wan22", "ltx") and not os.getenv("MONTAJE_NO_LIBERAR_LM"):
            if comfy_video_builder.liberar_lm_studio_vram():
                print("[LyricVideo] LM Studio descargado para dejar VRAM a ComfyUI.")

    tiempos: list[tuple[float, float]] = []
    if _plan and _plan.get("tiempos"):
        tiempos = [(float(a), float(b)) for a, b in _plan["tiempos"]]
    elif lineas_ts_seccion:
        # Fronteras de sección desde los tiempos reales de la letra. `inicio_k` =
        # primera línea con tiempo de la sección k; si toda la sección quedó sin
        # tiempo, se interpola entre las secciones vecinas que sí lo tienen.
        def _primer_start(grupo: list) -> float | None:
            for x in grupo:
                if x and x.get("start") is not None:
                    return float(x["start"])
            return None

        crudos = [_primer_start(g) for g in lineas_ts_seccion]
        crudos[0] = 0.0  # la primera sección arranca en 0 (cubre la intro)
        conoc = [k for k, s in enumerate(crudos) if s is not None]
        for a, b in zip(conoc, conoc[1:]):
            if b - a > 1:
                for k in range(a + 1, b):
                    crudos[k] = crudos[a] + (crudos[b] - crudos[a]) * (k - a) / (b - a)
        if conoc and conoc[-1] < len(crudos) - 1:
            paso = (dur_total - (crudos[conoc[-1]] or 0.0)) / (len(crudos) - conoc[-1])
            for k in range(conoc[-1] + 1, len(crudos)):
                crudos[k] = min(dur_total - 0.5, (crudos[k - 1] or 0.0) + paso)
        # monótono y con fin = inicio de la siguiente
        for k in range(len(crudos)):
            ini = max(crudos[k] or 0.0, tiempos[k - 1][1] if k else 0.0)
            fin = crudos[k + 1] if k + 1 < len(crudos) else dur_total
            fin = min(max(fin or dur_total, ini + 1.0), dur_total)
            tiempos.append((ini, fin))
    else:
        # Reparto uniforme proporcional al número de líneas (comportamiento previo)
        total_lineas = sum(len(s["lineas"]) for s in secciones) or 1
        t = 0.0
        for sec in secciones:
            prop = len(sec["lineas"]) / total_lineas
            dur = max(4.0, dur_total * prop)
            fin = min(t + dur, dur_total)
            tiempos.append((t, fin))
            t = fin
            if t >= dur_total:
                break

    # Persistir el plan: a partir de aquí un corte se puede reanudar sin repetir
    # whisper / detección de voz / guion.
    plan_actual = {
        "titulo": titulo, "total_secciones": len(secciones), "secciones_hechas": 0,
        "sync_modo": sync_modo, "voz_femenina": voz_femenina, "voz_tipo": voz_tipo,
        "voces": deteccion_voz, "style_prefix": style_prefix, "escenas_plan": escenas_plan,
        "tiempos": [list(t) for t in tiempos],
        "lineas_ts_seccion": lineas_ts_seccion,
        "aspect": aspect, "provider": provider, "status": "generando",
    }
    if _plan:
        plan_actual["secciones_hechas"] = _plan.get("secciones_hechas", 0)
    _guardar_plan(ruta_salida_base, plan_actual)

    rutas = []
    duraciones: list[float] = []  # duración REAL (sin la cola de xfade) por clip
    comfy_dir = Path(tempfile.mkdtemp(prefix=f"comfy_{os.getpid()}_"))
    fondos_video: list = []  # clips VideoFileClip abiertos, se cierran al final
    cancelado = False

    for i, (sec, (t_ini, t_fin)) in enumerate(zip(secciones, tiempos)):
        if t_fin <= t_ini:
            continue

        if _cancelado():
            print(f"[LyricVideo] cancelado por el usuario en la sección {i + 1}.")
            cancelado = True
            break

        slug_i = re.sub(r"[^\w]", "_", sec["label"].lower())[:18]
        ruta_prev = f"{ruta_salida_base}_{i + 1:02d}_{slug_i}_reel.mp4"
        marca_fallback = ruta_prev + ".imagen"
        # Reanudar: si el MP4 de esta sección ya existe y dura lo esperado, se salta.
        # EXCEPTO si se hizo con imagen fija porque ComfyUI falló y ahora sí
        # queremos vídeo: en ese caso se regenera.
        if os.path.exists(ruta_prev):
            try:
                from comfy_video_builder import probe_duration
                d_prev = probe_duration(Path(ruta_prev), default=0.0)
            except Exception:  # noqa: BLE001
                d_prev = 0.0
            esperado = t_fin - t_ini
            dur_ok = d_prev > 1.0 and abs(d_prev - esperado) <= max(2.0, esperado * 0.35)
            reintenta_video = usar_video and os.path.exists(marca_fallback)
            if dur_ok and not reintenta_video:
                print(f"[LyricVideo] sección {i + 1} ya hecha ({Path(ruta_prev).name}); se salta.")
                rutas.append(ruta_prev)
                duraciones.append(d_prev)
                plan_actual["secciones_hechas"] = max(plan_actual["secciones_hechas"], i + 1)
                _guardar_plan(ruta_salida_base, plan_actual)
                continue
            if dur_ok and reintenta_video:
                print(f"[LyricVideo] sección {i + 1} se había hecho con imagen fija "
                      f"(ComfyUI falló); se reintenta el vídeo IA.")

        def _prog(label_extra: str = ""):
            if cb_progreso:
                etiqueta = sec["label"] + (f" · {label_extra}" if label_extra else "")
                cb_progreso(i, len(secciones), etiqueta)

        _prog()

        audio_clip = audio_full.subclip(t_ini, t_fin)
        dur = audio_clip.duration
        # Los clips de sección se escriben a su duración exacta; la cola que
        # necesita el crossfade del videoclip completo la añade _xfade_silent
        # con tpad, así estos ficheros no quedan con vídeo de más.
        dur_v = dur

        fondo = None
        uso_fallback = False
        seccion_cantada = bool(sec["lineas"])

        # ── Fondo con vídeo IA (ComfyUI) ─────────────────────────────────────
        if usar_video and i < len(escenas_plan):
            try:
                fondo_path = comfy_dir / f"s{i + 1:02d}.mp4"
                comfy_video_builder.generar_fondo_seccion(
                    provider, style_prefix, escenas_plan[i], dur, seed=i * 19 + 7,
                    out_path=fondo_path, width=cw, height=ch, log_fn=_prog,
                    should_cancel=_cancelado,
                )
                if voz_femenina and seccion_cantada:
                    if voz_full is not None:
                        voz_seg = voz_full.subclip(min(t_ini, voz_full.duration),
                                                   min(t_fin, voz_full.duration))
                    else:
                        voz_seg = audio_clip
                    voz_wav = comfy_dir / f"s{i + 1:02d}_voz.wav"
                    voz_seg.write_audiofile(str(voz_wav), fps=16000, logger=None)
                    synced = comfy_dir / f"s{i + 1:02d}_sync.mp4"
                    comfy_video_builder.aplicar_lipsync(fondo_path, voz_wav, synced, log_fn=_prog)
                    fondo_path = synced

                vfc = VideoFileClip(str(fondo_path))
                fondos_video.append(vfc)
                # Escala manteniendo aspecto y recorta al encuadre exacto (W×H)
                escala = max(W / vfc.w, H / vfc.h)
                vfc = vfc.resize(escala)
                vfc = vfc.crop(x_center=vfc.w / 2, y_center=vfc.h / 2, width=W, height=H)
                if vfc.duration < dur_v - 0.05:
                    vfc = vfc.fx(vfx.loop, duration=dur_v)
                fondo = vfc.set_duration(dur_v).set_position("center")
            except MontajeCancelado:
                print(f"[LyricVideo] cancelado por el usuario durante la sección {i + 1}.")
                cancelado = True
            except Exception as e:  # noqa: BLE001
                print(f"[LyricVideo] Sección {i + 1}: falló el vídeo IA ({e}); "
                      f"se usa imagen fija para esta sección.")
                fondo = None

        if cancelado:
            break

        # ── Fallback: imagen fija AI + Ken Burns ─────────────────────────────
        if fondo is None:
            uso_fallback = usar_video  # sólo es "fallback" si queríamos vídeo
            _prog("imagen fija")
            img_arr = _imagen_seccion(
                "\n".join(sec["lineas"]), artista, estilo, seed=i * 19 + 7, W=W, H=H
            )
            fondo = (
                ImageClip(img_arr)
                .set_duration(dur_v)
                .fx(vfx.resize, lambda t, d=dur_v: 1.0 + 0.06 * (t / max(d, 0.01)))
                .set_position("center")
            )

        capas: list = [fondo]

        # Etiqueta de sección (esquina superior)
        capas.append(_clip_etiqueta(sec["label"], dur, W, H))

        # Cabecera título/artista (solo primer clip)
        if mostrar_cabecera and i == 0:
            capas += _clips_cabecera(titulo, artista, dur, W, H)

        # Letra
        if mostrar_letra and sec["lineas"]:
            ts = lineas_ts_seccion[i] if lineas_ts_seccion else None
            capas += _clips_letra(sec["lineas"], dur, W, H, lineas_ts=ts, t_offset=t_ini)

        video = (
            CompositeVideoClip(capas, size=(W, H))
            .set_audio(audio_clip)
            .set_duration(dur_v)
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

        # Marcador para poder reintentar el vídeo en una reanudación si esta
        # sección salió con imagen fija por un fallo de ComfyUI.
        try:
            if uso_fallback:
                Path(ruta_out + ".imagen").touch()
            else:
                Path(ruta_out + ".imagen").unlink(missing_ok=True)
        except OSError:
            pass

        print(f"[LyricVideo] {i + 1}/{len(secciones)} → {Path(ruta_out).name}"
              f"{'  (imagen fija — ComfyUI falló)' if uso_fallback else ''}")
        rutas.append(ruta_out)
        duraciones.append(dur)
        plan_actual["secciones_hechas"] = max(plan_actual["secciones_hechas"], i + 1)
        _guardar_plan(ruta_salida_base, plan_actual)

    if cancelado:
        plan_actual["status"] = "cancelado"
        _guardar_plan(ruta_salida_base, plan_actual)
        if info_out is not None:
            info_out["cancelado"] = True
        _cerrar_recursos(fondos_video, voz_full, audio_full, comfy_dir)
        print(f"[LyricVideo] cancelado: {len(rutas)}/{len(secciones)} secciones hechas "
              f"(se pueden reanudar).")
        return list(rutas)

    # ── Videoclip completo ──────────────────────────────────────────────────
    # Se concatena SOLO el vídeo de las secciones y se le pone encima la pista
    # de audio original entera: empalmar los tramos de audio AAC de cada sección
    # metía un chasquido audible en cada corte.
    resultado = list(rutas)
    if len(rutas) > 1:
        if cb_progreso:
            cb_progreso(len(secciones) - 1, len(secciones), "Ensamblando videoclip completo")
        full_path = f"{ruta_salida_base}_full_reel.mp4"
        try:
            comfy_video_builder.ensamblar_videoclip_completo(
                [Path(r) for r in rutas], Path(ruta_audio), Path(full_path),
                duraciones=duraciones, xfade=COLA_XFADE,
            )
            if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                resultado = [full_path] + rutas
                print(f"[LyricVideo] Videoclip completo → {Path(full_path).name}")
        except Exception as e:  # noqa: BLE001
            print(f"[LyricVideo] No se pudo ensamblar el videoclip completo ({e}).")

    plan_actual["status"] = "completado"
    _guardar_plan(ruta_salida_base, plan_actual)
    _cerrar_recursos(fondos_video, voz_full, audio_full, comfy_dir)
    return resultado


def _cerrar_recursos(fondos_video, voz_full, audio_full, comfy_dir) -> None:
    for vfc in fondos_video:
        try:
            vfc.close()
        except Exception:  # noqa: BLE001
            pass
    if voz_full is not None:
        try:
            voz_full.close()
        except Exception:  # noqa: BLE001
            pass
    try:
        audio_full.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        import shutil
        shutil.rmtree(comfy_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
