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
        if f.get("dominio"):
            nivel_dom[f["dominio"]] = int(f["nivel"])
            org_dom[f["dominio"]] = f["nombre"]
            if int(f["nivel"]) <= 3:
                confiables.add(f["dominio"])
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
