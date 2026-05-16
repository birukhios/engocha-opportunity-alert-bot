"""Keyword scoring for Engocha funding and personal job opportunities."""

from __future__ import annotations

import re
from dataclasses import dataclass


MIN_SCORE = 3
FUNDING_MIN_SCORE = 5


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
    "entrepreneurship",
    "SME",
    "MSME",
    "women",
    "climate",
    "governance",
    "open data",
    "digital inclusion",
    "financial inclusion",
]


JOB_KEYWORDS = [
    "Product Manager",
    "Product Owner",
    "Product Lead",
    "Digital Product",
    "UX Research",
    "User Research",
    "Design Research",
    "Research Officer",
    "Research Manager",
    "Research Consultant",
    "Innovation Officer",
    "Innovation Manager",
    "Innovation",
    "MEAL",
    "Monitoring and Evaluation",
    "M&E",
    "Data Officer",
    "Data Analyst",
    "Data Manager",
    "Data Visualization",
    "Program Manager",
    "Programme Manager",
    "Program Analyst",
    "Programme Analyst",
    "Program Advisor",
    "Programme Advisor",
    "Project Manager",
    "ICT Officer",
    "Digital Transformation",
    "Digital Development",
    "Fintech",
    "NGO",
    "Humanitarian",
    "International Development",
    "Addis Ababa",
    "Ethiopia",
    "Africa",
    "Remote",
    "Home based",
    "Home-based",
    "Full-time",
    "Full time",
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
    "product owner": 3,
    "product lead": 3,
    "user research": 3,
    "design research": 3,
    "innovation": 2,
    "meal": 3,
    "monitoring and evaluation": 3,
    "m&e": 3,
    "data analyst": 2,
    "data manager": 2,
    "data visualization": 3,
    "program manager": 2,
    "programme manager": 2,
    "program analyst": 2,
    "programme analyst": 2,
    "program advisor": 2,
    "programme advisor": 2,
    "project manager": 2,
    "remote": 3,
    "home based": 3,
    "home-based": 3,
    "full-time": 2,
    "full time": 2,
    "entrepreneurship": 2,
    "sme": 2,
    "msme": 2,
    "financial inclusion": 3,
    "digital inclusion": 3,
    "open data": 3,
    "civic tech": 3,
    "digital public goods": 3,
    "data collection": 2,
    "market research": 3,
    "community data": 3,
    "social impact": 2,
    "youth employment": 3,
}


FUNDING_GEO_KEYWORDS = {
    "ethiopia",
    "africa",
}


FUNDING_ENGOCHA_KEYWORDS = {
    "startup",
    "innovation",
    "ai",
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
    "entrepreneurship",
    "sme",
    "msme",
    "open data",
    "digital inclusion",
    "financial inclusion",
}


FUNDING_EXCLUSION_KEYWORDS = {
    "clinical trial",
    "oncology",
    "diabetes",
    "minority institutions",
    "biomedical",
    "life science",
    "life sciences",
    "postdoctoral",
    "criminal justice",
}


JOB_SKILL_KEYWORDS = {
    "product manager",
    "product owner",
    "product lead",
    "digital product",
    "ux research",
    "user research",
    "design research",
    "research officer",
    "research manager",
    "research consultant",
    "innovation officer",
    "innovation manager",
    "innovation",
    "meal",
    "monitoring and evaluation",
    "m&e",
    "data officer",
    "data analyst",
    "data manager",
    "data visualization",
    "program manager",
    "programme manager",
    "program analyst",
    "programme analyst",
    "program advisor",
    "programme advisor",
    "project manager",
    "ict officer",
    "digital transformation",
    "digital development",
    "fintech",
}


JOB_WORK_FIT_KEYWORDS = {
    "ethiopia",
    "addis ababa",
    "africa",
    "remote",
    "home based",
    "home-based",
    "full-time",
    "full time",
}


JOB_EXCLUSION_KEYWORDS = {
    "internship",
    "intern ",
    "volunteer",
    "unpaid",
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


def is_relevant_match(opportunity: dict, matched_keywords: list[str]) -> bool:
    """Apply stricter fit gates after keyword scoring."""
    if opportunity.get("type") == "funding":
        return _is_relevant_funding(opportunity, matched_keywords)

    normalized_matches = {keyword.lower() for keyword in matched_keywords}
    text = _searchable_text(opportunity)
    title_text = str(opportunity.get("title", "")).lower()
    has_skill_fit = any(keyword in title_text for keyword in JOB_SKILL_KEYWORDS)
    has_work_fit = bool(normalized_matches & JOB_WORK_FIT_KEYWORDS)
    is_excluded = any(excluded in text for excluded in JOB_EXCLUSION_KEYWORDS)
    return has_skill_fit and has_work_fit and not is_excluded


def _is_relevant_funding(opportunity: dict, matched_keywords: list[str]) -> bool:
    normalized_matches = {keyword.lower() for keyword in matched_keywords}
    text = _searchable_text(opportunity)
    has_geo_fit = bool(normalized_matches & FUNDING_GEO_KEYWORDS)
    engocha_hits = normalized_matches & FUNDING_ENGOCHA_KEYWORDS
    is_excluded = any(excluded in text for excluded in FUNDING_EXCLUSION_KEYWORDS)

    # Engocha should see startup/social impact/data/digital funding, not every
    # generic research notice that happens to contain "funding".
    return not is_excluded and (has_geo_fit or len(engocha_hits) >= 2)


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
