"""
image_pipeline.py
Gestiona las imágenes de fondo para los reels:
  - Extrae imágenes del artículo (scraping)
  - Genera imágenes con IA via Pollinations.ai (gratis, sin API key)
  - Descarga imágenes desde URL
"""
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

ANCHO, ALTO = 1080, 1920
_TMP_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "_img_cache"


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

    # Capa oscura semi-transparente para que el texto se lea bien
    from PIL import ImageDraw
    overlay = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, overlay, 0.45)

    img.save(ruta, "JPEG", quality=90)
    return ruta


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
        # Filtrar íconos y logos pequeños
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
            ext = "jpg"
            nombre = carpeta / f"art_img_{i}.{ext}"
            r = requests.get(img_url, timeout=10, headers=headers)
            r.raise_for_status()
            with open(nombre, "wb") as f:
                f.write(r.content)
            # Verificar que es una imagen válida y lo suficientemente grande
            img = Image.open(nombre)
            if img.width < 300 or img.height < 200:
                os.unlink(nombre)
                continue
            img.close()
            _redimensionar_para_video(str(nombre))
            rutas.append(str(nombre))
        except Exception as e:
            print(f"[WARN image] No se pudo descargar {img_url}: {e}")
            continue

    return rutas


def generar_imagen_ai(
    prompt: str,
    ruta_salida: str,
    servicio: str = "pollinations",
    seed: Optional[int] = None,
    api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Genera una imagen con IA relacionada al prompt.

    Servicios soportados:
      - "pollinations"  → Pollinations.ai (gratis, sin API key, FLUX)
      - "pexels"        → Busca foto real en Pexels (requiere PEXELS_API_KEY)
    """
    if servicio == "pollinations":
        return _generar_pollinations(prompt, ruta_salida, seed)
    elif servicio == "pexels":
        key = api_key or os.environ.get("PEXELS_API_KEY", "")
        if not key:
            print("[WARN image] PEXELS_API_KEY no configurada, usando pollinations")
            return _generar_pollinations(prompt, ruta_salida, seed)
        return _generar_pexels(prompt, ruta_salida, key)
    else:
        return _generar_pollinations(prompt, ruta_salida, seed)


def _generar_pollinations(prompt: str, ruta_salida: str, seed: Optional[int] = None) -> Optional[str]:
    """
    Genera imagen con Pollinations.ai (FLUX, gratis, sin API key).
    """
    prompt_limpio = re.sub(r"[^\w\s,.-]", " ", prompt).strip()
    prompt_enc = urllib.parse.quote(f"{prompt_limpio}, cinematic, dark background, vertical portrait")

    _seed = seed if seed is not None else hash(prompt) % 9999
    url = (
        f"https://image.pollinations.ai/prompt/{prompt_enc}"
        f"?width=1080&height=1920&seed={_seed}&nologo=true&model=flux"
    )

    print(f"   -> Generando imagen con Pollinations.ai (FLUX)...")
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(ruta_salida, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        # Verificar que se descargó bien
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


def _generar_pexels(query: str, ruta_salida: str, api_key: str) -> Optional[str]:
    """Descarga foto de Pexels relacionada al tema."""
    import random
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "orientation": "portrait", "per_page": 10},
            headers={"Authorization": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        fotos = resp.json().get("photos", [])
        if not fotos:
            return None
        foto = random.choice(fotos[:5])
        img_url = foto["src"]["portrait"]
        r = requests.get(img_url, timeout=15)
        r.raise_for_status()
        with open(ruta_salida, "wb") as f:
            f.write(r.content)
        _redimensionar_para_video(ruta_salida)
        return ruta_salida
    except Exception as e:
        print(f"[WARN image] Pexels falló: {e}")
        return None


def preparar_imagenes(
    titulo: str,
    url_articulo: str = None,
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
    3. Generadas con IA

    Devuelve lista de rutas locales listas para usar como fondo del video.
    """
    _mkdir()
    carpeta = Path(carpeta_tmp) if carpeta_tmp else _TMP_DIR
    carpeta.mkdir(exist_ok=True)

    imagenes = []

    # 1. Imágenes del usuario
    if rutas_usuario:
        for ruta in rutas_usuario:
            if os.path.isfile(ruta):
                try:
                    dest = str(carpeta / f"usr_{Path(ruta).name}")
                    import shutil
                    shutil.copy2(ruta, dest)
                    _redimensionar_para_video(dest)
                    imagenes.append(dest)
                except Exception as e:
                    print(f"[WARN image] No se pudo procesar {ruta}: {e}")

    # 2. Imágenes del artículo
    if url_articulo and len(imagenes) < 4:
        print("   -> Extrayendo imágenes del artículo...")
        imgs_art = extraer_imagenes_articulo(url_articulo, max_imgs=4 - len(imagenes), carpeta=str(carpeta))
        imagenes.extend(imgs_art)
        if imgs_art:
            print(f"   -> {len(imgs_art)} imagen(es) extraída(s) del artículo")

    # 3. Generar con IA
    if generar_ai and len(imagenes) < n_ai:
        faltantes = n_ai - len(imagenes)
        for i in range(faltantes):
            ruta_img = str(carpeta / f"ai_img_{i}.jpg")
            resultado = generar_imagen_ai(
                prompt=titulo,
                ruta_salida=ruta_img,
                servicio=servicio_ai,
                seed=i * 37,
            )
            if resultado:
                imagenes.append(resultado)

    return imagenes
