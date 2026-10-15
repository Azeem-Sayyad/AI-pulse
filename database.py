"""
database.py — SQLite persistence layer for AI Pulse
"""
import sqlite3
from datetime import datetime
from config import DB_PATH


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL,
            link          TEXT UNIQUE NOT NULL,
            raw_summary   TEXT,
            source        TEXT,
            published     TEXT,
            fetched_at    TEXT DEFAULT CURRENT_TIMESTAMP,

            -- AI-generated fields
            ai_headline      TEXT,
            ai_summary       TEXT,
            why_it_matters   TEXT,
            quick_challenge  TEXT,
            category         TEXT,
            relevance_score  REAL DEFAULT 0,
            reading_time     INTEGER DEFAULT 1,

            -- Coordinator decision
            included      INTEGER DEFAULT 1
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
    conn.commit()
    conn.close()


# ─── Articles ─────────────────────────────────────────────────────────────────

def insert_articles(articles: list[dict]) -> int:
    """Bulk-insert raw harvested articles; skip duplicates. Returns count inserted."""
    conn = get_db()
    inserted = 0
    for a in articles:
        try:
            conn.execute(
                """INSERT INTO articles (title, link, raw_summary, source, published)
                   VALUES (?, ?, ?, ?, ?)""",
                (a["title"], a["link"], a.get("summary", ""), a["source"], a.get("published", ""))
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # duplicate link — skip
    conn.commit()
    conn.close()
    return inserted


def get_unprocessed_articles() -> list[dict]:
    """Return articles that have NOT yet been scored by the AI pipeline."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE ai_summary IS NULL ORDER BY fetched_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_articles(limit: int = 100) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles ORDER BY relevance_score DESC, fetched_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_approved_articles() -> list[dict]:
    """Return articles the coordinator has approved (included=1, scored, AI processed)."""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM articles
           WHERE included = 1
             AND relevance_score >= 6
             AND ai_summary IS NOT NULL
           ORDER BY relevance_score DESC""",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_ai_fields(article_id: int, fields: dict) -> None:
    """Patch AI-generated fields onto an article row."""
    conn = get_db()
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [article_id]
    conn.execute(f"UPDATE articles SET {keys} WHERE id=?", vals)
    conn.commit()
    conn.close()


def set_included(article_id: int, included: bool) -> None:
    conn = get_db()
    conn.execute("UPDATE articles SET included=? WHERE id=?", (1 if included else 0, article_id))
    conn.commit()
    conn.close()


def update_article_text(article_id: int, headline: str, summary: str,
                        why: str, challenge: str, category: str) -> None:
    """Allow coordinator to save manual edits."""
    conn = get_db()
    conn.execute(
        """UPDATE articles
           SET ai_headline=?, ai_summary=?, why_it_matters=?,
               quick_challenge=?, category=?
           WHERE id=?""",
        (headline, summary, why, challenge, category, article_id)
    )
    conn.commit()
    conn.close()


def clear_articles() -> None:
    conn = get_db()
    conn.execute("DELETE FROM articles")
    conn.commit()
    conn.close()


# ─── Newsletters ──────────────────────────────────────────────────────────────

def save_newsletter(title: str, editor_note: str, html: str,
                    md: str, fmt: str = "weekly") -> int:
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO newsletters (title, editor_note, html_content, md_content, format)
           VALUES (?, ?, ?, ?, ?)""",
        (title, editor_note, html, md, fmt)
    )
    nid = cur.lastrowid
    conn.commit()
    conn.close()
    return nid


def get_newsletters(limit: int = 10) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, format, created_at FROM newsletters ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_newsletter_html(newsletter_id: int) -> str:
    conn = get_db()
    row = conn.execute(
        "SELECT html_content FROM newsletters WHERE id=?", (newsletter_id,)
    ).fetchone()
    conn.close()
    return row["html_content"] if row else ""
