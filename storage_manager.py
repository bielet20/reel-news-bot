"""
storage_manager.py
Copia videos generados a los destinos configurados: local, Google Drive (rclone), red SMB.
Config almacenada en _config/storage.json
"""
import os
import json
import shutil
import subprocess
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "_config" / "storage.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"destinations": []}


def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def copy_to_destinations(video_path: str) -> list[dict]:
    """Copia el video a todos los destinos activos. Devuelve lista de resultados."""
    cfg = load_config()
    results = []
    for dest in cfg.get("destinations", []):
        if not dest.get("enabled", True):
            continue
        try:
            r = _copy_to(video_path, dest)
            results.append({"dest": dest["name"], "ok": True, **r})
        except Exception as e:
            results.append({"dest": dest["name"], "ok": False, "error": str(e)})
    return results


def _copy_to(video_path: str, dest: dict) -> dict:
    tipo = dest["type"]
    if tipo == "local":
        dst = Path(dest["path"]) / Path(video_path).name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video_path, dst)
        return {"path": str(dst)}
    elif tipo in ("drive", "smb"):
        # Requiere rclone instalado y configurado
        remote = dest["rclone_remote"]  # e.g. "gdrive:Reels" o "nas:Videos/Reels"
        cmd = ["rclone", "copy", video_path, remote, "--progress"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr or r.stdout)
        return {"remote": remote}
    else:
        raise ValueError(f"Tipo de destino desconocido: {tipo}")
