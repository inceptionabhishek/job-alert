from pathlib import Path
import sqlite3
import tempfile
import unittest

from job_alert.models import Job
from job_alert.storage import JobStore


class StorageTests(unittest.TestCase):
    def test_existing_database_gets_baseline_column(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.db"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE jobs (dedup_key TEXT PRIMARY KEY, source TEXT, external_id TEXT, "
                                   "title TEXT, company TEXT, location TEXT, url TEXT, description TEXT, "
                                   "posted_date TEXT, first_seen_at TEXT, last_seen_at TEXT, "
                                   "matched INTEGER, alerted_at TEXT)")
            store = JobStore(path)
            store.initialize()
            with sqlite3.connect(path) as connection:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            self.assertIn("baselined_at", columns)

    def test_duplicate_is_not_inserted_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.db")
            store.initialize()
            job = Job("source", "123", "Backend Engineer", "Acme", "Remote", "https://example.test/123")
            self.assertTrue(store.record(job, True))
            self.assertFalse(store.record(job, True))
            self.assertTrue(store.contains(job))


if __name__ == "__main__":
    unittest.main()
