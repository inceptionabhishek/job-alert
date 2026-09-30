import csv
import hashlib
from pathlib import Path
import tempfile
import unittest

from job_alert.models import Job
from job_alert.report import csv_value, export_report, report_rows
from job_alert.storage import JobStore


class ReportTests(unittest.TestCase):
    def test_export_rechecks_rules_without_database_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "jobs.db"
            store = JobStore(db)
            store.initialize()
            job = Job("Sample", "1", "Backend Engineer <script>alert(1)</script>", "=Company", "India",
                      "javascript:alert(1)", "<img src=x onerror=alert(1)> Python. 3+ years.")
            store.record(job, False, baseline=True)
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            matching = {"title_keywords": ["backend engineer"], "skills": ["python"], "minimum_score": 4}
            self.assertEqual(export_report(db, root / "reports", matching), 1)
            row = report_rows(db, matching)[0]
            self.assertEqual((row["current_match"], row["saved_match"], row["status"]), ("yes", "no", "baseline"))
            self.assertEqual(before, hashlib.sha256(db.read_bytes()).hexdigest())
            html = (root / "reports/jobs.html").read_text()
            self.assertNotIn("<img src=x", html)
            self.assertNotIn('href="javascript:', html)
            self.assertIn("&lt;script&gt;", html)
            with (root / "reports/jobs.csv").open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["company"], "'=Company")

    def test_empty_database_still_exports_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "jobs.db"
            JobStore(db).initialize()
            self.assertEqual(export_report(db, root / "reports", {}), 0)
            self.assertIn("0 saved jobs", (root / "reports/jobs.html").read_text())

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "missing.db"
            with self.assertRaises(ValueError):
                export_report(db, db.parent / "reports", {})
            self.assertFalse(db.exists())

    def test_csv_preserves_zero_and_neutralizes_formulas(self):
        self.assertEqual(csv_value(0), "0")
        for value in ["=SUM(1,2)", " +CMD", "@SUM(1)", "\tformula"]:
            self.assertTrue(csv_value(value).startswith("'"))
