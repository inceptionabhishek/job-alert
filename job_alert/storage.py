from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import json
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
CREATE TABLE IF NOT EXISTS digest_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    job_keys TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS digest_queue (
    dedup_key TEXT PRIMARY KEY,
    queued_at TEXT NOT NULL,
    part_id INTEGER
);
CREATE TABLE IF NOT EXISTS fetch_checks (
    checked_at TEXT PRIMARY KEY,
    failed_sources TEXT NOT NULL
);
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

    def enqueue_pending(self) -> int:
        """Also preserve unsent matches from pre-digest versions; no baseline replay."""
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO digest_queue (dedup_key, queued_at) "
                "SELECT dedup_key, ? FROM jobs WHERE matched=1 AND alerted_at IS NULL AND baselined_at IS NULL",
                (datetime.now(timezone.utc).isoformat(),),
            )
            return cursor.rowcount

    def queued_jobs(self) -> list[dict]:
        with self.connect() as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(
                "SELECT jobs.* FROM jobs JOIN digest_queue USING(dedup_key) WHERE part_id IS NULL"
            )]

    def drop_queued(self, keys: list[str]) -> None:
        with self.connect() as connection:
            connection.executemany("DELETE FROM digest_queue WHERE dedup_key=? AND part_id IS NULL", [(key,) for key in keys])

    def stage_parts(self, parts: list[tuple[str, list[str]]]) -> None:
        with self.connect() as connection:
            for text, keys in parts:
                cursor = connection.execute("INSERT INTO digest_parts (text, job_keys, created_at) VALUES (?, ?, ?)",
                                            (text, json.dumps(keys), datetime.now(timezone.utc).isoformat()))
                connection.executemany("UPDATE digest_queue SET part_id=? WHERE dedup_key=? AND part_id IS NULL",
                                       [(cursor.lastrowid, key) for key in keys])

    def pending_parts(self) -> list[dict]:
        with self.connect() as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute("SELECT * FROM digest_parts WHERE sent_at IS NULL ORDER BY id")]

    def complete_part(self, part: dict) -> int:
        keys = json.loads(part["job_keys"])
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute("UPDATE digest_parts SET sent_at=? WHERE id=?", (now, part["id"]))
            connection.executemany("UPDATE jobs SET alerted_at=? WHERE dedup_key=?", [(now, key) for key in keys])
            connection.executemany("DELETE FROM digest_queue WHERE dedup_key=?", [(key,) for key in keys])
        return len(keys)

    def record_check(self, failed_sources: list[str]) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO fetch_checks VALUES (?, ?)",
                               (datetime.now(timezone.utc).isoformat(), json.dumps(failed_sources)))
            connection.execute("DELETE FROM fetch_checks WHERE checked_at < datetime('now', '-7 days')")

    def recent_failures(self, since: str) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT failed_sources FROM fetch_checks WHERE checked_at>=?", (since,)).fetchall()
        return sorted({source for row in rows for source in json.loads(row[0])})
