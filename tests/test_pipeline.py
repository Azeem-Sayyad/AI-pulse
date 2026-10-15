from datetime import datetime, timezone

import config
import database as db
from ai_pipeline import mark_duplicates, process_articles
from harvester import _entry_to_dict, dedupe_by_url, load_demo_articles
from publisher import generate_newsletter, group_articles, select_for_edition

IRRELEVANT = ("Coffee Machine", "Celebrity Chef", "Fast Food")


def _processed():
    return process_articles(load_demo_articles())


def test_summary_fallback_uses_content_when_summary_missing():
    entry = {"title": "T", "link": "https://x", "content": [{"value": "<p>Body text</p>"}]}
    assert _entry_to_dict(entry, "Src")["summary"] == "Body text"
    entry = {"title": "T", "link": "https://x", "summary": "<b>Short</b>"}
    assert _entry_to_dict(entry, "Src")["summary"] == "Short"


def test_url_dedupe_ignores_scheme_www_and_query():
    arts = [{"link": "https://www.a.com/post/?utm=1"}, {"link": "http://a.com/post"}]
    assert len(dedupe_by_url(arts)) == 1


def test_near_duplicate_titles_are_flagged():
    arts = mark_duplicates([
        {"title": "OpenAI releases GPT-5 model for developers"},
        {"title": "OpenAI releases the GPT-5 model to developers"},
        {"title": "Mistral open-sources a new coding model"},
    ])
    assert [a["duplicate_of"] is not None for a in arts] == [False, True, False]


def test_irrelevant_demo_articles_are_filtered_below_threshold():
    arts = _processed()
    assert config.RELEVANCE_THRESHOLD == 7
    for a in arts:
        if any(k in a["title"] for k in IRRELEVANT):
            assert a["status"] == "filtered" and a["relevance_score"] <= 3
        if a["status"] == "pending":
            assert a["relevance_score"] >= config.RELEVANCE_THRESHOLD
            assert a["category"] in config.TOPIC_CATEGORIES
            assert len(a["ai_headline"].split()) <= 11
    assert sum(a["status"] == "pending" for a in arts) >= 8


def test_weekly_and_monthly_editions_differ():
    approved = [a for a in _processed() if a["status"] == "pending"]
    weekly = select_for_edition([dict(a) for a in approved], "weekly")
    monthly = select_for_edition([dict(a) for a in approved], "monthly")
    assert 0 < len(weekly["articles"]) <= config.EDITIONS["weekly"]["max_items"]
    assert len(monthly["articles"]) > len(weekly["articles"])
    assert all(g["label"].split()[-1] in config.TOPIC_CATEGORIES or "Open Source" in g["label"]
               for g in group_articles(weekly["articles"], "weekly"))
    assert all("Week of" in g["label"] for g in group_articles(monthly["articles"], "monthly"))


def test_newsletter_renders_compact_html_and_markdown(isolated_paths):
    approved = [a for a in _processed() if a["status"] == "pending"]
    approved[0]["ai_headline"] = "Edited <headline> by coordinator"
    out = generate_newsletter(approved, fmt="monthly")
    assert "Edited &lt;headline&gt; by coordinator" in out["html"]
    assert "Edited <headline> by coordinator" in out["markdown"]
    assert "Coffee" not in out["html"]
    assert out["html_path"].endswith(".html") and out["md_path"].endswith(".md")
    # Compact: whole monthly edition stays small enough for an email body
    assert len(out["html"]) < 25_000


def test_database_round_trip():
    db.init_db()
    arts = _processed()
    db.replace_articles(arts)
    stored = db.get_all_articles()
    assert len(stored) == len(arts)
    link = next(a["link"] for a in stored if a["status"] == "pending")
    db.update_article(link, {"status": "approved", "ai_headline": "New"})
    approved = db.get_approved_articles()
    assert [a["ai_headline"] for a in approved] == ["New"]
    nid = db.save_newsletter("AI Pulse", "note", "<html>", "# md", "weekly")
    assert db.get_newsletter(nid)["md_content"] == "# md"


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>
<item><title>New open-source LLM for coding</title><link>https://example.com/a</link>
<description>&lt;p&gt;A model for developers.&lt;/p&gt;</description>
<pubDate>Mon, 13 Oct 2025 10:00:00 +0000</pubDate></item>
<item><title>Same story again</title><link>https://www.example.com/a/</link></item>
</channel></rss>"""


def test_live_fetch_parses_feeds_and_dedupes(monkeypatch):
    import harvester

    class Resp:
        content = RSS
        def raise_for_status(self):
            pass

    monkeypatch.setattr(harvester.requests, "get", lambda *a, **k: Resp())
    arts = harvester.fetch_all_feeds({"One": "u1", "Two": "u2"})
    assert len(arts) == 1
    assert arts[0]["summary"] == "A model for developers."
    assert arts[0]["source"] == "One"
    assert arts[0]["published"].startswith("Mon, 13 Oct 2025")


def test_offline_falls_back_to_demo_data(monkeypatch, tmp_path):
    import harvester
    monkeypatch.setattr(harvester, "fetch_all_feeds", lambda **k: [])
    monkeypatch.setattr(harvester, "LIVE_CACHE_PATH", str(tmp_path / "none.json"))
    arts, origin = harvester.get_articles(demo_mode=False)
    assert origin == "demo-fallback" and len(arts) == 26
