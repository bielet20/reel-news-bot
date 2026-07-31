"""
avatar_generator.py
Genera un video de avatar hablando sincronizado con el audio (lip sync).

Servicios soportados:
  - "sadtalker"  → Local, gratuito. Requiere setup previo (bash setup_sadtalker.sh)
  - "did"        → D-ID API (cloud). Requiere DID_API_KEY en .env. Tiene plan gratuito.
  - "auto"       → Prueba D-ID primero (si hay API key), luego SadTalker
"""
import os
import re
import sys
import time
import uuid
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

_AQUI = Path(__file__).parent
ST_DIR = _AQUI / "vendor" / "sadtalker"
ST_INFERENCE = ST_DIR / "inference.py"
AVATARES_DIR = _AQUI / "assets" / "avatars"
AVATARES_DIR.mkdir(parents=True, exist_ok=True)

# En Docker, SADTALKER_VENV apunta a /opt/sadtalker_venv (CUDA, fuera de /app).
# En local, se usa vendor/sadtalker/venv/ (MPS en Mac, CPU en Linux sin GPU).
_st_venv_env = os.environ.get("SADTALKER_VENV")
if _st_venv_env:
    ST_PYTHON = Path(_st_venv_env) / "bin" / "python"
else:
    ST_PYTHON = ST_DIR / "venv" / "bin" / "python"


# ──────────────────────────────────────────────
#  Verificación de estado
# ──────────────────────────────────────────────

def sadtalker_instalado() -> bool:
    checkpoints_ok = (ST_DIR / "checkpoints").exists() and any((ST_DIR / "checkpoints").iterdir())
    return ST_PYTHON.exists() and ST_INFERENCE.exists() and checkpoints_ok


def did_disponible() -> bool:
    return bool(os.environ.get("DID_API_KEY"))


def estado() -> dict:
    return {
        "sadtalker": sadtalker_instalado(),
        "did": did_disponible(),
    }


# ──────────────────────────────────────────────
#  D-ID (cloud)
# ──────────────────────────────────────────────

def _did_auth_header(api_key: str) -> str:
    """Genera el header Authorization correcto para D-ID (Basic base64(key:))."""
    import base64
    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
    return f"Basic {encoded}"


