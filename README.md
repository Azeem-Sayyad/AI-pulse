# 🤖 AI Pulse — Automated Student Newsletter Generator

Prototype for TCS Tech Day @ VESIT, hackathon problem P7. AI Pulse pulls AI news from approved
RSS feeds, scores each story for relevance to CS students, writes short student-friendly blurbs,
lets a club coordinator review and edit them, and publishes a compact newsletter as HTML and Markdown.

```
RSS feeds ─► harvester.py ─► ai_pipeline.py ─► app.py (Streamlit) ─► publisher.py
             (feedparser,     (dedupe, score    (review, edit,         (HTML + Markdown,
              offline cache)   ≥7/10, write)     approve/reject)         outputs/)
                                     │
                              database.py (SQLite)
```

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # optional: add GEMINI_API_KEY
streamlit run app.py
```

No Gemini key? The app runs end to end with a built-in **mock AI** that scores and summarizes
articles with heuristics, so the demo never depends on network or quota. Add a key to
`.env` to switch to Gemini (`gemini-2.5-flash`); if a Gemini call fails mid-run, that article
falls back to the mock so processing never stops.

| Setting (`.env` or Streamlit secrets) | Effect |
|---|---|
| `GEMINI_API_KEY` | Use Gemini for scoring and writing. Empty = mock AI. |
| `DEMO_MODE=true` | Start with Demo Mode on (bundled sample articles instead of live feeds). |
| `MOCK_AI=true` | Force the mock AI even when a key is set. |

The relevance threshold (7/10), edition sizes and feed list live in `config.py`.

## Dashboard

1. **🔍 Fetch & Filter**: fetch live feeds (or load demo data), then score every story. A table shows
   each score with the AI's reasoning; stories below 7/10 and near-duplicates are set aside.
2. **📝 Review & Edit**: an editable card per story (headline, summary, why it matters, challenge,
   category, reading time) with Approve / Reject. Filtered stories can be rescued.
   The sidebar filters cards by category.
3. **📰 Generate Newsletter**: Weekly / Monthly toggle, title and editor's note, one-click publish
   with HTML and Markdown downloads.
4. **👁️ Preview**: the rendered newsletter inline, plus every previously generated edition.

Review decisions are stored in `newsletter.db`, so they survive a browser refresh.

## The newsletter

The output is deliberately compact: a slim header, one line of editor's note, and for each story a
headline, a two-sentence summary, a one-line "Why" and a one-line "Try". Files are written to
`outputs/newsletter_YYYY-MM-DD.html` and `.md` (monthly editions get a `_monthly` suffix).

| Edition | Window | Max stories | Grouped by |
|---|---|---|---|
| Weekly | last 7 days | 6 | topic |
| Monthly | last 30 days | 12 | week |

The window ends at the newest approved story, so the cached demo data produces a full edition.

## Demo script

1. Turn on **Demo Mode** and click **Load Demo Data**. The coffee machine, celebrity chef and
   drive-through stories score 1/10 and are filtered out.
2. In **Review & Edit**, change a headline live, then **Approve all**.
3. **Generate Newsletter** → open **Preview**.
4. Switch **Weekly ↔ Monthly** and generate again: the edition widens and regroups by week.

## Checks

```bash
python harvester.py            # each approved feed parses (needs internet)
python ai_pipeline.py --test   # one article through both AI passes (Gemini or mock)
python publisher.py --test     # renders weekly + monthly demo editions into outputs/
pytest                         # unit tests + a scripted run of the whole dashboard
```

## Deploying to Streamlit Cloud

Push the repo, create an app pointing at `app.py`, and (optionally) add `GEMINI_API_KEY` under
*Secrets*. Nothing else is needed; SQLite and `outputs/` live on the app's local disk.

## Files

| File | Role |
|---|---|
| `app.py` | Streamlit dashboard (entry point) |
| `harvester.py` | Parallel RSS fetch, URL de-duplication, offline fallback to cache |
| `ai_pipeline.py` | Dedupe → relevance score → content generation (Gemini or mock) |
| `publisher.py` | Edition selection, grouping, HTML + Markdown rendering |
| `database.py` | SQLite storage for articles and generated newsletters |
| `config.py` | Feeds, threshold, editions, categories, paths |
| `templates/newsletter.html` | Compact, email-safe Jinja2 template |
| `cache/sample_articles.json` | 26 demo articles, including deliberately irrelevant ones |
