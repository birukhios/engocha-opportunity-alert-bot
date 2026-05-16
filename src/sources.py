"""Opportunity source collectors.

The MVP prefers public APIs. Placeholder classes document future integrations
without scraping sites whose terms or robots rules need a separate review.
"""

from __future__ import annotations

import logging
import os
from html import unescape
from abc import ABC, abstractmethod
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from storage import make_opportunity_id, utc_today


LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = "EngochaOpportunityAlert/1.0 (+https://github.com/)"


class OpportunitySource(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> list[dict]:
        raise NotImplementedError


class ReliefWebJobsSource(OpportunitySource):
    name = "ReliefWeb"
    api_url = "https://api.reliefweb.int/v2/jobs"

    def fetch(self) -> list[dict]:
        appname = os.getenv("RELIEFWEB_APP_NAME", "engocha-opportunity-alert")
        query_terms = [
            "Ethiopia",
            "Addis Ababa",
            "Africa",
            "Product Manager",
            "UX Research",
            "MEAL",
            "Monitoring and Evaluation",
            "Digital Transformation",
            "Innovation Officer",
            "Research Officer",
            "Data Officer",
            "Program Manager",
            "ICT Officer",
            "Fintech",
        ]
        params = {
            "appname": appname,
            "profile": "list",
            "limit": 50,
            "sort[]": "date:desc",
            "query[value]": " OR ".join(f'"{term}"' for term in query_terms),
            "fields[include][]": [
                "title",
                "url",
                "source",
                "country",
                "city",
                "date",
                "body",
            ],
        }

        response = requests.get(
            self.api_url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()

        opportunities = []
        for item in payload.get("data", []):
            fields = item.get("fields", {})
            title = fields.get("title", "").strip()
            link = fields.get("url") or f"https://reliefweb.int/job/{item.get('id')}"
            if not title or not link:
                continue

            source_names = _names_from_list(fields.get("source", []))
            country_names = _names_from_list(fields.get("country", []))
            city_names = _names_from_list(fields.get("city", []))
            location = ", ".join(part for part in [", ".join(city_names), ", ".join(country_names)] if part)
            deadline = _nested_date(fields.get("date", {}), "closing")

            opportunities.append(
                _normalized_opportunity(
                    title=title,
                    link=link,
                    source=self.name,
                    opportunity_type="job",
                    organization=", ".join(source_names) or self.name,
                    location=location,
                    deadline=deadline,
                    summary=_html_to_text(fields.get("body", "")),
                )
            )
        return opportunities


class GrantsGovFundingSource(OpportunitySource):
    name = "Grants.gov"
    api_url = "https://api.grants.gov/v1/api/search2"

    def fetch(self) -> list[dict]:
        search_terms = [
            "Ethiopia",
            "Africa",
            "innovation",
            "AI",
            "research",
            "fintech",
            "startup",
            "digital public goods",
            "youth employment",
            "social impact",
            "data collection",
        ]

        results: dict[str, dict] = {}
        for term in search_terms:
            for item in self._search(term):
                title = unescape((item.get("title") or "").strip())
                item_id = str(item.get("id") or "").strip()
                if not title or not item_id:
                    continue
                link = f"https://www.grants.gov/search-results-detail/{item_id}"
                organization = item.get("agencyName") or item.get("agency") or item.get("agencyCode") or self.name
                deadline = item.get("closeDate") or ""
                opportunity = _normalized_opportunity(
                    title=title,
                    link=link,
                    source=self.name,
                    opportunity_type="funding",
                    organization=organization,
                    location="",
                    deadline=deadline,
                    summary=" ".join(
                        str(value)
                        for value in [
                            item.get("number", ""),
                            item.get("agencyCode", ""),
                            item.get("agencyName", ""),
                            item.get("oppStatus", ""),
                            item.get("docType", ""),
                        ]
                        if value
                    ),
                )
                results[opportunity["id"]] = opportunity
        return list(results.values())

    def _search(self, keyword: str) -> list[dict]:
        payload = {
            "rows": 25,
            "keyword": keyword,
            "oppStatuses": "forecasted|posted",
        }
        response = requests.post(
            self.api_url,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("errorcode") not in (0, "0", None):
            LOGGER.warning("Grants.gov returned an error for %r: %s", keyword, body.get("msg"))
            return []
        return body.get("data", {}).get("oppHits", [])


class PlaceholderSource(OpportunitySource):
    """Non-active interface for future API/RSS/safe HTML integrations."""

    def __init__(self, name: str, note: str) -> None:
        self.name = name
        self.note = note

    def fetch(self) -> list[dict]:
        LOGGER.info("Skipping placeholder source %s: %s", self.name, self.note)
        return []


def get_sources() -> list[OpportunitySource]:
    return [
        ReliefWebJobsSource(),
        GrantsGovFundingSource(),
        PlaceholderSource("fundsforNGOs", "Add RSS/API or terms-approved HTML collector later."),
        PlaceholderSource("Devex", "Add API/RSS or approved integration later."),
        PlaceholderSource("EU Funding & Tenders", "Add official API integration later."),
        PlaceholderSource("UNjobs", "Add RSS or terms-approved collector later."),
        PlaceholderSource("Ethiojobs", "Add RSS/API or terms-approved collector later."),
        PlaceholderSource("LinkedIn search links", "Add manual search URL generation; avoid automated scraping."),
    ]


def fetch_all_sources(sources: Iterable[OpportunitySource] | None = None) -> list[dict]:
    opportunities: list[dict] = []
    for source in sources or get_sources():
        try:
            LOGGER.info("Fetching %s", source.name)
            found = source.fetch()
            LOGGER.info("%s returned %s opportunities", source.name, len(found))
            opportunities.extend(found)
        except requests.HTTPError as exc:
            LOGGER.error("%s failed with HTTP error: %s", source.name, exc)
        except requests.RequestException as exc:
            LOGGER.error("%s failed with network error: %s", source.name, exc)
        except Exception:
            LOGGER.exception("%s failed unexpectedly", source.name)
    return opportunities


def _normalized_opportunity(
    *,
    title: str,
    link: str,
    source: str,
    opportunity_type: str,
    organization: str = "",
    location: str = "",
    deadline: str = "",
    summary: str = "",
) -> dict:
    return {
        "id": make_opportunity_id(title, link),
        "title": unescape(title),
        "link": link,
        "source": source,
        "type": opportunity_type,
        "organization": organization,
        "location": location,
        "deadline": deadline,
        "summary": summary,
        "date_found": utc_today(),
    }


def _names_from_list(items: list[dict]) -> list[str]:
    names = []
    for item in items or []:
        name = item.get("name") if isinstance(item, dict) else str(item)
        if name:
            names.append(name)
    return names


def _nested_date(date_payload: dict, key: str) -> str:
    value = (date_payload or {}).get(key, {})
    if isinstance(value, dict):
        return value.get("date") or value.get("original") or ""
    return str(value or "")


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)
