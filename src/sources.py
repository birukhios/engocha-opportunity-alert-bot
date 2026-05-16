"""Opportunity source collectors.

The MVP prefers public APIs. Placeholder classes document future integrations
without scraping sites whose terms or robots rules need a separate review.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from html import unescape
from typing import Iterable
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from storage import make_opportunity_id, utc_today


LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 25
MAX_UNJOBS_DETAIL_PAGES_PER_LISTING = 20
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


class ReliefWebJobsRssSource(OpportunitySource):
    name = "ReliefWeb RSS"
    feed_url = "https://reliefweb.int/jobs/rss.xml?country=87"

    def fetch(self) -> list[dict]:
        response = requests.get(
            self.feed_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)

        opportunities = []
        for item in root.findall("./channel/item"):
            title = _xml_text(item, "title")
            link = _xml_text(item, "link")
            description = _html_to_text(_xml_text(item, "description"))
            if not title or not link:
                continue

            opportunities.append(
                _normalized_opportunity(
                    title=title,
                    link=link,
                    source=self.name,
                    opportunity_type="job",
                    organization=_extract_labeled_value(description, "Organization") or self.name,
                    location="Ethiopia",
                    deadline=_extract_labeled_value(description, "Closing date"),
                    summary=description,
                )
            )
        return opportunities


class UNjobsSource(OpportunitySource):
    name = "UNjobs"
    base_url = "https://unjobs.org"
    listing_urls = [
        "https://unjobs.org/duty_stations/ethiopia",
        "https://unjobs.org/duty_stations/remote",
    ]

    def fetch(self) -> list[dict]:
        vacancy_urls = []
        for listing_url in self.listing_urls:
            vacancy_urls.extend(self._vacancy_urls(listing_url)[:MAX_UNJOBS_DETAIL_PAGES_PER_LISTING])

        opportunities = []
        for vacancy_url in list(dict.fromkeys(vacancy_urls)):
            opportunity = self._fetch_vacancy(vacancy_url)
            if opportunity:
                opportunities.append(opportunity)
        return opportunities

    def _vacancy_urls(self, listing_url: str) -> list[str]:
        response = requests.get(
            listing_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for anchor in soup.select('a[href*="/vacancies/"]'):
            href = anchor.get("href")
            if href:
                urls.append(urljoin(self.base_url, href))
        return urls

    def _fetch_vacancy(self, vacancy_url: str) -> dict | None:
        response = requests.get(
            vacancy_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title_node = soup.find("h2") or soup.find("h1")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not title:
            return None

        page_text = soup.get_text(" ", strip=True)
        organization = _extract_labeled_value(page_text, "Organization") or self.name
        country = _extract_labeled_value(page_text, "Country")
        city = _extract_labeled_value(page_text, "City")
        deadline = _extract_labeled_value(page_text, "Closing date")
        location = ", ".join(part for part in [city, country] if part)
        if "remote" in title.lower() or "home based" in title.lower() or "home-based" in title.lower():
            location = location or "Remote / Home based"

        paragraphs = [node.get_text(" ", strip=True) for node in soup.find_all("p")[:8]]
        summary = " ".join(paragraphs) or page_text[:2500]
        return _normalized_opportunity(
            title=title,
            link=vacancy_url,
            source=self.name,
            opportunity_type="job",
            organization=organization,
            location=location,
            deadline=deadline,
            summary=summary,
        )


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
        ReliefWebJobsRssSource(),
        UNjobsSource(),
        ReliefWebJobsSource(),
        GrantsGovFundingSource(),
        PlaceholderSource("fundsforNGOs", "Add RSS/API or terms-approved HTML collector later."),
        PlaceholderSource("Devex", "Add API/RSS or approved integration later."),
        PlaceholderSource("EU Funding & Tenders", "Add official API integration later."),
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


def _xml_text(item: ElementTree.Element, tag: str) -> str:
    node = item.find(tag)
    return unescape((node.text or "").strip()) if node is not None else ""


def _extract_labeled_value(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}:\s*([^:]+?)(?=\s+[A-Z][A-Za-z /&()-]+:|$)", text)
    return match.group(1).strip() if match else ""
