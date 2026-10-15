"""
ai_pipeline.py — AI filtering and summarization for AI Pulse

Two-pass pipeline (after a deduplication step):
  Pass 1: Relevance scoring — articles scoring below RELEVANCE_THRESHOLD are discarded
  Pass 2: Content generation — headline, summary, why it matters, challenge, category

Uses Gemini when GEMINI_API_KEY is set; otherwise a built-in mock that produces
realistic output offline. Run `python ai_pipeline.py --test` to check the setup.
"""
import hashlib
import re
import sys
from typing import Optional

from pydantic import BaseModel, Field

import config
from config import GEMINI_MODEL, RELEVANCE_THRESHOLD, TOPIC_CATEGORIES


# ─── Schemas ──────────────────────────────────────────────────────────────────

class RelevanceResult(BaseModel):
    relevant: bool = Field(description="Is this article relevant to CS/software engineering students?")
    score: int = Field(description="Relevance score from 1 (irrelevant) to 10 (highly relevant)")
    reason: str = Field(description="One sentence explaining the score")


class ArticleContent(BaseModel):
    headline: str = Field(description="Catchy, student-friendly headline (max 10 words)")
    summary: str = Field(description="2-3 sentences, plain language")
    why_it_matters: str = Field(description="One sentence on why a CS student should care")
    topic_category: str = Field(description="One of: Tools | Research | Career | Open Source | Industry")
    quick_challenge: str = Field(description="One actionable thing to try today (one sentence)")
    reading_time: int = Field(description="Estimated minutes to read the original article (1-15)")


# ─── Text helpers ─────────────────────────────────────────────────────────────

_STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
              "is", "are", "now", "new", "its", "at", "from", "as", "that", "this"}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOPWORDS}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _shorten_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(",;:–-") + "…"


def normalize_category(value: str) -> str:
    """Map whatever the model returned onto one of TOPIC_CATEGORIES."""
    v = (value or "").lower()
    for cat in TOPIC_CATEGORIES:
        if cat.lower() in v:
            return cat
    return "Industry"


# ─── Deduplication ────────────────────────────────────────────────────────────

def mark_duplicates(articles: list[dict], similarity: float = 0.6) -> list[dict]:
    """
    Flag near-duplicate stories (same news from two sources) by title word overlap.
    The first occurrence is kept; later ones get duplicate_of = first title.
    """
    kept: list[tuple[set[str], dict]] = []
    for a in articles:
        toks = _tokens(a.get("title", ""))
        a["duplicate_of"] = None
        for other_toks, other in kept:
            union = toks | other_toks
            if union and len(toks & other_toks) / len(union) >= similarity:
                a["duplicate_of"] = other["title"]
                break
        else:
            kept.append((toks, a))
    return articles


# ─── Mock AI (no API key needed) ──────────────────────────────────────────────

_POSITIVE = {
    "model": 1, "models": 1, "llm": 2, "llms": 2, "open-source": 2, "open": 1, "api": 2,
    "developer": 2, "developers": 2, "code": 2, "coding": 2, "codebase": 2, "programming": 2,
    "framework": 2, "library": 2, "python": 2, "github": 2, "agents": 2, "agent": 2,
    "benchmark": 1, "research": 1, "paper": 1, "training": 1, "fine-tuning": 2, "rag": 2,
    "students": 2, "course": 2, "free": 1, "certification": 2, "learn": 1, "skills": 1,
    "software": 2, "engineering": 1, "ide": 2, "rlhf": 2, "hallucinations": 1, "reasoning": 1,
    "context": 1, "hugging": 1, "deploy": 1, "neural": 1, "jobs": 1, "career": 2,
    "open-sources": 2, "multimodal": 1, "vision": 1, "token": 1, "license": 1, "math": 1,
    "science": 1, "regulation": 1, "compliance": 1, "networks": 1, "parameters": 1,
}
_NEGATIVE = {
    "coffee": 5, "chef": 5, "recipe": 4, "recipes": 4, "restaurant": 4, "michelin": 4,
    "fast": 1, "food": 4, "drive-through": 4, "celebrity": 4, "fashion": 4, "sports": 3,
    "raises": 2, "funding": 2, "valuation": 2, "stock": 2, "cinematic": 1, "consumer": 1,
}


