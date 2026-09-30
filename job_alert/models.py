from __future__ import annotations

from dataclasses import dataclass, field
import hashlib


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    posted_date: str | None = None

    @property
    def dedup_key(self) -> str:
        value = self.external_id or self.url or f"{self.company}|{self.title}|{self.location}"
        return hashlib.sha256(f"{self.source}|{value}".encode()).hexdigest()


@dataclass
class MatchResult:
    matched: bool
    score: int
    reasons: list[str] = field(default_factory=list)
