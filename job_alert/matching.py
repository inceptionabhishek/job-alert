from __future__ import annotations

import re
from typing import Any

from .models import Job, MatchResult

YEAR_PATTERNS = [
    re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:-|–|to)\s*(\d{1,2}(?:\.\d+)?)\s*(?:\+\s*)?years?\b", re.I),
    re.compile(r"\b(\d{1,2}(?:\.\d+)?)\+\s*years?\b", re.I),
    re.compile(r"\b(?:minimum|min\.?|at least)\s+(\d{1,2}(?:\.\d+)?)\s*years?\b", re.I),
    re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*years?\s+(?:of\s+)?(?:[a-z-]+\s+){0,8}experience\b", re.I),
]


def _hits(needles: list[str], text: str) -> list[str]:
    lower = text.casefold()
    return [needle for needle in needles if re.search(
        r"(?<!\w)" + re.escape(needle.casefold()).replace(r"\ ", r"\s+") + r"(?!\w)", lower
    )]


def extract_years(text: str) -> tuple[float, float | None] | None:
    candidates = []
    spans = []
    def number(value):
        numeric = float(value)
        return int(numeric) if numeric.is_integer() else numeric
    for index, pattern in enumerate(YEAR_PATTERNS):
        for match in pattern.finditer(text):
            if any(match.start() < end and match.end() > start for start, end in spans):
                continue
            spans.append(match.span())
            candidates.append((number(match.group(1)), number(match.group(2)) if index == 0 else None))
    if candidates:
        # Avoid accepting 1+ years in one skill when another requirement says 5+.
        return max(candidates, key=lambda years: years[0])
    if re.search(r"\bno (?:prior |professional |work )?experience (?:is )?(?:required|necessary)\b", text, re.I):
        return (0, 0)
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
    if not years and not config.get("allow_unknown_experience", True):
        return MatchResult(False, 0, ["experience unavailable; explicit requirement needed"])
    target_min = int(config.get("min_years", 0))
    target_max = int(config.get("max_years", 99))
    if years:
        exclusive = config.get("max_years_exclusive")
        if exclusive is not None and years[0] >= float(exclusive):
            return MatchResult(False, 0, [f"minimum required experience {years[0]} years is not below {exclusive}"])
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
