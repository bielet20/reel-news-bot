"""
api/article_index.py
━━━━━━━━━━━━━━━━━━━
Endpoints para indexar artículos completos y buscar en el índice persistente.
Usa article_extractor.py para scraping y article_index_db.py para SQLite FTS5.
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

CORE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CORE_DIR))

router = APIRouter(prefix="/api/articles", tags=["articles"])


class ReadRequest(BaseModel):
    url: str
    title: Optional[str] = None
    source: Optional[str] = None
    category: str = "general"
    score: float = 0.0
    summary: str = ""


@router.post("/read")
async def read_and_index(req: ReadRequest):
    """
    Descarga el contenido completo de una URL y lo indexa en SQLite FTS5.
    Si ya estaba indexado, devuelve el registro existente sin re-scraping
    a menos que el contenido esté vacío.
    """
    def _scrape():
        from article_extractor import extraer_articulo
        from article_index_db import get_by_url, index_article

        existing = get_by_url(req.url)
        if existing and existing.get("word_count", 0) > 50:
            return existing

        art = extraer_articulo(req.url)

        return index_article(
            url=req.url,
            title=req.title or art["titulo"],
            content=art["texto"],
            summary=req.summary or art.get("descripcion", ""),
            source=req.source or art["fuente"],
            category=req.category,
            score=req.score,
        )

    try:
        result = await run_in_threadpool(_scrape)
        if not result:
            raise HTTPException(status_code=500, detail="No se pudo indexar el artículo")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_articles(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
):
    """Búsqueda full-text en título, resumen y contenido completo de los artículos."""
    def _search():
        from article_index_db import search_articles as _sa
        return _sa(q, limit=limit)

    try:
        results = await run_in_threadpool(_search)
        return {"results": results, "total": len(results), "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats():
    """Estadísticas del índice: total de artículos, por categoría, más usados."""
    try:
        result = await run_in_threadpool(lambda: __import__("article_index_db").stats())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check")
async def check_url(url: str = Query(...)):
    """Comprueba si una URL ya está indexada. Rápido (no hace scraping)."""
    def _check():
        from article_index_db import get_by_url
        a = get_by_url(url)
        return {"indexed": a is not None, "id": a["id"] if a else None,
                "word_count": a.get("word_count", 0) if a else 0}

    try:
        return await run_in_threadpool(_check)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_articles(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
):
    """Lista los artículos indexados más recientes."""
    def _list():
        from article_index_db import list_articles as _la
        return _la(limit=limit, offset=offset, category=category or None)

    try:
        articles = await run_in_threadpool(_list)
        return {"articles": articles, "total": len(articles)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{article_id}")
async def get_article(article_id: str):
    """Obtiene un artículo por su ID."""
    def _get():
        from article_index_db import get_article, mark_used
        art = get_article(article_id)
        if art:
            mark_used(article_id)
        return art

    try:
        article = await run_in_threadpool(_get)
        if not article:
            raise HTTPException(status_code=404, detail="Artículo no encontrado")
        return article
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{article_id}")
async def delete_article(article_id: str):
    """Elimina un artículo del índice."""
    def _delete():
        from article_index_db import delete_article as _da
        return _da(article_id)

    try:
        deleted = await run_in_threadpool(_delete)
        if not deleted:
            raise HTTPException(status_code=404, detail="Artículo no encontrado")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
