from __future__ import annotations

from urllib.parse import quote

from job_alert.models import Job
from .base import SourceAdapter
from .utils import plain_text


class LeverAdapter(SourceAdapter):
    def fetch(self) -> list[Job]:
        site = self.config.get("site")
        if not site:
            raise ValueError(f"{self.name}: site is required")
        payload = self.http.get_json(f"https://api.lever.co/v0/postings/{quote(str(site))}?mode=json")
        company = str(self.config.get("company", self.name))
        jobs: list[Job] = []
        for item in payload:
            categories = item.get("categories") or {}
            sections = [item.get("descriptionPlain") or plain_text(item.get("description"))]
            for section in item.get("lists") or []:
                sections.extend([section.get("text"), plain_text(section.get("content"))])
            sections.append(item.get("additionalPlain") or plain_text(item.get("additional")))
            description = "\n\n".join(str(section) for section in sections if section)
            jobs.append(Job(
                source=self.name,
                external_id=str(item.get("id", "")),
                title=str(item.get("text", "")),
                company=company,
                location=str(categories.get("location", "")),
                url=str(item.get("hostedUrl", item.get("applyUrl", ""))),
                description=description,
                posted_date=None,
            ))
        return jobs
