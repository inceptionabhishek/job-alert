from __future__ import annotations

from urllib.parse import quote

from job_alert.models import Job
from .base import SourceAdapter
from .utils import plain_text


class GreenhouseAdapter(SourceAdapter):
    def fetch(self) -> list[Job]:
        token = self.config.get("board_token")
        if not token:
            raise ValueError(f"{self.name}: board_token is required")
        url = f"https://boards-api.greenhouse.io/v1/boards/{quote(str(token))}/jobs?content=true"
        payload = self.http.get_json(url)
        company = str(self.config.get("company", self.name))
        return [
            Job(
                source=self.name,
                external_id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                company=company,
                location=str((item.get("location") or {}).get("name", "")),
                url=str(item.get("absolute_url", "")),
                description=plain_text(item.get("content")),
                posted_date=item.get("updated_at"),
            )
            for item in payload.get("jobs", [])
        ]

