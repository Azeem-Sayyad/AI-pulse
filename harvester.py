"""
harvester.py — RSS Feed ingestion module for AI Pulse
Fetches articles from approved sources; falls back to cached demo data.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests

from config import RSS_FEEDS, MAX_ARTICLES_PER_FEED, CACHE_PATH


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _parse_date(entry) -> str:
    """Extract a normalized date string from a feed entry."""
    for attr in ("published", "updated", "created"):
        val = getattr(entry, attr, None)
        if val:
            return val
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def _entry_to_dict(entry, source_name: str) -> dict:
    """Convert a feedparser entry to a clean dict."""
    raw_summary = (
        entry.get("summary", "") or
        entry.get("description", "") or
        entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
    )
    return {
        "title":     _strip_html(entry.get("title", "Untitled")),
        "link":      entry.get("link", ""),
        "summary":   _strip_html(raw_summary)[:600],
        "published": _parse_date(entry),
        "source":    source_name,
    }


# ─── Live Fetch ───────────────────────────────────────────────────────────────

def fetch_feed(url: str, source_name: str, max_items: int = MAX_ARTICLES_PER_FEED) -> list[dict]:
    """Parse a single RSS feed URL and return a list of article dicts."""
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "AI-Pulse/1.0 Newsletter Bot"})
        if feed.bozo and not feed.entries:
            return []
        articles = []
        for entry in feed.entries[:max_items]:
            a = _entry_to_dict(entry, source_name)
            if a["title"] and a["link"]:
                articles.append(a)
        return articles
    except Exception as e:
        print(f"[harvester] Failed to fetch {source_name}: {e}")
        return []


def fetch_all_feeds(feeds: dict | None = None) -> list[dict]:
    """
    Fetch articles from all approved RSS feeds.
    Returns deduplicated list of article dicts.
    """
    if feeds is None:
        feeds = RSS_FEEDS

    all_articles: list[dict] = []
    seen_links: set[str] = set()

    for source_name, url in feeds.items():
        print(f"[harvester] Fetching: {source_name}...")
        articles = fetch_feed(url, source_name)
        for a in articles:
            if a["link"] not in seen_links:
                seen_links.add(a["link"])
                all_articles.append(a)
        print(f"  → {len(articles)} articles fetched")

    print(f"[harvester] Total unique articles: {len(all_articles)}")
    return all_articles


# ─── Demo / Cache Mode ────────────────────────────────────────────────────────

def load_demo_articles() -> list[dict]:
    """Load pre-cached demo articles from JSON file."""
    path = Path(CACHE_PATH)
    if not path.exists():
        print(f"[harvester] Cache file not found at {CACHE_PATH}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[harvester] Loaded {len(data)} demo articles from cache.")
    return data


def get_articles(demo_mode: bool = False) -> list[dict]:
    """
    Main entry point: returns articles from live feeds or cache.
    Also saves fresh articles to cache for offline use.
    """
    if demo_mode:
        return load_demo_articles()

    articles = fetch_all_feeds()

    # Save to cache as fallback for next time
    if articles:
        Path(CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        print(f"[harvester] Saved {len(articles)} articles to cache.")

    return articles
