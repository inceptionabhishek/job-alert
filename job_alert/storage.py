from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterator

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    dedup_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    url TEXT,
    description TEXT,
    posted_date TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    matched INTEGER NOT NULL DEFAULT 0,
    alerted_at TEXT,
    baselined_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_source_external_id ON jobs(source, external_id);
"""


class JobStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "baselined_at" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN baselined_at TEXT")

    def contains(self, job: Job) -> bool:
        with self.connect() as connection:
            row = connection.execute("SELECT 1 FROM jobs WHERE dedup_key = ?", (job.dedup_key,)).fetchone()
            return row is not None

    def record(self, job: Job, matched: bool, *, baseline: bool = False) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO jobs
                (dedup_key, source, external_id, title, company, location, url, description,
                 posted_date, first_seen_at, last_seen_at, matched, baselined_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job.dedup_key, job.source, job.external_id, job.title, job.company, job.location,
                 job.url, job.description, job.posted_date, now, now, int(matched), now if baseline else None),
            )
            inserted = cursor.rowcount == 1
            if not inserted:
                connection.execute("UPDATE jobs SET last_seen_at = ? WHERE dedup_key = ?", (now, job.dedup_key))
            return inserted

    def mark_alerted(self, job: Job) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute("UPDATE jobs SET alerted_at = ? WHERE dedup_key = ?", (now, job.dedup_key))

    def needs_alert(self, job: Job) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT matched, alerted_at, baselined_at FROM jobs WHERE dedup_key = ?", (job.dedup_key,)
            ).fetchone()
            return bool(row and row[0] and row[1] is None and row[2] is None)
