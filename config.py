"""
config.py — Global configuration for AI Pulse Newsletter Generator
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _secret(name: str, default: str = "") -> str:
    """Read a setting from the environment, then Streamlit secrets (for Streamlit Cloud)."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


# ─── API Keys / Modes ────────────────────────────────────────────────────────
GEMINI_API_KEY = _secret("GEMINI_API_KEY")
if GEMINI_API_KEY.startswith("your_"):          # untouched .env.example placeholder
    GEMINI_API_KEY = ""

# Demo mode: load cached sample articles instead of hitting RSS feeds.
DEMO_MODE = _secret("DEMO_MODE", "false").lower() == "true"

# Mock AI: use built-in heuristics instead of Gemini. Forced on when no key is set.
MOCK_AI = _secret("MOCK_AI", "false").lower() == "true" or not GEMINI_API_KEY

# ─── Gemini Model ────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"

# ─── Approved RSS Feed Sources ───────────────────────────────────────────────
RSS_FEEDS = {
    "OpenAI":               "https://openai.com/blog/rss",
    "HuggingFace":          "https://huggingface.co/blog/feed.xml",
    "TechCrunch AI":        "https://techcrunch.com/category/artificial-intelligence/feed/",
    "MIT Tech Review":      "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "The Batch":            "https://www.deeplearning.ai/the-batch/feed/",
    "GitHub Blog":          "https://github.blog/feed/",
    "Towards Data Science": "https://towardsdatascience.com/feed",
    "Analytics Vidhya":     "https://www.analyticsvidhya.com/feed/",
}

# ─── Newsletter Settings ─────────────────────────────────────────────────────
MAX_ARTICLES_PER_FEED = 5
RELEVANCE_THRESHOLD   = 7          # Articles scoring below this (out of 10) are discarded
FEED_TIMEOUT_SECONDS  = 10

# Edition settings: how far back each edition looks and how many stories it holds.
EDITIONS = {
    "weekly":  {"label": "Weekly",  "days": 7,  "max_items": 6},
    "monthly": {"label": "Monthly", "days": 30, "max_items": 12},
}

# ─── Topic Categories ────────────────────────────────────────────────────────
TOPIC_CATEGORIES = ["Tools", "Research", "Career", "Open Source", "Industry"]

CATEGORY_EMOJI = {
    "Tools":       "🛠️",
    "Research":    "🔬",
    "Career":      "💼",
    "Open Source": "🌐",
    "Industry":    "🏢",
}

CATEGORY_COLORS = {
    "Tools":       "#e94560",
    "Research":    "#6c63ff",
    "Career":      "#f39c12",
    "Open Source": "#00b894",
    "Industry":    "#0984e3",
}

# ─── Paths ───────────────────────────────────────────────────────────────────
CACHE_PATH      = str(BASE_DIR / "cache" / "sample_articles.json")   # curated demo data
LIVE_CACHE_PATH = str(BASE_DIR / "cache" / "live_articles.json")     # last successful live fetch
OUTPUTS_DIR     = str(BASE_DIR / "outputs")
TEMPLATE_PATH   = str(BASE_DIR / "templates" / "newsletter.html")
DB_PATH         = str(BASE_DIR / "newsletter.db")
