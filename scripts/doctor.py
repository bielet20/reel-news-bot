#!/usr/bin/env python3
"""
doctor.py — chequeo rápido del entorno de reel-news-bot.

Comprueba lo que suele romper el pipeline sin que el error sea obvio:
binarios del sistema, dependencias de Python, frescura de yt-dlp, ficheros de
config y si los servicios del host (ComfyUI / LM Studio / Centro de Control)
responden.

    python scripts/doctor.py            # todo
    python scripts/doctor.py --montaje  # solo lo que necesita el Montaje con vídeo IA

Los chequeos de ComfyUI / LM Studio / Centro de Control usan
`host.docker.internal`, así que para que tengan sentido hay que correrlo DENTRO
del contenedor del backend:

    docker compose exec backend python scripts/doctor.py

Sale con código 1 si hay algún fallo BLOQUEANTE (los avisos no cuentan).
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# La consola de Windows (cp1252) revienta con acentos; forzamos UTF-8 tolerante.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

OK, WARN, FAIL = "  ok  ", " aviso", " FALLO"
_fallos = 0
_avisos = 0


def _linea(estado: str, msg: str, detalle: str = "") -> None:
    global _fallos, _avisos
    if estado == FAIL:
        _fallos += 1
    elif estado == WARN:
        _avisos += 1
    print(f"[{estado}] {msg}" + (f"  — {detalle}" if detalle else ""))


def check_python() -> None:
    v = sys.version_info
    if (v.major, v.minor) >= (3, 11):
        _linea(OK, f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _linea(FAIL, f"Python {v.major}.{v.minor}", "hace falta 3.11+")


def check_binario(nombre: str, bloqueante: bool = True) -> None:
    ruta = shutil.which(nombre)
    if ruta:
        _linea(OK, f"{nombre} en PATH", ruta)
    else:
        _linea(FAIL if bloqueante else WARN, f"{nombre} no está en PATH")


def check_import(mod: str, bloqueante: bool = True, pista: str = "") -> bool:
    try:
        m = importlib.import_module(mod)
        ver = getattr(m, "__version__", "")
        _linea(OK, f"import {mod}", str(ver))
        return True
    except Exception as e:  # noqa: BLE001
        _linea(FAIL if bloqueante else WARN, f"import {mod} falló",
               pista or f"{type(e).__name__}: {e}")
        return False


def check_ytdlp() -> None:
    """yt-dlp por CLI (así lo usa video_clipper) + aviso si va por detrás del
    floor de requirements.txt — YouTube rompe compatibilidad a menudo."""
    exe = shutil.which("yt-dlp")
    if not exe:
        _linea(FAIL, "yt-dlp no está en PATH")
        return
    try:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=20).stdout.strip()
    except (subprocess.SubprocessError, OSError) as e:
        _linea(FAIL, "yt-dlp no ejecuta", str(e))
        return
    floor = ""
    req = RAIZ / "requirements.txt"
    if req.exists():
        for ln in req.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("yt-dlp>="):
                floor = ln.split(">=", 1)[1].split()[0].split("#")[0].strip()
    if floor and _norm_ver(v) < _norm_ver(floor):
        _linea(WARN, f"yt-dlp {v}", f"por debajo del floor {floor} — "
               f"`pip install --upgrade yt-dlp` dentro del venv")
    else:
        _linea(OK, f"yt-dlp {v}")


def _norm_ver(s: str) -> tuple:
    out = []
    for parte in s.replace("-", ".").split("."):
        try:
            out.append(int(parte))
        except ValueError:
            out.append(0)
    return tuple(out)


def check_ficheros() -> None:
    if (RAIZ / ".env").exists():
        _linea(OK, ".env presente")
    elif (RAIZ / ".env.example").exists():
        _linea(WARN, "no hay .env", "copia .env.example a .env (todas las claves son opcionales)")
    for carpeta in ("output", "_uploads"):
        p = RAIZ / carpeta
        try:
            p.mkdir(exist_ok=True)
            probe = p / ".doctor_write_test"
            probe.write_text("x")
            probe.unlink()
            _linea(OK, f"{carpeta}/ escribible")
        except OSError as e:
            _linea(FAIL, f"{carpeta}/ no escribible", str(e))


def check_servicios_montaje() -> None:
    try:
        import comfy_video_builder as cvb
    except Exception as e:  # noqa: BLE001
        _linea(FAIL, "no se pudo importar comfy_video_builder", str(e))
        return

    _linea(OK if cvb.comfy_disponible() else WARN,
           f"ComfyUI ({cvb.COMFY_URL})",
           "" if cvb.comfy_disponible() else "apagado — arráncalo o usa el generador «Imagen fija»")

    cc = cvb.control_center_disponible()
    _linea(OK if cc else WARN, f"Centro de Control ({cvb.CONTROL_CENTER_URL})",
           "" if cc else "sin él, no hay botón de arrancar ni auto-reinicio de ComfyUI")

    try:
        import requests
        lm = requests.get(f"{cvb.LLM_BASE_URL}/models", timeout=4).status_code == 200
    except Exception:  # noqa: BLE001
        lm = False
    tiene_api = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY"))
    if lm:
        _linea(OK, f"LM Studio ({cvb.LLM_BASE_URL})")
    elif tiene_api:
        _linea(WARN, "LM Studio apagado", "hay ANTHROPIC/GEMINI key para el guion, ok")
    else:
        _linea(WARN, "LM Studio apagado y sin API key",
               "el guion visual del Montaje fallará (wan22/ltx)")

    if cvb.comfy_disponible():
        estado = cvb.verificar_herramientas()
        for prov in estado["providers"]:
            if prov["id"] in ("wan22", "ltx"):
                _linea(OK if prov["disponible"] else WARN,
                       f"generador {prov['id']}",
                       "" if prov["disponible"] else prov["nota"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--montaje", action="store_true",
                    help="solo los chequeos del Montaje con vídeo IA")
    args = ap.parse_args()

    if not args.montaje:
        print("--- Base --------------------------------------------")
        check_python()
        check_binario("ffmpeg")
        check_binario("ffprobe")
        check_ytdlp()
        print("--- Dependencias de Python -------------------------")
        check_import("requests")
        check_import("fastapi")
        check_import("moviepy.editor", pista="pip install -r requirements.txt")
        check_import("PIL")
        check_import("numpy")
        check_import("faster_whisper", bloqueante=False,
                     pista="sin el, la letra del Montaje va a reparto uniforme")
        check_import("librosa", bloqueante=False,
                     pista="sin el, no hay deteccion de voz hombre/mujer")
        print("--- Ficheros y permisos ---------------------------")
        check_ficheros()

    print("--- Montaje con video IA (servicios del host) ------")
    check_servicios_montaje()

    print("---------------------------------------------------")
    print(f"Resultado: {_fallos} fallo(s), {_avisos} aviso(s).")
    if _fallos:
        print("Hay fallos bloqueantes: revisa las líneas [ FALLO].")
        return 1
    print("Entorno OK (los avisos no bloquean el pipeline).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
