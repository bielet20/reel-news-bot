"""
horario.py
Día natural en la hora local del canal (España por defecto), para los límites
"por día" (autopublicador, escáner). Antes se contaba una ventana móvil de 24 h
en UTC: las publicaciones de ayer seguían contando como "hoy" hasta la tarde.

ZONA_HORARIA (env, def. Europe/Madrid). El contenedor no trae tzdata; si no
se puede cargar la zona, se calcula la hora de Europa central a mano
(CET +1 / CEST +2, cambio el último domingo de marzo y de octubre a la 01:00 UTC).
"""

import os
from datetime import datetime, timedelta, timezone

ZONA = os.environ.get("ZONA_HORARIA", "Europe/Madrid")

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(ZONA)
except Exception:  # sin tzdata en el sistema
    _TZ = None


def _ultimo_domingo(anio: int, mes: int) -> datetime:
    d = datetime(anio, mes + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _a_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if _TZ is not None:
        return dt.astimezone(_TZ)
    utc = dt.astimezone(timezone.utc)
    ini = _ultimo_domingo(utc.year, 3).replace(hour=1)
    fin = _ultimo_domingo(utc.year, 10).replace(hour=1)
    return utc.astimezone(timezone(timedelta(hours=2 if ini <= utc < fin else 1)))


def ahora_local() -> datetime:
    return _a_local(datetime.now(timezone.utc))


def dia_local(iso: str = "") -> str:
    """'YYYY-MM-DD' local de un timestamp ISO (o de ahora si viene vacío).
    Devuelve '' si el timestamp no se puede leer."""
    if not iso:
        return ahora_local().date().isoformat()
    try:
        return _a_local(datetime.fromisoformat(iso.replace("Z", "+00:00"))).date().isoformat()
    except Exception:
        return ""


def es_hoy(iso: str) -> bool:
    return bool(iso) and dia_local(iso) == dia_local()
