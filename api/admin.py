"""
api/admin.py
Gestión de contraseña de administrador de la app.
"""
import hashlib
import json
import secrets
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

CONFIG_DIR = Path(__file__).parent.parent / "_config"
ADMIN_FILE = CONFIG_DIR / "admin.json"


def _load() -> dict:
    if ADMIN_FILE.exists():
        try:
            return json.loads(ADMIN_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    ADMIN_FILE.write_text(json.dumps(data, indent=2), "utf-8")


def _hash(pw: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pw}".encode()).hexdigest()


def verify_admin_password(password: str) -> bool:
    cfg = _load()
    if not cfg.get("hash"):
        return False
    return _hash(password, cfg["salt"]) == cfg["hash"]


class SetPasswordReq(BaseModel):
    password: str
    current_password: str = ""


class VerifyReq(BaseModel):
    password: str


@router.get("/api/admin/status")
def admin_status():
    return {"configured": bool(_load().get("hash"))}


@router.post("/api/admin/set-password")
def set_password(req: SetPasswordReq):
    cfg = _load()
    if cfg.get("hash"):
        if not verify_admin_password(req.current_password):
            return {"ok": False, "error": "Contraseña actual incorrecta"}
    if len(req.password) < 4:
        return {"ok": False, "error": "Mínimo 4 caracteres"}
    salt = secrets.token_hex(16)
    _save({"salt": salt, "hash": _hash(req.password, salt)})
    return {"ok": True}


@router.post("/api/admin/verify")
def verify(req: VerifyReq):
    return {"ok": verify_admin_password(req.password)}
