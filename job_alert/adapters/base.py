from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from job_alert.models import Job


class SourceAdapter(ABC):
    def __init__(self, config: dict[str, Any], http: Any):
        self.config = config
        self.http = http
        self.name = str(config.get("name", config.get("type", "source")))

    @abstractmethod
    def fetch(self) -> list[Job]:
        raise NotImplementedError

