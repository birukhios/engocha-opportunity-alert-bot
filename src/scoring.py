"""Keyword scoring for Engocha funding and personal job opportunities."""

from __future__ import annotations

import re
from dataclasses import dataclass


MIN_SCORE = 3


FUNDING_KEYWORDS = [
    "Ethiopia",
    "Africa",
    "grant",
    "funding",
    "startup",
    "innovation",
    "AI",
    "research",
    "survey",
    "data collection",
    "civic tech",
    "digital public goods",
    "youth employment",
    "social impact",
    "market research",
    "community data",
    "fintech",
]


JOB_KEYWORDS = [
    "Product Manager",
    "Digital Product",
    "UX Research",
    "Research Officer",
    "Innovation Officer",
    "MEAL",
    "Monitoring and Evaluation",
    "Data Officer",
    "Program Manager",
    "ICT Officer",
    "Digital Transformation",
    "Fintech",
    "NGO",
    "Addis Ababa",
    "Ethiopia",
    "Remote",
]


EXTRA_WEIGHT_KEYWORDS = {
    "ethiopia": 3,
    "africa": 2,
    "product manager": 3,
    "ux research": 3,
    "grant": 3,
    "funding": 3,
    "ai": 2,
    "research": 2,
    "digital product": 3,
}


@dataclass(frozen=True)
class ScoreResult:
    score: int
    matched_keywords: list[str]


def score_opportunity(opportunity: dict) -> ScoreResult:
    """Score an opportunity from normalized source fields."""
    opportunity_type = opportunity.get("type", "job")
    keywords = FUNDING_KEYWORDS if opportunity_type == "funding" else JOB_KEYWORDS
    haystack = _searchable_text(opportunity)

    matched: list[str] = []
    total = 0
    for keyword in keywords:
        if _contains_keyword(haystack, keyword):
            matched.append(keyword)
            total += EXTRA_WEIGHT_KEYWORDS.get(keyword.lower(), 1)

    return ScoreResult(score=total, matched_keywords=matched)


def why_it_fits(opportunity: dict, matched_keywords: list[str]) -> str:
    """Return a concise human-readable explanation for the Telegram alert."""
    if not matched_keywords:
        return "It matched the configured opportunity profile."

    top_terms = ", ".join(matched_keywords[:5])
    if opportunity.get("type") == "funding":
        return f"It lines up with Engocha's focus through: {top_terms}."
    return f"It matches your target role and geography signals through: {top_terms}."


def _searchable_text(opportunity: dict) -> str:
    values = [
        opportunity.get("title", ""),
        opportunity.get("summary", ""),
        opportunity.get("organization", ""),
        opportunity.get("source", ""),
        opportunity.get("location", ""),
        opportunity.get("deadline", ""),
    ]
    return " ".join(str(value) for value in values if value).lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    normalized = keyword.lower()
    if len(normalized) <= 3 and normalized.isalpha():
        return re.search(rf"\b{re.escape(normalized)}\b", text) is not None
    return normalized in text
