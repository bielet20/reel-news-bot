#!/usr/bin/env python3
"""
Captura las cookies de TikTok abriendo un navegador para iniciar sesión.
Ejecutar UNA VEZ en el host (fuera de Docker):

    python3 scripts/tiktok_login.py

Guarda las cookies en _config/tiktok_cookies.json para que el bot
pueda subir videos sin OAuth ni portal de desarrolladores.
"""
import json
import pathlib
import subprocess
import sys

COOKIES_FILE = pathlib.Path(__file__).parent.parent / "_config" / "tiktok_cookies.json"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Instalando playwright…")
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    from playwright.sync_api import sync_playwright


def main():
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("Abriendo navegador… Inicia sesión en TikTok normalmente.")
    print("Cuando estés en el feed principal, vuelve aquí y pulsa ENTER.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-web-security"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")

        input(">>> Pulsa ENTER cuando hayas iniciado sesión en TikTok… ")

        cookies = ctx.cookies()
        tiktok_cookies = [
            c for c in cookies if "tiktok.com" in c.get("domain", "")
        ]
        browser.close()

    if not tiktok_cookies:
        print("ERROR: no se encontraron cookies de TikTok. ¿Iniciaste sesión?")
        sys.exit(1)

    COOKIES_FILE.write_text(json.dumps(tiktok_cookies, indent=2), encoding="utf-8")
    print(f"\n✓ {len(tiktok_cookies)} cookies guardadas en {COOKIES_FILE}")
    print("Ya puedes subir vídeos a TikTok desde el gestor.")


if __name__ == "__main__":
    main()
