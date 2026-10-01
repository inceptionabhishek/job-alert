from __future__ import annotations

from dataclasses import dataclass, field
import logging

from .adapters import create_adapter
from .config import Settings
from .http import HttpClient
from .matching import match_job
from .notifier import TelegramNotifier
from .storage import JobStore

logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    fetched: int = 0
    new: int = 0
    matched: int = 0
    alerted: int = 0
    baselined: int = 0
    errors: int = 0
    queued: int = 0
    failed_sources: list[str] = field(default_factory=list)


def run(settings: Settings, *, dry_run: bool = False, only_source: str | None = None,
        baseline: bool = False) -> RunSummary:
    if baseline and (dry_run or settings.dry_run or not only_source):
        raise ValueError("Baseline requires one source and a non-dry run")
    dry_run = dry_run or settings.dry_run
    digest_enabled = bool(settings.raw.get("digest", {}).get("enabled", False))
    client = HttpClient(settings.http)
    store = JobStore(settings.database_path)
    database_exists = settings.database_path.exists()
    if not dry_run:
        store.initialize()
    notifier = None
    if settings.telegram_enabled and settings.telegram_token and settings.telegram_chat_id and not dry_run and not baseline and not digest_enabled:
        notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id, client)
    elif settings.telegram_enabled and not dry_run and not baseline and not digest_enabled:
        logger.warning("Telegram is enabled but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID is missing; matches will only be logged")

    summary = RunSummary()
    for source in settings.sources:
        if only_source and source.get("name") != only_source:
            continue
        source = dict(source)
        source["_config_dir"] = str(settings.config_path.parent)
        try:
            jobs = create_adapter(source, client).fetch()
            logger.info("Fetched %d jobs from %s", len(jobs), source.get("name", source.get("type")))
        except Exception:
            summary.errors += 1
            summary.failed_sources.append(str(source.get("name", source.get("type"))))
            logger.exception("Source failed: %s", source.get("name", source.get("type")))
            continue
        summary.fetched += len(jobs)
        for job in jobs:
            result = match_job(job, settings.matching)
            already_seen = store.contains(job) if (not dry_run or database_exists) else False
            if not already_seen:
                summary.new += 1
                if result.matched:
                    summary.matched += 1
                    logger.log(logging.DEBUG if baseline else logging.INFO,
                               "MATCH score=%d: %s — %s (%s)",
                               result.score, job.company, job.title, job.url)
                else:
                    logger.debug("No match: %s — %s (%s)", job.company, job.title, "; ".join(result.reasons))
            if dry_run:
                continue
            inserted = store.record(job, result.matched, baseline=baseline)
            if baseline:
                if inserted and result.matched:
                    summary.baselined += 1
                continue
            if result.matched and notifier and store.needs_alert(job):
                try:
                    notifier.send(job, result)
                    store.mark_alerted(job)
                    summary.alerted += 1
                except Exception:
                    summary.errors += 1
                    logger.exception("Telegram alert failed for %s", job.url)
    if digest_enabled and not dry_run and not baseline:
        summary.queued = store.enqueue_pending()
        store.record_check(summary.failed_sources)
    return summary
