"""
fiabilidad.py
Índice de fiabilidad (0-100) de una noticia y seguimiento de su expansión.

Reglas (cada una deja una "razón" legible para la app):
  base 30
  + nivel de la fuente de origen: 1 → +35 · 2 → +22 · 3 → +8 · 4 → −20
  + medios independientes que la publican: 2 → +12 · 3 → +20 · 4 o más → +25
  + la confirma al menos un medio de nivel 1-2 distinto del origen → +10
  + la publica un verificador (Maldita, Newtral, AFP Factual…) → +5
  − solo la da una fuente de nivel 4 (alerta/PR) → queda como dudosa
  − más de 48 h de antigüedad → −5

Etiquetas: ≥80 Muy fiable · ≥65 Fiable · ≥45 Por confirmar · <45 Dudosa

Expansión: en cada escaneo se guarda cuántos medios la publican
(_config/propagacion.json); así se ve si la historia crece, se mantiene o se apaga.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

PROPAGACION = Path(__file__).parent / "_config" / "propagacion.json"
_lock = threading.Lock()

ETIQUETAS = [(80, "Muy fiable", "#22c55e"), (65, "Fiable", "#4ade80"),
             (45, "Por confirmar", "#fbbf24"), (0, "Dudosa", "#f87171")]
_FACT_CHECKERS = ("maldita", "newtral", "full fact", "afp factual", "efe verifica", "verifica")


def calcular(item: dict) -> dict:
    razones = []
    nivel = int(item.get("nivel_fuente", 3) or 3)
    score = 30
    puntos_nivel = {1: 35, 2: 22, 3: 8, 4: -20}.get(nivel, 0)
    score += puntos_nivel
    nombres_nivel = {1: "agencia o ciencia", 2: "prensa de referencia", 3: "especialista", 4: "alerta o PR"}
    origen = item.get("org_fuente") or item.get("origen") or item.get("fuente")
    razones.append(f"Origen: {origen or '?'} "
                   f"(nivel {nivel}, {nombres_nivel.get(nivel, '?')}) {puntos_nivel:+d}")

    detalle = item.get("fuentes_detalle") or []
    orgs = {d.get("org") for d in detalle if d.get("org")} or set(item.get("fuentes_confirmacion") or [])
    n = max(int(item.get("n_fuentes", 1) or 1), len(orgs))
    pts = 25 if n >= 4 else 20 if n == 3 else 12 if n == 2 else 0
    score += pts
    razones.append(f"{n} medio{'s' if n != 1 else ''} independiente{'s' if n != 1 else ''} "
                   f"la publica{'n' if n != 1 else ''} {pts:+d}" if pts else "Solo la publica un medio +0")

    fuertes = [d for d in detalle if d.get("org") != origen and int(d.get("nivel", 3) or 3) <= 2]
    if fuertes:
        score += 10
        razones.append(f"Confirmada por {fuertes[0].get('org')} (nivel {fuertes[0].get('nivel')}) +10")

    todas = " ".join(str(x).lower() for x in list(orgs) + list(item.get("fact_checkers") or []))
    if any(fc in todas for fc in _FACT_CHECKERS):
        score += 5
        razones.append("Aparece en un verificador de datos +5")

    horas = (item.get("recencia") or {}).get("horas")
    if isinstance(horas, (int, float)) and horas > 48:
        score -= 5
        razones.append(f"Antigua ({int(horas)} h) −5")

    if nivel == 4 and n < 2:
        score = min(score, 40)
        razones.append("Solo una fuente de alerta/PR: no se da por buena sin confirmación")

    score = max(0, min(100, score))
    etiqueta, color = next((e, c) for umbral, e, c in ETIQUETAS if score >= umbral)
    return {"fiabilidad": score, "fiabilidad_label": etiqueta, "fiabilidad_color": color,
            "fiabilidad_razones": razones, "n_medios": n, "medios": sorted(o for o in orgs if o)}


# ── Cobertura: quién más publica la historia ─────────────────────────────────

def verificar_cobertura(item: dict, dias_max: float = 3.0) -> dict:
    """Busca la misma historia en Google News (inglés y español) y añade los
    medios FIABLES (dominios de la lista de fuentes) que la publican en los
    últimos días. Así "confirmada" no depende de que la historia coincida por
    casualidad dentro del lote descargado (antes casi todo salía con 1 medio)."""
    import time as _t
    import urllib.parse
    import feedparser
    import news_fetcher as nf

    def limpio(t: str) -> str:
        return re.sub(r"\s+[-|–]\s+[^-|–]+$", "", t or "")  # quita " - AP News"

    base = limpio(item.get("titulo_original") or item.get("titulo", ""))
    tokens = nf._tokens_titulo(base)
    if len(tokens) < 3:
        return item
    consulta = " ".join(sorted(tokens, key=len, reverse=True)[:6])
    detalle = list(item.get("fuentes_detalle") or [])
    orgs = {d.get("org") for d in detalle if d.get("org")}
    origen = item.get("org_fuente") or item.get("origen")
    if origen:
        orgs.add(origen)
    for hl, gl in (("en-US", "US"), ("es", "ES")):
        url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(consulta)}"
               f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}")
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for e in feed.entries[:30]:
            src = getattr(e, "source", None)
            href = getattr(src, "href", "") if src is not None else ""
            nombre = getattr(src, "title", "") if src is not None else ""
            if not href or not nf._es_dominio_confiable(href):
                continue
            pub = e.get("published_parsed")
            if pub and (_t.time() - _t.mktime(pub)) > dias_max * 86400:
                continue
            if nf._sim_titulo(tokens, nf._tokens_titulo(limpio(e.get("title", "")))) < 0.25:
                continue
            nivel, org = nf._nivel_y_org(nombre, href)
            if not org or org in orgs:
                continue
            orgs.add(org)
            detalle.append({"org": org, "fuente": nombre, "url": e.get("link", ""),
                            "nivel": nivel, "rol": "confirmación"})
    item["fuentes_detalle"] = detalle
    item["fuentes_confirmacion"] = sorted(o for o in orgs if o)
    item["n_fuentes"] = len(orgs)
    item["confirmada"] = len(orgs) >= 2
    return item


# ── Expansión ─────────────────────────────────────────────────────────────────

def _clave(titulo: str) -> str:
    t = unicodedata.normalize("NFKD", (titulo or "").lower()).encode("ascii", "ignore").decode()
    palabras = sorted({w for w in re.findall(r"[a-z0-9]{4,}", t)})[:8]
    return hashlib.sha1(" ".join(palabras).encode()).hexdigest()[:12]


def registrar_expansion(items: list[dict]) -> None:
    """Anota cuántos medios publican cada historia en este momento."""
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        try:
            datos = json.loads(PROPAGACION.read_text(encoding="utf-8"))
        except Exception:
            datos = {}
        for it in items:
            k = _clave(it.get("titulo_original") or it.get("titulo", ""))
            reg = datos.setdefault(k, {"titulo": it.get("titulo_original") or it.get("titulo", ""), "puntos": []})
            n = int(it.get("n_medios") or it.get("n_fuentes") or 1)
            if not reg["puntos"] or reg["puntos"][-1]["n"] != n or reg["puntos"][-1]["t"][:13] != ahora[:13]:
                reg["puntos"].append({"t": ahora, "n": n, "medios": it.get("medios", [])[:8]})
            reg["puntos"] = reg["puntos"][-48:]
            reg["ultimo"] = ahora
        # quedarse con las 300 historias más recientes
        datos = dict(sorted(datos.items(), key=lambda kv: kv[1].get("ultimo", ""), reverse=True)[:300])
        PROPAGACION.parent.mkdir(exist_ok=True)
        PROPAGACION.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def expansion(item: dict) -> dict:
    """Historial de medios de una historia y su tendencia."""
    try:
        datos = json.loads(PROPAGACION.read_text(encoding="utf-8"))
    except Exception:
        datos = {}
    reg = datos.get(_clave(item.get("titulo_original") or item.get("titulo", "")))
    if not reg or not reg.get("puntos"):
        return {"expansion": [], "tendencia": "nueva"}
    pts = reg["puntos"]
    primero, ultimo = pts[0], pts[-1]
    if len(pts) == 1:
        tendencia = "nueva"
    elif ultimo["n"] > primero["n"]:
        tendencia = "creciendo"
    elif ultimo["n"] < primero["n"]:
        tendencia = "bajando"
    else:
        tendencia = "estable"
    return {"expansion": [{"t": p["t"], "n": p["n"]} for p in pts], "tendencia": tendencia,
            "primera_vez": primero["t"]}


def apta_auto(item: dict, reglas: dict) -> tuple[bool, list[str]]:
    """¿Cumple las reglas para generarse y publicarse sola? (apta, motivos_si_no)."""
    motivos = []
    if item.get("viralidad_estimada"):
        motivos.append("viralidad estimada sin IA (el modelo no respondió)")
    if float(item.get("score", 0) or 0) < float(reglas.get("score_min", 7.5)):
        motivos.append(f"viralidad {item.get('score', 0)} < {reglas.get('score_min', 7.5)}")
    if int(item.get("fiabilidad", 0) or 0) < int(reglas.get("fiabilidad_min", 70)):
        motivos.append(f"fiabilidad {item.get('fiabilidad', 0)} < {reglas.get('fiabilidad_min', 70)}")
    if int(item.get("n_medios", 1) or 1) < int(reglas.get("min_medios", 2)):
        motivos.append(f"{item.get('n_medios', 1)} medio(s) < {reglas.get('min_medios', 2)} exigidos")
    if reglas.get("excluir_nivel4", True) and int(item.get("nivel_fuente", 3) or 3) >= 4:
        motivos.append("origen de nivel 4 (alerta/PR)")
    return (not motivos), motivos
