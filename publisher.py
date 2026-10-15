"""
publisher.py — Newsletter generation for AI Pulse
Renders approved articles into a compact HTML newsletter and a Markdown version.

Run `python publisher.py --test` to render the demo data into outputs/.
"""
import sys
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import (OUTPUTS_DIR, TEMPLATE_PATH, CATEGORY_COLORS, CATEGORY_EMOJI,
                    TOPIC_CATEGORIES, EDITIONS)
from harvester import parse_published


# ─── Edition selection ────────────────────────────────────────────────────────

def select_for_edition(articles: list[dict], fmt: str = "weekly",
                       reference: datetime | None = None) -> dict:
    """
    Pick the stories for a weekly or monthly edition.

    The window ends at `reference` (default: the newest approved article, so cached
    demo data still produces a sensible edition) and spans the edition's day count.
    The highest-scoring stories inside the window are kept, up to max_items.
    """
    edition = EDITIONS[fmt]
    if not articles:
        return {"articles": [], "skipped": 0, "start": None, "end": None}

    dated = [(parse_published(a.get("published", "")), a) for a in articles]
    end = reference or max(d for d, _ in dated)
    start = end - timedelta(days=edition["days"] - 1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    in_window = [(d, a) for d, a in dated if start <= d <= end + timedelta(days=1)]
    in_window.sort(key=lambda da: (-(da[1].get("relevance_score") or 0), -da[0].timestamp()))
    chosen = in_window[: edition["max_items"]]
    for d, a in chosen:
        a["_date"] = d
    return {
        "articles": [a for _, a in chosen],
        "skipped": len(articles) - len(chosen),
        "start": start,
        "end": end,
    }


def group_articles(articles: list[dict], fmt: str = "weekly") -> list[dict]:
    """
    Weekly editions group stories by topic; monthly editions group them by week,
    newest week first. Returns [{"label": str, "articles": [...]}, ...].
    """
    if fmt == "weekly":
        groups = []
        for cat in TOPIC_CATEGORIES:
            items = [a for a in articles if a.get("category") == cat]
            if items:
                groups.append({"label": f"{CATEGORY_EMOJI.get(cat, '')} {cat}".strip(), "articles": items})
        other = [a for a in articles if a.get("category") not in TOPIC_CATEGORIES]
        if other:
            groups.append({"label": "📰 More", "articles": other})
        return groups

    buckets: "OrderedDict[str, list]" = OrderedDict()
    dated = sorted(articles, key=lambda a: a.get("_date") or parse_published(a.get("published", "")),
                   reverse=True)
    for a in dated:
        d = a.get("_date") or parse_published(a.get("published", ""))
        monday = d - timedelta(days=d.weekday())
        buckets.setdefault(f"📅 Week of {monday:%b} {monday.day}", []).append(a)
    return [{"label": k, "articles": v} for k, v in buckets.items()]


def _period_label(start: datetime | None, end: datetime | None) -> str:
    if not start or not end:
        return datetime.now().strftime("%B %d, %Y")
    if start.year != end.year:
        return f"{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}"
    if start.month == end.month:
        return f"{start:%b} {start.day}–{end.day}, {end.year}"
    return f"{start:%b} {start.day} – {end:%b} {end.day}, {end.year}"


def _context(articles: list[dict], title: str, editor_note: str, fmt: str) -> dict:
    selection = select_for_edition(articles, fmt)
    chosen = selection["articles"]
    for a in chosen:
        a["category_color"] = CATEGORY_COLORS.get(a.get("category", ""), "#6c63ff")
        a["category_emoji"] = CATEGORY_EMOJI.get(a.get("category", ""), "📰")
    return {
        "title": title,
        "editor_note": editor_note,
        "fmt": fmt,
        "edition_label": EDITIONS[fmt]["label"],
        "period": _period_label(selection["start"], selection["end"]),
        "groups": group_articles(chosen, fmt),
        "story_count": len(chosen),
        "total_minutes": sum(int(a.get("reading_time") or 0) for a in chosen),
        "skipped": selection["skipped"],
        "year": datetime.now().year,
    }


# ─── Renderers ────────────────────────────────────────────────────────────────

def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(Path(TEMPLATE_PATH).parent)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html_newsletter(articles: list[dict], title: str, editor_note: str,
                           fmt: str = "weekly") -> str:
    """Render approved articles into a compact HTML newsletter string."""
    template = _get_jinja_env().get_template(Path(TEMPLATE_PATH).name)
    return template.render(**_context(articles, title, editor_note, fmt))


def render_markdown_newsletter(articles: list[dict], title: str, editor_note: str,
                               fmt: str = "weekly") -> str:
    """Render a compact Markdown version of the newsletter."""
    ctx = _context(articles, title, editor_note, fmt)
    lines = [
        f"# {title}",
        f"*{ctx['edition_label']} edition · {ctx['period']} · "
        f"{ctx['story_count']} stories · {ctx['total_minutes']} min total*",
        "",
    ]
    if editor_note:
        lines += [f"> {editor_note}", ""]

    for group in ctx["groups"]:
        lines += [f"## {group['label']}", ""]
        for a in group["articles"]:
            headline = a.get("ai_headline") or a.get("title", "Untitled")
            lines += [
                f"**[{headline}]({a.get('link', '')})**  ",
                f"{a.get('ai_summary', '')}  ",
                f"💡 {a.get('why_it_matters', '')}  ",
                f"⚡ *Try:* {a.get('quick_challenge', '')}  ",
                f"<sub>{a.get('source', '')} · {a.get('reading_time', '?')} min read</sub>",
                "",
            ]

    lines.append("---\n*AI Pulse · curated by your club, summarized with AI*")
    return "\n".join(lines)


# ─── Save to Disk ─────────────────────────────────────────────────────────────

def save_newsletter(html: str, md: str, fmt: str = "weekly") -> tuple[str, str]:
    """Save to outputs/newsletter_YYYY-MM-DD[_monthly].{html,md}; returns both paths."""
    Path(OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)
    stem = f"newsletter_{datetime.now():%Y-%m-%d}" + ("" if fmt == "weekly" else f"_{fmt}")
    html_path = Path(OUTPUTS_DIR) / f"{stem}.html"
    md_path = Path(OUTPUTS_DIR) / f"{stem}.md"
    html_path.write_text(html, encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    print(f"[publisher] Saved → {html_path}\n[publisher] Saved → {md_path}")
    return str(html_path), str(md_path)


# ─── Convenience Wrapper ──────────────────────────────────────────────────────

def generate_newsletter(
    articles: list[dict],
    title: str = "AI Pulse",
    editor_note: str = "The AI news worth your time this week, picked for CS students.",
    fmt: str = "weekly",
    save: bool = True,
) -> dict:
    """Render HTML + Markdown, optionally save them, and return both."""
    html = render_html_newsletter(articles, title, editor_note, fmt)
    md = render_markdown_newsletter(articles, title, editor_note, fmt)
    html_path = md_path = None
    if save:
        html_path, md_path = save_newsletter(html, md, fmt)
    return {"html": html, "markdown": md, "html_path": html_path, "md_path": md_path}


if __name__ == "__main__":
    if "--test" not in sys.argv:
        print("Usage: python publisher.py --test")
        sys.exit(1)
    from ai_pipeline import process_articles
    from harvester import load_demo_articles

    processed = process_articles(load_demo_articles(), use_mock=True)
    approved = [a for a in processed if a["status"] == "pending"]
    for fmt in ("weekly", "monthly"):
        out = generate_newsletter(approved, fmt=fmt)
        print(f"{fmt}: {len(out['html']):,} bytes HTML → {out['html_path']}")
