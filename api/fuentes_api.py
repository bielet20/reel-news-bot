"""
api/fuentes_api.py
Página de Fuentes: gestionar las fuentes y ver el análisis de noticias
(viralidad + fiabilidad + expansión + si cumplen las reglas automáticas).
"""
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

ANALISIS_FILE = Path(__file__).parent.parent / "_config" / "ultimo_analisis.json"
_analisis_estado = {"activo": False, "error": None}


class FuenteNueva(BaseModel):
    nombre: str
    url: str
    nivel: int = 3
    categoria: str = "general"


class FuenteAjuste(BaseModel):
    nivel: Optional[int] = None
    activa: Optional[bool] = None


class Prueba(BaseModel):
    url: str


class Analizar(BaseModel):
    tema: Optional[str] = None


@router.get("/api/fuentes")
def listar_fuentes():
    import fuentes
    import news_fetcher as nf
    cats = sorted(set(getattr(nf, "_FUENTES_POR_CATEGORIA_ORIG", nf.FUENTES_POR_CATEGORIA)) | {"general"})
    return {"fuentes": fuentes.listar(), "niveles": fuentes.NIVELES, "categorias": cats}


@router.post("/api/fuentes/probar")
def probar_fuente(req: Prueba):
    import fuentes
    try:
        feed, muestra = fuentes._resolver_feed(req.url.strip())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"feed": feed, "muestra": muestra}


@router.post("/api/fuentes")
def agregar_fuente(req: FuenteNueva):
    import fuentes
    try:
        return fuentes.agregar(req.nombre, req.url, req.nivel, req.categoria)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/api/fuentes/{nombre}")
def ajustar_fuente(nombre: str, req: FuenteAjuste):
    import fuentes
    try:
        fuentes.ajustar(nombre, nivel=req.nivel, activa=req.activa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/api/fuentes/{nombre}")
def borrar_fuente(nombre: str):
    import fuentes
    try:
        fuentes.borrar(nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.get("/api/fuentes/analisis")
def ultimo_analisis():
    try:
        datos = json.loads(ANALISIS_FILE.read_text(encoding="utf-8"))
    except Exception:
        datos = {"fecha": None, "noticias": []}
    return {**datos, "analizando": _analisis_estado["activo"], "error": _analisis_estado["error"]}


@router.post("/api/fuentes/analizar")
def analizar_ahora(req: Analizar):
    """Busca y puntúa noticias ahora (sin generar nada). Tarda ~1 min: el
    resultado se consulta en GET /api/fuentes/analisis."""
    if _analisis_estado["activo"]:
        return {"ok": True, "analizando": True}

    def _job():
        try:
            from api.scanner import CONFIG_DEFAULTS, CONFIG_FILE, _load_json
            from fiabilidad import apta_auto
            from news_curator import buscar_y_curar
            config = _load_json(CONFIG_FILE, CONFIG_DEFAULTS)
            noticias = buscar_y_curar(tema=req.tema or None, pais=config.get("pais", "ES"),
                                      variado=not req.tema, n_retornar=15)
            for n in noticias:
                n["apta_auto"], n["motivos_no_apta"] = apta_auto(n, config)
            ANALISIS_FILE.write_text(json.dumps({
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "tema": req.tema,
                "reglas": {k: config.get(k) for k in ("score_min", "fiabilidad_min", "min_medios", "excluir_nivel4")},
                "noticias": noticias,
            }, ensure_ascii=False, default=str), encoding="utf-8")
            _analisis_estado["error"] = None
        except Exception as e:
            _analisis_estado["error"] = str(e)
        finally:
            _analisis_estado["activo"] = False

    _analisis_estado.update(activo=True, error=None)
    threading.Thread(target=_job, daemon=True).start()
    return {"ok": True, "analizando": True}
