"""
config.py — Global configuration for AI Pulse Newsletter Generator
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Keys ────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# ─── Gemini Model ────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"

# ─── Approved RSS Feed Sources ───────────────────────────────────────────────
RSS_FEEDS = {
    "OpenAI":           "https://openai.com/news/rss.xml",
    "HuggingFace":      "https://huggingface.co/blog/feed.xml",
    "TechCrunch AI":    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "MIT Tech Review":  "https://www.technologyreview.com/feed/",
    "The Verge AI":     "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "VentureBeat AI":   "https://venturebeat.com/category/ai/feed/",
    "DeepMind":         "https://deepmind.google/blog/rss.xml",
    "Wired AI":         "https://www.wired.com/feed/tag/ai/latest/rss",
    "arXiv AI":         "https://export.arxiv.org/rss/cs.AI",
}

# ─── Newsletter Settings ─────────────────────────────────────────────────────
MAX_ARTICLES_PER_FEED = 5
RELEVANCE_THRESHOLD   = 6          # Minimum score (out of 10) to include article
MAX_NEWSLETTER_ITEMS  = 7          # Maximum articles in final newsletter
READING_WPM           = 200        # Words per minute for reading-time estimate

# ─── Topic Categories ────────────────────────────────────────────────────────
TOPIC_CATEGORIES = [
    "🔬 Research & Papers",
    "🛠️ Tools & Products",
    "🌐 Open Source",
    "💼 Career & Industry",
    "📚 Learning & Education",
    "🔒 Ethics & Safety",
]

# ─── Category Colours (for UI badges) ────────────────────────────────────────
CATEGORY_COLORS = {
    "🔬 Research & Papers": "#6c63ff",
    "🛠️ Tools & Products":  "#e94560",
    "🌐 Open Source":        "#00b894",
    "💼 Career & Industry":  "#f39c12",
    "📚 Learning & Education": "#0984e3",
    "🔒 Ethics & Safety":   "#d63031",
}

# ─── Paths ───────────────────────────────────────────────────────────────────
CACHE_PATH    = "cache/sample_articles.json"
OUTPUTS_DIR   = "outputs"
TEMPLATE_PATH = "templates/newsletter.html"
DB_PATH       = "newsletter.db"
