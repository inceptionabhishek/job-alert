from __future__ import annotations

import json
from pathlib import Path

from job_alert.models import Job
from .base import SourceAdapter


class SampleAdapter(SourceAdapter):
    def fetch(self) -> list[Job]:
        path = Path(str(self.config.get("path", "")))
        if not path.is_absolute():
            base = Path(str(self.config.get("_config_dir", ".")))
            path = base / path
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [Job(
            source=self.name,
            external_id=str(item.get("id", "")),
            title=str(item.get("title", "")),
            company=str(item.get("company", self.name)),
            location=str(item.get("location", "")),
            url=str(item.get("url", "")),
            description=str(item.get("description", "")),
            posted_date=item.get("posted_date"),
        ) for item in payload]

