"""
app.py — AI Pulse coordinator dashboard (Streamlit)

Run:  streamlit run app.py
"""
import hashlib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import config
import database as db
from ai_pipeline import ensure_content, process_articles
from harvester import get_articles
from publisher import generate_newsletter, select_for_edition

st.set_page_config(page_title="AI Pulse", page_icon="🤖", layout="wide")

PAGES = ["🔍 Fetch & Filter", "📝 Review & Edit", "📰 Generate Newsletter", "👁️ Preview"]
STATUS_ICON = {"pending": "🕓", "approved": "✅", "rejected": "❌", "filtered": "🚫", "duplicate": "♊"}


# ─── State ────────────────────────────────────────────────────────────────────

db.init_db()
if "articles" not in st.session_state:
    st.session_state.articles = db.get_all_articles()
st.session_state.setdefault("page", PAGES[0])


def _goto(page: str) -> None:
    st.session_state.page = page


def _key(article: dict, field: str) -> str:
    return f"{field}_{hashlib.md5(article['link'].encode()).hexdigest()[:10]}"


def _set_status(article: dict, status: str) -> None:
    article["status"] = status
    db.update_article(article["link"], {"status": status})


def _save_edits(article: dict) -> None:
    fields = {
        "ai_headline":     st.session_state[_key(article, "headline")].strip(),
        "ai_summary":      st.session_state[_key(article, "summary")].strip(),
        "why_it_matters":  st.session_state[_key(article, "why")].strip(),
        "quick_challenge": st.session_state[_key(article, "challenge")].strip(),
        "category":        st.session_state[_key(article, "category")],
        "reading_time":    int(st.session_state[_key(article, "minutes")]),
    }
    article.update(fields)
    db.update_article(article["link"], fields)


def _score_badge(score) -> str:
    score = int(score or 0)
    color = "green" if score >= 8 else "orange" if score >= config.RELEVANCE_THRESHOLD else "red"
    return f":{color}-background[**{score}/10**]"


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🤖 AI Pulse")
    st.caption("Automated AI newsletter for CS students")
    st.radio("Go to", PAGES, key="page", label_visibility="collapsed")
    st.divider()

    demo_mode = st.toggle("Demo Mode (cached articles)", value=config.DEMO_MODE,
                          help="Use the bundled sample articles instead of live RSS feeds.")
    if config.MOCK_AI:
        st.info("**AI engine:** Mock (no Gemini key set). Scores and summaries come from "
                "built-in heuristics so the demo runs offline.", icon="🧪")
    else:
        st.success(f"**AI engine:** Gemini `{config.GEMINI_MODEL}`", icon="✨")
    st.caption(f"Relevance threshold: **{config.RELEVANCE_THRESHOLD}/10**")

    st.divider()
    category_filter = st.multiselect("Filter by category", config.TOPIC_CATEGORIES,
                                     placeholder="All categories")

articles: list[dict] = st.session_state.articles
page = st.session_state.page


# ─── Page 1: Fetch & Filter ───────────────────────────────────────────────────

