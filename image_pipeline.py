"""
image_pipeline.py
Gestiona las imágenes de fondo para los reels:
  - Extrae imágenes del artículo (scraping)
  - Busca fotos reales en Pexels / Unsplash (si hay API key en .env)
  - Genera imágenes con IA via Pollinations.ai (gratis, sin API key)

Pipeline de prioridad:
  1. Imágenes subidas por el usuario
  2. Imágenes scrapeadas del artículo
  3. Fotos de Pexels (PEXELS_API_KEY) o Unsplash (UNSPLASH_ACCESS_KEY)
  4. Imágenes generadas con Pollinations.ai (siempre disponible, sin key)
"""
import os
import re
import random
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

ANCHO, ALTO = 1080, 1920
_TMP_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "_img_cache"

_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "al", "en", "con", "por", "para", "que", "se", "su", "sus", "lo",
    "le", "les", "no", "si", "ya", "pero", "más", "como", "este", "esta",
    "estos", "estas", "son", "es", "ha", "han", "fue", "era", "ser",
    "estar", "también", "desde", "hasta", "entre", "sobre", "hacia", "a",
    "y", "o", "e", "ni", "ante", "tras", "sin", "bajo", "muy", "bien",
    "cuando", "donde", "quien", "cual", "cuyo", "cuya", "todo", "todos",
    "toda", "todas", "nuevo", "nueva", "gran", "grandes", "puede", "pueden",
    "tienen", "tiene", "hacer", "hace", "hecho", "sido", "años", "año",
    "vez", "veces", "parte", "según", "tras", "solo", "cada", "otro",
    "otra", "otros", "otras", "mismo", "misma", "durante", "después",
    "antes", "ahora", "aquí", "allí", "entonces", "así",
}


def _mkdir():
    _TMP_DIR.mkdir(exist_ok=True)


def _redimensionar_para_video(ruta: str) -> str:
    """Redimensiona y recorta la imagen a 1080x1920 (vertical), oscureciendo."""
    img = Image.open(ruta).convert("RGB")
    escala = max(ANCHO / img.width, ALTO / img.height)
    nuevo = (int(img.width * escala) + 1, int(img.height * escala) + 1)
    img = img.resize(nuevo, Image.LANCZOS)
    x0 = (img.width - ANCHO) // 2
    y0 = (img.height - ALTO) // 2
    img = img.crop((x0, y0, x0 + ANCHO, y0 + ALTO))

    from PIL import ImageDraw
    overlay = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, overlay, 0.45)

    img.save(ruta, "JPEG", quality=90)
    return ruta


def extraer_queries_articulo(titulo: str, texto: str = "") -> list:
    """
    Genera 3 queries de búsqueda relacionadas con el artículo.
    La primera usa el título completo; las otras usan palabras clave
    extraídas del texto para dar variedad visual al slideshow.
    """
    palabras = re.findall(
        r'\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{4,}\b',
        (titulo + " ") * 3 + texto[:600],
    )
    freq: dict = {}
    for p in palabras:
        pl = p.lower()
        if pl not in _STOPWORDS_ES:
            freq[pl] = freq.get(pl, 0) + 1

    top = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:10]]

    q1 = titulo[:80]
    q2 = " ".join(top[:3]) if top else titulo[:50]
    q3 = " ".join(top[3:6]) if len(top) > 3 else q2

    return [q1, q2, q3]


