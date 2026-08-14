"""
article_index_db.py
━━━━━━━━━━━━━━━━━━
Base de datos SQLite con FTS5 para indexar artículos completos.
Almacena el contenido íntegro de cada artículo para búsqueda textual
y reutilización en la generación de vídeos.
"""

import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "_library" / "article_index.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id          TEXT PRIMARY KEY,
                url         TEXT UNIQUE NOT NULL,
                title       TEXT NOT NULL,
                source      TEXT DEFAULT '',
                summary     TEXT DEFAULT '',
                content     TEXT DEFAULT '',
                category    TEXT DEFAULT 'general',
                score       REAL DEFAULT 0,
                lang        TEXT DEFAULT 'es',
                indexed_at  TEXT NOT NULL,
                used_count  INTEGER DEFAULT 0,
                word_count  INTEGER DEFAULT 0
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                title,
                summary,
                content,
                content='articles',
                content_rowid='rowid'
            );

            CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, title, summary, content)
                VALUES (new.rowid, new.title, new.summary, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, summary, content)
                VALUES ('delete', old.rowid, old.title, old.summary, old.content);
                INSERT INTO articles_fts(rowid, title, summary, content)
                VALUES (new.rowid, new.title, new.summary, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, summary, content)
                VALUES ('delete', old.rowid, old.title, old.summary, old.content);
            END;
        """)


def _url_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def index_article(
    url: str,
    title: str,
    content: str,
    summary: str = "",
    source: str = "",
    category: str = "general",
    score: float = 0.0,
    lang: str = "es",
) -> dict:
    """
    Guarda un artículo en el índice. Si la URL ya existe, actualiza el contenido.
    Devuelve el artículo guardado.
    """
    init_db()
    article_id = _url_id(url)
    now = datetime.now(timezone.utc).isoformat()
    word_count = len(content.split())

    with _conn() as conn:
        existing = conn.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE articles SET
                    title=?, source=?, summary=?, content=?,
                    category=?, score=?, lang=?, word_count=?, indexed_at=?
                WHERE url=?
            """, (title, source, summary, content, category, score, lang, word_count, now, url))
        else:
            conn.execute("""
                INSERT INTO articles (id, url, title, source, summary, content,
                    category, score, lang, indexed_at, word_count)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (article_id, url, title, source, summary, content,
                  category, score, lang, now, word_count))

    return get_article(article_id)


def get_article(article_id: str) -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        return dict(row) if row else None


def get_by_url(url: str) -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM articles WHERE url=?", (url,)).fetchone()
        return dict(row) if row else None


def search_articles(query: str, limit: int = 20) -> list[dict]:
    """Búsqueda full-text sobre título, resumen y contenido completo."""
    init_db()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT a.*, snippet(articles_fts, 2, '<mark>', '</mark>', '…', 32) AS snippet
            FROM articles_fts
            JOIN articles a ON a.rowid = articles_fts.rowid
            WHERE articles_fts MATCH ?
            ORDER BY rank, a.score DESC
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]


def list_articles(limit: int = 50, offset: int = 0,
                  category: str = None) -> list[dict]:
    """Lista artículos indexados, más recientes primero."""
    init_db()
    with _conn() as conn:
        if category:
            rows = conn.execute("""
                SELECT * FROM articles WHERE category=?
                ORDER BY indexed_at DESC LIMIT ? OFFSET ?
            """, (category, limit, offset)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM articles
                ORDER BY indexed_at DESC LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()
        return [dict(r) for r in rows]


def delete_article(article_id: str) -> bool:
    init_db()
    with _conn() as conn:
        rows = conn.execute("DELETE FROM articles WHERE id=?", (article_id,)).rowcount
        return rows > 0


def mark_used(article_id: str):
    init_db()
    with _conn() as conn:
        conn.execute("UPDATE articles SET used_count = used_count + 1 WHERE id=?", (article_id,))


def stats() -> dict:
    init_db()
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        cats = conn.execute("""
            SELECT category, COUNT(*) as n FROM articles GROUP BY category ORDER BY n DESC
        """).fetchall()
        most_used = conn.execute("""
            SELECT title, used_count FROM articles ORDER BY used_count DESC LIMIT 5
        """).fetchall()
        return {
            "total": total,
            "by_category": [dict(r) for r in cats],
            "most_used": [dict(r) for r in most_used],
        }