if page == PAGES[0]:
    st.header("🔍 Fetch & Filter")
    st.write("Pull articles from the approved sources, then let the AI score each one for "
             f"relevance to CS students. Anything below **{config.RELEVANCE_THRESHOLD}/10** is discarded.")

    label = "📦 Load Demo Data" if demo_mode else "🌐 Fetch Latest AI News"
    if st.button(label, type="primary"):
        bar = st.progress(0.0, text="Starting…")

        def on_progress(step, total, msg, offset=0.0, span=1.0):
            bar.progress(min(1.0, offset + span * step / max(total, 1)), text=msg)

        raw, origin = get_articles(demo_mode=demo_mode,
                                   progress_callback=lambda s, t, m: on_progress(s, t, m, 0.0, 0.3))
        if origin == "live-cache":
            st.warning("Feeds unreachable, so the last successful live fetch was used.")
        elif origin == "demo-fallback":
            st.warning("Feeds unreachable, so the demo articles were loaded instead.")

        processed = process_articles(raw, progress_callback=lambda s, t, m: on_progress(s, t, m, 0.3, 0.7))
        db.replace_articles(processed)
        st.session_state.articles = articles = db.get_all_articles()
        st.session_state.pop("newsletter", None)
        bar.progress(1.0, text=f"Done: {len(processed)} articles processed.")

    if not articles:
        st.info("No articles yet. Click the button above to start.")
    else:
        counts = pd.Series([a["status"] for a in articles]).value_counts()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fetched", len(articles))
        c2.metric("Passed AI filter", int(sum(counts.get(s, 0) for s in ("pending", "approved", "rejected"))))
        c3.metric("Filtered out", int(counts.get("filtered", 0)))
        c4.metric("Duplicates", int(counts.get("duplicate", 0)))

        df = pd.DataFrame([{
            "Score": a.get("relevance_score") or 0,
            "Status": f"{STATUS_ICON.get(a['status'], '')} {a['status']}",
            "Title": a["title"],
            "Source": a["source"],
            "AI reasoning": a.get("relevance_reason") or "",
        } for a in articles])
        st.dataframe(
            df, hide_index=True, width="stretch",
            column_config={"Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=10, format="%d/10")},
        )
        if counts.get("pending", 0):
            st.success(f"{counts['pending']} articles are waiting for review.")
            st.button("Go to Review & Edit →", on_click=_goto, args=(PAGES[1],))


# ─── Page 2: Review & Edit ────────────────────────────────────────────────────

elif page == PAGES[1]:
    st.header("📝 Review & Edit")
    reviewable = [a for a in articles if a["status"] in ("pending", "approved", "rejected")]
    if category_filter:
        reviewable = [a for a in reviewable if a.get("category") in category_filter]

    if not reviewable:
        st.info("Nothing to review yet. Fetch articles first.")
    else:
        n_pending = sum(a["status"] == "pending" for a in reviewable)
        n_approved = sum(a["status"] == "approved" for a in reviewable)
        st.write(f"**{n_approved}** approved · **{n_pending}** pending · "
                 f"**{len(reviewable) - n_pending - n_approved}** rejected")
        if n_pending and st.button(f"✅ Approve all {n_pending} pending"):
            for a in reviewable:
                if a["status"] == "pending":
                    if _key(a, "headline") in st.session_state:
                        _save_edits(a)          # keep any unsaved edits
                    _set_status(a, "approved")
            st.rerun()

        for a in reviewable:
            title = (f"{STATUS_ICON[a['status']]} {_score_badge(a.get('relevance_score'))} "
                     f"{a.get('ai_headline') or a['title']}")
            with st.expander(title, expanded=a["status"] == "pending"):
                st.caption(f"{config.CATEGORY_EMOJI.get(a.get('category'), '')} {a.get('category')} · "
                           f"{a['source']} · [original article]({a['link']}) · "
                           f"AI: {a.get('relevance_reason') or ''}")
                st.text_input("Headline", a.get("ai_headline") or "", key=_key(a, "headline"))
                st.text_area("Summary", a.get("ai_summary") or "", key=_key(a, "summary"), height=90)
                st.text_input("💡 Why it matters", a.get("why_it_matters") or "", key=_key(a, "why"))
                st.text_input("⚡ Quick challenge", a.get("quick_challenge") or "", key=_key(a, "challenge"))
                c1, c2 = st.columns(2)
                cat = a.get("category") if a.get("category") in config.TOPIC_CATEGORIES else "Industry"
                c1.selectbox("Category", config.TOPIC_CATEGORIES,
                             index=config.TOPIC_CATEGORIES.index(cat), key=_key(a, "category"))
                c2.number_input("Reading time (min)", 1, 30, int(a.get("reading_time") or 3),
                                key=_key(a, "minutes"))

                b1, b2, b3, _ = st.columns([1, 1, 1, 3])
                if b1.button("✅ Approve", key=_key(a, "approve"), type="primary"):
                    _save_edits(a)
                    _set_status(a, "approved")
                    st.rerun()
                if b2.button("❌ Reject", key=_key(a, "reject")):
                    _set_status(a, "rejected")
                    st.rerun()
                if b3.button("💾 Save", key=_key(a, "save")):
                    _save_edits(a)
                    st.toast("Edits saved")

    dropped = [a for a in articles if a["status"] in ("filtered", "duplicate")]
    if dropped:
        with st.expander(f"🚫 Filtered out by AI ({len(dropped)})"):
            for a in dropped:
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"{_score_badge(a.get('relevance_score'))} **{a['title']}**  \n"
                            f"<small>{a['source']} · {a.get('relevance_reason') or ''}</small>",
                            unsafe_allow_html=True)
                if c2.button("Rescue", key=_key(a, "rescue"),
                             help="Override the AI and send this article to review"):
                    ensure_content(a)
                    a["status"] = "pending"
                    db.update_article(a["link"], a)
                    st.rerun()


