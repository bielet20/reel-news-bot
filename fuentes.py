"""
fuentes.py
Fuentes de noticias gestionables desde la app.

Las fuentes integradas viven en news_fetcher (FUENTES_VERIFICADAS,
FUENTES_POR_CATEGORIA, NIVEL_FEED, NIVEL_DOMINIO…). Aquí se añaden las del
usuario y los ajustes (cambiar nivel, desactivar) guardados en
_config/fuentes.json, y `aplicar()` los inyecta en news_fetcher al importarlo,
así que afectan a toda búsqueda (web, Gestor, escáner, CLI).

Nivel de fiabilidad de una fuente:
  1 = agencia o ciencia revisada   2 = prensa de referencia
  3 = especialista                  4 = alerta o PR (no fiable por sí sola)
"""
from __future__ import annotations

import json
import re
import threading
import urllib.parse
from pathlib import Path

CONFIG = Path(__file__).parent / "_config" / "fuentes.json"
NIVELES = {1: "Agencia / ciencia", 2: "Prensa de referencia", 3: "Especialista", 4: "Alerta / PR"}
_lock = threading.Lock()


def _load() -> dict:
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("agregadas", [])
    d.setdefault("ajustes", {})
    return d


def _save(d: dict) -> None:
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def _dominio(url: str) -> str:
    d = urllib.parse.urlparse(url or "").netloc.lower()
    return d[4:] if d.startswith("www.") else d


def listar() -> list[dict]:
    """Todas las fuentes (integradas + añadidas) con su nivel y estado."""
    import news_fetcher as nf
    cfg = _load()
    ajustes = cfg["ajustes"]
    categorias: dict[str, str] = {}
    urls: dict[str, str] = {}
    for cat, lista in getattr(nf, "_FUENTES_POR_CATEGORIA_ORIG", nf.FUENTES_POR_CATEGORIA).items():
        for url, nombre in lista:
            categorias.setdefault(nombre, cat)
            urls.setdefault(nombre, url)
    for url, nombre in getattr(nf, "_FUENTES_VERIFICADAS_ORIG", nf.FUENTES_VERIFICADAS).items():
        urls.setdefault(nombre, url)
        categorias.setdefault(nombre, "general")

    out = []
    for nombre, url in urls.items():
        nf_orig = getattr(nf, "_NIVEL_FEED_ORIG", nf.NIVEL_FEED)
        nd_orig = getattr(nf, "_NIVEL_DOMINIO_ORIG", nf.NIVEL_DOMINIO)
        nivel_base = nf_orig.get(nombre) or nf._lookup_dominio(nd_orig, _dominio(url), 3)
        aj = ajustes.get(nombre, {})
        out.append({
            "nombre": nombre, "url": url, "dominio": _dominio(url),
            "categoria": categorias.get(nombre, "general"),
            "nivel": int(aj.get("nivel", nivel_base)), "nivel_base": int(nivel_base),
            "activa": bool(aj.get("activa", True)), "tipo": "integrada",
        })
    for f in cfg["agregadas"]:
        aj = ajustes.get(f["nombre"], {})
        out.append({**f, "nivel": int(aj.get("nivel", f["nivel"])), "nivel_base": int(f["nivel"]),
                    "activa": bool(aj.get("activa", True)), "tipo": "añadida"})
    out.sort(key=lambda x: (x["nivel"], x["nombre"].lower()))
    return out


