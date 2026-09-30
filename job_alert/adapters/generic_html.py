from __future__ import annotations

from html.parser import HTMLParser
import json
from typing import Any

from job_alert.models import Job
from .base import SourceAdapter
from .utils import plain_text


class JsonLdExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_json_ld = False
        self.parts: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "script" and (attributes.get("type") or "").lower() == "application/ld+json":
            self.in_json_ld = True
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_json_ld:
            self.blocks.append("".join(self.parts))
            self.in_json_ld = False


def _walk(value: Any):
    if isinstance(value, dict):
        if value.get("@type") == "JobPosting":
            yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _location(item: dict[str, Any]) -> str:
    locations = item.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    values = []
    for location in locations:
        address = (location or {}).get("address") or {}
        if isinstance(address, str):
            values.append(address)
        else:
            values.append(", ".join(filter(None, [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")])))
    return "; ".join(filter(None, values))


class GenericHtmlAdapter(SourceAdapter):
    """Reads standards-based schema.org JobPosting JSON-LD from an HTML page."""

    def fetch(self) -> list[Job]:
        url = str(self.config.get("url", ""))
        if not url:
            raise ValueError(f"{self.name}: url is required")
        parser = JsonLdExtractor()
        parser.feed(self.http.get_text(url))
        items: list[dict[str, Any]] = []
        for block in parser.blocks:
            try:
                items.extend(_walk(json.loads(block)))
            except json.JSONDecodeError:
                continue
        jobs = []
        for item in items:
            organization = item.get("hiringOrganization") or {}
            company = organization.get("name") if isinstance(organization, dict) else organization
            job_url = str(item.get("url") or url)
            identifier = item.get("identifier") or {}
            external_id = identifier.get("value") if isinstance(identifier, dict) else identifier
            jobs.append(Job(
                source=self.name,
                external_id=str(external_id or job_url),
                title=str(item.get("title", "")),
                company=str(company or self.config.get("company", self.name)),
                location=_location(item),
                url=job_url,
                description=plain_text(item.get("description")),
                posted_date=item.get("datePosted"),
            ))
        return jobs

