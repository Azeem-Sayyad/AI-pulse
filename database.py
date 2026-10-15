"""
database.py — SQLite persistence layer for AI Pulse

Articles are keyed by link. The dashboard reads and writes through these
functions so review decisions survive a browser refresh.
"""
import sqlite3
from contextlib import contextmanager
from typing import Optional

import config

ARTICLE_FIELDS = [
    "title", "link", "summary", "source", "published",
    "ai_headline", "ai_summary", "why_it_matters", "quick_challenge", "category",
    "relevance_score", "relevance_reason", "reading_time", "duplicate_of",
    "status", "ai_engine",
]


def get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _connect(db_path: Optional[str] = None):
    """Open a connection, commit on success, always close."""
    conn = get_db(db_path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Create tables if they don't exist."""
    with _connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                title            TEXT NOT NULL,
                link             TEXT UNIQUE NOT NULL,
                summary          TEXT,
                source           TEXT,
                published        TEXT,
                fetched_at       TEXT DEFAULT CURRENT_TIMESTAMP,

                -- AI-generated fields
                ai_headline      TEXT,
                ai_summary       TEXT,
                why_it_matters   TEXT,
                quick_challenge  TEXT,
                category         TEXT,
                relevance_score  INTEGER DEFAULT 0,
                relevance_reason TEXT,
                reading_time     INTEGER DEFAULT 1,
                duplicate_of     TEXT,
                ai_engine        TEXT,

                -- pending | approved | rejected | filtered | duplicate
                status           TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS newsletters (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT,
                editor_note  TEXT,
                html_content TEXT,
                md_content   TEXT,
                format       TEXT DEFAULT 'weekly',
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)


# ─── Articles ─────────────────────────────────────────────────────────────────

def replace_articles(articles: list[dict], db_path: Optional[str] = None) -> None:
    """Replace the current batch with freshly processed articles."""
    cols = ", ".join(ARTICLE_FIELDS)
    marks = ", ".join("?" for _ in ARTICLE_FIELDS)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM articles")
        conn.executemany(
            f"INSERT OR IGNORE INTO articles ({cols}) VALUES ({marks})",
            [tuple(a.get(f) for f in ARTICLE_FIELDS) for a in articles],
        )


def get_all_articles(db_path: Optional[str] = None) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM articles ORDER BY relevance_score DESC, id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_approved_articles(db_path: Optional[str] = None) -> list[dict]:
    """Articles the coordinator approved. Rescued low scorers are included on purpose."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM articles
               WHERE status = 'approved' AND ai_summary IS NOT NULL
               ORDER BY relevance_score DESC""",
        ).fetchall()
    return [dict(r) for r in rows]


def update_article(link: str, fields: dict, db_path: Optional[str] = None) -> None:
    """Patch any of ARTICLE_FIELDS on the article with this link."""
    fields = {k: v for k, v in fields.items() if k in ARTICLE_FIELDS and k != "link"}
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE articles SET {keys} WHERE link=?", [*fields.values(), link])


def clear_articles(db_path: Optional[str] = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM articles")


# ─── Newsletters ──────────────────────────────────────────────────────────────

def save_newsletter(title: str, editor_note: str, html: str, md: str,
                    fmt: str = "weekly", db_path: Optional[str] = None) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO newsletters (title, editor_note, html_content, md_content, format)
               VALUES (?, ?, ?, ?, ?)""",
            (title, editor_note, html, md, fmt),
        )
        return cur.lastrowid


def get_newsletters(limit: int = 10, db_path: Optional[str] = None) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, title, format, created_at FROM newsletters ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_newsletter(newsletter_id: int, db_path: Optional[str] = None) -> Optional[dict]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM newsletters WHERE id=?", (newsletter_id,)).fetchone()
    return dict(row) if row else None