# ─── Page 3: Generate Newsletter ──────────────────────────────────────────────

elif page == PAGES[2]:
    st.header("📰 Generate Newsletter")
    approved = [a for a in articles if a["status"] == "approved"]
    if not approved:
        st.info("Approve at least one article on the Review & Edit page first.")
    else:
        fmt_label = st.radio("Edition", [e["label"] for e in config.EDITIONS.values()], horizontal=True)
        fmt = next(k for k, e in config.EDITIONS.items() if e["label"] == fmt_label)
        title = st.text_input("Newsletter title", "AI Pulse")
        note = st.text_area("Editor's note (one or two lines)",
                            f"The AI news worth your time this {'week' if fmt == 'weekly' else 'month'}, "
                            "picked for CS students.", height=70)

        edition = config.EDITIONS[fmt]
        selection = select_for_edition([dict(a) for a in approved], fmt)
        st.caption(f"{fmt_label} editions cover the last {edition['days']} days, up to "
                   f"{edition['max_items']} stories, grouped by "
                   f"{'topic' if fmt == 'weekly' else 'week'}. "
                   f"**{len(selection['articles'])}** of {len(approved)} approved stories fit this edition.")

        if st.button("🚀 Generate Newsletter", type="primary"):
            out = generate_newsletter([dict(a) for a in approved], title, note, fmt)
            db.save_newsletter(title, note, out["html"], out["markdown"], fmt)
            st.session_state.newsletter = out
            st.success(f"Saved `{out['html_path']}` and `{out['md_path']}`")

        out = st.session_state.get("newsletter")
        if out:
            c1, c2, c3 = st.columns(3)
            c1.download_button("⬇️ Download HTML", out["html"], file_name="ai_pulse.html", mime="text/html")
            c2.download_button("⬇️ Download Markdown", out["markdown"], file_name="ai_pulse.md",
                               mime="text/markdown")
            c3.button("👁️ Open Preview", on_click=_goto, args=(PAGES[3],))


# ─── Page 4: Preview ──────────────────────────────────────────────────────────

elif page == PAGES[3]:
    st.header("👁️ Preview")
    out = st.session_state.get("newsletter")
    history = db.get_newsletters()
    if history:
        options = {f"#{n['id']} · {n['title']} ({n['format']}) · {n['created_at']}": n["id"] for n in history}
        choice = st.selectbox("Newsletter", list(options), index=0)
        saved = db.get_newsletter(options[choice])
        out = {"html": saved["html_content"], "markdown": saved["md_content"]}

    if not out:
        st.info("Generate a newsletter first.")
    else:
        tab_html, tab_md = st.tabs(["HTML", "Markdown"])
        with tab_html:
            components.html(out["html"], height=900, scrolling=True)
        with tab_md:
            st.markdown(out["markdown"], unsafe_allow_html=True)
            with st.expander("Raw Markdown"):
                st.code(out["markdown"], language="markdown")
