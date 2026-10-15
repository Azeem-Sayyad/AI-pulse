"""
harvester.py — RSS Feed ingestion module for AI Pulse
Fetches articles from approved sources; falls back to cached data when offline.

Run `python harvester.py` to check that every approved feed parses.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests

from config import (RSS_FEEDS, MAX_ARTICLES_PER_FEED, CACHE_PATH, LIVE_CACHE_PATH,
                    FEED_TIMEOUT_SECONDS)

USER_AGENT = "AI-Pulse/1.0 Newsletter Bot"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(entry) -> str:
    """Return the entry's date as an RFC 2822 string (now, if the feed gives none)."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(attr)
        if val:
            return datetime(*val[:6], tzinfo=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    for attr in ("published", "updated", "created"):
        if entry.get(attr):
            return entry.get(attr)
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def parse_published(value: str) -> datetime:
    """Parse a stored published string into an aware datetime (epoch on failure)."""
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _entry_to_dict(entry, source_name: str) -> dict:
    """Convert a feedparser entry to a clean dict."""
    content = entry.get("content") or [{}]
    raw_summary = (
        entry.get("summary", "")
        or entry.get("description", "")
        or content[0].get("value", "")
    )
    return {
        "title":     _strip_html(entry.get("title", "Untitled")),
        "link":      entry.get("link", ""),
        "summary":   _strip_html(raw_summary)[:600],
        "published": _parse_date(entry),
        "source":    source_name,
    }


def normalize_url(url: str) -> str:
    """Canonical form of a URL for duplicate detection."""
    url = (url or "").strip().lower()
    url = re.sub(r"^https?://(www\.)?", "", url)
    url = url.split("#")[0].split("?")[0]
    return url.rstrip("/")


def dedupe_by_url(articles: list[dict]) -> list[dict]:
    """Drop articles whose normalized URL has already been seen."""
    seen: set[str] = set()
    unique = []
    for a in articles:
        key = normalize_url(a.get("link", ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


# ─── Live Fetch ───────────────────────────────────────────────────────────────

def fetch_feed(url: str, source_name: str, max_items: int = MAX_ARTICLES_PER_FEED) -> list[dict]:
    """Parse a single RSS feed URL and return a list of article dicts."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=FEED_TIMEOUT_SECONDS)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        articles = []
        for entry in feed.entries[:max_items]:
            a = _entry_to_dict(entry, source_name)
            if a["title"] and a["link"]:
                articles.append(a)
        return articles
    except Exception as e:
        print(f"[harvester] Failed to fetch {source_name}: {e}")
        return []


def fetch_all_feeds(feeds: dict | None = None, progress_callback=None) -> list[dict]:
    """Fetch all approved RSS feeds in parallel; returns a URL-deduplicated list."""
    feeds = feeds if feeds is not None else RSS_FEEDS
    results: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_feed, url, name): name for name, url in feeds.items()}
        for done, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            results[name] = future.result()
            print(f"[harvester] {name}: {len(results[name])} articles")
            if progress_callback:
                progress_callback(done, len(feeds), f"Fetched {name}")
    # Keep the configured source order so results are stable
    all_articles = [a for name in feeds for a in results.get(name, [])]
    unique = dedupe_by_url(all_articles)
    print(f"[harvester] Total unique articles: {len(unique)}")
    return unique


# ─── Demo / Cache Mode ────────────────────────────────────────────────────────

def _load_json(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_demo_articles() -> list[dict]:
    """Load the curated demo articles (includes a few deliberately irrelevant ones)."""
    data = _load_json(CACHE_PATH)
    print(f"[harvester] Loaded {len(data)} demo articles from cache.")
    return data


def get_articles(demo_mode: bool = False, progress_callback=None) -> tuple[list[dict], str]:
    """
    Main entry point. Returns (articles, origin) where origin is one of
    "demo", "live", "live-cache" (offline fallback to last live fetch) or "demo-fallback".
    """
    if demo_mode:
        return dedupe_by_url(load_demo_articles()), "demo"

    articles = fetch_all_feeds(progress_callback=progress_callback)
    if articles:
        Path(LIVE_CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(LIVE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        return articles, "live"

    cached = _load_json(LIVE_CACHE_PATH)
    if cached:
        print("[harvester] Network unavailable — using last live fetch.")
        return dedupe_by_url(cached), "live-cache"

    print("[harvester] Network unavailable — using demo articles.")
    return dedupe_by_url(load_demo_articles()), "demo-fallback"


if __name__ == "__main__":
    ok = 0
    for name, url in RSS_FEEDS.items():
        items = fetch_feed(url, name)
        status = "OK " if items else "FAIL"
        ok += bool(items)
        print(f"  {status} {name:22} {len(items)} articles")
        if items:
            print(f"       e.g. {items[0]['title'][:70]}")
    print(f"\n{ok}/{len(RSS_FEEDS)} feeds returned articles.")
    sys.exit(0 if ok else 1)
