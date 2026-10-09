"""
fecha_noticia.py
Fecha de la noticia en el vídeo y en los textos publicados (petición 2026-10-07:
que cada noticia diga de cuándo es).

La fecha llega en formatos distintos según el origen: ISO del artículo
(2026-10-07T17:57:39+00:00), RFC 822 del RSS (Tue, 07 Oct 2026 14:00:00 GMT)
o YYYYMMDD de YouTube. Todo se normaliza al día natural en hora de España
(horario.py) como 'YYYY-MM-DD', que es lo que se guarda en {slug}_fuente.json.
"""

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from horario import _a_local, ahora_local

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

MARCA_TEXTO = "📅 Noticia del"


def normalizar(valor) -> str:
    """Día local 'YYYY-MM-DD' de cualquier fecha conocida, o '' si no se entiende
    o no es creíble (antes de 2000 o más de un día en el futuro)."""
    s = str(valor or "").strip()
    if not s:
        return ""
    dia = None
    if re.fullmatch(r"\d{8}", s):  # YouTube: 20261007
        try:
            dia = datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            return ""
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            dia = date.fromisoformat(s)
        except ValueError:
            return ""
    else:
        dt = None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(s)
            except (TypeError, ValueError, IndexError):
                return ""
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dia = _a_local(dt).date()
    hoy = ahora_local().date()
    if dia.year < 2000 or dia > hoy + timedelta(days=1):
        return ""
    return dia.isoformat()


def larga(dia: str) -> str:
    """'2026-10-07' → '7 de octubre de 2026'."""
    try:
        d = date.fromisoformat(dia)
    except (TypeError, ValueError):
        return ""
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def linea(dia: str) -> str:
    """Línea para los textos publicados: '📅 Noticia del 7 de octubre de 2026'."""
    texto = larga(dia)
    return f"{MARCA_TEXTO} {texto}" if texto else ""


def con_fecha(texto: str, dia: str) -> str:
    """Mete la línea de fecha justo debajo del título (la primera línea) del texto.
    No la repite si ya está, y si no hay fecha devuelve el texto tal cual."""
    lin = linea(dia)
    if not lin or not texto or MARCA_TEXTO in texto:
        return texto
    primera, sep, resto = texto.partition("\n")
    return f"{primera}\n{lin}{sep}{resto}" if sep else f"{primera}\n{lin}"


def de_reel(carpeta, filename: str) -> str:
    """Fecha guardada de un reel ya generado: {slug}_fuente.json (noticias y
    narrados) o la línea 'Fecha:' de {slug}_info.txt (recortes de YouTube)."""
    slug = re.sub(r"_(reel|largo)\.mp4$", "", filename)
    slug = re.sub(r"\.mp4$", "", slug)
    ruta = os.path.join(str(carpeta), f"{slug}_fuente.json")
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
            dia = normalizar(datos.get("fecha_noticia")) or normalizar(datos.get("fecha_publicacion"))
            if dia:
                return dia
        except Exception:
            pass
    ruta = os.path.join(str(carpeta), f"{slug}_info.txt")
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                for l in f:
                    if l.startswith("Fecha:"):
                        return normalizar(l.split(":", 1)[1])
        except Exception:
            pass
    return ""
