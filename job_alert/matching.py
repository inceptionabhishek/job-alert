from __future__ import annotations

import re
from typing import Any

from .models import Job, MatchResult

YEAR_PATTERNS = [
    re.compile(r"\b(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:\+\s*)?years?\b", re.I),
    re.compile(r"\b(\d{1,2})\+\s*years?\b", re.I),
    re.compile(r"\b(?:minimum|min\.?|at least)\s+(\d{1,2})\s*years?\b", re.I),
]


def _hits(needles: list[str], text: str) -> list[str]:
    lower = text.casefold()
    return [needle for needle in needles if re.search(
        r"(?<!\w)" + re.escape(needle.casefold()).replace(r"\ ", r"\s+") + r"(?!\w)", lower
    )]


def extract_years(text: str) -> tuple[int, int | None] | None:
    for index, pattern in enumerate(YEAR_PATTERNS):
        match = pattern.search(text)
        if match:
            if index == 0:
                return int(match.group(1)), int(match.group(2))
            return int(match.group(1)), None
    return None


def match_job(job: Job, config: dict[str, Any]) -> MatchResult:
    title = re.sub(r"\s*[-–—]\s*", " ", job.title.casefold())
    body = f"{job.title} {job.description}".casefold()
    title_hits = _hits(config.get("title_keywords", []), title)
    exclude_hits = _hits(config.get("exclude_title_keywords", []), title)
    exclude_hits += _hits(config.get("exclude_keywords", []), body)
    if exclude_hits:
        return MatchResult(False, 0, [f"excluded: {', '.join(exclude_hits)}"])
    if config.get("require_title_keyword", True) and not title_hits:
        return MatchResult(False, 0, ["no target title keyword"])

    locations = config.get("locations", [])
    location_hits = _hits(locations, job.location)
    if locations and job.location and not location_hits:
        return MatchResult(False, 0, ["location outside preferences"])
    if locations and not job.location and not config.get("allow_unknown_location", True):
        return MatchResult(False, 0, ["location unavailable"])

    years = extract_years(body)
    target_min = int(config.get("min_years", 0))
    target_max = int(config.get("max_years", 99))
    if years:
        found_min, found_max = years
        found_max = found_max if found_max is not None else 99
        if found_min > target_max or found_max < target_min:
            return MatchResult(False, 0, [f"experience requirement {years[0]}-{years[1] or '+'} years is outside target"])

    include_hits = _hits(config.get("include_keywords", []), body)
    skill_hits = _hits(config.get("skills", []), body)
    score = (3 if title_hits else 0) + min(3, len(include_hits)) + min(3, len(skill_hits)) + (2 if location_hits else 0)
    reasons = []
    if title_hits:
        reasons.append(f"title: {', '.join(title_hits)}")
    if include_hits:
        reasons.append(f"keywords: {', '.join(include_hits)}")
    if skill_hits:
        reasons.append(f"skills: {', '.join(skill_hits)}")
    if location_hits:
        reasons.append(f"location: {', '.join(location_hits)}")
    if years:
        reasons.append(f"experience: {years[0]}-{years[1] or '+'} years")
    else:
        reasons.append("experience: unknown (manual review)")
    minimum = int(config.get("minimum_score", 4))
    if score < minimum:
        reasons.append(f"score {score} below minimum {minimum}")
    return MatchResult(score >= minimum, score, reasons or ["no positive signals"])