def _did_subir_imagen(ruta_img: str, api_key: str) -> str:
    """Sube imagen a D-ID y devuelve la URL."""
    import requests
    url = "https://api.d-id.com/images"
    with open(ruta_img, "rb") as f:
        resp = requests.post(
            url,
            headers={"Authorization": _did_auth_header(api_key)},
            files={"image": f},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()["url"]


def _did_subir_audio(ruta_audio: str, api_key: str) -> str:
    """Sube audio a D-ID y devuelve la URL."""
    import requests
    url = "https://api.d-id.com/audios"
    with open(ruta_audio, "rb") as f:
        resp = requests.post(
            url,
            headers={"Authorization": _did_auth_header(api_key)},
            files={"audio": f},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()["url"]


def generar_con_did(
    ruta_imagen: str,
    ruta_audio: str,
    ruta_salida: str,
    api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Genera video de avatar hablando via D-ID API.
    Requiere DID_API_KEY (plan gratuito: ~10 créditos/mes).
    https://www.d-id.com
    """
    import requests

    api_key = api_key or os.environ.get("DID_API_KEY", "")
    if not api_key:
        print("[WARN avatar] DID_API_KEY no configurada.")
        return None

    auth_header = _did_auth_header(api_key)

    try:
        print("   -> Subiendo imagen a D-ID...")
        img_url = _did_subir_imagen(ruta_imagen, api_key)

        print("   -> Subiendo audio a D-ID...")
        audio_url = _did_subir_audio(ruta_audio, api_key)

        print("   -> Creando talk en D-ID...")
        body = {
            "source_url": img_url,
            "script": {
                "type": "audio",
                "audio_url": audio_url,
            },
            "config": {
                "stitch": True,
                "result_format": "mp4",
            },
        }
        resp = requests.post(
            "https://api.d-id.com/talks",
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        talk_id = resp.json()["id"]

        # Esperar resultado (polling)
        print("   -> Esperando resultado de D-ID", end="", flush=True)
        for _ in range(60):
            time.sleep(3)
            r = requests.get(
                f"https://api.d-id.com/talks/{talk_id}",
                headers={"Authorization": auth_header},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            print(".", end="", flush=True)
            if status == "done":
                print()
                video_url = data["result_url"]
                break
            elif status == "error":
                print(f"\n[ERROR] D-ID: {data.get('error')}")
                return None
        else:
            print("\n[ERROR] D-ID timeout esperando resultado.")
            return None

        # Descargar video
        print("   -> Descargando video de D-ID...")
        r = requests.get(video_url, timeout=60, stream=True)
        r.raise_for_status()
        with open(ruta_salida, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        print(f"   -> Avatar D-ID listo: {ruta_salida}")
        return ruta_salida

    except Exception as e:
        print(f"[ERROR] D-ID falló: {e}")
        return None


# ──────────────────────────────────────────────
#  SadTalker (local)
# ──────────────────────────────────────────────

def generar_con_sadtalker(
    ruta_imagen: str,
    ruta_audio: str,
    ruta_salida: str,
    tam: int = 256,
    preprocess: str = "crop",
    usar_cpu: bool = False,
) -> Optional[str]:
    """
    Genera video de avatar hablando localmente con SadTalker.
    Requiere haber ejecutado: bash setup_sadtalker.sh
    """
    if not sadtalker_instalado():
        print("[WARN avatar] SadTalker no instalado. Ejecuta: bash setup_sadtalker.sh")
        return None

    carpeta_tmp = tempfile.mkdtemp(prefix="_st_")
    try:
        cmd = [
            str(ST_PYTHON),
            str(ST_INFERENCE),
            "--driven_audio", str(ruta_audio),
            "--source_image", str(ruta_imagen),
            "--result_dir", carpeta_tmp,
            "--still",
            "--preprocess", preprocess,
            "--size", str(tam),
            "--expression_scale", "1.0",
        ]
        if usar_cpu:
            cmd.append("--cpu")

        import torch
        if usar_cpu:
            modo = "CPU"
        elif torch.backends.mps.is_available():
            modo = "MPS (Apple Silicon GPU)"
        elif torch.cuda.is_available():
            modo = "CUDA GPU"
        else:
            modo = "CPU"
        print(f"   -> Ejecutando SadTalker (modo {modo})...")
        print(f"      Esto puede tardar 1-5 min según el hardware.")

        result = subprocess.run(
            cmd,
            cwd=str(ST_DIR),
            capture_output=True,
            text=True,
            timeout=900,
        )

        if result.returncode != 0:
            print(f"[ERROR] SadTalker falló:\n{result.stderr[-1000:]}")
            return None

        # SadTalker guarda el video en result_dir con nombre derivado de la imagen
        videos = list(Path(carpeta_tmp).rglob("*.mp4"))
        if not videos:
            print("[ERROR] SadTalker no generó ningún mp4.")
            return None

        shutil.copy2(str(videos[0]), ruta_salida)
        print(f"   -> Avatar SadTalker listo: {ruta_salida}")
        return ruta_salida

    except subprocess.TimeoutExpired:
        print("[ERROR] SadTalker timeout (>10 min).")
        return None
    except Exception as e:
        print(f"[ERROR] SadTalker excepción: {e}")
        return None
    finally:
        shutil.rmtree(carpeta_tmp, ignore_errors=True)


# ──────────────────────────────────────────────
#  Función principal
# ──────────────────────────────────────────────

def generar_avatar(
    ruta_imagen: str,
    ruta_audio: str,
    ruta_salida: str,
    servicio: str = "auto",
    did_api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Pipeline de generación de avatar. Selector de servicio:
      "auto"       → D-ID si hay key, si no SadTalker
      "did"        → Solo D-ID
      "sadtalker"  → Solo SadTalker
    """
    if not os.path.isfile(ruta_imagen):
        print(f"[ERROR avatar] Imagen no encontrada: {ruta_imagen}")
        return None

    if servicio == "did" or (servicio == "auto" and did_disponible()):
        resultado = generar_con_did(ruta_imagen, ruta_audio, ruta_salida, api_key=did_api_key)
        if resultado:
            return resultado
        if servicio == "did":
            return None
        print("   -> D-ID falló, intentando SadTalker...")

    if servicio in ("sadtalker", "auto"):
        return generar_con_sadtalker(ruta_imagen, ruta_audio, ruta_salida)

    return None
