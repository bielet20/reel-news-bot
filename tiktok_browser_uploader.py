"""
tiktok_browser_uploader.py
Sube vídeos a TikTok usando cookies de sesión del navegador (sin OAuth).

Flujo:
  1. El usuario ejecuta UNA VEZ: python3 scripts/tiktok_login.py
     → guarda cookies en _config/tiktok_cookies.json
  2. Este módulo usa esas cookies + Playwright headless para subir vídeos
     desde el Creator Center de TikTok.
"""
import json
import time
from pathlib import Path

COOKIES_FILE = Path("/app/_config/tiktok_cookies.json")
_UPLOAD_URL = "https://www.tiktok.com/creator-center/upload?lang=en"


def _load_cookies() -> list:
    if not COOKIES_FILE.exists():
        raise RuntimeError(
            "No hay cookies de TikTok guardadas. "
            "Ejecuta: python3 scripts/tiktok_login.py"
        )
    data = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    if not data:
        raise RuntimeError("Archivo de cookies vacío. Vuelve a ejecutar tiktok_login.py")
    return data


def get_account_info() -> dict:
    """Devuelve estado de conexión basado en cookies guardadas."""
    try:
        cookies = _load_cookies()
        # Intentar extraer el username de las cookies
        display_name = None
        for c in cookies:
            if c.get("name") in ("nickname", "tt_chain_token"):
                pass
            if c.get("name") == "d_ticket":
                display_name = "TikTok (cookies)"
        return {
            "connected": True,
            "display_name": display_name or "TikTok (cookies)",
            "method": "cookies",
        }
    except RuntimeError as e:
        return {"connected": False, "error": str(e)}


def upload_video(video_path: str, titulo: str = "", privacy: str = "PUBLIC_TO_EVERYONE") -> dict:
    """
    Sube un vídeo a TikTok via Creator Center con Playwright headless.

    Args:
        video_path: Ruta absoluta al archivo MP4 dentro del container.
        titulo: Caption (max 2200 chars).
        privacy: PUBLIC_TO_EVERYONE | SELF_ONLY | MUTUAL_FOLLOW_FRIENDS

    Returns:
        {"ok": True, "method": "browser"}
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

    cookies = _load_cookies()
    fp = Path(video_path)
    if not fp.exists():
        raise RuntimeError(f"Vídeo no encontrado: {video_path}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        # Eliminar la firma de webdriver para evitar detección
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        try:
            print(f"[TikTok] Navegando al Creator Center…")
            page.goto(_UPLOAD_URL, timeout=30_000, wait_until="domcontentloaded")
            time.sleep(3)

            # Si nos redirige al login, las cookies expiraron
            if "login" in page.url.lower():
                raise RuntimeError(
                    "Cookies de TikTok expiradas. "
                    "Vuelve a ejecutar: python3 scripts/tiktok_login.py"
                )

            # TikTok carga el uploader en un iframe (creator-center usa un iframe interno)
            # Esperamos a que aparezca el input de archivo
            target = page
            try:
                # Esperar iframe de upload si existe
                page.wait_for_selector(
                    "iframe[src*='upload'], iframe[src*='creator']",
                    timeout=8_000,
                )
                frames = [f for f in page.frames if "upload" in (f.url or "")]
                if frames:
                    target = frames[0]
            except PwTimeout:
                pass  # Sin iframe — usamos la página directamente

            # Esperar y localizar el input de archivo
            print("[TikTok] Esperando input de archivo…")
            file_input = target.locator("input[type='file']").first
            file_input.wait_for(timeout=15_000)
            file_input.set_input_files(str(fp))
            print(f"[TikTok] Archivo seleccionado: {fp.name}")

            # Esperar a que el vídeo se procese (barra de progreso desaparece)
            print("[TikTok] Procesando vídeo…")
            time.sleep(8)

            # Rellenar caption
            caption_texto = (titulo or fp.stem.replace("_", " "))[:2200]
            try:
                cap = target.locator(
                    "[data-e2e='caption-input'], "
                    ".public-DraftEditor-content, "
                    "div[contenteditable='true']"
                ).first
                cap.wait_for(timeout=10_000)
                cap.click()
                cap.fill(caption_texto)
                print(f"[TikTok] Caption: {caption_texto[:60]}…")
            except PwTimeout:
                print("[TikTok] WARN: no se encontró el campo de caption")

            # Esperar a que el botón Post esté habilitado
            time.sleep(3)

            # Pulsar "Post"
            post_btn = target.locator(
                "button[data-e2e='post-btn'], "
                "button:has-text('Post'), "
                "button:has-text('Publicar')"
            ).first
            post_btn.wait_for(timeout=10_000)
            post_btn.click()
            print("[TikTok] Botón Post pulsado")

            # Esperar confirmación
            time.sleep(6)

            # Comprobar si hubo error
            error_el = page.locator("[data-e2e='upload-error'], .error-message").first
            try:
                error_el.wait_for(timeout=2_000)
                error_text = error_el.inner_text()
                raise RuntimeError(f"TikTok rechazó el vídeo: {error_text}")
            except PwTimeout:
                pass  # Sin error → éxito

            print("[TikTok] Vídeo publicado correctamente")
            return {"ok": True, "method": "browser"}

        finally:
            browser.close()