def _resolver_feed(url: str) -> tuple[str, list[str]]:
    """(url_del_feed, titulares_de_muestra). Acepta un RSS directo o la web del
    medio: busca su RSS en el HTML y, si no tiene, usa Google News filtrado
    por su dominio."""
    import feedparser
    import requests
    import news_fetcher as nf

    def probar(u: str) -> list[str]:
        feed = feedparser.parse(u)
        return [e.get("title", "") for e in feed.entries[:5] if e.get("title")]

    muestra = probar(url)
    if muestra:
        return url, muestra
    try:
        html = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).text
        for m in re.finditer(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', html, re.I):
            href = re.search(r'href=["\']([^"\']+)', m.group(0))
            if href:
                u = urllib.parse.urljoin(url, href.group(1))
                muestra = probar(u)
                if muestra:
                    return u, muestra
    except Exception:
        pass
    dom = _dominio(url)
    if dom:
        u = nf._gnews_site(dom, "news", hl="es", gl="ES")
        muestra = probar(u)
        if muestra:
            return u, muestra
    raise ValueError("No encuentro un feed de noticias en esa dirección")


def agregar(nombre: str, url: str, nivel: int, categoria: str = "general") -> dict:
    nombre = nombre.strip()
    if not nombre or not url.strip():
        raise ValueError("Falta el nombre o la dirección")
    if int(nivel) not in NIVELES:
        raise ValueError("El nivel debe ser 1, 2, 3 o 4")
    feed, muestra = _resolver_feed(url.strip())
    with _lock:
        cfg = _load()
        if any(f["nombre"].lower() == nombre.lower() for f in cfg["agregadas"]) or \
                any(f["nombre"].lower() == nombre.lower() for f in listar() if f["tipo"] == "integrada"):
            raise ValueError(f"Ya existe una fuente llamada «{nombre}»")
        fuente = {"nombre": nombre, "url": feed, "web": url.strip(), "dominio": _dominio(url),
                  "nivel": int(nivel), "categoria": categoria or "general"}
        cfg["agregadas"].append(fuente)
        _save(cfg)
    aplicar()
    return {**fuente, "muestra": muestra}


def ajustar(nombre: str, nivel: int | None = None, activa: bool | None = None) -> None:
    with _lock:
        cfg = _load()
        aj = cfg["ajustes"].setdefault(nombre, {})
        if nivel is not None:
            if int(nivel) not in NIVELES:
                raise ValueError("El nivel debe ser 1, 2, 3 o 4")
            aj["nivel"] = int(nivel)
        if activa is not None:
            aj["activa"] = bool(activa)
        _save(cfg)
    aplicar()


def borrar(nombre: str) -> None:
    with _lock:
        cfg = _load()
        antes = len(cfg["agregadas"])
        cfg["agregadas"] = [f for f in cfg["agregadas"] if f["nombre"] != nombre]
        if len(cfg["agregadas"]) == antes:
            raise ValueError("Solo se pueden borrar las fuentes añadidas (las integradas se desactivan)")
        cfg["ajustes"].pop(nombre, None)
        _save(cfg)
    aplicar()


def aplicar() -> None:
    """Inyecta fuentes añadidas y ajustes en news_fetcher (idempotente)."""
    import news_fetcher as nf
    # Guardar las listas originales la primera vez para poder recalcular
    if not hasattr(nf, "_FUENTES_VERIFICADAS_ORIG"):
        nf._FUENTES_VERIFICADAS_ORIG = dict(nf.FUENTES_VERIFICADAS)
        nf._FUENTES_POR_CATEGORIA_ORIG = {k: list(v) for k, v in nf.FUENTES_POR_CATEGORIA.items()}
        nf._NIVEL_FEED_ORIG = dict(nf.NIVEL_FEED)
        nf._NIVEL_DOMINIO_ORIG = dict(nf.NIVEL_DOMINIO)
        nf._ORG_DOMINIO_ORIG = dict(nf._ORG_DOMINIO)
        nf._DOMINIOS_CONFIABLES_ORIG = set(nf.DOMINIOS_CONFIABLES)
    cfg = _load()
    ajustes = cfg["ajustes"]
    inactivas = {n for n, a in ajustes.items() if a.get("activa") is False}

    fv = {u: n for u, n in nf._FUENTES_VERIFICADAS_ORIG.items() if n not in inactivas}
    fpc = {k: [(u, n) for u, n in v if n not in inactivas] for k, v in nf._FUENTES_POR_CATEGORIA_ORIG.items()}
    nivel_feed = dict(nf._NIVEL_FEED_ORIG)
    nivel_dom = dict(nf._NIVEL_DOMINIO_ORIG)
    org_dom = dict(nf._ORG_DOMINIO_ORIG)
    confiables = set(nf._DOMINIOS_CONFIABLES_ORIG)

    for f in cfg["agregadas"]:
        if f["nombre"] in inactivas:
            continue
        cat = f.get("categoria") or "general"
        if cat in fpc:
            fpc[cat].append((f["url"], f["nombre"]))
        else:
            fv[f["url"]] = f["nombre"]
        nivel_feed[f["nombre"]] = int(f["nivel"])
        dom = f.get("dominio")
        if dom and dom not in nf._NIVEL_DOMINIO_ORIG and dom not in nf._ORG_DOMINIO_ORIG:
            # Dominio nuevo: darle nivel y nombre. Si ya existía (p. ej. nasa.gov
            # al añadir "NASA en español") se respeta el de la lista integrada.
            nivel_dom[dom] = int(f["nivel"])
            org_dom[dom] = f["nombre"]
        if dom and int(f["nivel"]) <= 3:
            confiables.add(dom)
    url_de = {n: u for u, n in nf._FUENTES_VERIFICADAS_ORIG.items()}
    for v in nf._FUENTES_POR_CATEGORIA_ORIG.values():
        for u, n in v:
            url_de.setdefault(n, u)
    for nombre, a in ajustes.items():
        if "nivel" in a:
            nivel_feed[nombre] = int(a["nivel"])
            # El buscador usa el MEJOR nivel entre feed y dominio: hay que
            # cambiar también el del dominio (salvo feeds de Google News)
            dom = _dominio(url_de.get(nombre, ""))
            if dom and "google." not in dom:
                nivel_dom[dom] = int(a["nivel"])

    nf.FUENTES_VERIFICADAS.clear(); nf.FUENTES_VERIFICADAS.update(fv)
    nf.FUENTES_POR_CATEGORIA.clear(); nf.FUENTES_POR_CATEGORIA.update(fpc)
    nf.NIVEL_FEED.clear(); nf.NIVEL_FEED.update(nivel_feed)
    nf.NIVEL_DOMINIO.clear(); nf.NIVEL_DOMINIO.update(nivel_dom)
    nf._ORG_DOMINIO.clear(); nf._ORG_DOMINIO.update(org_dom)
    nf.DOMINIOS_CONFIABLES.clear(); nf.DOMINIOS_CONFIABLES.update(confiables)


# ── Evaluación automática de credibilidad ───────────────────────────────────

CALIBRACION = Path(__file__).parent / "_config" / "calibracion_fuentes.json"
_SENSACIONALES = ("increíble", "impactante", "no creerás", "no vas a creer", "brutal", "escándalo",
                  "urgente", "última hora", "shocking", "you won't believe", "insane", "unbelievable",
                  "viral", "bombazo", "alucinante", "lo que pasó", "esto es lo que")


def _sensacionalismo(titulos: list[str]) -> float:
    """Fracción de titulares con recursos sensacionalistas."""
    def es_sensacional(t: str) -> bool:
        tl = t.lower()
        mayus = sum(1 for w in re.findall(r"\b[A-ZÁÉÍÓÚÑ]{4,}\b", t))
        return ("!" in t or "¡" in t or mayus >= 2 or any(s in tl for s in _SENSACIONALES))
    return (sum(es_sensacional(t) for t in titulos) / len(titulos)) if titulos else 0.0


def _medir(feed_url: str, dominio: str, max_titulares: int = 8) -> dict:
    """Mide corroboración, sensacionalismo y frecuencia de un feed."""
    import time as _t
    import feedparser
    from fiabilidad import verificar_cobertura

    feed = feedparser.parse(feed_url)
    entradas = [e for e in feed.entries if e.get("title")][:40]
    # La corroboración solo mira los últimos 3 días: medir titulares viejos
    # (habitual en feeds de Google News) castigaba sin motivo a las agencias
    recientes = [e for e in entradas if e.get("published_parsed")
                 and _t.time() - _t.mktime(e["published_parsed"]) <= 3 * 86400]
    if len(recientes) >= 3:
        entradas = recientes
    titulos = [re.sub(r"\s+[-|–]\s+[^-|–]+$", "", e["title"]) for e in entradas]
    fechas = sorted(_t.mktime(e["published_parsed"]) for e in entradas if e.get("published_parsed"))
    por_dia = None
    if len(fechas) >= 2 and fechas[-1] > fechas[0]:
        por_dia = round(len(fechas) / max((fechas[-1] - fechas[0]) / 86400, 0.04), 1)

    muestra, confirmadas, fuertes = [], 0, 0
    for t in titulos[:max_titulares]:
        it = verificar_cobertura({"titulo_original": t, "org_fuente": f"__{dominio}__",
                                  "fuentes_detalle": []}, excluir_dominio=dominio)
        otros = [d for d in it.get("fuentes_detalle", []) if d.get("org") != f"__{dominio}__"]
        n1_2 = [d for d in otros if int(d.get("nivel", 3)) <= 2]
        confirmadas += bool(otros)
        fuertes += bool(n1_2)
        muestra.append({"titular": t, "confirman": [d["org"] for d in otros][:5],
                        "nivel_1_2": bool(n1_2)})
    n = len(muestra) or 1
    return {
        "titulares": len(titulos),
        "corroboracion": round(confirmadas / n, 2),       # la publican otros medios fiables
        "corroboracion_fuerte": round(fuertes / n, 2),    # …de nivel 1-2
        "sensacionalismo": round(_sensacionalismo(titulos), 2),
        "por_dia": por_dia,
        "muestra": muestra,
    }


def _puntuacion(m: dict, https: bool, rss_propio: bool) -> int:
    s = 55 * m["corroboracion_fuerte"] + 20 * m["corroboracion"]
    s += 15 * (1 - m["sensacionalismo"])
    s += 5 * https + 5 * rss_propio
    return int(round(max(0, min(100, s))))


def calibracion() -> dict:
    try:
        return json.loads(CALIBRACION.read_text(encoding="utf-8"))
    except Exception:
        return {}


_CATS_ACTUALIDAD = ("general", "mundo", "politica", "economia")


def calibrar(por_nivel: int = 4, log=print) -> dict:
    """Mide fuentes de NOTICIAS DE ACTUALIDAD que ya tienes de cada nivel
    (incluidas las agencias, que se leen por Google News) para saber cómo
    puntúa cada nivel en la práctica. Los medios especializados publican
    análisis propios que nadie repite y no sirven de referencia."""
    niveles: dict[int, list[int]] = {1: [], 2: [], 3: [], 4: []}
    detalle: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}
    candidatas = [f for f in listar() if f["activa"] and f["categoria"] in _CATS_ACTUALIDAD]
    candidatas.sort(key=lambda f: _CATS_ACTUALIDAD.index(f["categoria"]))
    for f in candidatas:
        nv = f["nivel"]
        if len(niveles[nv]) >= por_nivel:
            continue
        try:
            m = _medir(f["url"], f["dominio"], max_titulares=6)
        except Exception:
            continue
        if m["titulares"] < 3:
            continue
        p = _puntuacion(m, f["url"].startswith("https"), True)
        niveles[nv].append(p)
        detalle[nv].append({"nombre": f["nombre"], "puntuacion": p, "corroboracion": m["corroboracion"],
                            "corroboracion_fuerte": m["corroboracion_fuerte"],
                            "sensacionalismo": m["sensacionalismo"]})
        log(f"[calibración] nivel {nv}: {f['nombre']} → {p}")
    res = {"fecha": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
           "niveles": {str(k): {"media": round(sum(v) / len(v)) if v else None, "fuentes": detalle[k]}
                       for k, v in niveles.items()}}
    CALIBRACION.parent.mkdir(exist_ok=True)
    CALIBRACION.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