def _mock_relevance(article: dict) -> RelevanceResult:
    words = re.findall(r"[a-z0-9$-]+", f"{article.get('title', '')} {article.get('summary', '')}".lower())
    pos = sum(_POSITIVE.get(w, 0) for w in set(words))
    neg = sum(_NEGATIVE.get(w, 0) for w in set(words))
    score = max(1, min(10, round(5.5 + pos * 0.3 - neg * 1.0)))
    if score >= 8:
        reason = "Directly useful to CS students: covers tools, models or skills they can use or learn from."
    elif score >= RELEVANCE_THRESHOLD:
        reason = "Relevant tech news with clear takeaways for software engineering students."
    elif score >= 4:
        reason = "Loosely AI-related, but mostly business or consumer news with little to learn from."
    else:
        reason = "Consumer or lifestyle story that mentions AI; nothing a CS student can apply."
    return RelevanceResult(relevant=score >= RELEVANCE_THRESHOLD, score=score, reason=reason)


_CATEGORY_KEYWORDS = {
    "Career":      {"career", "jobs", "hiring", "certification", "course", "students", "skills", "report", "companies"},
    "Open Source": {"open-source", "open", "license", "llama", "mixtral", "hugging", "weights", "nemo"},
    "Research":    {"research", "paper", "benchmark", "benchmarks", "study", "arxiv", "olympiad", "rlhf", "method", "phd-level"},
    "Tools":       {"ide", "copilot", "api", "framework", "library", "tool", "langgraph", "cursor", "replit", "deploys"},
}

_WHY = {
    "Tools":       "Tools like this are changing how code gets written, and knowing them early is a real edge in internships.",
    "Research":    "Today's research results become tomorrow's interview questions and project ideas.",
    "Career":      "It shapes which skills recruiters will look for when you apply for internships and jobs.",
    "Open Source": "Open models and code mean you can run, study and build on this yourself for free.",
    "Industry":    "It shows where the industry is heading and which skills will be in demand.",
}

_CHALLENGE = {
    "Tools":       "Try it on one small task from your current assignment and compare it with your usual workflow.",
    "Research":    "Skim the abstract and figures, then explain the key idea to a friend in two sentences.",
    "Career":      "Add one skill from this story to your learning list and spend 30 minutes on it this week.",
    "Open Source": "Find the repo or model card, star it, and run the quickstart example locally or in Colab.",
    "Industry":    "Write down one product idea this trend makes possible and share it with your club.",
}


def _mock_category(article: dict) -> str:
    words = set(re.findall(r"[a-z0-9-]+", f"{article.get('title', '')} {article.get('summary', '')}".lower()))
    best, best_hits = "Industry", 0
    for cat, keys in _CATEGORY_KEYWORDS.items():
        hits = len(words & keys)
        if hits > best_hits:
            best, best_hits = cat, hits
    return best


def _mock_content(article: dict) -> ArticleContent:
    category = _mock_category(article)
    title = re.split(r"\s[–—]\s", article.get("title", ""))[0]
    summary = " ".join(_sentences(article.get("summary", ""))[:2]) or article.get("title", "")
    digest = int(hashlib.md5(article.get("link", "").encode()).hexdigest(), 16)
    return ArticleContent(
        headline=_shorten_words(title, 10),
        summary=summary,
        why_it_matters=_WHY[category],
        topic_category=category,
        quick_challenge=_CHALLENGE[category],
        reading_time=3 + digest % 5,
    )


# ─── Gemini ───────────────────────────────────────────────────────────────────

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai   # imported lazily so mock mode needs no Gemini SDK
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _gemini_json(prompt: str, schema: type[BaseModel]):
    from google.genai import types
    response = _get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    if response.parsed is None:
        raise ValueError(f"Gemini returned unparseable output: {response.text[:200]}")
    return response.parsed


def score_relevance(article: dict, use_mock: Optional[bool] = None) -> RelevanceResult:
    """Pass 1: rate an article's relevance to CS students (1-10)."""
    if config.MOCK_AI if use_mock is None else use_mock:
        return _mock_relevance(article)

    prompt = f"""You are a CS faculty member. Rate this article's relevance to undergraduate CS/software engineering students on a scale of 1-10.

Title: {article['title']}
Source: {article['source']}
Summary: {article.get('summary') or 'No summary available.'}

High scores: AI/ML tools and models, software engineering practice, languages and frameworks, open-source projects, careers in tech, learning resources, AI ethics and safety.
Be strict: business deals without technical impact, consumer gadgets and celebrity or lifestyle stories score 1-4.
Return JSON: {{relevant: bool, score: int, reason: str}} with a one-sentence reason."""
    return _gemini_json(prompt, RelevanceResult)


