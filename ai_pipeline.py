"""
ai_pipeline.py — Gemini-powered filtering and summarization for AI Pulse

Two-pass pipeline:
  Pass 1: Relevance scoring (filter articles below threshold)
  Pass 2: Content generation (headline, summary, why it matters, challenge)
"""
import os
import json
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL, RELEVANCE_THRESHOLD, READING_WPM, TOPIC_CATEGORIES


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class RelevanceResult(BaseModel):
    relevant: bool = Field(description="Is this article relevant to CS/software engineering students?")
    score: int = Field(description="Relevance score from 1 (irrelevant) to 10 (highly relevant) for CS undergrad students")
    reason: str = Field(description="One sentence explaining the score")


class ArticleContent(BaseModel):
    headline: str = Field(description="Catchy, student-friendly headline (max 12 words)")
    summary: str = Field(description="2-3 sentence plain-language summary of the article for a newsletter")
    why_it_matters: str = Field(description="1-2 sentences explaining why a CS/software engineering student should care about this")
    quick_challenge: str = Field(description="One actionable thing a student can try or explore today based on this article")
    category: str = Field(description=f"Best category from: {', '.join(TOPIC_CATEGORIES)}")
    reading_time: int = Field(description="Estimated reading time in minutes for the original article (1-15)")


# ─── Gemini Client ────────────────────────────────────────────────────────────

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# ─── Pass 1: Relevance Filter ─────────────────────────────────────────────────

def score_relevance(article: dict) -> RelevanceResult:
    """
    Ask Gemini to score an article's relevance to CS students (1-10).
    Returns a RelevanceResult with score, relevant flag, and reason.
    """
    client = _get_client()

    prompt = f"""You are a Computer Science professor evaluating whether a news article is useful for undergraduate CS and software engineering students.

Article Title: {article['title']}
Source: {article['source']}
Summary: {article.get('summary', 'No summary available.')}

Evaluate this article's relevance to CS students on topics like:
- AI/ML tools and models
- Software engineering practices
- Programming languages and frameworks  
- Career opportunities in tech
- Open-source projects
- AI ethics and safety
- Learning resources and courses

Score it 1-10 (10 = extremely relevant, 1 = completely irrelevant to CS students).
Be strict: general tech news, business deals without technical impact, and celebrity tech stories should score low (1-4).
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RelevanceResult,
        ),
    )
    return response.parsed


# ─── Pass 2: Content Generation ───────────────────────────────────────────────

def generate_article_content(article: dict) -> ArticleContent:
    """
    For a relevant article, generate all newsletter content fields via Gemini.
    """
    client = _get_client()

    prompt = f"""You are writing content for an AI newsletter aimed at college CS students.

Original Article:
Title: {article['title']}
Source: {article['source']}
Content: {article.get('summary', '')}
Link: {article.get('link', '')}

Create engaging newsletter content for this article. Use simple, enthusiastic language that excites students about AI. Avoid jargon — if you use a technical term, briefly explain it.

Available categories: {', '.join(TOPIC_CATEGORIES)}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ArticleContent,
        ),
    )
    return response.parsed


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def process_articles(
    articles: list[dict],
    threshold: int = RELEVANCE_THRESHOLD,
    progress_callback=None,
) -> list[dict]:
    """
    Full two-pass pipeline: score → filter → generate content.

    Args:
        articles:           Raw article dicts from harvester
        threshold:          Minimum relevance score to keep
        progress_callback:  Optional callable(step, total, message) for UI progress

    Returns:
        List of enriched article dicts ready for the coordinator dashboard
    """
    total = len(articles)
    results = []

    for i, article in enumerate(articles):
        if progress_callback:
            progress_callback(i, total, f"Scoring: {article['title'][:60]}…")

        # ── Pass 1: Relevance check ──────────────────────────────────────────
        try:
            relevance = score_relevance(article)
        except Exception as e:
            print(f"[ai_pipeline] Relevance check failed for '{article['title']}': {e}")
            continue

        article["relevance_score"] = relevance.score
        article["relevance_reason"] = relevance.reason
        article["included"] = relevance.relevant and relevance.score >= threshold

        if not article["included"]:
            print(f"  ✗ Filtered out (score={relevance.score}): {article['title'][:60]}")
            results.append(article)   # keep in results but marked excluded
            continue

        print(f"  ✓ Relevant (score={relevance.score}): {article['title'][:60]}")

        # ── Pass 2: Content generation ───────────────────────────────────────
        if progress_callback:
            progress_callback(i, total, f"Generating content: {article['title'][:50]}…")

        try:
            content = generate_article_content(article)
            article.update({
                "ai_headline":    content.headline,
                "ai_summary":     content.summary,
                "why_it_matters": content.why_it_matters,
                "quick_challenge": content.quick_challenge,
                "category":       content.category,
                "reading_time":   content.reading_time,
            })
        except Exception as e:
            print(f"[ai_pipeline] Content generation failed for '{article['title']}': {e}")
            # Fallback: use original title/summary
            article.update({
                "ai_headline":    article["title"],
                "ai_summary":     article.get("summary", ""),
                "why_it_matters": "This article may be relevant to your CS studies.",
                "quick_challenge": "Read the full article and share your thoughts.",
                "category":       "🛠️ Tools & Products",
                "reading_time":   3,
            })

        results.append(article)

    if progress_callback:
        progress_callback(total, total, "AI processing complete!")

    return results
