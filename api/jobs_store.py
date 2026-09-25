"""
api/jobs_store.py
Estado compartido de jobs en memoria — evita que gestor.py haga HTTP a sí mismo.
"""
import threading
from typing import Callable, Optional

jobs: dict = {}
jobs_lock = threading.Lock()

# server.py registra esta función al arrancar; gestor.py la llama directamente
# para iniciar un job sin pasar por HTTP.
_create_job_fn: Optional[Callable[[dict], str]] = None


def register_create_job(fn: Callable[[dict], str]) -> None:
    global _create_job_fn
    _create_job_fn = fn


def create_job(payload: dict) -> str:
    """Crea y arranca un job de generación. Devuelve el job_id."""
    if _create_job_fn is None:
        raise RuntimeError("create_job no registrado — server.py no ha arrancado aún")
    return _create_job_fn(payload)
