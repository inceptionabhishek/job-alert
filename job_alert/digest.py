"""Durable multipart delivery: acknowledged parts are not sent again."""
from datetime import datetime, timezone
import logging
import time
from zoneinfo import ZoneInfo

from .matching import extract_years, match_job
from .models import Job
from .ranking import PreferenceRank, rank_job
from .storage import JobStore

logger = logging.getLogger(__name__)


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def compact(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if utf16_length(text) <= limit:
        return text
    result, used = [], 0
    for char in text:
        width = utf16_length(char)
        if used + width > limit - 1:
            break
        result.append(char)
        used += width
    return "".join(result) + "…"


def build_parts(ranked: list[tuple[Job, PreferenceRank]], day: str, failures: list[str]) -> list[tuple[str, list[str]]]:
    header = f"📬 Job digest — {day} (IST)\n{len(ranked)} new matching jobs (including pending retries)"
    if failures:
        header += "\n⚠ Source failures today: " + compact(", ".join(failures), 300) + ". Results may be incomplete."
    if not ranked:
        header += "\nNo new matching jobs to send."
    groups = []
    text, keys = header, []
    for index, (job, rank) in enumerate(ranked, 1):
        years = extract_years(job.description)
        entry = (f"\n\n{index}. {compact(job.company, 100)} — {compact(job.title, 180)}\n"
                 f"{compact(job.location or 'Location unknown', 120)} · Minimum experience: {years[0] if years else 'unknown'} years\n"
                 f"Preference score: {rank.score}/10\nWhy: {compact('; '.join(rank.reasons), 550)}\n"
                 f"Apply: {job.url if utf16_length(job.url) <= 1000 else 'See full application URL in the HTML/CSV report'}")
        # Leave space for multipart numbering; UTF-16 accounting covers emoji.
        if utf16_length(text + entry) > 3900:
            groups.append((text, keys))
            text, keys = header, []
        text += entry
        keys.append(job.dedup_key)
    groups.append((text, keys))
    return [(f"{text}\n\nPart {index}/{len(groups)}", keys) for index, (text, keys) in enumerate(groups, 1)]


def send_digest(settings, store: JobStore, notifier) -> int:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    since = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    failures = store.recent_failures(since)
    ranked = []
    dropped = []
    enabled = {source.get("name") for source in settings.sources}
    for row in store.queued_jobs():
        job = Job(**{key: row[key] or "" for key in (
            "source", "external_id", "title", "company", "location", "url", "description", "posted_date"
        )})
        if job.source not in enabled or not match_job(job, settings.matching).matched:
            dropped.append(job.dedup_key)
            continue
        ranked.append((job, rank_job(job, settings.raw.get("ranking", {}))))
    store.drop_queued(dropped)
    ranked.sort(key=lambda item: (-item[1].score, item[0].company.casefold(), item[0].title.casefold(), item[0].dedup_key))
    if ranked or not store.pending_parts():
        store.stage_parts(build_parts(ranked, now.date().isoformat(), failures))
    delivered = 0
    for index, part in enumerate(store.pending_parts()):
        if index:
            time.sleep(1.1) # Pace multipart delivery to a single Telegram chat.
        notifier.send_text(part["text"])
        delivered += store.complete_part(part)
    logger.info("Digest delivered %d job entries", delivered)
    return delivered