def generate_article_content(article: dict, use_mock: Optional[bool] = None) -> ArticleContent:
    """Pass 2: generate compact newsletter content for a relevant article."""
    if config.MOCK_AI if use_mock is None else use_mock:
        return _mock_content(article)

    prompt = f"""Generate newsletter content for this article, for a compact AI newsletter read by college CS students.

Title: {article['title']}
Source: {article['source']}
Content: {article.get('summary', '')}

Keep it short and plain: headline max 10 words, summary 2-3 short sentences (under 50 words),
why_it_matters and quick_challenge one sentence each. Explain any jargon briefly.
topic_category must be one of: {', '.join(TOPIC_CATEGORIES)}."""
    return _gemini_json(prompt, ArticleContent)


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def process_articles(
    articles: list[dict],
    threshold: int = RELEVANCE_THRESHOLD,
    progress_callback=None,
    use_mock: Optional[bool] = None,
) -> list[dict]:
    """
    Dedupe → score → filter → generate content.

    Every article is returned with a `status`:
      "duplicate" — same story as an earlier article
      "filtered"  — relevance score below threshold
      "pending"   — relevant; waiting for coordinator review
    """
    mock = config.MOCK_AI if use_mock is None else use_mock
    total = len(articles)
    mark_duplicates(articles)

    for i, article in enumerate(articles):
        title = article.get("title", "")[:60]
        article["ai_engine"] = "mock" if mock else "gemini"

        if article["duplicate_of"]:
            article.update(status="duplicate", relevance_score=0,
                           relevance_reason=f"Duplicate of: {article['duplicate_of']}")
            continue

        if progress_callback:
            progress_callback(i, total, f"Scoring: {title}…")
        try:
            relevance = score_relevance(article, use_mock=mock)
        except Exception as e:
            print(f"[ai_pipeline] Gemini scoring failed for '{title}', using mock: {e}")
            relevance = _mock_relevance(article)
            article["ai_engine"] = "mock (fallback)"

        article["relevance_score"] = relevance.score
        article["relevance_reason"] = relevance.reason
        if relevance.score < threshold:
            article["status"] = "filtered"
            continue

        if progress_callback:
            progress_callback(i, total, f"Writing: {title}…")
        try:
            content = generate_article_content(article, use_mock=mock)
        except Exception as e:
            print(f"[ai_pipeline] Gemini content failed for '{title}', using mock: {e}")
            content = _mock_content(article)
            article["ai_engine"] = "mock (fallback)"

        article.update(
            status="pending",
            ai_headline=content.headline,
            ai_summary=content.summary,
            why_it_matters=content.why_it_matters,
            quick_challenge=content.quick_challenge,
            category=normalize_category(content.topic_category),
            reading_time=max(1, min(15, int(content.reading_time))),
        )

    if progress_callback:
        progress_callback(total, total, "AI processing complete!")
    return articles


def ensure_content(article: dict, use_mock: Optional[bool] = None) -> dict:
    """Generate content for an article the coordinator rescued from the filtered list."""
    if not article.get("ai_headline"):
        try:
            content = generate_article_content(article, use_mock=use_mock)
        except Exception:
            content = _mock_content(article)
        article.update(
            ai_headline=content.headline,
            ai_summary=content.summary,
            why_it_matters=content.why_it_matters,
            quick_challenge=content.quick_challenge,
            category=normalize_category(content.topic_category),
            reading_time=max(1, min(15, int(content.reading_time))),
        )
    return article


if __name__ == "__main__":
    if "--test" not in sys.argv:
        print("Usage: python ai_pipeline.py --test")
        sys.exit(1)
    sample = {
        "title": "Hugging Face Releases Open Leaderboard for Real-World Coding Tasks",
        "source": "HuggingFace",
        "link": "https://huggingface.co/blog/example",
        "summary": "A new benchmark tests open-source code models on GitHub issues from real Python projects.",
    }
    engine = "mock (no GEMINI_API_KEY)" if config.MOCK_AI else f"Gemini ({GEMINI_MODEL})"
    print(f"Engine: {engine}")
    rel = score_relevance(sample)
    print("Pass 1:", rel.model_dump_json())
    content = generate_article_content(sample)
    print("Pass 2:", content.model_dump_json(indent=2))