def extraer_imagenes_articulo(url: str, max_imgs: int = 4, carpeta: str = None) -> list:
    """
    Descarga imágenes del artículo (etiquetas <img> en el HTML).
    Devuelve lista de rutas locales.
    """
    _mkdir()
    carpeta = Path(carpeta) if carpeta else _TMP_DIR
    carpeta.mkdir(exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,*/*;q=0.8",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN image] No se pudo descargar {url}: {e}")
        return []

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")

    candidatos = []
    for img_tag in soup.find_all("img"):
        src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src")
        if not src:
            continue
        src = urllib.parse.urljoin(url, src)
        w = img_tag.get("width", "")
        h = img_tag.get("height", "")
        try:
            if int(w) < 200 or int(h) < 150:
                continue
        except (ValueError, TypeError):
            pass
        if any(x in src.lower() for x in ["logo", "icon", "avatar", "badge", "ads", "banner"]):
            continue
        candidatos.append(src)

    rutas = []
    for i, img_url in enumerate(candidatos[:max_imgs * 2]):
        if len(rutas) >= max_imgs:
            break
        try:
            nombre = carpeta / f"art_img_{i}.jpg"
            r = requests.get(img_url, timeout=10, headers=headers)
            r.raise_for_status()
            with open(nombre, "wb") as f:
                f.write(r.content)
            img = Image.open(nombre)
            if img.width < 300 or img.height < 200:
                os.unlink(nombre)
                continue
            img.close()
            _redimensionar_para_video(str(nombre))
            rutas.append(str(nombre))
        except Exception as e:
            print(f"[WARN image] No se pudo descargar {img_url}: {e}")

    return rutas


def _buscar_pexels(query: str, ruta_salida: str, api_key: str) -> Optional[str]:
    """Descarga foto vertical de Pexels relacionada al tema."""
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "orientation": "portrait", "per_page": 10, "size": "large"},
            headers={"Authorization": api_key},
            timeout=12,
        )
        resp.raise_for_status()
        fotos = resp.json().get("photos", [])
        if not fotos:
            return None
        foto = random.choice(fotos[:5])
        img_url = foto["src"]["portrait"]
        r = requests.get(img_url, timeout=20)
        r.raise_for_status()
        with open(ruta_salida, "wb") as f:
            f.write(r.content)
        _redimensionar_para_video(ruta_salida)
        return ruta_salida
    except Exception as e:
        print(f"[WARN image] Pexels falló ({query!r}): {e}")
        return None


def _buscar_unsplash(query: str, ruta_salida: str, access_key: str) -> Optional[str]:
    """Descarga foto de Unsplash relacionada al tema."""
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "orientation": "portrait", "per_page": 10},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=12,
        )
        resp.raise_for_status()
        resultados = resp.json().get("results", [])
        if not resultados:
            return None
        foto = random.choice(resultados[:5])
        img_url = foto["urls"]["regular"]
        r = requests.get(img_url, timeout=20)
        r.raise_for_status()
        with open(ruta_salida, "wb") as f:
            f.write(r.content)
        _redimensionar_para_video(ruta_salida)
        return ruta_salida
    except Exception as e:
        print(f"[WARN image] Unsplash falló ({query!r}): {e}")
        return None


def _buscar_pixabay(query: str, ruta_salida: str, api_key: str) -> Optional[str]:
    """Descarga foto vertical de Pixabay relacionada al tema."""
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": api_key,
                "q": query,
                "orientation": "vertical",
                "per_page": 10,
                "image_type": "photo",
                "safesearch": "true",
            },
            timeout=12,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            return None
        foto = random.choice(hits[:5])
        img_url = foto.get("largeImageURL") or foto.get("webformatURL")
        r = requests.get(img_url, timeout=20)
        r.raise_for_status()
        with open(ruta_salida, "wb") as f:
            f.write(r.content)
        _redimensionar_para_video(ruta_salida)
        return ruta_salida
    except Exception as e:
        print(f"[WARN image] Pixabay falló ({query!r}): {e}")
        return None


def _generar_pollinations(prompt: str, ruta_salida: str, seed: Optional[int] = None) -> Optional[str]:
    """Genera imagen con Pollinations.ai (FLUX, gratis, sin API key)."""
    prompt_limpio = re.sub(r"[^\w\s,.-]", " ", prompt).strip()
    prompt_enc = urllib.parse.quote(
        f"{prompt_limpio}, news photography, cinematic lighting, dark moody, vertical"
    )
    _seed = seed if seed is not None else abs(hash(prompt)) % 99999
    url = (
        f"https://image.pollinations.ai/prompt/{prompt_enc}"
        f"?width=1080&height=1920&seed={_seed}&nologo=true&model=flux"
    )

    print(f"   -> Generando imagen IA para: {prompt[:60]}...")
    try:
        resp = requests.get(url, timeout=90, stream=True)
        resp.raise_for_status()
        with open(ruta_salida, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        img = Image.open(ruta_salida)
        if img.width < 100:
            os.unlink(ruta_salida)
            return None
        img.close()
        _redimensionar_para_video(ruta_salida)
        print(f"   -> Imagen generada: {ruta_salida}")
        return ruta_salida
    except Exception as e:
        print(f"[WARN image] Pollinations.ai falló: {e}")
        if os.path.exists(ruta_salida):
            try:
                os.unlink(ruta_salida)
            except Exception:
                pass
        return None


def _buscar_foto_repositorios(query: str, ruta_salida: str) -> Optional[str]:
    """
    Busca una foto real en repositorios disponibles (Pexels → Unsplash → Pixabay).
    Devuelve la ruta si tiene éxito, None si no hay ninguna key configurada.
    """
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    if pexels_key:
        r = _buscar_pexels(query, ruta_salida, pexels_key)
        if r:
            return r

    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if unsplash_key:
        r = _buscar_unsplash(query, ruta_salida, unsplash_key)
        if r:
            return r

    pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
    if pixabay_key:
        r = _buscar_pixabay(query, ruta_salida, pixabay_key)
        if r:
            return r

    return None


def generar_imagen_ai(
    prompt: str,
    ruta_salida: str,
    servicio: str = "pollinations",
    seed: Optional[int] = None,
    api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Genera/busca una imagen relacionada al prompt.

    Servicios:
      - "pollinations"  → Pollinations.ai FLUX (gratis, sin key)
      - "pexels"        → Foto real de Pexels (requiere PEXELS_API_KEY)
      - "unsplash"      → Foto real de Unsplash (requiere UNSPLASH_ACCESS_KEY)
      - "pixabay"       → Foto real de Pixabay (requiere PIXABAY_API_KEY)
    """
    if servicio == "pexels":
        key = api_key or os.environ.get("PEXELS_API_KEY", "")
        if key:
            r = _buscar_pexels(prompt, ruta_salida, key)
            if r:
                return r
        print("[WARN image] PEXELS_API_KEY no disponible, usando pollinations")
        return _generar_pollinations(prompt, ruta_salida, seed)

    elif servicio == "unsplash":
        key = api_key or os.environ.get("UNSPLASH_ACCESS_KEY", "")
        if key:
            r = _buscar_unsplash(prompt, ruta_salida, key)
            if r:
                return r
        print("[WARN image] UNSPLASH_ACCESS_KEY no disponible, usando pollinations")
        return _generar_pollinations(prompt, ruta_salida, seed)

    elif servicio == "pixabay":
        key = api_key or os.environ.get("PIXABAY_API_KEY", "")
        if key:
            r = _buscar_pixabay(prompt, ruta_salida, key)
            if r:
                return r
        print("[WARN image] PIXABAY_API_KEY no disponible, usando pollinations")
        return _generar_pollinations(prompt, ruta_salida, seed)

    else:
        return _generar_pollinations(prompt, ruta_salida, seed)


def preparar_imagenes(
    titulo: str,
    url_articulo: str = None,
    texto_articulo: str = "",
    rutas_usuario: list = None,
    generar_ai: bool = False,
    n_ai: int = 3,
    servicio_ai: str = "pollinations",
    carpeta_tmp: str = None,
) -> list:
    """
    Pipeline completo de imágenes. Prioridad:
    1. Imágenes subidas por el usuario
    2. Imágenes del artículo (scraping)
    3. Fotos de repositorios (Pexels/Unsplash/Pixabay) usando keywords del artículo
    4. Imágenes generadas con IA (Pollinations.ai) usando keywords del artículo

    Los pasos 3 y 4 se ejecutan siempre automáticamente cuando faltan imágenes,
    usando queries extraídas del contenido del artículo para máxima relevancia.

    Devuelve lista de rutas locales listas para usar como fondo del video.
    """
    _mkdir()
    carpeta = Path(carpeta_tmp) if carpeta_tmp else _TMP_DIR
    carpeta.mkdir(exist_ok=True)

    imagenes = []

    # 1. Imágenes del usuario (prioridad máxima)
    if rutas_usuario:
        for ruta in rutas_usuario:
            if os.path.isfile(ruta):
                try:
                    import shutil
                    dest = str(carpeta / f"usr_{Path(ruta).name}")
                    shutil.copy2(ruta, dest)
                    _redimensionar_para_video(dest)
                    imagenes.append(dest)
                except Exception as e:
                    print(f"[WARN image] No se pudo procesar {ruta}: {e}")
        if len(imagenes) >= n_ai:
            return imagenes

    # 2. Imágenes del artículo (scraping)
    if url_articulo and len(imagenes) < n_ai:
        print("   -> Extrayendo imágenes del artículo...")
        imgs_art = extraer_imagenes_articulo(
            url_articulo, max_imgs=n_ai - len(imagenes), carpeta=str(carpeta)
        )
        imagenes.extend(imgs_art)
        if imgs_art:
            print(f"   -> {len(imgs_art)} imagen(es) extraída(s) del artículo")

    # 3 + 4. Buscar en repositorios y/o generar con IA (siempre automático)
    if len(imagenes) < n_ai:
        queries = extraer_queries_articulo(titulo, texto_articulo)
        faltantes = n_ai - len(imagenes)
        print(f"   -> Buscando {faltantes} imagen(es) relacionadas con el artículo...")

        for i, query in enumerate(queries[:faltantes]):
            ruta_foto = str(carpeta / f"repo_{i}.jpg")
            ruta_ai = str(carpeta / f"ai_{i}.jpg")

            # Intentar repositorios de fotos reales primero
            r = _buscar_foto_repositorios(query, ruta_foto)
            if r:
                imagenes.append(r)
                continue

            # Fallback: generar con IA si el usuario lo activó explícitamente
            # O siempre con Pollinations (gratis) para garantizar imágenes relevantes
            if generar_ai or servicio_ai == "pollinations" or not os.path.exists(ruta_foto):
                r = _generar_pollinations(query, ruta_ai, seed=abs(hash(query + str(i))) % 99999)
                if r:
                    imagenes.append(r)

            if len(imagenes) >= n_ai:
                break

    return imagenes