def evaluar(url: str) -> dict:
    """Informe de credibilidad de una fuente nueva y su nivel sugerido,
    comparado con cómo puntúan las fuentes que ya tienes."""
    import news_fetcher as nf
    url = url.strip()
    feed, _ = _resolver_feed(url)
    dominio = _dominio(url)
    rss_propio = "news.google.com" not in feed
    m = _medir(feed, dominio)
    https = url.startswith("https") or feed.startswith("https")
    puntuacion = _puntuacion(m, https, rss_propio)

    cal = calibracion().get("niveles", {})
    medias = {int(k): v["media"] for k, v in cal.items() if v.get("media") is not None}
    # La calibración solo vale si es coherente: cada nivel puntúa más que el siguiente
    orden = [medias[k] for k in sorted(medias)]
    coherente = len(orden) >= 3 and all(a > b for a, b in zip(orden, orden[1:]))
    if coherente:
        # umbral entre dos niveles = punto medio de sus medias
        niveles_ord = sorted(medias)
        nivel_sugerido = niveles_ord[-1]
        for a, b in zip(niveles_ord, niveles_ord[1:]):
            if puntuacion >= (medias[a] + medias[b]) / 2:
                nivel_sugerido = a
                break
    else:  # sin calibrar o calibración incoherente: umbrales fijos
        nivel_sugerido = 1 if puntuacion >= 75 else 2 if puntuacion >= 55 else 3 if puntuacion >= 30 else 4
    if m["sensacionalismo"] >= 0.4:
        nivel_sugerido = max(nivel_sugerido, 3)  # muy sensacionalista: nunca 1-2

    # Las fuentes de tu lista (medidas en la calibración) que puntúan más parecido
    medidas = [f | {"nivel": int(k)} for k, v in cal.items() for f in v.get("fuentes", [])]
    parecidas = sorted(medidas, key=lambda f: abs(f["puntuacion"] - puntuacion))[:4]

    ya = nf._lookup_dominio(getattr(nf, "_NIVEL_DOMINIO_ORIG", nf.NIVEL_DOMINIO), dominio)
    razones = [
        f"{int(m['corroboracion'] * 100)}% de sus titulares los publican otros medios fiables "
        f"({int(m['corroboracion_fuerte'] * 100)}% confirmados por nivel 1-2)",
        f"Sensacionalismo: {int(m['sensacionalismo'] * 100)}% de los titulares",
        ("Tiene RSS propio" if rss_propio else "Sin RSS propio (se leerá por Google News)")
        + (" · HTTPS" if https else " · sin HTTPS"),
    ]
    if m["por_dia"]:
        razones.append(f"Publica unas {m['por_dia']} noticias al día")
    if ya:
        razones.append(f"Ya está en tu lista como nivel {ya}")
    por_dia = m["por_dia"] or 0
    if m["corroboracion"] < 0.2 and por_dia >= 40:
        razones.append(f"Mucho volumen ({int(por_dia)} al día) y casi nada confirmado por medios fiables: "
                       "señal de poca verificación.")
    elif m["corroboracion"] < 0.35 and m["sensacionalismo"] < 0.15 and por_dia < 15:
        razones.append("Pocas noticias confirmadas por otros pero nada sensacionalista y poco volumen: puede ser "
                       "un medio especializado con contenido propio (análisis, exclusivas). Revisa el nivel a mano.")
    return {"feed": feed, "dominio": dominio, "puntuacion": puntuacion, "nivel_sugerido": nivel_sugerido,
            "nivel_actual": ya, "medias_por_nivel": medias, "razones": razones,
            "calibrado": coherente, "parecidas": parecidas, **m}
