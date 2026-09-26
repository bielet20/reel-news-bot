"""
video_ia.py
Fondos de VÍDEO EN MOVIMIENTO para los reels, generados en local:

  guion ──(LLM del Mac)──► escenas (prompt de imagen + movimiento)
        ──(Flux schnell)──► una imagen por escena
        ──(LTX-Video img→vídeo)──► un clip de ~4 s por escena

Todas las imágenes se generan primero y luego todos los clips (un solo cambio
de modelo en la GPU). Antes se descarga el LM Studio del PC y se toma el
bloqueo de GPU, para que dos trabajos de ComfyUI nunca compitan.
Si una escena falla, se queda con su imagen fija (el reel no se pierde).

Medido en la RTX 5070 Ti: ~28 s por imagen y ~29 s por clip con los modelos ya
cargados; un reel de 55 s (11 escenas) ≈ 15-18 min en total.

Uso desde línea de comandos (pasar a vídeo IA un reel ya generado):
  python video_ia.py <nombre>_reel.mp4
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path

ESTILO = "cinematic, photorealistic, dramatic lighting, vibrant colors, high detail, no text, no letters"
SEGUNDOS_POR_ESCENA = 5.0
GPU_LOCK = Path(os.environ.get("GPU_LOCK_FILE", "/app/output/.gpu.lock"))


def _log(msg: str) -> None:
    print(f"   [video-ia] {msg}", flush=True)


@contextlib.contextmanager
def bloqueo_gpu(motivo: str = ""):
    """Un solo trabajo de ComfyUI a la vez entre todos los procesos del
    contenedor (generaciones de reels, portadas, vídeo IA)."""
    try:
        import fcntl
    except ImportError:  # Windows sin Docker: sin bloqueo
        yield
        return
    GPU_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(GPU_LOCK, "w") as f:
        t = time.time()
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _log(f"GPU ocupada por otro trabajo; espero turno ({motivo})")
            fcntl.flock(f, fcntl.LOCK_EX)
            _log(f"turno conseguido tras {time.time() - t:.0f} s")
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _escenas(guion: str, n: int) -> list[dict]:
    import comfy_video_builder as c
    from llm_local import completar
    raw = completar(
        f"Divide este guion de reel de noticias en EXACTAMENTE {n} escenas consecutivas de igual duración. "
        "Para cada una escribe, EN INGLÉS, un prompt de imagen fotorrealista y concreto (sujeto, acción, "
        "lugar, luz; sin texto ni letras) y un prompt corto de movimiento de cámara/acción. "
        "Mantén coherencia visual entre escenas.\n"
        'Responde SOLO JSON: {"escenas": [{"image": "...", "motion": "..."}]}\n\n'
        f"GUION:\n{guion}", max_tokens=3000, temperature=0.6)
    escenas = [e for e in c._json_lenient(raw).get("escenas", []) if e.get("image")][:n]
    if not escenas:
        raise RuntimeError("el LLM no devolvió escenas")
    while len(escenas) < n:
        escenas.append(escenas[len(escenas) % max(1, len(escenas))])
    return escenas


def _wf_flux_schnell(prompt: str, seed: int) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 576, "height": 1024, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["5", 0],
            "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
            "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "videoia_escena"}},
    }


def _wf_ltx_i2v(image_name: str, prompt: str, seed: int) -> dict:
    import comfy_video_builder as c
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": c.LTX_UNET}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": c.LTX_VAE}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": c.LTX_T5, "type": "ltxv"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": c.LTX_NEGATIVE, "clip": ["3", 0]}},
        "14": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "6": {"class_type": "LTXVImgToVideo", "inputs": {
            "positive": ["4", 0], "negative": ["5", 0], "vae": ["2", 0], "image": ["14", 0],
            "width": 512, "height": 896, "length": 97, "batch_size": 1, "strength": 1.0}},
        "7": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["6", 0], "negative": ["6", 1], "frame_rate": float(c.LTX_FPS)}},
        "8": {"class_type": "LTXVScheduler", "inputs": {
            "steps": c.LTX_STEPS, "max_shift": 2.05, "base_shift": 0.95,
            "stretch": True, "terminal": 0.1, "latent": ["6", 2]}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "SamplerCustom", "inputs": {
            "model": ["1", 0], "add_noise": True, "noise_seed": seed, "cfg": c.LTX_CFG,
            "positive": ["7", 0], "negative": ["7", 1],
            "sampler": ["9", 0], "sigmas": ["8", 0], "latent_image": ["6", 2]}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["2", 0]}},
        "12": {"class_type": "CreateVideo", "inputs": {"images": ["11", 0], "fps": c.LTX_FPS}},
        "13": {"class_type": "SaveVideo", "inputs": {
            "video": ["12", 0], "filename_prefix": "videoia_clip", "format": "auto", "codec": "auto"}},
    }


def generar_clips(guion: str, duracion: float, carpeta: str | Path) -> list[str]:
    """Clips de vídeo (o imágenes, si una escena falla) para usar como fondo.
    Lanza RuntimeError si no hay ComfyUI o LLM: el llamador cae al modo rápido."""
    import comfy_video_builder as c
    from llm_local import liberar_gpu_para_video

    if not c.comfy_disponible():
        raise RuntimeError("ComfyUI no está encendido")
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    n = max(4, round(duracion / SEGUNDOS_POR_ESCENA))
    t0 = time.time()
    escenas = _escenas(guion, n)
    _log(f"{n} escenas ({time.time() - t0:.0f} s)")

    with bloqueo_gpu("vídeo IA"):
        liberar_gpu_para_video()
        imagenes = []
        for i, e in enumerate(escenas):
            t = time.time()
            wf = _wf_flux_schnell(f"{e['image']}, {ESTILO}", 1000 + i)
            info = c._first_output(c.comfy_wait(c.comfy_queue(wf), timeout=900), "8")
            p = carpeta / f"escena_{i:02d}.png"
            c.comfy_download(info["filename"], info.get("subfolder", ""), info["type"], p)
            imagenes.append(p)
            _log(f"imagen {i + 1}/{n} ({time.time() - t:.0f} s)")

        clips = []
        for i, (e, img) in enumerate(zip(escenas, imagenes)):
            t = time.time()
            try:
                wf = _wf_ltx_i2v(c.comfy_upload_image(img),
                                 f"{e['image']}, {e.get('motion', '')}, {ESTILO}", 2000 + i)
                info = c._first_output(c.comfy_wait(c.comfy_queue(wf), timeout=1800), "13")
                p = carpeta / f"clip_{i:02d}.mp4"
                c.comfy_download(info["filename"], info.get("subfolder", ""), info["type"], p)
                clips.append(str(p))
                _log(f"clip {i + 1}/{n} ({time.time() - t:.0f} s)")
            except Exception as ex:  # noqa: BLE001
                clips.append(str(img))
                _log(f"clip {i + 1}/{n} falló ({ex}); la escena queda con su imagen")
    _log(f"fondos listos en {time.time() - t0:.0f} s")
    return clips


def pasar_reel_a_video_ia(video_filename: str, carpeta_salida: str = "/app/output") -> str:
    """Rehace un reel narrado ya generado con fondos de vídeo IA, reutilizando
    su guion y su voz. El reel anterior se guarda como .<nombre>.rapido.mp4."""
    import shutil
    import tempfile
    import comfy_video_builder as c
    from video_builder import construir_video

    out = Path(carpeta_salida)
    video = out / video_filename
    slug = re.sub(r"_reel$", "", video.stem)
    guion_f = out / f"{slug}_guion_reel.txt"
    audio_f = out / f"{slug}_audio_reel.mp3"
    if not (guion_f.exists() and audio_f.exists()):
        raise RuntimeError("Este reel no tiene guion y voz guardados (solo se pueden pasar a vídeo IA "
                           "los reels narrados de noticias)")
    cab, _, guion = guion_f.read_text(encoding="utf-8").partition("\n\n")
    m = re.search(r"^Titulo:\s*(.+)$", cab, re.M)
    titulo = m.group(1).strip() if m else slug.replace("-", " ")
    dur = c.probe_duration(audio_f, 55.0)

    tmp = Path(tempfile.mkdtemp(prefix="_videoia_", dir=str(out)))
    try:
        clips = generar_clips(guion.strip(), dur, tmp)
        nuevo = out / f".{slug}_reel.nuevo.mp4"
        construir_video({"titulo": titulo, "guion": guion.strip()}, str(audio_f), str(nuevo),
                        imagenes=clips, mostrar_titulo=True, mostrar_subtitulos=True,
                        marca=os.environ.get("CANAL_NOMBRE") or None)
        if video.exists():
            video.replace(out / f".{slug}.rapido.mp4")
        nuevo.replace(video)
        (out / f"{slug}_video_ia.json").write_text(
            json.dumps({"escenas": len(clips), "generado": time.strftime("%Y-%m-%d %H:%M:%S")}),
            encoding="utf-8")
        return str(video)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    print(pasar_reel_a_video_ia(sys.argv[1]))
