"""Preference points only: never changes eligibility."""
from dataclasses import dataclass
import re

from .matching import _hits
from .models import Job


@dataclass
class PreferenceRank:
    score: int
    reasons: list[str]


def rank_job(job: Job, config: dict) -> PreferenceRank:
    title = re.sub(r"\s*[-–—]\s*", " ", job.title.casefold())
    body = f"{title} {job.description}"
    titles = _hits(config.get("preferred_title_keywords", []), title)
    skills = list(dict.fromkeys(_hits(config.get("skills", []), body)))[:4]
    topics = list(dict.fromkeys(_hits(config.get("topics", []), body)))[:3]
    reasons = []
    if titles:
        reasons.append(f"title: {titles[0]} (+3)")
    reasons.extend(f"skill: {skill} (+1)" for skill in skills)
    reasons.extend(f"topic: {topic} (+1)" for topic in topics)
    return PreferenceRank((3 if titles else 0) + len(skills) + len(topics), reasons or ["no configured preference signals (+0)"])
